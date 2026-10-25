"""Fusion add-in composition and the original honeycomb input diagnostic."""

import sys
import traceback
import json
from pathlib import Path

import adsk.core
import adsk.fusion

from .settings import HoneycombSettings
from .palette import ToolLibrary
from .tools.hinge.command import HingeCommands
from .tools.snap_fit.command import SnapCommands
from .tools.patterns.command import PatternCommands
from .tools.details.command import DetailCommands
from . import diagnostics


COMMAND_ID = "sktech_partelier_honeycomb_inputs_7947c039"
COMMAND_NAME = "Partelier: Check honeycomb inputs"
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"

_created_handler = None
_sessions = []
_tool_library = ToolLibrary()
_hinge_commands = None
_snap_commands = None
_pattern_commands = None
_detail_commands = None


def report_error(summary):
    """Show the real failure and expose the full traceback in Text Commands."""
    app = adsk.core.Application.get()
    diagnostics.emit('addin.error',summary=summary,traceback=traceback.format_exc())
    details = traceback.format_exc()
    exception = sys.exc_info()[1]
    message = summary + "."
    if exception is not None:
        reason = str(exception).strip() or type(exception).__name__
        message += "\n\n" + reason[:1200]
    try:
        app.log(f"{summary}\n{details}")
    except Exception:
        # A logging failure must not replace the original modeling error.
        pass
    try:
        palette = app.userInterface.palettes.itemById("TextCommands")
        if palette is not None:
            palette.isVisible = True
    except Exception:
        pass
    app.userInterface.messageBox(
        message + "\n\nFull details: View > Show Text Commands.", "Partelier"
    )


def start():
    """Register owned commands once and show the HTML tool library on Run."""
    global _created_handler, _hinge_commands, _snap_commands, _pattern_commands, _detail_commands
    version=json.loads((Path(__file__).resolve().parent.parent/'Partelier.manifest').read_text(encoding='utf-8'))['version']
    diagnostics.start(version)
    if _created_handler is not None:
        _tool_library.show()
        return
    ui = adsk.core.Application.get().userInterface
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    if panel is None:
        raise RuntimeError("The Fusion Design Add-Ins panel is unavailable.")
    try:
        definition = ui.commandDefinitions.itemById(COMMAND_ID)
        if definition is None:
            definition = ui.commandDefinitions.addButtonDefinition(
                COMMAND_ID,
                COMMAND_NAME,
                "Check one solid body and honeycomb dimensions. Creates no geometry.",
            )
        _created_handler = _Created()
        definition.commandCreated.add(_created_handler)
        if panel.controls.itemById(COMMAND_ID) is None:
            panel.controls.addCommand(definition)
        _hinge_commands = HingeCommands(report_error=report_error)
        _hinge_commands.start()
        _snap_commands = SnapCommands(report_error=report_error)
        _snap_commands.start()
        _pattern_commands=PatternCommands(report_error=report_error)
        _pattern_commands.start()
        _detail_commands=DetailCommands(report_error=report_error)
        _detail_commands.start()
        _tool_library.start(
            WORKSPACE_ID, PANEL_ID, COMMAND_ID, report_error,
            hinge_commands=_hinge_commands, snap_commands=_snap_commands, pattern_commands=_pattern_commands, detail_commands=_detail_commands,
        )
        _tool_library.show()
        diagnostics.emit('addin.ready',version=version,loaded_addin=__file__)
    except Exception:
        stop()
        raise


def stop():
    """Remove only this add-in's command, controls, and retained handlers."""
    global _created_handler, _hinge_commands, _snap_commands, _pattern_commands, _detail_commands
    diagnostics.emit('addin.stop.begin')
    app = adsk.core.Application.get()
    ui = app.userInterface
    errors = []

    def attempt(operation):
        try:
            return operation()
        except Exception:
            errors.append(traceback.format_exc())
            return None

    try:
        if ui.activeCommand == COMMAND_ID:
            attempt(ui.terminateActiveCommand)
        attempt(_tool_library.stop)
        if _hinge_commands is not None:
            attempt(_hinge_commands.stop)
        if _snap_commands is not None:
            attempt(_snap_commands.stop)
        if _pattern_commands is not None:
            attempt(_pattern_commands.stop)
        if _detail_commands is not None:attempt(_detail_commands.stop)
        workspace = attempt(lambda: ui.workspaces.itemById(WORKSPACE_ID))
        panel = attempt(lambda: workspace.toolbarPanels.itemById(PANEL_ID)) if workspace else None
        control = attempt(lambda: panel.controls.itemById(COMMAND_ID)) if panel else None
        if control is not None:
            attempt(control.deleteMe)
        definition = attempt(lambda: ui.commandDefinitions.itemById(COMMAND_ID))
        if definition is not None:
            if _created_handler is not None:
                attempt(lambda: definition.commandCreated.remove(_created_handler))
            attempt(definition.deleteMe)
    finally:
        _created_handler = None
        _hinge_commands = None
        _snap_commands = None
        _pattern_commands = None
        _detail_commands = None
        _sessions.clear()
    for error in errors:
        app.log(f"Partelier shutdown cleanup failed:\n{error}")
    diagnostics.emit('addin.stop.end',errors=len(errors))


