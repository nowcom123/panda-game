import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from rpg.quick_use import get_quick_use_items, QuickUseManager


class QuickUseTests(unittest.TestCase):
    def setUp(self):
        self.mock_game = MagicMock()
        self.mock_game.game_state = "PLAYING"
        self.mock_game.is_test_mode = False
        self.mock_game._extraction_pending = False
        self.mock_game.game_over = False
        self.mock_game.game_won = False
        self.mock_game.rpg_session = SimpleNamespace(is_valid=True)

        self.mock_player = MagicMock()
        self.mock_player.inventory = [
            {"id": "medkit", "count": 3, "quick_slot": 1},
            {"id": "adrenaline", "count": 2, "quick_slot": 2},
            {"id": "ammo_pack", "count": 5, "quick_slot": 3},
            {"id": "frag_grenade", "count": 4, "quick_slot": 4},
            {"id": "combat_stim", "count": 1, "quick_slot": None},
            {"id": "scrap_metal", "count": 10},
            {"id": "old_key", "count": 1},
        ]
        self.mock_player.use_item = MagicMock(return_value=(True, "사용 성공"))
        self.mock_player.is_aiming = False
        self.mock_player.lock_mouse = MagicMock()

        self.mock_game.player = self.mock_player
        self.mock_game.combat = MagicMock()
        self.mock_game.bullet_time_timer = 2.5
        self.mock_game.ui_mgr = MagicMock()
        self.mock_game.ui_mgr.is_char_delete_modal_open = MagicMock(return_value=False)
        self.mock_game.ui_mgr.is_inventory_open = MagicMock(return_value=False)

    def test_quick_use_item_filtering(self):
        """RPG 모드에서 1/2(medkit/adrenaline) 포함, 3/4(ammo/grenade) 제외, None(combat_stim) 포함, 재료 제외"""
        items = get_quick_use_items(self.mock_game.player, self.mock_game)
        item_ids = [it["id"] for it in items]

        # medkit, adrenaline should be included
        self.assertIn("medkit", item_ids)
        self.assertIn("adrenaline", item_ids)
        # combat_stim (quick_slot=None) should be included
        self.assertIn("combat_stim", item_ids)

        # ammo_pack (slot 3) and frag_grenade (slot 4) should be excluded
        self.assertNotIn("ammo_pack", item_ids)
        self.assertNotIn("frag_grenade", item_ids)

        # Materials/equipment/other non-consumables should be excluded
        self.assertNotIn("scrap_metal", item_ids)
        self.assertNotIn("old_key", item_ids)

    def test_quick_use_count_zero_excluded(self):
        """수량 0인 아이템은 제외"""
        self.mock_player.inventory[0]["count"] = 0  # medkit count = 0
        items = get_quick_use_items(self.mock_game.player, self.mock_game)
        item_ids = [it["id"] for it in items]
        self.assertNotIn("medkit", item_ids)

    def test_quick_use_manager_open_and_close(self):
        """백틱 누름 시 QUICK_USE 진입 및 불릿타임/상태 보존, 키 뗄 시 1회 소모 및 상태 복귀"""
        mgr = QuickUseManager(self.mock_game)

        # Test open
        mgr.on_key_down()
        self.assertTrue(mgr.is_open)
        self.assertEqual(self.mock_game.game_state, "QUICK_USE")
        # Bullet time timer preserved
        self.assertEqual(self.mock_game.bullet_time_timer, 2.5)

        self.assertIsNone(mgr.selected_index)
        mgr.select_next()
        self.assertEqual(mgr.selected_index, 0)
        selected_item_id = mgr.available_items[0]["id"]

        # Test key release
        mgr.on_key_up()
        self.assertFalse(mgr.is_open)
        self.assertEqual(self.mock_game.game_state, "PLAYING")
        self.mock_player.use_item.assert_called_once_with(selected_item_id, combat_system=self.mock_game.combat, game_instance=self.mock_game)

    def test_quick_use_manager_cancel_on_esc(self):
        """ESC나 취소 시 소모 없이 닫히고 이전 상태로 복구"""
        mgr = QuickUseManager(self.mock_game)
        mgr.on_key_down()
        self.assertTrue(mgr.is_open)
        mgr.selected_index = 0

        # Cancel
        mgr.cancel()
        self.assertFalse(mgr.is_open)
        self.assertEqual(self.mock_game.game_state, "PLAYING")
        self.mock_player.use_item.assert_not_called()

    def test_quick_use_manager_center_cancel_zone(self):
        """중앙 취소 영역(selected_index = None)인 채로 키를 놓으면 소모 없이 닫힘"""
        mgr = QuickUseManager(self.mock_game)
        mgr.on_key_down()
        self.assertTrue(mgr.is_open)
        mgr.selected_index = None

        mgr.on_key_up()
        self.assertFalse(mgr.is_open)
        self.assertEqual(self.mock_game.game_state, "PLAYING")
        self.mock_player.use_item.assert_not_called()

    def test_wheel_cycling_in_quick_use(self):
        """QUICK_USE 상태에서 휠 순환 시 선택 인덱스 변경"""
        mgr = QuickUseManager(self.mock_game)
        mgr.on_key_down()
        item_count = len(mgr.available_items)
        self.assertGreater(item_count, 1)

        self.assertIsNone(mgr.selected_index)
        mgr.select_next()
        self.assertEqual(mgr.selected_index, 0)
        mgr.select_next()
        self.assertEqual(mgr.selected_index, 1 % item_count)
        mgr.select_prev()
        self.assertEqual(mgr.selected_index, 0)
        mgr.select_prev()
        self.assertEqual(mgr.selected_index, item_count - 1)

    def test_game_wheel_handlers_respect_quick_use(self):
        """game.handle_weapon_next/prev가 QUICK_USE 상태에서는 무기 교체 대신 선택 순환"""
        from game import LiminalInfiniteLoop
        game = SimpleNamespace(
            game_state="QUICK_USE",
            quick_use_mgr=MagicMock(is_open=True),
            combat=MagicMock()
        )
        LiminalInfiniteLoop.handle_weapon_next(game)
        game.quick_use_mgr.select_next.assert_called_once()
        game.combat.next_weapon.assert_not_called()

        LiminalInfiniteLoop.handle_weapon_prev(game)
        game.quick_use_mgr.select_prev.assert_called_once()
        game.combat.prev_weapon.assert_not_called()


if __name__ == "__main__":
    unittest.main()

