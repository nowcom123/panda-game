"""Unit tests for RPG Loot Generation (rates, tier weights, affixes, materials)."""

import random
import unittest

from rpg.items import load_catalog
from rpg.loot import (
    AFFIX_COUNTS,
    AFFIX_RANGES,
    DROP_CHANCE_NORMAL,
    MATERIAL_DEF_IDS,
    RARITY_WEIGHTS,
    TYPE_WEIGHTS,
    WEAPON_DEF_IDS,
    roll_affixes,
    roll_loot,
)


class TestRPGLootGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_roll_affixes_count_and_ranges(self):
        rng = random.Random(12345)
        # Common: 0 affixes
        self.assertEqual(len(roll_affixes(rng, "common")), 0)

        # Uncommon: 1 affix
        uncommon_affs = roll_affixes(rng, "uncommon")
        self.assertEqual(len(uncommon_affs), 1)
        aff = uncommon_affs[0]
        self.assertIn(aff.id, AFFIX_RANGES)
        low, high = AFFIX_RANGES[aff.id]
        self.assertGreaterEqual(aff.value, low)
        self.assertLessEqual(aff.value, high)
        self.assertEqual(round(aff.value, 3), aff.value)

        # Rare: 2 affixes without duplicates
        rare_affs = roll_affixes(rng, "rare")
        self.assertEqual(len(rare_affs), 2)
        aff_ids = [a.id for a in rare_affs]
        self.assertEqual(len(set(aff_ids)), 2)

        # Epic: 3 affixes without duplicates
        epic_affs = roll_affixes(rng, "epic")
        self.assertEqual(len(epic_affs), 3)
        epic_ids = [a.id for a in epic_affs]
        self.assertEqual(len(set(epic_ids)), 3)

    def test_normal_enemy_drop_chance(self):
        rng = random.Random(42)
        drops = 0
        total = 1000
        for _ in range(total):
            items = roll_loot(self.catalog, rng, enemy_tier="normal", stage=1)
            if items:
                drops += 1
                self.assertEqual(len(items), 1)

        drop_rate = drops / total
        # Should be roughly 20% (allow 16% ~ 24%)
        self.assertAlmostEqual(drop_rate, DROP_CHANCE_NORMAL, delta=0.04)

    def test_elite_enemy_guaranteed_drop(self):
        rng = random.Random(999)
        for _ in range(50):
            items = roll_loot(self.catalog, rng, enemy_tier="elite", stage=2)
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.item_level, 2)
            if item.definition_id.startswith("weapon_"):
                self.assertIn(item.rarity, ["uncommon", "rare", "epic"])
            else:
                self.assertEqual(item.rarity, "common")
            self.assertNotEqual(item.rarity, "legendary")

    def test_boss_guaranteed_drops(self):
        rng = random.Random(777)
        for _ in range(50):
            items = roll_loot(self.catalog, rng, enemy_tier="boss", stage=3)
            # Boss drops exactly 2 items: 1 weapon + 1 material bundle
            self.assertEqual(len(items), 2)
            weapon_item = items[0]
            mat_item = items[1]

            self.assertTrue(weapon_item.definition_id.startswith("weapon_"))
            self.assertIn(weapon_item.definition_id, WEAPON_DEF_IDS)
            self.assertIn(weapon_item.rarity, ["rare", "epic"])
            self.assertNotEqual(weapon_item.rarity, "legendary")
            self.assertEqual(weapon_item.quantity, 1)
            self.assertEqual(weapon_item.item_level, 3)

            self.assertIn(mat_item.definition_id, MATERIAL_DEF_IDS)
            self.assertGreaterEqual(mat_item.quantity, 3)
            self.assertLessEqual(mat_item.quantity, 6)
            self.assertEqual(mat_item.item_level, 3)

    def test_legendary_never_generated(self):
        rng = random.Random(101)
        for tier in ["normal", "elite", "boss"]:
            for _ in range(100):
                items = roll_loot(self.catalog, rng, enemy_tier=tier, stage=1)
                for it in items:
                    self.assertNotEqual(it.rarity, "legendary")

    def test_uid_uniqueness(self):
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        items1 = roll_loot(self.catalog, rng1, enemy_tier="boss", stage=1)
        items2 = roll_loot(self.catalog, rng2, enemy_tier="boss", stage=1)

        all_uids = [it.uid for it in items1] + [it.uid for it in items2]
        self.assertEqual(len(all_uids), len(set(all_uids)))

    def test_stage_level_scaling(self):
        rng = random.Random(55)
        for stage in [1, 2, 5, 10]:
            items = roll_loot(self.catalog, rng, enemy_tier="elite", stage=stage)
            self.assertEqual(items[0].item_level, stage)

        # Stage 0 or negative clamps to 1
        items = roll_loot(self.catalog, rng, enemy_tier="elite", stage=0)
        self.assertEqual(items[0].item_level, 1)


if __name__ == "__main__":
    unittest.main()

