"""Visibility ownership and complete-result drawing; no native kernel proof."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.visibility import BodyVisibilityLease, VisibilityError


class Body:
    def __init__(self, visible=True):
        self.isValid = True
        self.isSolid = True
        self.isTemporary = False
        self.assemblyContext = None
        self._visible = visible
        self.writes = []
        self.fail_hide = 0
        self.fail_restore = 0

    @property
    def isLightBulbOn(self):
        return self._visible

    @isLightBulbOn.setter
    def isLightBulbOn(self, value):
        if not value and self.fail_hide:
            self.fail_hide -= 1
            raise RuntimeError("hide failed")
        if value and self.fail_restore:
            self.fail_restore -= 1
            raise RuntimeError("restore failed")
        self.writes.append(value)
        self._visible = value


def collection(items):
    return SimpleNamespace(count=len(items), item=lambda index: items[index])


class BodyVisibilityTests(unittest.TestCase):
    def test_cancel_restores_original_flags_without_resnapshotting_duplicates(self):
        visible, hidden = Body(), Body(False)
        lease = BodyVisibilityLease().hide((visible, hidden, visible))
        lease.hide((visible,))
        self.assertEqual(lease.pending_count, 2)
        self.assertFalse(visible.isLightBulbOn)
        lease.restore()
        self.assertTrue(visible.isLightBulbOn)
        self.assertFalse(hidden.isLightBulbOn)
        self.assertEqual(visible.writes, [False, True])
        self.assertEqual(hidden.writes, [])
        self.assertEqual(lease.pending_count, 0)

    def test_invalid_body_preflight_hides_nothing(self):
        visible, invalid = Body(), Body()
        invalid.isValid = False
        with self.assertRaises(VisibilityError):
            BodyVisibilityLease().hide((visible, invalid))
        self.assertEqual(visible.writes, [])

    def test_partial_hide_failure_restores_bodies_already_changed(self):
        first, second = Body(), Body()
        second.fail_hide = 1
        lease = BodyVisibilityLease()
        with self.assertRaisesRegex(VisibilityError, "hide failed"):
            lease.hide((first, second))
        self.assertTrue(first.isLightBulbOn)
        self.assertTrue(second.isLightBulbOn)
        self.assertEqual(lease.pending_count, 0)

    def test_failed_hide_cleanup_keeps_snapshot_for_retry(self):
        first, second = Body(), Body()
        first.fail_restore = 1
        second.fail_hide = 1
        lease = BodyVisibilityLease()
        with self.assertRaisesRegex(VisibilityError, "will retry"):
            lease.hide((first, second))
        self.assertEqual(lease.pending_count, 1)
        self.assertFalse(first.isLightBulbOn)
        lease.restore()
        self.assertTrue(first.isLightBulbOn)
        self.assertEqual(lease.pending_count, 0)

    def test_restore_failure_can_be_retried_without_losing_original_visibility(self):
        body = Body()
        lease = BodyVisibilityLease().hide((body,))
        body.fail_restore = 1
        with self.assertRaisesRegex(VisibilityError, "Retry Cancel or Stop"):
            lease.restore()
        self.assertEqual(lease.pending_count, 1)
        lease.restore()
        self.assertTrue(body.isLightBulbOn)
        self.assertEqual(lease.pending_count, 0)

    def test_external_visibility_change_is_not_overwritten(self):
        body = Body(False)
        lease = BodyVisibilityLease().hide((body,))
        body.isLightBulbOn = True
        with self.assertRaisesRegex(VisibilityError, "outside the hinge session"):
            lease.restore()
        self.assertTrue(body.isLightBulbOn)
        self.assertEqual(lease.pending_count, 1)

    def test_deleted_body_restore_fails_closed_and_keeps_record(self):
        body = Body()
        lease = BodyVisibilityLease().hide((body,))
        body.isValid = False
        with self.assertRaises(VisibilityError):
            lease.restore()
        self.assertEqual(lease.pending_count, 1)

    def test_commit_after_success_keeps_backups_hidden(self):
        body = Body()
        lease = BodyVisibilityLease().hide((body,))
        lease.commit()
        lease.restore()
        self.assertFalse(body.isLightBulbOn)
        self.assertEqual(lease.pending_count, 0)

    def test_temporary_or_proxy_bodies_are_not_visibility_targets(self):
        for field, value in (("isTemporary", True), ("assemblyContext", object()), ("isSolid", False)):
            body = Body()
            setattr(body, field, value)
            with self.subTest(field=field), self.assertRaises(VisibilityError):
                BodyVisibilityLease().hide((body,))
            self.assertEqual(body.writes, [])


class HingePresentationHookTests(unittest.TestCase):
    def prepared(self, mode="attached"):
        a, b = Body(), Body()
        return SimpleNamespace(settings=SimpleNamespace(output_mode=mode),
                               face_a=SimpleNamespace(body=a), face_b=SimpleNamespace(body=b),
                               design=SimpleNamespace(rootComponent=object()))

    def test_attached_sources_and_only_owned_root_edit_bodies_are_hidden(self):
        prepared = self.prepared()
        old, unrelated = Body(), Body()
        target = SimpleNamespace(anchor=SimpleNamespace(bodies=collection((old,))),
                                 component=prepared.design.rootComponent)
        bodies = fusion.preview_hide_bodies(prepared, target)
        self.assertEqual(bodies, (prepared.face_a.body, prepared.face_b.body, old))
        self.assertNotIn(unrelated, bodies)
        self.assertTrue(all(body.isLightBulbOn for body in bodies))

    def test_separate_output_keeps_sources_visible_and_hides_only_old_owned_leaves(self):
        prepared = self.prepared("separate")
        old = Body()
        target = SimpleNamespace(anchor=SimpleNamespace(),
                                 component=SimpleNamespace(bRepBodies=collection((old,))))
        self.assertEqual(fusion.source_bodies(prepared), ())
        self.assertEqual(fusion.preview_hide_bodies(prepared, target), (old,))

    def test_root_edit_requires_owned_base_feature_not_all_root_bodies(self):
        prepared = self.prepared()
        target = SimpleNamespace(anchor=None, component=prepared.design.rootComponent)
        with self.assertRaisesRegex(fusion.HingeGeometryError, "owned base feature"):
            fusion.preview_hide_bodies(prepared, target)

    def test_preview_draws_complete_results_and_never_removed_material_markers(self):
        prepared = self.prepared()
        halves = (Body(), Body(), Body())
        marker = object()
        prepared.result_bodies = tuple(zip(("A", "B", "pin"), halves))
        prepared.preview_bodies = (("clearance", marker),)
        graphics = []
        group = SimpleNamespace(isValid=True, deleteMe=Mock())
        def add(body):
            graphic = SimpleNamespace(body=body,setOpacity=Mock(return_value=True))
            graphics.append(graphic)
            return graphic
        group.addBRepBody = add
        prepared.design.rootComponent = SimpleNamespace(customGraphicsGroups=SimpleNamespace(add=lambda: group))
        api = (SimpleNamespace(Color=SimpleNamespace(create=lambda *values: values)),
               SimpleNamespace(CustomGraphicsAppearanceColorEffect=SimpleNamespace(create=lambda appearance: appearance)))
        with patch.object(fusion, "_assert_fresh"), patch.object(fusion, "_api", return_value=api), patch.object(
                fusion,"_preview_appearances",return_value={role:object() for role in ("A","B","pin")}), patch.object(fusion,"_preview_outlines"):
            fusion.preview_hinge(prepared)
        self.assertEqual([graphic.body for graphic in graphics], list(halves))
        self.assertTrue(all(graphic.isSelectable is False for graphic in graphics))
        self.assertTrue(all(body.writes == [] for body in halves))
        group.deleteMe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
