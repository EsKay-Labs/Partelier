"""Snap-fit adapter safety and native-store boundary checks, without Fusion.

These fakes exercise selection, freshness, explicit boolean outcomes, and
transaction delegation. They do not establish native solid validity or fit.
"""

from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit import fusion
from Partelier.partelier.tools.snap_fit.planner import BoxBounds, build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings
from Partelier.partelier.tools.solid_pair import SolidPairRecord


IDENTITY = "2f066aa6-e77a-450b-b8f5-ef5418330e7f"


class Entity:
    def __init__(self, **values):
        self.__dict__.update(values)


class Attributes:
    def __init__(self):
        self.values = {}
        self.writes = []

    def itemByName(self, group, name):
        return self.values.get((group, name))

    def add(self, group, name, value):
        self.writes.append((group, name, value))
        tag = SimpleNamespace(value=value)
        self.values[group, name] = tag
        return tag


def xyz(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


def solid(token="temporary", root=None, volume=7.2, temporary=False):
    return Entity(kind="body", isValid=True, isSolid=True, volume=volume,
                  lumps=SimpleNamespace(count=1), isTemporary=temporary,
                  isLightBulbOn=True, assemblyContext=None, parentComponent=root,
                  entityToken=token, attributes=Attributes(), name=token,
                  appearance=token + " appearance", material=SimpleNamespace(appearance=None))


def fixture():
    root = Entity(isValid=True, material=SimpleNamespace(appearance="default appearance"))
    a, b = solid("body a", root), solid("body b", root)
    face_a = Entity(kind="face", isValid=True, body=a, assemblyContext=None,
                    entityToken="face a", pointOnFace=xyz(0, 0, -1), area=14.4,
                    normal=(1, 0, 0))
    face_b = Entity(kind="face", isValid=True, body=b, assemblyContext=None,
                    entityToken="face b", pointOnFace=xyz(0, 0, 1), area=14.4,
                    normal=(1, 0, 0))
    edge = Entity(kind="edge", isValid=True, body=a, entityToken="axis edge")
    entities = {entity.entityToken: entity for entity in (a, b, face_a, face_b, edge)}
    design = Entity(isValid=True, designType=1, rootComponent=root, activeComponent=root,
                    timeline=SimpleNamespace(count=10, markerPosition=10),
                    findEntityByToken=lambda token: [entities[token]] if token in entities else [])
    return design, face_a, face_b, edge


def api(manager=None):
    def cast(kind):
        return SimpleNamespace(cast=lambda value: value if getattr(value, "kind", None) == kind else None)
    native = SimpleNamespace(DesignTypes=SimpleNamespace(ParametricDesignType=1),
                             BRepFace=cast("face"), BRepEdge=cast("edge"),
                             BooleanTypes=SimpleNamespace(UnionBooleanType=1,
                                                          DifferenceBooleanType=2,
                                                          IntersectionBooleanType=3),
                             TemporaryBRepManager=SimpleNamespace(get=lambda: manager))
    return None, native


@contextmanager
def selection_api(manager=None, endpoints=((0, -3, 0), (0, 3, 0))):
    with patch.object(fusion, "_api", return_value=api(manager)), patch.object(
            fusion.hinge, "_canonical_axis_edge", side_effect=lambda a, b, edge: edge), patch.object(
            fusion.hinge, "_straight_endpoints", return_value=endpoints), patch.object(
            fusion.hinge, "_plane_normal", side_effect=lambda face: face.normal), patch.object(
            fusion.hinge, "_body_signature", side_effect=lambda body: body.entityToken + " signature"):
        yield


def prepared_fixture():
    design, a, b, edge = fixture()
    with selection_api():
        values = fusion._selection(design, a, b, edge)
    settings = SnapFitSettings(chamfer_edges=False, print_support=False)
    finals = (("A", solid("final a", temporary=True)), ("B", solid("final b", temporary=True)))
    prepared = fusion.PreparedSnapFit(design, a, b, edge, settings,
                                     build_snap_fit_plan(settings, 60), values[3], finals,
                                     values[4], {}, fusion._source_tokens(a, b, edge))
    return design, prepared


def saved_fixture():
    design, prepared = prepared_fixture()
    anchor = Entity(isValid=True, attributes=Attributes())
    record = SolidPairRecord(anchor, IDENTITY, (prepared.face_a.body, prepared.face_b.body), {})
    recipe = {"version": fusion.RECIPE_VERSION, "tool": "snap_fit", "feature_id": IDENTITY,
              "settings": prepared.settings.to_dict(), "sources": dict(prepared.source_tokens)}
    anchor.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, json.dumps(recipe))
    target = fusion.EditTarget(anchor, record, prepared.settings, recipe, prepared.face_a,
                              prepared.face_b, prepared.axis_edge, IDENTITY)
    prepared = replace(prepared, history_anchor=anchor, record=record, saved_recipe=recipe)
    return design, prepared, target


