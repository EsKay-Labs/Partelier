"""Snap palette and transaction contracts; the native probe checks CAD geometry."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings


class Event:
    def __init__(self):
        self.handlers = []
    def add(self, handler):
        self.handlers.append(handler)
    def remove(self, handler):
        self.handlers.remove(handler)


class Group:
    isValid = True
    def __init__(self):
        self.delete_count = 0
        self.fail_delete = False
    def deleteMe(self):
        if self.fail_delete:
            return False
        self.isValid = False
        self.delete_count += 1
        return True


class Lease:
    def __init__(self):
        self.original = {}
        self.fail_restore = False
    def hide(self, bodies):
        for body in bodies:
            self.original.setdefault(id(body), (body, body.isLightBulbOn))
            body.isLightBulbOn = False
    def restore(self):
        if self.fail_restore:
            raise ValueError("retry visibility restore")
        for body, flag in self.original.values():
            body.isLightBulbOn = flag
        self.original.clear()


class SnapCommandTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        capture_patch=patch('Partelier.partelier.operations.capture')
        self.capture_operation=capture_patch.start();self.addCleanup(capture_patch.stop)
        self.definitions = {}
        def add(identity, *args):
            definition = NS(id=identity, isValid=True, commandCreated=Event(), execute=Mock(return_value=True))
            definition.deleteMe = lambda: self.definitions.pop(identity)
            self.definitions[identity] = definition
            return definition
        self.selection_values = []
        self.ui = NS(commandDefinitions=NS(itemById=self.definitions.get, addButtonDefinition=add),
                     activeCommand="SelectCommand", commandTerminated=Event(), terminateActiveCommand=Mock(),
                     activeSelections=NS(count=0), selectEntity=Mock(side_effect=lambda *args: self.selection_values.pop(0)))
        self.design = NS(isValid=True,timeline=NS(count=0))
        self.app = NS(userInterface=self.ui, activeProduct=self.design, documentDeactivating=Event(), log=Mock())
        core, fusion, adsk = ModuleType("adsk.core"), ModuleType("adsk.fusion"), ModuleType("adsk")
        core.Application = NS(get=lambda: self.app)
        for name in ("CommandCreatedEventHandler", "CommandEventHandler", "DocumentEventHandler", "ApplicationCommandEventHandler"):
            setattr(core, name, object)
        fusion.Design = NS(cast=lambda value: value)
        adsk.core, adsk.fusion = core, fusion
        adapter_name = "Partelier.partelier.tools.snap_fit.fusion"
        adapter = ModuleType(adapter_name)
        for name in ("prepare_snap_fit", "prepare_edit_snap_fit", "read_edit_target", "create_snap_fit",
                     "rebuild_snap_fit", "preview_snap_fit", "preview_hide_bodies", "capture_preview_sources", "validate_preview_sources"):
            setattr(adapter, name, Mock(name=name))
        path = Path(__file__).parents[1] / "Partelier/partelier/tools/snap_fit/command.py"
        spec = importlib.util.spec_from_file_location("Partelier.partelier.tools.snap_fit._command_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion, adapter_name: adapter}):
            spec.loader.exec_module(self.module)
        self.module.BodyVisibilityLease = Lease
        self.manager = self.module.SnapCommands()
        self.manager.start()
        self.a = NS(isValid=True, name="Base", isLightBulbOn=True)
        self.b = NS(isValid=True, name="Lid", isLightBulbOn=False)
        self.edge = NS(isValid=True, name="Rim")
        self.prepared = NS(timings={})
        self.module.prepare_snap_fit.return_value = self.prepared
        self.module.prepare_edit_snap_fit.return_value = self.prepared
        self.module.preview_hide_bodies.return_value = (self.a, self.b)
        self.module.preview_snap_fit.side_effect = lambda p: Group()
        self.module.capture_preview_sources.return_value = NS()

    def tearDown(self):
        if self.manager._session:
            self.manager._session.visibility.fail_restore = False
            if self.manager._session.preview:
                self.manager._session.preview.fail_delete = False
        self.manager.stop()

    def begin(self, editing=False):
        self.selection_values[:] = [NS(entity=value) for value in ((self.a,) if editing else (self.a, self.b, self.edge))]
        self.manager.begin_palette(SnapFitSettings().to_dict(), editing)
        return self.manager._session

    def action(self, session, action, revision=None, settings=None, **extra):
        return self.manager.palette_action(action, session.session_id,
            revision=session.revision if revision is None else revision,
            settings_dict=(settings or session.settings).to_dict(), **extra)

    def preview(self, session):
        return self.action(session, "snap_preview")

    def test_registration_is_idempotent_and_stop_preserves_unrelated_ui(self):
        self.manager.start()
        self.assertEqual(len(self.definitions), 1)
        self.assertEqual(len(self.app.documentDeactivating.handlers), 1)
        self.assertEqual(len(self.ui.commandTerminated.handlers), 1)
        self.manager.stop()
        self.ui.terminateActiveCommand.assert_not_called()
        self.assertFalse(self.definitions)
        self.assertFalse(self.app.documentDeactivating.handlers)

    def test_direct_picks_do_not_open_a_second_native_panel(self):
        session = self.begin()
        self.assertEqual(session.phase, "ready")
        self.assertEqual(self.ui.selectEntity.call_count, 3)
        self.manager._registration[0].execute.assert_not_called()
        self.module.create_snap_fit.assert_not_called()

    def test_annular_picker_uses_cylinders_and_circular_rim(self):
        self.selection_values[:] = [NS(entity=value) for value in (self.a, self.b, self.edge)]
        self.manager.begin_palette(SnapFitSettings(snap_family="annular", chamfer_edges=False).to_dict())
        calls = self.ui.selectEntity.call_args_list
        self.assertEqual([call.args[1] for call in calls], ["CylindricalFaces", "CylindricalFaces", "Edges"])
        self.assertIn("circular", calls[2].args[0])

    def test_refused_native_handler_closes_empty_command_without_blocking_session(self):
        for event_name in ("execute", "destroy"):
            with self.subTest(event=event_name):
                session = self.manager._session or self.begin()
                self.preview(session)
                self.action(session, "snap_commit")
                command = NS(execute=Event(), destroy=Event())
                refused = getattr(command, event_name)
                refused.add = Mock(return_value=False)
                self.module._Created(self.manager).notify(NS(command=command))
                self.assertTrue(command.isAutoExecute)
                self.assertIsNone(session.command)
                self.assertEqual(session.phase, "error")
                self.assertEqual(session.handlers, [])
                self.assertEqual(command.execute.handlers, [])
                self.assertEqual(command.destroy.handlers, [])
                self.module.create_snap_fit.assert_not_called()

    def test_partially_bound_native_execute_cannot_commit_after_setup_failure(self):
        session = self.begin()
        self.preview(session)
        self.action(session, "snap_commit")
        command = NS(execute=Event(), destroy=Event())
        retained = []
        def fail(handler):
            retained.append(handler)
            raise RuntimeError("binding failed after partial attachment")
        command.execute.add = fail
        self.module._Created(self.manager).notify(NS(command=command))
        args = NS(executeFailed=False)
        retained[0].notify(args)
        self.assertTrue(args.executeFailed)
        self.assertTrue(command.isAutoExecute)
        self.assertIsNone(session.command)
        self.module.create_snap_fit.assert_not_called()

    def test_new_session_crossing_to_annular_clears_old_picks_and_preview(self):
        session = self.begin()
        self.preview(session)
        old = session.preview
        self.action(session, "snap_update", revision=1,
                    settings=SnapFitSettings(snap_family="annular", chamfer_edges=False))
        self.assertEqual(session.selections, {})
        self.assertFalse(old.isValid)
        self.assertTrue(self.a.isLightBulbOn)
        self.assertFalse(session.preview_current)

    def test_planar_family_switch_retains_current_geometry_references(self):
        session = self.begin()
        selections = dict(session.selections)
        self.action(session, "snap_preview", revision=1,
                    settings=SnapFitSettings(snap_family="ball_detent"))
        self.assertEqual(session.selections, selections)
        self.assertTrue(session.preview_current)

    def test_edit_cannot_cross_between_cylindrical_and_planar_references(self):
        session = self.begin()
        session.editing = True
        with self.assertRaisesRegex(ValueError, "new snap-fit"):
            self.action(session, "snap_update", revision=1,
                        settings=SnapFitSettings(snap_family="annular", chamfer_edges=False))
        self.assertEqual(session.settings.snap_family, "hook")
        self.assertEqual(session.revision, 0)

    def test_esc_resets_partial_picks_and_keeps_dimensions_editable(self):
        self.selection_values[:] = [NS(entity=self.a), None]
        self.manager.begin_palette(SnapFitSettings().to_dict())
        session = self.manager._session
        self.assertEqual(set(session.selections), set())
        self.action(session, "snap_update", revision=session.revision+1, settings=SnapFitSettings(width_mm=9))
        self.assertEqual(session.phase, "selecting")
        self.assertEqual(session.settings.width_mm, 9)

    def test_begin_refuses_second_session(self):
        self.begin()
        with self.assertRaisesRegex(ValueError, "Finish or cancel"):
            self.manager.begin_palette(SnapFitSettings().to_dict())

    def test_replacing_a_wall_requires_a_fresh_rim_pick(self):
        session = self.begin()
        self.preview(session)
        session.set_selection("face_a", self.a)
        self.assertNotIn("axis_edge", session.selections)
        self.assertEqual(session.phase, "selecting")
        self.assertFalse(session.preview_current)
        self.assertTrue(self.a.isLightBulbOn)

    def test_stale_session_and_revision_do_not_replace_settings(self):
        session = self.begin()
        self.action(session, "snap_update", revision=3, settings=SnapFitSettings(width_mm=9))
        with self.assertRaisesRegex(ValueError, "stale"):
            self.action(session, "snap_update", revision=2)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.action(session, "snap_update", revision=3, settings=SnapFitSettings(width_mm=10))
        with self.assertRaisesRegex(ValueError, "ended"):
            self.manager.palette_action("snap_cancel", "old-session")
        self.assertEqual(session.settings.width_mm, 9)

    def test_malformed_full_snapshot_cannot_partially_change_settings(self):
        session = self.begin()
        with self.assertRaises(ValueError):
            self.manager.palette_action("snap_update", session.session_id, 1, {"width_mm": 9})
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.settings, SnapFitSettings())

    def test_live_preview_owns_only_its_group_and_visibility(self):
        session = self.begin()
        self.preview(session)
        group = session.preview
        self.assertTrue(session.preview_current)
        self.assertFalse(self.a.isLightBulbOn)
        self.assertFalse(self.b.isLightBulbOn)
        self.action(session, "snap_cancel")
        self.assertFalse(group.isValid)
        self.assertTrue(self.a.isLightBulbOn)
        self.assertFalse(self.b.isLightBulbOn)
        self.module.create_snap_fit.assert_not_called()
        self.assertIsNone(self.manager._session)

    def test_camera_navigation_preserves_a_current_preview(self):
        session = self.begin()
        self.preview(session)
        group = session.preview
        self.module._CommandEnded(self.manager).notify(NS(commandId="OrbitCommand"))
        self.assertIs(session.preview, group)
        self.assertTrue(group.isValid)
        self.module.validate_preview_sources.assert_called_once()

    def test_actual_source_changes_invalidate_preview_and_restore_flags(self):
        session = self.begin()
        self.preview(session)
        self.module.validate_preview_sources.side_effect = ValueError("changed source")
        self.module._CommandEnded(self.manager).notify(NS(commandId="ExtrudeCommand"))
        self.assertFalse(session.preview_current)
        self.assertIsNone(session.preview)
        self.assertTrue(self.a.isLightBulbOn)
        self.assertIn("changed source", session.message)

    def test_failed_live_refresh_retains_last_valid_view_but_prevents_commit(self):
        session = self.begin()
        self.preview(session)
        old = session.preview
        self.module.prepare_snap_fit.side_effect = ValueError("thin wall")
        with self.assertRaisesRegex(ValueError, "thin wall"):
            self.action(session, "snap_preview", revision=1, settings=SnapFitSettings(width_mm=10))
        self.assertIs(session.preview, old)
        self.assertTrue(old.isValid)
        self.assertFalse(session.preview_current)
        with self.assertRaisesRegex(ValueError, "Refresh"):
            self.action(session, "snap_commit")
        self.module.create_snap_fit.assert_not_called()

    def test_replacement_deletes_previous_group_after_success(self):
        session = self.begin()
        self.preview(session)
        old = session.preview
        self.action(session, "snap_preview", revision=1, settings=SnapFitSettings(width_mm=10))
        self.assertFalse(old.isValid)
        self.assertIsNot(old, session.preview)
        self.assertTrue(session.preview_current)

    def test_commit_requires_current_view_then_uses_native_transaction(self):
        session = self.begin()
        with self.assertRaisesRegex(ValueError, "Refresh"):
            self.action(session, "snap_commit")
        self.preview(session)
        self.action(session, "snap_commit")
        self.assertIs(self.manager._pending, session)
        command = NS(execute=Event(), destroy=Event())
        self.module._Created(self.manager).notify(NS(command=command))
        self.assertTrue(command.isAutoExecute)
        self.assertFalse(command.isExecutedWhenPreEmpted)
        self.assertFalse(command.isRepeatable)
        self.assertIs(session.command, command)
        self.module.create_snap_fit.side_effect = lambda *args: self.assertTrue(self.a.isLightBulbOn)
        args = NS(executeFailed=False)
        command.execute.handlers[0].notify(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(session.phase, "created")
        self.assertEqual(self.module.prepare_snap_fit.call_count, 2)
        self.module.create_snap_fit.assert_called_once_with(self.design, self.prepared)
        command.destroy.handlers[0].notify(NS())
        self.assertIsNone(self.manager._session)
        self.assertFalse(command.execute.handlers)
        self.assertFalse(command.destroy.handlers)

    def test_native_failure_requests_rollback_and_keeps_session_for_retry(self):
        session = self.begin()
        self.preview(session)
        self.action(session, "snap_commit")
        command = NS(execute=Event(), destroy=Event())
        self.module._Created(self.manager).notify(NS(command=command))
        self.module.create_snap_fit.side_effect = RuntimeError("native join failed")
        args = NS(executeFailed=False)
        command.execute.handlers[0].notify(args)
        self.assertTrue(args.executeFailed)
        self.assertIn("native join failed", args.executeFailedMessage)
        command.destroy.handlers[0].notify(NS())
        self.assertIs(self.manager._session, session)
        self.assertIsNone(session.command)
        self.assertEqual(session.phase, "error")
        self.assertTrue(self.a.isLightBulbOn)

    def test_preselected_root_loads_dimensions_without_repick(self):
        target = NS(anchor=self.a, settings=SnapFitSettings(width_mm=12))
        self.module.read_edit_target.return_value = target
        self.ui.activeSelections = NS(count=1, item=lambda index: NS(entity=self.a))
        self.manager.begin_palette(SnapFitSettings().to_dict(), True)
        session = self.manager._session
        self.assertEqual(session.settings.width_mm, 12)
        self.ui.selectEntity.assert_not_called()
        self.preview(session)
        self.module.prepare_edit_snap_fit.assert_called_once_with(self.design, target, target.settings)

    def test_edit_rebuild_uses_current_settings_and_existing_anchor(self):
        target = NS(anchor=self.a, settings=SnapFitSettings())
        self.module.read_edit_target.return_value = target
        session = self.begin(True)
        self.action(session, "snap_preview", revision=1, settings=SnapFitSettings(width_mm=11))
        self.module.prepare_edit_snap_fit.assert_called_with(self.design, target, SnapFitSettings(width_mm=11))
        session.execute(NS(executeFailed=False))
        self.module.rebuild_snap_fit.assert_called_once_with(self.design, target, self.prepared)
        self.module.create_snap_fit.assert_not_called()

    def test_edit_load_error_survives_preview_and_settings_retry(self):
        self.module.read_edit_target.side_effect = ValueError("ambiguous owned snap-fits")
        session = self.begin(True)
        with self.assertRaisesRegex(ValueError, "ambiguous owned snap-fits"):
            self.preview(session)
        self.action(session, "snap_update", revision=1, settings=SnapFitSettings(width_mm=10))
        self.assertIn("ambiguous owned snap-fits", session.message)

    def test_document_switch_closes_session_and_restores_preview(self):
        session = self.begin()
        self.preview(session)
        self.module._DocumentChanging(self.manager).notify(NS())
        self.assertTrue(session.closed)
        self.assertIsNone(self.manager._session)
        self.assertTrue(self.a.isLightBulbOn)

    def test_cancel_retains_cleanup_ownership_until_restore_succeeds(self):
        session = self.begin()
        self.preview(session)
        session.visibility.fail_restore = True
        with self.assertRaisesRegex(ValueError, "retry visibility"):
            self.action(session, "snap_cancel")
        self.assertIs(self.manager._session, session)
        self.assertFalse(session.closed)
        session.visibility.fail_restore = False
        self.action(session, "snap_cancel")
        self.assertTrue(self.a.isLightBulbOn)
        self.assertIsNone(self.manager._session)

    def test_user_cannot_run_commit_definition_without_palette_session(self):
        command = NS(execute=Event(), destroy=Event())
        self.module._Created(self.manager).notify(NS(command=command))
        self.assertTrue(command.isAutoExecute)
        self.assertFalse(command.isOKButtonVisible)
        self.module.create_snap_fit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
