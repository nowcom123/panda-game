import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from rpg.items import create_item, load_catalog, ValidationError
from rpg.save_store import SaveStore
from rpg.session import RPGSession
from rpg.workshop import material_count, RECIPES


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = load_catalog()
        self.store = SaveStore(Path(self.tmp.name) / 'profile.json', self.catalog)
        self.session = RPGSession(self.store, self.catalog)
        self.assertTrue(self.session.initialize())
        self.weapon = self.session.get_equipped_item('primary')

    def add_material(self, definition, quantity, locked=False):
        item = create_item(self.catalog, definition, quantity=quantity)
        item.locked = locked
        self.session.profile.add_item(item)
        return item

    def test_split_stacks_and_equipped_weapon_saved_together(self):
        first = self.add_material('scrap_metal', 3)
        second = self.add_material('scrap_metal', 7)
        locked = self.add_material('scrap_metal', 99, locked=True)
        before = self.session.get_effective_config_for_slot('primary')['damage']
        quote = self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        ok, msg = self.session.upgrade_weapon(quote)
        self.assertTrue(ok, msg)
        saved = self.store.load().profile
        self.assertNotIn(first.uid, saved.items)
        self.assertEqual(saved.items[second.uid].quantity, 2)
        self.assertEqual(saved.items[locked.uid].quantity, 99)
        self.assertEqual(saved.equipment['primary'], self.weapon.uid)
        self.assertAlmostEqual(self.session.get_effective_config_for_slot('primary')['damage'], before * 1.02)
        # A repeated callback cannot charge for the same preview twice.
        self.assertFalse(self.session.upgrade_weapon(quote)[0])

    def test_failed_save_preserves_profile_materials_and_effective_stats(self):
        self.add_material('bone_fragment', 12)
        self.store.save(self.session.profile)
        before = self.session.profile.to_dict()
        disk = self.store.path.read_bytes()
        quote = self.session.quote_upgrade(self.weapon.uid, 'weakpoint')
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            self.assertFalse(self.session.upgrade_weapon(quote)[0])
        self.assertEqual(self.session.profile.to_dict(), before)
        self.assertEqual(self.store.path.read_bytes(), disk)
        self.assertTrue(self.session.upgrade_weapon(quote)[0])
        self.assertEqual(material_count(self.session.profile, 'bone_fragment'), 6)

    def test_caps_preserve_other_affixes_and_never_charge_at_cap(self):
        for recipe_id, recipe in RECIPES.items():
            self.add_material(recipe.material_id, 999)
            while True:
                try:
                    quote = self.session.quote_upgrade(self.weapon.uid, recipe_id)
                except ValidationError:
                    break
                ok, msg = self.session.upgrade_weapon(quote)
                self.assertTrue(ok, msg)
            target = self.session.get_item(self.weapon.uid)
            self.assertEqual(next(a.value for a in target.affixes if a.id == recipe.affix_id), recipe.cap)
            before = self.session.profile.to_dict()
            with self.assertRaises(ValidationError):
                self.session.quote_upgrade(self.weapon.uid, recipe_id)
            self.assertEqual(self.session.profile.to_dict(), before)
        self.assertEqual(len(self.session.get_item(self.weapon.uid).affixes), 2)

    def test_locked_unsecured_unknown_and_wrong_profile_are_rejected(self):
        self.add_material('scrap_metal', 8, locked=True)
        with self.assertRaises(ValidationError):
            self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        self.add_material('scrap_metal', 8)
        self.weapon.locked = True
        with self.assertRaises(ValidationError):
            self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        self.weapon.locked = False
        foreign = create_item(self.catalog, 'weapon_ar')
        with self.assertRaises(ValidationError):
            self.session.quote_upgrade(foreign.uid, 'reinforce')
        with self.assertRaises(ValidationError):
            self.session.quote_upgrade(self.weapon.uid, 'bad_recipe')
        quote = self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        self.session.profile.profile_id = 'another-character'
        self.assertFalse(self.session.upgrade_weapon(quote)[0])

    def test_insufficient_material_never_spends_partial_stack(self):
        self.add_material('scrap_metal', 7)
        before = self.session.profile.to_dict()
        with self.assertRaises(ValidationError):
            self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        self.assertEqual(self.session.profile.to_dict(), before)

    def test_game_workshop_guard_blocks_test_mode_and_pending_extraction(self):
        from game import LiminalInfiniteLoop
        self.add_material('scrap_metal', 8)
        quote = self.session.quote_upgrade(self.weapon.uid, 'reinforce')
        game = SimpleNamespace(game_state='INVENTORY', rpg_session=self.session,
                               combat=SimpleNamespace(rpg_session=self.session))
        game.is_test_mode = True
        self.assertFalse(LiminalInfiniteLoop.upgrade_weapon(game, quote)[0])
        game.is_test_mode = False
        game._extraction_pending = True
        self.assertFalse(LiminalInfiniteLoop.upgrade_weapon(game, quote)[0])
        game._extraction_pending = False
        game.game_state = 'PLAYING'
        self.assertFalse(LiminalInfiniteLoop.upgrade_weapon(game, quote)[0])
        game.game_state = 'INVENTORY'
        self.assertTrue(LiminalInfiniteLoop.upgrade_weapon(game, quote)[0])
