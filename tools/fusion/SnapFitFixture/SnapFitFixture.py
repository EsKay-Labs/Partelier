"""Create the disposable two-body snap-fit fixture in a new Fusion document.

Run this folder as a standalone script from Fusion's Scripts and Add-Ins.
It has no dependency on the Partelier add-in and never saves a document.
"""

import math
import traceback

import adsk.core
import adsk.fusion


MM_TO_CM = 0.1
FIXTURE_BOUNDS_MM = (
    ("Snap-fit fixture A", (-3.0, -30.0, -24.0), (0.0, 30.0, 0.0)),
    ("Snap-fit fixture B", (-3.0, -30.0, 0.0), (0.0, 30.0, 24.0)),
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


def _check_body(body, minimum_cm, maximum_cm):
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
    if not math.isclose(body.volume, 4.32, rel_tol=1e-7, abs_tol=1e-8):
        raise RuntimeError("The fixture body does not have the expected 4320 mm^3 volume.")


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
        root = design.rootComponent
        root.name = "Partelier snap-fit fixture"
        manager = adsk.fusion.TemporaryBRepManager.get()
        base_feature = root.features.baseFeatures.add()
        base_feature.name = "Two-body snap-fit fixture"
        if not base_feature.startEdit():
            raise RuntimeError("Fusion could not enter the fixture base feature.")
        editing = True
        converted_bounds = []
        for name, minimum_mm, maximum_mm in FIXTURE_BOUNDS_MM:
            minimum_cm = tuple(value * MM_TO_CM for value in minimum_mm)
            maximum_cm = tuple(value * MM_TO_CM for value in maximum_mm)
            temporary = _temporary_box(manager, minimum_cm, maximum_cm)
            source = root.bRepBodies.add(temporary, base_feature)
            if source is None:
                raise RuntimeError("Fusion could not persist the fixture body.")
            source.name = name
            converted_bounds.append((name, minimum_cm, maximum_cm))
        if not base_feature.finishEdit():
            raise RuntimeError("Fusion could not finish the fixture base feature.")
        editing = False

        # BaseFeature source handles differ from the result bodies. Autodesk
        # documents index correspondence while immediately after this feature.
        results = base_feature.bodies
        if results.count != len(converted_bounds):
            raise RuntimeError("Fusion did not produce both fixture result bodies.")
        for index, (name, minimum_cm, maximum_cm) in enumerate(converted_bounds):
            body = results.item(index)
            _check_body(body, minimum_cm, maximum_cm)
            body.name = name
        app.activeViewport.fit()
        ui.messageBox(
            "A new, unsaved snap-fit fixture is ready.\n\n"
            "Open Partelier > Snap-fit and select:\n"
            "1. The broad exterior X=0 wall of Snap-fit fixture A (lower).\n"
            "2. The broad exterior X=0 wall of Snap-fit fixture B (upper).\n"
            "3. Their shared straight edge at X=0, Z=0.\n\n"
            "Use the default dimensions, or try Count=3 in Advanced settings.\n"
            "Create integrates the clasp and recess into these same two bodies.\n"
            "The two parts are intended to be printed separately.\n\n"
            "This script creates reference geometry only; it does not validate the tool.",
            "Partelier snap-fit fixture",
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
        ui.messageBox("Snap-fit fixture creation failed.\n\n" + details + suffix, "Partelier snap-fit fixture")
