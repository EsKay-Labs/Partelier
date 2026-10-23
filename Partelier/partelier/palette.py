"""HTML tool library lifecycle. This module performs no geometry writes."""

import json
import traceback
import time
from pathlib import Path
from urllib.parse import quote

import adsk.core

from .palette_protocol import PROTOCOL_VERSION, SESSION_ACTIONS, SNAP_SESSION_ACTIONS, PATTERN_SESSION_ACTIONS, read_request
from .tools.hinge.settings import HingeSettings
from .tools.snap_fit.settings import SnapFitSettings
from .tools.patterns.settings import PatternSettings
from .diagnostics import emit


COMMAND_ID = "sktech_partelier_library_b520ea78"
PALETTE_ID = "sktech_partelier_library_palette_b520ea78"


class ToolLibrary:
    """Own one launcher, palette and their event references."""

    def __init__(self):
        self._created_handler = None
        self._html_handler = None
        self._palette = None
        self._workspace_id = None
        self._panel_id = None
        self._input_check_id = None
        self._report_error = None
        self._hinge_commands = None
        self._snap_commands = None
        self._pattern_commands = None

    def start(self, workspace_id, panel_id, input_check_id, report_error, hinge_commands=None, snap_commands=None, pattern_commands=None):
        if self._created_handler is not None:
            return
        self._workspace_id = workspace_id
        self._panel_id = panel_id
        self._input_check_id = input_check_id
        self._report_error = report_error
        self._hinge_commands = hinge_commands
        self._snap_commands = snap_commands
        self._pattern_commands = pattern_commands
        ui = adsk.core.Application.get().userInterface
        panel = self._panel(ui)
        if panel is None:
            raise RuntimeError("The Fusion Design Add-Ins panel is unavailable.")
        definition = ui.commandDefinitions.itemById(COMMAND_ID)
        if definition is None:
            definition = ui.commandDefinitions.addButtonDefinition(
                COMMAND_ID,
                "Partelier: Tool library",
                "Configure pin hinges and snap-fits, or explore the planned CAD helpers.",
            )
        self._created_handler = _LauncherCreated(self)
        definition.commandCreated.add(self._created_handler)
        if panel.controls.itemById(COMMAND_ID) is None:
            panel.controls.addCommand(definition)
        if self._has_palette_hinge():
            self._hinge_commands.set_state_callback(self._publish_hinge_state)
        if self._has_palette_snap():
            self._snap_commands.set_state_callback(self._publish_snap_state)
        if self._has_palette_pattern():
            self._pattern_commands.set_state_callback(lambda snapshot:self._publish_state("pattern_state",snapshot))

    @staticmethod
    def _has_palette_manager(manager):
        return manager is not None and all(
            callable(getattr(manager, name, None)) for name in
            ("set_state_callback", "begin_palette", "palette_action", "palette_state")
        )

    def _has_palette_hinge(self):
        return self._has_palette_manager(self._hinge_commands)

    def _has_palette_snap(self):
        return self._has_palette_manager(self._snap_commands)

    def _has_palette_pattern(self):
        return self._has_palette_manager(self._pattern_commands)

    def _require_idle_other_tool(self, manager, name):
        """One palette selection/preview owner at a time, including error recovery."""
        if not self._has_palette_manager(manager):
            return
        if getattr(manager,"busy",False) is True:
            raise ValueError(f"Wait for the current {name} operation to finish.")
        snapshot = manager.palette_state()
        if (isinstance(snapshot, dict) and isinstance(snapshot.get("sessionId"), str)
                and snapshot["sessionId"] and snapshot.get("phase") not in {"idle", "created", "cancelled"}):
            raise ValueError(f"Finish or cancel the current {name} before starting another tool.")

    def _publish_hinge_state(self, snapshot):
        self._publish_state("hinge_state", snapshot)

    def _publish_snap_state(self, snapshot):
        self._publish_state("snap_state", snapshot)

    def _publish_state(self, action, snapshot):
        """Best-effort UI notification; a closed palette cannot fail geometry."""
        palette = self._palette
        if self._created_handler is None or palette is None or not palette.isValid:
            return
        try:
            # Qt sends an asynchronous 'response' acknowledgement. An empty
            # immediate return is normal and must not be treated as failure.
            palette.sendInfoToHTML(action, json.dumps(snapshot))
            if action=='pattern_state':
                emit('bridge.push.sent',action=action,session_id=snapshot.get('sessionId'),
                     revision=snapshot.get('revision'),phase=snapshot.get('phase'),preview_current=snapshot.get('previewCurrent'))
        except Exception:
            emit('bridge.push.error',action=action,error=traceback.format_exc())
            adsk.core.Application.get().log("Partelier could not update the tool library state.")

    def _panel(self, ui):
        workspace = ui.workspaces.itemById(self._workspace_id)
        return workspace.toolbarPanels.itemById(self._panel_id) if workspace else None

    def _release_palette(self):
        palette = self._palette
        self._palette = None
        try:
            if palette is not None and palette.isValid:
                try:
                    if self._html_handler is not None:
                        palette.incomingFromHTML.remove(self._html_handler)
                finally:
                    palette.deleteMe()
        finally:
            self._html_handler = None

    def show(self):
        ui = adsk.core.Application.get().userInterface
        palette = self._palette
        if palette is None or not palette.isValid:
            self._release_palette()
            palette = ui.palettes.itemById(PALETTE_ID)
            if palette is not None:
                palette.deleteMe()
            bundle = Path(__file__).resolve().parent.parent
            version = json.loads((bundle / "Partelier.manifest").read_text(encoding="utf-8"))["version"]
            html_uri = (Path(__file__).parent / "ui" / "palette.html").resolve().as_uri() + "?v=" + quote(str(version), safe="")
            palette = ui.palettes.add(
                PALETTE_ID, "Partelier · Tool library", html_uri,
                False, True, True, 540, 840, True,
            )
            if palette is None:
                raise RuntimeError("Fusion could not open the tool library.")
            self._palette = palette
            self._html_handler = _HTMLMessage(self)
            palette.incomingFromHTML.add(self._html_handler)
            palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        palette.isVisible = True

    def handle_message(self, action, raw_data):
        if self._created_handler is None:
            raise RuntimeError("The tool library has stopped. Run the add-in again.")
        request = read_request(action, raw_data)
        if action=='diagnostic_log':
            for entry in request.diagnostics:
                emit('ui.'+entry['event'],ui_at=entry['at'],context=entry['context'])
            return json.dumps({'protocol':PROTOCOL_VERSION,'requestId':request.request_id,'ok':True})
        snapshot = None
        snap_snapshot = None
        pattern_snapshot = None
        if action == "open_input_check":
            ui = adsk.core.Application.get().userInterface
            command = ui.commandDefinitions.itemById(self._input_check_id)
            if command is None or not command.isValid or not command.execute():
                raise RuntimeError("The input checker is unavailable. Stop and Run the add-in.")
        elif action == "hinge_begin" or action in SESSION_ACTIONS:
            if not self._has_palette_hinge():
                raise RuntimeError("The palette hinge session is unavailable. Stop and Run the add-in.")
            if action == "hinge_begin":
                self._require_idle_other_tool(self._pattern_commands,"pattern")
                self._require_idle_other_tool(self._snap_commands, "snap-fit")
                snapshot = self._hinge_commands.begin_palette(request.settings.to_dict(), editing=request.editing)
            else:
                snapshot = self._hinge_commands.palette_action(
                    action, request.session_id, revision=request.revision,
                    settings_dict=request.settings.to_dict() if request.settings is not None else None,
                    target=request.target,
                )
        elif action == "snap_begin" or action in SNAP_SESSION_ACTIONS:
            if not self._has_palette_snap():
                raise RuntimeError("The palette snap-fit session is unavailable. Stop and Run the add-in.")
            if action == "snap_begin":
                self._require_idle_other_tool(self._pattern_commands,"pattern")
                self._require_idle_other_tool(self._hinge_commands, "hinge")
                snap_snapshot = self._snap_commands.begin_palette(request.settings.to_dict(), editing=request.editing)
            else:
                snap_snapshot = self._snap_commands.palette_action(
                    action, request.session_id, revision=request.revision,
                    settings_dict=request.settings.to_dict() if request.settings is not None else None,
                    target=request.target,
                )
        elif action == "pattern_begin" or action in PATTERN_SESSION_ACTIONS:
            if not self._has_palette_pattern():
                raise RuntimeError("The pattern session is unavailable. Stop and Run Partelier.")
            if action=="pattern_begin":
                self._require_idle_other_tool(self._hinge_commands,"hinge")
                self._require_idle_other_tool(self._snap_commands,"snap-fit")
                pattern_snapshot=self._pattern_commands.begin_palette(request.settings.to_dict(),editing=request.editing)
            else:
                pattern_snapshot=self._pattern_commands.palette_action(action,request.session_id,revision=request.revision,
                    settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        elif action=="pattern_status":
            if not self._has_palette_pattern():raise RuntimeError("Run Partelier to enable patterns.")
            pattern_snapshot=self._pattern_commands.palette_state()
        elif action == "snap_status":
            if not self._has_palette_snap():
                raise RuntimeError("The palette snap-fit session is unavailable. Stop and Run the add-in.")
            snap_snapshot = self._snap_commands.palette_state()
        elif action == "hinge_status":
            if not self._has_palette_hinge():
                raise RuntimeError("The palette hinge session is unavailable. Stop and Run the add-in.")
            snapshot = self._hinge_commands.palette_state()
        elif action in {"hinge_create", "hinge_edit"}:
            self._require_idle_other_tool(self._pattern_commands,"pattern")
            if self._hinge_commands is None:
                raise RuntimeError("The hinge tool is unavailable. Stop and Run the add-in.")
            self._require_idle_other_tool(self._snap_commands, "snap-fit")
            if action == "hinge_create":
                self._hinge_commands.launch_create(request.settings.to_dict())
            else:
                self._hinge_commands.launch_edit()
        capabilities = ["input-check"]
        if self._hinge_commands is not None:
            capabilities.extend(["hinge-create", "hinge-edit"])
        if self._has_palette_hinge():
            capabilities.append("hinge-palette")
            if snapshot is None:
                snapshot = self._hinge_commands.palette_state()
        if self._has_palette_snap():
            capabilities.extend(["snap-palette", "snap-edit"])
            if snap_snapshot is None:
                snap_snapshot = self._snap_commands.palette_state()
        if self._has_palette_pattern():
            capabilities.extend(["pattern-palette","pattern-edit"])
            if pattern_snapshot is None:pattern_snapshot=self._pattern_commands.palette_state()
        return json.dumps({
            "protocol": PROTOCOL_VERSION,
            "requestId": request.request_id,
            "ok": True,
            "capabilities": capabilities,
            "hingeDefaults": HingeSettings().to_dict(),
            "hingeState": snapshot,
            "snapDefaults": SnapFitSettings().to_dict(),
            "snapState": snap_snapshot,
            "patternDefaults": PatternSettings().to_dict(),
            "patternState": pattern_snapshot,
        })

    def stop(self):
        ui = adsk.core.Application.get().userInterface
        errors = []

        def attempt(operation):
            try:
                operation()
            except Exception:
                errors.append(traceback.format_exc())

        if ui.activeCommand == COMMAND_ID:
            attempt(ui.terminateActiveCommand)
        if self._has_palette_hinge():
            attempt(lambda: self._hinge_commands.set_state_callback(None))
        if self._has_palette_snap():
            attempt(lambda: self._snap_commands.set_state_callback(None))
        if self._has_palette_pattern():
            attempt(lambda:self._pattern_commands.set_state_callback(None))
        attempt(self._release_palette)
        panel = self._panel(ui) if self._workspace_id else None
        control = panel.controls.itemById(COMMAND_ID) if panel else None
        if control is not None:
            attempt(control.deleteMe)
        definition = ui.commandDefinitions.itemById(COMMAND_ID)
        if definition is not None:
            if self._created_handler is not None:
                attempt(lambda: definition.commandCreated.remove(self._created_handler))
            attempt(definition.deleteMe)
        self._created_handler = None
        self._hinge_commands = None
        self._snap_commands = None
        self._pattern_commands = None
        for error in errors:
            adsk.core.Application.get().log(f"Partelier UI cleanup failed:\n{error}")


class _LauncherCreated(adsk.core.CommandCreatedEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        try:
            args.command.isExecutedWhenPreEmpted = False
            self.owner.show()
        except Exception:
            try:
                self.owner._release_palette()
            finally:
                self.owner._report_error("Partelier could not open the tool library")


class _HTMLMessage(adsk.core.HTMLEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        if args.action == "response":
            args.returnData = "OK"
            return
        started=time.perf_counter()
        request_id=None
        try:
            payload=json.loads(args.data)
            if isinstance(payload,dict):request_id=payload.get('requestId')
        except Exception:pass
        trace=args.action!='diagnostic_log'
        if trace:emit('bridge.request.begin',action=args.action,request_id=request_id)
        try:
            args.returnData = self.owner.handle_message(args.action, args.data)
            if trace:emit('bridge.request.end',action=args.action,request_id=request_id,elapsed_ms=(time.perf_counter()-started)*1000)
        except (ValueError, RuntimeError) as error:
            emit('bridge.request.error',action=args.action,request_id=request_id,error=str(error),elapsed_ms=(time.perf_counter()-started)*1000)
            args.returnData = json.dumps({"protocol": PROTOCOL_VERSION, "ok": False, "message": str(error)})
        except Exception:
            emit('bridge.request.exception',action=args.action,request_id=request_id,error=traceback.format_exc(),elapsed_ms=(time.perf_counter()-started)*1000)
            args.returnData = json.dumps({"protocol": PROTOCOL_VERSION, "ok": False, "message": "Fusion could not complete the request. See its log."})
            adsk.core.Application.get().log(f"Partelier HTML bridge request failed:\n{traceback.format_exc()}")
