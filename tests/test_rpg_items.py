"""Tests for RPG item catalog and item instance handling."""

import os
import tempfile
import unittest

from combat.weapon_config import WEAPON_CONFIGS
from rpg.items import (
    ItemAffix,
    ItemDefinition,
    ItemInstance,
    ItemNotFoundError,
    ValidationError,
    create_item,
    load_catalog,
)


class TestRPGItems(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_load_catalog_default(self) -> None:
        self.assertGreaterEqual(len(self.catalog), 6)
        self.assertIn("weapon_pistol", self.catalog)
        self.assertIn("scrap_metal", self.catalog)

    def test_catalog_cwd_independence(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                os.chdir(tmp_dir)
                catalog_from_other_dir = load_catalog()
                self.assertIn("weapon_pistol", catalog_from_other_dir)
            finally:
                os.chdir(original_cwd)

    def test_catalog_weapon_keys_match_runtime_configs(self) -> None:
        catalog_weapon_keys = {
            defn.weapon_key
            for defn in self.catalog.values()
            if defn.kind == "weapon"
        }
        runtime_weapon_keys = set(WEAPON_CONFIGS.keys())
        self.assertEqual(catalog_weapon_keys, runtime_weapon_keys)

        # Ensure runtime battle stats (damage, cooldown, etc.) are NOT duplicated in catalog definitions
        for defn in self.catalog.values():
            self.assertFalse(hasattr(defn, "damage"))
            self.assertFalse(hasattr(defn, "cooldown"))
            self.assertFalse(hasattr(defn, "max_ammo"))

    def test_create_item_unique_uids(self) -> None:
        item1 = create_item(self.catalog, "weapon_pistol")
        item2 = create_item(self.catalog, "weapon_pistol")
        self.assertNotEqual(item1.uid, item2.uid)
        self.assertTrue(len(item1.uid) > 0)

    def test_create_item_explicit_uid(self) -> None:
        custom_uid = "pistol-special-001"
        item = create_item(self.catalog, "weapon_pistol", uid=custom_uid)
        self.assertEqual(item.uid, custom_uid)

    def test_instances_affixes_are_independent(self) -> None:
        item1 = create_item(
            self.catalog,
            "weapon_pistol",
            affixes=[{"id": "damage_mult", "value": 1.2}],
        )
        item2 = create_item(
            self.catalog,
            "weapon_pistol",
            affixes=[{"id": "reload_time_mult", "value": 0.8}],
        )
        self.assertNotEqual(item1.affixes, item2.affixes)
        self.assertEqual(item1.affixes[0].id, "damage_mult")
        self.assertEqual(item2.affixes[0].id, "reload_time_mult")

    def test_valid_affixes(self) -> None:
        affixes = [
            ("damage_mult", 1.25),
            ("reload_time_mult", 0.85),
            ("weakpoint_mult", 1.5),
        ]
        item = create_item(self.catalog, "weapon_ar", affixes=affixes)
        self.assertEqual(len(item.affixes), 3)

    def test_invalid_affix_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("unknown_affix", 1.5)])

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("damage_mult", 0.0)])

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("damage_mult", -0.5)])

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("damage_mult", float("nan"))])

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("damage_mult", float("inf"))])

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", affixes=[("damage_mult", True)])

    def test_duplicate_affix_id_rejected(self) -> None:
        duplicate_affixes = [
            ("damage_mult", 1.1),
            ("damage_mult", 1.2),
        ]
        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_shotgun", affixes=duplicate_affixes)

    def test_material_cannot_have_affixes(self) -> None:
        with self.assertRaises(ValidationError):
            create_item(
                self.catalog,
                "scrap_metal",
                quantity=5,
                affixes=[("damage_mult", 1.1)],
            )

    def test_weapon_quantity_must_be_one(self) -> None:
        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", quantity=2)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", quantity=0)

    def test_material_quantity_limits(self) -> None:
        mat = create_item(self.catalog, "scrap_metal", quantity=50)
        self.assertEqual(mat.quantity, 50)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "scrap_metal", quantity=0)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "scrap_metal", quantity=-5)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "scrap_metal", quantity=1000)  # max_stack is 999

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "scrap_metal", quantity=True)

    def test_item_level_validation(self) -> None:
        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", item_level=0)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", item_level=-1)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", item_level=True)

    def test_rarity_validation(self) -> None:
        item = create_item(self.catalog, "weapon_ar", rarity="legendary")
        self.assertEqual(item.rarity, "legendary")

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_ar", rarity="mythic")

    def test_locked_flag(self) -> None:
        item = create_item(self.catalog, "weapon_dual_pistol", locked=True)
        self.assertTrue(item.locked)

        with self.assertRaises(ValidationError):
            create_item(self.catalog, "weapon_dual_pistol", locked="true")  # type: ignore

    def test_roundtrip_serialization(self) -> None:
        item = create_item(
            self.catalog,
            "weapon_ar",
            rarity="rare",
            item_level=15,
            affixes=[("damage_mult", 1.15), ("reload_time_mult", 0.9)],
            locked=True,
            uid="roundtrip-test-uid-123",
        )
        serialized = item.to_dict()
        restored = ItemInstance.from_dict(serialized, self.catalog)

        self.assertEqual(item.uid, restored.uid)
        self.assertEqual(item.definition_id, restored.definition_id)
        self.assertEqual(item.rarity, restored.rarity)
        self.assertEqual(item.item_level, restored.item_level)
        self.assertEqual(item.quantity, restored.quantity)
        self.assertEqual(len(item.affixes), len(restored.affixes))
        self.assertEqual(item.affixes[0], restored.affixes[0])
        self.assertEqual(item.affixes[1], restored.affixes[1])
        self.assertEqual(item.locked, restored.locked)

    def test_unknown_definition_in_from_dict(self) -> None:
        data = {
            "uid": "test-uid",
            "definition_id": "non_existent_item",
            "rarity": "common",
            "item_level": 1,
            "quantity": 1,
            "affixes": [],
            "locked": False,
        }
        with self.assertRaises(ItemNotFoundError):
            ItemInstance.from_dict(data, self.catalog)


if __name__ == "__main__":
    unittest.main()