class SnapFitSelectionTests(unittest.TestCase):
    def test_frame_is_right_handed_and_points_from_hook_body_toward_receiver(self):
        design, a, b, edge = fixture()
        for endpoints in (((0, -3, 0), (0, 3, 0)), ((0, 3, 0), (0, -3, 0))):
            with self.subTest(endpoints=endpoints), selection_api(endpoints=endpoints):
                values = fusion._selection(design, a, b, edge)
            frame = values[3]
            self.assertEqual(frame.origin_mm, (0, 0, 0))
            self.assertEqual(frame.x_axis, (1, 0, 0))
            self.assertEqual(frame.z_axis, (0, 0, 1))
            self.assertEqual(fusion.hinge._cross(frame.x_axis, frame.y_axis), frame.z_axis)
            self.assertEqual(values[5], 60)

    def test_opposite_normals_offset_planes_and_wrong_rim_are_refused(self):
        for mutation, text in ((lambda a, b: setattr(b, "normal", (-1, 0, 0)), "matching outward"),
                               (lambda a, b: setattr(b, "pointOnFace", xyz(.1, 0, 1)), "same plane"),
                               (lambda a, b: setattr(a, "pointOnFace", xyz(0, 0, .5)), "lower hook")):
            design, a, b, edge = fixture()
            mutation(a, b)
            with self.subTest(text=text), selection_api(), self.assertRaisesRegex(ValueError, text):
                fusion._selection(design, a, b, edge)

    def test_same_body_proxy_nonroot_nonsolid_and_temporary_selections_are_refused(self):
        changes = (lambda d, a, b: setattr(b, "body", a.body),
                   lambda d, a, b: setattr(a, "assemblyContext", object()),
                   lambda d, a, b: setattr(a.body, "parentComponent", object()),
                   lambda d, a, b: setattr(a.body, "isSolid", False),
                   lambda d, a, b: setattr(a.body, "isTemporary", True),
                   lambda d, a, b: setattr(a.body, "volume", float("nan")))
        for index, change in enumerate(changes):
            design, a, b, edge = fixture()
            change(design, a, b)
            with self.subTest(index=index), selection_api(), self.assertRaises(ValueError):
                fusion._selection(design, a, b, edge)

    def test_history_and_active_component_guards_apply_before_geometry_reads(self):
        design, a, b, edge = fixture()
        design.timeline.markerPosition = 4
        with selection_api(), self.assertRaisesRegex(ValueError, "marker"):
            fusion._selection(design, a, b, edge)
        with selection_api():
            fusion._selection(design, a, b, edge, historical=True)
        design.activeComponent = object()
        with selection_api(), self.assertRaisesRegex(ValueError, "root component"):
            fusion._selection(design, a, b, edge, historical=True)

    def test_sources_resolve_exactly_one_body_face_and_edge_relationship(self):
        design, prepared = prepared_fixture()
        with patch.object(fusion, "_api", return_value=api()):
            self.assertEqual(fusion._sources(design, prepared.source_tokens),
                             (prepared.face_a, prepared.face_b, prepared.axis_edge))
            with self.assertRaisesRegex(ValueError, "original bodies"):
                fusion._sources(design, prepared.source_tokens,
                                (prepared.face_b.body, prepared.face_a.body))
            broken = dict(prepared.source_tokens, axis_edge="missing")
            with self.assertRaisesRegex(ValueError, "missing or split"):
                fusion._sources(design, broken)


