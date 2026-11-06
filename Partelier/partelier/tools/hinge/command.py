"""HTML hinge sessions, direct model picking and undoable Create/Edit.

Palette callbacks own direct selectEntity prompts and disposable graphics.
Joined edge finishes compute in rollback-only zero-input native preview commands.
Create/Rebuild persists in a separate native transaction. The legacy native
dialog remains a compatibility path.
"""

from collections.abc import Mapping
import math
import time
import traceback
import uuid
from types import SimpleNamespace

import adsk.core
import adsk.fusion

from .fusion import (
    capture_preview_sources,
    create_hinge,
    prepare_hinge,
    prepare_edit_hinge,
    preview_hinge,
    preview_hide_bodies,
    read_edit_target,
    rebuild_hinge,
    validate_preview_sources,
)
from .settings import HingeSettings
from .visibility import BodyVisibilityLease
from .native_finish import finish_native_results
from .native_preview import NativePreviewRunner, PREVIEW_COMMAND_ID


CREATE_COMMAND_ID = "sktech_partelier_hinge_create_16e681a4"
EDIT_COMMAND_ID = "sktech_partelier_hinge_edit_16e681a4"

_PLACEMENT_LENGTH_INPUTS = (
    ("start_margin_mm", "Start margin", "Distance from the selected edge start to the first barrel end. Pins can extend beyond this margin."),
    ("end_margin_mm", "End margin", "Distance from the last barrel end to the selected edge end. Pins can extend beyond this margin."),
)
_LENGTH_INPUTS = (
    ("length_mm", "Length per hinge", "Barrel length of each individual hinge, excluding pin overhang."),
    ("barrel_diameter_mm", "Barrel diameter", "Outside diameter of the knuckles."),
    ("pin_diameter_mm", "Pin diameter", "Diameter of the separate straight pin."),
    ("diametral_clearance_mm", "Diametral clearance", "Bore diameter minus pin diameter; radial clearance is half this value."),
    ("axial_gap_mm", "Axial gap", "Clear gap between adjacent knuckles along the axis."),
    ("leaf_reach_mm", "Leaf reach", "Nominal distance from the hinge axis into each source body; tapered support can extend farther."),
    ("leaf_thickness_mm", "Leaf thickness", "Height of the flat attachment web above the selected plane; tapered support rises to the barrel."),
    ("attachment_overlap_mm", "Attachment overlap", "Depth of the web into each source body."),
    ("pin_overhang_mm", "Pin overhang", "Pin extension beyond each end of the hinge."),
    ("axis_offset_mm", "Axis offset toward B", "Distance from the reference A boundary toward B; disabled for Split seam, whose axis stays on the seam."),
    ("seam_clearance_mm", "Split seam clearance", "Total gap removed equally from the two attached bodies along the verified rectangular contact. Used only for Split seam."),
)
_ALL_LENGTH_INPUTS = _PLACEMENT_LENGTH_INPUTS + _LENGTH_INPUTS
_PARAMETER_IDS = {name for name, _, _ in _ALL_LENGTH_INPUTS} | {"hinge_count", "knuckle_count", "include_pin", "split_seam"}
_SELECTION_IDS = {"face_a", "face_b", "axis_edge", "edit_target"}


def _settings_from_launch(values):
    if values is None:
        return HingeSettings()
    if not isinstance(values, Mapping):
        raise ValueError("Hinge dimensions must be an object.")
    settings = HingeSettings().to_dict()
    if set(values) - set(settings):
        raise ValueError("Hinge dimensions contain unsupported fields.")
    settings.update(values)
    return HingeSettings.from_dict(settings)


def _active_design():
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    if design is None:
        raise ValueError("Open a Fusion Design document before using the hinge tool.")
    return design


