"""Attack windup, interruption and directional dodge regressions."""

import unittest
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import Vec3

import test_gameplay_regressions as fixtures
from audio_system import AudioManager
from monster import AbominableMudOrc, AlluringAshWitch, ShadowStalker


class AttackTelegraphs(unittest.TestCase):
    setUp = fixtures.GameplayRegressions.setUp
    tearDown = fixtures.GameplayRegressions.tearDown

    def test_orc_warns_then_impacts_once_and_recovers(self):
        orc = AbominableMudOrc(self.root, 9, 19)
        orc.slam_cooldown = 0
        self.assertTrue(orc.begin_slam(self.audio))
        self.assertFalse(orc.slam_warning.isHidden())
        self.assertFalse(orc.slam_ground(0.49))
        self.assertTrue(orc.slam_ground(0.02))
        self.assertTrue(orc.slam_warning.isHidden())
        self.assertTrue(orc.slam_charge.isHidden())
        self.assertFalse(orc.slam_ground(0.5))
        self.assertFalse(orc.is_slamming)
        self.assertEqual(orc.slam_cooldown, 5.5)
        self.audio.play_attack_warning.assert_called_once_with('orc', orc.pos)

    def test_witch_charge_and_release_are_separate(self):
        witch = AlluringAshWitch(self.root, 9, 19)
        witch.cast_cooldown = 0
        self.assertTrue(witch.begin_cast(self.audio))
        self.assertFalse(witch.cast_fireball(0.39))
        self.assertFalse(witch.cast_warning.isHidden())
        self.assertGreater(witch.orb.getScale().x, 1)
        self.assertTrue(witch.cast_fireball(0.02))
        self.assertTrue(witch.cast_warning.isHidden())
        self.assertFalse(witch.cast_fireball(0.4))
        self.assertFalse(witch.is_casting)
        self.assertEqual(witch.orb.getScale().x, 1)
        self.assertEqual(witch.cast_cooldown, 3.2)
        self.audio.play_attack_warning.assert_called_once_with('witch', witch.pos)

    def test_stalker_warns_without_moving_and_locks_direction(self):
        stalker = ShadowStalker(self.root, 9, 14)
        stalker.lunge_cooldown = 0
        self.assertTrue(stalker.trigger_lunge((9, 9), self.audio))
        initial_pos, initial_dir = Vec3(stalker.pos), Vec3(stalker.lunge_dir)
        self.assertFalse(stalker.trigger_lunge((20, 20), self.audio))
        self.assertFalse(stalker.update_lunge_windup(0.44, self.audio))
        self.assertEqual(stalker.pos, initial_pos)
        self.assertEqual(stalker.lunge_dir, initial_dir)
        self.assertFalse(stalker.is_lunging)
        self.assertFalse(stalker.lunge_warning.isHidden())
        self.audio.play_stalker_lunge.assert_not_called()
        self.assertTrue(stalker.update_lunge_windup(0.02, self.audio))
        self.assertTrue(stalker.is_lunging)
        self.assertTrue(stalker.lunge_warning.isHidden())
        self.assertEqual(stalker.lunge_cooldown, 4.2)
        self.audio.play_attack_warning.assert_called_once_with('stalker', stalker.pos)
        self.audio.play_stalker_lunge.assert_called_once()

    def test_stun_cancels_each_preparation_and_keeps_cooldown(self):
        for cls, cooldown, start, tick, active, warning in (
            (AbominableMudOrc, 'slam_cooldown', 'begin_slam', 'slam_ground', 'is_slamming', 'slam_warning'),
            (AlluringAshWitch, 'cast_cooldown', 'begin_cast', 'cast_fireball', 'is_casting', 'cast_warning'),
            (ShadowStalker, 'lunge_cooldown', 'trigger_lunge', 'update_lunge_windup', 'is_lunge_winding', 'lunge_warning'),
        ):
            with self.subTest(monster=cls.__name__):
                monster = cls(self.root, 9, 14)
                setattr(monster, cooldown, 0)
                args = ((9, 9), self.audio) if cls is ShadowStalker else (self.audio,)
                getattr(monster, start)(*args)
                getattr(monster, tick)(0.2)
                remaining_cooldown = getattr(monster, cooldown)
                monster.stun(0.85)
                self.assertFalse(getattr(monster, active))
                self.assertTrue(getattr(monster, warning).isHidden())
                self.assertFalse(getattr(monster, tick)(0.8))
                self.assertEqual(getattr(monster, cooldown), remaining_cooldown)
                self.assertFalse(getattr(monster, start)(*args))
                monster.destroy()

    def test_preparation_cannot_be_bypassed_by_contact_damage(self):
        for cls in (AbominableMudOrc, AlluringAshWitch, ShadowStalker):
            with self.subTest(monster=cls.__name__):
                monster = cls(self.root, 9, 10)
                monster.has_los, monster.los_timer = True, 1
                if cls is AbominableMudOrc:
                    monster.slam_cooldown = 0
                    monster.begin_slam(self.audio)
                elif cls is AlluringAshWitch:
                    monster.cast_cooldown = 0
                    monster.begin_cast(self.audio)
                else:
                    monster.lunge_cooldown = 0
                    monster.trigger_lunge((9, 9), self.audio)
                self.game.monsters = [monster]
                hp = self.player.hp
                self.game._update_monsters(0.1, 9, 9)
                self.assertEqual(self.player.hp, hp)
                monster.destroy()

    def test_stalker_direction_can_be_dodged_and_walls_block_lunge(self):
        for wall in (False, True):
            with self.subTest(wall=wall):
                stalker = ShadowStalker(self.root, 9, 14)
                stalker.lunge_cooldown = 0
                stalker.trigger_lunge((9, 9), self.audio)
                stalker.update_lunge_windup(0.45, self.audio)
                stalker.has_los, stalker.los_timer = True, 1
                cols = {(1, 1): [(8, 11.5, 10, 11.7)], (1, 2): [(8, 11.5, 10, 11.7)]} if wall else {}
                self.game.chunks = {(0, 0): SimpleNamespace(cell_colliders=cols)}
                self.game.monsters = [stalker]
                for _ in range(4):
                    self.game._update_monsters(0.1, 13, 9)
                self.assertEqual(self.player.hp, 100)
                self.assertAlmostEqual(stalker.pos.x, 9)
                if wall:
                    self.assertGreaterEqual(stalker.pos.y, 12.09)
                else:
                    self.assertLess(stalker.pos.y, 9)
                stalker.destroy()

    def test_death_hides_all_attack_warnings(self):
        orc = AbominableMudOrc(self.root, 9, 19)
        witch = AlluringAshWitch(self.root, 12, 19)
        stalker = ShadowStalker(self.root, 9, 14)
        orc.slam_cooldown = witch.cast_cooldown = stalker.lunge_cooldown = 0
        orc.begin_slam(self.audio)
        witch.begin_cast(self.audio)
        stalker.trigger_lunge((9, 9), self.audio)
        for monster, warning in ((orc, orc.slam_warning), (witch, witch.cast_warning), (stalker, stalker.lunge_warning)):
            monster.turn_into_corpse()
            self.assertTrue(warning.isHidden())
            monster.destroy()
            self.assertFalse(self.root.isAncestorOf(warning))


