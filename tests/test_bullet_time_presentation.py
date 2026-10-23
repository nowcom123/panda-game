import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath, Vec3
from bullet_time import intensity, world_scale
from combat_system import CombatSystem
from audio_system import AudioManager
from projectiles import Fireball


class BulletTimePresentationTests(unittest.TestCase):
    def test_pause_clears_colour_before_early_return_without_spending_timer(self):
        from game import LiminalInfiniteLoop
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.game_state = 'PAUSED'
        game.bullet_time_timer = 2.0
        game.bullet_time_strength = 1.0
        game.pbr_pipeline = Mock()
        game.ui_mgr = Mock()
        game.update(None)
        self.assertEqual(game.bullet_time_timer, 2.0)
        self.assertEqual(game.bullet_time_strength, 0.0)
        game.pbr_pipeline.set_bullet_time.assert_called_once_with(0.0)
        game.ui_mgr.set_bullet_time_hud.assert_called_with(False)

    def test_envelope_returns_to_normal_without_extending_duration(self):
        self.assertEqual(world_scale(intensity(2, .1)), .25)
        self.assertAlmostEqual(world_scale(intensity(.15, 2)), .625)
        self.assertEqual(world_scale(intensity(0, 2)), 1)

    def test_cosmetics_slow_but_weapon_cooldown_and_reload_do_not(self):
        root = NodePath('test')
        try:
            base = SimpleNamespace(bullet_time_timer=2, bullet_time_strength=1, camLens=Mock())
            combat = CombatSystem(base, root, root.attachNewNode('camera'), root, None, Mock())
            combat.casing_effects.update = Mock()
            combat.shoot_cooldown = .5
            combat.is_reloading = True
            combat.reload_timer = 1.0
            particle = combat.hit_particle_pool[0]
            particle.update(active=True, timer=1., vel=Vec3(1, 0, 0), pos=Vec3(0, 0, 1))
            combat.update(.1)
            combat.casing_effects.update.assert_called_once_with(.025)
            self.assertAlmostEqual(particle['timer'], .975)
            self.assertAlmostEqual(combat.shoot_cooldown, .4)
            self.assertAlmostEqual(combat.reload_timer, .9)
        finally:
            root.removeNode()

    def test_world_audio_restores_and_gun_attack_keeps_pitch(self):
        audio = AudioManager.__new__(AudioManager)
        audio.bullet_time_hum_sfx = None
        audio.bullet_time_audio_active = True
        audio.bullet_time_audio_elapsed = 0
        audio.bullet_time_audio_level = 0
        sound = Mock()
        audio._register_world_sound(sound, .8)
        audio.update_bullet_time(.12)
        self.assertAlmostEqual(sound.setPlayRate.call_args.args[0], .45)
        audio.gunshot_voices = [Mock()]
        audio.gunshot_voice_index = 0
        audio.play_gunshot()
        audio.gunshot_voices[0].setPlayRate.assert_called_once_with(1.0)
        audio.stop_bullet_time()
        sound.setPlayRate.assert_called_with(1.)
        sound.setVolume.assert_called_with(.8)

    def test_projectile_trails_are_pooled_and_hidden_after_effect(self):
        root = NodePath('test')
        ball = Fireball(root)
        try:
            ball.activate((0, 0, 1), (0, 10, 1))
            ghosts = tuple(ball.time_trail)
            ball.time_trail_strength = 1.
            ball.update(.025)
            self.assertTrue(all(not g.isHidden() for g in ghosts))
            ball.time_trail_strength = 0.
            ball.update(.1)
            self.assertTrue(all(g.isHidden() for g in ghosts))
            self.assertEqual(tuple(ball.time_trail), ghosts)
        finally:
            ball.destroy()
            root.removeNode()
