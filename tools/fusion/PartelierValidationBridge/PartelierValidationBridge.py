"""Development-only file queue for fixed allowlisted native Fusion probes.

The watcher performs file I/O and fireCustomEvent only. Fusion model/UI reads and
the fixed probe run exclusively in a main-thread custom-event callback. This is
an adaptation of the file-queue/custom-event technique, not StructForge code.
"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid


PROTOCOL_VERSION = 2
SCENARIO = "joined_finish"
PROBES = {
    "joined_finish": ("tools", "fusion", "JoinFinishProbe", "JoinFinishProbe.py"),
    "snap_fit": ("tools", "fusion", "SnapFitProbe", "SnapFitProbe.py"),
    "patterns": ("tools", "fusion", "PatternProbe", "PatternProbe.py"),
    "pattern_status": ("tools", "fusion", "PatternStatusProbe", "PatternStatusProbe.py"),
}
SCENARIOS = frozenset(PROBES)
EVENT_ID = "sktech_partelier_validation_bridge_tick_946fef9c"
MAX_REQUEST_BYTES = 2048
MAX_BUSY_SECONDS = 30.0
IDLE_COMMANDS = frozenset(("", "SelectCommand"))
STATE = {}


def queue_root():
    return Path(tempfile.gettempdir()) / "PartelierValidationBridge"


def canonical_request_id(value):
    if not isinstance(value, str):
        raise ValueError("Request identifier must be a canonical UUID.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError("Request identifier must be a canonical UUID.") from error
    if str(parsed) != value or parsed.version != 4:
        raise ValueError("Request identifier must be a canonical UUID version 4.")
    return value


def validate_request(value, filename_id):
    canonical_request_id(filename_id)
    if not isinstance(value, dict) or set(value) != {"version", "request_id", "scenario", "submitted_at", "session_id"}:
        raise ValueError("Unexpected validation request structure.")
    if type(value["version"]) is not int or value["version"] != PROTOCOL_VERSION:
        raise ValueError("Unsupported validation protocol version.")
    if canonical_request_id(value["request_id"]) != filename_id:
        raise ValueError("Request identifier must match its queue filename.")
    canonical_request_id(value["session_id"])
    if not isinstance(value["scenario"], str) or value["scenario"] not in SCENARIOS:
        raise ValueError("Only fixed allowlisted validation scenarios are allowed.")
    submitted = value["submitted_at"]
    try:
        finite = not isinstance(submitted, bool) and isinstance(submitted, (int, float)) and math.isfinite(submitted)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("Submission time must be finite.")
    if submitted < 0 or submitted > time.time() + 300:
        raise ValueError("Submission time is invalid.")
    return value


def atomic_json(path, value, attempts=4):
    """Publish whole JSON files, with bounded retries for Windows file locks."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    try:
        temporary.write_text(data, encoding="utf-8")
        for attempt in range(attempts):
            try:
                os.replace(temporary, path)
                return
            except OSError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def read_json(path, max_bytes=MAX_REQUEST_BYTES):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError("Validation file is a link or too large.")
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Validation file is too large.")
    return json.loads(data.decode("utf-8"))