class AttackWarningAudio(unittest.TestCase):
    def test_warning_pool_positions_and_stops_sounds_on_scene_change(self):
        audio = AudioManager.__new__(AudioManager)
        sounds = [Mock(), Mock()]
        audio._attack_warning_pools = {'orc': sounds}
        audio._attack_warning_indices = {'orc': 0}
        audio.attack_warning_sfx = sounds
        audio.play_attack_warning('orc', Vec3(1, 2, 3))
        audio.play_attack_warning('orc', Vec3(4, 5, 6))
        for sound in sounds:
            sound.play.assert_called_once()
        sounds[0].set3dAttributes.assert_called_once_with(1, 2, 4, 0, 0, 0)
        sounds[1].set3dAttributes.assert_called_once_with(4, 5, 7, 0, 0, 0)
        audio.stop_effects()
        for sound in sounds:
            sound.stop.assert_called_once()

    def test_warning_assets_match_preparation_duration(self):
        folder = Path(__file__).resolve().parents[1] / 'assets' / 'audio'
        for name, duration in (('orc_slam_charge.wav', 0.5), ('witch_cast_charge.wav', 0.4), ('stalker_lunge_charge.wav', 0.45)):
            data = (folder / name).read_bytes()
            self.assertEqual(data[:4], b'RIFF')
            self.assertEqual(data[8:12], b'WAVE')
            pcm_format, channels, rate = struct.unpack_from('<HHI', data, 20)
            self.assertEqual((pcm_format, channels), (1, 1))
            self.assertEqual(struct.unpack_from('<H', data, 34)[0], 16)
            self.assertEqual(data[36:40], b'data')
            self.assertAlmostEqual((len(data) - 44) / (rate * channels * 2), duration)


if __name__ == '__main__':
    unittest.main()
