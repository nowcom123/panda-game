"""Tests for RPGSession, equipment operations, and data integrity."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpg import (
    ItemNotFoundError,
    PlayerProfile,
    RPGSession,
    SaveStore,
    ValidationError,
    create_item,
    load_catalog,
    new_profile,
)
from rpg.session import STARTER_UNLOCK_KEY


class TestRPGEquipment(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_starter_loadout_grant_and_no_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)

            # First session: new profile should get 4 starter weapons and equip PISTOL/SHOTGUN
            session1 = RPGSession(store, self.catalog)
            success = session1.initialize()
            self.assertTrue(success)
            self.assertTrue(session1.is_valid)

            prof1 = session1.profile
            self.assertIsNotNone(prof1)
            self.assertEqual(len(prof1.items), 4)
            self.assertIn(STARTER_UNLOCK_KEY, prof1.unlocks)
            self.assertIsNotNone(prof1.equipment["primary"])
            self.assertIsNotNone(prof1.equipment["secondary"])

            p_item = prof1.items[prof1.equipment["primary"]]
            s_item = prof1.items[prof1.equipment["secondary"]]
            self.assertEqual(self.catalog[p_item.definition_id].weapon_key, "PISTOL")
            self.assertEqual(self.catalog[s_item.definition_id].weapon_key, "SHOTGUN")

            # Second session: restart should load existing without duplicate grant
            session2 = RPGSession(store, self.catalog)
            session2.initialize()
            prof2 = session2.profile
            self.assertEqual(len(prof2.items), 4)
            self.assertEqual(prof2.equipment["primary"], prof1.equipment["primary"])
            self.assertEqual(prof2.equipment["secondary"], prof1.equipment["secondary"])

    def test_equip_unequip_locking_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            prof = session.profile
            # Find the AR in starter inventory
            ar_uid = None
            for uid, item in prof.items.items():
                if self.catalog[item.definition_id].weapon_key == "AR":
                    ar_uid = uid
                    break
            self.assertIsNotNone(ar_uid)

            # Equip AR into primary slot
            success, msg = session.equip("primary", ar_uid)
            self.assertTrue(success)
            self.assertEqual(session.profile.equipment["primary"], ar_uid)

            # Lock the AR
            success_lock, msg_lock = session.set_locked(ar_uid, True)
            self.assertTrue(success_lock)
            self.assertTrue(session.profile.items[ar_uid].locked)

            # Unequip secondary slot (leaving primary equipped)
            success_un, msg_un = session.unequip("secondary")
            self.assertTrue(success_un)
            self.assertIsNone(session.profile.equipment["secondary"])

            # Reload fresh from disk and verify persistence
            reloaded_session = RPGSession(store, self.catalog)
            reloaded_session.initialize()
            r_prof = reloaded_session.profile
            self.assertEqual(r_prof.equipment["primary"], ar_uid)
            self.assertIsNone(r_prof.equipment["secondary"])
            self.assertTrue(r_prof.items[ar_uid].locked)

    def test_last_weapon_unequip_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            # Unequip secondary first
            session.unequip("secondary")
            self.assertIsNone(session.profile.equipment["secondary"])

            # Now attempting to unequip primary should be rejected
            success, msg = session.unequip("primary")
            self.assertFalse(success)
            self.assertIn("최소 1개", msg)
            self.assertIsNotNone(session.profile.equipment["primary"])

    def test_material_equip_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            # Add scrap metal
            scrap = create_item(self.catalog, "scrap_metal", quantity=10, uid="scrap-01")
            session.profile.add_item(scrap)
            session.store.save(session.profile)

            success, msg = session.equip("primary", "scrap-01")
            self.assertFalse(success)
            self.assertIn("재료", msg)
            self.assertNotEqual(session.profile.equipment["primary"], "scrap-01")

    def test_same_uid_both_slots_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            p_uid = session.profile.equipment["primary"]
            # Attempt to equip the same UID into secondary
            success, msg = session.equip("secondary", p_uid)
            self.assertFalse(success)
            self.assertIn("이미 다른 슬롯", msg)

    def test_corrupted_or_unsupported_save_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            # Write invalid raw bytes
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("CORRUPTED_JSON_DATA{{{")

            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            success = session.initialize()

            self.assertFalse(success)
            self.assertFalse(session.is_valid)
            self.assertIsNotNone(session.load_error)

            # Ensure file on disk was preserved and not overwritten with empty profile
            with open(save_path, "r", encoding="utf-8") as f:
                data = f.read()
            self.assertEqual(data, "CORRUPTED_JSON_DATA{{{")

    def test_save_failure_keeps_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            initial_primary = session.profile.equipment["primary"]

            # Mock store.save to raise OSError
            with patch.object(store, "save", side_effect=OSError("Disk Full")):
                success, msg = session.unequip("secondary")
                self.assertFalse(success)
                self.assertIn("저장 실패", msg)

            # In-memory profile must maintain existing state
            self.assertIsNotNone(session.profile.equipment["secondary"])
            self.assertEqual(session.profile.equipment["primary"], initial_primary)


if __name__ == "__main__":
    unittest.main()

