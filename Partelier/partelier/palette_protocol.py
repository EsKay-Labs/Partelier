"""Host-independent, tool-specific HTML message validation."""

from dataclasses import dataclass
import json
import uuid

from .tools.hinge.settings import HingeSettings
from .tools.snap_fit.settings import SnapFitSettings
from .tools.patterns.settings import PatternSettings
from .tools.details.settings import DetailSettings
from .tools.fans.settings import FanSettings
from .tools.mechanisms.settings import MechanismSettings
from .tools.finishing.settings import FinishingSettings
from .diagnostics import validate_ui_entries


PROTOCOL_VERSION = 1
SESSION_SETTINGS_ACTIONS = frozenset({"hinge_update", "hinge_preview", "hinge_commit"})
SESSION_ACTIONS = SESSION_SETTINGS_ACTIONS | {"hinge_cancel", "hinge_focus", "hinge_reset"}
SNAP_SESSION_SETTINGS_ACTIONS = frozenset({"snap_update", "snap_preview", "snap_commit"})
SNAP_SESSION_ACTIONS = SNAP_SESSION_SETTINGS_ACTIONS | {"snap_cancel", "snap_focus", "snap_reset"}
PATTERN_SETTINGS_ACTIONS=frozenset({"pattern_update","pattern_preview","pattern_commit"})
PATTERN_SESSION_ACTIONS=PATTERN_SETTINGS_ACTIONS|{"pattern_cancel","pattern_focus","pattern_finish_faces","pattern_clear_faces","pattern_reset"}
DETAIL_SETTINGS_ACTIONS=frozenset({'detail_update','detail_preview','detail_commit'})
DETAIL_SESSION_ACTIONS=DETAIL_SETTINGS_ACTIONS|{'detail_cancel','detail_focus','detail_reset','detail_finish_sides','detail_clear_sides'}
FAN_SETTINGS_ACTIONS=frozenset({'fan_update','fan_preview','fan_commit'})
FAN_SESSION_ACTIONS=FAN_SETTINGS_ACTIONS|{'fan_cancel','fan_focus','fan_reset'}
MECHANISM_SETTINGS_ACTIONS=frozenset({"mechanism_update","mechanism_preview","mechanism_commit"})
MECHANISM_SESSION_ACTIONS=MECHANISM_SETTINGS_ACTIONS|{"mechanism_cancel","mechanism_focus","mechanism_reset"}
FINISHING_SETTINGS_ACTIONS=frozenset({"finishing_update","finishing_preview","finishing_commit"})
FINISHING_SESSION_ACTIONS=FINISHING_SETTINGS_ACTIONS|{"finishing_cancel","finishing_focus","finishing_reset"}
ALLOWED_ACTIONS = frozenset({"finishing_begin","finishing_status"})|FINISHING_SESSION_ACTIONS|frozenset({"mechanism_begin","mechanism_status"})|MECHANISM_SESSION_ACTIONS|frozenset({
    "ready", "open_input_check", "hinge_create", "hinge_edit", "hinge_begin", "hinge_status",
    "snap_begin", "snap_status", "pattern_begin", "pattern_status", "pattern_export", "diagnostic_log",
    'fan_begin','fan_status','detail_begin','detail_status','operations_list','operation_edit','operation_delete',
}) | SESSION_ACTIONS | SNAP_SESSION_ACTIONS | PATTERN_SESSION_ACTIONS | DETAIL_SESSION_ACTIONS | FAN_SESSION_ACTIONS


@dataclass(frozen=True)
class PaletteRequest:
    request_id: str
    settings: HingeSettings | SnapFitSettings | PatternSettings | FanSettings | None = None
    session_id: str | None = None
    revision: int | None = None
    editing: bool = False
    target: str | None = None
    diagnostics: tuple = ()
    operation_id: str | None = None


