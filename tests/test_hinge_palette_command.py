"""Direct picking and no-dialog command contracts; not Fusion validation."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import test_hinge_command_contract as native_fakes
from Partelier.partelier.tools.hinge.settings import HingeSettings


class HingePaletteCommandTests(unittest.TestCase):
    def setUp(self):
        native_fakes.HingeCommandContractTests.setUp(self)
        self.published = []
        self.owner.set_state_callback(self.published.append)
        self.entities = {name: SimpleNamespace(isValid=True, name=name)
                         for name in ("face_a", "face_b", "axis_edge", "edit_target")}
        self.ui.selectEntity = Mock()
        self.commands = []
        self.execute_args = []
        for identity in (self.module.CREATE_COMMAND_ID, self.module.EDIT_COMMAND_ID):
            self.ui.commandDefinitions.itemById(identity).execute.side_effect = (
                lambda identity=identity: self.native_commit(identity))

    def tearDown(self):
        self.owner.stop()

    def native_commit(self, identity):
        """Simulate documented zero-input auto-execute, then destroy."""
        command = native_fakes.Command()
        self.commands.append(command)
        self.ui.activeCommand = identity
        self.ui.commandDefinitions.itemById(identity).commandCreated.fire(SimpleNamespace(command=command))
        if command.isAutoExecute:
            self.assertEqual(command.commandInputs.items, {})
            args = SimpleNamespace(executeFailed=False)
            command.execute.fire(args)
            self.execute_args.append(args)
            command.destroy.fire(SimpleNamespace())
            command.commandInputs.itemById = Mock(side_effect=RuntimeError("Native inputs destroyed"))
            self.ui.activeCommand = "SelectCommand"
        return True  # An acknowledgement is independent of execute success.

    def open_palette(self, settings=None, editing=False, picks=None):
        names = ("edit_target",) if editing else ("face_a", "face_b", "axis_edge")
        self.ui.selectEntity.side_effect = picks if picks is not None else [
            SimpleNamespace(entity=self.entities[name]) for name in names]
        self.owner.begin_palette((settings or HingeSettings()).to_dict(), editing)
        self.assertEqual(len(self.owner._sessions), 1)
        return self.owner._sessions[0]

    def action(self, session, action, settings=None, revision=None, **keywords):
        result = self.owner.palette_action(
            action, session.session_id,
            revision=session.revision if revision is None else revision,
            settings_dict=(settings or session.palette_settings).to_dict()
                if action in {"hinge_update", "hinge_preview", "hinge_commit"} else None,
            **keywords,
        )
        self.drain_native_preview_events()
        return self.owner.palette_state() if action == "hinge_preview" else result

    def test_begin_picks_directly_without_launching_any_command_or_inputs(self):
        session = self.open_palette()
        self.assertIsNone(session.command)
        self.assertIsNone(session.inputs)
        self.assertEqual([call.args[1] for call in self.ui.selectEntity.call_args_list],
                         ["PlanarFaces", "PlanarFaces", "Edges"])
        for definition, _ in self.owner._registrations:
            definition.execute.assert_not_called()
        snapshot = self.owner.palette_state()
        self.assertEqual(snapshot["phase"], "ready")
        self.assertTrue(all(item["selected"] for item in snapshot["selections"].values()))
        self.assertTrue(self.published)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_escape_stops_sequence_and_retry_keeps_captured_references(self):
        session = self.open_palette(picks=[SimpleNamespace(entity=self.entities["face_a"]), RuntimeError("aborted")])
        self.assertEqual(self.ui.selectEntity.call_count, 2)
        self.assertIs(session.selection_entities["face_a"], self.entities["face_a"])
        self.assertEqual(session.phase, "selecting")
        self.ui.selectEntity.side_effect = [SimpleNamespace(entity=self.entities["face_b"]),
                                           SimpleNamespace(entity=self.entities["axis_edge"])]
        self.action(session, "hinge_focus", target="face_b")
        self.assertEqual(self.action(session, "hinge_focus", target="axis_edge")["phase"], "ready")
        self.ui.terminateActiveCommand.assert_not_called()

    def test_escape_from_repick_retains_existing_selection_and_ready_state(self):
        session = self.open_palette()
        self.ui.selectEntity.side_effect = RuntimeError("aborted")
        state = self.action(session, "hinge_focus", target="face_a")
        self.assertEqual(state["phase"], "ready")
        self.assertIs(session.selection_entities["face_a"], self.entities["face_a"])
        self.assertIn("Previous selections were kept", state["message"])

    def test_different_face_clears_reference_edge_and_preview(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        self.ui.selectEntity.side_effect = [SimpleNamespace(entity=SimpleNamespace(isValid=True, name="new face"))]
        state = self.action(session, "hinge_focus", target="face_b")
        self.assertFalse(state["selections"]["axis_edge"]["selected"])
        self.assertFalse(self.graphics[-1].isValid)
        self.assertEqual(state["phase"], "selecting")

    def test_full_snapshot_update_invalidates_preview_without_kernel_work(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        settings = replace(session.palette_settings, output_mode="separate", leaf_profile="rounded", screw_holes=True)
        self.adapter.prepare_hinge.reset_mock()
        snapshot = self.action(session, "hinge_update", settings, revision=1)
        self.assertFalse(self.graphics[-1].isValid)
        self.adapter.prepare_hinge.assert_not_called()
        self.assertEqual(snapshot["settings"], settings.to_dict())
        self.assertEqual(snapshot["revision"], 1)

    def test_support_profile_changes_flow_through_live_preview_and_create_snapshot(self):
        session = self.open_palette()
        self.assertEqual(session.palette_settings.web_profile, "tangent")
        settings = replace(session.palette_settings, web_profile="flat")
        preview = self.action(session, "hinge_preview", settings, revision=1)
        self.assertEqual(preview["settings"]["web_profile"], "flat")
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], settings)
        self.action(session, "hinge_commit", settings)
        self.assertEqual(self.adapter.create_hinge.call_args.args[1].settings, settings)

    def test_preview_is_temporary_and_repeated_preview_reuses_current_graphics(self):
        session = self.open_palette()
        self.assertEqual(self.action(session, "hinge_preview")["phase"], "preview")
        self.assertEqual(self.action(session, "hinge_preview")["phase"], "preview")
        self.adapter.prepare_hinge.assert_called_once()
        self.adapter.create_hinge.assert_not_called()
        self.assertFalse(self.commands)

    def test_style_refresh_keeps_old_graphics_until_replacement_is_drawn(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        prepare = self.adapter.prepare_hinge.side_effect
        draw = self.adapter.preview_hinge.side_effect
        def preparing(*args, **keywords):
            self.assertTrue(previous.isValid)
            return prepare(*args, **keywords)
        def drawing(prepared):
            self.assertTrue(previous.isValid)
            return draw(prepared)
        self.adapter.prepare_hinge.side_effect = preparing
        self.adapter.preview_hinge.side_effect = drawing
        settings = replace(session.palette_settings, knuckle_profile="square", chamfer_edges=True)
        state = self.action(session, "hinge_preview", settings, revision=1)
        self.assertTrue(state["previewCurrent"])
        self.assertEqual(state["phase"], "preview")
        self.assertFalse(previous.isValid)
        self.assertTrue(session.preview.isValid)
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], settings)
        self.adapter.create_hinge.assert_not_called()

    def test_failed_live_refresh_preserves_last_valid_graphics_and_can_retry(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        prepare = self.adapter.prepare_hinge.side_effect
        self.adapter.prepare_hinge.side_effect = ValueError("The fillet does not fit")
        settings = replace(session.palette_settings, fillet_edges=True)
        state = self.action(session, "hinge_preview", settings, revision=1)
        self.assertEqual(state["phase"], "error")
        self.assertFalse(state["previewCurrent"])
        self.assertTrue(previous.isValid)
        self.assertIn("previous valid preview", state["message"])
        self.adapter.prepare_hinge.side_effect = prepare
        state = self.action(session, "hinge_preview", settings, revision=1)
        self.assertTrue(state["previewCurrent"])
        self.assertFalse(previous.isValid)
        self.adapter.create_hinge.assert_not_called()

    def test_aborted_repick_keeps_graphics_and_subsequent_refresh_is_cached(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        self.ui.selectEntity.side_effect = RuntimeError("Esc")
        self.action(session, "hinge_focus", target="axis_edge")
        self.assertTrue(previous.isValid)
        self.action(session, "hinge_preview")
        self.assertIs(session.preview, previous)
        self.adapter.prepare_hinge.assert_called_once()

    def test_failed_old_graphics_retirement_cleans_candidate_and_cancel_retries(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        previous.deleteMe.side_effect = None
        previous.deleteMe.return_value = False
        with self.assertRaisesRegex(RuntimeError, "remove a temporary"):
            self.action(session, "hinge_preview", replace(session.palette_settings, length_mm=35), revision=1)
        self.assertTrue(previous.isValid)
        self.assertFalse(self.graphics[-1].isValid)
        self.assertIs(session.preview, previous)
        previous.deleteMe.side_effect = lambda: setattr(previous, "isValid", False)
        self.action(session, "hinge_cancel")
        self.assertFalse(previous.isValid)

    def test_failed_candidate_cleanup_remains_owned_and_blocks_graphics_growth(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        previous.deleteMe.side_effect = None
        previous.deleteMe.return_value = False
        draw = self.adapter.preview_hinge.side_effect
        def failed_cleanup(prepared):
            group = draw(prepared)
            group.deleteMe.side_effect = None
            group.deleteMe.return_value = False
            return group
        self.adapter.preview_hinge.side_effect = failed_cleanup
        with self.assertRaises(RuntimeError):
            self.action(session, "hinge_preview", replace(session.palette_settings, length_mm=35), revision=1)
        self.assertEqual(len(session.retained_preview_groups), 1)
        with self.assertRaises(RuntimeError):
            self.action(session, "hinge_preview")
        self.assertEqual(len(self.graphics), 2)
        for group in self.graphics:
            group.deleteMe.side_effect = lambda group=group: setattr(group, "isValid", False)
        self.action(session, "hinge_cancel")
        self.assertTrue(all(not group.isValid for group in self.graphics))
        self.assertFalse(session.retained_preview_groups)

    def test_failed_cancel_keeps_owned_graphics_and_can_be_retried(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        group = session.preview
        group.deleteMe.side_effect = None
        group.deleteMe.return_value = False
        with self.assertRaisesRegex(RuntimeError, "clear all temporary"):
            self.action(session, "hinge_cancel")
        self.assertFalse(session.closed)
        self.assertEqual(session.phase, "error")
        self.assertTrue(group.isValid)
        group.deleteMe.side_effect = lambda: setattr(group, "isValid", False)
        self.assertEqual(self.action(session, "hinge_cancel")["phase"], "cancelled")
        self.assertFalse(group.isValid)

    def test_commit_runs_zero_input_auto_command_and_uses_fresh_settings(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        settings = replace(session.palette_settings, length_mm=35)
        result = self.action(session, "hinge_commit", settings, revision=1)
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], settings)
        self.adapter.create_hinge.assert_called_once_with(self.design, self.prepared)
        self.assertEqual(len(self.commands), 1)
        command = self.commands[0]
        self.assertTrue(command.isAutoExecute)
        self.assertFalse(command.isExecutedWhenPreEmpted)
        self.assertFalse(command.commandInputs.items)
        self.assertFalse(command.executePreview.handlers)
        self.assertFalse(command.inputChanged.handlers)
        self.assertEqual(result["phase"], "created")
        self.assertIsNone(result["sessionId"])
        self.assertFalse(self.owner._sessions)
        self.assertTrue(all(not group.isValid for group in self.graphics))
        self.assertFalse(command.execute.handlers)
        self.assertFalse(command.destroy.handlers)

    def test_launch_ack_without_native_execute_does_not_report_created(self):
        session = self.open_palette()
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        definition.execute.side_effect = None
        state = self.action(session, "hinge_commit")
        self.assertEqual(state["phase"], "opening")
        self.adapter.create_hinge.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Wait for"):
            self.action(session, "hinge_commit")
        with self.assertRaisesRegex(ValueError, "Wait for"):
            self.action(session, "hinge_cancel")

    def test_failed_launch_can_retry_same_logical_session(self):
        session = self.open_palette()
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        definition.execute.side_effect = RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.action(session, "hinge_commit")
        self.assertIsNone(self.owner._palette_pending)
        self.assertFalse(self.owner._opening)
        self.assertIsNone(session.command)
        definition.execute.side_effect = lambda: self.native_commit(self.module.CREATE_COMMAND_ID)
        self.assertEqual(self.action(session, "hinge_commit")["phase"], "created")

    def test_stale_revision_session_and_document_never_preview_or_create(self):
        session = self.open_palette()
        self.action(session, "hinge_update", revision=2)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.action(session, "hinge_commit", revision=1)
        with self.assertRaisesRegex(ValueError, "session has ended"):
            self.owner.palette_action("hinge_commit", "other", 3, session.palette_settings.to_dict())
        application = self.module.adsk.core.Application.get()
        application.activeProduct = object()
        with self.assertRaisesRegex(ValueError, "Return to the design"):
            self.action(session, "hinge_preview", revision=3)
        application.activeProduct = self.design
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_same_revision_cannot_replace_different_snapshot(self):
        session = self.open_palette()
        with self.assertRaisesRegex(ValueError, "stale"):
            self.action(session, "hinge_update", replace(session.palette_settings, length_mm=30), revision=0)
        self.assertEqual(session.palette_settings.length_mm, 40)

    def test_incomplete_or_invalidated_geometry_blocks_commit(self):
        session = self.open_palette(picks=[RuntimeError("aborted")])
        with self.assertRaisesRegex(ValueError, "Select face A"):
            self.action(session, "hinge_commit")
        session.selection_entities.update(self.entities)
        self.entities["face_b"].isValid = False
        with self.assertRaisesRegex(ValueError, "Select face B"):
            self.action(session, "hinge_commit")
        self.adapter.create_hinge.assert_not_called()

    def test_cancel_clears_preview_references_and_never_terminates_unrelated_command(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        self.ui.activeCommand = "unrelated"
        result = self.action(session, "hinge_cancel")
        self.ui.terminateActiveCommand.assert_not_called()
        self.assertEqual(result["phase"], "cancelled")
        self.assertIsNone(result["sessionId"])
        self.assertFalse(session.selection_entities)
        self.adapter.create_hinge.assert_not_called()
        self.assertTrue(all(not group.isValid for group in self.graphics))

    def test_native_execute_without_palette_confirmation_is_rejected(self):
        session = self.open_palette()
        args = SimpleNamespace(executeFailed=False)
        session.execute(args)
        self.assertTrue(args.executeFailed)
        self.adapter.create_hinge.assert_not_called()

    def test_edit_direct_selection_loads_every_saved_field_and_rebuilds(self):
        saved = HingeSettings(output_mode="separate", knuckle_profile="square", fillet_edges=True, fillet_radius_mm=.4, screw_holes=True, length_mm=34)
        self.adapter.read_edit_target.return_value = SimpleNamespace(
            settings=saved, face_a=object(), face_b=object(), axis_edge=object())
        session = self.open_palette(editing=True)
        self.assertEqual(self.ui.selectEntity.call_args.args[1], "Occurrences,SolidBodies")
        self.assertEqual(self.owner.palette_state()["settings"], saved.to_dict())
        self.assertTrue(session.edit_target_loaded)
        result = self.action(session, "hinge_commit")
        self.assertEqual(result["phase"], "created")
        self.adapter.rebuild_hinge.assert_called_once()
        self.adapter.create_hinge.assert_not_called()
        self.adapter.prepare_hinge.assert_not_called()
        self.assertEqual(self.adapter.prepare_edit_hinge.call_args.args[2], saved)

    def test_edit_adopts_single_preselected_entity_and_saved_dimensions_without_picker(self):
        saved = HingeSettings(length_mm=31, knuckle_count=3)
        self.adapter.read_edit_target.return_value = SimpleNamespace(settings=saved)
        selected = SimpleNamespace(isValid=True, name="Selected Part")
        self.ui.activeSelections = SimpleNamespace(count=1, item=lambda index: SimpleNamespace(entity=selected))
        self.owner.begin_palette(HingeSettings().to_dict(), editing=True)
        session = self.owner._sessions[0]
        self.assertIs(session.selection_entities["edit_target"], selected)
        self.assertTrue(session.edit_target_loaded)
        self.assertEqual(session.palette_settings, saved)
        self.assertEqual(session.phase, "ready")
        self.ui.selectEntity.assert_not_called()
        self.adapter.read_edit_target.assert_called_once_with(self.design, selected)

    def test_multiple_preselections_use_picker_instead_of_guessing(self):
        self.adapter.read_edit_target.return_value = SimpleNamespace(settings=HingeSettings())
        self.ui.activeSelections = SimpleNamespace(count=2)
        session = self.open_palette(editing=True)
        self.ui.selectEntity.assert_called_once()
        self.assertIs(session.selection_entities["edit_target"], self.entities["edit_target"])

    def test_failed_edit_load_keeps_its_real_error_across_preview_settings_and_escape(self):
        message = "The selected Part contains multiple hinges. Pick one hinge body or pin."
        self.adapter.read_edit_target.side_effect = ValueError(message)
        session = self.open_palette(editing=True)
        self.assertEqual(session.message, message)
        for revision in (1, 2):
            with self.assertRaisesRegex(ValueError, "multiple hinges"):
                self.owner.palette_action("hinge_preview", session.session_id, revision=revision,
                                          settings_dict=session.palette_settings.to_dict())
            self.assertEqual(session.message, message)
        state = self.action(session, "hinge_update", replace(session.palette_settings, length_mm=33), revision=3)
        self.assertEqual(state["phase"], "error")
        self.assertEqual(state["message"], message)
        self.ui.selectEntity.side_effect = RuntimeError("Esc")
        state = self.action(session, "hinge_focus", target="edit_target")
        self.assertEqual(state["phase"], "error")
        self.assertEqual(state["message"], message)
        self.adapter.read_edit_target.side_effect = None
        self.adapter.read_edit_target.return_value = SimpleNamespace(settings=HingeSettings(length_mm=29))
        self.ui.selectEntity.side_effect = [SimpleNamespace(entity=self.entities["edit_target"])]
        state = self.action(session, "hinge_focus", target="edit_target")
        self.assertEqual(state["phase"], "ready")
        self.assertTrue(session.edit_target_loaded)
        self.assertEqual(state["settings"]["length_mm"], 29)

    def test_auto_seam_effective_settings_publish_without_native_controls(self):
        session = self.open_palette()
        self.adapter.prepare_hinge.side_effect = lambda *args: SimpleNamespace(settings=replace(args[4], split_seam=True))
        result = self.action(session, "hinge_preview")
        self.assertTrue(result["settings"]["split_seam"])
        self.assertTrue(session.auto_split_detected)
        self.assertEqual(result["phase"], "preview")

    def test_geometry_failure_never_claims_created(self):
        session = self.open_palette()
        self.adapter.prepare_hinge.side_effect = ValueError("Leaf holes do not fit")
        result = self.action(session, "hinge_preview")
        self.assertEqual(result["phase"], "error")
        self.assertIn("Leaf holes do not fit", result["message"])
        self.adapter.create_hinge.assert_not_called()

    def test_callback_and_logging_failures_do_not_reject_successful_creation(self):
        session = self.open_palette()
        self.owner.set_state_callback(Mock(side_effect=RuntimeError("Palette closed")))
        self.module.adsk.core.Application.get().log = Mock(side_effect=RuntimeError("Logging unavailable"))
        result = self.action(session, "hinge_commit")
        self.assertEqual(result["phase"], "created")
        self.adapter.create_hinge.assert_called_once()

    def test_failed_native_commit_keeps_actionable_error_and_allows_new_session(self):
        session = self.open_palette()
        self.adapter.create_hinge.side_effect = ValueError("The leaf holes do not fit")
        state = self.action(session, "hinge_commit")
        self.assertEqual(state["phase"], "error")
        self.assertIn("leaf holes do not fit", state["message"])
        self.assertIsNone(state["sessionId"])
        self.assertTrue(self.execute_args[-1].executeFailed)
        self.assertTrue(self.open_palette())

    def test_failed_queued_commit_setup_never_autoexecutes_and_releases_session(self):
        session = self.open_palette()
        definition = self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID)
        definition.execute.side_effect = None
        self.action(session, "hinge_commit")
        self.module.adsk.core.Application.get().activeProduct = object()
        command = native_fakes.Command()
        definition.commandCreated.fire(SimpleNamespace(command=command))
        self.assertFalse(command.isAutoExecute)
        self.assertFalse(command.isOKButtonVisible)
        self.assertFalse(command.commandInputs.items)
        self.assertIsNone(self.owner._palette_pending)
        self.assertFalse(self.owner._opening)
        self.ui.terminateActiveCommand.assert_not_called()
        state = self.owner.palette_state()
        self.assertEqual(state["phase"], "error")
        self.assertIsNone(state["sessionId"])
        self.assertIn("Press Esc", state["message"])
        self.adapter.create_hinge.assert_not_called()

    def test_focus_rejects_wrong_target_and_begin_cannot_replace_open_session(self):
        session = self.open_palette()
        with self.assertRaises(ValueError):
            self.action(session, "hinge_focus", target="edit_target")
        with self.assertRaises(ValueError):
            self.owner.begin_palette(HingeSettings().to_dict())

    def test_document_change_during_pick_releases_session_and_prevents_commit(self):
        def change_design(*args):
            self.module.adsk.core.Application.get().activeProduct = object()
            return SimpleNamespace(entity=self.entities["face_a"])
        with self.assertRaisesRegex(ValueError, "Return to the design"):
            self.open_palette(picks=change_design)
        self.assertFalse(self.owner._sessions)
        self.assertFalse(self.owner._palette_action_busy)
        self.adapter.create_hinge.assert_not_called()

    def test_reentrant_action_during_pick_is_rejected(self):
        def reentrant(*args):
            session = self.owner._sessions[0]
            with self.assertRaisesRegex(ValueError, "Finish the current selection"):
                self.action(session, "hinge_commit")
            return None
        self.open_palette(picks=reentrant)
        self.adapter.create_hinge.assert_not_called()

    def test_default_selection_command_does_not_remove_live_preview(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        self.ui.commandStarting.fire(SimpleNamespace(commandId="SelectCommand"))
        self.assertIs(session.preview, previous)
        self.assertTrue(previous.isValid)
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_navigation_never_deletes_or_rebuilds_current_preview(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        generation = session.generation
        for identity in ("OrbitCommand", "FreeOrbit", "ConstrainedOrbit", "PanCommand",
                         "ZoomCommand", "FitViewCommand", "ViewCubeCommand", "UnknownCameraCommand"):
            with self.subTest(identity=identity):
                self.ui.commandStarting.fire(SimpleNamespace(commandId=identity))
                self.assertIs(session.preview, previous)
                self.ui.commandTerminated.fire(SimpleNamespace(commandId=identity))
                self.assertIs(session.preview, previous)
                self.assertTrue(previous.isValid)
                self.assertEqual(session.generation, generation)
                self.assertTrue(self.owner.palette_state()["previewCurrent"])
        previous.deleteMe.assert_not_called()
        self.adapter.prepare_hinge.assert_called_once()
        self.adapter.preview_hinge.assert_called_once()
        self.assertEqual(self.adapter.validate_preview_sources.call_count, 8)
        self.adapter.create_hinge.assert_not_called()

    def test_cancelled_or_nonmutating_command_keeps_preview(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        self.ui.commandStarting.fire(SimpleNamespace(commandId="ExtrudeCommand"))
        self.ui.commandTerminated.fire(SimpleNamespace(commandId="ExtrudeCommand"))
        self.assertIs(session.preview, previous)
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        previous.deleteMe.assert_not_called()
        self.ui.terminateActiveCommand.assert_not_called()

    def test_changed_sources_clear_stale_preview_keep_picks_and_allow_refresh(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        self.adapter.validate_preview_sources.side_effect = ValueError("Source body changed")
        self.ui.commandStarting.fire(SimpleNamespace(commandId="ExtrudeCommand"))
        self.assertTrue(previous.isValid)
        self.ui.commandTerminated.fire(SimpleNamespace(commandId="ExtrudeCommand"))
        self.assertFalse(previous.isValid)
        self.assertFalse(self.owner.palette_state()["previewCurrent"])
        self.assertTrue(all(session.palette_snapshot()["selections"][name]["selected"]
                            for name in ("face_a", "face_b", "axis_edge")))
        self.assertEqual(session.phase, "error")
        self.assertIn("Source body changed", session.message)
        with self.assertRaisesRegex(ValueError, "hinge sources changed"):
            self.action(session, "hinge_commit")
        self.adapter.create_hinge.assert_not_called()
        self.adapter.validate_preview_sources.side_effect = None
        self.action(session, "hinge_preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertIsNot(session.preview, previous)
        self.ui.terminateActiveCommand.assert_not_called()

    def test_source_check_failure_invalidates_and_document_or_pick_actions_do_not_reenter(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        for identity in (self.module.CREATE_COMMAND_ID, self.module.EDIT_COMMAND_ID, self.module.PREVIEW_COMMAND_ID, "SelectCommand"):
            self.ui.commandTerminated.fire(SimpleNamespace(commandId=identity))
        self.owner._palette_action_busy = True
        self.ui.commandTerminated.fire(SimpleNamespace(commandId="OrbitCommand"))
        self.owner._palette_action_busy = False
        self.adapter.validate_preview_sources.assert_not_called()
        self.assertIs(session.preview, previous)
        self.adapter.validate_preview_sources.side_effect = RuntimeError("Native source read failed")
        self.ui.commandTerminated.fire(SimpleNamespace(commandId="UnknownCommand"))
        self.assertFalse(previous.isValid)
        self.assertEqual(session.phase, "error")
        self.assertIsNone(session.preview_sources)
        self.assertIn("could not be verified", session.message)

    def test_document_deactivate_closes_session_and_releases_graphics_and_references(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        self.module.adsk.core.Application.get().documentDeactivating.fire(SimpleNamespace())
        self.assertFalse(self.graphics[-1].isValid)
        self.assertFalse(self.owner._sessions)
        self.assertFalse(session.selection_entities)
        self.assertEqual(self.owner.palette_state()["phase"], "cancelled")
        self.ui.terminateActiveCommand.assert_not_called()

    def test_stop_removes_context_handlers_and_preview(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        app = self.module.adsk.core.Application.get()
        self.assertFalse(self.ui.commandStarting.handlers)
        self.assertEqual(len(self.ui.commandTerminated.handlers), 1)
        self.assertEqual(len(app.documentDeactivating.handlers), 1)
        self.owner.stop()
        self.assertFalse(self.ui.commandStarting.handlers)
        self.assertFalse(self.ui.commandTerminated.handlers)
        self.assertFalse(app.documentDeactivating.handlers)
        self.assertFalse(self.graphics[-1].isValid)
        self.assertFalse(self.owner._sessions)


if __name__ == "__main__":
    unittest.main()