class SnapFitRimGapTests(unittest.TestCase):
    def setUp(self):
        self.design,self.a,self.b,_=fixture()
        self.rim=Entity(assemblyContext=None,body=self.a.body,bounds=((0,-3,0),(0,3,0)))
        self.pick=Entity(assemblyContext=None,body=self.b.body,bounds=((0,3,.03),(0,-3,.03)))
        self.a.edges=SimpleNamespace(count=1,item=lambda index:self.rim)
        self.b.edges=SimpleNamespace(count=1,item=lambda index:self.pick)
        def vertices(zs):
            values=[Entity(geometry=xyz(0,y,z)) for y in (-3,3) for z in zs]
            return SimpleNamespace(count=len(values),item=values.__getitem__)
        self.a.vertices=vertices((-2.4,0))
        self.b.vertices=vertices((.03,2.4))
        self.patches=[patch.object(fusion.hinge,"_canonical_axis_edge",side_effect=fusion.hinge.HingeGeometryError("exact mismatch")),
                      patch.object(fusion.hinge,"_straight_endpoints",side_effect=lambda edge:edge.bounds),
                      patch.object(fusion.hinge,"_plane_normal",side_effect=lambda face:face.normal)]
        for item in self.patches:item.start()
        self.addCleanup(lambda:[item.stop() for item in reversed(self.patches)])

    def test_lid_rim_across_point_three_mm_gap_resolves_to_base_rim(self):
        self.assertIs(fusion._canonical_rim(self.a,self.b,self.pick),self.rim)
        self.pick.bounds=tuple(reversed(self.pick.bounds))
        self.assertIs(fusion._canonical_rim(self.a,self.b,self.pick),self.rim)

    def test_exact_original_boundary_path_is_preserved(self):
        fusion.hinge._canonical_axis_edge.side_effect=None
        fusion.hinge._canonical_axis_edge.return_value=self.rim
        self.assertIs(fusion._canonical_rim(self.a,self.b,self.rim),self.rim)

    def test_partial_shifted_diagonal_and_out_of_plane_rims_are_refused(self):
        for points in (((0,2,.03),(0,-2,.03)),((0,4,.03),(0,-2,.03)),
                       ((0,3,.03),(0,-3,.04)),((.1,3,.03),(.1,-3,.03))):
            self.pick.bounds=points
            with self.subTest(points=points),self.assertRaises(ValueError):
                fusion._canonical_rim(self.a,self.b,self.pick)

    def test_lid_far_edge_cannot_be_used_as_the_seam(self):
        self.pick.bounds=((0,3,2.4),(0,-3,2.4))
        with self.assertRaises(ValueError):fusion._canonical_rim(self.a,self.b,self.pick)

    def test_another_body_or_nonboundary_edge_cannot_choose_a_rim(self):
        self.pick.body=object()
        with self.assertRaises(ValueError):fusion._canonical_rim(self.a,self.b,self.pick)
        self.pick.body=self.b.body
        self.b.edges=SimpleNamespace(count=0)
        with self.assertRaises(ValueError):fusion._canonical_rim(self.a,self.b,self.pick)

    def test_ambiguous_matching_base_boundaries_are_refused(self):
        self.a.edges=SimpleNamespace(count=2,item=lambda index:self.rim)
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            fusion._canonical_rim(self.a,self.b,self.pick)


