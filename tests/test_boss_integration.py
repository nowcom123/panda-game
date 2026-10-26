"""Regression checks using the real boss hierarchy and collision system."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from panda3d.core import NodePath, Vec3
from monster import CableOverlordBoss
from boss_patterns import BossPatternState as State
from collision import register_custom_collider, clear_custom_colliders


class BossIntegrationTests(unittest.TestCase):
    def test_leg_break_interrupts_attack_and_exposes_head(self):
        self.ctrl._start_bone_arm_sweep(self.game)
        self.boss.take_damage(300, hit_part=0)
        self.assertEqual(self.boss.leg_hp[0], 0)
        self.assertTrue(self.boss.spider_legs[0][0].isHidden())
        self.assertEqual(self.ctrl.state, State.RECOVERY)
        self.assertEqual(self.ctrl.recovery_duration, 2)
        self.assertFalse(self.ctrl.indicators)
        before = self.boss.hp
        self.boss.take_damage(100, hit_part='head')
        self.assertAlmostEqual(before-self.boss.hp, 135)
        self.ctrl.timer = .5
        self.boss.take_damage(10)  # DOT/explosion does not reuse the previous ray part.
        self.assertEqual(self.ctrl.timer, .5)
        self.assertEqual(self.boss.leg_hp[1], 300)

    def test_leg_ray_tracks_bones_and_broken_leg_is_excluded(self):
        bone = self.boss.leg_hit_nodes[0][1]
        center = self.root.getRelativePoint(bone, Vec3(0))
        origin = center + Vec3(0, 0, 5)
        hit, distance = self.boss.is_hit_by_ray(origin, Vec3(0, 0, -1))
        self.assertTrue(hit)
        self.assertIsInstance(self.boss.last_hit_part, int)
        index = self.boss.last_hit_part
        self.boss.take_damage(300, hit_part=index)
        self.boss.is_hit_by_ray(origin, Vec3(0, 0, -1))
        self.assertNotEqual(self.boss.last_hit_part, index)

    def test_phase_two_spikes_chain_with_fresh_telegraph_then_finish(self):
        self.boss.phase = 2
        self.ctrl._start_bone_spikes(self.game, 0, 8)
        self.step(1)
        self.step(1.4)
        self.assertTrue(self.ctrl.pending_chain)
        self.step(.41)
        self.assertEqual(self.ctrl.current_pattern, 'leap')
        self.assertEqual(self.ctrl.state, State.TELEGRAPH)
        self.assertGreaterEqual(self.ctrl.telegraph_duration, .8)
        self.step(1)
        self.step(1)
        self.assertFalse(self.ctrl.pending_chain)
        self.step(2)
        self.assertEqual(self.ctrl.state, State.IDLE)

    def setUp(self):
        self.root = NodePath('boss_integration')
        self.boss = CableOverlordBoss(self.root, 0, 0)
        self.ctrl = self.boss.pattern_controller
        self.player = SimpleNamespace(take_damage=Mock(return_value=False),
                                      trigger_quake_shake=Mock(), apply_slow=Mock())
        self.game = SimpleNamespace(render=self.root, chunks={}, player=self.player,
                                    monsters=[self.boss], shockwaves=[],
                                    spawn_fireball=Mock(), trigger_game_over=Mock())
        clear_custom_colliders()

    def tearDown(self):
        clear_custom_colliders()
        self.boss.destroy()
        self.root.removeNode()

    def step(self, dt=.05, x=0, y=8, z=1.7):
        return self.ctrl.update(dt, self.game, x, y, z, math.hypot(x, y), abs(z-self.boss.pos.z))

    def test_all_patterns_finish_recovery_and_can_repeat(self):
        for _ in range(2):
            for name in ('sweep', 'spikes', 'leap', 'volley'):
                with self.subTest(pattern=name):
                    if name == 'sweep':
                        self.ctrl._start_bone_arm_sweep(self.game)
                    elif name == 'spikes':
                        self.ctrl._start_bone_spikes(self.game, 0, 8)
                    elif name == 'leap':
                        self.ctrl.leap_start = Vec3(self.boss.pos)
                        self.ctrl.leap_target = Vec3(0, 8-self.boss.pos.y, 0)
                        self.ctrl._start_spider_leap_slam(self.game, 0, 8)
                    else:
                        self.ctrl._start_bone_volley(self.game, 0, 8, 1.7)
                    states = set()
                    for frame in range(100):
                        states.add(self.ctrl.state)
                        self.step()
                        if self.ctrl.state == State.IDLE:
                            break
                    self.assertEqual(self.ctrl.state, State.IDLE)
                    self.assertIn(State.RECOVERY, states)
                    self.assertFalse(self.ctrl.indicators)
                    self.assertFalse(self.ctrl.bone_spikes)
                    self.assertFalse(self.ctrl.is_skull_exposed)

    def test_wall_blocks_sweep_and_spikes(self):
        register_custom_collider((-5, 1, 5, 1.2))
        self.ctrl._start_bone_arm_sweep(self.game)
        self.step(1, y=3)
        self.step(1, y=3)
        self.player.take_damage.assert_not_called()
        self.ctrl.cleanup()
        self.ctrl._start_bone_spikes(self.game, 0, 3)
        self.step(1, y=3)
        self.step(1, y=3)
        self.player.take_damage.assert_not_called()

    def test_leap_cannot_cross_wall_and_stops_if_wall_appears(self):
        self.assertTrue(self.ctrl._can_leap_to_target(self.game, 0, 8))
        self.ctrl._start_spider_leap_slam(self.game, 0, 8)
        self.step(1)
        register_custom_collider((-5, 4, 5, 4.15))
        self.step(1)
        self.assertLess(self.boss.pos.y, 4)
        self.assertEqual(self.boss.pos.z, 0)
        self.assertEqual(self.ctrl.state, State.RECOVERY)
        self.player.take_damage.assert_not_called()
        self.assertFalse(self.ctrl._can_leap_to_target(self.game, 0, 8))

    def test_sweep_damage_follows_rotating_arm(self):
        self.ctrl._start_bone_arm_sweep(self.game)
        self.step(1, y=3)
        self.step(.01, y=3)
        self.player.take_damage.assert_not_called()
        self.step(.18, y=3)
        self.player.take_damage.assert_called_once()
        self.step(.6, y=3)
        self.player.take_damage.assert_called_once()

    def test_volley_aim_locked_and_rib_dimensions_restored(self):
        original = [Vec3(r.getScale()) for r in self.boss.rib_nodes]
        self.boss.phase = 2
        self.ctrl._start_bone_volley(self.game, 0, 8, 1.7)
        targets = list(self.ctrl.volley_targets)
        self.assertGreaterEqual(self.ctrl.telegraph_duration, .8)
        self.step(1, x=15, y=0)
        self.step(.05, x=15, y=0)
        self.step(.05, x=15, y=0)
        self.assertEqual(self.game.spawn_fireball.call_count, 5)
        self.assertEqual([c.args[1] for c in self.game.spawn_fireball.call_args_list], targets)
        for rib, scale in zip(self.boss.rib_nodes, original):
            self.assertLess((rib.getScale()-scale).length(), 1e-6)

    def test_dead_boss_cannot_restart_attacks(self):
        self.ctrl._start_bone_arm_sweep(self.game)
        self.boss.hp = 0
        self.step(10)
        self.step(10)
        self.assertEqual(self.ctrl.state, State.IDLE)
        self.assertFalse(self.ctrl.indicators)
        self.player.take_damage.assert_not_called()

    def test_stun_advances_elemental_effects_once(self):
        self.boss.stun_timer = 1
        with patch.object(self.boss, 'update_elemental') as update:
            self.boss.update_pos(0, 0, .1, 0, 0)
        update.assert_called_once_with(.1)
        self.assertAlmostEqual(self.boss.stun_timer, .9)

    def test_headshot_follows_rotated_recovery_pose(self):
        self.boss.node.setH(75)
        self.ctrl._enter_recovery(1)
        center = self.root.getRelativePoint(self.boss.cranium, Vec3(0))
        hit, distance = self.boss.is_hit_by_ray(center+Vec3(0, 10, 0), Vec3(0, -1, 0))
        self.assertTrue(hit)
        self.assertTrue(self.boss.last_hit_was_head)
        self.assertLess(distance, 10)
