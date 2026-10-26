"""Tests for RPG PlayerProfile and atomic SaveStore operations."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpg.items import (
    ItemNotFoundError,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    create_item,
    load_catalog,
)
from rpg.profile import PlayerProfile, new_profile
from rpg.save_store import SaveStore, get_default_save_path


class TestRPGSave(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_new_profile_defaults(self) -> None:
        profile = new_profile()
        self.assertEqual(profile.schema_version, 1)
        self.assertTrue(len(profile.profile_id) > 0)
        self.assertEqual(profile.items, {})
        self.assertEqual(profile.equipment, {"primary": None, "secondary": None})
        self.assertEqual(profile.currencies, {"credits": 0})
        self.assertEqual(profile.unlocks, [])

    def test_profile_isolation(self) -> None:
        profile = new_profile(profile_id="p1")
        weapon = create_item(self.catalog, "weapon_pistol", uid="w1")
        profile.add_item(weapon)
        profile.currencies["credits"] = 500
        profile.unlocks.append("badge_alpha")

        serialized = profile.to_dict()
        serialized["currencies"]["credits"] = 9999
        serialized["unlocks"].append("badge_beta")

        # Ensure original profile was not affected by mutation of serialized dict
        self.assertEqual(profile.currencies["credits"], 500)
        self.assertEqual(profile.unlocks, ["badge_alpha"])

    def test_equipment_rules(self) -> None:
        profile = new_profile(profile_id="p1")
        w1 = create_item(self.catalog, "weapon_pistol", uid="w1")
        w2 = create_item(self.catalog, "weapon_ar", uid="w2")
        mat = create_item(self.catalog, "scrap_metal", uid="m1", quantity=10)

        profile.add_item(w1)
        profile.add_item(w2)
        profile.add_item(mat)

        # Valid equipping
        profile.equip("primary", w1.uid, self.catalog)
        profile.equip("secondary", w2.uid, self.catalog)
        profile.validate(self.catalog)
        self.assertEqual(profile.equipment["primary"], "w1")
        self.assertEqual(profile.equipment["secondary"], "w2")

        # Cannot equip unowned UID
        with self.assertRaises(ValidationError):
            profile.equip("primary", "unowned-uid", self.catalog)

        # Cannot equip material
        with self.assertRaises(ValidationError):
            profile.equip("primary", mat.uid, self.catalog)

        # Cannot equip same UID in both slots
        with self.assertRaises(ValidationError):
            profile.equip("primary", w2.uid, self.catalog)  # w2 is already in secondary

        # Direct dictionary tampering validation
        tampered_profile = new_profile()
        tampered_profile.add_item(w1)
        tampered_profile.equipment["primary"] = w1.uid
        tampered_profile.equipment["secondary"] = w1.uid  # same uid in both
        with self.assertRaises(ValidationError):
            tampered_profile.validate(self.catalog)

    def test_currency_validation(self) -> None:
        profile = new_profile()
        profile.currencies["credits"] = -10
        with self.assertRaises(ValidationError):
            profile.validate(self.catalog)

        profile.currencies["credits"] = True  # type: ignore
        with self.assertRaises(ValidationError):
            profile.validate(self.catalog)

    def test_unlocks_validation(self) -> None:
        profile = new_profile()
        profile.unlocks = ["zone1", "zone1"]  # duplicate
        with self.assertRaises(ValidationError):
            profile.validate(self.catalog)

        profile.unlocks = [""]  # empty string
        with self.assertRaises(ValidationError):
            profile.validate(self.catalog)

    def test_item_uid_key_mismatch_rejected(self) -> None:
        profile = new_profile()
        w1 = create_item(self.catalog, "weapon_pistol", uid="real-uid")
        profile.items["different-key"] = w1
        with self.assertRaises(ValidationError):
            profile.validate(self.catalog)

    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            profile = new_profile(profile_id="roundtrip-p1")
            w1 = create_item(
                self.catalog,
                "weapon_ar",
                uid="ar-01",
                rarity="rare",
                item_level=5,
                affixes=[("damage_mult", 1.1)],
                locked=True,
            )
            mat = create_item(
                self.catalog,
                "bone_fragment",
                uid="bone-01",
                quantity=42,
            )
            profile.add_item(w1)
            profile.add_item(mat)
            profile.equip("primary", w1.uid, self.catalog)
            profile.currencies["credits"] = 2500
            profile.unlocks.append("achieve_survivor")

            store.save(profile)
            self.assertTrue(save_path.is_file())

            load_res = store.load()
            self.assertEqual(load_res.source, "primary")
            self.assertEqual(load_res.warnings, [])

            loaded = load_res.profile
            self.assertEqual(loaded.profile_id, "roundtrip-p1")
            self.assertEqual(loaded.schema_version, 1)
            self.assertEqual(loaded.currencies["credits"], 2500)
            self.assertEqual(loaded.unlocks, ["achieve_survivor"])
            self.assertEqual(loaded.equipment["primary"], "ar-01")
            self.assertIsNone(loaded.equipment["secondary"])
            self.assertIn("ar-01", loaded.items)
            self.assertIn("bone-01", loaded.items)

            loaded_w1 = loaded.items["ar-01"]
            self.assertEqual(loaded_w1.rarity, "rare")
            self.assertEqual(loaded_w1.item_level, 5)
            self.assertTrue(loaded_w1.locked)
            self.assertEqual(len(loaded_w1.affixes), 1)
            self.assertEqual(loaded_w1.affixes[0].id, "damage_mult")
            self.assertEqual(loaded_w1.affixes[0].value, 1.1)

            loaded_mat = loaded.items["bone-01"]
            self.assertEqual(loaded_mat.quantity, 42)

    def test_load_non_existent_file_returns_new_without_writing_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            res = store.load()
            self.assertEqual(res.source, "new")
            self.assertEqual(res.warnings, [])
            self.assertFalse(save_path.exists())
            self.assertFalse(store.backup_path.exists())
            self.assertEqual(res.profile.items, {})

    def test_atomic_save_replace_failure_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            profile1 = new_profile(profile_id="first")
            store.save(profile1)
            self.assertTrue(save_path.exists())

            # Attempt a second save where os.replace fails
            profile2 = new_profile(profile_id="second")
            with patch("os.replace", side_effect=OSError("Disk full or permission denied")):
                with self.assertRaises(OSError):
                    store.save(profile2)

            # The original save must still be intact and loadable
            load_res = store.load()
            self.assertEqual(load_res.source, "primary")
            self.assertEqual(load_res.profile.profile_id, "first")

    def test_primary_corrupted_recovered_from_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            # First save
            p1 = new_profile(profile_id="good-profile-v1")
            store.save(p1)

            # Second save (rotates p1 into .bak)
            p2 = new_profile(profile_id="good-profile-v2")
            store.save(p2)
            self.assertTrue(store.backup_path.exists())

            # Corrupt the primary save file
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("CORRUPTED_JSON_DATA{{{")

            load_res = store.load()
            self.assertEqual(load_res.source, "backup")
            self.assertEqual(load_res.profile.profile_id, "good-profile-v1")
            self.assertGreater(len(load_res.warnings), 0)

            # Ensure load did not alter the corrupted primary file on disk
            with open(save_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "CORRUPTED_JSON_DATA{{{")

    def test_both_corrupted_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            # Save once, then corrupt primary and backup
            p = new_profile()
            store.save(p)
            store.save(p)  # Creates backup

            with open(save_path, "w", encoding="utf-8") as f:
                f.write("BAD_PRIMARY")
            with open(store.backup_path, "w", encoding="utf-8") as f:
                f.write("BAD_BACKUP")

            with self.assertRaises(SaveCorruptedError):
                store.load()

    def test_corrupt_primary_does_not_overwrite_good_backup_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            # Create good save 1 and 2
            p1 = new_profile(profile_id="profile-valid-1")
            store.save(p1)
            p2 = new_profile(profile_id="profile-valid-2")
            store.save(p2)

            # Backup now contains p1. Now corrupt primary file
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("CORRUPT_JSON")

            # Saving p3 should NOT rotate the corrupted primary into backup!
            p3 = new_profile(profile_id="profile-valid-3")
            store.save(p3)

            # Primary should now be p3
            res_primary = store.load()
            self.assertEqual(res_primary.source, "primary")
            self.assertEqual(res_primary.profile.profile_id, "profile-valid-3")

            # Backup should still be p1 (not the corrupted file)
            with open(store.backup_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            self.assertEqual(backup_data["profile_id"], "profile-valid-1")

    def test_unsupported_save_version_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            # Create a save with schema_version = 999
            future_save = {
                "schema_version": 999,
                "profile_id": "future-profile",
                "items": {},
                "equipment": {"primary": None, "secondary": None},
                "currencies": {"credits": 0},
                "unlocks": [],
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(future_save, f)

            # Also create a valid .bak
            p_backup = new_profile(profile_id="valid-backup")
            with open(store.backup_path, "w", encoding="utf-8") as f:
                json.dump(p_backup.to_dict(), f)

            # Must raise UnsupportedSaveVersion and NOT fall back to backup
            with self.assertRaises(UnsupportedSaveVersion):
                store.load()

    def test_unsupported_save_version_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            future_save = {
                "schema_version": 999,
                "profile_id": "future-profile",
                "items": {},
                "equipment": {"primary": None, "secondary": None},
                "currencies": {"credits": 0},
                "unlocks": [],
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(future_save, f)

            p_new = new_profile(profile_id="new-attempt")
            with self.assertRaises(UnsupportedSaveVersion):
                store.save(p_new)

    def test_get_default_save_path(self) -> None:
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:\\MockAppData"}, clear=False):
            p = get_default_save_path()
            self.assertEqual(str(p), "C:\\MockAppData\\LiminalBackrooms\\profile.json")

        env_without_localappdata = dict(os.environ)
        env_without_localappdata.pop("LOCALAPPDATA", None)
        with patch.dict(os.environ, env_without_localappdata, clear=True):
            p = get_default_save_path()
            expected = Path.home() / ".liminal_backrooms" / "profile.json"
            self.assertEqual(p, expected)

    def test_unknown_item_definition_in_save_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            invalid_data = {
                "schema_version": 1,
                "profile_id": "test-p",
                "items": {
                    "item1": {
                        "uid": "item1",
                        "definition_id": "deleted_legacy_weapon",
                        "rarity": "common",
                        "item_level": 1,
                        "quantity": 1,
                        "affixes": [],
                        "locked": False,
                    }
                },
                "equipment": {"primary": None, "secondary": None},
                "currencies": {"credits": 0},
                "unlocks": [],
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(invalid_data, f)

            with self.assertRaises(SaveCorruptedError) as ctx:
                store.load()
            self.assertIn("deleted_legacy_weapon", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