class SnapFitGeometryBoundaryTests(unittest.TestCase):
    def test_exterior_halfspace_refuses_protrusions_but_allows_internal_lips(self):
        a, b, manager, frame = object(), object(), object(), object()
        valid = (((-3, -30, -24), (0, 30, 0)), ((-3, -30, 0), (0, 30, 24)))
        with patch.object(fusion, "_local_bounds", side_effect=valid):
            fusion._halfspaces(manager, frame, a, b)
        with patch.object(fusion, "_local_bounds", side_effect=(
                ((-3,-30,-24),(0,30,4)),((-3,-30,-4),(0,30,24)))):
            fusion._halfspaces(manager, frame, a, b)
        cases = [(((0, 0, -24), (.1, 30, 0)), valid[1])]
        for bounds in cases:
            with self.subTest(bounds=bounds), patch.object(fusion, "_local_bounds", side_effect=bounds):
                with self.assertRaises(ValueError):
                    fusion._halfspaces(manager, frame, a, b)

    def test_local_bounds_transforms_a_copy_and_never_the_source(self):
        matrix = SimpleNamespace(setWithCoordinateSystem=Mock(return_value=True),
                                 invert=Mock(return_value=True))
        core = SimpleNamespace(Matrix3D=SimpleNamespace(create=lambda: matrix),
                               Point3D=SimpleNamespace(create=lambda *values: values),
                               Vector3D=SimpleNamespace(create=lambda *values: values))
        source = solid()
        detached = solid(temporary=True)
        detached.boundingBox = SimpleNamespace(minPoint=xyz(-.3, -3, -2.4), maxPoint=xyz(0, 3, 0))
        manager = SimpleNamespace(copy=Mock(return_value=detached), transform=Mock(return_value=True))
        frame = fusion.hinge.HingeFrame((10, 20, 30), (0, 1, 0), (-1, 0, 0), (0, 0, 1))
        with patch.object(fusion, "_api", return_value=(core, None)):
            self.assertEqual(fusion._local_bounds(manager, frame, source), ((-3, -30, -24), (0, 30, 0)))
        matrix.setWithCoordinateSystem.assert_called_once_with((1, 2, 3), (0, 1, 0), (-1, 0, 0), (0, 0, 1))
        manager.transform.assert_called_once_with(detached, matrix)
        manager.copy.assert_called_once_with(source)

    def test_exact_coverage_rejects_missing_material_and_boolean_failure(self):
        source, frame = object(), object()
        bounds = BoxBounds(-.5, 0, -4, 4, -4, 0)
        for lost, succeeds in ((0, True), (.001, True), (0, False)):
            check = solid(volume=1)
            def intersect(target, tool, operation):
                target.volume -= lost
                return succeeds
            manager = SimpleNamespace(booleanOperation=Mock(side_effect=intersect))
            with self.subTest(lost=lost, succeeds=succeeds), patch.object(
                    fusion, "_api", return_value=api()), patch.object(fusion.hinge, "_box", return_value=check):
                if lost == 0 and succeeds:
                    fusion._coverage(manager, frame, source, bounds, "coverage failed")
                else:
                    with self.assertRaisesRegex(ValueError, "coverage failed"):
                        fusion._coverage(manager, frame, source, bounds, "coverage failed")

    def test_preparation_requires_remaining_wall_around_blind_receiver(self):
        design, prepared = prepared_fixture()
        manager = SimpleNamespace(copy=Mock(side_effect=lambda source: solid(temporary=True)),
                                  booleanOperation=Mock(return_value=True))
        values = (prepared.face_a, prepared.face_b, prepared.axis_edge, prepared.frame,
                  prepared.source_signature, 60)
        boxes = []
        def make_box(manager, frame, bounds):
            boxes.append(bounds)
            return solid(temporary=True)
        with patch.object(fusion, "_api", return_value=api(manager)), patch.object(
                fusion, "_selection", return_value=values), patch.object(fusion, "_halfspaces"), patch.object(
                fusion, "_coverage") as coverage, patch.object(fusion.hinge, "_box", side_effect=make_box), patch.object(
                fusion, "_prism", return_value=solid(temporary=True)), patch.object(fusion, "_no_positive_overlap"):
            result = fusion.prepare_snap_fit(design, prepared.face_a, prepared.face_b,
                                             prepared.axis_edge, prepared.settings)
        root_check = coverage.call_args_list[0].args[3]
        pocket_check = coverage.call_args_list[1].args[3]
        cutter = prepared.plan.units[0].receiver
        self.assertEqual(root_check.x_max_mm, 0)
        self.assertAlmostEqual(pocket_check.x_min_mm, cutter.x_min_mm - .3)
        self.assertAlmostEqual(pocket_check.y_min_mm, cutter.y_min_mm - .3)
        self.assertAlmostEqual(pocket_check.y_max_mm, cutter.y_max_mm + .3)
        self.assertAlmostEqual(pocket_check.z_min_mm, cutter.z_min_mm - .3)
        self.assertAlmostEqual(pocket_check.z_max_mm, cutter.z_max_mm + .3)
        self.assertEqual(pocket_check.x_max_mm, 0)
        self.assertEqual(tuple(role for role, body in result.result_bodies), ("A", "B"))
        self.assertEqual(boxes, [prepared.plan.units[0].root])
        self.assertFalse(design.rootComponent.__dict__.get("created", False))
        self.assertEqual(prepared.face_a.body.attributes.writes, [])
        self.assertEqual(prepared.face_b.body.attributes.writes, [])

    def test_prepare_failure_cannot_reach_persistence(self):
        design, prepared = prepared_fixture()
        values = (prepared.face_a, prepared.face_b, prepared.axis_edge, prepared.frame,
                  prepared.source_signature, 60)
        manager = SimpleNamespace(copy=Mock(side_effect=lambda source: solid(temporary=True)))
        with patch.object(fusion, "_api", return_value=api(manager)), patch.object(
                fusion, "_selection", return_value=values), patch.object(fusion, "_halfspaces"), patch.object(
                fusion, "_coverage", side_effect=ValueError("missing root")), patch.object(fusion, "STORE") as store:
            with self.assertRaisesRegex(ValueError, "missing root"):
                fusion.prepare_snap_fit(design, prepared.face_a, prepared.face_b, prepared.axis_edge, prepared.settings)
        store.create.assert_not_called()
        store.update.assert_not_called()
        self.assertEqual(prepared.face_a.body.attributes.writes, [])

    def test_clearance_difference_must_succeed_and_preserve_volume(self):
        for after, succeeds in ((1, True), (.99, True), (1, False), (1.01, True), (float("nan"), True)):
            witness = solid(volume=1)
            def difference(*args):
                witness.volume = after
                return succeeds
            manager = SimpleNamespace(copy=lambda source:witness,booleanOperation=difference)
            with self.subTest(after=after,succeeds=succeeds), patch.object(fusion,"_api",return_value=api()):
                if succeeds and after == 1:
                    fusion._no_positive_overlap(manager,object(),object())
                else:
                    with self.assertRaises(ValueError):
                        fusion._no_positive_overlap(manager,object(),object())


