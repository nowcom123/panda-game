import random
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
from panda3d.core import NodePath
from monster import (LongBlackSerpent, TallSkeletonMonster, AbominableMudOrc,
                     AlluringAshWitch, SkeletalDobermanHellhound, CableOverlordBoss)
from monster_visuals import (optimize_monster_geometry, referenced_nodes,
                             animation_dt, set_shared_tint, group_shared_tint)


class ModelBatchTests(unittest.TestCase):
    def test_bounds_handles_and_animation_survive_batching(self):
        for kind in (LongBlackSerpent, TallSkeletonMonster, AbominableMudOrc,
                     AlluringAshWitch, SkeletalDobermanHellhound, CableOverlordBoss):
            with self.subTest(kind=kind.__name__):
                root = NodePath('test')
                with patch('monster.optimize_monster_geometry'):
                    random.seed(123)
                    model = kind(root, 0, 0)
                try:
                    bounds = model.node.getTightBounds()
                    handles = [(p, p.getParent(), p.getTransform())
                               for p in referenced_nodes(model)]
                    before = model.node.findAllMatches('**/+GeomNode').getNumPaths()
                    optimize_monster_geometry(model)
                    after = model.node.findAllMatches('**/+GeomNode').getNumPaths()
                    self.assertLess(after, before)
                    for old, new in zip(bounds, model.node.getTightBounds()):
                        self.assertTrue(old.almostEqual(new, .001))
                    for path, parent, transform in handles:
                        self.assertFalse(path.isEmpty())
                        self.assertEqual(path.getParent(), parent)
                        self.assertEqual(path.getTransform(), transform)
                    model.update(.016, is_moving=True)
                    model.update(.016, is_moving=False, is_attacking=True)
                finally:
                    model.destroy()
                    root.removeNode()


class VisualUpdateTests(unittest.TestCase):
    def test_shared_tint_is_only_written_on_change(self):
        nodes = [Mock(), Mock()]
        model = SimpleNamespace(hellfire_vein_nodes=nodes)
        color = (1, .2, .1, .8)
        set_shared_tint(model, color)
        set_shared_tint(model, color)
        for node in nodes:
            node.setColorScale.assert_called_once_with(*color)
        set_shared_tint(model, (1, .3, .1, .8))
        self.assertEqual(nodes[0].setColorScale.call_count, 2)

    def test_hound_tint_grouping_preserves_bounds_and_joint_parents(self):
        root = NodePath('test')
        with patch('monster.group_shared_tint', side_effect=lambda nodes: nodes):
            model = SkeletalDobermanHellhound(root, 0, 0)
        try:
            before = model.node.getTightBounds()
            old_count = len(model.hellfire_vein_nodes)
            parents = {n.getParent() for n in model.hellfire_vein_nodes}
            groups = group_shared_tint(model.hellfire_vein_nodes)
            model.hellfire_vein_nodes = groups
            self.assertEqual({g.getParent() for g in groups}, parents)
            self.assertLess(len(groups), old_count)
            for old, new in zip(before, model.node.getTightBounds()):
                self.assertTrue(old.almostEqual(new, .001))
            model.update(.016, True)
            tint = groups[0].getColorScale()
            self.assertTrue(all(g.getColorScale() == tint for g in groups))
        finally:
            model.destroy()
            root.removeNode()

    def test_pose_throttle_preserves_time_and_near_attack_transitions(self):
        model = SimpleNamespace(_animation_interval=.1)
        self.assertEqual(animation_dt(model, .01), .01)
        for _ in range(9):
            self.assertIsNone(animation_dt(model, .01))
        self.assertAlmostEqual(animation_dt(model, .01), .1)
        self.assertIsNone(animation_dt(model, .02))
        self.assertAlmostEqual(animation_dt(model, .01, is_attacking=True), .03)
        self.assertIsNone(animation_dt(model, .02))
        model._animation_interval = 0
        self.assertAlmostEqual(animation_dt(model, .01), .03)

    def test_far_pose_skip_still_updates_elemental_and_stun_timers(self):
        root = NodePath('test')
        model = TallSkeletonMonster(root, 0, 0)
        try:
            model._animation_interval = .1
            model._animation_started = True
            phase = model.anim_time
            with patch.object(model, 'update_elemental') as elemental:
                model.update(.01, is_moving=True)
                elemental.assert_called_once_with(.01)
                self.assertEqual(model.anim_time, phase)
            model.stun_timer = .5
            model.update(.01, is_moving=False)
            self.assertAlmostEqual(model.stun_timer, .49)
        finally:
            model.destroy()
            root.removeNode()

    def test_far_animation_budget_at_high_frame_rate(self):
        model = SimpleNamespace(_animation_interval=.1)
        poses = [animation_dt(model, 1/144) for _ in range(144)]
        drawn = [dt for dt in poses if dt is not None]
        self.assertLessEqual(len(drawn), 11)
        self.assertAlmostEqual(sum(drawn) + model._animation_pending, 1.0)
