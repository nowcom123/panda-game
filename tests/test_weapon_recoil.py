import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath
from player_controller import PlayerController
from weapon_recoil import RecoilSpring, WeaponRecoil


class WeaponRecoilTests(unittest.TestCase):
    def test_recovery_matches_at_different_frame_rates(self):
        results = []
        for fps in (30, 60, 144):
            spring = RecoilSpring()
            spring.kick()
            for _ in range(fps // 6):
                spring.update(1 / fps)
            results.append(spring.position)
        self.assertAlmostEqual(results[0], results[1], places=10)
        self.assertAlmostEqual(results[1], results[2], places=10)

    def test_sustained_fire_is_bounded_and_recovers_after_frame_stall(self):
        spring = RecoilSpring()
        for _ in range(500):
            spring.kick()
            self.assertLessEqual(abs(spring.update(.005)), spring.limit)
        self.assertEqual(spring.update(2), 0)
        self.assertEqual(spring.velocity, 0)

    def test_dual_hands_recover_independently_and_ads_reduces_kick(self):
        recoil = WeaponRecoil()
        recoil.kick('DUAL_PISTOL', left=False)
        pose = recoil.update(.025, 0)
        self.assertGreater(pose['dual_right_recoil'][2], 0)
        self.assertNotIn('dual_left_recoil', pose)
        recoil.kick('DUAL_PISTOL', left=True)
        pose = recoil.update(.025, 0)
        self.assertGreater(pose['dual_left_recoil'][2], 0)
        self.assertGreater(pose['dual_right_recoil'][2], 0)
        ads = recoil.update(0, 1)
        self.assertLess(ads['dual_left_recoil'][2], pose['dual_left_recoil'][2])
        recoil.reset()
        self.assertTrue(all(p == (0, 0, 0, 0) for p in recoil.update(0, 0).values()))

    def test_camera_recovers_to_new_mouse_aim_without_overwriting_it(self):
        player = PlayerController(SimpleNamespace(game_state='PLAYING'), None,
                                  NodePath('camera'), None, None, Mock())
        player.reset_position(0, 0, heading=12, pitch=5)
        player.add_weapon_recoil(.8, .04)
        player.update(.04, {})
        self.assertGreater(player.camera.getP(), 5)
        self.assertEqual(player.pitch, 5)
        # A mouse movement during recovery changes the desired aim normally.
        player.heading, player.pitch = 20, -7
        player.update(.016, {})
        self.assertGreater(player.camera.getP(), -7)
        for _ in range(90):
            player.update(1/60, {})
        self.assertAlmostEqual(player.camera.getP(), -7, places=5)
        self.assertAlmostEqual(player.camera.getH(), 20, places=5)
        self.assertEqual((player.heading, player.pitch), (20, -7))
        player.add_weapon_recoil(1)
        player.reset_position(0, 0)
        self.assertEqual(player.recoil_pitch.velocity, 0)


if __name__ == '__main__':
    unittest.main()