def read_request(action, raw_data):
    """Reject malformed or unsupported messages before any host operation."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("This action is unavailable in the tool library.")
    if not isinstance(raw_data, str) or len(raw_data) > (16384 if action=='diagnostic_log' else 4096):
        raise ValueError("The UI message is invalid or too large.")
    try:
        request = json.loads(raw_data)
    except (ValueError, TypeError) as error:
        raise ValueError("The UI message must contain valid JSON.") from error
    if not isinstance(request, dict):
        raise ValueError("The UI message must be an object.")
    if type(request.get("protocol")) is not int or request["protocol"] != PROTOCOL_VERSION:
        raise ValueError("Reopen the tool library to use a compatible UI version.")
    request_id = request.get("requestId")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 80:
        raise ValueError("The UI message needs a valid request identifier.")
    if action=='diagnostic_log':
        if set(request)!={'protocol','requestId','entries'}:
            raise ValueError('Unexpected diagnostic message data.')
        return PaletteRequest(request_id,diagnostics=validate_ui_entries(request['entries']))
    if action in {'operations_list','operation_edit','operation_delete'}:
        expected={'protocol','requestId'} | ({'operationId'} if action!='operations_list' else set())
        if set(request)!=expected:raise ValueError('Unexpected operation request data.')
        identity=request.get('operationId')
        if identity is not None:
            try:
                if not isinstance(identity,str) or str(uuid.UUID(identity))!=identity:raise ValueError()
            except (ValueError,AttributeError,TypeError):raise ValueError('Choose a saved Partelier operation.')
        elif action!='operations_list':raise ValueError('Choose a saved Partelier operation.')
        return PaletteRequest(request_id,operation_id=identity)
    fan=action.startswith('fan_')
    snap = action.startswith("snap_")
    pattern = action.startswith("pattern_")
    tool_name = "pattern" if pattern else "snap-fit" if snap else "hinge"
    detail=action.startswith('detail_')
    if detail:tool_name='Small detail'
    if fan:tool_name="fan"
    settings_type = FanSettings if fan else DetailSettings if detail else PatternSettings if pattern else SnapFitSettings if snap else HingeSettings
    if action.startswith("mechanism_"):settings_type=MechanismSettings;tool_name="mechanism"
    if action.startswith("finishing_"):settings_type=FinishingSettings;tool_name="finishing"
    settings_actions = FINISHING_SETTINGS_ACTIONS | MECHANISM_SETTINGS_ACTIONS | SESSION_SETTINGS_ACTIONS | SNAP_SESSION_SETTINGS_ACTIONS | PATTERN_SETTINGS_ACTIONS | DETAIL_SETTINGS_ACTIONS | FAN_SETTINGS_ACTIONS
    session_actions = FINISHING_SESSION_ACTIONS | MECHANISM_SESSION_ACTIONS | SESSION_ACTIONS | SNAP_SESSION_ACTIONS | PATTERN_SESSION_ACTIONS | DETAIL_SESSION_ACTIONS | FAN_SESSION_ACTIONS
    begin_actions = {"finishing_begin"} | {"mechanism_begin"} | {"hinge_begin", "snap_begin", "pattern_begin",'detail_begin','fan_begin'}
    focus_actions = {"finishing_focus"} | {"mechanism_focus"} | {"hinge_focus", "snap_focus", "pattern_focus",'detail_focus','fan_focus'}
    expected = {"protocol", "requestId"}
    if action in {"hinge_create"} | begin_actions | settings_actions:
        expected.add("settings")
    if action in begin_actions:
        expected.add("editing")
    if action in session_actions:
        expected.add("sessionId")
    if action in settings_actions:
        expected.add("revision")
    if action in focus_actions:
        expected.add("target")
    if set(request) != expected:
        raise ValueError("Unexpected data in the UI message.")
    session_id = request.get("sessionId")
    if action in session_actions:
        try:
            if not isinstance(session_id, str) or str(uuid.UUID(session_id)) != session_id:
                raise ValueError()
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError(f"Use the current {tool_name} session identifier.") from error
    revision = request.get("revision")
    if action in settings_actions and (type(revision) is not int or not 0 <= revision <= 1_000_000_000):
        raise ValueError(f"Use a valid {tool_name} settings revision.")
    editing = request.get("editing", False)
    if action in begin_actions and type(editing) is not bool:
        raise ValueError(f"{tool_name.capitalize()} editing mode must be true or false.")
    target = request.get("target")
    targets={'face_a','face_b','edit_target','lip_sides'} if detail else {"faces","add_face","body","edit_target"} if pattern else {"face_a", "face_b", "axis_edge", "edit_target"}
    if fan:targets={'circle','outline','edit_target'}
    if action.startswith("mechanism_"):targets={'edit_target'}
    if action.startswith("finishing_"):targets={'face','edit_target'}
    if action in focus_actions and (not isinstance(target, str) or target not in targets):
        raise ValueError(f"Select a supported {tool_name} geometry target.")
    settings = None
    if "settings" in expected:
        supplied = request["settings"]
        defaults = settings_type().to_dict()
        if not isinstance(supplied, dict) or not set(supplied) <= set(defaults):
            raise ValueError(f"Use the supported {tool_name} dimension fields.")
        # Active sessions require atomic full snapshots; a missing field must
        # never silently reset an edited dimension to a default.
        values = supplied if action in settings_actions else {**defaults, **supplied}
        settings = settings_type.from_dict(values)
    return PaletteRequest(request_id, settings, session_id, revision, editing, target)
