"""Native-command ownership checks with fake events, not Fusion validation."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge.settings import HingeSettings


class Event:
    def __init__(self):
        self.handlers = []
        self.fail_remove = False

    def add(self, handler):
        self.handlers.append(handler)

    def remove(self, handler):
        if self.fail_remove:
            raise RuntimeError("Simulated event removal failure")
        self.handlers.remove(handler)

    def fire(self, args):
        for handler in list(self.handlers):
            handler.notify(args)


class Input:
    def __init__(self, identity, value=None):
        self.id = identity
        self.value = value
        self.text = ""
        self.isValidExpression = True
        self.isEnabled = True
        self.entities = []
        self.filters = []

    @property
    def expression(self):
        return f"{self.value * 10.0} mm"

    @expression.setter
    def expression(self, value):
        self.value = float(value.removesuffix(" mm")) / 10.0
        self.isValidExpression = True

    @property
    def selectionCount(self):
        return len(self.entities)

    def addSelectionFilter(self, value):
        self.filters.append(value)

    def setSelectionLimits(self, minimum, maximum):
        self.limits = (minimum, maximum)

    def selection(self, index):
        return SimpleNamespace(entity=self.entities[index])


class Inputs:
    def __init__(self):
        self.items = {}

    def itemById(self, identity):
        return self.items.get(identity)

    def _add(self, identity, value=None):
        result = Input(identity, value)
        self.items[identity] = result
        return result

    def addTextBoxCommandInput(self, identity, name, text, rows, readonly):
        result = self._add(identity)
        result.text = text
        return result

    def addSelectionInput(self, identity, name, prompt):
        result = self._add(identity)
        result.name = name
        result.prompt = prompt
        return result

    def addValueInput(self, identity, name, units, expression):
        result = self._add(identity)
        result.name = name
        result.expression = expression
        return result

    def addIntegerSpinnerCommandInput(self, identity, name, minimum, maximum, step, value):
        result = self._add(identity, value)
        result.name = name
        result.limits = (minimum, maximum, step)
        return result

    def addBoolValueInput(self, identity, name, checkbox, resource, value):
        return self._add(identity, value)


class Command:
    def __init__(self):
        self.commandInputs = Inputs()
        for name in ("inputChanged", "validateInputs", "executePreview", "execute", "destroy"):
            setattr(self, name, Event())


class Definitions:
    def __init__(self):
        self.items = {}
        self.execute_hook = None

    def itemById(self, identity):
        return self.items.get(identity)

    def addButtonDefinition(self, identity, title, description):
        definition = SimpleNamespace(
            id=identity, isValid=True, commandCreated=Event(), execute=Mock(return_value=True),
        )

        def delete():
            definition.isValid = False
            self.items.pop(identity)

        definition.deleteMe = delete
        self.items[identity] = definition
        if self.execute_hook is not None and identity == "sktech_partelier_hinge_compute_16e681a4":
            definition.execute.side_effect = lambda: self.execute_hook(definition)
        return definition


class HingeCommandContractTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        capture_patch=patch('Partelier.partelier.operations.capture')
        self.capture_operation=capture_patch.start();self.addCleanup(capture_patch.stop)
        self.design = SimpleNamespace(isValid=True,timeline=SimpleNamespace(count=0))
        self.ui = SimpleNamespace(commandDefinitions=Definitions(), activeCommand="unrelated", commandStarting=Event(), commandTerminated=Event())
        self.ui.terminateActiveCommand = Mock()
        self.logs = []
        application = SimpleNamespace(
            userInterface=self.ui, activeProduct=self.design, log=self.logs.append,
            documentDeactivating=Event(),
        )
        core = ModuleType("adsk.core")
        for name in ("CommandCreatedEventHandler", "InputChangedEventHandler",
                     "ValidateInputsEventHandler", "CommandEventHandler", "ApplicationCommandEventHandler", "DocumentEventHandler", "CustomEventHandler"):
            setattr(core, name, object)
        core.Application = SimpleNamespace(get=lambda: application)
        core.ValueInput = SimpleNamespace(createByString=lambda value: value)
        fusion = ModuleType("adsk.fusion")
        fusion.Design = SimpleNamespace(cast=lambda value: value if value is self.design else None)
        adsk = ModuleType("adsk")
        adsk.core = core
        adsk.fusion = fusion
        adapter_name = "Partelier.partelier.tools.hinge.fusion"
        adapter = ModuleType(adapter_name)
        for name in ("capture_preview_sources", "validate_preview_sources", "create_hinge", "prepare_hinge", "prepare_edit_hinge", "preview_hinge", "preview_hide_bodies", "source_bodies", "read_edit_target", "rebuild_hinge"):
            setattr(adapter, name, Mock())
        adapter.preview_hide_bodies.return_value = ()
        adapter.source_bodies.return_value = ()
        self.adapter = adapter
        self.prepared = SimpleNamespace(settings=HingeSettings())
        adapter.prepare_hinge.return_value = self.prepared

        def requested_preparation(*arguments, **keywords):
            self.prepared.settings = arguments[4]
            return self.prepared

        adapter.prepare_hinge.side_effect = requested_preparation

        def requested_edit_preparation(design, target, settings, **keywords):
            self.prepared.settings = settings
            return self.prepared

        adapter.prepare_edit_hinge.return_value = self.prepared
        adapter.prepare_edit_hinge.side_effect = requested_edit_preparation
        self.graphics = []

        def new_graphics(prepared):
            group = SimpleNamespace(isValid=True)
            group.deleteMe = Mock(side_effect=lambda: setattr(group, "isValid", False))
            self.graphics.append(group)
            return group

        adapter.preview_hinge.side_effect = new_graphics
        path = Path(__file__).parents[1] / "Partelier/partelier/tools/hinge/command.py"
        spec = importlib.util.spec_from_file_location(
            "Partelier.partelier.tools.hinge._command_contract_test", path,
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {
            "adsk": adsk, "adsk.core": core, "adsk.fusion": fusion, adapter_name: adapter,
        }):
            spec.loader.exec_module(self.module)
        for helper in ("run_compute_command", "terminate_compute_command", "drain_native_preview_events"):
            if not hasattr(self, helper):
                setattr(self, helper, getattr(HingeCommandContractTests, helper).__get__(self))
        self.application = application
        self.custom_events = {}
        self.custom_queue = []
        self.compute_commands = []
        self.compute_order = []
        self.compute_preview_args = []
        self.active_compute = None
        self.inside_created = False
        def register_event(identity):
            event = self.custom_events.setdefault(identity, Event())
            event.eventId = identity
            return event

        application.registerCustomEvent = register_event
        application.unregisterCustomEvent = lambda identity: self.custom_events.pop(identity, None)
        application.fireCustomEvent = lambda identity, information: self.custom_queue.append((identity, information)) or True
        self.ui.commandDefinitions.execute_hook = self.run_compute_command
        self.ui.terminateActiveCommand.side_effect = self.terminate_compute_command
        preview_globals = self.module.NativePreviewRunner.__init__.__globals__
        preview_patch = patch.dict(preview_globals, {"adsk": adsk})
        preview_patch.start()
        self.addCleanup(preview_patch.stop)
        self.owner = self.module.HingeCommands()
        self.owner.start()

    def run_compute_command(self, definition):
        if definition.id != self.module.PREVIEW_COMMAND_ID:
            return True
        command = Command()
        command.isValid = True
        self.compute_commands.append(command)
        self.active_compute = command
        self.ui.activeCommand = definition.id

        def calculate():
            self.assertFalse(self.inside_created, "never compute from CommandCreated")
            self.compute_order.append("preview")
            args = SimpleNamespace(isValidResult=True)
            self.compute_preview_args.append(args)
            command.executePreview.fire(args)
            return True

        def execute(terminate):
            self.assertFalse(self.inside_created, "never execute from CommandCreated")
            self.assertTrue(terminate)
            self.compute_order.append("rollback")
            self.compute_order.append("execute")
            command.execute.fire(SimpleNamespace(executeFailed=False))
            self.compute_order.append("destroy")
            command.destroy.fire(SimpleNamespace())
            command.isValid = False
            self.active_compute = None
            self.ui.activeCommand = "SelectCommand"
            self.ui.commandTerminated.fire(SimpleNamespace(commandId=definition.id))
            return True

        command.doExecutePreview = Mock(side_effect=calculate)
        command.doExecute = Mock(side_effect=execute)
        self.inside_created = True
        try:
            definition.commandCreated.fire(SimpleNamespace(command=command))
        finally:
            self.inside_created = False
        if command.isAutoExecute:
            command.doExecute(True)
        return True

    def terminate_compute_command(self):
        command = self.active_compute
        if command is not None and command.isValid:
            self.compute_order.append("abort")
            command.destroy.fire(SimpleNamespace())
            command.isValid = False
            self.active_compute = None
            self.ui.activeCommand = "SelectCommand"

    def drain_native_preview_events(self):
        for _ in range(30):
            if not self.custom_queue:
                return
            identity, information = self.custom_queue.pop(0)
            event = self.custom_events.get(identity)
            if event is not None:
                event.fire(SimpleNamespace(additionalInfo=information))
        self.fail("Native preview driver did not drain.")

    def tearDown(self):
        self.owner.stop()

    def open_command(self, editing=False, settings=None):
        if editing:
            self.owner.launch_edit()
            identity = self.module.EDIT_COMMAND_ID
        else:
            self.owner.launch_create(settings)
            identity = self.module.CREATE_COMMAND_ID
        command = Command()
        self.ui.commandDefinitions.itemById(identity).commandCreated.fire(SimpleNamespace(command=command))
        self.assertEqual(len(self.owner._sessions), 1)
        return command, self.owner._sessions[0]

    def select_sources(self, session):
        for name in ("face_a", "face_b", "axis_edge"):
            session.inputs.itemById(name).entities = [SimpleNamespace(isValid=True, name=name)]

    def test_queued_launch_retains_seed_dimensions_until_created_and_converts_cm_once(self):
        command, session = self.open_command(settings={"length_mm": 42.0})
        self.select_sources(session)
        self.assertEqual(session.inputs.itemById("length_mm").value, 4.2)
        self.assertEqual(session._settings().length_mm, 42.0)
        self.assertEqual(session._settings().axis_offset_mm, 4.0)
        self.assertIsNone(self.owner._pending_settings)
        self.assertFalse(command.isExecutedWhenPreEmpted)

    def test_layout_launch_has_separate_hinge_count_and_zero_inclusive_margins(self):
        command, session = self.open_command(settings={
            "length_mm": 12, "hinge_count": 3, "knuckle_count": 5,
            "start_margin_mm": 10, "end_margin_mm": 15,
        })
        self.select_sources(session)
        count = session.inputs.itemById("hinge_count")
        self.assertEqual(count.name, "Number of hinges")
        self.assertEqual(count.limits, (1, 20, 1))
        self.assertEqual(session.inputs.itemById("knuckle_count").name, "Knuckles per hinge (odd)")
        self.assertEqual(session.inputs.itemById("length_mm").name, "Length per hinge")
        self.assertEqual(session.inputs.itemById("start_margin_mm").value, 1)
        self.assertEqual(session.inputs.itemById("end_margin_mm").value, 1.5)
        for key in ("start_margin_mm", "end_margin_mm"):
            control = session.inputs.itemById(key)
            self.assertEqual(control.minimumValue, 0)
            self.assertTrue(control.isMinimumInclusive)
        expected = session._settings()
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], expected)
        status = session.inputs.itemById("status").text
        self.assertIn("3 hinges, 12 mm each", status)
        self.assertIn("End margins and equal gaps applied", status)
        self.assertIn("joins the hinge into the two selected bodies", status)
        execute = SimpleNamespace(executeFailed=False)
        command.execute.fire(execute)
        self.assertFalse(execute.executeFailed)
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], expected)
        self.adapter.create_hinge.assert_called_once_with(self.design, self.prepared)

    def test_count_and_each_margin_invalidate_preview_and_allow_zero_margins(self):
        command, session = self.open_command(settings={"length_mm": 12})
        self.select_sources(session)
        args = SimpleNamespace(isValidResult=True)
        command.executePreview.fire(args)
        for key, value in (("hinge_count", 3), ("start_margin_mm", 1.0), ("end_margin_mm", 1.5)):
            previous = self.graphics[-1]
            generation = session.generation
            session.inputs.itemById(key).value = value
            session.changed(key)
            self.assertFalse(previous.isValid)
            self.assertEqual(session.generation, generation + 1)
            command.executePreview.fire(args)
        latest = self.adapter.prepare_hinge.call_args.args[4]
        self.assertEqual(latest.hinge_count, 3)
        self.assertEqual(latest.start_margin_mm, 10)
        self.assertEqual(latest.end_margin_mm, 15)
        for key in ("start_margin_mm", "end_margin_mm"):
            session.inputs.itemById(key).value = 0
            session.changed(key)
        self.assertTrue(session.validate())
        self.assertEqual(session._settings().start_margin_mm, 0)
        self.assertEqual(session._settings().end_margin_mm, 0)

    def test_invalid_layout_dimensions_block_geometry_before_creation(self):
        command, session = self.open_command()
        self.select_sources(session)
        for key, value in (("hinge_count", 0), ("hinge_count", 21), ("hinge_count", 1.5),
                           ("start_margin_mm", -.1), ("end_margin_mm", -.1)):
            baseline = session.inputs.itemById(key).value
            session.inputs.itemById(key).value = value
            execute = SimpleNamespace(executeFailed=False)
            command.execute.fire(execute)
            self.assertTrue(execute.executeFailed)
            self.adapter.prepare_hinge.assert_not_called()
            self.adapter.create_hinge.assert_not_called()
            session.inputs.itemById(key).value = baseline

    def test_edit_loads_and_rebuilds_hinge_count_and_margins_without_resetting_other_dimensions(self):
        command, session = self.open_command(editing=True)
        session.inputs.itemById("edit_target").entities = [SimpleNamespace(isValid=True)]
        settings = HingeSettings(length_mm=12, hinge_count=3, start_margin_mm=10,
                                 end_margin_mm=15, knuckle_count=7, axis_offset_mm=6)
        target = SimpleNamespace(settings=settings, face_a="a", face_b="b", axis_edge="edge")
        self.adapter.read_edit_target.return_value = target
        session.changed("edit_target")
        self.assertEqual(session._settings(), settings)
        session.inputs.itemById("hinge_count").value = 2
        session.changed("hinge_count")
        session.inputs.itemById("end_margin_mm").value = 2
        session.changed("end_margin_mm")
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        execute = SimpleNamespace(executeFailed=False)
        command.execute.fire(execute)
        self.assertFalse(execute.executeFailed)
        self.adapter.prepare_hinge.assert_not_called()
        self.assertIs(self.adapter.prepare_edit_hinge.call_args.args[1], target)
        latest = self.adapter.prepare_edit_hinge.call_args.args[2]
        self.assertEqual(latest.hinge_count, 2)
        self.assertEqual(latest.length_mm, 12)
        self.assertEqual(latest.start_margin_mm, 10)
        self.assertEqual(latest.end_margin_mm, 20)
        self.assertEqual(latest.knuckle_count, 7)
        self.assertEqual(latest.axis_offset_mm, 6)
        self.assertEqual(target.settings, settings)
        self.adapter.rebuild_hinge.assert_called_once_with(self.design, target, self.prepared)

    def test_native_launch_preserves_html_support_choice_without_a_second_control(self):
        for profile in ("tangent", "flat"):
            with self.subTest(profile=profile):
                command, session = self.open_command(settings={"web_profile": profile})
                self.assertEqual(session._settings().web_profile, profile)
                session.inputs.itemById("length_mm").value = 4.2
                self.assertEqual(session._settings().web_profile, profile)
                command.destroy.fire(SimpleNamespace())

    def test_native_edit_retains_saved_flat_support_when_loading_old_result(self):
        _, session = self.open_command(editing=True)
        session.inputs.itemById("edit_target").entities = [SimpleNamespace(isValid=True)]
        saved = HingeSettings(web_profile="flat", length_mm=38)
        self.adapter.read_edit_target.return_value = SimpleNamespace(
            settings=saved, face_a="a", face_b="b", axis_edge="edge")
        session.changed("edit_target")
        self.assertEqual(session._settings(), saved)
        session.inputs.itemById("length_mm").value = 4.2
        self.assertEqual(session._settings().web_profile, "flat")

    def test_default_mode_preserves_gapped_fixture_and_labels_coincident_edge_selection(self):
        _, session = self.open_command()
        self.assertFalse(session.inputs.itemById("split_seam").value)
        self.assertTrue(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertFalse(session.inputs.itemById("seam_clearance_mm").isEnabled)
        self.assertEqual(session._settings().seam_clearance_mm, .3)
        reference = session.inputs.itemById("axis_edge")
        self.assertEqual(reference.name, "Reference edge")
        self.assertIn("coincident edge on B", reference.prompt)
        self.assertIn("same outward direction", session.inputs.itemById("scope").text)

    def test_split_launch_passes_mode_and_clearance_without_overwriting_saved_offset(self):
        command, session = self.open_command(settings={
            "split_seam": True, "seam_clearance_mm": .6, "axis_offset_mm": 7,
        })
        self.select_sources(session)
        self.assertFalse(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertTrue(session.inputs.itemById("seam_clearance_mm").isEnabled)
        settings = session._settings()
        self.assertTrue(settings.split_seam)
        self.assertAlmostEqual(settings.seam_clearance_mm, .6)
        self.assertEqual(settings.axis_offset_mm, 7)
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], settings)

    def test_detected_touching_seam_syncs_only_mode_without_invalidating_or_resetting_dimensions(self):
        command, session = self.open_command(settings={
            "length_mm": 46, "axis_offset_mm": 7, "seam_clearance_mm": .6,
            "knuckle_count": 7, "include_pin": False,
        })
        self.select_sources(session)
        requested = session._settings()
        effective = HingeSettings.from_dict({**requested.to_dict(), "split_seam": True})
        self.prepared.settings = effective
        self.adapter.prepare_hinge.side_effect = None
        generation = session.generation
        sync_controls = session._sync_mode_controls

        def sync_with_native_change_notification():
            self.assertTrue(session.loading_settings)
            session.changed("split_seam")
            sync_controls()

        with patch.object(session, "_sync_mode_controls", side_effect=sync_with_native_change_notification):
            command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertTrue(session.inputs.itemById("split_seam").value)
        self.assertFalse(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertTrue(session.inputs.itemById("seam_clearance_mm").isEnabled)
        self.assertEqual(session._settings(), effective)
        self.assertEqual(session.generation, generation)
        self.assertEqual(session.preview_generation, generation)
        self.assertFalse(session.loading_settings)
        status = session.inputs.itemById("status").text
        self.assertIn("Touching seam auto-detected", status)
        self.assertIn("Axis centered", status)
        self.assertIn("clearance is applied to the selected bodies when created", status)
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertEqual(self.adapter.prepare_hinge.call_count, 1)
        execute = SimpleNamespace(executeFailed=False)
        command.execute.fire(execute)
        self.assertFalse(execute.executeFailed)
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], effective)
        self.adapter.create_hinge.assert_called_once_with(self.design, self.prepared)

    def test_edit_retains_auto_detected_split_mode_for_fresh_rebuild(self):
        command, session = self.open_command(editing=True)
        selected = SimpleNamespace(isValid=True)
        session.inputs.itemById("edit_target").entities = [selected]
        original = HingeSettings(length_mm=42, axis_offset_mm=7, seam_clearance_mm=.6)
        target = SimpleNamespace(settings=original, face_a="A", face_b="B", axis_edge="edge")
        self.adapter.read_edit_target.return_value = target
        session.changed("edit_target")
        session.inputs.itemById("length_mm").value = 4.6
        session.changed("length_mm")
        effective = HingeSettings.from_dict({**session._settings().to_dict(), "split_seam": True})
        self.prepared.settings = effective
        self.adapter.prepare_edit_hinge.side_effect = None
        generation = session.generation
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertEqual(session.generation, generation)
        self.assertEqual(session._settings(), effective)
        self.assertIn("auto-detected", session.inputs.itemById("status").text)
        execute = SimpleNamespace(executeFailed=False)
        command.execute.fire(execute)
        self.assertFalse(execute.executeFailed)
        self.assertTrue(self.adapter.prepare_edit_hinge.call_args.args[2].split_seam)
        self.assertEqual(target.settings, original)
        self.assertFalse(target.settings.split_seam)
        self.adapter.rebuild_hinge.assert_called_once_with(self.design, target, self.prepared)

    def test_prepared_mode_sync_never_disables_manual_split_or_accepts_unvalidated_settings(self):
        _, session = self.open_command(settings={"split_seam": True})
        manual = session._settings()
        session._sync_prepared_mode(manual, SimpleNamespace(settings=HingeSettings()))
        self.assertTrue(session._settings().split_seam)
        self.assertFalse(session.auto_split_detected)
        session.inputs.itemById("split_seam").value = False
        for invalid in (None, SimpleNamespace(split_seam=True), {"split_seam": True}):
            session._sync_prepared_mode(HingeSettings(), SimpleNamespace(settings=invalid))
            self.assertFalse(session.inputs.itemById("split_seam").value)
        self.assertFalse(session.auto_split_detected)

    def test_split_mode_and_clearance_changes_invalidate_preview_and_restore_offset_control(self):
        command, session = self.open_command(settings={"axis_offset_mm": 7})
        self.select_sources(session)
        args = SimpleNamespace(isValidResult=True)
        command.executePreview.fire(args)
        session.inputs.itemById("split_seam").value = True
        session.changed("split_seam")
        self.assertFalse(self.graphics[0].isValid)
        self.assertFalse(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertIn("axis stays on the seam", session.inputs.itemById("status").text)
        command.executePreview.fire(args)
        session.inputs.itemById("seam_clearance_mm").value = .045
        session.changed("seam_clearance_mm")
        self.assertFalse(self.graphics[1].isValid)
        self.assertAlmostEqual(session._settings().seam_clearance_mm, .45)
        session.inputs.itemById("split_seam").value = False
        session.changed("split_seam")
        self.assertTrue(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertFalse(session.inputs.itemById("seam_clearance_mm").isEnabled)
        self.assertEqual(session._settings().axis_offset_mm, 7)

    def test_switching_mode_repairs_only_invalid_now_disabled_values(self):
        _, session = self.open_command()
        axis = session.inputs.itemById("axis_offset_mm")
        axis.isValidExpression = False
        session.inputs.itemById("split_seam").value = True
        session.changed("split_seam")
        self.assertTrue(axis.isValidExpression)
        self.assertEqual(session._settings().axis_offset_mm, HingeSettings().axis_offset_mm)
        seam = session.inputs.itemById("seam_clearance_mm")
        seam.value = 0
        session.inputs.itemById("split_seam").value = False
        session.changed("split_seam")
        self.assertEqual(session._settings().seam_clearance_mm, HingeSettings().seam_clearance_mm)

    def test_invalid_active_seam_clearance_prevents_model_writes(self):
        command, session = self.open_command(settings={"split_seam": True})
        self.select_sources(session)
        session.inputs.itemById("seam_clearance_mm").isValidExpression = False
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertTrue(args.executeFailed)
        self.assertIn("split seam clearance", args.executeFailedMessage)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_invalid_launch_never_queues_native_execution(self):
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        for values in ({"unknown": 1}, {"knuckle_count": 4}, {"length_mm": "40"},
                       {"split_seam": 1}, {"seam_clearance_mm": 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.owner.launch_create(values)
        definition.execute.assert_not_called()

    def test_double_launch_cannot_replace_dimensions_of_a_command_still_opening(self):
        self.owner.launch_create({"length_mm": 42})
        with self.assertRaises(ValueError):
            self.owner.launch_create({"length_mm": 44})
        with self.assertRaises(ValueError):
            self.owner.launch_edit()
        self.assertEqual(self.owner._pending_settings.length_mm, 42)
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        self.assertEqual(definition.execute.call_count, 1)

    def test_queued_edit_also_blocks_another_launch_until_created(self):
        self.owner.launch_edit()
        with self.assertRaises(ValueError):
            self.owner.launch_edit()
        with self.assertRaises(ValueError):
            self.owner.launch_create()
        definition = self.ui.commandDefinitions.itemById(self.module.EDIT_COMMAND_ID)
        self.assertEqual(definition.execute.call_count, 1)

    def test_rejected_native_launch_does_not_lock_future_attempts(self):
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        definition.execute.return_value = False
        with self.assertRaises(RuntimeError):
            self.owner.launch_create({"length_mm": 42})
        self.assertFalse(self.owner._opening)
        self.assertIsNone(self.owner._pending_settings)
        definition.execute.return_value = True
        self.assertTrue(self.owner.launch_create({"length_mm": 44}))

    def test_validation_does_not_build_geometry_or_resolve_recipes(self):
        command, session = self.open_command()
        args = SimpleNamespace(areInputsValid=True)
        command.validateInputs.fire(args)
        self.assertFalse(args.areInputsValid)
        self.select_sources(session)
        for _ in range(3):
            command.validateInputs.fire(args)
            self.assertTrue(args.areInputsValid)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.read_edit_target.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_preview_is_disposable_cached_until_input_change_and_never_a_persistent_result(self):
        command, session = self.open_command()
        self.select_sources(session)
        args = SimpleNamespace(isValidResult=True)
        command.executePreview.fire(args)
        command.executePreview.fire(args)
        self.assertFalse(args.isValidResult)
        self.assertEqual(self.adapter.prepare_hinge.call_count, 1)
        first = self.graphics[0]
        session.changed("status")
        self.assertTrue(first.isValid)
        session.changed("length_mm")
        self.assertFalse(first.isValid)
        command.executePreview.fire(args)
        self.assertEqual(self.adapter.prepare_hinge.call_count, 2)
        command.destroy.fire(SimpleNamespace())
        self.assertFalse(self.graphics[-1].isValid)
        self.assertEqual(self.owner._sessions, [])
        self.adapter.create_hinge.assert_not_called()
        self.adapter.rebuild_hinge.assert_not_called()

    def test_execute_revalidates_geometry_instead_of_persisting_cached_preview(self):
        command, session = self.open_command()
        self.select_sources(session)
        fresh = SimpleNamespace(settings=HingeSettings(length_mm=42))
        self.adapter.prepare_hinge.side_effect = [self.prepared, fresh]
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(self.adapter.prepare_hinge.call_count, 2)
        self.adapter.create_hinge.assert_called_once_with(self.design, fresh)
        self.assertFalse(self.graphics[0].isValid)

    def test_invalidated_custom_graphics_are_rebuilt_even_when_inputs_are_unchanged(self):
        command, session = self.open_command()
        self.select_sources(session)
        args = SimpleNamespace(isValidResult=True)
        command.executePreview.fire(args)
        self.graphics[0].isValid = False
        command.executePreview.fire(args)
        self.assertEqual(self.adapter.prepare_hinge.call_count, 2)
        self.assertTrue(self.graphics[1].isValid)

    def test_preview_logs_only_stage_totals_and_cached_preview_is_not_measured_again(self):
        command, session = self.open_command()
        self.select_sources(session)
        self.prepared.timings = {
            "source_read_ms": 1.1, "planning_ms": 2.2, "temporary_geometry_ms": 3.3,
            "body_name": "private-part", "source_token": "private-token",
            "diameter_mm": 8,
        }
        args = SimpleNamespace(isValidResult=True)
        with patch.object(self.module.time, "perf_counter", side_effect=[10, 10.01, 10.03, 10.04]) as timer:
            command.executePreview.fire(args)
            command.executePreview.fire(args)
        self.assertEqual(timer.call_count, 4)
        self.assertEqual(len(self.logs), 1)
        line = self.logs[0]
        for field in ("preview timings", "source_read_ms=1.100", "planning_ms=2.200",
                      "temporary_geometry_ms=3.300", "graphics_draw_ms=20.000", "total_ms=40.000"):
            self.assertIn(field, line)
        for forbidden in ("private-part", "private-token", "diameter_mm"):
            self.assertNotIn(forbidden, line)

    def test_create_logs_persistence_duration_even_without_adapter_timing_metadata(self):
        command, session = self.open_command()
        self.select_sources(session)
        args = SimpleNamespace(executeFailed=False)
        with patch.object(self.module.time, "perf_counter", side_effect=[20, 20.01, 20.04, 20.05]):
            command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(len(self.logs), 1)
        self.assertIn("create timings: persistence_ms=30.000 total_ms=50.000", self.logs[0])

    def test_timing_log_failure_does_not_reject_a_successfully_created_hinge(self):
        command, session = self.open_command()
        self.select_sources(session)
        self.module.adsk.core.Application.get().log = Mock(side_effect=RuntimeError("Log unavailable"))
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.adapter.create_hinge.assert_called_once_with(self.design, self.prepared)

    def test_unusable_optional_timing_metadata_cannot_reject_successful_persistence(self):
        command, session = self.open_command()
        self.select_sources(session)
        self.prepared.timings = {"source_read_ms": 10 ** 1000}
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.adapter.create_hinge.assert_called_once_with(self.design, self.prepared)

    def test_geometry_error_blocks_create_until_a_relevant_input_changes(self):
        command, session = self.open_command()
        self.select_sources(session)
        self.adapter.prepare_hinge.side_effect = ValueError("Attachment does not intersect body A.")
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertEqual(self.logs, [])
        args = SimpleNamespace(areInputsValid=True)
        command.validateInputs.fire(args)
        self.assertFalse(args.areInputsValid)
        execute = SimpleNamespace(executeFailed=False)
        command.execute.fire(execute)
        self.assertTrue(execute.executeFailed)
        self.adapter.create_hinge.assert_not_called()
        self.adapter.prepare_hinge.side_effect = None
        session.changed("leaf_reach_mm")
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertTrue(session.validate())

    def test_wrapped_preview_error_logs_native_cause_once_without_changing_user_message(self):
        command, session = self.open_command()
        self.select_sources(session)

        def native_failure(*arguments):
            try:
                raise RuntimeError("Native kernel operation failed")
            except RuntimeError as cause:
                raise ValueError("The hinge attachment could not be built.") from cause

        self.adapter.prepare_hinge.side_effect = native_failure
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertEqual(session.inputs.itemById("status").text, "The hinge attachment could not be built.")
        self.assertEqual(len(self.logs), 1)
        self.assertIn("Native kernel operation failed", self.logs[0])
        self.assertIn("Traceback", self.logs[0])
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertTrue(args.executeFailed)
        self.assertEqual(args.executeFailedMessage, "The hinge attachment could not be built.")
        self.assertEqual(len(self.logs), 1)

    def test_wrapped_create_error_preserves_failure_if_diagnostic_logging_also_fails(self):
        command, session = self.open_command()
        self.select_sources(session)

        def native_failure(*arguments):
            try:
                raise RuntimeError("Native persistence operation failed")
            except RuntimeError as cause:
                raise ValueError("The hinge copies could not be stored.") from cause

        self.adapter.create_hinge.side_effect = native_failure
        log = Mock(side_effect=RuntimeError("Log unavailable"))
        self.module.adsk.core.Application.get().log = log
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertTrue(args.executeFailed)
        self.assertEqual(args.executeFailedMessage, "The hinge copies could not be stored.")
        log.assert_called_once()
        self.assertIn("Native persistence operation failed", log.call_args.args[0])

    def test_invalid_native_expression_prevents_model_writes(self):
        command, session = self.open_command()
        self.select_sources(session)
        session.inputs.itemById("pin_diameter_mm").isValidExpression = False
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertTrue(args.executeFailed)
        self.assertIn("pin diameter", args.executeFailedMessage)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_edit_loads_dimensions_but_re_resolves_sources_before_preview_and_rebuild(self):
        command, session = self.open_command(editing=True)
        entity = SimpleNamespace(isValid=True)
        session.inputs.itemById("edit_target").entities = [entity]

        def target(name):
            return SimpleNamespace(
                settings=HingeSettings(length_mm=42, split_seam=True, seam_clearance_mm=.6, axis_offset_mm=7), component=name,
                face_a=f"{name}-a", face_b=f"{name}-b", axis_edge=f"{name}-edge",
            )

        loaded, reviewed, displayed, current = (target(name) for name in ("loaded", "reviewed", "displayed", "current"))
        self.adapter.read_edit_target.side_effect = [loaded, reviewed, displayed, current]
        session.changed("edit_target")
        self.assertEqual(session._settings().length_mm, 42)
        self.assertTrue(session._settings().split_seam)
        self.assertAlmostEqual(session._settings().seam_clearance_mm, .6)
        self.assertEqual(session._settings().axis_offset_mm, 7)
        self.assertFalse(session.inputs.itemById("axis_offset_mm").isEnabled)
        self.assertTrue(session.inputs.itemById("seam_clearance_mm").isEnabled)
        session.inputs.itemById("length_mm").value = 4.6
        session.changed("length_mm")
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        args = SimpleNamespace(executeFailed=False)
        command.execute.fire(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(self.adapter.read_edit_target.call_count, 4)
        latest = self.adapter.prepare_edit_hinge.call_args.args
        self.assertIs(latest[1], current)
        self.adapter.prepare_hinge.assert_not_called()
        self.assertEqual(latest[2].length_mm, 46)
        self.assertTrue(latest[2].split_seam)
        self.assertAlmostEqual(latest[2].seam_clearance_mm, .6)
        self.adapter.rebuild_hinge.assert_called_once_with(self.design, current, self.prepared)
        self.adapter.create_hinge.assert_not_called()
        self.assertTrue(any("hinge rebuild timings:" in line for line in self.logs))

    def test_stop_removes_owned_handlers_and_graphics_despite_one_detach_error(self):
        unrelated = self.ui.commandDefinitions.addButtonDefinition("other", "Other", "Other")
        command, session = self.open_command()
        self.select_sources(session)
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        command.inputChanged.fail_remove = True
        self.owner.start()
        self.owner.stop()
        self.assertEqual(set(self.ui.commandDefinitions.items), {"other"})
        self.assertTrue(unrelated.isValid)
        self.assertFalse(self.graphics[0].isValid)
        self.assertEqual(command.execute.handlers, [])
        self.assertEqual(command.destroy.handlers, [])
        self.assertEqual(self.owner._sessions, [])
        self.assertEqual(len([line for line in self.logs if "could not detach" in line]), 1)
        self.ui.terminateActiveCommand.assert_not_called()
        self.owner.start()
        self.assertEqual(len(self.ui.commandDefinitions.items), 3)

    def test_partial_dialog_setup_releases_already_bound_events(self):
        self.owner.launch_create()
        command = Command()
        command.executePreview.add = Mock(side_effect=RuntimeError("Event unavailable"))
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        definition.commandCreated.fire(SimpleNamespace(command=command))
        self.assertFalse(command.isOKButtonVisible)
        self.assertEqual(self.owner._sessions, [])
        self.assertEqual(command.inputChanged.handlers, [])
        self.assertEqual(command.validateInputs.handlers, [])
        self.assertEqual(len(self.logs), 1)


if __name__ == "__main__":
    unittest.main()
