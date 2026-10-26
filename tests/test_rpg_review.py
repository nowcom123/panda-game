import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rpg import (load_catalog, create_item, new_profile, PlayerProfile,
                 ItemInstance, SaveStore, ValidationError, UnsupportedSaveVersion)


class RPGReviewTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_uid_types_are_not_coerced(self):
        item = create_item(self.catalog, 'weapon_ar')
        for bad in (None, True, 123, [], ''):
            data = item.to_dict()
            data['uid'] = bad
            with self.subTest(uid=bad), self.assertRaises(ValidationError):
                ItemInstance.from_dict(data, self.catalog)
        with self.assertRaises(ValidationError):
            create_item(self.catalog, 'weapon_ar', uid=123)

    def test_duplicate_add_preserves_original_item(self):
        profile = new_profile()
        item = create_item(self.catalog, 'weapon_ar', uid='one')
        profile.add_item(item)
        with self.assertRaises(ValidationError):
            profile.add_item(create_item(self.catalog, 'weapon_pistol', uid='one'))
        self.assertIs(profile.items['one'], item)

    def test_equipment_keys_cannot_be_silently_dropped(self):
        for slots in ({}, {'primary': None, 'secondary': None, 'third': None}):
            data = new_profile().to_dict()
            data['equipment'] = slots
            with self.assertRaises(ValidationError):
                PlayerProfile.from_dict(data, self.catalog)

    def test_equip_material_without_explicit_catalog_is_rejected(self):
        profile = new_profile()
        item = create_item(self.catalog, 'scrap_metal')
        profile.add_item(item)
        with self.assertRaises(ValidationError):
            profile.equip('primary', item.uid)
        self.assertIsNone(profile.equipment['primary'])

    def test_catalog_bool_version_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'items.json'
            path.write_text('{"catalog_version":true,"definitions":[]}', encoding='utf8')
            with self.assertRaises(ValidationError):
                load_catalog(path)

    def test_duplicate_json_key_recovers_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SaveStore(Path(temp) / 'profile.json', self.catalog)
            profile = new_profile('one')
            store.save(profile)
            store.save(profile)
            raw = store.path.read_text(encoding='utf8').replace(
                '"items": {}', '"items": {}, "items": {}')
            store.path.write_text(raw, encoding='utf8')
            self.assertEqual(store.load().source, 'backup')
            self.assertEqual(store.path.read_text(encoding='utf8'), raw)

    def test_failed_backup_or_primary_replace_preserves_good_files(self):
        for fail_backup in (True, False):
            with self.subTest(backup=fail_backup), tempfile.TemporaryDirectory() as temp:
                store = SaveStore(Path(temp) / 'profile.json', self.catalog)
                store.save(new_profile('old'))
                store.save(new_profile('current'))
                primary = store.path.read_bytes()
                backup = store.backup_path.read_bytes()
                real_replace = os.replace
                def replace(src, dst):
                    if dst == (store.backup_path if fail_backup else store.path):
                        raise OSError('injected disk failure')
                    return real_replace(src, dst)
                with patch('rpg.save_store.os.replace', side_effect=replace):
                    with self.assertRaises(OSError):
                        store.save(new_profile('next'))
                self.assertEqual(store.path.read_bytes(), primary)
                if fail_backup:
                    self.assertEqual(store.backup_path.read_bytes(), backup)
                self.assertEqual(store.load().profile.profile_id, 'current')
                self.assertFalse(list(Path(temp).glob('*.tmp.*')))

    def test_future_backup_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SaveStore(Path(temp) / 'profile.json', self.catalog)
            data = new_profile().to_dict()
            data['schema_version'] = 999
            store.backup_path.write_text(json.dumps(data), encoding='utf8')
            with self.assertRaises(UnsupportedSaveVersion):
                store.save(new_profile())
            self.assertFalse(store.path.exists())

    def test_io_error_is_not_treated_as_corrupt_json(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SaveStore(Path(temp) / 'profile.json', self.catalog)
            store.save(new_profile())
            with patch('builtins.open', side_effect=PermissionError('access denied')):
                with self.assertRaises(PermissionError):
                    store.save(new_profile())
                with self.assertRaises(PermissionError):
                    store.load()