class HingeCommands:
    """Own hinge commands and the rollback-only preview driver, without toolbar UI."""

    def __init__(self, report_error=None):
        self._report_error = report_error
        self._registrations = []
        self._sessions = []
        self._pending_settings = None
        self._opening = False
        self._state_callback = None
        self._palette_pending = None
        self._cancelled_palette_opening = False
        self._palette_action_busy = False
        self._last_palette_state = self._idle_palette_state()
        self._context_handlers = []
        self._native_preview = None

    @staticmethod
    def _idle_palette_state():
        return {"sessionId": None, "revision": 0, "phase": "idle", "editing": False,
                "settings": None, "selections": {}, "message": "Select geometry to begin."}

    def set_state_callback(self, callback):
        self._state_callback = callback

    def _publish_palette(self, session=None):
        if session is not None and session.palette_mode:
            self._last_palette_state = session.palette_snapshot()
        if self._state_callback is not None:
            try:
                self._state_callback(self._last_palette_state)
            except Exception:
                # A disconnected palette cannot invalidate a model operation.
                try:
                    self._log_error("Partelier could not update the palette state")
                except Exception:
                    pass
        return self._last_palette_state

    def palette_state(self):
        for session in self._sessions:
            if session.palette_mode and not session.closed:
                self._last_palette_state = session.palette_snapshot()
                break
        return self._last_palette_state

    def begin_palette(self, settings_dict, editing=False, selected_entity=None):
        settings = _settings_from_launch(settings_dict)
        if type(editing) is not bool:
            raise ValueError("Edit mode must be true or false.")
        _active_design()
        self._ensure_not_opening()
        if self._sessions:
            raise ValueError("Finish or cancel the current hinge before starting another.")
        if not self._registrations:
            raise ValueError("The hinge tool has stopped. Run the add-in again.")
        session = _Session(self, None, editing)
        session.palette_mode = True
        session.session_id = str(uuid.uuid4())
        self._sessions.append(session)
        session.open(settings)
        self._palette_action_busy = True
        try:
            # selectEntity is supported from the palette's HTML callback, never
            # from Command events. Esc resets the captured selection set.
            if editing and selected_entity is not None:
                session.selection_entities['edit_target']=selected_entity;session.changed('edit_target')
                return self._publish_palette(session)
            if editing and self._capture_preselected_edit(session):
                return self._publish_palette(session)
            for target in (("edit_target",) if editing else ("face_a", "face_b", "axis_edge")):
                if not self._pick_palette_entity(session, target):
                    break
            session.picking_target=None
            return self._publish_palette(session)
        except Exception:
            session.close()
            raise
        finally:
            self._palette_action_busy = False

    def _capture_preselected_edit(self, session):
        """Use one existing model/browser pick; multiple picks need disambiguation."""
        selections = getattr(adsk.core.Application.get().userInterface, "activeSelections", None)
        if selections is None or selections.count != 1:
            return False
        entity = selections.item(0).entity
        if entity is None or not entity.isValid:
            return False
        session.selection_entities["edit_target"] = entity
        session.changed("edit_target")
        return True

    def _pick_palette_entity(self, session, target):
        allowed = {"edit_target"} if session.editing else {"face_a", "face_b", "axis_edge"}
        if target not in allowed:
            raise ValueError("Choose a supported geometry selection.")
        session._ensure_design()
        session.preview_error = None
        session.picking_target=target
        prompts = {
            "face_a": ("Select face A in the model. Esc resets all selections.", "PlanarFaces"),
            "face_b": ("Select coplanar face B on the other body. Esc resets all selections.", "PlanarFaces"),
            "axis_edge": ("Select the straight reference edge. Esc resets all selections.", "Edges"),
            "edit_target": ("Select a hinge body, pin, or a Part containing one hinge. Esc resets all selections.", "Occurrences,SolidBodies,Features,Faces,Edges"),
        }
        prompt, selection_filter = prompts[target]
        session.phase = "selecting"
        session._status(prompt)
        session._ensure_design()
        previous_preview = session.preview
        previous_hidden = session._preview_hidden_bodies
        previous_visible = getattr(previous_preview, "isVisible", True) if previous_preview is not None else True
        try:
            if previous_preview is not None and previous_preview.isValid:
                previous_preview.isVisible = False
                session.preview_visibility.restore()
            try:
                selected = adsk.core.Application.get().userInterface.selectEntity(prompt, selection_filter)
            except RuntimeError:
                # Autodesk documents an assertion when the user aborts selectEntity.
                selected = None
        finally:
            if (not session.closed and previous_preview is not None
                    and previous_preview is session.preview and previous_preview.isValid):
                session.preview_visibility.hide(previous_hidden)
                previous_preview.isVisible = previous_visible
        session._ensure_design()
        if session.closed:
            raise ValueError("This hinge session ended while picking. Start again.")
        entity = selected.entity if selected is not None else None
        if entity is None or not entity.isValid:
            self._reset_palette_selection(session)
            return False
        if target in {"face_a", "face_b"} and session.selection_entities.get(target) != entity:
            session.selection_entities.pop("axis_edge", None)
        session.selection_entities[target] = entity
        session.changed(target)
        return True

    def cancel_palette(self):
        sessions=[session for session in self._sessions if session.palette_mode and not session.closed]
        if self._palette_pending is not None and self._opening:self._cancelled_palette_opening=True
        self._palette_pending=None
        ui=adsk.core.Application.get().userInterface
        picking=any(session.picking_target for session in sessions) and self._palette_action_busy
        errors=[]
        pending_work=any(session.phase!='created' for session in sessions)
        for session in sessions:
            try:
                session.cancel_requested=session.phase!='created'
                session.generation+=1
                self._cancel_native_preview(session)
                session.clear_preview()
                if session.phase!='created':
                    session.phase='cancelled';session.message='Hinge cancelled. Original bodies are unchanged.'
                session.close()
            except Exception as error:errors.append(str(error))
        preview_id=self._native_preview._command_id if self._native_preview else None
        if pending_work and (picking or ui.activeCommand in (CREATE_COMMAND_ID,EDIT_COMMAND_ID,preview_id)):
            ui.terminateActiveCommand()
        if errors:raise RuntimeError('Could not cancel the hinge completely. '+'; '.join(errors))

    def palette_action(self, action, session_id, revision=None, settings_dict=None, target=None):
        if self._palette_action_busy:
            raise ValueError("Finish the current selection or press Esc before another hinge action.")
        sessions = [item for item in self._sessions if item.palette_mode and not item.closed
                    and item.session_id == session_id]
        if len(sessions) != 1:
            raise ValueError("This hinge session has ended. Select geometry to start again.")
        session = sessions[0]
        session._ensure_design()
        if self._opening or session.command is not None:
            raise ValueError("Wait for the hinge creation to finish.")
        self._palette_action_busy = True
        try:
            if action in {"hinge_update", "hinge_preview", "hinge_commit"}:
                if type(revision) is not int or not 0 <= revision <= 1_000_000_000:
                    raise ValueError("Use a valid hinge revision.")
                settings = HingeSettings.from_dict(settings_dict)
                if revision < session.revision or (revision == session.revision
                        and settings != session.palette_settings):
                    raise ValueError("These hinge settings are stale. Use the current palette values.")
                if settings != session.palette_settings:
                    self._cancel_native_preview(session)
                    session.palette_settings = settings
                    session.generation += 1
                    session.preview_error = None
                    session.auto_split_detected = False
                    if action != "hinge_preview":
                        session.clear_preview()
                if action == "hinge_preview":
                    # A live refresh also retries a prior geometry/display error.
                    session.preview_error = None
                session.revision = revision
                valid = session.validate()
                session.phase = "ready" if valid else ("error" if session.edit_target_error else "selecting")
                if action == "hinge_update":
                    if valid:
                        session._status("Settings updated. Preview to inspect the result.")
                else:
                    session._basic_validate()
                    if action == "hinge_preview":
                        session.preview_requested = True
                        try:
                            session.show_preview(SimpleNamespace(isValidResult=False))
                        finally:
                            session.preview_requested = False
                    else:
                        session.phase = "opening"
                        session._status("Creating the hinge…" if not session.editing else "Rebuilding the hinge…")
                        if session.closed or getattr(session,'cancel_requested',False):raise ValueError('The hinge was cancelled before Create.')
                        self._palette_pending = session
                        try:
                            self._launch(EDIT_COMMAND_ID if session.editing else CREATE_COMMAND_ID)
                        except Exception:
                            self._palette_pending = None
                            self._opening = False
                            raise
            elif action == "hinge_focus":
                targets=('edit_target',) if session.editing else ('face_a','face_b','axis_edge')
                if target not in targets:raise ValueError('Choose a supported geometry selection.')
                for current in targets[targets.index(target):]:
                    if not self._pick_palette_entity(session,current):break
                session.picking_target=None
            elif action == 'hinge_reset':
                self._reset_palette_selection(session)
            elif action == "hinge_cancel":
                # Do not claim Cancel succeeded if temporary graphics remain.
                session.clear_preview()
                session.phase = "cancelled"
                session._status("Hinge cancelled. Original bodies are unchanged.")
                session.close()
            else:
                raise ValueError("This hinge action is unavailable.")
            return self._publish_palette(session)
        except Exception as error:
            if not session.closed:
                session.picking_target=None
                session.phase = "error"
                session._status(str(error))
            raise
        finally:
            self._palette_action_busy = False

    def _reset_palette_selection(self,session):
        session.revision=min(session.revision+1,1_000_000_000);session.generation+=1
        self._cancel_native_preview(session);session.clear_preview()
        session.selection_entities.clear();session.picking_target=None
        session.edit_target_loaded=False;session.edit_target_error=None;session.preview_error=None
        session.phase='selecting';session._status('Selection reset. Pick face A to start again. Dimensions kept.')

    def _cancel_native_preview(self, session):
        if self._native_preview is not None:
            self._native_preview.cancel(session)
        session._native_preview_generation = None

    def _queue_native_preview(self, session, generation, started):
        if self._native_preview is None:
            self._native_preview = NativePreviewRunner(self._log_error)
        try:
            self._native_preview.request(
                session,
                lambda: session._prepare_native_preview(generation),
                lambda prepared: session._complete_native_preview(prepared, started, generation),
                lambda error: session._preview_failed(error, generation),
            )
        except Exception:
            session._native_preview_generation = None
            if not self._native_preview.busy:
                self._native_preview.stop()
                self._native_preview = None
            raise

    def _validate_palette_previews(self):
        for session in list(self._sessions):
            if (not session.palette_mode or session.closed or session.preview is None
                    or session.preview_sources is None):
                continue
            try:
                validate_preview_sources(session.design, session.preview_sources)
            except Exception as error:
                # Camera/navigation commands leave source geometry unchanged.
                # Only an actual source/context change invalidates the graphics.
                session.generation += 1
                session.clear_preview()
                session.preview_error = ("The hinge sources changed or could not be verified. "
                                         "Refresh preview or reselect the geometry. " + str(error))
                session.phase = "error"
                session._status(session.preview_error)

    def start(self):
        if self._registrations:
            return
        ui = adsk.core.Application.get().userInterface
        try:
            for identity, title, editing in (
                (CREATE_COMMAND_ID, "Partelier: Create pin hinge", False),
                (EDIT_COMMAND_ID, "Partelier: Edit / Rebuild pin hinge", True),
            ):
                definition = ui.commandDefinitions.itemById(identity)
                if definition is None:
                    definition = ui.commandDefinitions.addButtonDefinition(
                        identity, title,
                        "Create or rebuild a separate-pin hinge on two supported source bodies.",
                    )
                handler = _Created(self, editing)
                self._registrations.append((definition, handler))
                definition.commandCreated.add(handler)
            app = adsk.core.Application.get()
            for event, handler in ((ui.commandTerminated, _ContextCommandTerminated(self)),
                                   (app.documentDeactivating, _ContextDocumentDeactivating(self))):
                event.add(handler)
                self._context_handlers.append((event, handler))
        except Exception:
            self.stop()
            raise

    def launch_create(self, settings_dict=None):
        settings = _settings_from_launch(settings_dict)
        _active_design()
        self._ensure_not_opening()
        self._pending_settings = settings
        try:
            return self._launch(CREATE_COMMAND_ID)
        except Exception:
            self._pending_settings = None
            raise

    def launch_edit(self):
        _active_design()
        self._ensure_not_opening()
        return self._launch(EDIT_COMMAND_ID)

    def _ensure_not_opening(self):
        ui = adsk.core.Application.get().userInterface
        if self._opening or self._pending_settings is not None or ui.activeCommand in (
            CREATE_COMMAND_ID, EDIT_COMMAND_ID, PREVIEW_COMMAND_ID,
        ):
            raise ValueError("Finish or cancel the open hinge command before starting another.")

    def _launch(self, identity):
        if not self._registrations:
            raise RuntimeError("The hinge tool is unavailable. Stop and Run the add-in.")
        definition = adsk.core.Application.get().userInterface.commandDefinitions.itemById(identity)
        if definition is None or not definition.isValid:
            raise RuntimeError("Fusion could not open the hinge command. Stop and Run the add-in.")
        self._opening = True
        try:
            if not definition.execute():
                raise RuntimeError("Fusion could not open the hinge command. Stop and Run the add-in.")
        except Exception:
            self._opening = False
            raise
        return True

    def _log_error(self, summary):
        adsk.core.Application.get().log(f"{summary}\n{traceback.format_exc()}")

    def _unexpected_error(self, summary):
        if self._report_error is not None:
            self._report_error(summary)
        else:
            self._log_error(summary)

    def stop(self):
        if self._native_preview is not None:
            self._native_preview.stop()
            self._native_preview = None
        ui = adsk.core.Application.get().userInterface
        if ui.activeCommand in (CREATE_COMMAND_ID, EDIT_COMMAND_ID):
            try:
                ui.terminateActiveCommand()
            except Exception:
                self._log_error("Partelier could not terminate its hinge command")
        for session in list(self._sessions):
            session.close()
        for event, handler in self._context_handlers:
            try:
                event.remove(handler)
            except Exception:
                self._log_error("Partelier could not detach its context handler")
        self._context_handlers.clear()
        for definition, handler in self._registrations:
            try:
                definition.commandCreated.remove(handler)
            except Exception:
                self._log_error("Partelier could not detach a hinge creation handler")
            try:
                if definition.isValid:
                    definition.deleteMe()
            except Exception:
                self._log_error("Partelier could not remove a hinge command definition")
        self._registrations.clear()
        self._pending_settings = None
        self._palette_pending = None
        self._opening = False
        self._cancelled_palette_opening = False
        self._last_palette_state = self._idle_palette_state()
        self._publish_palette()


