"""Read-only native check of temporary tapered hinge geometry.

Run from Fusion Scripts and Add-Ins. No documents, features, attributes, or
settings are created or changed. Results are written to output/native/.
"""

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

import adsk.core
import adsk.fusion


def _load_modules(root):
    name = "_partelier_taper_probe"
    package = root / "Partelier" / "partelier"
    spec = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return tuple(importlib.import_module(name + ".tools.hinge." + suffix)
                 for suffix in ("fusion", "planner", "settings", "support"))


def _snapshot(design):
    root = design.rootComponent
    return {"body_count": root.bRepBodies.count,
            "timeline_count": design.timeline.count,
            "timeline_marker": design.timeline.markerPosition,
            "bodies": [{"name": body.name, "volume_cm3": body.volume,
                        "faces": body.faces.count, "edges": body.edges.count}
                       for body in root.bRepBodies]}


def run(context):
    app = adsk.core.Application.get()
    root = Path(__file__).resolve().parents[3]
    output = root / "output" / "native" / "tangent-support-probe.json"
    report = {"fusion_version": app.version, "python_version": sys.version,
              "cases": [], "success": False}
    design = adsk.fusion.Design.cast(app.activeProduct)
    before = _snapshot(design) if design is not None else None
    report["before"] = before
    report["active_recipes"] = []
    if design is not None:
        for body in design.rootComponent.bRepBodies:
            attribute = body.attributes.itemByName("sktech_partelier_hinge_8c319ce2", "recipe")
            if attribute is not None:
                report["active_recipes"].append({"body": body.name, "recipe": json.loads(attribute.value)})
    try:
        adapter, planner, settings_module, support_module = _load_modules(root)
        manager = adsk.fusion.TemporaryBRepManager.get()
        frames = (
            adapter.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
            adapter.HingeFrame((17, -9, 31), (0, 0, -1), (1, 0, 0), (0, -1, 0)),
        )
        cases = [(mode, housing, finish, index, 5, "rectangular")
                 for mode in ("attached", "separate") for housing in ("round", "square")
                 for finish in ("none", "chamfer", "fillet") for index in (0, 1)]
        cases += [(mode, "round", "chamfer", 0, count, "rectangular")
                  for mode in ("attached", "separate") for count in (3, 11)]
        cases += [("separate", housing, finish, 0, 5, "rounded")
                  for housing in ("round", "square") for finish in ("none", "chamfer")]
        for mode, housing, finish, frame_index, count, leaf_profile in cases:
            started = time.perf_counter()
            item = {"mode": mode, "housing": housing, "finish": finish,
                    "frame_index": frame_index, "knuckle_count": count,
                    "leaf_profile": leaf_profile, "success": False}
            try:
                frame = frames[frame_index]
                settings = settings_module.HingeSettings(
                    output_mode=mode, knuckle_profile=housing, web_profile="tangent",
                    rotation_clearance_mm=.3, knuckle_count=count,
                    leaf_profile=leaf_profile, screw_holes=mode == "separate",
                    chamfer_edges=finish == "chamfer", fillet_edges=finish == "fillet",
                    fillet_radius_mm=.4 if housing == "square" else .6)
                plan = planner.build_hinge_plan(settings)
                sources = {}
                if mode == "attached":
                    for owner, low, high in (("A", -25, -.15), ("B", .15, 25)):
                        sources[owner] = adapter._box(manager, frame,
                            planner.WebBounds(owner, low, high, -25, 25, -4, 0))
                else:
                    for plate in plan.plates:
                        sources[plate.owner] = (adapter.rounded_box(manager, frame, plate,
                            settings.fillet_radius_mm) if settings.fillet_edges else
                            adapter._leaf_plate(manager, frame, plate))
                        if settings.chamfer_edges:
                            adapter._finish_leaf_plate(manager, frame, sources[plate.owner],
                                                       plate, settings.chamfer_size_mm)
                before_volumes = {role: body.volume for role, body in sources.items()}
                markers = adapter.cut_rotation_relief(manager, frame, sources, settings)
                item["relief_removed_mm3"] = {role: (before_volumes[role] - body.volume) * 1000
                                               for role, body in sources.items()}
                if mode == "attached" and not all(value > 0 for value in item["relief_removed_mm3"].values()):
                    raise RuntimeError("Default attached sources did not receive both movement recesses.")
                item["relief_marker_count"] = len(markers)
                knuckles = []
                for knuckle, web in zip(plan.knuckles, plan.webs):
                    attachment = adapter._attachment_body(manager, frame, web, settings)
                    adapter._positive_attachment(manager, attachment, sources[web.owner])
                    body = adapter._knuckle_body(manager, frame, plan, knuckle, attachment)
                    adapter._boolean(manager, sources[web.owner], body,
                                     adsk.fusion.BooleanTypes.UnionBooleanType,
                                     "A tapered knuckle did not join its temporary source/leaf.")
                    knuckles.append(body)
                if mode == "separate":
                    plates = {plate.owner: plate for plate in plan.plates}
                    for hole in plan.mounting_holes:
                        plate = plates[hole.owner]
                        adapter._drill_leaf(manager, frame, sources[hole.owner], plate, hole,
                                           settings.chamfer_size_mm if settings.chamfer_edges else 0)
                        if settings.fillet_edges:
                            for position, inward in ((plate.z_min_mm, 1), (plate.z_max_mm, -1)):
                                adapter.round_bore_entry(manager, frame, sources[hole.owner],
                                    hole.diameter_mm / 2, position, inward, 0, settings.fillet_radius_mm,
                                    axis="z", x=hole.x_mm, y=hole.y_mm)
                adapter._require_separate(manager, sources["A"], sources["B"], "Temporary hinge halves")
                pin = adapter._cylinder(manager, frame, plan.pin_start_mm, plan.pin_end_mm,
                                        settings.pin_diameter_mm / 2, plan.barrel_radius_mm)
                for owner in ("A", "B"):
                    adapter._require_separate(manager, sources[owner], pin, "Temporary hinge half and pin")
                for first, second in zip(knuckles, knuckles[1:]):
                    adapter._require_separate(manager, first, second, "Adjacent temporary knuckles")
                tested_angles = []
                for degrees in (0, 30, 60, 90, 120, 150, 180):
                    moving = manager.copy(sources["B"])
                    transform = adsk.core.Matrix3D.create()
                    if not transform.setToRotation(-degrees * 3.141592653589793 / 180,
                            adsk.core.Vector3D.create(*frame.y_axis),
                            adapter._point(frame, 0, 0, plan.barrel_radius_mm)):
                        raise RuntimeError("Could not construct the temporary hinge rotation.")
                    if not manager.transform(moving, transform):
                        raise RuntimeError("Could not rotate the temporary hinge half.")
                    adapter._require_separate(manager, sources["A"], moving,
                                              "Temporary hinge at " + str(degrees) + " degrees")
                    tested_angles.append(degrees)
                item["tested_opening_angles_deg"] = tested_angles
                item["success"] = True
            except Exception:
                item["error"] = traceback.format_exc()
            item["elapsed_ms"] = (time.perf_counter() - started) * 1000
            report["cases"].append(item)
        if not all(item["success"] for item in report["cases"]):
            raise RuntimeError("One or more temporary hinge variants failed; see per-case errors.")
        report["after"] = _snapshot(design) if design is not None else None
        if report["after"] != before:
            raise RuntimeError("The current model changed during the read-only probe.")
        report["success"] = True
    except Exception:
        report["error"] = traceback.format_exc()
        report["after"] = _snapshot(design) if design is not None else None
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        for name in tuple(sys.modules):
            if name == "_partelier_taper_probe" or name.startswith("_partelier_taper_probe."):
                del sys.modules[name]
    app.log("Partelier temporary taper probe: " + str(report["success"]) + " -> " + str(output))
    app.userInterface.messageBox(
        ("Temporary tapered hinge checks passed. The current model was unchanged."
         if report["success"] else "Temporary tapered hinge check failed. See the local JSON report.")
        + "\n\n" + str(output), "Partelier taper check")