class SnapFitFreshnessAndRecipeTests(unittest.TestCase):
    def test_v2_recipe_preserves_fifteen_fields_and_loads_hook_family_without_writes(self):
        design, prepared, target = saved_fixture()
        current = SnapFitSettings(snap_style="tapered", chamfer_edges=True, print_support=True)
        old = dict(target.recipe, version=2,
                   settings={key: value for key, value in current.to_dict().items()
                             if key not in fusion.FAMILY_DEFAULTS})
        raw = json.dumps(old)
        target.anchor.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, raw)
        writes = len(target.anchor.attributes.writes)
        recipe, loaded = fusion._read_recipe(target.anchor, target.record)
        self.assertEqual(recipe, old)
        self.assertEqual(len(recipe["settings"]), 15)
        self.assertEqual(loaded, current)
        self.assertEqual(loaded.snap_family, "hook")
        self.assertEqual(len(target.anchor.attributes.writes), writes)
        for settings in (dict(old["settings"], snap_family="hook"),
                         {key: value for key, value in old["settings"].items() if key != "width_mm"}):
            with self.assertRaisesRegex(ValueError, "fifteen"):
                fusion._parse_recipe(json.dumps(dict(old, settings=settings)), target.record)

    def test_v3_recipe_preserves_each_new_family_and_its_parameters(self):
        design, prepared, target = saved_fixture()
        for family in ("hook", "ball_detent", "torsion", "annular"):
            settings = SnapFitSettings(snap_family=family, chamfer_edges=family != "annular",
                                      ball_radius_mm=2.2, torsion_radius_mm=.85,
                                      annular_bead_height_mm=.6)
            recipe = dict(target.recipe, version=3, settings=settings.to_dict())
            parsed, loaded = fusion._parse_recipe(json.dumps(recipe), target.record)
            self.assertEqual(parsed, recipe)
            self.assertEqual(loaded, settings)
            self.assertEqual(len(loaded.to_dict()), 21)

    def test_legacy_recipe_loads_exact_original_geometry_without_writes(self):
        design, prepared, target = saved_fixture()
        old = dict(target.recipe, version=1,
                   settings={key: value for key, value in target.recipe["settings"].items()
                             if key in fusion.LEGACY_SETTINGS_FIELDS})
        original = json.dumps(old)
        target.anchor.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, original)
        before_writes = len(target.anchor.attributes.writes)
        recipe, settings = fusion._read_recipe(target.anchor, target.record)
        self.assertEqual(recipe, old)
        self.assertEqual(recipe["version"], 1)
        self.assertEqual(len(recipe["settings"]), 11)
        self.assertEqual(settings.snap_style, "standard")
        self.assertFalse(settings.chamfer_edges)
        self.assertFalse(settings.print_support)
        self.assertEqual(len(target.anchor.attributes.writes), before_writes)
        for values in (dict(old["settings"], snap_style="standard"),
                       {key: value for key, value in old["settings"].items() if key != "reach_mm"}):
            with self.assertRaisesRegex(ValueError, "original eleven"):
                fusion._parse_recipe(json.dumps(dict(old, settings=values)), target.record)

    def test_snapshot_drops_generated_solids_and_validation_reads_only_sources(self):
        design, prepared = prepared_fixture()
        sources = fusion.capture_preview_sources(prepared)
        self.assertFalse(hasattr(sources, "result_bodies"))
        self.assertFalse(hasattr(sources, "plan"))
        with selection_api(), patch.object(fusion, "prepare_snap_fit") as prepare:
            fusion.validate_preview_sources(design, sources)
        prepare.assert_not_called()

    def test_changed_source_or_active_design_invalidates_candidate(self):
        design, prepared = prepared_fixture()
        with self.assertRaisesRegex(ValueError, "active design changed"):
            fusion.validate_preview_sources(object(), prepared)
        with selection_api(), patch.object(fusion.hinge, "_body_signature", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "source geometry changed"):
                fusion.validate_preview_sources(design, prepared)

    def test_edit_preparation_restores_history_on_failure_and_uses_original_sources(self):
        design, prepared, target = saved_fixture()
        visits = []
        @contextmanager
        def scope(design, record):
            self.assertIs(record, target.record)
            previous = design.timeline.markerPosition
            design.timeline.markerPosition = 2
            visits.append("enter")
            try:
                yield record.targets
            finally:
                design.timeline.markerPosition = previous
                visits.append("leave")
        store = SimpleNamespace(input_scope=scope)
        with patch.object(fusion, "STORE", store), patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "prepare_snap_fit", side_effect=ValueError("geometry refused")) as prepare:
            with self.assertRaisesRegex(ValueError, "geometry refused"):
                fusion.prepare_edit_snap_fit(design, target, SnapFitSettings(reach_mm=18))
        self.assertEqual(visits, ["enter", "leave"])
        self.assertEqual(design.timeline.markerPosition, 10)
        self.assertTrue(prepare.call_args.kwargs["_historical"])
        self.assertEqual(prepare.call_args.args[1:4], (target.face_a, target.face_b, target.axis_edge))

    def test_edit_freshness_uses_history_not_stale_end_of_history_faces(self):
        design, prepared, target = saved_fixture()
        @contextmanager
        def scope(design, record):
            design.timeline.markerPosition = 2
            try:
                yield record.targets
            finally:
                design.timeline.markerPosition = 10
        values = (target.face_a, target.face_b, object(), prepared.frame, prepared.source_signature, 60)
        with patch.object(fusion, "STORE", SimpleNamespace(input_scope=scope)), patch.object(
                fusion, "_api", return_value=api()), patch.object(fusion, "_selection", return_value=values) as select:
            fusion.validate_preview_sources(design, prepared)
        self.assertTrue(select.call_args.kwargs["historical"])
        self.assertEqual(design.timeline.markerPosition, 10)

    def test_edit_refuses_recipe_changed_after_selection(self):
        design, prepared, target = saved_fixture()
        updated = dict(target.recipe, settings=SnapFitSettings(width_mm=9).to_dict())
        target.anchor.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, json.dumps(updated))
        with patch.object(fusion, "STORE") as store:
            with self.assertRaisesRegex(ValueError, "settings changed"):
                fusion.prepare_edit_snap_fit(design, target, prepared.settings)
            with self.assertRaisesRegex(ValueError, "settings changed"):
                fusion.validate_preview_sources(design, prepared)
        store.input_scope.assert_not_called()

    def test_recipe_is_strict_and_independent_of_hinge_attributes(self):
        design, prepared, target = saved_fixture()
        raw = json.dumps(target.recipe)
        parsed, settings = fusion._parse_recipe(raw, target.record)
        self.assertEqual(parsed, target.recipe)
        self.assertEqual(settings, target.settings)
        bad = [dict(target.recipe, version=True), dict(target.recipe, tool="pin_hinge"),
               dict(target.recipe, feature_id="another"), dict(target.recipe, unsupported=True),
               dict(target.recipe, settings={}), dict(target.recipe, sources={})]
        duplicate = dict(target.recipe["sources"])
        duplicate["axis_edge"] = duplicate["face_a"]
        bad.append(dict(target.recipe, sources=duplicate))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                fusion._parse_recipe(json.dumps(value), target.record)
        for value in (None, "[1]", "invalid", " " * 131073):
            with self.subTest(value=repr(value)[:25]), self.assertRaises(ValueError):
                fusion._parse_recipe(value, target.record)
        self.assertNotEqual(fusion.ATTRIBUTE_GROUP, fusion.hinge.ATTRIBUTE_GROUP)


