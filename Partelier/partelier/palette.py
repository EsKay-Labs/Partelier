"""HTML tool library lifecycle. This module performs no geometry writes."""

import json
import traceback
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import adsk.core

from .palette_protocol import PROTOCOL_VERSION, SESSION_ACTIONS, SNAP_SESSION_ACTIONS, PATTERN_SESSION_ACTIONS, read_request
from .tools.hinge.settings import HingeSettings
from .tools.snap_fit.settings import SnapFitSettings
from .tools.patterns.settings import PatternSettings
from .tools.fans.settings import FanSettings
from .tools.mechanisms.settings import MechanismSettings
from .tools.finishing.settings import FinishingSettings
from .tools.threads.settings import ThreadSettings
from .tools.knurl.settings import KnurlSettings
from .diagnostics import emit
from . import operations


COMMAND_ID = "sktech_partelier_library_b520ea78"
PALETTE_ID = "sktech_partelier_library_palette_b520ea78"


class ToolLibrary:
    """Own one launcher, palette and their event references."""

    def __init__(self):
        self._created_handler = None
        self._html_handler = None
        self._close_handler = None
        self._page_generation = 0
        self._palette_closed = False
        self._palette = None
        self._workspace_id = None
        self._panel_id = None
        self._input_check_id = None
        self._report_error = None
        self._hinge_commands = None
        self._snap_commands = None
        self._pattern_commands = None
        self._detail_commands = None
        self._fan_commands = None
        self._finishing_commands = None
        self._thread_commands = None
        self._knurling_commands = None
        self._mechanism_commands = None
        self._operation_delete = None

    def start(self, workspace_id, panel_id, input_check_id, report_error, hinge_commands=None, snap_commands=None, pattern_commands=None, detail_commands=None, fan_commands=None, mechanism_commands=None, finishing_commands=None, thread_commands=None, knurling_commands=None):
        if self._created_handler is not None:
            return
        self._palette_closed = False
        self._workspace_id = workspace_id
        self._panel_id = panel_id
        self._input_check_id = input_check_id
        self._report_error = report_error
        self._hinge_commands = hinge_commands
        self._snap_commands = snap_commands
        self._pattern_commands = pattern_commands
        self._detail_commands = detail_commands
        self._fan_commands = fan_commands
        self._finishing_commands = finishing_commands
        self._knurling_commands = knurling_commands
        if self._has_palette_manager(knurling_commands):knurling_commands.set_state_callback(lambda state:self._publish_state("knurling_state",state))
        self._thread_commands = thread_commands
        if self._has_palette_manager(thread_commands):thread_commands.set_state_callback(lambda state:self._publish_state("thread_state",state))
        if self._has_palette_manager(finishing_commands):finishing_commands.set_state_callback(lambda state:self._publish_state("finishing_state",state))
        self._mechanism_commands = mechanism_commands
        if self._has_palette_manager(mechanism_commands):mechanism_commands.set_state_callback(lambda state:self._publish_state("mechanism_state",state))
        if self._has_palette_manager(fan_commands):fan_commands.set_state_callback(lambda state:self._publish_state('fan_state',state))
        if self._has_palette_manager(detail_commands):detail_commands.set_state_callback(lambda state:self._publish_state('detail_state',state))
        ui = adsk.core.Application.get().userInterface
        panel = self._panel(ui)
        if panel is None:
            raise RuntimeError("The Fusion Design Add-Ins panel is unavailable.")
        definition = ui.commandDefinitions.itemById(COMMAND_ID)
        if definition is None:
            definition = ui.commandDefinitions.addButtonDefinition(
                COMMAND_ID,
                "Partelier",
                "Open Partelier: printable details, patterns, mechanisms and threads.",
                str(Path(__file__).resolve().parent / "resources" / "launcher"),
            )
        self._operation_delete=operations.DeleteCommand(self._operations_changed)
        self._operation_delete.start(adsk.core)
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

    def _operations_changed(self,message):
        if self._palette_closed:return
        import adsk.fusion
        design=adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
        value={'items':operations.snapshot(design),'message':message}
        automatic=getattr(self,'_automatic_updates',None)
        if automatic is not None:value['autoUpdate']=automatic.enabled()
        self._publish_state('operations_state',value)

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
        if self._palette_closed or self._created_handler is None or palette is None or not palette.isValid:
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
                    if self._close_handler is not None:
                        palette.closed.remove(self._close_handler)
                finally:
                    palette.deleteMe()
        finally:
            self._html_handler = None
            self._close_handler = None

    def close(self):
        """Retire this page before cancelling tools; stale HTML cannot restart it."""
        self._palette_closed = True
        self._page_generation += 1
        errors = []
        automatic=getattr(self,'_automatic_updates',None)
        if automatic:automatic.cancel_palette()
        for manager in (self._hinge_commands, self._snap_commands, self._pattern_commands, self._detail_commands, self._fan_commands, self._mechanism_commands, self._finishing_commands, self._thread_commands, self._knurling_commands, self._operation_delete):
            cancel = getattr(manager, 'cancel_palette', None)
            if callable(cancel):
                try:
                    cancel()
                except Exception as error:
                    errors.append(str(error))
                    adsk.core.Application.get().log('Partelier Close cleanup failed:\n'+traceback.format_exc())
        try:
            self._release_palette()
        except Exception as error:
            errors.append(str(error))
        if errors:
            raise RuntimeError('Partelier could not finish cancelling. '+ '; '.join(errors))

    def _new_palette(self, ui, identity=PALETTE_ID, visible=False):
        self._release_palette()
        palette = ui.palettes.itemById(identity)
        if palette is not None:
            palette.deleteMe()
        bundle = Path(__file__).resolve().parent.parent
        version = json.loads((bundle / "Partelier.manifest").read_text(encoding="utf-8"))["version"]
        html_uri = (Path(__file__).parent / "ui" / "palette.html").resolve().as_uri() + "?v=" + quote(str(version), safe="")
        palette = ui.palettes.add(
            identity, "Partelier · Tool library", html_uri,
            visible, True, True, 380, 760, True,
        )
        if palette is None:
            raise RuntimeError("Fusion could not open the tool library.")
        self._palette = palette
        self._page_generation += 1
        self._palette_closed = False
        self._html_handler = _HTMLMessage(self)
        self._close_handler = _PaletteClosed(self)
        palette.incomingFromHTML.add(self._html_handler)
        if palette.closed.add(self._close_handler) is False:
            raise RuntimeError('Fusion could not register Close cancellation.')
        return palette

    def show(self):
        ui = adsk.core.Application.get().userInterface
        palette = self._palette
        created = palette is None or not palette.isValid
        recovered = False
        try:
            if created:
                palette = self._new_palette(ui)
            palette.isVisible = True
        except RuntimeError as error:
            if 'pArea' not in str(error):
                raise
            # Fusion can retain a broken dock area for an otherwise valid ID.
            # A fresh ID and visible-at-creation bypass that saved dock entry.
            # One bounded retry only; unrelated display failures still propagate.
            emit('palette.display.recovering',error=str(error),fallback='fresh_floating')
            self._release_palette()
            try:
                palette = self._new_palette(ui, PALETTE_ID+'_recovery_'+uuid.uuid4().hex, True)
                try:
                    palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
                except RuntimeError as docking_error:
                    emit('palette.docking.unavailable',error=str(docking_error),fallback='native_default')
                if not palette.isVisible:
                    palette.isVisible = True
            except Exception:
                self._release_palette()
                raise
            created = recovered = True
        if created and not recovered:
            # A new native docking area may not exist until the palette is
            # visible. Docking is a layout preference, not a startup gate.
            try:
                palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
            except RuntimeError as error:
                emit('palette.docking.unavailable',error=str(error),fallback='floating')
        emit('palette.show',created=created,visible=palette.isVisible)

    def handle_message(self, action, raw_data):
        if self._created_handler is None:
            raise RuntimeError("The tool library has stopped. Run the add-in again.")
        if self._palette_closed:
            raise ValueError('This Partelier window is closed. Open the tool library again.')
        request = read_request(action, raw_data)
        # Cancel bypasses ordinary busy guards, like Close, but only for the
        # exact requested session. A stale page must never cancel new work.
        cancel_managers = {
            'hinge': self._hinge_commands, 'snap': self._snap_commands,
            'pattern': self._pattern_commands, 'detail': self._detail_commands,
            'fan': self._fan_commands, 'mechanism': self._mechanism_commands,
            'finishing': self._finishing_commands, 'thread': self._thread_commands,
            'knurling': self._knurling_commands,
        }
        if action.endswith('_cancel') and action[:-7] in cancel_managers:
            tool = action[:-7]
            manager = cancel_managers[tool]
            if manager is None:raise ValueError('Run Partelier to enable this tool.')
            snapshot = manager.palette_state()
            if snapshot.get('sessionId') != request.session_id:
                if snapshot.get('sessionId') or snapshot.get('endedSessionId') != request.session_id:
                    raise ValueError('This session has ended. The current work was not cancelled.')
            else:
                emit('palette.cancel.request', tool=tool, session_id=request.session_id,
                     phase=snapshot.get('phase'), busy=getattr(manager,'busy',False))
                manager.cancel_palette()
                snapshot = manager.palette_state()
                if snapshot.get('sessionId') == request.session_id:
                    raise RuntimeError('Cancellation is incomplete. Try Cancel again.')
                emit('palette.cancel.complete', tool=tool, session_id=request.session_id,
                     phase=snapshot.get('phase'))
            return json.dumps({'protocol':PROTOCOL_VERSION,'requestId':request.request_id,
                               'ok':True,tool+'State':snapshot})
        automatic=getattr(self,'_automatic_updates',None)
        if automatic is not None and automatic.busy and action not in ('operations_list','diagnostic_log') and not action.endswith('_status'):
            raise ValueError('Wait for automatic feature updates to finish.')
        if self._operation_delete is not None and self._operation_delete.busy and action not in ('operations_list','diagnostic_log'):
            raise ValueError('Wait for operation deletion to finish.')
        if action in ('auto_update_status','auto_update_toggle'):
            import adsk.fusion as native
            from .auto_refresh import GROUP
            design=native.Design.cast(adsk.core.Application.get().activeProduct)
            if design is None:raise ValueError('Open a Fusion Design.')
            if action=='auto_update_toggle':
                design.rootComponent.attributes.add(GROUP,'enabled','true' if request.enabled else 'false')
                if automatic is not None and request.enabled:automatic.reset_failure(design)
            tag=design.rootComponent.attributes.itemByName(GROUP,'enabled')
            return json.dumps({'protocol':PROTOCOL_VERSION,'requestId':request.request_id,'ok':True,'autoUpdate':automatic.enabled() if automatic is not None else tag is None or tag.value=='true'})
        operation_alias=None
        operation_items=None
        if action in ('operations_list','operation_edit','operation_delete'):
            from adsk import fusion as native_api
            design=native_api.Design.cast(adsk.core.Application.get().activeProduct)
            if design is None:raise ValueError('Open a Fusion Design to view its operations.')
            if action!='operations_list':
                for manager,label in ((self._hinge_commands,'hinge'),(self._snap_commands,'snap-fit'),(self._pattern_commands,'pattern'),(self._detail_commands,'Small detail'),(self._fan_commands,'fan'),(self._mechanism_commands,'mechanism'),(self._finishing_commands,'finishing'),(self._thread_commands,'thread'),(self._knurling_commands,'knurling')):
                    self._require_idle_other_tool(manager,label)
                operations.expand(design)
                record=operations.resolve(design,request.operation_id)
                if action=='operation_delete':self._operation_delete.launch(design,request.operation_id)
                else:
                    from .tools.details.settings import DetailSettings
                    managers={'knurling':(self._knurling_commands,KnurlSettings()),'thread':(self._thread_commands,ThreadSettings()),'finishing':(self._finishing_commands,FinishingSettings()),'mechanism':(self._mechanism_commands,MechanismSettings()),'fan':(self._fan_commands,FanSettings()),'hinge':(self._hinge_commands,HingeSettings()),'snap':(self._snap_commands,SnapFitSettings()),
                              'pattern':(self._pattern_commands,PatternSettings()),'detail':(self._detail_commands,DetailSettings(kind=record['alias']) if record['tool']=='detail' else DetailSettings())}
                    manager,defaults=managers[record['tool']]
                    if not self._has_palette_manager(manager):raise ValueError('Run Partelier to edit this operation.')
                    manager.begin_palette(defaults.to_dict(),editing=True,selected_entity=record['anchor'])
                    operation_alias=record['alias']
            operation_items=operations.snapshot(design)
        if action.startswith(('hinge_','snap_','pattern_')) and not action.endswith('_status'):
            self._require_idle_other_tool(self._detail_commands,'Small detail')
        if action=='diagnostic_log':
            for entry in request.diagnostics:
                emit('ui.'+entry['event'],ui_at=entry['at'],context=entry['context'])
            return json.dumps({'protocol':PROTOCOL_VERSION,'requestId':request.request_id,'ok':True})
        if action.startswith(('hinge_','snap_','pattern_','detail_')) and not action.endswith('_status'):
            self._require_idle_other_tool(self._fan_commands,'fan')
        knurling_snapshot=None
        if (action.endswith('_begin') or action in ('hinge_create','hinge_edit')) and not action.startswith('knurling_'):
            self._require_idle_other_tool(self._knurling_commands,'knurling')
        if action.startswith('knurling_'):
            manager=self._knurling_commands
            if not self._has_palette_manager(manager):raise RuntimeError('Run Partelier to enable Knurling.')
            if action=='knurling_begin':
                for other in (self._hinge_commands,self._snap_commands,self._pattern_commands,self._detail_commands,self._fan_commands,self._mechanism_commands,self._finishing_commands,self._thread_commands):
                    self._require_idle_other_tool(other,'tool')
                knurling_snapshot=manager.begin_palette(request.settings.to_dict(),editing=request.editing)
            elif action=='knurling_status':knurling_snapshot=manager.palette_state()
            else:knurling_snapshot=manager.palette_action(action,request.session_id,revision=request.revision,settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        thread_snapshot=None
        if (action.endswith('_begin') or action in ('hinge_create','hinge_edit')) and not action.startswith('thread_'):
            self._require_idle_other_tool(self._thread_commands,'thread')
        if action.startswith('thread_'):
            manager=self._thread_commands
            if not self._has_palette_manager(manager):raise RuntimeError('Run Partelier to enable Threads.')
            if action=='thread_begin':
                for other in (self._hinge_commands,self._snap_commands,self._pattern_commands,self._detail_commands,self._fan_commands,self._mechanism_commands,self._finishing_commands):
                    self._require_idle_other_tool(other,'tool')
                thread_snapshot=manager.begin_palette(request.settings.to_dict(),editing=request.editing)
            elif action=='thread_status':thread_snapshot=manager.palette_state()
            else:thread_snapshot=manager.palette_action(action,request.session_id,revision=request.revision,settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        mechanism_snapshot=None
        if (action.endswith('_begin') or action in ('hinge_create','hinge_edit')) and not action.startswith('mechanism_'):
            self._require_idle_other_tool(self._mechanism_commands,'mechanism')
        if action.startswith('mechanism_'):
            manager=self._mechanism_commands
            if not self._has_palette_manager(manager):raise RuntimeError('Run Partelier to enable mechanism.')
            if action=='mechanism_begin':
                for other in (self._hinge_commands,self._snap_commands,self._pattern_commands,self._detail_commands,self._fan_commands,self._mechanism_commands,self._finishing_commands,self._thread_commands):
                    if other is not manager:self._require_idle_other_tool(other,'tool')
                mechanism_snapshot=manager.begin_palette(request.settings.to_dict(),editing=request.editing)
            elif action=='mechanism_status':mechanism_snapshot=manager.palette_state()
            else:mechanism_snapshot=manager.palette_action(action,request.session_id,revision=request.revision,settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        finishing_snapshot=None
        if (action.endswith('_begin') or action in ('hinge_create','hinge_edit')) and not action.startswith('finishing_'):
            self._require_idle_other_tool(self._finishing_commands,'finishing')
        if action.startswith('finishing_'):
            manager=self._finishing_commands
            if not self._has_palette_manager(manager):raise RuntimeError('Run Partelier to enable finishing.')
            if action=='finishing_begin':
                for other in (self._hinge_commands,self._snap_commands,self._pattern_commands,self._detail_commands,self._fan_commands,self._mechanism_commands,self._finishing_commands,self._thread_commands):
                    if other is not manager:self._require_idle_other_tool(other,'tool')
                finishing_snapshot=manager.begin_palette(request.settings.to_dict(),editing=request.editing)
            elif action=='finishing_status':finishing_snapshot=manager.palette_state()
            else:finishing_snapshot=manager.palette_action(action,request.session_id,revision=request.revision,settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        fan_snapshot=None
        if action.startswith('fan_'):
            if not self._has_palette_manager(self._fan_commands):raise RuntimeError('Run Partelier to enable Fans & Propellers.')
            if action=='fan_begin':
                for manager,label in ((self._hinge_commands,'hinge'),(self._snap_commands,'snap-fit'),(self._pattern_commands,'pattern'),(self._detail_commands,'Small detail')):
                    self._require_idle_other_tool(manager,label)
                fan_snapshot=self._fan_commands.begin_palette(request.settings.to_dict(),editing=request.editing)
            elif action=='fan_status':fan_snapshot=self._fan_commands.palette_state()
            else:fan_snapshot=self._fan_commands.palette_action(action,request.session_id,revision=request.revision,settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        snapshot = None
        snap_snapshot = None
        pattern_snapshot = None
        detail_snapshot = None
        if action=='detail_begin' or action.startswith('detail_') and action!='detail_status':
            if not self._has_palette_manager(self._detail_commands):raise RuntimeError('Run Partelier to enable Small details.')
            if action=='detail_begin':
                for manager,label in ((self._hinge_commands,'hinge'),(self._snap_commands,'snap-fit'),(self._pattern_commands,'pattern')):
                    self._require_idle_other_tool(manager,label)
                detail_snapshot=self._detail_commands.begin_palette(request.settings.to_dict(),editing=request.editing)
            else:
                detail_snapshot=self._detail_commands.palette_action(action,request.session_id,revision=request.revision,
                    settings_dict=request.settings.to_dict() if request.settings else None,target=request.target)
        elif action=='detail_status':
            if not self._has_palette_manager(self._detail_commands):raise RuntimeError('Run Partelier to enable Small details.')
            detail_snapshot=self._detail_commands.palette_state()
        elif action == "open_input_check":
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
        elif action=="pattern_export":
            if not self._has_palette_pattern():raise RuntimeError("Run Partelier to export flat colour.")
            self._require_idle_other_tool(self._hinge_commands,"hinge")
            self._require_idle_other_tool(self._snap_commands,"snap-fit")
            export_message=self._pattern_commands.export_colour()
            return json.dumps({"protocol":PROTOCOL_VERSION,"requestId":request.request_id,"ok":True,"message":export_message})
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
        if self._has_palette_manager(self._knurling_commands):
            capabilities.extend(["knurling-palette","knurling-edit"])
            if knurling_snapshot is None:knurling_snapshot=self._knurling_commands.palette_state()
        if self._has_palette_manager(self._thread_commands):
            capabilities.extend(["thread-palette","thread-edit"])
            if thread_snapshot is None:thread_snapshot=self._thread_commands.palette_state()
        if self._has_palette_manager(self._finishing_commands):
            capabilities.extend(['finishing-palette','finishing-edit'])
            if finishing_snapshot is None:finishing_snapshot=self._finishing_commands.palette_state()
        if self._has_palette_manager(self._mechanism_commands):
            capabilities.extend(['mechanism-palette','mechanism-edit'])
            if mechanism_snapshot is None:mechanism_snapshot=self._mechanism_commands.palette_state()
        if self._has_palette_manager(self._fan_commands):
            capabilities.extend(['fan-palette','fan-edit'])
            if fan_snapshot is None:fan_snapshot=self._fan_commands.palette_state()
        if self._operation_delete is not None:capabilities.append("operation-history")
        if self._has_palette_manager(self._detail_commands):
            capabilities.extend(['detail-palette','detail-edit'])
            if detail_snapshot is None:detail_snapshot=self._detail_commands.palette_state()
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
            if callable(getattr(self._pattern_commands,"export_colour",None)):capabilities.append("pattern-colour-export")
            if pattern_snapshot is None:pattern_snapshot=self._pattern_commands.palette_state()
        from .tools.details.settings import DetailSettings
        return json.dumps({
            "protocol": PROTOCOL_VERSION,
            "requestId": request.request_id,
            "ok": True,
            "capabilities": capabilities,
            "operations":operation_items,"operationAlias":operation_alias,
            "operationPending":bool(self._operation_delete and self._operation_delete.busy),
            'mechanismDefaults':MechanismSettings().to_dict(),'mechanismState':mechanism_snapshot,
            'threadDefaults':ThreadSettings().to_dict(),'threadState':thread_snapshot,
            'knurlingDefaults':KnurlSettings().to_dict(),'knurlingState':knurling_snapshot,
            'finishingDefaults':FinishingSettings().to_dict(),'finishingState':finishing_snapshot,
            "hingeDefaults": HingeSettings().to_dict(),
            "hingeState": snapshot,
            "snapDefaults": SnapFitSettings().to_dict(),
            "snapState": snap_snapshot,
            "patternDefaults": PatternSettings().to_dict(),
            "patternState": pattern_snapshot,
            'detailDefaults':DetailSettings().to_dict(),
            'detailState':detail_snapshot,'fanDefaults':FanSettings().to_dict(),'fanState':fan_snapshot,
        })

    def stop(self):
        self._palette_closed=True
        self._page_generation+=1
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
        if self._has_palette_manager(self._detail_commands):attempt(lambda:self._detail_commands.set_state_callback(None))
        if self._has_palette_manager(self._fan_commands):attempt(lambda:self._fan_commands.set_state_callback(None))
        if self._has_palette_manager(self._mechanism_commands):attempt(lambda:self._mechanism_commands.set_state_callback(None))
        if self._has_palette_manager(self._finishing_commands):attempt(lambda:self._finishing_commands.set_state_callback(None))
        if self._has_palette_manager(self._thread_commands):attempt(lambda:self._thread_commands.set_state_callback(None))
        if self._has_palette_manager(self._knurling_commands):attempt(lambda:self._knurling_commands.set_state_callback(None))
        if self._operation_delete is not None:attempt(self._operation_delete.stop)
        self._operation_delete=None
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
        self._detail_commands = None
        self._fan_commands = None
        self._finishing_commands = None
        self._thread_commands = None
        self._knurling_commands = None
        self._mechanism_commands = None
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
        self.generation = owner._page_generation

    def notify(self, args):
        if args.action == "response":
            args.returnData = "OK"
            return
        if self.generation != self.owner._page_generation or self.owner._palette_closed:
            args.returnData = json.dumps({'protocol':PROTOCOL_VERSION,'ok':False,'message':'This Partelier window has closed. Open the tool library again.'})
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


class _PaletteClosed(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.generation = owner._page_generation

    def notify(self, args):
        if self.generation != self.owner._page_generation or self.owner._palette is None or self.owner._palette_closed:
            return
        try:
            self.owner.close()
        except Exception:
            adsk.core.Application.get().log('Partelier Close cancellation failed:\n'+traceback.format_exc())
            self.owner._report_error('Partelier could not fully cancel the current tool. See the Fusion log.')