class _Session:
    """Own one hinge session, native entity references and disposable graphics."""

    def __init__(self, owner, command, editing):
        self.owner = owner
        self.command = command
        self.inputs = command.commandInputs if command is not None else None
        self.design = _active_design()
        self.editing = editing
        self.handlers = []
        self.preview = None
        self.preview_sources = None
        self.preview_visibility = BodyVisibilityLease()
        self._preview_hidden_bodies = ()
        self.retained_preview_groups = []
        self.generation = 0
        self.preview_generation = None
        self.preview_error = None
        self.loading_settings = False
        self.auto_split_detected = False
        self.edit_target_loaded = False
        self.edit_target_error = None
        self.closed = False
        self.palette_mode = False
        self.session_id = None
        self.palette_settings = HingeSettings()
        self.launch_settings = HingeSettings()
        self.revision = 0
        self.phase = "selecting"
        self.message = "Select the hinge geometry."
        self.preview_requested = False
        self._native_preview_generation = None
        self.commit_requested = False
        self._palette_selections = {}
        self.selection_entities = {}
        self.picking_target=None

    def open(self, settings):
        self.launch_settings = settings
        self.palette_settings = settings
        if self.palette_mode:
            return self._open_palette_picker()
        command = self.command
        editing = self.editing
        command.isExecutedWhenPreEmpted = False
        command.okButtonText = "Rebuild hinge" if editing else "Create hinge"
        self.inputs.addTextBoxCommandInput(
            "scope", "",
            "Select a Partelier hinge result in the browser or a generated body. "
            "Rebuild updates this hinge. Attached hinges modify the selected bodies."
            if editing else
            "Select coplanar exterior faces with the same outward direction on two root solid bodies "
            "(for example, a lower front face and the front strip above it). Select a straight "
            "reference edge of A, or the coincident edge of B. Fusion automatically detects supported "
            "touching seams after their shared edge is selected. The axis is centered on the seam "
            "and clearance is applied to the selected bodies when created. "
            "Attached output modifies these same bodies; separate leaves leave them unchanged.",
            5, True,
        )
        if editing:
            target = self.inputs.addSelectionInput(
                "edit_target", "Hinge result", "Select a Partelier hinge occurrence or generated solid body"
            )
            target.addSelectionFilter("Occurrences")
            target.addSelectionFilter("SolidBodies")
            target.setSelectionLimits(1, 1)
        else:
            for identity, title, prompt, filter_name in (
                ("face_a", "Face A", "Select an exterior planar face on root body A, such as the lower front face", "PlanarFaces"),
                ("face_b", "Face B", "Select the coplanar exterior face of B facing the same way, such as the upper front strip", "PlanarFaces"),
                ("axis_edge", "Reference edge", "Select a straight boundary edge of A, or its visible coincident edge on B; for Split seam select the shared seam", "Edges"),
            ):
                selection = self.inputs.addSelectionInput(identity, title, prompt)
                selection.addSelectionFilter(filter_name)
                selection.setSelectionLimits(1, 1)
        self.inputs.addTextBoxCommandInput(
            "placement_heading", "", "<b>Placement along selected edge</b><br>"
            "Two or more hinges use exact end margins and equal gaps. One hinge is centered "
            "between the margins. Margins stop at barrel ends; pins can extend beyond them.", 4, True,
        )
        self.inputs.addIntegerSpinnerCommandInput(
            "hinge_count", "Number of hinges", 1, 20, 1, settings.hinge_count
        )
        for identity, title, tooltip in _PLACEMENT_LENGTH_INPUTS:
            control = self.inputs.addValueInput(
                identity, title, "mm",
                adsk.core.ValueInput.createByString(f"{getattr(settings, identity):.15g} mm"),
            )
            control.tooltip = tooltip
            control.minimumValue = 0
            control.isMinimumInclusive = True
        self.inputs.addTextBoxCommandInput(
            "hinge_heading", "", "<b>Dimensions of each hinge</b>", 1, True,
        )
        self.inputs.addBoolValueInput(
            "split_seam", "Split seam (touching parts)", True, "", settings.split_seam
        )
        for identity, title, tooltip in _LENGTH_INPUTS:
            control = self.inputs.addValueInput(
                identity, title, "mm",
                adsk.core.ValueInput.createByString(f"{getattr(settings, identity):.15g} mm"),
            )
            control.tooltip = tooltip
        self.inputs.addIntegerSpinnerCommandInput(
            "knuckle_count", "Knuckles per hinge (odd)", 3, 15, 2, settings.knuckle_count
        )
        self.inputs.addBoolValueInput("include_pin", "Include separate pin", True, "", settings.include_pin)
        self.inputs.addTextBoxCommandInput(
            "status", "Status", "Select the hinge result." if editing else
            "Select the two coplanar exterior faces and a reference edge. Fusion detects supported touching seams automatically.", 5, True,
        )
        self._sync_mode_controls()
        self._bind(command.inputChanged, _Changed(self))
        self._bind(command.validateInputs, _Validate(self))
        self._bind(command.executePreview, _Preview(self))
        self._bind(command.execute, _Execute(self))
        self._bind(command.destroy, _Destroyed(self))

    def _open_palette_picker(self):
        # A logical session contains only plain settings and native entity refs.
        # No CommandInputs are created, so no second panel can be displayed.
        self.owner._publish_palette(self)

    def _attach_palette_commit(self, command):
        self._ensure_design()
        self.command = command
        self.inputs = command.commandInputs
        command.isExecutedWhenPreEmpted = False
        command.isAutoExecute = True
        self.commit_requested = True
        self._bind(command.execute, _Execute(self))
        self._bind(command.destroy, _Destroyed(self))

    def palette_snapshot(self):
        if not self.closed:
            selections = {}
            for identity in ("edit_target",) if self.editing else ("face_a", "face_b", "axis_edge"):
                entity = self.selection_entities.get(identity)
                selected = entity is not None and entity.isValid
                label = "Not selected"
                if selected:
                    label = getattr(entity, "name", "") or getattr(getattr(entity, "body", None), "name", "") or "Selected"
                selections[identity] = {"selected": bool(selected), "label": str(label)[:120]}
            self._palette_selections = selections
        return {"sessionId": None if self.closed else self.session_id, "endedSessionId": self.session_id if self.closed else None,
                "revision": self.revision, "phase": self.phase, "editing": self.editing,"pickingTarget":self.picking_target,
                "settings": self.palette_settings.to_dict(), "selections": self._palette_selections.copy(),
                "previewCurrent": bool(not self.closed and self.preview is not None and self.preview.isValid
                                       and self.preview_generation == self.generation and self.preview_error is None),
                "message": self.message}

    def _bind(self, event, handler):
        event.add(handler)
        self.handlers.append((event, handler))

    def _status(self, message):
        self.message = message
        control = self.inputs.itemById("status") if self.inputs is not None and not self.palette_mode else None
        if control is not None and control.text != message:
            control.text = message
        if self.palette_mode:
            self.owner._publish_palette(self)

    def _record_timings(self, operation, prepared, **measured):
        """Log only bounded aggregate stage numbers; logging cannot fail Create."""
        try:
            stages = {}
            supplied = getattr(prepared, "timings", None)
            if isinstance(supplied, Mapping):
                for name in ("source_read_ms", "planning_ms", "temporary_geometry_ms"):
                    value = supplied.get(name)
                    if (isinstance(value, (int, float)) and not isinstance(value, bool)
                            and math.isfinite(value) and value >= 0):
                        stages[name] = value
            stages.update(measured)
            message = " ".join(f"{name}={value:.3f}" for name, value in stages.items())
            adsk.core.Application.get().log(f"Partelier hinge {operation} timings: {message}")
        except Exception:
            # Timing diagnostics are ancillary to the successful model operation.
            pass

    def _log_caused_error(self, summary, error):
        """Keep native exception details while leaving ordinary input errors quiet."""
        if error.__cause__ is not None:
            try:
                self.owner._log_error(summary)
            except Exception:
                pass

    def _one_selection(self, identity, description):
        if self.palette_mode:
            entity = self.selection_entities.get(identity)
            if entity is None or not entity.isValid:
                raise ValueError(f"Select {description}.")
            return entity
        selected = self.inputs.itemById(identity)
        if selected.selectionCount != 1:
            raise ValueError(f"Select {description}.")
        entity = selected.selection(0).entity
        if entity is None or not entity.isValid:
            raise ValueError(f"Select a valid {description}.")
        return entity

    def _sync_mode_controls(self):
        if self.palette_mode:
            return
        split_seam = self.inputs.itemById("split_seam").value
        axis = self.inputs.itemById("axis_offset_mm")
        # Keep a usable stored offset when switching back to the gapped-body mode.
        if split_seam and (not axis.isValidExpression or not math.isfinite(axis.value) or axis.value <= 0):
            axis.expression = f"{HingeSettings().axis_offset_mm:.15g} mm"
        if axis.isEnabled == split_seam:
            axis.isEnabled = not split_seam
        clearance = self.inputs.itemById("seam_clearance_mm")
        if not split_seam and (not clearance.isValidExpression or not math.isfinite(clearance.value) or clearance.value <= 0):
            clearance.expression = f"{HingeSettings().seam_clearance_mm:.15g} mm"
        if clearance.isEnabled != split_seam:
            clearance.isEnabled = split_seam

    def _settings(self):
        if self.palette_mode:
            return self.palette_settings
        values = self.launch_settings.to_dict()
        for identity, title, _ in _ALL_LENGTH_INPUTS:
            control = self.inputs.itemById(identity)
            if not control.isValidExpression:
                raise ValueError(f"Enter a valid length for {title.lower()} (mm).")
            values[identity] = control.value * 10.0
        values["hinge_count"] = self.inputs.itemById("hinge_count").value
        values["knuckle_count"] = self.inputs.itemById("knuckle_count").value
        values["include_pin"] = self.inputs.itemById("include_pin").value
        values["split_seam"] = self.inputs.itemById("split_seam").value
        return HingeSettings.from_dict(values)

    def _ensure_design(self):
        if self.closed or getattr(self,'cancel_requested',False):
            raise ValueError('This hinge session was cancelled. Start again.')
        try:
            active = _active_design()
        except ValueError:
            active = None
        if not self.design.isValid or active != self.design:
            raise ValueError("Return to the design where this hinge command was opened.")

    def _basic_validate(self):
        self._ensure_design()
        settings = self._settings()
        if self.preview_error is not None:
            raise ValueError(self.preview_error)
        if self.editing:
            self._one_selection("edit_target", "a Partelier hinge result")
            if not self.edit_target_loaded:
                raise ValueError(self.edit_target_error or "Select a supported Partelier hinge result to load its dimensions.")
        else:
            self._one_selection("face_a", "face A")
            self._one_selection("face_b", "face B")
            self._one_selection("axis_edge", "a straight reference edge of A or its coincident edge on B")
        return settings

    def validate(self):
        try:
            self._basic_validate()
            return True
        except ValueError as error:
            self._status(str(error))
            return False

    @staticmethod
    def _delete_graphics(group):
        if group is not None and group.isValid and group.deleteMe() is False:
            raise RuntimeError("Fusion could not remove a temporary hinge preview.")

    def clear_preview(self):
        self.owner._cancel_native_preview(self)
        self.preview_generation = None
        self.preview_sources = None
        failed = []
        for group in ([self.preview] if self.preview is not None else []) + self.retained_preview_groups:
            try:
                self._delete_graphics(group)
            except Exception:
                failed.append(group)
        self.preview = failed[0] if failed else None
        self.retained_preview_groups = failed[1:]
        visibility_error = None
        try:
            self.preview_visibility.restore()
            self._preview_hidden_bodies = ()
        except ValueError as error:
            visibility_error = error
        if failed or visibility_error is not None:
            detail = str(visibility_error) if visibility_error is not None else "Fusion could not clear all temporary hinge graphics. Stop and Run Partelier."
            raise RuntimeError(detail)

    def _replace_preview(self, candidate):
        previous = self.preview
        if candidate is None or not candidate.isValid:
            raise ValueError("Fusion could not draw the updated hinge preview.")
        if previous is not candidate:
            try:
                self._delete_graphics(previous)
            except Exception:
                try:
                    self._delete_graphics(candidate)
                except Exception:
                    self.retained_preview_groups.append(candidate)
                raise
        self.preview = candidate
        self.preview_generation = self.generation

    def changed(self, identity):
        if self.loading_settings or identity not in _PARAMETER_IDS | _SELECTION_IDS:
            return
        if identity in {"split_seam", "edit_target"}:
            self.auto_split_detected = False
        self.owner._cancel_native_preview(self)
        self._sync_mode_controls()
        self.generation += 1
        self.preview_error = None
        if not self.palette_mode:
            self.clear_preview()
        if self.editing and identity == "edit_target":
            self.clear_preview()
            self.edit_target_loaded = False
            self.edit_target_error = None
            try:
                entity = self._one_selection("edit_target", "a Partelier hinge result")
                target = read_edit_target(self.design, entity)
                self.loading_settings = True
                try:
                    self.launch_settings = target.settings
                    self.palette_settings = target.settings
                    for key, value in target.settings.to_dict().items():
                        control = self.inputs.itemById(key) if self.inputs is not None else None
                        if control is None:
                            continue
                        if key.endswith("_mm"):
                            control.expression = f"{value:.15g} mm"
                        else:
                            control.value = value
                finally:
                    self.loading_settings = False
                self._sync_mode_controls()
                self.edit_target_loaded = True
            except ValueError as error:
                self.edit_target_error = str(error)
                self.preview_error = str(error)
        if self.palette_mode:
            self.phase = "ready" if self.validate() else ("error" if self.preview_error or self.edit_target_error else "selecting")
            if self.phase != "ready":
                self.clear_preview()
            self._status("Geometry selected. Live preview will update automatically." if self.phase == "ready" else self.message)
            return
        if self.validate():
            self._status(
                "Inputs ready. Split seam applies clearance to attached bodies; the axis stays on the seam."
                if self.inputs.itemById("split_seam").value else
                "Inputs ready. Fusion will prepare an exact temporary preview with the offset toward B."
            )

    def _auto_split_message(self):
        if self.palette_mode and self.palette_settings.output_mode == "separate":
            return "Shared edge detected. Separate hinges are centered; source bodies are unchanged. " if self.auto_split_detected else ""
        return (
            "Touching seam auto-detected. Axis centered on the seam; clearance is applied to the selected bodies when created. "
            if self.auto_split_detected else ""
        )

    def _placement_message(self, prepared):
        settings = getattr(prepared, "settings", None)
        if isinstance(settings, HingeSettings) and settings.hinge_count > 1:
            return (f"{settings.hinge_count} hinges, {settings.length_mm:g} mm each. "
                    "End margins and equal gaps applied. ")
        return ""

    def _sync_prepared_mode(self, requested, prepared):
        """Reflect only a verified automatic split-mode upgrade in the dialog."""
        effective = getattr(prepared, "settings", None)
        if (not isinstance(effective, HingeSettings) or requested.split_seam
                or not effective.split_seam):
            return
        previous_loading = self.loading_settings
        self.loading_settings = True
        try:
            if self.palette_mode:
                self.palette_settings = effective
            else:
                self.inputs.itemById("split_seam").value = True
                self._sync_mode_controls()
        finally:
            self.loading_settings = previous_loading
        self.auto_split_detected = True
        self._status(self._auto_split_message().strip())

    def _prepare(self, *, native_transaction=False):
        settings = self._basic_validate()
        keywords = {}
        if (self.command is not None or native_transaction) and (
                settings.chamfer_edges or settings.fillet_edges):
            keywords["edge_finisher"] = finish_native_results
        target = None
        if self.editing:
            entity = self._one_selection("edit_target", "a Partelier hinge result")
            target = read_edit_target(self.design, entity)
            prepared = prepare_edit_hinge(self.design, target, settings, **keywords)
        else:
            prepared = prepare_hinge(
                self.design,
                self._one_selection("face_a", "face A"),
                self._one_selection("face_b", "face B"),
                self._one_selection("axis_edge", "a straight reference edge of A or its coincident edge on B"),
                settings, **keywords,
            )
        self._sync_prepared_mode(settings, prepared)
        return prepared, target

    def _prepare_native_preview(self, generation):
        if self.closed or generation != self.generation:
            raise ValueError("This temporary preview has been superseded.")
        return self._prepare(native_transaction=True)[0]

    def _complete_native_preview(self, prepared, started, generation):
        if self.closed or generation != self.generation:
            return
        self._native_preview_generation = None
        try:
            self._ensure_design()
            self._display_preview(prepared, started)
        except Exception as error:
            self._preview_failed(error, generation)

    def _preview_failed(self, error, generation):
        if self.closed or generation != self.generation:
            return
        self._native_preview_generation = None
        self.preview_error = str(error)
        if self.palette_mode:
            self.phase = "error"
        previous = " Showing the previous valid preview; it does not match these settings." if (
            self.preview is not None and self.preview.isValid) else ""
        self._status(str(error) + previous)
        self._log_caused_error("Partelier hinge preview failed in a native operation", error)
        if not isinstance(error, ValueError):
            self.owner._log_error("Partelier could not compute or display the hinge preview")

    def _display_preview(self, prepared, started):
        # Native finish computation has already rolled back before palette
        # graphics are created. Prepared contains detached temporary bodies.
        source_state = capture_preview_sources(prepared)
        draw_started = time.perf_counter()
        candidate = preview_hinge(prepared)
        previous_hidden = self._preview_hidden_bodies
        changed_visibility = False
        try:
            target = read_edit_target(self.design, self._one_selection("edit_target", "a Partelier hinge result")) if self.editing else None
            hidden = tuple(preview_hide_bodies(prepared, target))
            changed_visibility = (len(hidden) != len(previous_hidden)
                or any(not any(body == old for old in previous_hidden) for body in hidden))
            if changed_visibility:
                self.preview_visibility.restore()
            self.preview_visibility.hide(hidden)
            self._preview_hidden_bodies = hidden
            self._replace_preview(candidate)
        except Exception:
            if self.preview is not candidate and candidate is not None and candidate.isValid:
                self._delete_graphics(candidate)
            if self.preview is None or changed_visibility:
                self.preview_visibility.restore()
                self._preview_hidden_bodies = ()
                if self.preview is not None and self.preview.isValid:
                    self.preview_visibility.hide(previous_hidden)
                    self._preview_hidden_bodies = previous_hidden
            raise
        self.preview_sources = source_state
        draw_ms = (time.perf_counter() - draw_started) * 1000.0
        if self.palette_mode:
            self.phase = "preview"
        result_message = (
            "Temporary preview ready. Rebuild replaces this hinge; Cancel restores the previous view."
            if self.editing else
            "Temporary preview ready. Create adds owned result bodies; original sources stay unchanged."
            if prepared.settings.output_mode == "separate" else
            "Temporary preview ready. Create joins the hinge into the two selected bodies."
        )
        self._status(self._auto_split_message() + self._placement_message(prepared) + result_message)
        self._record_timings(
            "preview", prepared, graphics_draw_ms=draw_ms,
            total_ms=(time.perf_counter() - started) * 1000.0,
        )

    def show_preview(self, args):
        # Custom graphics are not a persistent command result. OK must execute.
        args.isValidResult = False
        if self.palette_mode and not self.preview_requested:
            return
        if not self.validate():
            self.clear_preview()
            return
        if (self.preview is not None and self.preview.isValid
                and self.preview_generation == self.generation):
            if self.palette_mode:
                self.phase = "preview"
                self._status("Temporary preview is current. Create or Rebuild from Partelier.")
            return
        if self.palette_mode and self._native_preview_generation == self.generation:
            return
        try:
            if self.retained_preview_groups:
                self.clear_preview()
            started = time.perf_counter()
            settings = self._settings()
            native_busy = self.owner._native_preview is not None and self.owner._native_preview.busy
            if self.palette_mode and (settings.fillet_edges or settings.chamfer_edges or native_busy):
                generation = self.generation
                self._native_preview_generation = generation
                self.phase = "computing"
                self._status("Computing the joined hinge edge finish…")
                self.owner._queue_native_preview(self, generation, started)
                return
            prepared, _ = self._prepare()
            self._display_preview(prepared, started)
        except ValueError as error:
            self._preview_failed(error, self.generation)

    def execute(self, args):
        try:
            if self.palette_mode and not self.commit_requested:
                raise ValueError("Use Create in the Partelier palette to confirm the hinge.")
            # Never accept the cached graphics as evidence that sources are current.
            total_started = time.perf_counter()
            prepared, target = self._prepare()
            self.clear_preview()
            persistence_started = time.perf_counter()
            from ... import operations
            start=self.design.timeline.count
            if self.editing:
                anchor=rebuild_hinge(self.design, target, prepared)
            else:
                anchor=create_hinge(self.design, prepared)
            operations.capture(self.design,anchor,'hinge',prepared.settings.to_dict(),start,editing=self.editing)
            persistence_ms = (time.perf_counter() - persistence_started) * 1000.0
            self._record_timings(
                "rebuild" if self.editing else "create", prepared,
                persistence_ms=persistence_ms,
                total_ms=(time.perf_counter() - total_started) * 1000.0,
            )
            if self.palette_mode:
                self.phase = "created"
                self._status("Hinge rebuilt successfully." if self.editing else (
                    "Hinge joined into the selected bodies successfully."
                    if prepared.settings.output_mode == "attached" else
                    "Hinge created successfully. Original sources are unchanged."))
        except Exception as error:
            if self.palette_mode:
                self.phase = "error"
                self._status(str(error))
            args.executeFailed = True
            args.executeFailedMessage = str(error) if isinstance(error, ValueError) else (
                "The hinge could not be created. See the Fusion log for details."
            )
            if isinstance(error, ValueError):
                self._status(str(error))
                self._log_caused_error("Partelier hinge creation or rebuild failed in a native operation", error)
            else:
                self.owner._unexpected_error("Partelier could not create or rebuild the hinge")

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.palette_mode and self.phase not in {"created", "error", "cancelled"}:
            self.phase = "cancelled"
            self.message = "Hinge cancelled. Original bodies are unchanged."
        try:
            self.clear_preview()
        except Exception:
            self.owner._log_error("Partelier could not clear its hinge preview")
        for event, handler in self.handlers:
            try:
                event.remove(handler)
            except Exception:
                self.owner._log_error("Partelier could not detach a hinge session handler")
        self.handlers.clear()
        if self in self.owner._sessions:
            self.owner._sessions.remove(self)
        if self.palette_mode:
            self.owner._publish_palette(self)
        self.selection_entities.clear()


