"""Ownership/failure contracts with small fakes, not native geometry validation."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.settings import HingeSettings
from Partelier.partelier.tools.hinge.seam import SeamCutBounds


class HingeFusionContractTests(unittest.TestCase):
    def selection_fixture(self):
        def point(x, y, z):
            return SimpleNamespace(x=x, y=y, z=z)

        root = object()
        body_a = SimpleNamespace(name="A", parentComponent=root, assemblyContext=None, isSolid=True,
                                 lumps=SimpleNamespace(count=1))
        body_b = SimpleNamespace(name="B", parentComponent=root, assemblyContext=None, isSolid=True,
                                 lumps=SimpleNamespace(count=1))
        edge = SimpleNamespace(
            isValid=True, assemblyContext=None, body=body_a, geometry=object(),
            startVertex=SimpleNamespace(geometry=point(-0.4, -2.5, 0)),
            endVertex=SimpleNamespace(geometry=point(-0.4, 2.5, 0)))
        face_a = SimpleNamespace(
            isValid=True, body=body_a, assemblyContext=None, area=10,
            geometry=SimpleNamespace(normal=point(0, 0, 1)), isParamReversed=False,
            pointOnFace=point(-1.4, 0, 0), edges=SimpleNamespace(count=1, item=lambda index: edge))
        face_b = SimpleNamespace(
            isValid=True, body=body_b, assemblyContext=None, area=10,
            geometry=SimpleNamespace(normal=point(0, 0, 1)), isParamReversed=False,
            pointOnFace=point(1.4, 0, 0), edges=SimpleNamespace(count=0))
        design = SimpleNamespace(isValid=True, designType=1, rootComponent=root,
                                 activeComponent=root, timeline=SimpleNamespace(markerPosition=3, count=3))
        identity_cast = SimpleNamespace(cast=lambda value: value)
        core = SimpleNamespace(Plane=identity_cast, Line3D=identity_cast)
        api = (core, SimpleNamespace(BRepFace=identity_cast, BRepEdge=identity_cast,
                                     DesignTypes=SimpleNamespace(ParametricDesignType=1)))
        return design, face_a, face_b, edge, api

    def recipe(self, version=1):
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat").to_dict()
        if version < 8:
            settings.pop("rotation_clearance_mm")
        if version < 7:
            settings.pop("web_profile")
        if version < 6:
            for field in fusion.STYLE_DEFAULTS:
                settings.pop(field)
        if version < 5:
            for field in fusion.FINISH_DEFAULTS:
                settings.pop(field)
        if version < 4:
            for field in fusion.LEAF_DEFAULTS:
                settings.pop(field)
        if version < 3:
            for field in ("hinge_count", "start_margin_mm", "end_margin_mm"):
                settings.pop(field)
        if version == 1:
            settings.pop("split_seam")
            settings.pop("seam_clearance_mm")
        return {"version": version, "tool": "pin_hinge",
                "feature_id": "de431a33-e909-4d18-9f1f-7518678982a4",
                "settings": settings,
                "sources": {key: key + " token" for key in
                            ("face_a", "face_b", "axis_edge", "body_a", "body_b")},
                "results": {role: "a" * 64 for role in ("A", "B", "pin")},
                "base_feature": "base feature token"}

    def owned_result_fixture(self, group):
        """An unchanged saved result, using real recipe/ownership validation."""
        def attributes(entries):
            tags = {key: SimpleNamespace(value=value, deleteMe=Mock())
                    for key, value in entries.items()}
            return SimpleNamespace(tags=tags, add=Mock(),
                                   itemByName=lambda namespace, name: tags.get((namespace, name)))

        recipe = self.recipe()
        component = SimpleNamespace(
            isValid=True, name="Existing hinge", features=SimpleNamespace(count=1),
            attributes=attributes({(group, fusion.RECIPE_NAME): json.dumps(recipe)}))
        for name in ("occurrences", "sketches", "meshBodies", "constructionPlanes", "constructionAxes",
                     "constructionPoints", "canvases", "decals", "joints", "asBuiltJoints", "jointOrigins"):
            setattr(component, name, SimpleNamespace(count=0))
        bodies = tuple(SimpleNamespace(attributes=attributes({
            (group, fusion.OWNER_NAME): json.dumps({"feature_id": recipe["feature_id"], "role": role})}))
            for role in ("A", "B", "pin"))
        component.bRepBodies = SimpleNamespace(count=len(bodies), item=lambda index: bodies[index])
        feature = SimpleNamespace(
            isValid=True, parentComponent=component,
            attributes=attributes({(group, fusion.OWNER_NAME): recipe["feature_id"]}),
            timelineObject=SimpleNamespace(index=5, isDeletable=True))
        source_a, source_b = SimpleNamespace(isValid=True), SimpleNamespace(isValid=True)
        entities = {
            recipe["base_feature"]: feature,
            recipe["sources"]["body_a"]: source_a,
            recipe["sources"]["body_b"]: source_b,
            recipe["sources"]["face_a"]: SimpleNamespace(isValid=True, body=source_a),
            recipe["sources"]["face_b"]: SimpleNamespace(isValid=True, body=source_b),
            recipe["sources"]["axis_edge"]: SimpleNamespace(isValid=True),
        }
        design = SimpleNamespace(
            isValid=True, designType=1, rootComponent=object(),
            timeline=SimpleNamespace(count=6, markerPosition=6),
            findEntityByToken=lambda token: [entities[token]] if token in entities else [])
        identity_cast = SimpleNamespace(cast=lambda value: value)
        api = (None, SimpleNamespace(
            BRepFace=SimpleNamespace(cast=lambda value: value if hasattr(value, "body") else None),
            BRepEdge=SimpleNamespace(cast=lambda value: value if value is entities[recipe["sources"]["axis_edge"]] else None),
            DesignTypes=SimpleNamespace(ParametricDesignType=1)))
        return design, component, feature, bodies, api

    def test_legacy_hinge_is_read_without_migrating_or_mutating_saved_result(self):
        design, component, feature, bodies, api = self.owned_result_fixture(fusion.LEGACY_ATTRIBUTE_GROUP)
        occurrence = object()
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_result_component", return_value=component), patch.object(
                fusion, "_owned_occurrence", return_value=occurrence), patch.object(
                fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, component)
        self.assertIs(target.component, component)
        self.assertIs(target.occurrence, occurrence)
        self.assertEqual(target.settings, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
        self.assertEqual(target.recipe, self.recipe())
        self.assertEqual(component.name, "Existing hinge")
        for entity in (component, feature, *bodies):
            entity.attributes.add.assert_not_called()
            for (group, _), tag in entity.attributes.tags.items():
                self.assertEqual(group, fusion.LEGACY_ATTRIBUTE_GROUP)
                tag.deleteMe.assert_not_called()

    def test_edit_refuses_mixed_namespaces_for_feature_or_body_ownership(self):
        for recipe_group, owner_group in (
                (fusion.LEGACY_ATTRIBUTE_GROUP, fusion.ATTRIBUTE_GROUP),
                (fusion.ATTRIBUTE_GROUP, fusion.LEGACY_ATTRIBUTE_GROUP)):
            for owner_location in ("feature", "body"):
                with self.subTest(recipe_group=recipe_group, owner_location=owner_location):
                    design, component, feature, bodies, api = self.owned_result_fixture(recipe_group)
                    owner = feature if owner_location == "feature" else bodies[0]
                    tag = owner.attributes.tags.pop((recipe_group, fusion.OWNER_NAME))
                    owner.attributes.tags[(owner_group, fusion.OWNER_NAME)] = tag
                    with patch.object(fusion, "_api", return_value=api), patch.object(
                            fusion, "_result_component", return_value=component), patch.object(
                            fusion, "_owned_occurrence", return_value=object()), patch.object(
                            fusion, "_body_signature", return_value="a" * 64):
                        with self.assertRaises(fusion.HingeGeometryError):
                            fusion.read_edit_target(design, component)

    def test_duplicate_recipe_namespaces_are_refused_even_when_recipes_match(self):
        _, component, _, _, _ = self.owned_result_fixture(fusion.LEGACY_ATTRIBUTE_GROUP)
        component.attributes.tags[(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME)] = SimpleNamespace(
            value=json.dumps(self.recipe()))
        with self.assertRaisesRegex(fusion.HingeGeometryError, "conflicting ownership"):
            fusion._recipe_attribute(component)
        component.attributes.add.assert_not_called()

    def test_new_ownership_is_written_only_in_partelier_namespace(self):
        entity = SimpleNamespace(attributes=SimpleNamespace(add=Mock(return_value=object())))
        fusion._attribute(entity, fusion.OWNER_NAME, "new hinge identity")
        entity.attributes.add.assert_called_once_with(
            "sktech_partelier_hinge_8c319ce2", fusion.OWNER_NAME, "new hinge identity")

    def test_recipe_rejects_future_versions_without_guessing(self):
        recipe = self.recipe()
        recipe["version"] = fusion.RECIPE_VERSION + 1
        with self.assertRaisesRegex(fusion.HingeGeometryError, "version"):
            fusion._read_recipe(json.dumps(recipe))

    def test_recipe_rejects_bool_version_and_missing_or_extra_fields(self):
        cases = []
        recipe = self.recipe()
        recipe["version"] = True
        cases.append(recipe)
        recipe = self.recipe()
        del recipe["sources"]["body_a"]
        cases.append(recipe)
        recipe = self.recipe()
        recipe["external_path"] = "untrusted"
        cases.append(recipe)
        for recipe in cases:
            with self.subTest(recipe=recipe), self.assertRaises(fusion.HingeGeometryError):
                fusion._read_recipe(json.dumps(recipe))

    def test_recipe_pin_roles_follow_settings(self):
        recipe = self.recipe()
        recipe["settings"]["include_pin"] = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "ownership"):
            fusion._read_recipe(json.dumps(recipe))
        del recipe["results"]["pin"]
        _, settings = fusion._read_recipe(json.dumps(recipe))
        self.assertFalse(settings.include_pin)

    def test_source_tokens_are_resolved_uniquely(self):
        design = Mock()
        entity = SimpleNamespace(isValid=True)
        for results in ([], [entity, entity], [SimpleNamespace(isValid=False)]):
            design.findEntityByToken.return_value = results
            with self.subTest(results=results), self.assertRaisesRegex(
                    fusion.HingeGeometryError, "missing or split"):
                fusion._resolve_one(design, "saved token", "Source face A")
        design.findEntityByToken.return_value = [entity]
        self.assertIs(fusion._resolve_one(design, "different token text", "Source A"), entity)

    def test_worker_cannot_enter_fusion_adapter(self):
        with patch.object(fusion.threading, "current_thread", return_value=object()):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "main thread"):
                fusion.prepare_hinge(None, None, None, None, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_fixture_frame_is_invariant_to_edge_orientation_and_converts_cm_once(self):
        design, face_a, face_b, edge, api = self.selection_fixture()
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="body fingerprint"):
            forward, _, _ = fusion._selection(design, face_a, face_b, edge, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
            edge.startVertex, edge.endVertex = edge.endVertex, edge.startVertex
            reverse, _, _ = fusion._selection(design, face_a, face_b, edge, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
        self.assertEqual(forward, reverse)
        self.assertEqual(forward.origin_mm, (0, 0, 0))
        self.assertEqual(forward.x_axis, (1, 0, 0))
        self.assertEqual(forward.y_axis, (0, 1, 0))
        self.assertEqual(forward.point_mm(0, -20, 4), (0, -20, 4))

    def test_coincident_edge_of_body_b_uses_a_identity_even_when_reversed(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="body fingerprint"):
            expected_frame, expected_signature, _ = fusion._selection(
                design, face_a, face_b, edge_a, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
            for reverse in (False, True):
                edge_b = SimpleNamespace(**vars(edge_a))
                edge_b.body = face_b.body
                if reverse:
                    edge_b.startVertex, edge_b.endVertex = edge_b.endVertex, edge_b.startVertex
                with self.subTest(reverse=reverse):
                    frame, signature, canonical = fusion._selection(
                        design, face_a, face_b, edge_b, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
                    self.assertIs(canonical, edge_a)
                    self.assertEqual(frame, expected_frame)
                    self.assertEqual(signature, expected_signature)

    def test_coincident_edge_from_unselected_body_is_refused(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        unrelated = SimpleNamespace(**vars(edge_a))
        unrelated.body = SimpleNamespace(name="C")
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "shared boundary"):
                fusion._selection(design, face_a, face_b, unrelated, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_axis_proxy_is_refused_even_when_native_segment_coincides(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        proxy = SimpleNamespace(**vars(edge_a))
        proxy.assemblyContext = object()
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "shared boundary"):
                fusion._selection(design, face_a, face_b, proxy, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_b_edge_must_match_complete_a_segment_not_just_its_support_line(self):
        for displacement, shortened in ((0.01, False), (0, True)):
            design, face_a, face_b, edge_a, api = self.selection_fixture()
            edge_b = SimpleNamespace(**vars(edge_a))
            edge_b.body = face_b.body
            start = edge_a.startVertex.geometry
            end = edge_a.endVertex.geometry
            edge_b.startVertex = SimpleNamespace(geometry=SimpleNamespace(
                x=start.x + displacement, y=start.y + (0.2 if shortened else 0), z=start.z))
            edge_b.endVertex = SimpleNamespace(geometry=SimpleNamespace(
                x=end.x + displacement, y=end.y, z=end.z))
            with self.subTest(displacement=displacement, shortened=shortened), patch.object(
                    fusion, "_api", return_value=api):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "complete straight boundary"):
                    fusion._selection(design, face_a, face_b, edge_b, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_multiple_coincident_boundaries_are_refused(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        duplicate = SimpleNamespace(**vars(edge_a))
        candidates = (edge_a, duplicate)
        face_a.edges = SimpleNamespace(count=2, item=lambda index: candidates[index])
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "multiple edges"):
                fusion._selection(design, face_a, face_b, edge_a, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_curved_b_edge_with_same_endpoints_cannot_stand_in_for_a_line(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        curved = SimpleNamespace(**vars(edge_a))
        curved.body = face_b.body
        curved.geometry = "curve"
        api[0].Line3D = SimpleNamespace(cast=lambda value: None if value == "curve" else value)
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "straight, finite"):
                fusion._selection(design, face_a, face_b, curved, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_prepare_saves_and_freshness_checks_the_canonical_a_edge(self):
        design, face_a, face_b, edge_a, api = self.selection_fixture()
        edge_b = SimpleNamespace(**vars(edge_a))
        edge_b.body = face_b.body
        edge_b.startVertex, edge_b.endVertex = edge_b.endVertex, edge_b.startVertex
        manager = SimpleNamespace(copy=lambda body: SimpleNamespace(
            isValid=True, isSolid=True, lumps=SimpleNamespace(count=1)))
        api[1].TemporaryBRepManager = SimpleNamespace(get=lambda: manager)
        api[1].BooleanTypes = SimpleNamespace(UnionBooleanType=1, DifferenceBooleanType=2)
        requested = HingeSettings(rotation_clearance_mm=0, web_profile="flat", include_pin=False, axis_offset_mm=9)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="body fingerprint"), patch.object(
                fusion, "_box", return_value=object()), patch.object(
                fusion, "_cylinder", return_value=object()), patch.object(
                fusion, "_positive_attachment"), patch.object(
                fusion, "_boolean"), patch.object(fusion, "_require_separate"):
            prepared = fusion.prepare_hinge(
                design, face_a, face_b, edge_b, requested)
            self.assertIs(prepared.axis_edge, edge_a)
            self.assertIs(prepared.settings, requested)
            self.assertFalse(prepared.settings.split_seam)
            self.assertEqual(prepared.frame.origin_mm, (5, 0, 0))
            # B's original pick is not retained as a hidden freshness dependency.
            edge_b.isValid = False
            fusion._assert_fresh(design, prepared)
            # Persisted recipes read exactly the canonical identity from prepared.
            edge_a.entityToken = "canonical A edge token"
            self.assertEqual(fusion._token(prepared.axis_edge), "canonical A edge token")
            edge_a.isValid = False
            with self.assertRaises(fusion.HingeGeometryError):
                fusion._assert_fresh(design, prepared)

    def split_fixture(self):
        def collection(items):
            return SimpleNamespace(count=len(items), item=lambda index: items[index])

        def point_mm(values):
            return SimpleNamespace(**dict(zip(("x", "y", "z"), (v / 10 for v in values))))

        def edge(body, start, end):
            return SimpleNamespace(
                isValid=True, assemblyContext=None, body=body,
                geometry=SimpleNamespace(kind="line"),
                startVertex=SimpleNamespace(geometry=point_mm(start)),
                endVertex=SimpleNamespace(geometry=point_mm(end)))

        design, _, _, _, api = self.selection_fixture()
        api[0].Plane = SimpleNamespace(cast=lambda value: value if hasattr(value, "normal") else None)
        api[0].Line3D = SimpleNamespace(cast=lambda value: value if getattr(value, "kind", None) == "line" else None)
        faces = []
        for role, x_min, x_max, normal in (("A", -20, 0, 1), ("B", 0, 6, -1)):
            body = SimpleNamespace(name=role, parentComponent=design.rootComponent, assemblyContext=None,
                                   isSolid=True, lumps=SimpleNamespace(count=1))
            corners = ((0, -30, 0), (0, 30, 0), (0, 30, -8), (0, -30, -8))
            edges = tuple(edge(body, corners[i], corners[(i + 1) % 4]) for i in range(4))
            top = SimpleNamespace(
                name="top " + role, isValid=True, body=body, assemblyContext=None, area=12,
                geometry=SimpleNamespace(normal=SimpleNamespace(x=0, y=0, z=1)), isParamReversed=False,
                pointOnFace=point_mm(((x_min + x_max) / 2, 0, 0)), edges=collection((edges[0],)))
            mating = SimpleNamespace(
                name="mating " + role, isValid=True, body=body, assemblyContext=None,
                geometry=SimpleNamespace(normal=SimpleNamespace(x=normal, y=0, z=0)),
                isParamReversed=False, loops=collection((object(),)), edges=collection(edges))
            edges[0].faces = collection((top, mating))
            body.faces = collection((top, mating))
            body.edges = collection(edges)
            body.vertices = collection(tuple(SimpleNamespace(geometry=point_mm((x, y, z)))
                                             for x in (x_min, x_max) for y in (-30, 30) for z in (-8, 0)))
            faces.append(top)
        return design, *faces, faces[0].edges.item(0), api

    def test_split_frame_centers_on_shared_edge_and_cuts_full_interface(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", split_seam=True, length_mm=40, axis_offset_mm=9)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="source fingerprint"):
            frame, _, canonical = fusion._selection(design, face_a, face_b, face_b.edges.item(0), settings)
            bounds = fusion._split_clearance_bounds(face_a, face_b, canonical, frame, settings)
        self.assertIs(canonical, edge_a)
        self.assertEqual(frame.origin_mm, (0, 0, 0))
        self.assertEqual(frame.x_axis, (1, 0, 0))
        self.assertEqual((bounds.x_min_mm, bounds.x_max_mm), (-0.15, 0.15))
        self.assertLess(bounds.y_min_mm, -30)
        self.assertGreater(bounds.y_max_mm, 30)
        self.assertLess(bounds.z_min_mm, -8)
        self.assertGreater(bounds.z_max_mm, 0)

    def test_touching_seam_is_centered_automatically_without_mutating_requested_settings(self):
        for reverse_pick in (False, True):
            design, face_a, face_b, edge_a, api = self.split_fixture()
            edge_b = face_b.edges.item(0)
            if reverse_pick:
                for edge in (edge_a, edge_b):
                    edge.startVertex, edge.endVertex = edge.endVertex, edge.startVertex
            selected = edge_b if reverse_pick else edge_a
            requested = HingeSettings(rotation_clearance_mm=0, web_profile="flat", include_pin=False, axis_offset_mm=9)
            manager = SimpleNamespace(copy=lambda body: SimpleNamespace(
                isValid=True, isSolid=True, lumps=SimpleNamespace(count=1)))
            api[1].TemporaryBRepManager = SimpleNamespace(get=lambda: manager)
            api[1].BooleanTypes = SimpleNamespace(UnionBooleanType=1, DifferenceBooleanType=2)
            with self.subTest(reverse_pick=reverse_pick), patch.object(
                    fusion, "_api", return_value=api), patch.object(
                    fusion, "_body_signature", return_value="source fingerprint"), patch.object(
                    fusion, "_cut_split_copies", return_value=object()) as cut, patch.object(
                    fusion, "_box", return_value=object()), patch.object(
                    fusion, "_cylinder", return_value=object()), patch.object(
                    fusion, "_positive_attachment"), patch.object(
                    fusion, "_boolean"), patch.object(fusion, "_require_separate"):
                prepared = fusion.prepare_hinge(design, face_a, face_b, selected, requested)
                fusion._assert_fresh(design, prepared)
            self.assertFalse(requested.split_seam)
            self.assertIsNot(prepared.settings, requested)
            self.assertTrue(prepared.settings.split_seam)
            self.assertTrue(prepared.settings.to_dict()["split_seam"])
            self.assertEqual(prepared.settings.axis_offset_mm, 9)
            self.assertEqual(prepared.settings.seam_clearance_mm, requested.seam_clearance_mm)
            self.assertEqual(prepared.frame.origin_mm, (0, 0, 0))
            self.assertEqual(prepared.frame.x_axis, (1, 0, 0))
            self.assertEqual(prepared.frame.y_axis, (0, 1, 0))
            self.assertIs(prepared.axis_edge, edge_a)
            cut.assert_called_once()
            bounds = cut.call_args.args[3]
            self.assertEqual((bounds.x_min_mm, bounds.x_max_mm), (-0.15, 0.15))

    def test_automatic_touching_seam_refuses_unsupported_geometry_before_temporary_writes(self):
        for failure in ("hole", "depth", "curved face", "cross seam"):
            design, face_a, face_b, edge_a, api = self.split_fixture()
            if failure == "hole":
                face_b.body.faces.item(1).loops.count = 2
            elif failure == "depth":
                for boundary in fusion._items(face_b.body.faces.item(1).edges):
                    for vertex in (boundary.startVertex, boundary.endVertex):
                        if vertex.geometry.z < 0:
                            vertex.geometry.z = -0.7
            elif failure == "curved face":
                existing_faces = fusion._items(face_b.body.faces)
                boundary_faces = (*existing_faces, SimpleNamespace(geometry=object()))
                face_b.body.faces = SimpleNamespace(count=3, item=lambda index: boundary_faces[index])
            else:
                face_a.body.vertices.item(0).geometry.x = 0.1
            manager = Mock()
            get_manager = Mock(return_value=manager)
            api[1].TemporaryBRepManager = SimpleNamespace(get=get_manager)
            requested = HingeSettings(rotation_clearance_mm=0, web_profile="flat")
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api), patch.object(
                    fusion, "_body_signature", return_value="source fingerprint"):
                with self.assertRaises(fusion.HingeGeometryError):
                    fusion.prepare_hinge(design, face_a, face_b, edge_a, requested)
            self.assertFalse(requested.split_seam)
            get_manager.assert_not_called()
            self.assertEqual(manager.mock_calls, [])

    def test_automatic_touching_seam_refuses_ambiguous_b_boundaries_before_temporary_writes(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        edge_b = face_b.edges.item(0)
        duplicate = SimpleNamespace(**vars(edge_b))
        boundaries = (edge_b, duplicate)
        face_b.edges = SimpleNamespace(count=2, item=lambda index: boundaries[index])
        get_manager = Mock()
        api[1].TemporaryBRepManager = SimpleNamespace(get=get_manager)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="source fingerprint"):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "one complete coincident"):
                fusion.prepare_hinge(design, face_a, face_b, edge_a, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))
        get_manager.assert_not_called()

    def test_split_placement_survives_rigid_rotation_translation_and_reversed_pick(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        # World mapping in cm: (x,y,z) -> (z+3,x-2,y+5).
        # It is a proper rotation, so handedness and surface normals are kept.
        points = {}
        for face in (face_a, face_b):
            points[id(face.pointOnFace)] = face.pointOnFace
            for vertex in fusion._items(face.body.vertices):
                points[id(vertex.geometry)] = vertex.geometry
            for edge in fusion._items(face.body.edges):
                for vertex in (edge.startVertex, edge.endVertex):
                    points[id(vertex.geometry)] = vertex.geometry
            for boundary_face in fusion._items(face.body.faces):
                normal = boundary_face.geometry.normal
                normal.x, normal.y, normal.z = normal.z, normal.x, normal.y
        for point in points.values():
            point.x, point.y, point.z = point.z + 3, point.x - 2, point.y + 5
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", split_seam=True)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="fingerprint"):
            expected_frame, _, canonical = fusion._selection(design, face_a, face_b, edge_a, settings)
            expected_bounds = fusion._split_clearance_bounds(face_a, face_b, canonical, expected_frame, settings)
            edge_a.startVertex, edge_a.endVertex = edge_a.endVertex, edge_a.startVertex
            actual_frame, _, canonical = fusion._selection(
                design, face_a, face_b, face_b.edges.item(0), settings)
            actual_bounds = fusion._split_clearance_bounds(face_a, face_b, canonical, actual_frame, settings)
        self.assertEqual(actual_frame, expected_frame)
        self.assertEqual(actual_bounds, expected_bounds)
        self.assertEqual(actual_frame.origin_mm, (30, -20, 50))
        self.assertEqual(actual_frame.x_axis, (0, 1, 0))
        self.assertEqual(actual_frame.y_axis, (0, 0, 1))
        self.assertEqual(actual_frame.z_axis, (1, 0, 0))

    def test_split_refuses_nonmatching_rectangles_holes_and_wrong_normals(self):
        for failure in ("depth", "hole", "normal", "missing B edge"):
            design, face_a, face_b, edge_a, api = self.split_fixture()
            mating = face_b.body.faces.item(1)
            if failure == "depth":
                for boundary in fusion._items(mating.edges):
                    for vertex in (boundary.startVertex, boundary.endVertex):
                        if vertex.geometry.z < 0:
                            vertex.geometry.z = -0.7
            elif failure == "hole":
                mating.loops.count = 2
            elif failure == "normal":
                mating.geometry.normal.x = 1
            else:
                face_b.edges.count = 0
            settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", split_seam=True)
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api), patch.object(
                    fusion, "_body_signature", return_value="fingerprint"):
                frame, _, _ = fusion._selection(design, face_a, face_b, edge_a, settings)
                with self.assertRaises(fusion.HingeGeometryError):
                    fusion._split_clearance_bounds(face_a, face_b, edge_a, frame, settings)

    def test_split_refuses_curved_or_cross_seam_source_geometry(self):
        for failure in ("curved face", "curved edge", "cross plane"):
            design, face_a, face_b, edge_a, api = self.split_fixture()
            if failure == "curved face":
                face_a.body.faces.item(0).geometry = object()
            elif failure == "curved edge":
                face_a.body.edges.item(1).geometry = object()
            else:
                face_a.body.vertices.item(0).geometry.x = 0.1
            frame = fusion.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "flat faces|straight|own side"):
                    fusion._require_split_half_space(face_a.body, frame, "A")

    def test_split_cut_targets_only_copied_bodies_and_keeps_clearance_marker_out_of_results(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        originals = (face_a.body, face_b.body)
        manager = SimpleNamespace()
        copied_sources = []
        def copy(body):
            result = SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1), volume=10,
                                     copied_from=body)
            if any(body is original for original in originals):
                copied_sources.append(result)
            return result
        manager.copy = copy
        api[1].TemporaryBRepManager = SimpleNamespace(get=lambda: manager)
        api[1].BooleanTypes = SimpleNamespace(UnionBooleanType=1, DifferenceBooleanType=2)
        cutter = object()
        attachment = object()
        operations = []
        def boolean(manager_arg, target, tool, operation, message):
            self.assertFalse(any(target is original for original in originals))
            operations.append((target, tool, operation))
            if tool is cutter:
                target.volume -= 1
            return target
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", split_seam=True, include_pin=False)
        attachments = Mock()
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="fingerprint"), patch.object(
                fusion, "_box", side_effect=lambda manager, frame, bounds: cutter
                    if isinstance(bounds, SeamCutBounds) else attachment), patch.object(
                fusion, "_cylinder", return_value=object()), patch.object(
                fusion, "_positive_attachment", attachments), patch.object(
                fusion, "_boolean", side_effect=boolean), patch.object(fusion, "_require_separate") as separate:
            prepared = fusion.prepare_hinge(design, face_a, face_b, edge_a, settings)
        self.assertEqual(tuple(role for role, _ in prepared.result_bodies), ("A", "B"))
        self.assertIs(prepared.preview_bodies, prepared.result_bodies)
        self.assertNotIn("clearance", {role for role, _ in prepared.preview_bodies})
        cut_operations = [(target, tool, operation) for target, tool, operation in operations if tool is cutter]
        self.assertEqual(len(cut_operations), 2)
        self.assertIs(cut_operations[0][0], copied_sources[0])
        self.assertIs(cut_operations[1][0], copied_sources[1])
        self.assertTrue(all(operation == 2 for _, _, operation in cut_operations))
        for call in attachments.call_args_list:
            reference = call.args[2]
            self.assertTrue(any(reference.copied_from is copy for copy in copied_sources))
        separate.assert_called_once()

    def test_multiple_hinges_share_source_copies_and_one_seam_cut_with_independent_pins(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        copied = []
        def copy(original):
            result = SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1),
                                     copied_from=original)
            copied.append(result)
            return result
        manager = SimpleNamespace(copy=copy)
        api[1].TemporaryBRepManager = SimpleNamespace(get=lambda: manager)
        api[1].BooleanTypes = SimpleNamespace(UnionBooleanType=1, DifferenceBooleanType=2)
        cylinders = []
        def cylinder(manager_arg, frame, start, end, radius, height):
            result = object()
            cylinders.append((frame, start, end, radius, result))
            return result
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", hinge_count=3, length_mm=10, start_margin_mm=5, end_margin_mm=10)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="fingerprint"), patch.object(
                fusion, "_cut_split_copies", return_value=object()) as cut, patch.object(
                fusion, "_box", return_value=object()), patch.object(
                fusion, "_cylinder", side_effect=cylinder), patch.object(
                fusion, "_positive_attachment"), patch.object(fusion, "_boolean"), patch.object(
                fusion, "_require_separate") as separate:
            prepared = fusion.prepare_hinge(design, face_a, face_b, edge_a, settings)
        self.assertEqual(len(copied), 4)  # Two result copies and two attachment references.
        self.assertIs(copied[0].copied_from, face_a.body)
        self.assertIs(copied[1].copied_from, face_b.body)
        cut.assert_called_once()
        self.assertEqual([item.center_mm for item in prepared.layout.placements], [-20, -2.5, 15])
        self.assertEqual({item[0].origin_mm for item in cylinders}, {(0, -20, 0), (0, -2.5, 0), (0, 15, 0)})
        self.assertEqual(len(cylinders), 3 * (2 * settings.knuckle_count + 1))
        self.assertEqual(tuple(role for role, _ in prepared.result_bodies), ("A", "B", "pin_1", "pin_2", "pin_3"))
        self.assertEqual(separate.call_count, 10)  # Halves, pins/halves and all three pin pairs.
        pin_calls = [item for item in cylinders if item[3] == settings.pin_diameter_mm / 2]
        self.assertEqual(len(pin_calls), 3)
        self.assertEqual([item[0].origin_mm[1] + item[1] for item in pin_calls], [-27, -9.5, 8])
        self.assertEqual([item[0].origin_mm[1] + item[2] for item in pin_calls], [-13, 4.5, 22])
        self.assertTrue(prepared.settings.split_seam)
        self.assertFalse(settings.split_seam)

    def test_layout_that_does_not_fit_is_rejected_before_temporary_source_copies(self):
        design, face_a, face_b, edge_a, api = self.split_fixture()
        get_manager = Mock()
        api[1].TemporaryBRepManager = SimpleNamespace(get=get_manager)
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", hinge_count=3, length_mm=20)
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_body_signature", return_value="fingerprint"):
            with self.assertRaises(ValueError):
                fusion.prepare_hinge(design, face_a, face_b, edge_a, settings)
        get_manager.assert_not_called()

    def test_separate_units_do_not_copy_trim_or_require_attachment_to_source_bodies(self):
        for profile, holes in (("rectangular", False), ("rounded", True)):
            design, face_a, face_b, edge_a, api = self.split_fixture()
            # These source mating faces are unsupported for a cut, but separate
            # leaves only use the chosen coplanar outside faces for placement.
            face_b.body.faces.item(1).loops.count = 2
            manager = SimpleNamespace(copy=Mock(side_effect=AssertionError("Source copy was attempted")))
            api[1].TemporaryBRepManager = SimpleNamespace(get=lambda: manager)
            api[1].BooleanTypes = SimpleNamespace(UnionBooleanType=1, DifferenceBooleanType=2)
            leaves = []
            def plate(manager_arg, frame, bounds):
                result = object()
                leaves.append((frame, bounds, result))
                return result
            settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", output_mode="separate", leaf_profile=profile, screw_holes=holes,
                                     hinge_count=2, length_mm=20, start_margin_mm=5, end_margin_mm=5)
            with self.subTest(profile=profile, holes=holes), patch.object(
                    fusion, "_api", return_value=api), patch.object(
                    fusion, "_body_signature", return_value="fingerprint"), patch.object(
                    fusion, "_split_clearance_bounds") as bounds, patch.object(
                    fusion, "_cut_split_copies") as cut, patch.object(
                    fusion, "_positive_attachment") as attached, patch.object(
                    fusion, "_leaf_plate", side_effect=plate), patch.object(
                    fusion, "_box", return_value=object()), patch.object(
                    fusion, "_cylinder", side_effect=lambda *args: object()), patch.object(
                    fusion, "_boolean"), patch.object(fusion, "_drill_leaf") as drill, patch.object(
                    fusion, "_require_separate") as separate:
                prepared = fusion.prepare_hinge(design, face_a, face_b, edge_a, settings)
                fusion._assert_fresh(design, prepared)
            manager.copy.assert_not_called()
            bounds.assert_not_called()
            cut.assert_not_called()
            attached.assert_not_called()
            self.assertEqual(tuple(role for role, _ in prepared.result_bodies),
                             ("A_1", "B_1", "A_2", "B_2", "pin_1", "pin_2"))
            self.assertEqual(len(leaves), 4)
            self.assertEqual(drill.call_count, 8 if holes else 0)
            self.assertEqual(separate.call_count, 15)
            self.assertEqual(len(prepared.preview_bodies), 6)
            self.assertNotIn("clearance", {role for role, _ in prepared.preview_bodies})
            self.assertTrue(prepared.settings.split_seam)
            self.assertEqual(prepared.frame.origin_mm, (0, 0, 0))
            self.assertTrue(all(web.z_min_mm == 0 for web in prepared.plan.webs))

    def test_split_cut_rejects_unchanged_or_disconnected_copy(self):
        body_a = SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1), volume=2)
        body_b = SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1), volume=2)
        api = (None, SimpleNamespace(BooleanTypes=SimpleNamespace(DifferenceBooleanType=2)))
        for disconnected in (False, True):
            body_a.lumps.count = 1
            def operation(target, tool, kind):
                if disconnected:
                    target.lumps.count = 2
                    target.volume = 1
                return True
            manager = SimpleNamespace(booleanOperation=operation)
            with self.subTest(disconnected=disconnected), patch.object(fusion, "_api", return_value=api), patch.object(
                    fusion, "_box", return_value=object()):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "positive material|remove or split"):
                    fusion._cut_split_copies(manager, {"A": body_a, "B": body_b}, object(), object())

    def test_v1_recipe_migrates_settings_only_in_memory_and_rejects_new_or_missing_keys(self):
        recipe = self.recipe()
        original = json.dumps(recipe, sort_keys=True)
        decoded, settings = fusion._read_recipe(json.dumps(recipe))
        self.assertEqual(json.dumps(decoded, sort_keys=True), original)
        self.assertNotIn("split_seam", decoded["settings"])
        self.assertFalse(settings.split_seam)
        self.assertEqual(settings.seam_clearance_mm, 0.3)
        for key, value in (("split_seam", True), ("seam_clearance_mm", 0.3), ("unknown", 1)):
            changed = self.recipe()
            changed["settings"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(fusion.HingeGeometryError, "version 1"):
                fusion._read_recipe(json.dumps(changed))
        changed = self.recipe()
        del changed["settings"]["length_mm"]
        with self.assertRaisesRegex(fusion.HingeGeometryError, "version 1"):
            fusion._read_recipe(json.dumps(changed))

    def test_v2_recipe_round_trips_split_settings_and_rejects_missing_fields(self):
        recipe = self.recipe(version=2)
        recipe["settings"]["split_seam"] = True
        recipe["settings"]["seam_clearance_mm"] = 0.4
        decoded, settings = fusion._read_recipe(json.dumps(recipe))
        self.assertEqual(decoded, recipe)
        self.assertTrue(settings.split_seam)
        self.assertEqual(settings.seam_clearance_mm, 0.4)
        self.assertEqual(fusion.RECIPE_VERSION, 8)
        del recipe["settings"]["split_seam"]
        with self.assertRaises(ValueError):
            fusion._read_recipe(json.dumps(recipe))

    def test_create_writes_v5_recipe_with_full_split_and_layout_settings(self):
        bodies = tuple(SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1),
                                       entityToken="result " + role) for role in ("A", "B"))
        base = SimpleNamespace(
            isValid=True, entityToken="new base", startEdit=Mock(return_value=True),
            finishEdit=Mock(return_value=True),
            bodies=SimpleNamespace(count=2, item=lambda index: bodies[index]))
        component = SimpleNamespace(
            features=SimpleNamespace(baseFeatures=SimpleNamespace(add=Mock(return_value=base))),
            bRepBodies=SimpleNamespace(add=Mock(side_effect=bodies)))
        occurrence = SimpleNamespace(component=component, isValid=True, deleteMe=Mock(return_value=True))
        design = SimpleNamespace(rootComponent=SimpleNamespace(occurrences=SimpleNamespace(
            addNewComponent=Mock(return_value=occurrence))))
        settings = HingeSettings(rotation_clearance_mm=0, web_profile="flat", split_seam=True, seam_clearance_mm=0.4, include_pin=False)
        prepared = SimpleNamespace(
            face_a=SimpleNamespace(entityToken="fa", body=SimpleNamespace(entityToken="ba")),
            face_b=SimpleNamespace(entityToken="fb", body=SimpleNamespace(entityToken="bb")),
            axis_edge=SimpleNamespace(entityToken="canonical A edge"), settings=settings,
            result_bodies=(("A", object()), ("B", object())))
        core = SimpleNamespace(Matrix3D=SimpleNamespace(create=lambda: object()))
        with patch.object(fusion, "_assert_fresh"), patch.object(
                fusion, "_api", return_value=(core, None)), patch.object(
                fusion, "_body_signature", return_value="a" * 64), patch.object(
                fusion, "_attribute") as attribute:
            result = fusion._create(design, prepared, self.recipe()["feature_id"])
        self.assertIs(result, component)
        saved = [json.loads(call.args[2]) for call in attribute.call_args_list
                 if call.args[0] is component and call.args[1] == fusion.RECIPE_NAME]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["version"], 8)
        self.assertEqual(saved[0]["settings"], settings.to_dict())
        self.assertEqual(saved[0]["sources"]["axis_edge"], "canonical A edge")
        decoded, read_settings = fusion._read_recipe(json.dumps(saved[0]))
        self.assertEqual(read_settings, settings)
        self.assertEqual(decoded, saved[0])
        occurrence.deleteMe.assert_not_called()

    def test_opposite_normals_are_rejected_before_temporary_geometry(self):
        design, face_a, face_b, edge, api = self.selection_fixture()
        face_b.isParamReversed = True
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "matching outward normals"):
                fusion._selection(design, face_a, face_b, edge, HingeSettings(rotation_clearance_mm=0, web_profile="flat"))

    def test_failed_intersection_requires_independent_positive_gap(self):
        overlap = SimpleNamespace(isValid=True, isSolid=False, volume=0)
        manager = SimpleNamespace(copy=Mock(return_value=overlap),
                                  booleanOperation=Mock(return_value=False))
        measure = Mock(return_value=SimpleNamespace(value=0.03))
        core = SimpleNamespace(Application=SimpleNamespace(get=lambda: SimpleNamespace(
            measureManager=SimpleNamespace(measureMinimumDistance=measure))))
        api = (core, SimpleNamespace(BooleanTypes=SimpleNamespace(IntersectionBooleanType=1)))
        with patch.object(fusion, "_api", return_value=api):
            fusion._require_separate(manager, object(), object(), "Halves")
            measure.return_value = None
            with self.assertRaisesRegex(fusion.HingeGeometryError, "ambiguous"):
                fusion._require_separate(manager, object(), object(), "Halves")
            measure.return_value = SimpleNamespace(value=0)
            with self.assertRaisesRegex(fusion.HingeGeometryError, "touch"):
                fusion._require_separate(manager, object(), object(), "Halves")

    def test_positive_intersection_rejected_even_if_measurement_would_claim_gap(self):
        overlap = SimpleNamespace(isValid=True, isSolid=True, volume=0.1)
        manager = SimpleNamespace(copy=Mock(return_value=overlap),
                                  booleanOperation=Mock(return_value=True))
        api = (object(), SimpleNamespace(BooleanTypes=SimpleNamespace(IntersectionBooleanType=1)))
        with patch.object(fusion, "_api", return_value=api):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "overlap"):
                fusion._require_separate(manager, object(), object(), "Halves")

    def test_failed_create_closes_base_feature_and_deletes_only_new_occurrence(self):
        new_occurrence = Mock(isValid=True)
        base = Mock(isValid=True)
        base.startEdit.return_value = True
        base.finishEdit.return_value = True
        new_occurrence.component.features.baseFeatures.add.return_value = base
        new_occurrence.component.bRepBodies.add.side_effect = RuntimeError("injected add failure")
        design = Mock()
        design.rootComponent.occurrences.addNewComponent.return_value = new_occurrence
        prepared = SimpleNamespace(
            face_a=SimpleNamespace(entityToken="fa", body=SimpleNamespace(entityToken="ba")),
            face_b=SimpleNamespace(entityToken="fb", body=SimpleNamespace(entityToken="bb")),
            axis_edge=SimpleNamespace(entityToken="ea"), result_bodies=(("A", object()),))
        core = SimpleNamespace(Matrix3D=SimpleNamespace(create=lambda: object()))
        with patch.object(fusion, "_assert_fresh"), patch.object(fusion, "_api", return_value=(core, None)):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                fusion._create(design, prepared, self.recipe()["feature_id"])
        base.finishEdit.assert_called_once_with()
        new_occurrence.deleteMe.assert_called_once_with()

    def test_incomplete_create_cleanup_is_reported(self):
        occurrence = Mock(isValid=True)
        occurrence.component.features.baseFeatures.add.return_value = None
        occurrence.deleteMe.return_value = False
        design = Mock()
        design.rootComponent.occurrences.addNewComponent.return_value = occurrence
        prepared = SimpleNamespace(
            face_a=SimpleNamespace(entityToken="fa", body=SimpleNamespace(entityToken="ba")),
            face_b=SimpleNamespace(entityToken="fb", body=SimpleNamespace(entityToken="bb")),
            axis_edge=SimpleNamespace(entityToken="ea"))
        core = SimpleNamespace(Matrix3D=SimpleNamespace(create=lambda: object()))
        with patch.object(fusion, "_assert_fresh"), patch.object(fusion, "_api", return_value=(core, None)):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "Cleanup incomplete.*Undo"):
                fusion._create(design, prepared, self.recipe()["feature_id"])

    def test_rebuild_keeps_previous_result_when_replacement_creation_fails(self):
        target = SimpleNamespace(component=object(), feature_id="same", recipe={},
                                 face_a=object(), face_b=object(), axis_edge=object(), occurrence=Mock())
        prepared = SimpleNamespace(face_a=target.face_a, face_b=target.face_b, axis_edge=target.axis_edge,
                                   settings=HingeSettings(output_mode="separate"))
        with patch.object(fusion, "read_edit_target", return_value=target), patch.object(
                fusion, "_create", side_effect=RuntimeError("new geometry failed")):
            with self.assertRaisesRegex(RuntimeError, "new geometry"):
                fusion.rebuild_hinge(object(), target, prepared)
        target.occurrence.deleteMe.assert_not_called()

    def test_rebuild_cleans_replacement_if_retiring_prior_result_fails(self):
        previous = Mock()
        previous.deleteMe.return_value = False
        target = SimpleNamespace(component=object(), feature_id="same", recipe={},
                                 face_a=object(), face_b=object(), axis_edge=object(), occurrence=previous)
        prepared = SimpleNamespace(face_a=target.face_a, face_b=target.face_b, axis_edge=target.axis_edge,
                                   settings=HingeSettings(output_mode="separate"))
        replacement = object()
        next_occurrence = Mock(isValid=True)
        next_occurrence.deleteMe.return_value = True
        with patch.object(fusion, "read_edit_target", return_value=target), patch.object(
                fusion, "_create", return_value=replacement), patch.object(
                fusion, "_owned_occurrence", return_value=next_occurrence), patch.object(
                fusion, "_is_part_design", return_value=False):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "prior hinge was retained"):
                fusion.rebuild_hinge(object(), target, prepared)
        next_occurrence.deleteMe.assert_called_once_with()

    def test_rebuild_rejects_changed_recipe_before_creating_anything(self):
        target = SimpleNamespace(component=object(), feature_id="same", recipe={"version": 1})
        current = SimpleNamespace(feature_id="same", recipe={"version": 2})
        with patch.object(fusion, "read_edit_target", return_value=current), patch.object(
                fusion, "_create") as create:
            with self.assertRaisesRegex(fusion.HingeGeometryError, "changed"):
                fusion.rebuild_hinge(object(), target, object())
        create.assert_not_called()

    def test_edit_refuses_any_later_timeline_feature_before_touching_bodies(self):
        component = SimpleNamespace(isValid=True, features=SimpleNamespace(count=1))
        for name in ("occurrences", "sketches", "meshBodies", "constructionPlanes", "constructionAxes",
                     "constructionPoints", "canvases", "decals", "joints", "asBuiltJoints", "jointOrigins"):
            setattr(component, name, SimpleNamespace(count=0))
        recipe = self.recipe()
        tag = SimpleNamespace(value=recipe["feature_id"])
        feature = SimpleNamespace(parentComponent=component,
                                  attributes=SimpleNamespace(itemByName=lambda *args: tag),
                                  timelineObject=SimpleNamespace(index=4, isDeletable=True))
        design = SimpleNamespace(rootComponent=object(), timeline=SimpleNamespace(count=6))
        with patch.object(fusion, "_owned_occurrence", return_value=object()), patch.object(
                fusion, "_resolve_one", return_value=feature):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "last in the timeline"):
                fusion._guard_owned_result(design, component, recipe)

    def test_edit_refuses_added_component_content(self):
        component = SimpleNamespace(isValid=True, occurrences=SimpleNamespace(count=1))
        design = SimpleNamespace(rootComponent=object())
        with patch.object(fusion, "_owned_occurrence", return_value=object()):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "added content"):
                fusion._guard_owned_result(design, component, self.recipe())


if __name__ == "__main__":
    unittest.main()
