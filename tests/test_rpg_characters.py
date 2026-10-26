import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from rpg.characters import (
    CharacterList,
    CharacterManager,
    CharacterSummary,
    validate_character_name,
)
from rpg.items import (
    RPGError,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    create_item,
    load_catalog,
)
from rpg.profile import new_profile
from rpg.save_store import SaveStore
from rpg.session import RPGSession


class RPGCharactersTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.catalog = load_catalog()
        self.manager = CharacterManager(self.root_path, self.catalog)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_name_validation(self):
        # Valid names (2 to 12 chars, korean, english, numbers)
        self.assertEqual(validate_character_name("  탐험가  "), "탐험가")
        self.assertEqual(validate_character_name("Hero123"), "Hero123")
        self.assertEqual(validate_character_name("십이글자길이의이름이야"), "십이글자길이의이름이야")

        # Invalid lengths
        with self.assertRaises(ValidationError):
            validate_character_name("a")
        with self.assertRaises(ValidationError):
            validate_character_name("   ")
        with self.assertRaises(ValidationError):
            validate_character_name("열세글자가넘어가는너무긴이름입니다")

        # Control characters rejected
        with self.assertRaises(ValidationError):
            validate_character_name("Hero\x00Name")
        with self.assertRaises(ValidationError):
            validate_character_name("탐험\n가")

    def test_character_creation_and_max_limit(self):
        char_list = self.manager.load_character_list()
        self.assertEqual(len(char_list.characters), 0)

        # Create 3 characters
        c1 = self.manager.create_character("알파")
        c2 = self.manager.create_character("베타")
        c3 = self.manager.create_character("감마")

        self.assertEqual(len(self.manager.character_list.characters), 3)
        self.assertEqual(self.manager.character_list.active_character_id, c3.id)

        # 4th character creation must fail
        with self.assertRaises(RPGError):
            self.manager.create_character("델타")

    def test_two_characters_storage_and_currency_isolation(self):
        c1 = self.manager.create_character("탐험가A")
        c2 = self.manager.create_character("탐험가B")

        store1 = self.manager.get_character_save_store(c1.id)
        store2 = self.manager.get_character_save_store(c2.id)

        sess1 = RPGSession(store1, self.catalog)
        sess1.initialize(grant_starters=True)
        sess1.profile.currencies["credits"] = 500
        extra_item = create_item(self.catalog, "weapon_ar", rarity="rare", item_level=5)
        sess1.profile.add_item(extra_item)
        store1.save(sess1.profile)

        sess2 = RPGSession(store2, self.catalog)
        sess2.initialize(grant_starters=True)
        sess2.profile.currencies["credits"] = 50
        store2.save(sess2.profile)

        # Reload both and verify isolation
        reloaded_prof1 = store1.load().profile
        reloaded_prof2 = store2.load().profile

        self.assertEqual(reloaded_prof1.currencies["credits"], 500)
        self.assertEqual(reloaded_prof2.currencies["credits"], 50)
        self.assertIn(extra_item.uid, reloaded_prof1.items)
        self.assertNotIn(extra_item.uid, reloaded_prof2.items)

    def test_selection_restores_on_reload(self):
        c1 = self.manager.create_character("캐릭터1")
        c2 = self.manager.create_character("캐릭터2")

        self.manager.select_character(c1.id)
        self.assertEqual(self.manager.character_list.active_character_id, c1.id)

        # Create new manager instance on same directory
        new_mgr = CharacterManager(self.root_path, self.catalog)
        loaded = new_mgr.load_character_list()
        self.assertEqual(loaded.active_character_id, c1.id)
        self.assertEqual(len(loaded.characters), 2)

    def test_legacy_profile_migration_preserves_bytes_and_is_idempotent(self):
        # Create legacy profile.json and .bak
        legacy_path = self.root_path / "profile.json"
        legacy_bak_path = self.root_path / "profile.json.bak"
        legacy_store = SaveStore(legacy_path, self.catalog)

        legacy_prof = new_profile()
        legacy_prof.currencies["credits"] = 777
        legacy_item = create_item(self.catalog, "weapon_pistol", rarity="epic", item_level=3)
        legacy_prof.add_item(legacy_item)
        legacy_prof.equip("primary", legacy_item.uid, self.catalog)
        legacy_store.save(legacy_prof)

        # Ensure .bak exists by saving a second time
        legacy_prof.currencies["credits"] = 888
        legacy_store.save(legacy_prof)

        primary_bytes_before = legacy_path.read_bytes()
        bak_bytes_before = legacy_bak_path.read_bytes()

        # Run migration via load_character_list()
        char_list = self.manager.load_character_list()
        self.assertEqual(len(char_list.characters), 1)
        migrated_char = char_list.characters[0]
        self.assertEqual(migrated_char.name, "기존 탐험가")
        self.assertEqual(char_list.active_character_id, migrated_char.id)

        # Check byte-for-byte preservation of original files!
        self.assertEqual(legacy_path.read_bytes(), primary_bytes_before)
        self.assertEqual(legacy_bak_path.read_bytes(), bak_bytes_before)

        # Verify migrated character data
        migrated_store = self.manager.get_character_save_store(migrated_char.id)
        migrated_prof = migrated_store.load().profile
        self.assertEqual(migrated_prof.currencies["credits"], 888)
        self.assertIn(legacy_item.uid, migrated_prof.items)
        self.assertEqual(migrated_prof.equipment["primary"], legacy_item.uid)

        # Second migration attempt should be idempotent and not duplicate
        re_mgr = CharacterManager(self.root_path, self.catalog)
        re_list = re_mgr.load_character_list()
        self.assertEqual(len(re_list.characters), 1)
        self.assertEqual(re_list.characters[0].id, migrated_char.id)

    def test_unsupported_version_blocks_and_preserves_file(self):
        list_file = self.root_path / "characters.json"
        future_data = {
            "version": 999,
            "active_character_id": None,
            "characters": []
        }
        list_file.write_text(json.dumps(future_data), encoding="utf-8")

        with self.assertRaises(UnsupportedSaveVersion):
            self.manager.load_character_list()

        # File must not be overwritten or cleared
        self.assertEqual(json.loads(list_file.read_text(encoding="utf-8"))["version"], 999)

    def test_corrupted_primary_recovers_from_backup(self):
        c1 = self.manager.create_character("백업테스트")
        self.manager.save_character_list()
        self.assertTrue((self.root_path / "characters.json").exists())

        # Modify to create a backup
        c2 = self.manager.create_character("두번째")
        self.assertTrue((self.root_path / "characters.json.bak").exists())

        # Corrupt primary
        (self.root_path / "characters.json").write_text("{ corrupt json ...", encoding="utf-8")

        # Load should recover from backup
        recovered = self.manager.load_character_list()
        self.assertEqual(len(recovered.characters), 1)
        self.assertEqual(recovered.characters[0].name, "백업테스트")

    def test_path_traversal_prevention(self):
        # Attempt path traversal via char_id
        with self.assertRaises(ValidationError):
            self.manager.get_character_save_store("../../evil_dir")
        with self.assertRaises(ValidationError):
            self.manager.get_character_save_store("not-a-uuid")


if __name__ == '__main__':
    unittest.main()
