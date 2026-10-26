import unittest
from unittest.mock import patch
from rpg import create_item, load_catalog, RunLootBag
from rpg.loot_world import LootWorldManager


class LootWorldReviewTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.bag = RunLootBag()
        self.world = LootWorldManager(None, None, self.catalog, self.bag)

    def test_wall_blocks_near_loot(self):
        self.world.spawn_loot((2, 0, .3), create_item(self.catalog, 'weapon_ar'))
        with patch('rpg.loot_world.get_nearby_colliders', return_value=[(.8, -1, 1.2, 1)]):
            self.assertIsNone(self.world.get_nearest_loot(0, 0, 0, {})[0])
        with patch('rpg.loot_world.get_nearby_colliders', return_value=[]):
            self.assertIsNotNone(self.world.get_nearest_loot(0, 0, 0, {})[0])

    def test_foreign_world_item_cannot_be_collected(self):
        other = LootWorldManager(None, None, self.catalog, self.bag)
        item = other.spawn_loot((0, 0, .3), create_item(self.catalog, 'weapon_ar'))
        self.assertFalse(self.world.try_pickup(item)[0])
        self.assertEqual(self.bag.count, 0)
        self.assertFalse(item.is_collected)
