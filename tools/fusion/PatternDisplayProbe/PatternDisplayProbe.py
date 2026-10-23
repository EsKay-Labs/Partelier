"""Read-only disabled diagnostic; native display experiments are suspended."""

import json
from pathlib import Path


def run(context):
    report = {
        "scenario": "pattern_display", "success": False, "disabled": True,
        "reason": "Native display experiments disabled after two Fusion heap-corruption crashes.",
        "last_native_checkpoint": "mesh_manager",
        "model_accessed": False,
    }
    if context.get("report_path"):
        Path(context["report_path"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
    callback = context.get("on_complete")
    if callback is not None:
        callback(report)
