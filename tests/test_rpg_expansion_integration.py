import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from panda3d.core import NodePath
from rpg.characters import CharacterManager
from rpg.items import create_item, load_catalog
from rpg.session import RPGSession
from rpg.save_store import SaveStore
from rpg.equipment_ui import EquipmentUIPanel
from rpg.run_loot import RunLootBag
from rpg.run_loot_ui import RunLootUIPanel


class RPGExpansionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.catalog = load_catalog()
        self.node = NodePath("test_expansion_ui")

    def tearDown(self):
        self.node.removeNode()
        self.temp_dir.cleanup()

    def test_equipment_ui_40_items_sorting_pagination_and_preservation(self):
        char_mgr = CharacterManager(self.root_path, self.catalog)
        c1 = char_mgr.create_character("테스터")
        store = char_mgr.get_character_save_store(c1.id)
        session = RPGSession(store, self.catalog)
        session.initialize(grant_starters=True)

        # Add 40 items of various rarities and definitions
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        weapon_keys = ["weapon_pistol", "weapon_dual_pistol", "weapon_ar", "weapon_shotgun"]
        for i in range(40):
            r = rarities[i % len(rarities)]
            w = weapon_keys[i % len(weapon_keys)]
            item = create_item(self.catalog, w, rarity=r, item_level=(i % 10) + 1)
            session.profile.add_item(item)
        store.save(session.profile)

        panel = EquipmentUIPanel(self.node, session)
        self.assertEqual(len(session.profile.items), 44)  # 4 starters + 40 added

        # Check total pages (44 / 7 = 7 pages)
        sorted_items = panel._get_sorted_items()
        self.assertEqual(len(sorted_items), 44)
        panel.refresh()
        self.assertIn("/ 7", panel.lbl_page.getText())

        # Test sorting modes
        panel._set_sort_mode("rarity")
        rarity_sorted = panel._get_sorted_items()
        # Legendary items should appear first
        self.assertEqual(rarity_sorted[0].rarity, "legendary")

        panel._set_sort_mode("name")
        name_sorted = panel._get_sorted_items()
        first_name = self.catalog[name_sorted[0].definition_id].name
        second_name = self.catalog[name_sorted[1].definition_id].name
        self.assertLessEqual(first_name, second_name)

        # Test pagination navigation and selection retention
        panel._set_sort_mode("rarity")
        panel._next_page()
        self.assertEqual(panel.current_page, 1)
        selected_item = rarity_sorted[7]  # first item of page 1
        panel._select_item_by_index(0)
        self.assertEqual(panel.selected_uid, selected_item.uid)

        # Toggle lock on selected item: selection and page must be preserved!
        panel._on_click_lock_toggle()
        self.assertEqual(panel.current_page, 1)
        self.assertEqual(panel.selected_uid, selected_item.uid)
        self.assertTrue(session.profile.items[selected_item.uid].locked)

        # Unequip button on target slot when both slots equipped
        panel.target_slot = "secondary"
        panel.refresh()
        self.assertTrue(panel.btn_unequip["state"] != "disabled")

        # Unequip secondary weapon
        panel._on_click_unequip()
        self.assertIsNone(session.profile.equipment["secondary"])

        # Now only primary is equipped; attempting to unequip last weapon must be blocked!
        panel.target_slot = "primary"
        panel.refresh()
        self.assertIn("마지막 무기 해제 불가", panel.btn_unequip["text"])
        self.assertEqual(panel.btn_unequip["state"], "disabled")

    def test_run_loot_ui_24_items_capacity(self):
        bag = RunLootBag()
        for i in range(24):
            item = create_item(self.catalog, "weapon_pistol", rarity="rare", item_level=i + 1)
            success, _ = bag.add_item(item)
            self.assertTrue(success)
        self.assertFalse(bag.can_add())
        self.assertEqual(bag.count, 24)

        panel = RunLootUIPanel(self.node, bag, self.catalog)
        panel.refresh()
        self.assertIn("24 / 24", panel.lbl_bag_status.getText())
        self.assertIn("/ 4", panel.lbl_page_info.getText())  # 24 items / 7 = 4 pages

    def test_game_character_switch_rules(self):
        from game import LiminalInfiniteLoop
        # Mock game instance
        char_mgr = CharacterManager(self.root_path, self.catalog)
        c1 = char_mgr.create_character("첫번째")
        c2 = char_mgr.create_character("두번째")

        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.game_state = "INTRO"
        game._extraction_pending = False
        game.character_mgr = char_mgr
        game.rpg_catalog = self.catalog
        game.combat = SimpleNamespace(
            set_rpg_session=Mock(),
            item_states={},
            reset_state=Mock(),
        )
        game.ui_mgr = SimpleNamespace(
            equipment_ui=SimpleNamespace(session=None, combat=None),
            update_active_explorer_display=Mock(),
        )

        # 1. Switch character in INTRO state -> succeeds
        res = game.switch_to_character(c2.id)
        self.assertTrue(res)
        self.assertEqual(char_mgr.character_list.active_character_id, c2.id)
        game.combat.set_rpg_session.assert_called()

        # 2. Switch character during PLAYING state -> blocked
        game.game_state = "PLAYING"
        res = game.switch_to_character(c1.id)
        self.assertFalse(res)
        self.assertEqual(char_mgr.character_list.active_character_id, c2.id)

        # 3. Switch character when _extraction_pending is True -> blocked
        game.game_state = "INTRO"
        game._extraction_pending = True
        res = game.switch_to_character(c1.id)
        self.assertFalse(res)
        self.assertEqual(char_mgr.character_list.active_character_id, c2.id)


if __name__ == '__main__':
    unittest.main()