class _Created(adsk.core.CommandCreatedEventHandler):
    def __init__(self, owner, editing):
        super().__init__()
        self.owner = owner
        self.editing = editing

    def notify(self, args):
        session = None
        self.owner._opening = False
        pending = self.owner._palette_pending
        self.owner._palette_pending = None
        if self.owner._cancelled_palette_opening:
            self.owner._cancelled_palette_opening=False
            args.command.isAutoExecute=True;args.command.isOKButtonVisible=False
            return
        try:
            if pending is not None:
                session = pending
                if session.closed or session.editing != self.editing:
                    raise ValueError("This hinge creation session has ended.")
                session._attach_palette_commit(args.command)
                return
            settings = HingeSettings() if self.editing else (
                self.owner._pending_settings or HingeSettings()
            )
            if not self.editing:
                self.owner._pending_settings = None
            session = _Session(self.owner, args.command, self.editing)
            self.owner._sessions.append(session)
            session.open(settings)
        except Exception as error:
            self.owner._pending_settings = None
            self.owner._opening = False
            # No-input commands must not auto-execute after failed setup.
            args.command.isAutoExecute = False
            if session is not None:
                if session.palette_mode:
                    session.phase = "error"
                    session.message = str(error) + " Press Esc, then start again."
                session.close()
            args.command.isOKButtonVisible = False
            self.owner._unexpected_error("Partelier could not open the hinge command")


