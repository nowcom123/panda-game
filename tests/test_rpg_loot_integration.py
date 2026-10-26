"""Integration tests for in-run loot bag, world manager, and extraction transactions."""

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from rpg.items import create_item, load_catalog
from rpg.loot_world import LootWorldItem, LootWorldManager
from rpg.profile import new_profile
from rpg.run_loot import MAX_RUN_LOOT_CAPACITY, RunLootBag
from rpg.save_store import SaveStore
from rpg.session import RPGSession


class TestRPGLootIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.save_path = Path(self.tmp_dir.name) / "test_profile.json"
        self.catalog = load_catalog()
        self.store = SaveStore(self.save_path, self.catalog)
        self.session = RPGSession(self.store, self.catalog)
        self.session.initialize(grant_starters=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_run_loot_bag_capacity_limit(self):
        bag = RunLootBag()
        self.assertEqual(bag.capacity, 24)
        self.assertEqual(bag.count, 0)
        self.assertTrue(bag.can_add())

        # Fill bag up to 24 items
        for i in range(24):
            item = create_item(self.catalog, "scrap_metal", quantity=1)
            success, msg = bag.add_item(item, session=self.session)
            self.assertTrue(success, f"Failed at item {i}: {msg}")

        self.assertEqual(bag.count, 24)
        self.assertFalse(bag.can_add())

        # 25th item must fail
        extra_item = create_item(self.catalog, "bone_fragment", quantity=1)
        success, msg = bag.add_item(extra_item, session=self.session)
        self.assertFalse(success)
        self.assertIn("가득", msg)
        self.assertEqual(bag.count, 24)

    def test_duplicate_uid_rejection(self):
        bag = RunLootBag()
        item = create_item(self.catalog, "weapon_ar", rarity="rare")
        ok, _ = bag.add_item(item, session=self.session)
        self.assertTrue(ok)

        # Adding same item instance / UID again must be rejected
        ok, msg = bag.add_item(item, session=self.session)
        self.assertFalse(ok)
        self.assertIn("이미", msg)

        # Adding an item that exists in permanent profile must be rejected
        owned_uid = list(self.session.profile.items.keys())[0]
        owned_item = self.session.profile.items[owned_uid]
        ok, msg = bag.add_item(owned_item, session=self.session)
        self.assertFalse(ok)
        self.assertIn("영구 소유", msg)

    def test_successful_extraction_transaction(self):
        bag = RunLootBag()
        w1 = create_item(self.catalog, "weapon_shotgun", rarity="rare", item_level=2)
        m1 = create_item(self.catalog, "scrap_metal", quantity=5, item_level=2)
        bag.add_item(w1, session=self.session)
        bag.add_item(m1, session=self.session)
        self.assertEqual(bag.count, 2)

        initial_profile_items = len(self.session.profile.items)

        # Execute extraction
        ok, msg = bag.extract(self.session)
        self.assertTrue(ok)
        self.assertTrue(bag.is_extracted)
        self.assertEqual(bag.count, 0)  # Pending cleared on success

        # Permanent profile updated
        self.assertIn(w1.uid, self.session.profile.items)
        self.assertIn(m1.uid, self.session.profile.items)
        self.assertEqual(len(self.session.profile.items), initial_profile_items + 2)

        # Verify disk persistence by loading fresh
        fresh_load = self.store.load().profile
        self.assertIn(w1.uid, fresh_load.items)
        self.assertIn(m1.uid, fresh_load.items)

        # Subsequent extract call must be harmless
        ok2, msg2 = bag.extract(self.session)
        self.assertTrue(ok2)
        self.assertIn("이미", msg2)
        # Should not re-add items
        self.assertEqual(len(self.session.profile.items), initial_profile_items + 2)

    def test_save_failure_preserves_pending_items_for_retry(self):
        bag = RunLootBag()
        w1 = create_item(self.catalog, "weapon_ar", rarity="epic")
        bag.add_item(w1, session=self.session)

        # Mock store.save to simulate disk write failure
        orig_save = self.session.store.save
        self.session.store.save = MagicMock(side_effect=OSError("Disk full simulation"))

        ok, msg = bag.extract(self.session)
        self.assertFalse(ok)
        self.assertIn("실패", msg)
        self.assertFalse(bag.is_extracted)
        # Pending items MUST be preserved for retry!
        self.assertEqual(bag.count, 1)
        self.assertNotIn(w1.uid, self.session.profile.items)

        # Now fix save and retry
        self.session.store.save = orig_save
        ok_retry, msg_retry = bag.extract(self.session)
        self.assertTrue(ok_retry)
        self.assertTrue(bag.is_extracted)
        self.assertEqual(bag.count, 0)
        self.assertIn(w1.uid, self.session.profile.items)

    def test_clear_on_death_discards_pending_only(self):
        bag = RunLootBag()
        item = create_item(self.catalog, "weapon_pistol", rarity="uncommon")
        bag.add_item(item, session=self.session)
        self.assertEqual(bag.count, 1)

        perm_items_before = copy.deepcopy(self.session.profile.items)

        # Player dies
        bag.clear_on_death()
        self.assertEqual(bag.count, 0)

        # Permanent items MUST remain untouched
        self.assertEqual(self.session.profile.items, perm_items_before)

    def test_abandon_run_disallows_extraction(self):
        bag = RunLootBag()
        item = create_item(self.catalog, "scrap_metal", quantity=3)
        bag.add_item(item, session=self.session)

        bag.abandon()
        self.assertTrue(bag.is_abandoned)

        ok, msg = bag.extract(self.session)
        self.assertFalse(ok)
        self.assertIn("포기", msg)

    def test_loot_world_manager_ground_cap_and_pickup(self):
        bag = RunLootBag()
        mgr = LootWorldManager(
            render=None,
            world_root=None,
            catalog=self.catalog,
            run_loot_bag=bag,
        )

        # Spawn 45 items; manager has cap of 40
        for i in range(45):
            it = create_item(self.catalog, "scrap_metal", quantity=1)
            mgr.spawn_loot((float(i), 0.0, 0.2), it)

        # Total active world items should never exceed 40
        self.assertEqual(len(mgr.world_items), 40)
        # The first 5 items (i=0..4) should have been pruned
        self.assertEqual(mgr.world_items[0].base_x, 5.0)

        # Pickup test: player near x=5.0
        nearest, dist = mgr.get_nearest_loot(px=5.2, py=0.0, pz=0.2)
        self.assertIsNotNone(nearest)
        self.assertAlmostEqual(dist, 0.2, places=2)

        # Pickup succeeds and places into bag
        ok, msg = mgr.try_pickup(nearest, session=self.session)
        self.assertTrue(ok)
        self.assertEqual(len(mgr.world_items), 39)
        self.assertEqual(bag.count, 1)

        # Fill bag to 24
        for _ in range(23):
            bag.add_item(create_item(self.catalog, "scrap_metal", quantity=1), session=self.session)
        self.assertEqual(bag.count, 24)

        # Attempt pickup with full bag
        nearest_next, _ = mgr.get_nearest_loot(px=6.0, py=0.0, pz=0.2)
        self.assertIsNotNone(nearest_next)
        ok_full, msg_full = mgr.try_pickup(nearest_next, session=self.session)
        self.assertFalse(ok_full)
        self.assertIn("가득", msg_full)
        # Item MUST remain in world!
        self.assertEqual(len(mgr.world_items), 39)
        self.assertIn(nearest_next, mgr.world_items)


if __name__ == "__main__":
    unittest.main()

