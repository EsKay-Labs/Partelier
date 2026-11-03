"""Composition cleanup under host failures; these fakes do not validate Fusion."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Event:
    def __init__(self):
        self.handlers = []
        self.fail_remove = False

    def add(self, handler):
        self.handlers.append(handler)

    def remove(self, handler):
        if self.fail_remove:
            raise RuntimeError("Simulated diagnostic event removal failure")
        self.handlers.remove(handler)


class Item:
    def __init__(self, collection, identity):
        self.collection = collection
        self.id = identity
        self.isValid = True
        self.commandCreated = Event()

    def deleteMe(self):
        self.collection.items.pop(self.id, None)
        self.isValid = False


class Collection:
    def __init__(self):
        self.items = {}
        self.creations = 0

    def itemById(self, identity):
        return self.items.get(identity)

    def addButtonDefinition(self, identity, *unused):
        if identity in self.items:
            raise RuntimeError("Duplicate definition")
        self.creations += 1
        item = Item(self, identity)
        self.items[identity] = item
        return item

    def addCommand(self, definition):
        return self.addButtonDefinition(definition.id)


class AddinLifecycleTests(unittest.TestCase):
    def setUp(self):
        definitions = Collection()
        self.controls = Collection()
        panel = SimpleNamespace(controls=self.controls)
        workspace = SimpleNamespace(toolbarPanels=SimpleNamespace(itemById=lambda identity: panel))
        self.ui = SimpleNamespace(
            commandDefinitions=definitions,
            workspaces=SimpleNamespace(itemById=lambda identity: workspace),
            activeCommand="unrelated-command",
            terminateActiveCommand=Mock(), messageBox=Mock(),
        )
        self.logs = []
        application = SimpleNamespace(userInterface=self.ui, log=self.logs.append)
        core = ModuleType("adsk.core")
        for name in ("CommandCreatedEventHandler", "InputChangedEventHandler",
                     "ValidateInputsEventHandler", "CommandEventHandler"):
            setattr(core, name, object)
        core.Application = SimpleNamespace(get=lambda: application)
        fusion = ModuleType("adsk.fusion")
        adsk = ModuleType("adsk")
        adsk.core = core
        adsk.fusion = fusion
        self.managers = []

        class Manager:
            fail_start = False

            def __init__(manager, report_error=None):
                manager.report_error = report_error
                manager.start_count = 0
                manager.stop_count = 0
                self.managers.append(manager)

            def start(manager):
                manager.start_count += 1
                if manager.fail_start:
                    raise RuntimeError("Simulated hinge registration failure")

            def stop(manager):
                manager.stop_count += 1

        self.manager_type = Manager
        self.snap_managers = []

        class SnapManager:
            fail_start = False

            def __init__(manager, report_error=None):
                manager.start_count = 0
                manager.stop_count = 0
                self.snap_managers.append(manager)

            def start(manager):
                manager.start_count += 1
                if manager.fail_start:
                    raise RuntimeError("Simulated snap registration failure")

            def stop(manager):
                manager.stop_count += 1

        self.snap_manager_type = SnapManager
        self.pattern_managers = []

        class PatternManager:
            fail_start = False

            def __init__(manager, report_error=None):
                manager.start_count = 0
                manager.stop_count = 0
                self.pattern_managers.append(manager)

            def start(manager):
                manager.start_count += 1
                if manager.fail_start:
                    raise RuntimeError("Simulated pattern registration failure")

            def stop(manager):
                manager.stop_count += 1

        self.pattern_manager_type = PatternManager

        class Library:
            def __init__(library):
                library.start_calls = []
                library.stop_count = 0
                library.show_count = 0
                library.fail_start = False
                library.fail_stop = False
                library.fail_show = False

            def start(library, *arguments, **keywords):
                library.start_calls.append((arguments, keywords))
                if library.fail_start:
                    raise RuntimeError("Simulated library registration failure")

            def stop(library):
                library.stop_count += 1
                if library.fail_stop:
                    raise RuntimeError("Simulated library teardown failure")

            def show(library):
                library.show_count += 1
                if library.fail_show:
                    raise RuntimeError("Simulated palette display failure")

        palette_name = "Partelier.partelier.palette"
        palette = ModuleType(palette_name)
        palette.ToolLibrary = Library
        hinge_name = "Partelier.partelier.tools.hinge.command"
        hinge = ModuleType(hinge_name)
        hinge.HingeCommands = Manager
        snap_name = "Partelier.partelier.tools.snap_fit.command"
        snap = ModuleType(snap_name)
        snap.SnapCommands = SnapManager
        pattern_name = "Partelier.partelier.tools.patterns.command"
        pattern = ModuleType(pattern_name)
        pattern.PatternCommands = PatternManager
        detail_name = 'Partelier.partelier.tools.details.command'
        detail = ModuleType(detail_name)
        self.detail_managers=[]
        class DetailManager:
            def __init__(manager,**kwargs):
                manager.start_count=0;manager.stop_count=0;self.detail_managers.append(manager)
            def start(manager):manager.start_count+=1
            def stop(manager):manager.stop_count+=1
        detail.DetailCommands=DetailManager
        fan_name='Partelier.partelier.tools.fans.command'
        fan=ModuleType(fan_name)
        self.fan_managers=[]
        class FanManager:
            def __init__(manager,**kwargs):
                manager.start_count=0;manager.stop_count=0;self.fan_managers.append(manager)
            def start(manager):manager.start_count+=1
            def stop(manager):manager.stop_count+=1
        fan.FanCommands=FanManager
        extras={}
        for stem,classname in (('mechanisms','MechanismCommands'),('finishing','FinishingCommands')):
            managers=[];setattr(self,stem+'_managers',managers)
            class ExtraManager:
                fail_start=False
                def __init__(manager,report_error=None,_instances=managers):
                    manager.start_count=0;manager.stop_count=0;_instances.append(manager)
                def start(manager):
                    manager.start_count+=1
                    if manager.fail_start:raise RuntimeError('Simulated extra registration failure')
                def stop(manager):manager.stop_count+=1
            setattr(self,stem+'_manager_type',ExtraManager)
            name='Partelier.partelier.tools.'+stem+'.command';module=ModuleType(name)
            setattr(module,classname,ExtraManager);extras[name]=module
        path = Path(__file__).parents[1] / "Partelier/partelier/addin.py"
        spec = importlib.util.spec_from_file_location(
            "Partelier.partelier._addin_lifecycle_test", path,
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {
            "adsk": adsk, "adsk.core": core, "adsk.fusion": fusion,
            **extras, palette_name: palette, hinge_name: hinge, snap_name: snap, pattern_name: pattern, detail_name: detail, fan_name: fan,
        }):
            spec.loader.exec_module(self.module)
        self.module.diagnostics=SimpleNamespace(start=Mock(),emit=Mock())
        self.library = self.module._tool_library

    def tearDown(self):
        self.library.fail_stop = False
        self.ui.terminateActiveCommand.side_effect = None
        definition = self.ui.commandDefinitions.itemById(self.module.COMMAND_ID)
        if definition is not None:
            definition.commandCreated.fail_remove = False
        self.module.stop()

    def assert_stopped(self):
        self.assertIsNone(self.module._created_handler)
        self.assertIsNone(self.module._hinge_commands)
        self.assertIsNone(self.module._snap_commands)
        self.assertIsNone(self.module._pattern_commands)
        self.assertIsNone(self.module._mechanism_commands)
        self.assertIsNone(self.module._finishing_commands)
        self.assertEqual(self.module._sessions, [])
        self.assertIsNone(self.ui.commandDefinitions.itemById(self.module.COMMAND_ID))
        self.assertIsNone(self.controls.itemById(self.module.COMMAND_ID))

    def test_snap_start_failure_stops_both_and_allows_retry(self):
        self.snap_manager_type.fail_start = True
        with self.assertRaisesRegex(RuntimeError, "snap registration"):
            self.module.start()
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assertEqual(self.snap_managers[0].stop_count, 1)
        self.assertEqual(self.library.start_calls, [])
        self.snap_manager_type.fail_start = False
        self.module.start()
        self.assertEqual(self.snap_managers[-1].start_count, 1)

    def test_small_details_are_started_and_passed_to_the_library(self):
        self.module.start()
        self.assertEqual(self.detail_managers[0].start_count,1)
        self.assertIs(self.library.start_calls[0][1]['detail_commands'],self.detail_managers[0])
        self.module.stop();self.assertEqual(self.detail_managers[0].stop_count,1)
        self.assertIsNone(self.module._detail_commands)

    def test_fan_manager_is_started_stopped_and_passed_to_the_library(self):
        self.module.start()
        self.assertEqual(self.fan_managers[0].start_count,1)
        self.assertIs(self.library.start_calls[0][1]['fan_commands'],self.fan_managers[0])
        self.module.stop()
        self.assertEqual(self.fan_managers[0].stop_count,1)
        self.assertIsNone(self.module._fan_commands)

    def test_new_tool_managers_register_once_and_release_on_stop(self):
        self.module.start();self.module.start()
        for stem,field in (('mechanisms','mechanism_commands'),('finishing','finishing_commands')):
            managers=getattr(self,stem+'_managers');self.assertEqual(len(managers),1)
            self.assertEqual(managers[0].start_count,1)
            self.assertIs(self.library.start_calls[0][1][field],managers[0])
        self.module.stop()
        for stem in ('mechanisms','finishing'):self.assertEqual(getattr(self,stem+'_managers')[0].stop_count,1)
        self.assert_stopped()

    def test_new_manager_registration_failures_roll_back_all_owned_registrations(self):
        for stem in ('mechanisms','finishing'):
            with self.subTest(manager=stem):
                manager_type=getattr(self,stem+'_manager_type');manager_type.fail_start=True
                with self.assertRaisesRegex(RuntimeError,'extra registration'):self.module.start()
                self.assert_stopped()
                self.assertEqual(getattr(self,stem+'_managers')[-1].stop_count,1)
                self.assertEqual(self.fan_managers[-1].stop_count,1)
                manager_type.fail_start=False
                self.module.start();self.module.stop();self.assert_stopped()

    def test_new_tool_stop_failure_does_not_skip_other_cleanup(self):
        self.module.start()
        self.mechanisms_managers[0].stop=Mock(side_effect=RuntimeError('mechanism stop'))
        self.module.stop();self.assert_stopped()
        self.assertEqual(self.finishing_managers[0].stop_count,1)
        self.assertTrue(self.logs)

    def test_detail_stop_failure_still_releases_the_library_and_other_managers(self):
        self.module.start();self.detail_managers[0].stop=Mock(side_effect=RuntimeError('detail stop'))
        self.module.stop()
        self.assertIsNone(self.module._detail_commands);self.assertGreater(self.library.stop_count,0)

    def test_snap_stop_failure_does_not_skip_owned_ui_cleanup(self):
        self.module.start()
        self.snap_managers[0].stop = Mock(side_effect=RuntimeError("snap stop"))
        self.module.stop()
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assertTrue(self.logs)

    def test_report_error_exposes_original_reason_and_full_traceback(self):
        palette = SimpleNamespace(isVisible=False)
        self.ui.palettes = SimpleNamespace(itemById=lambda identity: palette)
        try:
            raise RuntimeError("Part Design documents can only contain one component")
        except RuntimeError:
            self.module.report_error("Could not create the hinge")
        message, title = self.ui.messageBox.call_args.args
        self.assertEqual(title, "Partelier")
        self.assertIn("Part Design documents can only contain one component", message)
        self.assertIn("Show Text Commands", message)
        self.assertIn("Traceback", self.logs[-1])
        self.assertTrue(palette.isVisible)

    def test_report_error_preserves_modeling_reason_when_logging_fails(self):
        application = self.module.adsk.core.Application.get()
        application.log = Mock(side_effect=RuntimeError("Logging unavailable"))
        try:
            raise RuntimeError("Original native failure")
        except RuntimeError:
            self.module.report_error("Could not create the hinge")
        message = self.ui.messageBox.call_args.args[0]
        self.assertIn("Original native failure", message)
        self.assertNotIn("Logging unavailable", message)

    def test_start_is_idempotent_and_passes_started_manager_to_the_library(self):
        self.module.start()
        self.assertEqual(self.library.show_count, 1, "Run opens the HTML library immediately")
        self.module.start()
        self.assertEqual(self.library.show_count, 2, "Run reveals the existing library again")
        self.assertEqual(len(self.managers), 1)
        manager = self.managers[0]
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(len(self.library.start_calls), 1)
        arguments, keywords = self.library.start_calls[0]
        self.assertEqual(arguments[:3], (
            self.module.WORKSPACE_ID, self.module.PANEL_ID, self.module.COMMAND_ID,
        ))
        self.assertIs(keywords["hinge_commands"], manager)
        self.assertIs(keywords["snap_commands"], self.snap_managers[0])
        self.assertIs(keywords["pattern_commands"], self.pattern_managers[0])
        self.assertEqual(self.snap_managers[0].start_count, 1)
        self.assertEqual(self.pattern_managers[0].start_count, 1)
        self.assertEqual(len(self.ui.commandDefinitions.items), 1)
        self.assertEqual(len(self.controls.items), 1)
        self.assertEqual(len(self.ui.commandDefinitions.itemById(self.module.COMMAND_ID).commandCreated.handlers), 1)

    def test_auto_show_runs_after_both_managers_and_library_are_ready(self):
        show = self.library.show

        def assert_ready():
            self.assertEqual(self.managers[0].start_count, 1)
            self.assertEqual(self.snap_managers[0].start_count, 1)
            self.assertEqual(self.pattern_managers[0].start_count, 1)
            self.assertEqual(len(self.library.start_calls), 1)
            self.assertIsNotNone(self.module._created_handler)
            show()

        self.library.show = Mock(side_effect=assert_ready)
        self.module.start()
        self.library.show.assert_called_once_with()
        self.assertEqual(self.library.show_count, 1)

    def test_initial_auto_show_failure_cleans_up_and_allows_fresh_retry(self):
        self.library.fail_show = True
        with self.assertRaisesRegex(RuntimeError, "palette display"):
            self.module.start()
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assertEqual(self.snap_managers[0].stop_count, 1)
        self.assertEqual(self.pattern_managers[0].stop_count, 1)
        self.assertEqual(self.library.stop_count, 1)
        self.assertEqual(self.library.show_count, 1)
        self.library.fail_show = False
        self.module.start()
        self.assertEqual(self.library.show_count, 2)
        self.assertEqual(len(self.managers), 2)
        self.assertEqual(len(self.snap_managers), 2)
        self.assertEqual(len(self.library.start_calls), 2)
        self.assertEqual(len(self.ui.commandDefinitions.items), 1)
        self.assertEqual(len(self.controls.items), 1)

    def test_repeated_run_show_failure_keeps_registration_available_for_retry(self):
        self.module.start()
        definition = self.ui.commandDefinitions.itemById(self.module.COMMAND_ID)
        self.library.fail_show = True
        with self.assertRaisesRegex(RuntimeError, "palette display"):
            self.module.start()
        self.assertTrue(definition.isValid)
        self.assertEqual(self.managers[0].stop_count, 0)
        self.assertEqual(self.snap_managers[0].stop_count, 0)
        self.assertEqual(self.pattern_managers[0].stop_count, 0)
        self.library.fail_show = False
        self.module.start()
        self.assertEqual(self.library.show_count, 3)
        self.assertEqual(len(self.managers), 1)
        self.assertEqual(len(self.snap_managers), 1)
        self.assertEqual(len(self.pattern_managers), 1)
        self.assertEqual(len(self.library.start_calls), 1)
        self.assertIs(self.ui.commandDefinitions.itemById(self.module.COMMAND_ID), definition)

    def test_normal_stop_preserves_unrelated_ui_and_restart_gets_a_fresh_manager(self):
        unrelated = self.ui.commandDefinitions.addButtonDefinition("other")
        self.controls.addCommand(unrelated)
        self.module.start()
        old_manager = self.managers[0]
        self.module.stop()
        self.assert_stopped()
        self.assertTrue(unrelated.isValid)
        self.assertIsNotNone(self.controls.itemById("other"))
        self.assertEqual(old_manager.stop_count, 1)
        self.ui.terminateActiveCommand.assert_not_called()
        self.module.start()
        self.assertEqual(len(self.managers), 2)
        self.assertIsNot(self.module._hinge_commands, old_manager)
        self.assertEqual(self.managers[-1].start_count, 1)

    def test_library_stop_failure_does_not_skip_hinge_or_diagnostic_cleanup(self):
        self.module.start()
        manager = self.managers[0]
        self.library.fail_stop = True
        self.module._sessions.append(SimpleNamespace(handlers=[]))
        self.module.stop()
        self.assertEqual(manager.stop_count, 1)
        self.assert_stopped()
        self.assertTrue(self.logs)
        self.library.fail_stop = False
        self.module.start()
        self.assertEqual(len(self.managers), 2)

    def test_terminate_failure_still_stops_both_managers_and_removes_owned_ui(self):
        self.module.start()
        self.ui.activeCommand = self.module.COMMAND_ID
        self.ui.terminateActiveCommand.side_effect = RuntimeError("Simulated terminate failure")
        self.module.stop()
        self.ui.terminateActiveCommand.assert_called_once_with()
        self.assertEqual(self.library.stop_count, 1)
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assert_stopped()
        self.assertTrue(self.logs)

    def test_diagnostic_detach_failure_still_deletes_definition_and_resets_start_guard(self):
        self.module.start()
        definition = self.ui.commandDefinitions.itemById(self.module.COMMAND_ID)
        definition.commandCreated.fail_remove = True
        self.module.stop()
        self.assertFalse(definition.isValid)
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.module.start()
        self.assertEqual(len(self.managers), 2)
        self.assertEqual(self.managers[-1].start_count, 1)

    def test_hinge_registration_failure_rolls_back_diagnostic_before_retry(self):
        self.manager_type.fail_start = True
        with self.assertRaisesRegex(RuntimeError, "hinge registration"):
            self.module.start()
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assertEqual(self.library.start_calls, [])
        self.manager_type.fail_start = False
        self.module.start()
        self.assertEqual(len(self.managers), 2)
        self.assertEqual(self.managers[-1].start_count, 1)

    def test_library_registration_failure_stops_the_previously_started_hinge_manager(self):
        self.library.fail_start = True
        with self.assertRaisesRegex(RuntimeError, "library registration"):
            self.module.start()
        self.assertEqual(self.managers[0].start_count, 1)
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assert_stopped()
        self.library.fail_start = False
        self.module.start()
        self.assertEqual(len(self.managers), 2)

    def test_pattern_start_failure_stops_all_managers_and_allows_retry(self):
        self.pattern_manager_type.fail_start = True
        with self.assertRaisesRegex(RuntimeError, "pattern registration"):
            self.module.start()
        self.assert_stopped()
        for manager in (self.managers[0], self.snap_managers[0], self.pattern_managers[0]):
            self.assertEqual(manager.stop_count, 1)
        self.assertEqual(self.library.start_calls, [])
        self.pattern_manager_type.fail_start = False
        self.module.start()
        self.assertEqual(self.pattern_managers[-1].start_count, 1)
        self.assertEqual(self.library.show_count, 1)

    def test_pattern_stop_failure_does_not_skip_owned_ui_cleanup(self):
        self.module.start()
        self.pattern_managers[0].stop = Mock(side_effect=RuntimeError("pattern stop"))
        self.module.stop()
        self.assert_stopped()
        self.assertEqual(self.managers[0].stop_count, 1)
        self.assertEqual(self.snap_managers[0].stop_count, 1)
        self.assertTrue(self.logs)


if __name__ == "__main__":
    unittest.main()
