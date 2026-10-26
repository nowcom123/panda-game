import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rpg.characters import CharacterList, CharacterManager
from rpg.items import load_catalog, ValidationError, UnsupportedSaveVersion, SaveCorruptedError


class CharacterReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = load_catalog()
        self.manager = CharacterManager(Path(self.tmp.name), self.catalog)
        self.first = self.manager.create_character('First')

    def test_list_rejects_duplicate_and_unknown_active(self):
        data = self.manager.character_list.to_dict()
        data['characters'].append(dict(data['characters'][0]))
        with self.assertRaises(ValidationError):
            CharacterList.from_dict(data)
        data['characters'].pop()
        data['active_character_id'] = str(uuid.uuid4())
        with self.assertRaises(ValidationError):
            CharacterList.from_dict(data)

    def test_failed_creation_and_selection_preserve_memory_and_disk(self):
        second = self.manager.create_character('Second')
        before = self.manager.list_path.read_bytes()
        with patch.object(self.manager, '_atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.select_character(self.first.id)
            with self.assertRaises(OSError):
                self.manager.create_character('Third')
        self.assertEqual(self.manager.character_list.active_character_id, second.id)
        self.assertEqual(len(self.manager.character_list.characters), 2)
        self.assertEqual(self.manager.list_path.read_bytes(), before)

    def test_future_backup_not_overwritten(self):
        payload = self.manager.character_list.to_dict()
        payload['version'] = 9
        self.manager.list_backup_path.write_text(json.dumps(payload), encoding='utf-8')
        before = self.manager.list_backup_path.read_bytes()
        with self.assertRaises(UnsupportedSaveVersion):
            self.manager.save_character_list()
        self.assertEqual(self.manager.list_backup_path.read_bytes(), before)

    def test_missing_character_profile_does_not_become_empty_profile(self):
        store = self.manager.get_active_save_store()
        store.path.unlink()
        with self.assertRaises(SaveCorruptedError):
            self.manager.get_active_save_store()
        self.assertFalse(store.path.exists())

    def test_corrupt_selection_keeps_previous_session(self):
        from game import LiminalInfiniteLoop
        second = self.manager.create_character('Second')
        store = self.manager.get_character_save_store(self.first.id)
        store.path.write_text('{broken', encoding='utf-8')
        old_session = object()
        game = SimpleNamespace(game_state='INTRO', character_mgr=self.manager,
                               rpg_catalog=self.catalog, rpg_session=old_session,
                               combat=Mock(), ui_mgr=Mock())
        self.assertFalse(LiminalInfiniteLoop.switch_to_character(game, self.first.id))
        self.assertIs(game.rpg_session, old_session)
        self.assertEqual(self.manager.character_list.active_character_id, second.id)
        game.combat.set_rpg_session.assert_not_called()
        self.assertTrue(game.character_error)


class SealReviewTests(unittest.TestCase):
    def test_real_player_without_pos_uses_telegraphed_positions(self):
        from panda3d.core import NodePath
        from monster import CableOverlordBoss
        root = NodePath('review')
        boss = CableOverlordBoss(root, 0, 0)
        try:
            boss.stage_level = 5
            game = SimpleNamespace(render=root, chunks={}, player=SimpleNamespace())
            ctrl = boss.pattern_controller
            ctrl._start_bone_heart_seal(game, 0, 8)
            ctrl.timer = ctrl.telegraph_duration
            ctrl._update_seal_telegraph(.1, game)
            self.assertEqual(len(ctrl.active_seals), 2)
            self.assertGreater((ctrl.active_seals[0].pos - ctrl.active_seals[1].pos).length(), 7)
            for seal in ctrl.active_seals:
                self.assertAlmostEqual((seal.pos - boss.pos).length(), 3.8, places=5)
        finally:
            boss.destroy()
            root.removeNode()

    def test_blocked_seals_cancel_without_free_weakpoint_reward(self):
        from panda3d.core import NodePath
        from monster import CableOverlordBoss
        root = NodePath('review')
        boss = CableOverlordBoss(root, 0, 0)
        try:
            boss.stage_level = 5
            game = SimpleNamespace(render=root, chunks={})
            ctrl = boss.pattern_controller
            ctrl._start_bone_heart_seal(game, 0, 8)
            ctrl.timer = ctrl.telegraph_duration
            with patch('boss_patterns.clear_attack_path', return_value=False):
                ctrl._update_seal_telegraph(.1, game)
            self.assertFalse(ctrl.is_protecting)
            self.assertFalse(ctrl.is_skull_exposed)
            self.assertFalse(ctrl.active_seals)
            self.assertFalse(boss.is_protected)
        finally:
            boss.destroy()
            root.removeNode()
