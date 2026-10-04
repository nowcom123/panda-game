"""Navigation bearings and objective selection, independent of game state."""

import unittest

from compass_ui import relative_bearing, select_objective


class Navigation(unittest.TestCase):
    def test_north_seam_and_shortest_turn(self):
        self.assertEqual(relative_bearing(1, 359), 2)
        self.assertEqual(relative_bearing(359, 1), -2)
        self.assertEqual(relative_bearing(90, 0), 90)
        self.assertEqual(relative_bearing(270, 0), -90)
        for heading in range(-720, 721, 15):
            self.assertEqual(relative_bearing(heading % 360, heading), 0)

    def test_world_axes_and_distance(self):
        for pos, bearing in (((0, 10), 0), ((10, 0), 90), ((0, -10), 180), ((-10, 0), 270)):
            target = select_objective(0, 0, [dict(pos=pos, activated=False, name='altar')], None)
            self.assertEqual(target['bearing'], bearing)
            self.assertEqual(target['distance'], 10)

    def test_nearest_unlit_altar_then_open_gate_without_mutation(self):
        altars = [dict(pos=(0, 5), activated=True, name='done'),
                  dict(pos=(0, 20), activated=False, name='far'),
                  dict(pos=(3, 4), activated=False, name='near')]
        gate = dict(pos=(0, 50), opened=False)
        target = select_objective(0, 0, altars, gate)
        self.assertEqual(target['name'], 'near')
        self.assertEqual(target['distance'], 5)
        self.assertNotIn('bearing', altars[2])
        altars[2]['activated'] = True
        self.assertEqual(select_objective(0, 0, altars, gate)['name'], 'far')
        altars[1]['activated'] = True
        self.assertIsNone(select_objective(0, 0, altars, gate))
        gate['opened'] = True
        self.assertEqual(select_objective(0, 0, altars, gate)['kind'], 'gate')
        self.assertIsNone(select_objective(0, 0, [], None))
