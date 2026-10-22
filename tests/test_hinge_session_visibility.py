"""Session presentation and persistence failure recovery, using fake native events."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
import test_hinge_palette_command as fakes
from Partelier.partelier.tools.hinge.settings import HingeSettings


def body(name,visible=True):
    return SimpleNamespace(name=name,isValid=True,isSolid=True,isTemporary=False,
                           assemblyContext=None,isLightBulbOn=visible)


class SessionVisibilityTests(unittest.TestCase):
    setUp=fakes.HingePaletteCommandTests.setUp
    tearDown=fakes.HingePaletteCommandTests.tearDown
    open_palette=fakes.HingePaletteCommandTests.open_palette
    action=fakes.HingePaletteCommandTests.action
    native_commit=fakes.HingePaletteCommandTests.native_commit

    def test_edit_preview_hides_old_geometry_resize_cancel_then_new(self):
        sources=(body("sourceA"),body("sourceB",False))
        old=(body("oldA"),body("oldB"),body("pin"))
        self.adapter.read_edit_target.return_value=SimpleNamespace(settings=HingeSettings(),face_a=object(),face_b=object(),axis_edge=object())
        self.adapter.preview_hide_bodies.return_value=sources+old
        session=self.open_palette(editing=True)
        self.action(session,"hinge_preview")
        self.assertTrue(all(not b.isLightBulbOn for b in sources+old))
        first=session.preview
        smaller=replace(session.palette_settings,barrel_diameter_mm=7.5)
        self.action(session,"hinge_preview",smaller,revision=1)
        self.assertFalse(first.isValid)
        self.assertEqual(self.adapter.prepare_edit_hinge.call_args.args[2],smaller)
        self.assertTrue(all(not b.isLightBulbOn for b in sources+old))
        self.action(session,"hinge_cancel")
        self.assertEqual([b.isLightBulbOn for b in sources+old],[True,False,True,True,True])
        self.adapter.create_hinge.assert_not_called()
        self.adapter.rebuild_hinge.assert_not_called()
        new=self.open_palette()
        self.assertFalse(new.editing)
        self.assertNotEqual(new.session_id,session.session_id)

    def test_repick_reveals_selectable_bodies_then_escape_restores_current_view(self):
        sources=(body("sourceA"),body("sourceB"))
        self.adapter.preview_hide_bodies.return_value=sources
        session=self.open_palette()
        self.action(session,"hinge_preview")
        previous=session.preview
        def pick(*args):
            self.assertFalse(previous.isVisible)
            self.assertTrue(all(b.isLightBulbOn for b in sources))
            raise RuntimeError("User pressed Esc")
        self.ui.selectEntity.side_effect=pick
        self.action(session,"hinge_focus",target="face_a")
        self.assertIs(session.preview,previous)
        self.assertTrue(previous.isVisible)
        self.assertTrue(all(not b.isLightBulbOn for b in sources))
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_switching_output_mode_releases_and_reacquires_source_visibility(self):
        sources=(body("sourceA"),body("sourceB"))
        self.adapter.preview_hide_bodies.side_effect=lambda prepared,target=None: sources if prepared.settings.output_mode=="attached" else ()
        session=self.open_palette()
        self.action(session,"hinge_preview")
        self.assertTrue(all(not b.isLightBulbOn for b in sources))
        separate=replace(session.palette_settings,output_mode="separate")
        self.action(session,"hinge_preview",separate,revision=1)
        self.assertTrue(all(b.isLightBulbOn for b in sources))
        self.assertEqual(session.preview_visibility.pending_count,0)
        attached=replace(separate,output_mode="attached")
        self.action(session,"hinge_preview",attached,revision=2)
        self.assertTrue(all(not b.isLightBulbOn for b in sources))
        self.action(session,"hinge_cancel")
        self.assertTrue(all(b.isLightBulbOn for b in sources))

    def test_successful_create_restores_original_visibility_before_persisting(self):
        sources=(body("sourceA"),body("sourceB",False))
        self.adapter.preview_hide_bodies.return_value=sources
        self.adapter.source_bodies.return_value=sources
        session=self.open_palette()
        self.action(session,"hinge_preview")
        def persist(*args):
            self.assertEqual([b.isLightBulbOn for b in sources],[True,False])
        self.adapter.create_hinge.side_effect=persist
        result=self.action(session,"hinge_commit")
        self.assertEqual(result["phase"],"created")
        self.assertTrue(session.closed)
        self.assertEqual([b.isLightBulbOn for b in sources],[True,False])
        self.assertEqual(session.preview_visibility.pending_count,0)

    def test_rebuild_restores_existing_targets_before_modifying_them(self):
        targets=(body("targetA"),body("targetB",False),body("existingPin"))
        target=SimpleNamespace(settings=HingeSettings(),face_a=object(),face_b=object(),axis_edge=object())
        self.adapter.read_edit_target.return_value=target
        self.adapter.preview_hide_bodies.return_value=targets
        session=self.open_palette(editing=True)
        self.action(session,"hinge_preview")
        self.assertTrue(all(not b.isLightBulbOn for b in targets))
        def rebuild(design,actual,prepared):
            self.assertIs(actual,target)
            self.assertEqual([b.isLightBulbOn for b in targets],[True,False,True])
        self.adapter.rebuild_hinge.side_effect=rebuild
        result=self.action(session,"hinge_commit")
        self.assertEqual(result["phase"],"created")
        self.assertEqual([b.isLightBulbOn for b in targets],[True,False,True])
        self.adapter.prepare_hinge.assert_not_called()
        self.adapter.rebuild_hinge.assert_called_once()

    def test_failed_create_restores_sources_and_does_not_block_a_new_session(self):
        sources=(body("sourceA"),body("sourceB"))
        self.adapter.preview_hide_bodies.return_value=sources
        self.adapter.source_bodies.return_value=sources
        self.adapter.create_hinge.side_effect=ValueError("Native storage failed")
        session=self.open_palette()
        self.action(session,"hinge_preview")
        result=self.action(session,"hinge_commit")
        self.assertEqual(result["phase"],"error")
        self.assertTrue(self.execute_args[-1].executeFailed)
        self.assertTrue(all(b.isLightBulbOn for b in sources))
        self.assertFalse(self.owner._sessions)
        new=self.open_palette()
        self.action(new,"hinge_preview")
        self.assertTrue(self.owner.palette_state()["previewCurrent"])

    def test_failed_preview_does_not_hide_model_and_deletes_unused_graphics(self):
        self.adapter.preview_hide_bodies.side_effect=ValueError("Owned target no longer matches")
        session=self.open_palette()
        state=self.action(session,"hinge_preview")
        self.assertEqual(state["phase"],"error")
        self.assertFalse(self.graphics[-1].isValid)
        self.assertEqual(session.preview_visibility.pending_count,0)

    def test_invalid_edit_selection_exposes_error_instead_of_silent_selecting(self):
        self.adapter.read_edit_target.side_effect=ValueError("Select the last hinge in the timeline")
        session=self.open_palette(editing=True)
        snapshot=self.owner.palette_state()
        self.assertEqual(snapshot["phase"],"error")
        self.assertIn("last hinge",snapshot["message"])
        self.action(session,"hinge_cancel")
        self.assertFalse(self.owner._sessions)

    def test_stop_restores_mixed_original_visibility(self):
        bodies=(body("visible"),body("already hidden",False))
        self.adapter.preview_hide_bodies.return_value=bodies
        session=self.open_palette()
        self.action(session,"hinge_preview")
        self.owner.stop()
        self.assertEqual([b.isLightBulbOn for b in bodies],[True,False])
        self.assertFalse(session.preview)

if __name__=="__main__":unittest.main()
