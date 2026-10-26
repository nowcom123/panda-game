import unittest
from unittest.mock import Mock
from panda3d.core import NodePath
from audio_system import AudioManager


class HoundAudioTests(unittest.TestCase):
    def test_hound_helpers_reach_real_3d_pool(self):
        for key, method, volume in (
                ('hound_growl', 'play_hound_growl', 1.0),
                ('hound_step', 'play_hound_step', .85)):
            with self.subTest(sound=key):
                audio = AudioManager.__new__(AudioManager)
                audio.audio3d = Mock()
                audio._register_world_sound = Mock()
                sound = Mock()
                sound.PLAYING = 2
                sound.status.return_value = 0
                audio.monster_sound_pools = {key: dict(instances=[sound], idx=0,
                    base_vol=.9, min_dist=2, max_dist=32)}
                node = NodePath('hound')
                try:
                    getattr(audio, method)(node)
                    audio.audio3d.attachSoundToObject.assert_called_once_with(sound, node)
                    sound.setVolume.assert_called_once_with(.9*volume)
                    sound.play.assert_called_once()
                finally:
                    node.removeNode()

    def test_non_spatial_fallback(self):
        audio = AudioManager.__new__(AudioManager)
        audio.audio3d = None
        audio.hound_growl_sfx = Mock()
        audio.hound_step_sfx = Mock()
        audio.play_hound_growl()
        audio.play_hound_step()
        audio.hound_growl_sfx.play.assert_called_once()
        audio.hound_step_sfx.play.assert_called_once()
