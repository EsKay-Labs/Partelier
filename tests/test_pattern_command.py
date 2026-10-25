"""Pattern session contracts with detached results and a controlled rollback runner.

These fakes verify ownership and event ordering, not native surface geometry.
The shared native rollback driver has its own lifecycle tests.
"""

from dataclasses import replace
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools import patterns as package


class Event:
    def __init__(self):
        self.handlers = []
        self.fail_add = False
        self.raise_add = False

    def add(self, handler):
        if self.fail_add:
            return False
        self.handlers.append(handler)
        if self.raise_add:
            raise RuntimeError("partial event binding failure")
        return True

    def remove(self, handler):
        self.handlers.remove(handler)


class Collection:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]

    def add(self, value):
        self.values.append(value)
        return True

    @property
    def all(self):
        return Collection([value.entity for value in self.values])

    @all.setter
    def all(self, entities):
        self.values = [NS(entity=entity) for entity in entities.values]


class Group:
    def __init__(self):
        self.isValid = True
        self.fail_delete = False
        self.delete_count = 0

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
            raise ValueError("visibility restore needs retry")
        for body, visible in self.original.values():
            body.isLightBulbOn = visible
        self.original.clear()


class Runner:
    """Hold callbacks until an explicit rollback boundary, including old work."""
    def __init__(self):
        self.jobs = []
        self.current = None
        self.order = []
        self.stopped = False

    @property
    def busy(self):
        return self.current is not None or bool(self.jobs)

    def request(self, owner, compute, completed, failed):
        self.jobs.append(NS(owner=owner, compute=compute, completed=completed,
                            failed=failed, cancelled=False, result=None, error=None))
        self.order.append("requested")

    def compute(self):
        self.current = self.jobs.pop(0)
        self.order.append("compute")
        try:
            self.current.result = self.current.compute()
        except Exception as error:
            self.current.error = error
        return self.current

    def rollback(self):
        job, self.current = self.current, None
        self.order.append("rollback")
        if not job.cancelled:
            if job.error is None:
                job.completed(job.result)
            else:
                job.failed(job.error)
        return job

    def finish(self):
        self.compute()
        return self.rollback()

    def cancel(self, owner):
        for job in self.jobs + ([self.current] if self.current else []):
            if job.owner is owner:
                job.cancelled = True

    def stop(self):
        self.jobs.clear()
        self.current = None
        self.stopped = True


