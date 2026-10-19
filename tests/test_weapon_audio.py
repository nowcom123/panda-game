"""Regression checks for rapid fire and frame-independent shotgun action."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from audio_system import AudioManager
from combat_system import CombatSystem


class WeaponAudioTests(unittest.TestCase):
    def test_fast_fire_uses_independent_voices_without_pitch_changes(self):
        manager = AudioManager.__new__(AudioManager)
        manager.gunshot_voices = [Mock() for _ in range(24)]
        manager.gunshot_voice_index = 0
        for _ in range(24):
            manager.play_gunshot()
        for sound in manager.gunshot_voices:
            sound.play.assert_called_once()
            sound.stop.assert_not_called()
            sound.setPlayRate.assert_called_once_with(1.0)
        manager.play_gunshot()
        self.assertEqual(manager.gunshot_voices[0].play.call_count, 2)

    def test_pump_and_ejection_fire_once_even_when_frame_skips_threshold(self):
        for steps in ([1 / 60] * 60, [.3, .3, .3], [.6, .6]):
            with self.subTest(steps=steps[:3]):
                node = Mock()
                node.isEmpty.return_value = False
                state = SimpleNamespace(sg_pump_node=node, sg_pump_timer=.44,
                                        sg_pump_cycled=False, audio_mgr=Mock(),
                                        _eject_casing=Mock())
                for dt in steps:
                    CombatSystem._update_shotgun_pump(state, dt)
                state.audio_mgr.play_shotgun_pump.assert_called_once()
                state._eject_casing.assert_called_once_with(is_left=False, is_shotgun=True)
                self.assertEqual(state.sg_pump_timer, 0)
                node.setPos.assert_called_with(0, .28, -.010)

    def test_pump_waits_for_action_and_ejection_timing(self):
        node = Mock()
        node.isEmpty.return_value = False
        state = SimpleNamespace(sg_pump_node=node, sg_pump_timer=.44,
                                sg_pump_cycled=False, audio_mgr=Mock(),
                                _eject_casing=Mock())
        CombatSystem._update_shotgun_pump(state, .02)
        state.audio_mgr.play_shotgun_pump.assert_not_called()
        CombatSystem._update_shotgun_pump(state, .03)
        state.audio_mgr.play_shotgun_pump.assert_called_once()
        state._eject_casing.assert_not_called()
        CombatSystem._update_shotgun_pump(state, .12)
        state._eject_casing.assert_called_once()

    def test_reload_selects_weapon_recording_and_cancels_previous_actions(self):
        manager = AudioManager.__new__(AudioManager)
        manager.reload_sfx = Mock()
        manager.reload_sounds = {k: Mock() for k in ("PISTOL", "DUAL_PISTOL", "SHOTGUN")}
        manager.shotgun_pump_sfx = Mock()
        manager.reload_sounds["SHOTGUN"].length.return_value = 1.75
        manager.play_reload("SHOTGUN", duration=1.75)
        manager.reload_sounds["SHOTGUN"].play.assert_called_once()
        manager.reload_sounds["SHOTGUN"].setPlayRate.assert_called_once_with(1.0)
        manager.reload_sounds["PISTOL"].play.assert_not_called()
        manager.reload_sounds["DUAL_PISTOL"].play.assert_not_called()
        manager.shotgun_pump_sfx.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
