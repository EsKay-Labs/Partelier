"""Host-independent, tool-specific HTML message validation."""

from dataclasses import dataclass
import json
import uuid

from .tools.hinge.settings import HingeSettings


PROTOCOL_VERSION = 1
SESSION_SETTINGS_ACTIONS = frozenset({"hinge_update", "hinge_preview", "hinge_commit"})
SESSION_ACTIONS = SESSION_SETTINGS_ACTIONS | {"hinge_cancel", "hinge_focus"}
ALLOWED_ACTIONS = frozenset({
    "ready", "open_input_check", "hinge_create", "hinge_edit", "hinge_begin", "hinge_status",
}) | SESSION_ACTIONS


@dataclass(frozen=True)
class PaletteRequest:
    request_id: str
    settings: HingeSettings | None = None
    session_id: str | None = None
    revision: int | None = None
    editing: bool = False
    target: str | None = None


def read_request(action, raw_data):
    """Reject malformed or unsupported messages before any host operation."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("This action is unavailable in the tool library.")
    if not isinstance(raw_data, str) or len(raw_data) > 4096:
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
    expected = {"protocol", "requestId"}
    if action in {"hinge_create", "hinge_begin"} | SESSION_SETTINGS_ACTIONS:
        expected.add("settings")
    if action == "hinge_begin":
        expected.add("editing")
    if action in SESSION_ACTIONS:
        expected.add("sessionId")
    if action in SESSION_SETTINGS_ACTIONS:
        expected.add("revision")
    if action == "hinge_focus":
        expected.add("target")
    if set(request) != expected:
        raise ValueError("Unexpected data in the UI message.")
    session_id = request.get("sessionId")
    if action in SESSION_ACTIONS:
        try:
            if not isinstance(session_id, str) or str(uuid.UUID(session_id)) != session_id:
                raise ValueError()
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError("Use the current hinge session identifier.") from error
    revision = request.get("revision")
    if action in SESSION_SETTINGS_ACTIONS and (type(revision) is not int or not 0 <= revision <= 1_000_000_000):
        raise ValueError("Use a valid hinge settings revision.")
    editing = request.get("editing", False)
    if action == "hinge_begin" and type(editing) is not bool:
        raise ValueError("Hinge editing mode must be true or false.")
    target = request.get("target")
    if action == "hinge_focus" and (not isinstance(target, str) or target not in {"face_a", "face_b", "axis_edge", "edit_target"}):
        raise ValueError("Select a supported hinge geometry target.")
    settings = None
    if "settings" in expected:
        supplied = request["settings"]
        defaults = HingeSettings().to_dict()
        if not isinstance(supplied, dict) or not set(supplied) <= set(defaults):
            raise ValueError("Use the supported hinge dimension fields.")
        # Active sessions require atomic full snapshots; a missing field must
        # never silently reset an edited dimension to a default.
        values = supplied if action in SESSION_SETTINGS_ACTIONS else {**defaults, **supplied}
        settings = HingeSettings.from_dict(values)
    return PaletteRequest(request_id, settings, session_id, revision, editing, target)
