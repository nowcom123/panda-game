import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath
from perks import PERK_CATALOG
from player_controller import PlayerController
from ui_manager import UIManager


class PerkUITests(unittest.TestCase):
    def make_ui(self):
        ui = UIManager.__new__(UIManager)
        player = PlayerController(SimpleNamespace(game_state='SHOP'), None,
                                  NodePath('camera'), None, None, Mock())
        ui.base = SimpleNamespace(player=player)
        ui.shop_player = player
        ui.shop_combat = None
        ui.shop_modal = Mock()
        ui.shop_modal.isHidden.return_value = False
        ui.selected_perk_idx = -1
        ui.offered_perks = [PERK_CATALOG['vampiric_leech']]
        ui.perk_cards = [{'frame': {}, 'btn': {}}]
        ui.shop_msg_text = Mock()
        ui.shop_owned_perks_text = Mock()
        ui.perk_badge_text = Mock()
        return ui, player

    def test_keyboard_repeat_does_not_grant_extra_picks(self):
        ui, player = self.make_ui()
        ui._select_perk_card(0)
        ui._select_perk_card(0)
        self.assertEqual(player.perk_levels['vampiric_leech'], 1)
        # A new legitimate offer upgrades the same perk.
        ui.selected_perk_idx = -1
        ui._select_perk_card(0)
        self.assertEqual(player.perk_levels['vampiric_leech'], 2)

    def test_invalid_or_hidden_selection_does_not_grant_perks(self):
        ui, player = self.make_ui()
        ui._select_perk_card(-1)
        ui._select_perk_card(10)
        self.assertFalse(player.perks)
        ui.shop_modal.isHidden.return_value = True
        ui._select_perk_card(0)
        self.assertFalse(player.perks)

    def test_badges_and_owned_label_include_current_level(self):
        ui, player = self.make_ui()
        player.add_perk('vampiric_leech')
        player.add_perk('vampiric_leech')
        ui.update_perk_badges(player.perks, player.perk_levels)
        self.assertIn('2', ui.perk_badge_text.setText.call_args.args[0])
        ui._refresh_owned_perks_label()
        self.assertIn('2', ui.shop_owned_perks_text.setText.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