def source_manifest(repo_root):
    """Hash the complete local product runtime and all fixed probe sources."""
    repo_root = Path(repo_root).resolve()
    runtime_root = repo_root / "Partelier" / "partelier"
    probes = [repo_root.joinpath(*relative) for relative in PROBES.values()]
    paths = sorted(runtime_root.rglob("*.py")) + probes
    if not runtime_root.is_dir() or not paths or any(not path.is_file() for path in probes):
        raise ValueError("The fixed validation source files are missing.")
    files = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(repo_root):
            raise ValueError("Validation source files must stay inside the local project.")
        files[path.relative_to(repo_root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for name, value in sorted(files.items()):
        digest.update((name + "\0" + value + "\n").encode("utf-8"))
    return {"sha256": digest.hexdigest(), "files": files}


def _status(state, detail="", request_id=None):
    value = {"version": PROTOCOL_VERSION, "state": state, "detail": detail,
             "request_id": request_id, "updated_at": time.time(),
             "pid": os.getpid(), "scenario": (STATE.get("active") or {}).get("scenario", SCENARIO),
             "scenarios": sorted(SCENARIOS), "session_id": STATE.get("session_id")}
    atomic_json(STATE["queue"] / "status.json", value)


def _write_result(request_id, state, detail="", report=None, manifest=None, *, queue=None, session_id=None,
                  scenario=SCENARIO):
    queue = Path(queue) if queue is not None else STATE["queue"]
    value = {"version": PROTOCOL_VERSION, "request_id": request_id,
             "scenario": scenario, "state": state, "detail": detail,
             "completed_at": time.time(), "success": False,
             "session_id": session_id or STATE.get("session_id")}
    if report is not None:
        value["report"] = report
        value["success"] = state == "complete" and report.get("success") is True
    if manifest is not None:
        value["sources"] = manifest
    atomic_json(queue / "results" / (request_id + ".json"), value)
    (queue / "requests" / (request_id + ".json")).unlink(missing_ok=True)
    return value


def _next_request():
    for path in sorted((STATE["queue"] / "requests").glob("*.json")):
        try:
            request_id = canonical_request_id(path.stem)
        except ValueError:
            continue
        result_path = STATE["queue"] / "results" / path.name
        if result_path.exists():
            path.unlink(missing_ok=True)
            continue
        try:
            request = validate_request(read_json(path), request_id)
            if request["session_id"] != STATE["session_id"]:
                _write_result(request_id, "cancelled", "Request belongs to an earlier bridge Run; resubmit it.",
                              session_id=request["session_id"], scenario=request["scenario"])
                continue
            return request
        except (ValueError, OSError, UnicodeError) as error:
            _write_result(request_id, "error", "Rejected request: " + str(error))
    return None


def _complete(request_id, report, job=None):
    """Finalize even an old session's cancelled job, without touching a new Run."""
    active = job if job is not None else STATE.get("active")
    if active is None or active["request_id"] != request_id or active.get("finalized"):
        return
    queue = active.get("queue", STATE["queue"])
    session_id = active.get("session_id", STATE.get("session_id"))
    is_current = STATE.get("active") is active and STATE.get("session_id") == session_id
    failure = None
    try:
        if not isinstance(report, dict):
            raise ValueError("Probe did not return a report object.")
        after = source_manifest(active.get("repo") or STATE["repo"])
        changed = after["sha256"] != active["sources"]["sha256"]
        cancel_event = active.get("cancel_event")
        cancelled = bool(report.get("cancelled") or (cancel_event is not None and cancel_event.is_set()))
        state = "cancelled" if cancelled else "error" if changed else "complete"
        detail = "Validation cancelled by bridge Stop; probe cleanup finished." if cancelled else (
            "Source changed while the probe was running; rerun validation." if changed else "")
        value = _write_result(request_id, state, detail, report, active["sources"],
                              queue=queue, session_id=session_id, scenario=active.get("scenario", SCENARIO))
        if changed:
            value["sources_after"] = after
            atomic_json(queue / "results" / (request_id + ".json"), value)
    except Exception as error:
        failure = "Could not finalize validation: " + str(error)
        try:
            _write_result(request_id, "error", failure, manifest=active["sources"],
                          queue=queue, session_id=session_id, scenario=active.get("scenario", SCENARIO))
        except Exception:
            pass
    finally:
        active["finalized"] = True
        sys.modules.pop(active["module_name"], None)
        if is_current:
            STATE["active"] = None
            STATE["busy"] = None
            try:
                state = "stopped" if STATE.get("stopped") else "error" if failure else "ready"
                _status(state, failure or ("Validation cleanup finished." if STATE.get("stopped")
                                         else "Waiting for a validation request."))
            except Exception:
                pass


def _start_request(request):
    request_id = request["request_id"]
    module_name = "_partelier_validation_probe_" + request_id.replace("-", "")
    manifest = None
    try:
        manifest = source_manifest(STATE["repo"])
        probe_path = STATE["repo"].joinpath(*PROBES[request["scenario"]])
        spec = importlib.util.spec_from_file_location(module_name, probe_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        job = {"request_id": request_id, "scenario": request["scenario"], "module_name": module_name,
               "sources": manifest, "started": time.monotonic(), "module": module,
               "session_id": STATE["session_id"], "queue": STATE["queue"], "repo": STATE["repo"],
               "cancel_event": threading.Event(), "finalized": False}
        STATE["active"] = job
        _status("running", "Running " + request["scenario"] + " in the current document.", request_id)
        spec.loader.exec_module(module)
        report_path = STATE["queue"] / "probe" / (request_id + ".json")
        module.run({"quiet": True, "no_auto_terminate": True, "report_path": str(report_path),
                    "cancel_requested": job["cancel_event"].is_set,
                    "on_complete": lambda report: _complete(request_id, report, job)})
    except Exception as error:
        _write_result(request_id, "error", "Probe could not start: " + str(error), manifest=manifest,
                      scenario=request["scenario"])
        sys.modules.pop(module_name, None)
        STATE["active"] = None
        _status("error", "The previous validation could not start.", request_id)


def _tick():
    """Only this main-thread event handler reads Fusion state or invokes probes."""
    if STATE.get("stopped"):
        return
    active = STATE.get("active")
    if active is not None:
        _status("running", "Waiting for the probe's command-destroy report.", active["request_id"])
        return
    request = _next_request()
    if request is None:
        STATE["busy"] = None
        _status("ready", "Waiting for a validation request.")
        return
    request_id = request["request_id"]
    command = STATE["app"].userInterface.activeCommand
    if command not in IDLE_COMMANDS and request['scenario'] != 'pattern_status':
        busy = STATE.get("busy")
        if busy is None or busy["request_id"] != request_id:
            busy = {"request_id": request_id, "since": time.monotonic()}
            STATE["busy"] = busy
        detail = "Fusion active command " + repr(command) + " is busy; leave it idle to allow script validation."
        if time.monotonic() - busy["since"] >= MAX_BUSY_SECONDS:
            _write_result(request_id, "blocked", detail, scenario=request["scenario"])
            STATE["busy"] = None
        _status("blocked", detail, request_id)
        return
    STATE["busy"] = None
    _start_request(request)


def _watch(stop_event, app):
    """Worker: plain file checks plus Fusion's documented event-queue entry."""
    last_signal = 0.0
    last_heartbeat = 0.0
    while not stop_event.wait(0.5):
        try:
            now = time.monotonic()
            active = STATE.get("active")
            if active is not None and now - last_heartbeat >= 5:
                _status("running", "The probe is working on Fusion's main thread.", active["request_id"])
                last_heartbeat = now
            pending = any((STATE["queue"] / "requests").glob("*.json"))
            signal_pending = STATE.get("signal_pending")
            already_queued = signal_pending is not None and signal_pending.is_set()
            if not already_queued and (pending or now - last_signal >= 5):
                if signal_pending is not None:
                    signal_pending.set()
                if app.fireCustomEvent(EVENT_ID) is False and signal_pending is not None:
                    signal_pending.clear()
                last_signal = now
        except Exception as error:
            # File-only diagnostics are safe here. Never call app.log/UI from a worker.
            try:
                _status("error", "Watcher error: " + str(error))
            except Exception:
                pass


def run(context):
    import adsk.core

    if STATE.get("thread") is not None and STATE["thread"].is_alive():
        return
    app = adsk.core.Application.get()
    root = Path(__file__).resolve().parents[3]
    queue = queue_root()
    for folder in ("requests", "results", "probe"):
        (queue / folder).mkdir(parents=True, exist_ok=True)
    STATE.clear()
    STATE.update(app=app, repo=root, queue=queue, active=None, busy=None, stopped=False,
                 signal_pending=threading.Event(), session_id=str(uuid.uuid4()))

    class TickHandler(adsk.core.CustomEventHandler):
        def notify(self, args):
            STATE["signal_pending"].clear()
            try:
                _tick()
            except Exception as error:
                _status("error", "Validation bridge error: " + str(error))

    event = app.registerCustomEvent(EVENT_ID)
    if event is None:
        raise RuntimeError("Could not register the Partelier validation event.")
    handler = TickHandler()
    if not event.add(handler):
        app.unregisterCustomEvent(EVENT_ID)
        raise RuntimeError("Could not retain the Partelier validation handler.")
    stop_event = threading.Event()
    thread = threading.Thread(target=_watch, args=(stop_event, app),
                              name="PartelierValidationFiles", daemon=True)
    STATE.update(event=event, handler=handler, stop_event=stop_event, thread=thread)
    _status("ready", "Waiting for a validation request.")
    thread.start()
    app.log("Partelier validation bridge ready: " + str(queue))


def stop(context):
    if not STATE:
        return
    STATE["stopped"] = True
    active = STATE.get("active")
    if active is not None:
        active["cancel_event"].set()
    STATE["stop_event"].set()
    STATE["thread"].join(timeout=2)
    # Reject current-session waiting jobs. A racing submit keeps its old session
    # token and will also be rejected by the next Run rather than executed.
    for path in (STATE["queue"] / "requests").glob("*.json"):
        try:
            request_id = canonical_request_id(path.stem)
            if active is not None and request_id == active["request_id"]:
                continue
            request = validate_request(read_json(path), request_id)
            if request["session_id"] == STATE["session_id"]:
                _write_result(request_id, "cancelled", "Bridge stopped before this validation started.",
                              scenario=request["scenario"])
        except (ValueError, OSError, UnicodeError):
            continue
    try:
        STATE["event"].remove(STATE["handler"])
    finally:
        STATE["app"].unregisterCustomEvent(EVENT_ID)
        STATE.pop("handler", None)
    detail = "The development validation bridge is stopped."
    if active is not None:
        detail += " Probe cancellation requested; waiting for owned-command cleanup."
        try:
            active["module"].cancel()
        except Exception as error:
            detail += " Cleanup error: " + str(error)
    _status("stopped", detail, active["request_id"] if STATE.get("active") is not None else None)