class SnapFitPersistenceBoundaryTests(unittest.TestCase):
    def test_create_delegates_exact_existing_targets_and_detached_finals_then_saves_recipe(self):
        design, prepared = prepared_fixture()
        anchor = Entity(attributes=Attributes())
        record = SolidPairRecord(anchor, IDENTITY, (prepared.face_a.body, prepared.face_b.body), {})
        store = SimpleNamespace(create=Mock(return_value=anchor), read=Mock(return_value=record))
        with patch.object(fusion, "STORE", store), patch.object(fusion, "_assert_fresh"):
            self.assertIs(fusion.create_snap_fit(design, prepared), anchor)
        store.create.assert_called_once_with(design, record.targets,
                                             tuple(body for role, body in prepared.result_bodies))
        self.assertEqual(len(anchor.attributes.writes), 1)
        recipe = json.loads(anchor.attributes.writes[0][2])
        self.assertEqual(recipe["settings"], prepared.settings.to_dict())
        self.assertEqual(recipe["sources"], prepared.source_tokens)
        self.assertEqual(prepared.face_a.body.attributes.writes, [])
        self.assertEqual(prepared.face_b.body.attributes.writes, [])

    def test_rebuild_updates_same_record_instead_of_creating_history(self):
        design, prepared, target = saved_fixture()
        prepared = replace(prepared, settings=SnapFitSettings(width_mm=9))
        store = SimpleNamespace(update=Mock(return_value=target.anchor), read=Mock(return_value=target.record), create=Mock())
        with patch.object(fusion, "STORE", store), patch.object(fusion, "_assert_fresh"):
            self.assertIs(fusion.rebuild_snap_fit(design, target, prepared), target.anchor)
        store.update.assert_called_once_with(design, target.record,
                                             tuple(body for role, body in prepared.result_bodies))
        store.create.assert_not_called()
        recipe = json.loads(target.anchor.attributes.writes[-1][2])
        self.assertEqual(recipe["settings"]["width_mm"], 9)

    def test_wrong_target_or_wrong_role_order_never_reaches_store_mutation(self):
        design, prepared, target = saved_fixture()
        with patch.object(fusion, "STORE") as store, patch.object(fusion, "_assert_fresh"):
            with self.assertRaisesRegex(ValueError, "Use Rebuild"):
                fusion.create_snap_fit(design, prepared)
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                fusion.rebuild_snap_fit(design, replace(target, anchor=object()), prepared)
            wrong = replace(prepared, result_bodies=tuple(reversed(prepared.result_bodies)))
            with self.assertRaisesRegex(ValueError, "exactly two"):
                fusion.rebuild_snap_fit(design, target, wrong)
        store.create.assert_not_called()
        store.update.assert_not_called()

    def test_failed_recipe_write_is_reported_for_caller_transaction_rollback(self):
        design, prepared = prepared_fixture()
        anchor = Entity(attributes=SimpleNamespace(add=Mock(return_value=None)))
        record = SolidPairRecord(anchor, IDENTITY, (prepared.face_a.body, prepared.face_b.body), {})
        store = SimpleNamespace(create=Mock(return_value=anchor), read=Mock(return_value=record))
        with patch.object(fusion, "STORE", store), patch.object(fusion, "_assert_fresh"):
            with self.assertRaisesRegex(ValueError, "roll back"):
                fusion.create_snap_fit(design, prepared)
        store.create.assert_called_once()

    def test_preview_hides_only_two_explicit_targets_and_uses_existing_appearances(self):
        design, prepared = prepared_fixture()
        expected = (prepared.face_a.body, prepared.face_b.body)
        with patch.object(fusion, "_assert_fresh"), patch.object(
                fusion.hinge, "draw_solid_preview", return_value="owned group") as draw:
            self.assertEqual(fusion.preview_hide_bodies(prepared), expected)
            self.assertEqual(fusion.preview_snap_fit(prepared), "owned group")
        draw.assert_called_once_with(design, prepared.result_bodies,
                                     {"A": "body a appearance", "B": "body b appearance"})
        self.assertTrue(all(body.isLightBulbOn for body in expected))

    def test_read_edit_target_enters_owned_history_to_validate_saved_sources(self):
        design, prepared, target = saved_fixture()
        entered = []
        @contextmanager
        def scope(design, record):
            entered.append(record)
            yield record.targets
        store = SimpleNamespace(read=Mock(return_value=target.record), input_scope=scope)
        with patch.object(fusion, "STORE", store), patch.object(fusion, "_api", return_value=api()):
            result = fusion.read_edit_target(design, prepared.face_a.body)
        self.assertEqual(result.record, target.record)
        self.assertEqual(result.settings, target.settings)
        self.assertEqual(entered, [target.record])


if __name__ == "__main__":
    unittest.main()
