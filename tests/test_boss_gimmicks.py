import unittest
import math
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

from panda3d.core import NodePath, Vec3
from boss_scaling import apply_boss_scaling
from boss_patterns import FanWaveIndicator, BoneHeartSeal, BossPatternState
from monster import CableOverlordBoss
from combat.weapon_config import WEAPON_CONFIGS


class BossGimmicksTests(unittest.TestCase):
    def setUp(self):
        self.root = NodePath('test_root')
        self.boss = CableOverlordBoss(self.root, 0, 0)
        self.player = SimpleNamespace(
            pos=Vec3(0, 8, 0),
            take_damage=Mock(return_value=False),
            trigger_quake_shake=Mock(),
            get_attack_power=Mock(return_value=35.0),
        )
        self.game = SimpleNamespace(
            render=self.root,
            chunks={},
            player=self.player,
            ui_mgr=Mock(),
            audio_mgr=Mock(),
            trigger_game_over=Mock(),
            current_stage=5,
        )

    def tearDown(self):
        self.boss.destroy()
        self.root.removeNode()

    def test_fan_wave_safe_corridor_and_danger_sector(self):
        ctrl = self.boss.pattern_controller
        # Stage 3+: Start fan wave facing +Y (90 deg / math.pi/2)
        ctrl._start_bone_fan_wave(self.game, 0, 8)
        self.assertEqual(ctrl.current_pattern, "fan_wave")
        self.assertGreaterEqual(ctrl.telegraph_duration, 1.0)
        self.assertAlmostEqual(ctrl.fan_wave_angle, math.pi / 2, places=4)

        # Complete telegraph
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_fan_wave_telegraph(0.1, self.game)
        self.assertEqual(ctrl.state, BossPatternState.ACTIVE)

        # Case 1: Player inside safe corridor (directly along fan_wave_angle, angle diff = 0 < 12 deg)
        self.player.pos = Vec3(0, 8, 0)
        ctrl.fan_wave_hit_done = False
        ctrl._update_fan_wave_active(0.1, self.game, 0, 8, 1.7)
        self.assertTrue(ctrl.fan_wave_hit_done)
        self.player.take_damage.assert_not_called()

        # Case 2: Player inside danger zone (30 degrees offset from fan_wave_angle)
        rad = math.pi / 2 + math.radians(30)
        px = math.cos(rad) * 8.0
        py = math.sin(rad) * 8.0
        ctrl.fan_wave_hit_done = False
        ctrl._update_fan_wave_active(0.1, self.game, px, py, 1.7)
        self.assertTrue(ctrl.fan_wave_hit_done)
        self.player.take_damage.assert_called_once()
        damage_taken = self.player.take_damage.call_args[0][0]
        self.assertAlmostEqual(damage_taken, 28.0)

        # Case 3: Single hit per wave — subsequent frames should not hit again
        self.player.take_damage.reset_mock()
        ctrl._update_fan_wave_active(0.1, self.game, px, py, 1.7)
        self.player.take_damage.assert_not_called()
        ctrl.cleanup()

    def test_fan_wave_stage_requirement_and_wall_block(self):
        ctrl = self.boss.pattern_controller
        self.boss.stage_level = 2
        # Under stage 3, fan wave should not be selected
        ctrl._select_next_pattern(self.game, 0, 8, 1.7, 8.0, 0.0)
        self.assertNotEqual(ctrl.current_pattern, "fan_wave")

        # Stage 3+: if path is blocked, fan wave should not start
        self.boss.stage_level = 3
        with patch('boss_patterns.clear_attack_path', return_value=False):
            self.assertFalse(ctrl._can_start_fan_wave(self.game, 0, 8))

    def test_bone_heart_seal_generation_protection_and_destruction(self):
        ctrl = self.boss.pattern_controller
        apply_boss_scaling(self.boss, 6)
        self.boss.stage_level = 6

        # Start seal pattern
        ctrl._start_bone_heart_seal(self.game, 0, 8)
        self.assertEqual(ctrl.current_pattern, "seal")
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_seal_telegraph(0.1, self.game)

        # Active state: protection active, seals spawned
        self.assertTrue(ctrl.is_protecting)
        self.assertTrue(self.boss.is_protected)
        self.assertGreaterEqual(len(ctrl.active_seals), 1)
        self.assertLessEqual(len(ctrl.active_seals), 2)

        # Test 60% damage reduction on boss
        old_hp = self.boss.hp
        self.boss.take_damage(100.0)
        self.assertAlmostEqual(self.boss.hp, old_hp - 40.0)

        # Test seal raycast hit and destruction
        seal = ctrl.active_seals[0]
        hit, dist = seal.is_hit_by_ray(Vec3(seal.pos.x, seal.pos.y - 5.0, seal.pos.z + 0.7), Vec3(0, 1, 0))
        self.assertTrue(hit)
        self.assertGreater(dist, 0.0)

        # Destroy all seals
        for s in list(ctrl.active_seals):
            s.take_damage(999.0)

        # Update active: all seals dead -> protection lifted, 2s stun and skull exposed!
        ctrl._update_seal_active(0.1, self.game, 0, 8, 1.7)
        self.assertFalse(ctrl.is_protecting)
        self.assertFalse(self.boss.is_protected)
        self.assertEqual(self.boss.stun_timer, 2.0)
        self.assertTrue(ctrl.is_skull_exposed)
        self.assertEqual(ctrl.state, BossPatternState.RECOVERY)
        ctrl.cleanup()

    def test_bone_heart_seal_timeout_ends_without_stun(self):
        ctrl = self.boss.pattern_controller
        self.boss.stage_level = 5
        ctrl._start_bone_heart_seal(self.game, 0, 8)
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_seal_telegraph(0.1, self.game)

        self.assertTrue(ctrl.is_protecting)
        self.assertGreater(len(ctrl.active_seals), 0)

        # Run out the 8 second timer
        ctrl._update_seal_active(8.1, self.game, 0, 8, 1.7)
        self.assertFalse(ctrl.is_protecting)
        self.assertFalse(self.boss.is_protected)
        self.assertEqual(len(ctrl.active_seals), 0)
        # Timeout does not grant stun bonus
        self.assertEqual(self.boss.stun_timer, 0.0)
        ctrl.cleanup()

    def test_cleanup_clears_all_seals_and_protection(self):
        ctrl = self.boss.pattern_controller
        self.boss.stage_level = 5
        ctrl._start_bone_heart_seal(self.game, 0, 8)
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_seal_telegraph(0.1, self.game)
        self.assertTrue(self.boss.is_protected)

        # Invoke cleanup (called on boss death, leg break interruption, next floor, menu exit)
        ctrl.cleanup()
        self.assertFalse(self.boss.is_protected)
        self.assertFalse(ctrl.is_protecting)
        self.assertEqual(len(ctrl.active_seals), 0)

    def test_spider_leap_prohibited_when_four_legs_broken(self):
        ctrl = self.boss.pattern_controller
        # Initially all legs intact -> leap allowed
        self.assertTrue(ctrl._can_leap_to_target(self.game, 0, 10))

        # Break 3 legs -> leap still allowed
        self.boss.leg_hp[0] = 0
        self.boss.leg_hp[1] = 0
        self.boss.leg_hp[2] = 0
        self.assertTrue(ctrl._can_leap_to_target(self.game, 0, 10))

        # Break 4th leg -> leap forbidden!
        self.boss.leg_hp[3] = 0
        self.assertFalse(ctrl._can_leap_to_target(self.game, 0, 10))

    def test_boss_hud_level_and_broken_parts(self):
        from ui_manager import UIManager
        ui = UIManager.__new__(UIManager)
        ui.base = SimpleNamespace(boss=self.boss)
        ui.boss_hud_frame = Mock()
        ui.boss_hud_frame.isHidden.return_value = False
        ui.boss_bar_fill = MagicMock()
        ui.boss_name_text = Mock()
        ui.boss_hp_text = Mock()
        ui._boss_hud_name = "골해의 지배자"
        ui._boss_hp_display_ratio = None
        ui._boss_hp_target_ratio = None
        ui._boss_hud_stage_level = None
        ui._boss_hud_broken_legs = None
        ui._boss_hud_phase = None
        ui._boss_hud_last_broken = None

        self.boss.stage_level = 6
        self.boss.leg_hp[0] = 0
        self.boss.leg_hp[1] = 0
        # 2 legs broken out of 8
        ui._animate_boss_hp(0.1)
        ui.boss_name_text.setText.assert_called_with("[Lv.6] 골해의 지배자 (다리 파괴: 2/8)")


if __name__ == '__main__':
    unittest.main()
