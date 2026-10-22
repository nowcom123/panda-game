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

    def test_ar_ads_increases_viewmodel_kick_unlike_other_weapons(self):
        recoil = WeaponRecoil()
        recoil.kick('AR')
        pose_hip = recoil.update(0.02, 0.0)
        recoil.reset()
        recoil.kick('AR')
        pose_ads = recoil.update(0.02, 1.0)
        # AR 조준사격 시 총구 들림(pitch)과 후퇴(travel) 반동이 비조준보다 크게 증가해야 함
        self.assertGreater(pose_ads['ar_recoil_node'][2], pose_hip['ar_recoil_node'][2])
        self.assertGreater(abs(pose_ads['ar_recoil_node'][0]), abs(pose_hip['ar_recoil_node'][0]))

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

    def test_ar_ads_recoil_can_be_manually_controlled_with_mouse(self):
        """AR 조준사격 시 마우스를 아래로 당겨 반동을 직접 상쇄 및 제어할 수 있는지 검증"""
        mock_win = Mock()
        mock_win.getXSize.return_value = 800
        mock_win.getYSize.return_value = 600
        # 마우스를 아래로 10픽셀 당긴 상태 시뮬레이션 (center_y = 300, getPointer y = 310)
        mock_win.getPointer.return_value = SimpleNamespace(getX=lambda: 400, getY=lambda: 310)
        mock_mouse_watcher = Mock()
        mock_mouse_watcher.hasMouse.return_value = True

        player = PlayerController(SimpleNamespace(game_state='PLAYING'), mock_win,
                                  NodePath('camera'), mock_mouse_watcher, None, Mock())
        player.reset_position(0, 0, heading=0, pitch=0)
        player.mouse_locked = True
        player.is_aiming = True

        # AR 조준사격 반동 1.5도 인가
        player.add_weapon_recoil(1.5, 0.0, weapon="AR", is_ads=True)
        self.assertEqual(player.recoil_pitch.position, 1.5)
        self.assertGreater(player.ar_recoil_hold_timer, 0.0)

        # 마우스를 당긴 상태로 프레임 갱신 -> 반동 수동 흡수
        player.update(0.016, {})

        # 10px * (0.13 * 0.88) = 1.144도 흡수되어 recoil_pitch가 0.356도 이하로 줄어들고, pitch는 0 유지
        self.assertLess(player.recoil_pitch.position, 0.40)
        self.assertEqual(player.pitch, 0.0, "반동을 잡는 동안 기본 에임 앙각(pitch)이 바닥으로 처지지 않아야 함")


if __name__ == '__main__':
    unittest.main()