class PatternCommandTests(unittest.TestCase):
    def setUp(self):
        self.definitions = {}
        def add(identity, *arguments):
            value = NS(id=identity, isValid=True, commandCreated=Event(), execute=Mock(return_value=True))
            def delete():
                value.isValid = False
                self.definitions.pop(identity, None)
                return True
            value.deleteMe = delete
            self.definitions[identity] = value
            return value
        self.picks = []
        self.ui = NS(commandDefinitions=NS(itemById=self.definitions.get, addButtonDefinition=add),
                     activeCommand="SelectCommand", activeSelectionChanged=Event(), commandStarting=Event(), commandTerminated=Event(), terminateActiveCommand=Mock(),
                     activeSelections=Collection(), selectEntity=Mock(side_effect=lambda *args: self.picks.pop(0)))
        self.select_definition=NS()
        self.custom_events={};self.native_queue=[]
        def activate_select():
            for handler in tuple(self.ui.commandStarting.handlers):handler.notify(NS(commandId='SelectCommand'))
            self.ui.activeCommand='SelectCommand'
            while self.native_queue:
                identity=self.native_queue.pop(0)
                for handler in tuple(self.custom_events.get(identity,Event()).handlers):handler.notify(NS())
            return True
        self.select_definition.execute=Mock(side_effect=activate_select)
        self.ui.commandDefinitions.itemById=lambda identity:self.select_definition if identity=='SelectCommand' else self.definitions.get(identity)
        self.design = NS(isValid=True)
        self.app = NS(userInterface=self.ui, activeProduct=self.design, documentDeactivating=Event(), log=Mock())
        self.app.registerCustomEvent=lambda identity:self.custom_events.setdefault(identity,Event())
        self.app.unregisterCustomEvent=lambda identity:self.custom_events.pop(identity,None)
        self.app.fireCustomEvent=lambda identity,*args:self.native_queue.append(identity) or True
        core, native, adsk = ModuleType("adsk.core"), ModuleType("adsk.fusion"), ModuleType("adsk")
        core.Application = NS(get=lambda: self.app)
        for name in ("CommandCreatedEventHandler", "CommandEventHandler", "DocumentEventHandler", "ApplicationCommandEventHandler", "ActiveSelectionEventHandler", "CustomEventHandler"):
            setattr(core, name, object)
        core.ObjectCollection = NS(create=Collection)
        native.Design = NS(cast=lambda value: value)
        native.BRepFace = NS(cast=lambda value: value if getattr(value, "kind", None) == "face" else None)
        native.BRepBody = NS(cast=lambda value: value if getattr(value, "kind", None) == "body" else None)
        adsk.core, adsk.fusion = core, native
        self.fusion = ModuleType(package.__name__ + ".fusion")
        self.recipe = ModuleType(package.__name__ + ".recipe")
        self.recipe.edit_notice = Mock(return_value='')
        preview = ModuleType(package.__name__ + ".preview")
        preview.PatternPreviewRunner = Runner
        for name in ("prepare_pattern", "preview_pattern", "preview_hide_bodies"):
            setattr(self.fusion, name, Mock(name=name))
        for name in ("read_edit_target", "prepare_edit_pattern", "validate_preview_sources", "create_pattern", "rebuild_pattern"):
            setattr(self.recipe, name, Mock(name=name))
        path = Path(__file__).parents[1] / "Partelier/partelier/tools/patterns/command.py"
        spec = importlib.util.spec_from_file_location(package.__name__ + "._command_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"adsk": adsk, "adsk.core": core, "adsk.fusion": native,
                        self.fusion.__name__: self.fusion, self.recipe.__name__: self.recipe,
                        preview.__name__: preview}), patch.object(package, "fusion", self.fusion, create=True), patch.object(package, "recipe", self.recipe, create=True):
            spec.loader.exec_module(self.module)
            selection_spec=importlib.util.spec_from_file_location(package.__name__+'._face_selection_test',path.with_name('face_selection.py'))
            selection_module=importlib.util.module_from_spec(selection_spec)
            selection_spec.loader.exec_module(selection_module)
            self.module.FaceSelection=selection_module.FaceSelection
        self.module.BodyVisibilityLease = Lease
        self.module.display_export = NS(prepare=Mock(side_effect=lambda prepared:prepared))
        self.manager = self.module.PatternCommands()
        self.manager.start()
        self.body = NS(kind="body", isValid=True, name="Cylinder", isLightBulbOn=True)
        self.faces = tuple(NS(kind="face", isValid=True, name="Face " + str(index), body=self.body) for index in range(3))
        self.body.faces = Collection(self.faces)
        self.prepared = []
        def prepare(design, faces, settings):
            value = NS(design=design, body=self.body, faces=faces, settings=settings, cell_count=24,
                       result_body=NS(isTemporary=True), record=None,
                       layouts=(NS(cell_count=24,cell_size_mm=12.5,effective_pitch_mm=20,proposals_evaluated=16,acceptance_checks=24),))
            self.prepared.append(value)
            return value
        self.fusion.prepare_pattern.side_effect = prepare
        self.recipe.prepare_edit_pattern.side_effect = lambda design, target, settings: prepare(design, self.faces, settings)
        self.fusion.preview_hide_bodies.return_value = (self.body,)
        def draw(prepared):
            self.assertEqual(self.manager.runner.order[-1], "rollback", "drawing waits for the owned native rollback")
            return Group()
        self.fusion.preview_pattern.side_effect = draw

    def tearDown(self):
        if self.manager._session:
            self.manager._session.visibility.fail_restore = False
            if self.manager._session.preview:
                self.manager._session.preview.fail_delete = False
        self.manager.stop()

    def begin(self, settings=None, editing=False, finish=True):
        self.ui.activeSelections = Collection([NS(entity=self.body)] if editing else [NS(entity=face) for face in self.faces])
        self.manager.begin_palette((settings or PatternSettings()).to_dict(), editing=editing)
        session=self.manager._session
        if finish and session.face_picker is not None:self.action(session,'pattern_finish_faces')
        return session

    def action(self, session, action, settings=None, revision=None, **kwargs):
        return self.manager.palette_action(action, session.session_id,
            revision=session.revision if revision is None else revision,
            settings_dict=(settings or session.settings).to_dict(), **kwargs)

    def preview(self, session):
        queued = self.action(session, "pattern_preview")
        self.manager.runner.finish()
        return queued

    def native_command(self, session):
        command = NS(execute=Event(), destroy=Event())
        self.module._Created(self.manager).notify(NS(command=command))
        return command

    def test_truss_preview_message_and_commit_use_the_reviewed_result(self):
        make=self.fusion.prepare_pattern.side_effect
        def prepare(*args):
            value=make(*args);value.cell_count=7
            value.timings={'truss_bay_span_mm':19,'truss_open_area_percent':70}
            return value
        self.fusion.prepare_pattern.side_effect=prepare
        session=self.begin(PatternSettings(pattern='truss_warren',layout_mode='fill',web_mm=2,border_mm=3))
        self.preview(session)
        self.assertEqual(session.phase,'preview')
        self.assertIn('6 bays · 7 windows',session.message)
        self.assertIn('19.00 mm',session.message)
        reviewed=session.prepared
        self.action(session,'pattern_commit');command=self.native_command(session)
        command.execute.handlers[0].notify(NS(executeFailed=False))
        self.recipe.create_pattern.assert_called_once_with(self.design,reviewed)

    def test_register_once_and_stop_only_owned_events_and_runner(self):
        self.manager.start()
        self.assertEqual(len(self.definitions), 1)
        self.assertEqual(len(self.app.documentDeactivating.handlers), 1)
        self.assertEqual(len(self.ui.commandTerminated.handlers), 1)
        self.manager.stop()
        self.assertFalse(self.definitions)
        self.assertFalse(self.app.documentDeactivating.handlers)
        self.assertTrue(self.manager.runner.stopped)
        self.ui.terminateActiveCommand.assert_not_called()

    def test_multiple_preselected_faces_are_loaded_without_native_panel(self):
        session = self.begin(finish=False)
        self.assertEqual(session.faces, self.faces)
        self.assertEqual(session.snapshot()["selections"]["surface"]["label"], "3 face(s) on Cylinder")
        self.assertEqual(session.phase, "picking_faces")
        self.ui.selectEntity.assert_not_called()
        self.fusion.prepare_pattern.assert_not_called()
        self.manager._registration[0].execute.assert_not_called()
        self.action(session,'pattern_finish_faces')
        self.assertEqual(session.phase,'ready')

    def test_done_before_deferred_highlighting_keeps_all_clicked_faces(self):
        self.manager.begin_palette(PatternSettings().to_dict())
        session=self.manager._session
        self.select_native(self.faces[:1])
        self.select_native(self.faces[1:2])
        self.assertTrue(session.face_picker.paint_pending)
        self.action(session,'pattern_finish_faces')
        self.drain_native()
        self.assertEqual(session.faces,self.faces[:2])
        self.assertFalse(self.custom_events)
        self.fusion.prepare_pattern.assert_not_called()

    def test_cancel_with_pending_highlight_does_not_restore_retired_faces(self):
        self.manager.begin_palette(PatternSettings().to_dict())
        session=self.manager._session
        self.select_native(self.faces[:1])
        self.select_native(self.faces[1:2])
        self.action(session,'pattern_cancel')
        self.drain_native()
        self.assertEqual(self.ui.activeSelections.count,0)
        self.assertFalse(self.custom_events)
        self.assertFalse(self.ui.activeSelectionChanged.handlers)

    def test_initial_normal_clicks_accumulate_and_only_done_allows_preview(self):
        state=self.manager.begin_palette(PatternSettings().to_dict())
        session=self.manager._session
        self.assertTrue(state['pickingFaces'])
        self.assertFalse(state['canFinishFaces'])
        self.ui.selectEntity.assert_not_called()
        self.select_native(self.faces[:1])
        self.select_native(self.faces[1:2])
        self.drain_native()
        self.assertEqual(session.faces,self.faces[:2])
        self.assertEqual([v.entity for v in self.ui.activeSelections.values],list(self.faces[:2]))
        self.fusion.prepare_pattern.assert_not_called()
        self.assertFalse(self.manager.runner.busy)
        with self.assertRaisesRegex(ValueError,'Done'):self.action(session,'pattern_preview')
        self.action(session,'pattern_finish_faces')
        self.preview(session)
        self.assertEqual(session.prepared.faces,self.faces[:2])

    def drain_native(self):
        while self.native_queue:
            identity=self.native_queue.pop(0)
            for handler in tuple(self.custom_events.get(identity,Event()).handlers):handler.notify(NS())

    def select_native(self, entities):
        self.ui.activeSelections.all=Collection(entities)
        for handler in tuple(self.ui.activeSelectionChanged.handlers):
            handler.notify(NS(currentSelection=self.ui.activeSelections.values))

    def test_add_faces_is_non_modal_highlights_seeds_and_finishes_once(self):
        self.ui.activeSelections=Collection([NS(entity=self.faces[0])])
        self.manager.begin_palette(PatternSettings().to_dict())
        session=self.manager._session
        self.action(session,'pattern_finish_faces')
        self.preview(session)
        result=self.action(session,'pattern_focus',target='add_face')
        self.assertTrue(result['pickingFaces'])
        self.assertTrue(result['canFinishFaces'])
        self.assertFalse(self.manager.busy)
        self.assertTrue(self.body.isLightBulbOn)
        self.ui.selectEntity.assert_not_called()
        self.assertEqual([value.entity for value in self.ui.activeSelections.values],list(self.faces[:1]))
        self.select_native(self.faces)
        self.assertEqual(session.faces,self.faces)
        self.assertEqual(len(self.prepared),1,'native picks do not trigger geometry computation')
        result=self.action(session,'pattern_finish_faces')
        self.assertFalse(result['pickingFaces'])
        self.assertEqual(result['phase'],'ready')
        self.assertFalse(self.ui.activeSelectionChanged.handlers)
        self.preview(session)
        self.assertEqual(session.prepared.faces,self.faces)

    def test_picker_reactivates_select_after_preview_leaves_no_command(self):
        session=self.begin()
        self.preview(session)
        self.ui.activeCommand=''
        self.action(session,'pattern_focus',target='add_face')
        self.select_definition.execute.assert_called_once()
        self.assertEqual(self.ui.activeCommand,'SelectCommand')
        self.assertFalse(self.manager.busy)

    def test_done_reads_native_selection_even_when_event_was_not_delivered(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        session.faces=self.faces[:1]
        self.ui.activeSelections.all=Collection(self.faces[:2])
        self.assertEqual(session.faces,self.faces[:1],'no callback was sent')
        self.action(session,'pattern_finish_faces')
        self.assertEqual(session.faces,self.faces[:2])
        self.preview(session)
        self.assertEqual(session.prepared.faces,self.faces[:2])

    def test_cancel_while_waiting_for_native_select_removes_activation_hooks(self):
        session=self.begin()
        self.ui.activeCommand=''
        self.select_definition.execute.side_effect=None
        self.select_definition.execute.return_value=True
        result=self.action(session,'pattern_focus',target='add_face')
        self.assertTrue(result['pickingFaces'])
        self.assertFalse(result['canFinishFaces'])
        self.assertTrue(self.custom_events)
        self.assertTrue(self.ui.commandStarting.handlers)
        self.action(session,'pattern_cancel')
        self.assertFalse(self.custom_events)
        self.assertFalse(self.ui.commandStarting.handlers)
        self.assertFalse(self.ui.activeSelectionChanged.handlers)
        self.assertIsNone(self.manager._session)

    def test_done_waits_for_activation_instead_of_using_stale_seed_faces(self):
        session=self.begin()
        self.ui.activeCommand=''
        self.select_definition.execute.side_effect=None
        self.select_definition.execute.return_value=True
        self.action(session,'pattern_focus',target='add_face')
        with self.assertRaisesRegex(ValueError,'Wait for Fusion face selection'):
            self.action(session,'pattern_finish_faces')
        self.assertFalse(session.snapshot()['canFinishFaces'])
        self.assertFalse(self.manager.busy)
        self.action(session,'pattern_cancel')

    def test_picker_does_not_interrupt_an_unrelated_modeling_command(self):
        session=self.begin()
        self.ui.activeCommand='ExtrudeCommand'
        with self.assertRaisesRegex(ValueError,'Finish the active Fusion command'):
            self.action(session,'pattern_focus',target='add_face')
        self.select_definition.execute.assert_not_called()
        self.assertFalse(self.ui.activeSelectionChanged.handlers)
        self.action(session,'pattern_cancel')

    def test_clear_is_explicit_and_can_restart_on_another_body(self):
        session=self.begin(finish=False)
        self.select_native([])
        self.assertEqual(session.faces,self.faces,'native deselection does not discard accumulated faces')
        self.action(session,'pattern_clear_faces')
        self.drain_native()
        self.assertFalse(session.snapshot()['canFinishFaces'])
        self.assertEqual(self.ui.activeSelections.count,0)
        with self.assertRaisesRegex(ValueError,'at least one face'):
            self.action(session,'pattern_finish_faces')
        other=NS(kind='face',isValid=True,body=NS(name='Other'))
        self.select_native([other])
        self.assertEqual(session.faces,(other,))
        self.fusion.prepare_pattern.assert_not_called()
        self.action(session,'pattern_cancel')
        self.assertFalse(self.custom_events)
        self.assertFalse(self.ui.activeSelectionChanged.handlers)

    def test_duplicate_native_picks_do_not_duplicate_sources(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        self.action(session,'pattern_clear_faces')
        self.drain_native()
        self.select_native([self.faces[0],self.faces[0],self.faces[1]])
        self.assertEqual(session.faces,self.faces[:2])
        self.assertFalse(self.manager.busy)

    def test_picker_rejects_preview_updates_until_done_without_losing_picker(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        for action in ('pattern_preview','pattern_update','pattern_commit','pattern_focus'):
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'Done'):
                self.action(session,action,target='faces')
            self.assertIsNotNone(session.face_picker)
        self.assertFalse(self.manager.busy)

    def test_replacing_faces_waits_for_done_and_starts_empty(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='faces')
        self.assertEqual(session.faces,())
        self.select_native(self.faces[2:])
        self.assertEqual(session.faces,self.faces[2:])
        self.assertIsNotNone(session.face_picker)
        self.fusion.prepare_pattern.assert_not_called()
        self.action(session,'pattern_finish_faces')
        self.assertEqual(session.phase,'ready')

    def test_other_body_selection_stays_recoverable_and_cannot_finish(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        other=NS(kind='face',isValid=True,body=NS(name='Other'))
        self.select_native([self.faces[0],other])
        self.assertFalse(session.snapshot()['canFinishFaces'])
        with self.assertRaisesRegex(ValueError,'same solid'):
            self.action(session,'pattern_finish_faces')
        self.select_native(self.faces)
        self.assertTrue(session.snapshot()['canFinishFaces'])
        self.action(session,'pattern_finish_faces')
        self.assertFalse(self.manager.busy)

    def test_picker_face_cap_and_return_to_valid_selection(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        faces=tuple(NS(kind='face',isValid=True,index=index,body=self.body) for index in range(101))
        self.action(session,'pattern_clear_faces')
        self.drain_native()
        self.select_native(faces)
        self.assertFalse(session.snapshot()['canFinishFaces'])
        self.assertLessEqual(len(session.faces),100)
        self.select_native(faces[:100])
        self.assertTrue(session.snapshot()['canFinishFaces'])
        self.assertTrue(session.snapshot()['pickingFaces'],'a full selection still has an explicit Done')
        self.action(session,'pattern_finish_faces')
        self.assertEqual(session.faces,faces[:100])

    def test_cancel_restores_prior_native_selection_and_detaches_handler(self):
        session=self.begin()
        original=list(self.ui.activeSelections.values)
        self.action(session,'pattern_focus',target='add_face')
        self.select_native(self.faces[:1])
        self.action(session,'pattern_cancel')
        self.assertEqual([value.entity for value in self.ui.activeSelections.values],[value.entity for value in original])
        self.assertFalse(self.ui.activeSelectionChanged.handlers)

    def test_stop_during_picker_restores_selection_and_releases_handler(self):
        session=self.begin()
        self.action(session,'pattern_focus',target='add_face')
        self.select_native(self.faces[:1])
        self.manager.stop()
        self.assertFalse(self.ui.activeSelectionChanged.handlers)
        self.assertIsNone(self.manager._session)

    def test_empty_initial_selection_can_cancel_without_geometry(self):
        state=self.manager.begin_palette(PatternSettings().to_dict())
        self.assertEqual(state['phase'],'picking_faces')
        self.assertFalse(state['canFinishFaces'])
        self.ui.selectEntity.assert_not_called()
        self.action(self.manager._session,'pattern_cancel')
        self.assertFalse(self.custom_events)
        self.fusion.prepare_pattern.assert_not_called()

    def test_add_face_is_unavailable_in_body_scope_or_edit_mode(self):
        self.picks[:] = [NS(entity=self.body)]
        self.manager.begin_palette(PatternSettings(selection_scope="body").to_dict())
        session = self.manager._session
        with self.assertRaisesRegex(ValueError, "face selection scope"):
            self.action(session, "pattern_focus", target="add_face")
        session.close()
        session = self.begin(editing=True)
        with self.assertRaisesRegex(ValueError, "existing Partelier"):
            self.action(session, "pattern_focus", target="add_face")
        self.assertEqual(self.ui.selectEntity.call_count, 1)

    def test_body_scope_picks_one_body_and_expands_its_faces(self):
        self.picks[:] = [NS(entity=self.body)]
        self.manager.begin_palette(PatternSettings(selection_scope="body").to_dict())
        self.assertEqual(self.manager._session.faces, self.faces)
        self.assertEqual(self.ui.selectEntity.call_args.args[1], "SolidBodies")

    def test_preview_queues_compute_and_draws_only_after_rollback(self):
        session = self.begin()
        snapshot = self.action(session, "pattern_preview")
        self.assertEqual(snapshot["phase"], "computing")
        self.fusion.prepare_pattern.assert_not_called()
        self.fusion.preview_pattern.assert_not_called()
        self.module.display_export.prepare.assert_not_called()
        job = self.manager.runner.compute()
        self.assertIsNotNone(job.result)
        self.module.display_export.prepare.assert_called_once_with(job.result)
        self.fusion.preview_pattern.assert_not_called()
        self.assertTrue(self.body.isLightBulbOn)
        self.manager.runner.rollback()
        self.assertEqual(session.phase, "preview")
        self.assertTrue(session.preview_current)
        self.assertFalse(self.body.isLightBulbOn)
        self.recipe.create_pattern.assert_not_called()

    def test_old_revision_completion_cannot_draw_or_replace_newer_settings(self):
        session = self.begin()
        self.action(session, "pattern_preview")
        self.action(session, "pattern_preview", settings=PatternSettings(pitch_mm=10), revision=1)
        self.manager.runner.finish()
        self.fusion.preview_pattern.assert_not_called()
        self.assertTrue(self.body.isLightBulbOn)
        self.manager.runner.finish()
        self.assertEqual(session.prepared.settings.pitch_mm, 10)
        self.assertEqual(session.preview_revision, 1)
        self.assertTrue(session.preview_current)

    def test_failed_replacement_retains_last_valid_view_without_allowing_commit(self):
        session = self.begin()
        self.preview(session)
        previous = session.preview
        self.fusion.prepare_pattern.side_effect = ValueError("Curve offset failed")
        self.action(session, "pattern_preview", settings=PatternSettings(depth_mm=2), revision=1)
        self.manager.runner.finish()
        self.assertIs(session.preview, previous)
        self.assertTrue(previous.isValid)
        self.assertFalse(self.body.isLightBulbOn)
        self.assertEqual(session.phase, "error")
        self.assertFalse(session.preview_current)
        with self.assertRaisesRegex(ValueError, "current pattern preview"):
            self.action(session, "pattern_commit")
        self.recipe.create_pattern.assert_not_called()

    def test_missing_or_invalid_draw_result_does_not_hide_the_source(self):
        for candidate in (None, NS(isValid=False)):
            with self.subTest(candidate=candidate):
                session = self.manager._session or self.begin()
                self.fusion.preview_pattern.side_effect = None
                self.fusion.preview_pattern.return_value = candidate
                self.action(session, "pattern_preview")
                self.manager.runner.finish()
                self.assertEqual(session.phase, "error")
                self.assertFalse(session.preview_current)
                self.assertTrue(self.body.isLightBulbOn)
                self.recipe.create_pattern.assert_not_called()
                session.close()

    def test_cancel_restores_visibility_and_late_completion_cannot_redraw(self):
        session = self.begin()
        self.preview(session)
        old = session.preview
        self.action(session, "pattern_preview", settings=PatternSettings(pitch_mm=9), revision=1)
        job = self.manager.runner.compute()
        self.action(session, "pattern_cancel")
        self.assertFalse(old.isValid)
        self.assertTrue(self.body.isLightBulbOn)
        self.assertTrue(session.closed)
        draws = self.fusion.preview_pattern.call_count
        self.manager.runner.rollback()
        job.completed(job.result)
        self.assertEqual(self.fusion.preview_pattern.call_count, draws)
        self.assertIsNone(self.manager._session)

    def test_scope_change_cancels_compute_and_requires_new_selections(self):
        session = self.begin()
        self.preview(session)
        old = session.preview
        self.action(session, "pattern_update", settings=PatternSettings(selection_scope="body"), revision=1)
        self.assertFalse(old.isValid)
        self.assertTrue(self.body.isLightBulbOn)
        self.assertEqual(session.faces, ())
        self.assertEqual(session.phase, "selecting")
        self.assertFalse(session.snapshot()["selections"]["surface"]["selected"])

    def test_spacing_change_retains_faces_but_requires_review_of_replacement_preview(self):
        session = self.begin(PatternSettings(layout_mode="fixed"))
        self.preview(session)
        previous, reviewed = session.preview, session.prepared
        automatic = replace(session.settings, layout_mode="fit")
        state = self.action(session, "pattern_update", settings=automatic, revision=1)
        self.assertEqual(session.faces, self.faces)
        self.assertTrue(state["selections"]["surface"]["selected"])
        self.assertFalse(state["previewCurrent"])
        self.assertIs(session.preview, previous, "keep the last valid view while spacing is recalculated")
        self.assertIs(session.prepared, reviewed)
        self.assertTrue(previous.isValid)
        self.ui.selectEntity.assert_not_called()
        with self.assertRaisesRegex(ValueError, "current pattern preview"):
            self.action(session, "pattern_commit")
        self.manager._registration[0].execute.assert_not_called()
        self.recipe.create_pattern.assert_not_called()
        self.action(session, "pattern_preview")
        self.manager.runner.compute()
        self.assertTrue(previous.isValid, "replacement waits for the computation rollback boundary")
        self.assertFalse(session.preview_current)
        self.manager.runner.rollback()
        self.assertFalse(previous.isValid)
        self.assertIsNot(session.preview, previous)
        self.assertEqual(session.prepared.settings.layout_mode, "fit")
        self.assertEqual(session.preview_revision, 1)
        self.assertTrue(session.preview_current)
        self.assertEqual(session.faces, self.faces)

    def test_balanced_preview_reports_actual_cell_size_instead_of_hidden_pitch(self):
        original = self.fusion.prepare_pattern.side_effect
        def prepare(*args):
            result = original(*args)
            result.layouts = (NS(cell_count=3, effective_pitch_mm=20),
                              NS(cell_count=4, effective_pitch_mm=22))
            return result
        self.fusion.prepare_pattern.side_effect = prepare
        session = self.begin(PatternSettings(layout_mode="balanced",pitch_mm=17.5,web_mm=1.5))
        self.preview(session)
        self.assertIn('cell size 16 mm', session.message)
        self.assertIn('grid gap ≈ 4.00 mm', session.message)
        self.assertNotIn('pitch', session.message)

    def test_auto_preview_reports_proposal_and_never_overwrites_the_saved_seed(self):
        original=self.fusion.prepare_pattern.side_effect
        def prepare(*args):
            result=original(*args)
            result.layouts=(NS(cell_count=7,cell_size_mm=18.25,proposals_evaluated=16,acceptance_checks=30),)
            return result
        self.fusion.prepare_pattern.side_effect=prepare
        session=self.begin(PatternSettings(layout_mode='auto'))
        self.preview(session)
        self.assertIn('Auto fit · balanced',session.message)
        self.assertIn('cell size 18.25 mm',session.message)
        self.assertEqual(session.snapshot()['suggestedSizeMm'],18.25)
        self.assertEqual(session.settings.pitch_mm,19.5)
        session.clear_preview()
        self.assertIsNone(session.snapshot()['suggestedSizeMm'])

    def test_fill_preview_reports_the_three_user_dimensions(self):
        session = self.begin(PatternSettings(layout_mode='fill',pitch_mm=11.5,web_mm=1.5,border_mm=2))
        self.preview(session)
        self.assertIn('size 10 mm',session.message)
        self.assertIn('minimum gap 1.5 mm',session.message)
        self.assertIn('border ≥ 2 mm',session.message)

    def test_polygon_mosaics_report_the_reference_dimension_and_minimum_gap(self):
        original=self.fusion.prepare_pattern.side_effect
        def prepare(*args):
            result=original(*args)
            result.layouts=(NS(cell_count=7,cell_size_mm=12.5,repeat_u_mm=40),)
            return result
        self.fusion.prepare_pattern.side_effect=prepare
        session=self.begin(PatternSettings(pattern='trihex',layout_mode='fill',pitch_mm=17.5,web_mm=5))
        self.preview(session)
        self.assertIn('cell size 12.50 mm',session.message)
        self.assertIn('minimum gap 5 mm',session.message)
        self.assertNotIn('grid gap',session.message)

    def test_create_reuses_exact_reviewed_detached_result_without_recomputing(self):
        session = self.begin()
        self.preview(session)
        reviewed = session.prepared
        def create(design, prepared):
            self.assertIs(prepared, reviewed)
            self.assertTrue(prepared.result_body.isTemporary)
            self.assertTrue(self.body.isLightBulbOn, "visibility restores before persistence snapshots")
        self.recipe.create_pattern.side_effect = create
        self.action(session, "pattern_commit")
        self.manager._registration[0].execute.assert_called_once_with()
        command = self.native_command(session)
        args = NS(executeFailed=False)
        command.execute.handlers[0].notify(args)
        self.assertFalse(args.executeFailed)
        self.assertEqual(session.phase, "created")
        self.fusion.prepare_pattern.assert_called_once()
        self.recipe.create_pattern.assert_called_once_with(self.design, reviewed)
        self.assertGreaterEqual(self.recipe.validate_preview_sources.call_count, 3)
        command.destroy.handlers[0].notify(NS())
        self.assertIsNone(self.manager._session)
        self.assertTrue(self.body.isLightBulbOn)

    def test_stale_sources_refuse_commit_before_opening_native_transaction(self):
        session = self.begin()
        self.preview(session)
        self.recipe.validate_preview_sources.side_effect = ValueError("Source changed")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.action(session, "pattern_commit")
        self.manager._registration[0].execute.assert_not_called()
        self.recipe.create_pattern.assert_not_called()

    def test_source_change_after_commit_launch_still_prevents_persistence(self):
        session = self.begin()
        self.preview(session)
        self.action(session, "pattern_commit")
        command = self.native_command(session)
        self.recipe.validate_preview_sources.side_effect = ValueError("Changed before Execute")
        args = NS(executeFailed=False)
        command.execute.handlers[0].notify(args)
        self.assertTrue(args.executeFailed)
        self.recipe.create_pattern.assert_not_called()
        self.assertEqual(session.phase, "error")

    def test_edit_loads_saved_settings_and_rebuilds_reviewed_result(self):
        target = NS(anchor=object(), settings=PatternSettings(pattern="circle", mode="engrave", depth_mm=.7))
        self.recipe.read_edit_target.return_value = target
        session = self.begin(editing=True)
        self.assertEqual(session.settings, target.settings)
        self.preview(session)
        prepared = session.prepared
        self.recipe.prepare_edit_pattern.assert_called_once_with(self.design, target, target.settings)
        self.action(session, "pattern_commit")
        command = self.native_command(session)
        command.execute.handlers[0].notify(NS(executeFailed=False))
        self.recipe.rebuild_pattern.assert_called_once_with(self.design, target, prepared)
        self.recipe.create_pattern.assert_not_called()
        with self.assertRaisesRegex(ValueError, "new pattern"):
            session.update(replace(target.settings, selection_scope="body").to_dict(), 1)

    def test_legacy_limit_notice_survives_first_preview_and_clears_after_an_edit(self):
        target=NS(anchor=object(),settings=PatternSettings(pattern='grille_louver',layout_mode='fill'))
        self.recipe.read_edit_target.return_value=target
        self.recipe.edit_notice.return_value='Legacy tilt exceeds 45. Existing body is unchanged.'
        session=self.begin(editing=True)
        self.assertIn('Legacy tilt',session.message)
        self.preview(session)
        self.assertEqual(session.phase,'preview')
        self.assertIn('Legacy tilt',session.message)
        session.update(replace(target.settings,louver_angle_deg=20).to_dict(),1)
        self.preview(session)
        self.assertNotIn('Legacy tilt',session.message)

    def test_malformed_or_stale_snapshots_do_not_partially_change_session(self):
        session = self.begin()
        self.action(session, "pattern_update", settings=PatternSettings(pitch_mm=9), revision=3)
        for revision, values in ((2, session.settings.to_dict()), (3, PatternSettings(pitch_mm=10).to_dict()), (4, {"pitch_mm": 12})):
            with self.subTest(revision=revision, fields=len(values)), self.assertRaises(ValueError):
                self.manager.palette_action("pattern_update", session.session_id, revision, values)
        self.assertEqual(session.settings.pitch_mm, 9)
        self.assertEqual(session.revision, 3)

    def test_refused_or_partially_bound_commit_handlers_cannot_persist(self):
        for event_name, partial in (("destroy", False), ("execute", False), ("execute", True)):
            with self.subTest(event=event_name, partial=partial):
                session = self.manager._session or self.begin()
                self.preview(session)
                self.action(session, "pattern_commit")
                command = NS(execute=Event(), destroy=Event())
                event = getattr(command, event_name)
                event.fail_add, event.raise_add = not partial, partial
                self.module._Created(self.manager).notify(NS(command=command))
                self.assertTrue(command.isAutoExecute)
                self.assertIsNone(session.command)
                self.assertEqual(session.phase, "error")
                self.assertEqual(session.handlers, [])
                self.assertEqual(command.destroy.handlers, [])
                self.assertEqual(command.execute.handlers, [])
                args = NS(executeFailed=False)
                self.module._Execute(session).notify(args)
                self.assertTrue(args.executeFailed)
        self.recipe.create_pattern.assert_not_called()

    def test_orbit_keeps_preview_but_changed_geometry_clears_it(self):
        session = self.begin()
        self.preview(session)
        group = session.preview
        event = self.module._CommandEnded(self.manager)
        event.notify(NS(commandId="OrbitCommand"))
        self.assertIs(session.preview, group)
        self.assertTrue(group.isValid)
        self.recipe.validate_preview_sources.side_effect = ValueError("Source changed")
        event.notify(NS(commandId="ExtrudeCommand"))
        self.assertFalse(group.isValid)
        self.assertTrue(self.body.isLightBulbOn)
        self.assertFalse(session.preview_current)
        self.assertEqual(session.phase, "error")

    def test_document_change_cancels_pending_work_and_restores_source(self):
        session = self.begin()
        self.preview(session)
        self.module._DocumentChanging(self.manager).notify(NS())
        self.assertTrue(session.closed)
        self.assertTrue(self.body.isLightBulbOn)
        self.assertIsNone(self.manager._session)

    def test_cancel_cleanup_failure_retains_ownership_for_retry(self):
        session = self.begin()
        self.preview(session)
        session.preview.fail_delete = True
        with self.assertRaisesRegex(RuntimeError, "Cancel or Stop"):
            session.close()
        self.assertIs(self.manager._session, session)
        self.assertFalse(session.closed)
        session.preview.fail_delete = False
        session.close()
        self.assertTrue(self.body.isLightBulbOn)
        self.assertIsNone(self.manager._session)


if __name__ == "__main__":
    unittest.main()
