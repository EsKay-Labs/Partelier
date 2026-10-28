"""Saved pattern and reviewed-result contracts; no native CAD is simulated here."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools import patterns as package
from Partelier.partelier.tools.patterns.settings import PatternSettings


class Entity:
    def __init__(self, token, kind="body", body=None):
        self.entityToken = token
        self.kind = kind
        self.body = body
        self.isValid = True


class Attributes:
    def __init__(self, events):
        self.values = {}
        self.events = events
        self.reject_write = False

    def itemByName(self, group, name):
        value = self.values.get((group, name))
        return None if value is None else NS(value=value)

    def add(self, group, name, value):
        self.events.append("save")
        if self.reject_write:
            return None
        self.values[(group, name)] = value
        return NS(value=value)


@dataclass(frozen=True)
class Prepared:
    design: object
    body: object
    settings: PatternSettings
    result_body: object
    source_tokens: dict
    record: object = None
    saved_recipe: object = None


class PatternRecipeTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.body = Entity("opaque-source-body")
        self.faces = tuple(Entity("opaque-face-" + str(index), "face", self.body) for index in range(2))
        self.entities = {entity.entityToken: [entity] for entity in (self.body, *self.faces)}
        self.design = NS(historical=False)
        def resolve(token):
            self.assertTrue(self.design.historical, "saved references must resolve before the owned feature")
            self.events.append("resolve:" + token)
            return self.entities.get(token, [])
        self.design.findEntityByToken = Mock(side_effect=resolve)
        self.anchor = NS(attributes=Attributes(self.events))
        self.record = NS(anchor=self.anchor, feature_id="a824b03c-044b-467b-8b12-19e85e6d3510", recipe={'version':1})
        self.settings = PatternSettings(pattern="circle", mode="engrave", layout_mode="balanced", pitch_mm=9,
            web_mm=1.5, depth_mm=.6, border_mm=0, rotation_deg=-30,
            offset_u_mm=-1.2, offset_v_mm=2.3, selection_scope="faces")
        self.tokens = {"body": self.body.entityToken, "faces": [face.entityToken for face in self.faces]}
        self.prepared = Prepared(self.design, self.body, self.settings,
                                 NS(isTemporary=True), deepcopy(self.tokens))
        self.scope_exit_error = None
        @contextmanager
        def input_scope(design, record):
            self.assertIs(design, self.design)
            self.assertIs(record, self.record)
            self.assertFalse(design.historical)
            self.events.append("enter-history")
            design.historical = True
            try:
                yield self.body
            finally:
                design.historical = False
                self.events.append("restore-history")
                if self.scope_exit_error:
                    raise self.scope_exit_error
        def store_write(name):
            def write(*args):
                self.assertFalse(self.design.historical, "persistence waits for history restoration")
                self.events.append(name)
                return self.anchor
            return write
        self.store = NS(read=Mock(return_value=self.record), input_scope=Mock(side_effect=input_scope),
                        create=Mock(side_effect=store_write("create")), update=Mock(side_effect=store_write("update")))
        self.fusion = ModuleType(package.__name__ + ".fusion")
        def validate(prepared, **kwargs):
            self.assertEqual(self.design.historical, kwargs.get("_historical", False))
            self.events.append("validate-historical" if kwargs.get("_historical") else "validate-current")
        def prepare(design, faces, settings, **kwargs):
            self.assertTrue(design.historical)
            self.assertEqual(kwargs, {"_historical": True})
            self.assertEqual(faces, self.faces)
            self.events.append("prepare-historical")
            return replace(self.prepared, settings=settings)
        self.fusion.validate_sources = Mock(side_effect=validate)
        self.fusion.prepare_pattern = Mock(side_effect=prepare)
        native, adsk = ModuleType("adsk.fusion"), ModuleType("adsk")
        native.BRepFace = NS(cast=lambda value: value if getattr(value, "kind", None) == "face" else None)
        adsk.fusion = native
        native_patch = patch.dict("sys.modules", {"adsk": adsk, "adsk.fusion": native,
                                                  self.fusion.__name__: self.fusion})
        native_patch.start()
        self.addCleanup(native_patch.stop)
        path = Path(__file__).parents[1] / "Partelier/partelier/tools/patterns/recipe.py"
        spec = importlib.util.spec_from_file_location(package.__name__ + "._recipe_contract_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.object(package, "fusion", self.fusion, create=True):
            spec.loader.exec_module(self.module)
        self.module.STORE = self.store
        self.module.colour_store=NS(selection_anchor=lambda selected,group:selected,read=Mock(return_value=None),apply=Mock())
        self.saved = {"version": 16, "tool": "surface_pattern", "feature_id": self.record.feature_id,
                      "settings": self.settings.to_dict(), "sources": deepcopy(self.tokens)}
        self.write_recipe(self.saved)

    def write_recipe(self, value):
        self.anchor.attributes.values[(self.module.GROUP, "recipe")] = json.dumps(value)

    def read(self):
        return self.module.read_edit_target(self.design, self.faces[0])

    def edited(self, settings=None):
        target = self.read()
        self.events.clear()
        return target, self.module.prepare_edit_pattern(self.design, target, settings or self.settings)

    def test_legacy_raised_tilt_keeps_its_original_fixed_geometry_without_saving(self):
        for version in (6,7):
            for angle in (0,20,45,60):
                with self.subTest(version=version,angle=angle):
                    legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['version']=version
                    legacy['settings'].update(pattern='grille_louver',mode='through',layout_mode='fill',grille_profile='raised',louver_angle_deg=angle)
                    if version==6:
                        legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('mount_')}
                    self.write_recipe(legacy)
                    target=self.read()
                    self.assertEqual(target.settings.louver_angle_deg,45)
                    self.assertEqual(target.recipe,legacy)
                    self.assertEqual(json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value),legacy)
                    self.assert_no_persistence()

    def test_legacy_flat_tilt_proposes_new_limit_and_explicit_rebuild_notice(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['version']=7
        legacy['settings'].update(pattern='grille_louver',mode='through',layout_mode='fill',louver_angle_deg=60)
        self.write_recipe(legacy);target=self.read()
        self.assertEqual(target.settings.louver_angle_deg,45)
        self.assertEqual(target.recipe,legacy)
        self.assertIn('existing body is unchanged',self.module.edit_notice(target))
        self.assert_no_persistence()
        for angle in (0,20,45):
            legacy['settings']['louver_angle_deg']=angle;self.write_recipe(legacy)
            self.assertEqual(self.read().settings.louver_angle_deg,angle)

    def test_legacy_and_current_angle_corruption_is_never_clamped(self):
        for version,angles in ((7,(True,'45',-1,61,10**400,float('nan'))),(8,(46,60))):
            for angle in angles:
                value=deepcopy(self.saved);value['version']=version;value['settings']['louver_angle_deg']=angle
                if version<10:value['settings']={k:v for k,v in value['settings'].items() if not k.startswith('truss_')}
                self.write_recipe(value)
                with self.subTest(version=version,angle=angle),self.assertRaises(ValueError):self.read()
                self.assert_no_persistence()

    def test_old_mounted_recipe_keeps_its_requested_border_and_explains_new_preview(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['version']=8
        legacy['settings'].update(pattern='grille_parallel',mode='through',layout_mode='fill',mount_mode='plain',border_mm=7)
        self.write_recipe(legacy);target=self.read()
        self.assertEqual(target.recipe,legacy)
        self.assertEqual(target.settings.border_mm,7)
        self.assertIn('minimum border',self.module.edit_notice(target))
        self.assert_no_persistence()

    def assert_no_persistence(self):
        self.store.create.assert_not_called()
        self.store.update.assert_not_called()
        self.assertNotIn("save", self.events)

    def test_create_saves_all_settings_and_sources_then_edit_reads_the_same_recipe(self):
        result = self.module.create_pattern(self.design, self.prepared)
        self.assertIs(result, self.anchor)
        self.store.create.assert_called_once_with(self.design, self.body, self.prepared.result_body)
        self.assertEqual(self.events, ["validate-current", "create", "save"])
        saved = json.loads(self.anchor.attributes.itemByName(self.module.GROUP, "recipe").value)
        self.assertEqual(saved, self.saved)
        self.assertEqual(len(saved["settings"]), 28)
        self.assertEqual(saved["sources"], self.tokens)
        selected = object()
        self.events.clear()
        target = self.module.read_edit_target(self.design, selected)
        self.store.read.assert_called_with(self.design, selected)
        self.assertIs(target.anchor, self.anchor)
        self.assertIs(target.record, self.record)
        self.assertEqual(target.settings, self.settings)
        self.assertEqual(target.recipe, saved)
        self.assertEqual(self.events[0], "enter-history")
        self.assertEqual(self.events[-1], "restore-history")
        self.assertFalse(self.design.historical)

    def test_missing_oversized_or_non_json_recipe_refuses_before_history_or_writes(self):
        for raw in (None, " " * 131073, "not-json", "null", "[]"):
            with self.subTest(raw=None if raw is None else raw[:20]):
                key = (self.module.GROUP, "recipe")
                if raw is None:
                    self.anchor.attributes.values.pop(key, None)
                else:
                    self.anchor.attributes.values[key] = raw
                with self.assertRaises(ValueError):
                    self.read()
                self.assertEqual(self.events, [])
                self.assert_no_persistence()
        self.store.input_scope.assert_not_called()

    def test_new_fixed_grilles_require_version_thirteen_without_reinterpreting_old_records(self):
        for shape in ('grille_deflection','grille_diffuser'):
            current=deepcopy(self.saved);current['settings']=replace(self.settings,pattern=shape,mode='through',layout_mode='fill',rotation_deg=0,offset_u_mm=0,offset_v_mm=0).to_dict()
            self.write_recipe(current);self.assertEqual(self.read().settings.pattern,shape);self.assert_no_persistence()
            legacy=deepcopy(current);legacy['version']=12;legacy['settings'].pop('grille_chamfer_mm');self.write_recipe(legacy)
            with self.assertRaisesRegex(ValueError,'legacy grille'):self.read()
            self.assert_no_persistence()
        previous=deepcopy(self.saved);previous['version']=12;previous['settings'].pop('grille_chamfer_mm');self.write_recipe(previous)
        self.assertEqual(self.read().recipe,previous);self.assert_no_persistence()

    def test_version_thirteen_chamfer_migrates_read_only_and_rebuild_saves_explicit_size(self):
        legacy=deepcopy(self.saved);legacy['version']=13;legacy['settings'].pop('grille_chamfer_mm')
        legacy['settings'].update(pattern='grille_louver',mode='through',layout_mode='fill',grille_profile='chamfer',mount_mode='plain')
        self.write_recipe(legacy);raw=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.grille_chamfer_mm,0)
        self.assertEqual(target.recipe,legacy);self.assert_no_persistence()
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,raw)
        notice=self.module.edit_notice(target)
        self.assertIn('45°',notice);self.assertIn('0.8 mm',notice)
        changed=replace(target.settings,grille_chamfer_mm=.7,mount_inset_mm=8.25)
        prepared=self.module.prepare_edit_pattern(self.design,target,changed)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16);self.assertEqual(saved['settings'],changed.to_dict())
        legacy['settings']['grille_chamfer_mm']=0;self.write_recipe(legacy)
        with self.assertRaisesRegex(ValueError,'settings'):self.read()

    def test_version_fourteen_keeps_values_and_warns_of_full_height_frame_until_rebuild(self):
        legacy=deepcopy(self.saved);legacy['version']=14
        legacy['settings'].update(pattern='grille_louver',mode='through',layout_mode='fill',
            grille_profile='chamfer',grille_chamfer_mm=.7,mount_inset_mm=8.25)
        self.write_recipe(legacy);raw=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read();self.assertEqual(target.settings.to_dict(),legacy['settings'])
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,raw)
        self.assertIn('full raised height',self.module.edit_notice(target));self.assert_no_persistence()
        prepared=self.module.prepare_edit_pattern(self.design,target,target.settings)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16);self.assertEqual(saved['settings'],legacy['settings'])

    def test_version_fifteen_mounting_stays_unchanged_until_explicit_flat_band_rebuild(self):
        legacy=deepcopy(self.saved);legacy['version']=15
        legacy['settings'].update(pattern='grille_parallel',mode='through',layout_mode='fill',
            grille_profile='chamfer',mount_mode='countersink',mount_inset_mm=8.25)
        self.write_recipe(legacy);raw=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read();self.assertEqual(target.settings.to_dict(),legacy['settings'])
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,raw)
        self.assertIn('flat screw band',self.module.edit_notice(target));self.assert_no_persistence()
        prepared=self.module.prepare_edit_pattern(self.design,target,target.settings)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16);self.assertEqual(saved['settings'],legacy['settings'])

    def test_recipe_envelope_and_exact_settings_are_strict_on_public_edit_read(self):
        malformed = []
        for key, value in (("version", True), ("version", 17), ("tool", "snap_fit"), ("feature_id", "another-pattern")):
            damaged = deepcopy(self.saved)
            damaged[key] = value
            malformed.append(damaged)
        damaged = deepcopy(self.saved)
        damaged["extra"] = "unexpected"
        malformed.append(damaged)
        damaged = deepcopy(self.saved)
        del damaged["sources"]
        malformed.append(damaged)
        for change in (lambda value: value.pop("offset_v_mm"),
                       lambda value: value.update(nozzle_mm=.4),
                       lambda value: value.update(depth_mm=True),
                       lambda value: value.update(pitch_mm=float("nan")),
                       lambda value: value.update(selection_scope="all_documents")):
            damaged = deepcopy(self.saved)
            change(damaged["settings"])
            malformed.append(damaged)
        for value in malformed:
            with self.subTest(value=value):
                self.write_recipe(value)
                with self.assertRaises(ValueError):
                    self.read()
                self.assertEqual(self.events, [])
                self.assert_no_persistence()
        self.store.input_scope.assert_not_called()

    def test_legacy_read_preserves_exact_spacing_and_migrates_only_on_rebuild(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('mount_')};legacy['settings'].pop('grille_profile');legacy['settings'].pop('grille_height_mm')
        legacy['version']=1
        legacy['settings'].pop('density');legacy['settings'].pop('size_locked');legacy['settings'].pop('louver_angle_deg')
        legacy['settings'].pop('layout_mode')
        legacy['settings'].pop('edge_mode')
        self.write_recipe(legacy)
        original=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.layout_mode,'fixed')
        self.assertEqual(target.recipe,legacy)
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,original)
        self.assert_no_persistence()
        settings=replace(target.settings,depth_mm=.8)
        prepared=self.module.prepare_edit_pattern(self.design,target,settings)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16)
        self.assertEqual(saved['settings']['layout_mode'],'fixed')
        self.assertEqual(saved['settings']['pitch_mm'],legacy['settings']['pitch_mm'])

    def test_recipe_version_must_match_its_exact_settings_schema(self):
        legacy_with_new_field=deepcopy(self.saved)
        legacy_with_new_field['version']=1
        current_without_new_field=deepcopy(self.saved)
        current_without_new_field['settings'].pop('layout_mode')
        for damaged in (legacy_with_new_field,current_without_new_field):
            with self.subTest(damaged=damaged):
                self.write_recipe(damaged)
                with self.assertRaises(ValueError):self.read()
                self.assert_no_persistence()

    def test_version_ten_truss_loads_sharp_without_writing_and_explicit_rebuild_saves_fillet(self):
        legacy=deepcopy(self.saved);legacy['version']=10
        legacy['settings']=PatternSettings(pattern='truss_warren',layout_mode='fill',web_mm=2,border_mm=3).to_dict()
        legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm')
        self.write_recipe(legacy);raw=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.truss_fillet_mm,0.0)
        self.assertEqual(target.recipe,legacy)
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,raw)
        self.assert_no_persistence()
        changed=replace(target.settings,truss_fillet_mm=1.25)
        prepared=self.module.prepare_edit_pattern(self.design,target,changed)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16);self.assertEqual(saved['settings']['truss_fillet_mm'],1.25)
        self.assertEqual(saved['sources'],legacy['sources'])

    def test_every_legacy_schema_injects_only_absent_fields_and_refuses_a_new_fillet_field(self):
        # These are the historical field additions, not permissive partial input.
        base=['pattern','mode','pitch_mm','web_mm','depth_mm','border_mm','rotation_deg',
              'offset_u_mm','offset_v_mm','selection_scope']
        additions={2:['layout_mode'],3:['edge_mode'],4:['density','size_locked'],5:['louver_angle_deg'],
                   6:['grille_profile','grille_height_mm'],7:['mount_mode','mount_screw','mount_clearance_mm',
                      'mount_head_extra_percent','mount_head_mm','mount_inset_mm'],10:['truss_bays','truss_axis'],11:['truss_fillet_mm']}
        for version in range(1,12):
            fields=base+[field for release,names in additions.items() if release<=version for field in names]
            legacy={**deepcopy(self.saved),'version':version,'settings':{field:self.saved['settings'][field] for field in fields}}
            self.write_recipe(legacy)
            before=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
            target=self.read()
            self.assertEqual(target.settings.truss_fillet_mm,0.0)
            self.assertEqual(target.settings.pattern_fillet_mm,0.0)
            self.assertEqual(target.recipe,legacy)
            for field,value in legacy['settings'].items():self.assertEqual(getattr(target.settings,field),value)
            self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,before)
            self.assert_no_persistence()
            for radius in (0,1.25):
                damaged=deepcopy(legacy);damaged['settings']['pattern_fillet_mm']=radius;self.write_recipe(damaged)
                with self.subTest(version=version,radius=radius),self.assertRaisesRegex(ValueError,'settings'):
                    self.read()
                self.assert_no_persistence()

    def test_current_fillet_schema_requires_the_field_and_preserves_its_exact_radius(self):
        current=deepcopy(self.saved);current['settings']['truss_fillet_mm']=1.75
        self.write_recipe(current);target=self.read()
        self.assertEqual(target.settings.truss_fillet_mm,1.75);self.assertEqual(target.recipe,current)
        self.assert_no_persistence()
        del current['settings']['truss_fillet_mm'];self.write_recipe(current)
        with self.assertRaisesRegex(ValueError,'settings'):self.read()
        self.assert_no_persistence()

    def test_version_eleven_preserves_the_truss_radius_and_defers_pattern_fillet_until_rebuild(self):
        legacy=deepcopy(self.saved);legacy['version']=11
        legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['settings']['truss_fillet_mm']=2.25
        self.write_recipe(legacy);raw=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.truss_fillet_mm,2.25);self.assertEqual(target.settings.pattern_fillet_mm,0)
        self.assertEqual(target.recipe,legacy);self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,raw)
        self.assert_no_persistence()
        changed=replace(target.settings,pattern_fillet_mm=.75)
        prepared=self.module.prepare_edit_pattern(self.design,target,changed)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16)
        self.assertEqual(saved['settings']['pattern_fillet_mm'],.75)
        self.assertEqual(saved['settings']['truss_fillet_mm'],2.25)

    def test_current_pattern_fillet_is_required_and_keeps_its_requested_radius(self):
        current=deepcopy(self.saved);current['settings']['pattern_fillet_mm']=1.75
        self.write_recipe(current);target=self.read()
        self.assertEqual(target.settings.pattern_fillet_mm,1.75);self.assertEqual(target.recipe,current)
        self.assert_no_persistence()
        del current['settings']['pattern_fillet_mm'];self.write_recipe(current)
        with self.assertRaisesRegex(ValueError,'settings'):self.read()
        self.assert_no_persistence()

    def test_legacy_surface_warren_id_cannot_be_enabled_by_removing_new_fields(self):
        from Partelier.partelier.tools.patterns import settings as settings_module
        supported=tuple(set((*settings_module.TILED_PATTERNS,'warren')))
        # The version guard must refuse this even when the runtime recognises
        # the new ID; a generic unknown-shape error would not prove migration.
        with patch.object(settings_module,'TILED_PATTERNS',supported):
            current=deepcopy(self.saved);current['settings']['pattern']='warren'
            self.write_recipe(current);self.assertEqual(self.read().settings.pattern,'warren')
            for version in (9,10,11):
                legacy=deepcopy(current);legacy['version']=version
                legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm')
                if version<11:legacy['settings'].pop('truss_fillet_mm')
                if version<10:
                    legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis')
                self.write_recipe(legacy)
                with self.subTest(version=version),self.assertRaisesRegex(ValueError,'legacy Warren'):
                    self.read()
                self.assert_no_persistence()

    def test_version_four_retains_all_dimensions_and_migrates_only_on_rebuild(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('mount_')};legacy['settings'].pop('grille_profile');legacy['settings'].pop('grille_height_mm');legacy['version']=4
        legacy['settings'].pop('louver_angle_deg')
        self.write_recipe(legacy)
        before=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings,self.settings)
        self.assertEqual(target.settings.louver_angle_deg,45)
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,before)
        prepared=self.module.prepare_edit_pattern(self.design,target,target.settings)
        self.module.rebuild_pattern(self.design,target,prepared)
        saved=json.loads(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value)
        self.assertEqual(saved['version'],16)
        self.assertEqual(saved['settings']['louver_angle_deg'],45)
        for key,value in legacy['settings'].items():self.assertEqual(saved['settings'][key],value)

    def test_version_three_injects_auto_defaults_without_rewriting_saved_settings(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('mount_')};legacy['settings'].pop('grille_profile');legacy['settings'].pop('grille_height_mm');legacy['version']=3
        legacy['settings'].pop('density');legacy['settings'].pop('size_locked');legacy['settings'].pop('louver_angle_deg')
        self.write_recipe(legacy)
        before=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.density,'balanced')
        self.assertFalse(target.settings.size_locked)
        self.assertEqual(target.settings.edge_mode,self.settings.edge_mode)
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,before)
        self.assert_no_persistence()

    def test_version_two_restores_whole_cells_without_rewriting_its_recipe(self):
        legacy=deepcopy(self.saved);legacy['settings'].pop('truss_bays');legacy['settings'].pop('truss_axis');legacy['settings'].pop('truss_fillet_mm');legacy['settings'].pop('grille_chamfer_mm');legacy['settings'].pop('pattern_fillet_mm');legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('mount_')};legacy['settings'].pop('grille_profile');legacy['settings'].pop('grille_height_mm');legacy['version']=2;legacy['settings'].pop('edge_mode')
        legacy['settings'].pop('density');legacy['settings'].pop('size_locked');legacy['settings'].pop('louver_angle_deg')
        self.write_recipe(legacy)
        before=self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value
        target=self.read()
        self.assertEqual(target.settings.edge_mode,'whole')
        self.assertEqual(target.settings.pitch_mm,self.settings.pitch_mm)
        self.assertEqual(self.anchor.attributes.itemByName(self.module.GROUP,'recipe').value,before)
        self.assert_no_persistence()

    def test_invalid_opaque_source_lists_are_refused_before_history_resolution(self):
        malformed = [None, {}, {**self.tokens, "unexpected": "token"}]
        malformed += [{"body": body, "faces": self.tokens["faces"]} for body in ("", 123, "b" * 16385)]
        malformed += [{"body": self.tokens["body"], "faces": faces}
                      for faces in ([], "face", [None], [""], ["f" * 16385], ["same", "same"],
                                    [str(index) for index in range(101)])]
        for sources in malformed:
            with self.subTest(sources=str(sources)[:80]):
                self.write_recipe({**self.saved, "sources": sources})
                with self.assertRaises(ValueError):
                    self.read()
                self.assertEqual(self.events, [])
                self.assert_no_persistence()
        self.design.findEntityByToken.assert_not_called()

    def test_missing_split_invalid_or_foreign_source_restores_historical_scope(self):
        other_body = Entity("other-body")
        invalid_face = Entity("invalid-face", "face", self.body)
        invalid_face.isValid = False
        cases = [(self.tokens["body"], []), (self.tokens["body"], [self.body, other_body]),
                 (self.tokens["body"], [other_body]), (self.tokens["faces"][0], [invalid_face]),
                 (self.tokens["faces"][0], [Entity("foreign-face", "face", other_body)]),
                 (self.tokens["faces"][0], [self.body])]
        for token, resolved in cases:
            with self.subTest(token=token, resolved=resolved):
                previous = self.entities[token]
                self.entities[token] = resolved
                self.events.clear()
                with self.assertRaises(ValueError):
                    self.read()
                self.assertEqual(self.events[0], "enter-history")
                self.assertEqual(self.events[-1], "restore-history")
                self.assertFalse(self.design.historical)
                self.assert_no_persistence()
                self.entities[token] = previous

    def test_prepare_edit_uses_original_faces_and_retains_original_recipe_for_validation(self):
        changed = replace(self.settings, pattern="diamond", mode="emboss", depth_mm=.8)
        target, prepared = self.edited(changed)
        self.fusion.prepare_pattern.assert_called_once_with(self.design, self.faces, changed, _historical=True)
        self.assertIs(prepared.record, self.record)
        self.assertEqual(prepared.saved_recipe, self.saved)
        self.assertEqual(prepared.settings, changed)
        self.assertEqual(target.settings, self.settings)
        self.assertEqual(target.recipe["settings"], self.settings.to_dict())
        self.assertEqual(self.events[0], "enter-history")
        self.assertEqual(self.events[-2:], ["prepare-historical", "restore-history"])
        self.assert_no_persistence()

    def test_changed_saved_recipe_or_scope_refuses_edit_before_geometry_work(self):
        target = self.read()
        for invalid_target, settings in ((object(), self.settings),
                                         (target, replace(self.settings, selection_scope="body"))):
            with self.subTest(target=invalid_target, settings=settings):
                self.events.clear()
                with self.assertRaises(ValueError):
                    self.module.prepare_edit_pattern(self.design, invalid_target, settings)
                self.assertEqual(self.events, [])
        self.write_recipe({**self.saved, "settings": replace(self.settings, pitch_mm=10).to_dict()})
        with self.assertRaisesRegex(ValueError, "changed"):
            self.module.prepare_edit_pattern(self.design, target, self.settings)
        self.assertEqual(self.events, [])
        self.fusion.prepare_pattern.assert_not_called()
        self.assert_no_persistence()

    def test_failed_edit_computation_restores_history_without_accepting_result(self):
        target = self.read()
        self.events.clear()
        self.fusion.prepare_pattern.side_effect = ValueError("surface offset failed")
        with self.assertRaisesRegex(ValueError, "surface offset"):
            self.module.prepare_edit_pattern(self.design, target, self.settings)
        self.assertFalse(self.design.historical)
        self.assertEqual(self.events[-1], "restore-history")
        self.assert_no_persistence()

    def test_preview_freshness_checks_new_source_now_and_edit_source_before_owned_feature(self):
        self.module.validate_preview_sources(self.prepared)
        self.assertEqual(self.events, ["validate-current"])
        self.fusion.validate_sources.assert_called_once_with(self.prepared)
        _, prepared = self.edited()
        self.events.clear()
        self.module.validate_preview_sources(prepared)
        self.assertEqual(self.events, ["enter-history", "validate-historical", "restore-history"])
        self.fusion.validate_sources.assert_called_with(prepared, _historical=True)
        self.assertFalse(self.design.historical)
        self.assert_no_persistence()

    def test_source_or_history_restore_failure_prevents_rebuild_writes(self):
        target, prepared = self.edited()
        self.events.clear()
        self.fusion.validate_sources.side_effect = ValueError("source changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.module.rebuild_pattern(self.design, target, prepared)
        self.assertEqual(self.events[-1], "restore-history")
        self.assert_no_persistence()
        self.fusion.validate_sources.side_effect = None
        self.scope_exit_error = ValueError("history marker could not be restored")
        self.events.clear()
        with self.assertRaisesRegex(ValueError, "history marker"):
            self.module.rebuild_pattern(self.design, target, prepared)
        self.assert_no_persistence()

    def test_changed_recipe_invalidates_cached_edit_preview_before_history_or_rebuild(self):
        target, prepared = self.edited()
        self.events.clear()
        self.fusion.validate_sources.reset_mock()
        self.write_recipe({**self.saved, "settings": replace(self.settings, border_mm=3).to_dict()})
        with self.assertRaisesRegex(ValueError, "changed"):
            self.module.rebuild_pattern(self.design, target, prepared)
        self.assertEqual(self.events, [])
        self.fusion.validate_sources.assert_not_called()
        self.assert_no_persistence()

    def test_rebuild_reuses_reviewed_detached_shape_only_after_historical_validation_restores(self):
        changed = replace(self.settings, mode="emboss", depth_mm=.8)
        target, prepared = self.edited(changed)
        self.events.clear()
        self.fusion.prepare_pattern.reset_mock()
        result = self.module.rebuild_pattern(self.design, target, prepared)
        self.assertIs(result, self.anchor)
        self.assertEqual(self.events, ["enter-history", "validate-historical", "restore-history", "update", "save"])
        self.store.update.assert_called_once_with(self.design, self.record, prepared.result_body)
        self.store.create.assert_not_called()
        self.fusion.prepare_pattern.assert_not_called()
        saved = json.loads(self.anchor.attributes.itemByName(self.module.GROUP, "recipe").value)
        self.assertEqual(saved["settings"], changed.to_dict())
        self.assertEqual(saved["sources"], self.tokens)
        self.assertEqual(saved["feature_id"], self.record.feature_id)
        self.events.clear()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.module.rebuild_pattern(self.design, target, prepared)
        self.assertEqual(self.events, [])
        self.assertEqual(self.store.update.call_count, 1, "old previews cannot overwrite a completed rebuild")

    def test_wrong_design_or_wrong_edit_ownership_cannot_persist_cached_results(self):
        with self.assertRaisesRegex(ValueError, "current new-pattern"):
            self.module.create_pattern(object(), self.prepared)
        target, prepared = self.edited()
        self.events.clear()
        wrong_record = NS(anchor=self.anchor, feature_id="another-record", recipe={'version':1})
        for design, invalid_target in ((object(), target), (self.design, object()),
                                      (self.design, replace(target, record=wrong_record)),
                                      (self.design, replace(target, recipe={**target.recipe, "tool": "another-tool"}))):
            with self.subTest(design=design, target=invalid_target), self.assertRaisesRegex(ValueError, "Reopen Edit"):
                self.module.rebuild_pattern(design, invalid_target, prepared)
        with self.assertRaisesRegex(ValueError, "current new-pattern"):
            self.module.create_pattern(self.design, prepared)
        self.assert_no_persistence()

    def test_new_source_freshness_failure_prevents_create(self):
        self.fusion.validate_sources.side_effect = ValueError("source changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.module.create_pattern(self.design, self.prepared)
        self.assert_no_persistence()

    def test_failed_attribute_save_signals_caller_rollback_after_single_store_operation(self):
        self.anchor.attributes.reject_write = True
        with self.assertRaisesRegex(ValueError, "roll back"):
            self.module.create_pattern(self.design, self.prepared)
        self.assertEqual(self.events, ["validate-current", "create", "save"])
        self.assertEqual(self.store.create.call_count, 1)
        self.store.update.assert_not_called()
        self.assertEqual(json.loads(self.anchor.attributes.itemByName(self.module.GROUP, "recipe").value), self.saved)

    def test_invalid_generated_recipe_cannot_be_saved_after_store_write(self):
        prepared = replace(self.prepared, source_tokens={"body": self.body.entityToken, "faces": []})
        with self.assertRaisesRegex(ValueError, "references"):
            self.module.create_pattern(self.design, prepared)
        self.assertEqual(self.events, ["validate-current", "create"])
        self.assertEqual(self.store.create.call_count, 1)
        self.assertNotIn("save", self.events, "invalid metadata must abort the caller-owned transaction")

    def test_generated_recipe_size_must_fit_the_same_limit_used_by_edit(self):
        tokens={"body":"body", "faces":[str(index)+"x"*16300 for index in range(10)]}
        prepared=replace(self.prepared, source_tokens=tokens)
        with self.assertRaisesRegex(ValueError,"too large"):
            self.module.create_pattern(self.design,prepared)
        self.assertEqual(self.events,["validate-current","create"])
        self.assertEqual(self.store.create.call_count,1)
        self.assertNotIn("save",self.events)


if __name__ == "__main__":
    unittest.main()
