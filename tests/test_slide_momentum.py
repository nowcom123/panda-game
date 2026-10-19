"""Exercise actual player movement across sprint-to-slide transitions."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import NodePath
from constants import PLAYER_EYE_HEIGHT, PLAYER_RADIUS
from collision import register_custom_collider, clear_custom_colliders
from player_controller import PlayerController


class SlideMomentumTests(unittest.TestCase):
    def make_player(self):
        camera = NodePath("player-camera")
        camera.setPos(6, 6, PLAYER_EYE_HEIGHT)
        player = PlayerController(SimpleNamespace(game_state="PLAYING"), None,
                                  camera, None, None, Mock())
        player.key_map.update(w=1, shift=1)
        return player

    def test_slide_preserves_measured_entry_speed_until_finished(self):
        for fps in (30, 60, 144):
            for mult, boost, aim in ((1, 0, False), (1.56, 10, False), (1.2, 10, True)):
                with self.subTest(fps=fps, mult=mult, boost=boost, aim=aim):
                    player = self.make_player()
                    player.speed_mult = mult
                    player.speed_boost_timer = boost
                    player.is_aiming = aim
                    player.key_map['d'] = 1
                    dt = 1 / fps
                    before = player.camera.getPos()
                    player.update(dt, {})
                    delta = player.camera.getPos() - before
                    entry_speed = delta.length() / dt
                    player.trigger_slide()
                    # Releasing keys and expiring a boost must not erase momentum.
                    player.key_map = dict(w=0, s=0, a=0, d=0, shift=0)
                    player.speed_boost_timer = 0
                    while player.is_sliding:
                        before = player.camera.getPos()
                        player.update(dt, {})
                        delta = player.camera.getPos() - before
                        delta.z = 0
                        self.assertAlmostEqual(delta.length() / dt, entry_speed, delta=.001)

    def test_external_slow_still_applies_once(self):
        player = self.make_player()
        player.apply_slow(duration=2, factor=.4)
        player.update(.02, {})
        player.trigger_slide()
        before = player.camera.getY()
        player.update(.1, {})
        self.assertAlmostEqual(player.camera.getY() - before,
                               player.slide_speed * .4 * .1, places=5)

    def test_fast_slide_still_stops_at_wall(self):
        player = self.make_player()
        player.speed_mult = 3
        player.update(.02, {})
        player.trigger_slide()
        register_custom_collider((4, 9, 8, 9.2))
        try:
            player.update(.1, {})
            self.assertLessEqual(player.camera.getY(), 9 - PLAYER_RADIUS + .001)
        finally:
            clear_custom_colliders()

    def test_stop_and_reset_clear_previous_momentum(self):
        player = self.make_player()
        player.update(.02, {})
        self.assertGreater(player.move_speed, 0)
        player.key_map['w'] = 0
        player.update(.02, {})
        self.assertEqual(player.move_speed, 0)
        player.key_map['w'] = 1
        player.update(.02, {})
        player.trigger_slide()
        player.reset_position(6, 6)
        self.assertEqual(player.move_speed, 0)
        self.assertEqual(player.slide_speed, 0)
        self.assertFalse(player.is_sliding)


if __name__ == '__main__':
    unittest.main()
