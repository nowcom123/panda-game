import unittest
from types import SimpleNamespace
from unittest.mock import patch
from panda3d.core import Vec3
from enemy_approach import approach_goal


class EnemyApproachTests(unittest.TestCase):
    def monster(self, side=1):
        return SimpleNamespace(pos=Vec3(0, 0, 0), col_radius=.4, _approach_side=side)

    def test_flank_sides_then_warning_then_chase(self):
        for side in (-1, 1):
            m = self.monster(side)
            goal, hold = approach_goal(m, 'flanker', {}, (0, 10), .1, True)
            self.assertEqual(goal[0], -4*side)
            self.assertFalse(hold)
            _, hold = approach_goal(m, 'flanker', {}, (0, 10), 1.4, True)
            self.assertTrue(hold)
            self.assertTrue(m._approach_warning)
            goal, hold = approach_goal(m, 'flanker', {}, (0, 10), .46, True)
            self.assertFalse(hold)
            self.assertEqual(goal, (0, 10))

    def test_witch_retreat_hold_and_reacquire(self):
        m = self.monster()
        goal, hold = approach_goal(m, 'ranged', {}, (0, 6), .1, True)
        self.assertLess(goal[1], 0)
        self.assertFalse(hold)
        _, hold = approach_goal(m, 'ranged', {}, (0, 13), .1, True)
        self.assertTrue(hold)
        goal, hold = approach_goal(m, 'ranged', {}, (0, 13), .1, False)
        self.assertEqual(goal, (0, 13))
        self.assertFalse(hold)

    def test_obstacle_blocks_flank_and_retreat(self):
        with patch('enemy_approach.get_nearby_colliders', return_value=[(-20, -2, 20, -1)]):
            goal, hold = approach_goal(self.monster(), 'ranged', {}, (0, 5), .1, True)
            self.assertTrue(hold)
        with patch('enemy_approach.get_nearby_colliders', return_value=[(-2, -20, -1, 20)]):
            goal, hold = approach_goal(self.monster(), 'flanker', {}, (0, 10), .1, True)
            self.assertEqual(goal, (0, 10))
            self.assertFalse(hold)

    def test_pressure_still_pursues(self):
        self.assertEqual(approach_goal(self.monster(), 'pressure', {}, (0, 10), .1, True),
                         ((0, 10), False))
