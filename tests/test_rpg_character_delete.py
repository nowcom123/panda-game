import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from rpg.characters import CharacterManager
from rpg.items import load_catalog, ValidationError


class CharacterDeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = load_catalog()
        self.manager = CharacterManager(Path(self.tmp.name), self.catalog)
        self.first = self.manager.create_character('First')
        self.second = self.manager.create_character('Second')

    def test_delete_inactive_keeps_active_and_profile_for_recovery(self):
        path = self.manager.get_character_save_store(self.first.id).path
        original = path.read_bytes()
        self.assertFalse(self.manager.delete_character(self.first.id, confirmation_name='First'))
        loaded = CharacterManager(Path(self.tmp.name), self.catalog).load_character_list()
        self.assertEqual([c.id for c in loaded.characters], [self.second.id])
        self.assertEqual(loaded.active_character_id, self.second.id)
        self.assertEqual(path.read_bytes(), original)

    def test_last_character_removed_stays_empty_and_slot_can_be_reused(self):
        self.assertTrue(self.manager.delete_character(self.second.id, confirmation_name='Second'))
        self.assertIsNone(self.manager.get_active_save_store())
        self.manager.delete_character(self.first.id, confirmation_name='First')
        reloaded = CharacterManager(Path(self.tmp.name), self.catalog)
        self.assertEqual(reloaded.load_character_list().characters, [])
        replacement = reloaded.create_character('Replacement')
        self.assertNotIn(replacement.id, (self.first.id, self.second.id))

    def test_failure_and_wrong_name_keep_roster(self):
        before = self.manager.character_list.to_dict()
        disk = self.manager.list_path.read_bytes()
        with self.assertRaises(ValidationError):
            self.manager.delete_character(self.second.id, confirmation_name='First')
        with patch.object(self.manager, '_atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.delete_character(self.second.id, confirmation_name='Second')
        self.assertEqual(self.manager.character_list.to_dict(), before)
        self.assertEqual(self.manager.list_path.read_bytes(), disk)

    def test_game_blocks_deletion_during_run_and_detaches_deleted_session(self):
        from game import LiminalInfiniteLoop
        game = SimpleNamespace(game_state='PLAYING', character_mgr=self.manager,
                               rpg_session=object(), combat=SimpleNamespace(
                                   rpg_session=object(), active_item_uid='old', item_states={'old': {}}),
                               ui_mgr=SimpleNamespace(equipment_ui=SimpleNamespace(session=object()),
                                                      update_active_explorer_display=Mock()))
        self.assertFalse(LiminalInfiniteLoop.delete_character(game, self.second.id, 'Second'))
        game.game_state = 'INTRO'
        game._extraction_pending = True
        self.assertFalse(LiminalInfiniteLoop.delete_character(game, self.second.id, 'Second'))
        game._extraction_pending = False
        self.assertTrue(LiminalInfiniteLoop.delete_character(game, self.second.id, 'Second'))
        self.assertIsNone(game.rpg_session)
        self.assertIsNone(game.combat.rpg_session)
        self.assertIsNone(game.ui_mgr.equipment_ui.session)
        self.assertEqual(game.combat.item_states, {})
