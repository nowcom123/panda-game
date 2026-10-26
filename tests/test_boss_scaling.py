import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import NodePath
from boss_scaling import apply_boss_scaling, movement_multiplier, scaling_for_stage
from monster import CableOverlordBoss
from projectiles import Fireball


class BossScalingTests(unittest.TestCase):
    def setUp(self):
        self.root = NodePath('scaling_test')
        self.boss = CableOverlordBoss(self.root, 0, 0)
        self.game = SimpleNamespace(render=self.root, chunks={}, player=Mock(),
                                    trigger_game_over=Mock())
        self.game.player.take_damage.return_value = False

    def tearDown(self):
        self.boss.destroy()
        self.root.removeNode()

    def test_stage_health_and_bounded_damage_movement(self):
        for stage, hp in ((1, 3500), (3, 3500), (6, 6650), (10, 10850)):
            self.assertAlmostEqual(3500 * scaling_for_stage(stage).health, hp)
        far = scaling_for_stage(10000)
        self.assertEqual(far.damage, 1.6)
        self.assertEqual(far.movement, 1.15)

    def test_no_reapplication_healing_or_double_movement(self):
        apply_boss_scaling(self.boss, 6)
        self.assertAlmostEqual(self.boss.max_hp, 6650)
        self.assertAlmostEqual(self.boss.leg_hp[0], 462)
        self.boss.hp -= 200
        self.boss.leg_hp[0] = 0
        apply_boss_scaling(self.boss, 10)
        self.assertAlmostEqual(self.boss.hp, 6450)
        self.assertEqual(self.boss.leg_hp[0], 0)
        self.assertEqual(self.boss.stage_level, 6)
        self.assertEqual(movement_multiplier(self.boss, 4), 1)
        self.assertEqual(movement_multiplier(SimpleNamespace(), 4), 4)

    def test_sweep_damage_and_phase_two_preserve_scaling(self):
        apply_boss_scaling(self.boss, 6)
        ctrl = self.boss.pattern_controller
        for phase, expected in ((1, 28 * 1.24), (2, 36 * 1.24)):
            if phase == 2:
                ctrl._enter_phase_2(self.game)
                self.assertAlmostEqual(self.boss.speed, 5.8 * 1.06)
            ctrl._start_bone_arm_sweep(self.game)
            self.assertGreaterEqual(ctrl.telegraph_duration, .8)
            ctrl.timer = ctrl.active_duration
            ctrl._update_sweep_active(.1, self.game, 3, 0, 1.7, 3, 1.7)
            self.assertAlmostEqual(self.game.player.take_damage.call_args.args[0], expected)
            ctrl.cleanup()

    def test_pooled_volley_resets_damage_for_ordinary_enemy(self):
        from game import LiminalInfiniteLoop
        projectile = Fireball(self.root)
        try:
            apply_boss_scaling(self.boss, 6)
            pool = SimpleNamespace(fireball_pool=[projectile], fireballs=[])
            self.game.spawn_fireball = lambda start, target, **kw: LiminalInfiniteLoop.spawn_fireball(pool, start, target, **kw)
            ctrl = self.boss.pattern_controller
            ctrl.volley_targets = [(0, 5, 1.7)]
            ctrl._update_volley_active(.1, self.game, 0, 5, 1.7)
            self.assertAlmostEqual(projectile.damage, 22 * 1.24)
            # Pool exhaustion uses the same object, and must also reset damage.
            LiminalInfiniteLoop.spawn_fireball(pool, (0, 0, 1), (0, 5, 1))
            self.assertEqual(projectile.damage, 22)
            projectile.deactivate()
            LiminalInfiniteLoop.spawn_fireball(pool, (0, 0, 1), (0, 5, 1))
            self.assertEqual(projectile.damage, 22)
            self.assertEqual(len(pool.fireballs), 1)
        finally:
            projectile.destroy()

    def test_actual_spawn_initializes_hud_with_scaled_maximum(self):
        from game import LiminalInfiniteLoop
        game = SimpleNamespace(world_root=self.root, boss=None, monsters=[],
                               current_stage=10, ui_mgr=Mock(), audio_mgr=Mock())
        boss = LiminalInfiniteLoop.spawn_boss(game, 0, 0)
        try:
            self.assertEqual(boss.hp, 10850)
            game.ui_mgr.show_boss_hp_bar.assert_called_once_with(boss.name, 10850, 10850)
            boss.hp -= 10
            self.assertIs(LiminalInfiniteLoop.spawn_boss(game, 0, 0), boss)
            self.assertEqual(boss.hp, 10840)
        finally:
            boss.destroy()
