"""Queued native finishing lifecycle; fake events do not prove kernel validity."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_hinge_palette_command as palette_fakes
from Partelier.partelier.tools.hinge.settings import HingeSettings


class NativePreviewLifecycleTests(unittest.TestCase):
    setUp = palette_fakes.HingePaletteCommandTests.setUp
    tearDown = palette_fakes.HingePaletteCommandTests.tearDown
    native_commit = palette_fakes.HingePaletteCommandTests.native_commit
    open_palette = palette_fakes.HingePaletteCommandTests.open_palette
    action = palette_fakes.HingePaletteCommandTests.action

    def queued_preview(self, session, settings=None, revision=None):
        return self.owner.palette_action(
            "hinge_preview", session.session_id,
            revision=session.revision if revision is None else revision,
            settings_dict=(settings or session.palette_settings).to_dict())

    def test_finished_preview_waits_for_custom_event_then_rolls_back_before_drawing(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        order = self.compute_order
        original_prepare = self.adapter.prepare_hinge.side_effect
        original_draw = self.adapter.preview_hinge.side_effect

        def preparing(*arguments, **keywords):
            self.assertEqual(self.ui.activeCommand, self.module.PREVIEW_COMMAND_ID)
            self.assertFalse(self.inside_created)
            self.assertIs(keywords["edge_finisher"], self.module.finish_native_results)
            return original_prepare(*arguments, **keywords)

        def drawing(prepared):
            self.assertEqual(order[-1], "destroy", "graphics require detached post-rollback bodies")
            return original_draw(prepared)

        self.adapter.prepare_hinge.side_effect = preparing
        self.adapter.preview_hinge.side_effect = drawing
        queued = self.queued_preview(session)
        self.assertEqual(queued["phase"], "computing")
        self.assertFalse(queued["previewCurrent"])
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.preview_hinge.assert_not_called()
        command = self.compute_commands[0]
        self.assertFalse(command.isAutoExecute)
        self.assertFalse(command.isExecutedWhenPreEmpted)
        self.assertFalse(command.isRepeatable)
        self.assertFalse(command.isOKButtonVisible)
        self.assertEqual(command.commandInputs.items, {})
        command.doExecutePreview.assert_not_called()
        command.doExecute.assert_not_called()
        self.assertIsNone(session.command)
        self.assertIsNone(session.inputs)
        self.drain_native_preview_events()
        self.assertEqual(order, ["preview", "rollback", "execute", "destroy"])
        self.assertFalse(self.compute_preview_args[0].isValidResult)
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertEqual(session.phase, "preview")
        self.adapter.create_hinge.assert_not_called()
        self.adapter.rebuild_hinge.assert_not_called()
        self.assertFalse(self.owner._native_preview.busy)
        self.assertFalse(command.executePreview.handlers)
        self.assertFalse(command.execute.handlers)
        self.assertFalse(command.destroy.handlers)

    def test_completed_preview_then_edit_cancel_and_new_edit_session_reuse_runner_without_leaks(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        runner = self.owner._native_preview
        definition = runner._definition
        self.drain_native_preview_events()
        first_graphics = session.preview
        self.assertFalse(runner.busy)
        second = replace(session.palette_settings, length_mm=35)
        self.queued_preview(session, second, revision=1)
        self.assertTrue(first_graphics.isValid, "Keep graphics until the replacement has rolled back and drawn.")
        self.drain_native_preview_events()
        self.assertFalse(first_graphics.isValid)
        self.assertEqual(session.phase, "preview")
        self.assertFalse(runner.busy)
        self.assertIs(runner._definition, definition)
        self.queued_preview(session, replace(second, knuckle_count=3), revision=2)
        self.owner.palette_action("hinge_cancel", session.session_id)
        self.assertTrue(session.closed)
        # Picking a new session starts only after the cancelled native command
        # receives its queued rollback/Destroy and releases Fusion ownership.
        self.drain_native_preview_events()
        self.assertFalse(runner.busy)
        edit_settings = HingeSettings(chamfer_edges=True)
        self.adapter.read_edit_target.return_value = SimpleNamespace(settings=edit_settings,
            face_a=self.entities["face_a"], face_b=self.entities["face_b"], axis_edge=self.entities["axis_edge"])
        editing = self.open_palette(editing=True)
        self.assertNotEqual(editing.session_id, session.session_id)
        self.queued_preview(editing)
        self.drain_native_preview_events()
        self.assertIs(self.owner._native_preview, runner)
        self.assertEqual(editing.phase, "preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertEqual(self.adapter.prepare_hinge.call_count, 2)
        self.adapter.prepare_edit_hinge.assert_called_once()
        self.assertEqual(self.adapter.prepare_edit_hinge.call_args.args[2], edit_settings)
        self.assertEqual(len(self.compute_commands), 4)
        self.assertFalse(runner.busy)
        self.assertIsNone(runner._current)
        self.assertIsNone(runner._pending)
        self.assertEqual(len(self.custom_events), 1)
        self.assertEqual(len(definition.commandCreated.handlers), 1)
        self.assertTrue(all(not command.executePreview.handlers and not command.execute.handlers
                            and not command.destroy.handlers for command in self.compute_commands))
        self.assertEqual(sum(group.isValid for group in self.graphics), 1)
        self.adapter.create_hinge.assert_not_called()
        self.adapter.rebuild_hinge.assert_not_called()

    def test_a_session_closed_during_its_state_push_cannot_queue_new_native_work(self):
        runner=self.module.NativePreviewRunner(self.logs.append)
        compute,done,failed=Mock(),Mock(),Mock()
        runner.request(SimpleNamespace(closed=True),compute,done,failed)
        runner.request(SimpleNamespace(cancel_requested=True),compute,done,failed)
        self.assertFalse(runner.busy);self.assertIsNone(runner._definition)
        self.assertEqual(self.compute_commands,[])
        compute.assert_not_called();done.assert_not_called();failed.assert_not_called()

    def test_new_request_between_destroy_and_queued_next_supersedes_older_pending_work(self):
        runner = self.module.NativePreviewRunner(self.logs.append)
        self.addCleanup(runner.stop)
        old_compute, pending_compute, newest_compute = Mock(return_value="old"), Mock(return_value="pending"), Mock(return_value="newest")
        old_done, pending_done, newest_done, failed = Mock(), Mock(), Mock(), Mock()
        runner.request(object(), old_compute, old_done, failed)
        runner.request(object(), pending_compute, pending_done, failed)
        identity, information = self.custom_queue.pop(0)
        self.custom_events[identity].fire(SimpleNamespace(additionalInfo=information))
        self.assertIsNone(runner._current)
        self.assertIsNotNone(runner._pending)
        self.assertEqual(self.custom_queue[-1][1], "next")
        runner.request(object(), newest_compute, newest_done, failed)
        self.drain_native_preview_events()
        old_compute.assert_not_called()
        pending_compute.assert_not_called()
        old_done.assert_not_called()
        pending_done.assert_not_called()
        newest_compute.assert_called_once_with()
        newest_done.assert_called_once_with("newest")
        failed.assert_not_called()
        self.assertFalse(runner.busy)
        self.assertEqual(len(self.compute_commands), 2)

    def test_destroy_handler_is_bound_before_preview_and_execute_handlers(self):
        session = self.open_palette(HingeSettings(chamfer_edges=True))
        original_command = palette_fakes.native_fakes.Command
        observed = []
        def command_factory():
            command = original_command()
            for name in ("destroy", "executePreview", "execute"):
                event = getattr(command, name)
                original_add = event.add
                def add(handler, name=name, original_add=original_add):
                    observed.append(name)
                    return original_add(handler)
                event.add = add
            return command
        with patch.object(palette_fakes.native_fakes, "Command", side_effect=command_factory):
            self.queued_preview(session)
        self.assertEqual(observed, ["destroy", "executePreview", "execute"])
        self.adapter.prepare_hinge.assert_not_called()
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertFalse(self.owner._native_preview.busy)

    def test_two_consecutive_false_launches_report_errors_and_retry_can_complete(self):
        session = self.open_palette(HingeSettings(chamfer_edges=True))
        self.action(session, "hinge_preview")
        previous = session.preview
        original_hook = self.ui.commandDefinitions.execute_hook
        self.ui.commandDefinitions.execute_hook = lambda definition: False
        updated = replace(session.palette_settings, length_mm=35)
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "could not start"):
                self.queued_preview(session, updated, revision=1)
            self.assertEqual(session.phase, "error")
            self.assertIsNone(self.owner._native_preview)
            self.assertIsNone(session._native_preview_generation)
            self.assertTrue(previous.isValid)
            self.assertFalse(self.custom_events)
        self.ui.commandDefinitions.execute_hook = original_hook
        self.queued_preview(session)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertFalse(previous.isValid)
        self.assertEqual(self.adapter.prepare_hinge.call_count, 2)
        self.assertFalse(self.owner._native_preview.busy)

    def test_each_refused_command_binding_closes_empty_command_and_next_request_recovers(self):
        original_command = palette_fakes.native_fakes.Command
        for event_name in ("destroy", "executePreview", "execute"):
            with self.subTest(event=event_name):
                session = self.open_palette(HingeSettings(fillet_edges=True))
                self.adapter.prepare_hinge.reset_mock()
                self.adapter.preview_hinge.reset_mock()
                def refused():
                    command = original_command()
                    getattr(command, event_name).add = Mock(return_value=False)
                    return command
                with patch.object(palette_fakes.native_fakes, "Command", side_effect=refused):
                    self.queued_preview(session)
                self.drain_native_preview_events()
                failed_command = self.compute_commands[-1]
                self.assertEqual(session.phase, "error")
                self.assertIn("attach", session.preview_error)
                self.assertFalse(self.owner._native_preview.busy)
                self.assertIsNone(session._native_preview_generation)
                self.assertIsNone(self.active_compute)
                self.assertTrue(failed_command.isAutoExecute)
                failed_command.doExecutePreview.assert_not_called()
                self.adapter.prepare_hinge.assert_not_called()
                self.adapter.preview_hinge.assert_not_called()
                self.assertFalse(failed_command.destroy.handlers)
                self.queued_preview(session)
                self.drain_native_preview_events()
                self.assertEqual(session.phase, "preview")
                self.assertTrue(self.owner.palette_state()["previewCurrent"])
                self.assertFalse(self.owner._native_preview.busy)
                self.adapter.prepare_hinge.assert_called_once()
                session.close()

    def test_refused_created_binding_cleans_definition_and_registration_then_retries(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        original_add = self.ui.commandDefinitions.addButtonDefinition
        def refused(identity, *args):
            definition = original_add(identity, *args)
            if identity == self.module.PREVIEW_COMMAND_ID:
                definition.commandCreated.add = Mock(return_value=False)
            return definition
        with patch.object(self.ui.commandDefinitions, "addButtonDefinition", side_effect=refused):
            with self.assertRaisesRegex(RuntimeError, "command-created handler"):
                self.queued_preview(session)
        self.assertEqual(session.phase, "error")
        self.assertIsNone(self.owner._native_preview)
        self.assertIsNone(self.ui.commandDefinitions.itemById(self.module.PREVIEW_COMMAND_ID))
        self.assertFalse(self.custom_events)
        self.assertFalse(self.compute_commands)
        self.adapter.prepare_hinge.assert_not_called()
        self.queued_preview(session)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertFalse(self.owner._native_preview.busy)

    def test_invalid_inactive_orphan_is_released_and_late_destroy_cannot_clear_replacement(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        runner = self.owner._native_preview
        old_request, old_command = runner._current, self.compute_commands[-1]
        old_command.isValid = False
        self.ui.activeCommand = "UnrelatedUserCommand"
        newest = replace(session.palette_settings, length_mm=35)
        self.queued_preview(session, newest, revision=1)
        replacement, replacement_command = runner._current, runner._command
        self.assertIsNot(replacement, old_request)
        self.assertIsNot(replacement_command, old_command)
        handlers = tuple(runner._handlers)
        runner.destroyed(old_request)
        self.assertIs(runner._current, replacement)
        self.assertIs(runner._command, replacement_command)
        self.assertEqual(tuple(runner._handlers), handlers)
        self.assertFalse(old_command.destroy.handlers)
        self.ui.terminateActiveCommand.assert_not_called()
        self.drain_native_preview_events()
        self.adapter.prepare_hinge.assert_called_once()
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], newest)
        self.assertEqual(session.phase, "preview")
        self.assertFalse(runner.busy)

    def test_valid_inactive_failed_command_remains_owned_until_delayed_destroy_then_next_runs(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        runner, old_command = self.owner._native_preview, self.compute_commands[-1]
        old_request = runner._current
        old_command.doExecutePreview.side_effect = RuntimeError("Native preview command failed")
        self.ui.activeCommand = "UnrelatedUserCommand"
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "error")
        self.assertTrue(runner.busy)
        latest = replace(session.palette_settings, length_mm=35)
        self.queued_preview(session, latest, revision=1)
        self.assertIs(runner._current, old_request)
        self.assertIs(runner._command, old_command)
        self.assertIsNotNone(runner._pending)
        self.assertFalse(self.custom_queue)
        self.ui.terminateActiveCommand.assert_not_called()
        self.adapter.prepare_hinge.assert_not_called()
        # Native Destroy may arrive after activeCommand has already changed.
        # This ownership proof, rather than an arbitrary timeout, releases work.
        self.terminate_compute_command()
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertFalse(runner.busy)
        self.adapter.prepare_hinge.assert_called_once()
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], latest)

    def test_sharp_preview_keeps_direct_nonmutating_fast_path(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        self.assertEqual(session.phase, "preview")
        self.assertFalse(self.compute_commands)
        self.assertFalse(self.custom_events)
        self.assertIsNone(self.owner._native_preview)
        self.assertEqual(self.adapter.prepare_hinge.call_args.kwargs, {})

    def test_latest_revision_wins_without_computing_superseded_requests(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        second = replace(session.palette_settings, knuckle_count=3)
        self.queued_preview(session, second, revision=1)
        newest = replace(second, knuckle_profile="square", fillet_radius_mm=.4)
        self.queued_preview(session, newest, revision=2)
        self.drain_native_preview_events()
        self.adapter.prepare_hinge.assert_called_once()
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], newest)
        self.assertEqual(len(self.compute_commands), 2, "only old cancellation and latest calculation launch")
        self.assertEqual(session.phase, "preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertEqual(self.owner.palette_state()["revision"], 2)

    def test_stale_completion_cannot_clear_the_latest_pending_generation(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        old_generation = session.generation
        latest = replace(session.palette_settings, knuckle_count=3)
        self.queued_preview(session, latest, revision=1)
        session._complete_native_preview(self.prepared, 0, old_generation)
        self.assertEqual(session._native_preview_generation, session.generation)
        self.adapter.preview_hinge.assert_not_called()
        self.drain_native_preview_events()
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_switching_to_sharp_waits_for_cancelled_compute_command_to_close(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        sharp = replace(session.palette_settings, fillet_edges=False)
        queued = self.queued_preview(session, sharp, revision=1)
        self.assertEqual(queued["phase"], "computing")
        self.adapter.prepare_hinge.assert_not_called()
        self.drain_native_preview_events()
        self.adapter.prepare_hinge.assert_called_once()
        self.assertEqual(self.adapter.prepare_hinge.call_args.kwargs, {})
        self.assertEqual(self.adapter.prepare_hinge.call_args.args[4], sharp)
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_cancel_before_driver_runs_never_computes_or_resurrects_graphics(self):
        session = self.open_palette(HingeSettings(chamfer_edges=True))
        self.queued_preview(session)
        self.owner.palette_action("hinge_cancel", session.session_id)
        self.drain_native_preview_events()
        self.assertTrue(session.closed)
        self.assertEqual(self.owner.palette_state()["phase"], "cancelled")
        self.assertFalse(self.graphics)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_document_deactivation_discards_pending_native_preview(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        self.application.documentDeactivating.fire(SimpleNamespace())
        self.drain_native_preview_events()
        self.assertTrue(session.closed)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.preview_hinge.assert_not_called()
        self.assertEqual(self.owner.palette_state()["phase"], "cancelled")

    def test_failed_finish_rolls_back_and_preserves_old_graphics_then_retries(self):
        session = self.open_palette()
        self.action(session, "hinge_preview")
        previous = session.preview
        original_prepare = self.adapter.prepare_hinge.side_effect
        self.adapter.prepare_hinge.side_effect = ValueError("The requested joined fillet cannot fit.")
        finished = replace(session.palette_settings, fillet_edges=True)
        self.queued_preview(session, finished, revision=1)
        self.assertTrue(previous.isValid)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "error")
        self.assertTrue(previous.isValid)
        self.assertIn("requested joined fillet", session.preview_error)
        self.assertFalse(self.owner.palette_state()["previewCurrent"])
        self.assertEqual(self.compute_order, ["preview", "rollback", "execute", "destroy"])
        self.adapter.prepare_hinge.side_effect = original_prepare
        self.queued_preview(session)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertFalse(previous.isValid)
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_preemption_after_calculation_never_publishes_unconfirmed_preview(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        command = self.compute_commands[0]
        command.doExecutePreview()
        self.assertFalse(self.compute_preview_args[-1].isValidResult)
        self.terminate_compute_command()
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "error")
        self.assertIn("interrupted", session.preview_error)
        self.adapter.preview_hinge.assert_not_called()
        self.adapter.create_hinge.assert_not_called()

    def test_refused_driver_calls_abort_owned_command_and_report_failure(self):
        for operation in ("doExecutePreview", "doExecute"):
            session = self.open_palette(HingeSettings(fillet_edges=True))
            self.queued_preview(session)
            command = self.compute_commands[-1]
            method = getattr(command, operation)
            method.side_effect = None
            method.return_value = False
            self.drain_native_preview_events()
            self.assertEqual(session.phase, "error")
            self.assertIsNone(self.active_compute)
            self.assertFalse(self.owner._native_preview.busy)
            self.adapter.preview_hinge.assert_not_called()
            session.close()

    def test_stop_cancels_pending_work_and_removes_owned_driver_handlers(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        runner = self.owner._native_preview
        definition = self.ui.commandDefinitions.itemById(self.module.PREVIEW_COMMAND_ID)
        self.owner.stop()
        self.drain_native_preview_events()
        self.assertTrue(session.closed)
        self.assertFalse(runner.busy)
        self.assertFalse(self.custom_events)
        self.assertFalse(definition.isValid)
        self.assertFalse(definition.commandCreated.handlers)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.preview_hinge.assert_not_called()
        self.assertFalse(self.compute_commands[0].destroy.handlers)

    def test_registered_event_identity_and_command_ids_are_frozen_per_runner(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        register = self.application.registerCustomEvent
        observed = []

        def registered_identity(requested):
            event = register(requested)
            event.eventId = requested + "_registered"
            self.custom_events.pop(requested)
            self.custom_events[event.eventId] = event
            return event

        def fire_registered(identity, information):
            observed.append(identity)
            if identity not in self.custom_events:
                return False
            self.custom_queue.append((identity, information))
            return True

        self.application.registerCustomEvent = registered_identity
        self.application.fireCustomEvent = Mock(side_effect=fire_registered)
        self.queued_preview(session)
        runner = self.owner._native_preview
        self.assertEqual(runner._event_id, runner._requested_event_id + "_registered")
        self.assertEqual(observed, [runner._event_id])
        globals_ = runner.__class__.__init__.__globals__
        with patch.dict(globals_, {"PREVIEW_EVENT_ID": "another_runner_event",
                                  "PREVIEW_COMMAND_ID": "another_runner_command"}):
            self.drain_native_preview_events()
            self.assertEqual(session.phase, "preview")
            self.assertTrue(self.owner.palette_state()["previewCurrent"])
            self.owner.stop()
            self.assertFalse(self.custom_events)

    def test_refused_custom_event_handler_registration_never_launches_compute(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        register = self.application.registerCustomEvent

        def refuse_handler(identity):
            event = register(identity)
            event.add = Mock(return_value=False)
            return event

        self.application.registerCustomEvent = refuse_handler
        with self.assertRaisesRegex(RuntimeError, "attach.*event driver"):
            self.queued_preview(session)
        self.assertFalse(self.compute_commands)
        self.assertFalse(self.custom_events)
        self.assertIsNone(self.owner._native_preview)
        self.adapter.prepare_hinge.assert_not_called()

    def test_false_queue_return_still_delivers_preview_after_command_created(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))

        def enqueue_but_return_false(identity, information):
            self.custom_queue.append((identity, information))
            return False

        self.application.fireCustomEvent = Mock(side_effect=enqueue_but_return_false)
        queued = self.queued_preview(session)
        command = self.compute_commands[-1]
        self.assertEqual(queued["phase"], "computing")
        self.assertFalse(command.isAutoExecute, "False is not a native queue error")
        command.doExecutePreview.assert_not_called()
        command.doExecute.assert_not_called()
        self.adapter.prepare_hinge.assert_not_called()
        self.assertFalse(self.inside_created)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])
        self.assertEqual(self.compute_order, ["preview", "rollback", "execute", "destroy"])
        self.assertFalse(any("queue" in entry.lower() or "failed" in entry.lower() for entry in self.logs),
                         "known native queue behavior must not log an error")

    def test_custom_event_queue_exception_closes_empty_command_after_creation(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.application.fireCustomEvent = Mock(side_effect=RuntimeError("Native queue call failed"))
        self.queued_preview(session)
        self.assertEqual(session.phase, "error")
        self.assertIn("queue", session.preview_error)
        self.assertIn("requested event=", session.preview_error)
        self.assertIn("registered event=", session.preview_error)
        self.assertFalse(self.inside_created)
        self.assertIsNone(self.active_compute)
        self.assertFalse(self.owner._native_preview.busy)
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.preview_hinge.assert_not_called()
        self.assertEqual(self.compute_order, ["rollback", "execute", "destroy"])

    def test_registration_failure_has_no_model_writes_and_can_retry(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        register = self.application.registerCustomEvent
        self.application.registerCustomEvent = Mock(return_value=None)
        with self.assertRaisesRegex(RuntimeError, "register"):
            self.queued_preview(session)
        self.assertEqual(session.phase, "error")
        self.assertIsNone(self.owner._native_preview)
        self.assertFalse(self.compute_commands)
        self.adapter.prepare_hinge.assert_not_called()
        self.application.registerCustomEvent = register
        self.queued_preview(session)
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "preview")

    def test_failed_owned_command_termination_reports_error_without_showing_result(self):
        session = self.open_palette(HingeSettings(fillet_edges=True))
        self.queued_preview(session)
        command = self.compute_commands[-1]
        command.doExecutePreview.side_effect = RuntimeError("Native preview driver failed")
        self.ui.terminateActiveCommand.side_effect = RuntimeError("Native terminate failed")
        self.drain_native_preview_events()
        self.assertEqual(session.phase, "error")
        self.assertIn("Native preview driver failed", session.preview_error)
        self.adapter.preview_hinge.assert_not_called()
        self.assertTrue(self.owner._native_preview.busy, "failed native command remains owned")
        self.ui.terminateActiveCommand.side_effect = self.terminate_compute_command
        self.owner.stop()
        self.assertIsNone(self.active_compute)

    def test_native_create_and_legacy_preview_use_identical_joined_finish_callback(self):
        for finish in ("fillet", "chamfer"):
            settings = HingeSettings(fillet_edges=finish == "fillet",
                                     chamfer_edges=finish == "chamfer")
            session = self.open_palette(settings)
            self.action(session, "hinge_preview")
            preview_callback = self.adapter.prepare_hinge.call_args.kwargs["edge_finisher"]
            self.action(session, "hinge_commit")
            self.assertIs(self.adapter.prepare_hinge.call_args.kwargs["edge_finisher"], preview_callback)
            self.assertIs(preview_callback, self.module.finish_native_results)
        # Direct legacy command preview already has its own host transaction.
        self.ui.commandDefinitions.itemById(self.module.CREATE_COMMAND_ID).execute.side_effect = None
        command, session = palette_fakes.native_fakes.HingeCommandContractTests.open_command(
            self, settings={"fillet_edges": True})
        palette_fakes.native_fakes.HingeCommandContractTests.select_sources(self, session)
        command.executePreview.fire(SimpleNamespace(isValidResult=True))
        self.assertIs(self.adapter.prepare_hinge.call_args.kwargs["edge_finisher"],
                      self.module.finish_native_results)


if __name__ == "__main__":
    unittest.main()