def _read_inputs(inputs):
    """Recheck both selection and dimensions at validation and execution time."""
    selected = inputs.itemById("body")
    if selected.selectionCount != 1:
        raise ValueError("Select one closed solid body.")
    body = adsk.fusion.BRepBody.cast(selected.selection(0).entity)
    if body is None or not body.isValid or not body.isSolid:
        raise ValueError("Select a valid closed solid body, not a surface or mesh.")
    cell = inputs.itemById("cell_size")
    wall = inputs.itemById("wall_thickness")
    if not cell.isValidExpression or not wall.isValidExpression:
        raise ValueError("Enter valid lengths for cell size and wall thickness.")
    return body, HoneycombSettings.from_centimetres(cell.value, wall.value)


class _Session:
    """Own only the event handlers for one open command dialog."""

    def __init__(self, command):
        self.inputs = command.commandInputs
        self.handlers = []

    def bind(self, event, handler):
        event.add(handler)
        self.handlers.append(handler)

    def validate(self):
        try:
            _read_inputs(self.inputs)
            self.inputs.itemById("status").text = (
                "Inputs are valid. Check inputs shows a summary; it creates no geometry."
            )
            return True
        except ValueError as error:
            self.inputs.itemById("status").text = str(error)
            return False


class _Created(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            command = args.command
            command.isExecutedWhenPreEmpted = False
            inputs = command.commandInputs
            inputs.addTextBoxCommandInput(
                "scope",
                "",
                "Check honeycomb inputs for a closed solid. Geometry generation "
                "is not available in this diagnostic.",
                3,
                True,
            )
            app = adsk.core.Application.get()
            if adsk.fusion.Design.cast(app.activeProduct) is None:
                inputs.itemById("scope").text = "Open a Fusion Design document first."
                command.isOKButtonVisible = False
                return
            command.okButtonText = "Check inputs"
            selection = inputs.addSelectionInput(
                "body", "Solid body", "Select one closed solid body"
            )
            selection.addSelectionFilter("SolidBodies")
            selection.setSelectionLimits(1, 1)
            defaults = HoneycombSettings()
            cell = inputs.addValueInput(
                "cell_size",
                "Cell size",
                "mm",
                adsk.core.ValueInput.createByString(f"{defaults.cell_size_mm} mm"),
            )
            cell.tooltip = "Distance between opposite hexagon wall centre lines."
            inputs.addValueInput(
                "wall_thickness",
                "Wall thickness",
                "mm",
                adsk.core.ValueInput.createByString(f"{defaults.wall_thickness_mm} mm"),
            )
            inputs.addTextBoxCommandInput(
                "status", "Status", "Select one closed solid body.", 3, True
            )
            session = _Session(command)
            _sessions.append(session)
            session.bind(command.inputChanged, _Changed(session))
            session.bind(command.validateInputs, _Validate(session))
            session.bind(command.execute, _Execute(session))
            session.bind(command.destroy, _Destroyed(session))
        except Exception:
            args.command.isOKButtonVisible = False
            report_error("Partelier could not open the input dialog")


class _Changed(adsk.core.InputChangedEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        if args.input.id not in ("body", "cell_size", "wall_thickness"):
            return
        try:
            self.session.validate()
        except Exception:
            report_error("Partelier could not check the changed inputs")


class _Validate(adsk.core.ValidateInputsEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        args.areInputsValid = False
        try:
            args.areInputsValid = self.session.validate()
        except Exception:
            report_error("Partelier could not validate the inputs")


class _Execute(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        try:
            body, settings = _read_inputs(self.session.inputs)
            adsk.core.Application.get().userInterface.messageBox(
                f"Body: {body.name}\n"
                f"Cell size: {settings.cell_size_mm:g} mm\n"
                f"Wall thickness: {settings.wall_thickness_mm:g} mm\n\n"
                "Inputs checked. No geometry was created or changed.\n"
                "These checks do not establish printability or strength.",
                "Partelier",
            )
        except Exception:
            args.executeFailed = True
            args.executeFailedMessage = "Input check failed. No geometry was created."
            report_error("Partelier could not check the inputs")


class _Destroyed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        if self.session in _sessions:
            _sessions.remove(self.session)
        self.session.handlers.clear()
