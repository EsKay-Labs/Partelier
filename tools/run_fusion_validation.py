"""Submit/poll the development Fusion validation bridge; standard library only."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid


def bridge_module():
    path = Path(__file__).resolve().parent / "fusion" / "PartelierValidationBridge" / "PartelierValidationBridge.py"
    spec = importlib.util.spec_from_file_location("_partelier_validation_queue", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submit(bridge, scenario):
    status = bridge.read_json(bridge.queue_root() / "status.json", max_bytes=16384)
    if (not isinstance(status, dict) or status.get("version") != bridge.PROTOCOL_VERSION
            or status.get("state") not in {"ready", "running", "blocked"}
            or not isinstance(status.get("updated_at"), (int, float))
            or not 0 <= time.time() - status["updated_at"] <= 20):
        raise ValueError("Load/run the current development validation bridge before submitting.")
    if scenario != bridge.SCENARIO and scenario not in status.get("scenarios", ()):
        raise ValueError("Reload the development validation bridge to enable the " + scenario + " scenario.")
    session_id = bridge.canonical_request_id(status.get("session_id"))
    request_id = str(uuid.uuid4())
    request = {"version": bridge.PROTOCOL_VERSION, "request_id": request_id,
               "scenario": scenario, "submitted_at": time.time(), "session_id": session_id}
    bridge.validate_request(request, request_id)
    bridge.atomic_json(bridge.queue_root() / "requests" / (request_id + ".json"), request)
    return request_id


def poll(bridge, request_id, timeout, expected_scenario=None):
    bridge.canonical_request_id(request_id)
    if expected_scenario is not None and expected_scenario not in bridge.SCENARIOS:
        raise ValueError("Unsupported validation scenario.")
    queued_path = bridge.queue_root() / "requests" / (request_id + ".json")
    if expected_scenario is None and queued_path.exists():
        request = bridge.validate_request(bridge.read_json(queued_path), request_id)
        expected_scenario = request["scenario"]
    deadline = time.monotonic() + timeout
    result_path = bridge.queue_root() / "results" / (request_id + ".json")
    while True:
        if result_path.exists():
            result = bridge.read_json(result_path, max_bytes=2 * 1024 * 1024)
            if (not isinstance(result, dict) or result.get("request_id") != request_id
                    or type(result.get("version")) is not int
                    or result.get("version") != bridge.PROTOCOL_VERSION
                    or not isinstance(result.get("scenario"), str)
                    or result["scenario"] not in bridge.SCENARIOS
                    or (expected_scenario is not None and result["scenario"] != expected_scenario)
                    or result.get("state") not in {"complete", "blocked", "error", "cancelled"}
                    or type(result.get("success")) is not bool
                    or (result["success"] and result["state"] != "complete")):
                raise ValueError("The bridge returned a mismatched result.")
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            status_path = bridge.queue_root() / "status.json"
            try:
                status = bridge.read_json(status_path, max_bytes=16384)
            except (OSError, ValueError, UnicodeError):
                status = {"state": "unavailable"}
            return {"version": bridge.PROTOCOL_VERSION, "request_id": request_id,
                    "scenario": expected_scenario or bridge.SCENARIO, "state": "timeout", "success": False,
                    "detail": "No result before the CLI timeout; the queued request was not cancelled.",
                    "bridge_status": status}
        time.sleep(min(0.25, remaining))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    submit_parser = commands.add_parser("submit", help="Queue the allowlisted probe and wait for its result.")
    submit_parser.add_argument("--scenario", choices=sorted(bridge_module().SCENARIOS), default="joined_finish")
    submit_parser.add_argument("--timeout", type=float, default=240)
    submit_parser.add_argument("--no-wait", action="store_true", help="Return the request UUID immediately.")
    poll_parser = commands.add_parser("poll", help="Wait for one previously submitted request UUID.")
    poll_parser.add_argument("request_id")
    poll_parser.add_argument("--timeout", type=float, default=240)
    commands.add_parser("status", help="Read the bridge heartbeat without submitting work.")
    args = parser.parse_args(argv)
    if hasattr(args, "timeout") and not 0 <= args.timeout <= 3600:
        parser.error("--timeout must be finite and between 0 and 3600 seconds.")
    bridge = bridge_module()
    try:
        if args.command == "status":
            try:
                value = bridge.read_json(bridge.queue_root() / "status.json", max_bytes=16384)
            except FileNotFoundError:
                value = {"state": "unavailable", "detail": "Load/run the development PartelierValidationBridge add-in once in Fusion."}
            if isinstance(value, dict) and isinstance(value.get("updated_at"), (int, float)):
                value["heartbeat_age_seconds"] = max(0, time.time() - value["updated_at"])
                if value["heartbeat_age_seconds"] > 20:
                    value["last_state"] = value.get("state")
                    value["state"] = "unavailable"
                    value["detail"] = "Bridge heartbeat is stale; load/run the development add-in in Fusion."
            print(json.dumps(value, indent=2, sort_keys=True))
            return 0 if value.get("state") in {"ready", "running", "blocked"} else 1
        request_id = submit(bridge, args.scenario) if args.command == "submit" else args.request_id
        if args.command == "submit" and args.no_wait:
            print(json.dumps({"request_id": request_id, "state": "queued"}, indent=2))
            return 0
        result = poll(bridge, request_id, args.timeout,
                      expected_scenario=args.scenario if args.command == "submit" else None)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("success") is True else 2 if result.get("state") == "timeout" else 1
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({"state": "error", "success": False, "detail": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