class _Changed(adsk.core.InputChangedEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        try:
            self.session.changed(args.input.id)
        except Exception:
            self.session.owner._unexpected_error("Partelier could not update hinge inputs")


class _Validate(adsk.core.ValidateInputsEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        args.areInputsValid = False
        try:
            args.areInputsValid = self.session.validate()
        except Exception:
            self.session.owner._log_error("Partelier could not validate hinge inputs")


class _Preview(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        args.isValidResult = False
        try:
            self.session.show_preview(args)
        except Exception:
            self.session.preview_error = "The temporary preview failed. Change the inputs or cancel and retry."
            if self.session.palette_mode:
                self.session.phase = "error"
            self.session._status(self.session.preview_error)
            self.session.owner._log_error("Partelier could not display the hinge preview")


class _Execute(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        self.session.execute(args)


class _Destroyed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        self.session.close()


class _ContextCommandTerminated(adsk.core.ApplicationCommandEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        if self.owner._palette_action_busy or args.commandId in (CREATE_COMMAND_ID, EDIT_COMMAND_ID, PREVIEW_COMMAND_ID, "SelectCommand"):
            return
        try:
            self.owner._validate_palette_previews()
        except Exception:
            self.owner._log_error("Partelier could not verify a preview after a Fusion command")


class _ContextDocumentDeactivating(adsk.core.DocumentEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        for session in list(self.owner._sessions):
            if session.palette_mode:
                session.message = "The design changed. Start a new hinge session in the active design."
                session.phase = "cancelled"
                session.close()
