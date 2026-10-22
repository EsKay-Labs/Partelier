"""Create the disposable touching-split hinge fixture in a new Fusion document.

Run this folder as a standalone script from Fusion's Scripts and Add-Ins.
It has no dependency on the Partelier add-in and never saves a document.
"""

import math
import traceback

import adsk.core
import adsk.fusion


MM_TO_CM = 0.1
FIXTURE_BOUNDS_MM = (
    ("Split fixture A", (-25.0, -20.0, -24.0), (25.0, 0.0, 0.0), 24000.0),
    ("Split fixture B", (-25.0, -20.0, 0.0), (25.0, 0.0, 6.0), 6000.0),
)


def _temporary_box(manager, minimum_cm, maximum_cm):
    center = adsk.core.Point3D.create(*(
        (minimum + maximum) / 2.0
        for minimum, maximum in zip(minimum_cm, maximum_cm)
    ))
    size = tuple(maximum - minimum for minimum, maximum in zip(minimum_cm, maximum_cm))
    bounds = adsk.core.OrientedBoundingBox3D.create(
        center,
        adsk.core.Vector3D.create(1.0, 0.0, 0.0),
        adsk.core.Vector3D.create(0.0, 1.0, 0.0),
        *size,
    )
    if bounds is None:
        raise RuntimeError("Fusion could not construct the fixture box bounds.")
    body = manager.createBox(bounds)
    if body is None or not body.isSolid:
        raise RuntimeError("Fusion could not construct a solid fixture box.")
    return body


def _check_body(body, minimum_cm, maximum_cm, expected_volume_mm3):
    """Check actual host geometry before offering it for manual validation."""
    if not body.isSolid or body.lumps.count != 1:
        raise RuntimeError("The fixture body is not a single solid.")
    bounds = body.boundingBox
    for actual, expected in zip(
        (bounds.minPoint.x, bounds.minPoint.y, bounds.minPoint.z,
         bounds.maxPoint.x, bounds.maxPoint.y, bounds.maxPoint.z),
        minimum_cm + maximum_cm,
    ):
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-7):
            raise RuntimeError("The fixture body does not have the expected bounds.")
    expected_volume_cm3 = expected_volume_mm3 * MM_TO_CM ** 3
    if not math.isclose(body.volume, expected_volume_cm3, rel_tol=1e-7, abs_tol=1e-8):
        raise RuntimeError(
            f"The fixture body does not have the expected {expected_volume_mm3:g} mm^3 volume.")


def run(context):
    """Create only a new parametric document; leave existing models untouched."""
    app = adsk.core.Application.get()
    ui = app.userInterface
    original_document = app.activeDocument
    fixture_document = None
    base_feature = None
    editing = False
    try:
        fixture_document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        if fixture_document is None:
            raise RuntimeError("Fusion did not create the new fixture document.")
        design = adsk.fusion.Design.cast(
            fixture_document.products.itemByProductType("DesignProductType")
        )
        if design is None:
            raise RuntimeError("The new document does not contain a Fusion Design.")
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.designIntent = adsk.fusion.DesignIntentTypes.PartDesignIntentType
        root = design.rootComponent
        root.name = "Partelier touching-split hinge fixture"
        manager = adsk.fusion.TemporaryBRepManager.get()
        if manager is None:
            raise RuntimeError("Fusion's temporary geometry manager is unavailable.")
        base_feature = root.features.baseFeatures.add()
        if base_feature is None:
            raise RuntimeError("Fusion could not create the fixture base feature.")
        base_feature.name = "Touching split-body hinge fixture"
        if not base_feature.startEdit():
            raise RuntimeError("Fusion could not enter the fixture base feature.")
        editing = True
        converted_bounds = []
        for name, minimum_mm, maximum_mm, expected_volume_mm3 in FIXTURE_BOUNDS_MM:
            minimum_cm = tuple(value * MM_TO_CM for value in minimum_mm)
            maximum_cm = tuple(value * MM_TO_CM for value in maximum_mm)
            temporary = _temporary_box(manager, minimum_cm, maximum_cm)
            source = root.bRepBodies.add(temporary, base_feature)
            if source is None:
                raise RuntimeError("Fusion could not persist the fixture body.")
            source.name = name
            converted_bounds.append((name, minimum_cm, maximum_cm, expected_volume_mm3))
        if not base_feature.finishEdit():
            raise RuntimeError("Fusion could not finish the fixture base feature.")
        editing = False

        # BaseFeature source handles differ from the result bodies. Autodesk
        # documents index correspondence while immediately after this feature.
        results = base_feature.bodies
        if results.count != len(converted_bounds):
            raise RuntimeError("Fusion did not produce both fixture result bodies.")
        for index, (name, minimum_cm, maximum_cm, expected_volume_mm3) in enumerate(converted_bounds):
            body = results.item(index)
            _check_body(body, minimum_cm, maximum_cm, expected_volume_mm3)
            body.name = name
        app.activeViewport.fit()
        ui.messageBox(
            "A new, unsaved touching-split fixture is ready.\n\n"
            "The two solids touch across the full 50 x 20 mm rectangle at Z=0.\n"
            "Open the Partelier pin-hinge tool and select:\n"
            "1. The FRONT exterior face (Y=0) of Split fixture A.\n"
            "2. The FRONT exterior face (Y=0) of Split fixture B.\n"
            "   Both faces point outward in +Y; do not select the internal split faces.\n"
            "3. Their shared straight edge along X, at Y=0 and Z=0.\n"
            "   Either coincident visible edge may be picked.\n\n"
            "The shared edge should automatically activate Split seam. Use:\n"
            "Seam clearance: 0.3 mm; hinge length: 40 mm; leaf reach: 5.5 mm.\n"
            "Keep the other defaults. Axis offset is ignored in split mode.\n"
            "The expected axis is Y=4 mm, Z=0, parallel to X.\n\n"
            "At the original contact, the copied seam faces should be Z=-0.15 mm\n"
            "and Z=+0.15 mm over 50 x 20 mm. Originals must remain unchanged.\n"
            "Original volumes: A = 24000 mm^3; B = 6000 mm^3.\n\n"
            "Multi-hinge check: count 3, length per hinge 10 mm, margins 5 mm.\n"
            "Expected centers along the edge: -15, 0, +15 mm; barrel gaps 5 mm.\n"
            "Expected copied result: two halves and three separate pins.\n"
            "Part intent must stay unchanged; no new component is required.\n\n"
            "This script creates reference geometry only. Native hinge outcomes remain unvalidated.",
            "Partelier touching-split fixture",
        )
    except Exception:
        details = traceback.format_exc()
        cleanup_notes = []
        if editing and base_feature is not None:
            try:
                if not base_feature.finishEdit():
                    cleanup_notes.append("Fusion could not finish the fixture base feature.")
            except Exception:
                cleanup_notes.append("Fusion could not leave fixture base-feature edit mode.")
        if fixture_document is not None:
            try:
                if fixture_document.isValid and not fixture_document.isSaved:
                    if not fixture_document.close(False):
                        cleanup_notes.append("Fusion could not close the new unsaved fixture document.")
            except Exception:
                cleanup_notes.append("The new fixture document may still be open.")
        if original_document is not None:
            try:
                if original_document.isValid:
                    original_document.activate()
            except Exception:
                cleanup_notes.append("Select the previously active document manually.")
        suffix = "\n\n" + "\n".join(cleanup_notes) if cleanup_notes else ""
        ui.messageBox("Touching-split fixture creation failed.\n\n" + details + suffix, "Partelier touching-split fixture")
