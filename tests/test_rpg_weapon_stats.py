import copy
import unittest

from combat.weapon_config import WEAPON_CONFIGS
from rpg import create_item, load_catalog, ValidationError
from rpg.weapon_stats import resolve_weapon_config


class WeaponStatsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_affixes_resolve_once_without_mutating_base(self):
        original = copy.deepcopy(WEAPON_CONFIGS)
        item = create_item(self.catalog, 'weapon_pistol', affixes=[
            ('damage_mult', 1.2), ('reload_time_mult', .8), ('weakpoint_mult', 1.25)])
        first = resolve_weapon_config(WEAPON_CONFIGS, self.catalog, item)
        self.assertEqual(first['damage'], original['PISTOL']['damage'] * 1.2)
        self.assertEqual(first['reload_time'], original['PISTOL']['reload_time'] * .8)
        self.assertEqual(first['headshot_mult'], original['PISTOL']['headshot_mult'] * 1.25)
        self.assertEqual(first, resolve_weapon_config(WEAPON_CONFIGS, self.catalog, item))
        first['damage'] = 0
        self.assertEqual(WEAPON_CONFIGS, original)

    def test_same_type_items_have_independent_options(self):
        plain = create_item(self.catalog, 'weapon_ar', rarity='legendary', item_level=99)
        rolled = create_item(self.catalog, 'weapon_ar', affixes=[('damage_mult', 1.5)])
        a = resolve_weapon_config(WEAPON_CONFIGS, self.catalog, plain)
        b = resolve_weapon_config(WEAPON_CONFIGS, self.catalog, rolled)
        self.assertEqual(a, WEAPON_CONFIGS['AR'])
        self.assertEqual(b['damage'], a['damage'] * 1.5)

    def test_material_cannot_resolve_to_weapon(self):
        with self.assertRaises(ValidationError):
            resolve_weapon_config(WEAPON_CONFIGS, self.catalog,
                                  create_item(self.catalog, 'scrap_metal'))
