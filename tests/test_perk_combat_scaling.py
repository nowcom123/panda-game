"""Tests for Antigravity-owned combat, projectile, and UI scaling."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath, Vec3
from perks import PERK_CATALOG, get_perk_stats
from ui_manager import UIManager
from projectiles import FragGrenade
from combat_system import CombatSystem, WEAPON_CONFIGS


class PerkCombatScalingTests(unittest.TestCase):
    def test_ui_update_perk_badges_with_and_without_explicit_map(self):
        ui = UIManager.__new__(UIManager)
        ui.perk_badge_text = Mock()

        # Empty perks
        ui.update_perk_badges(set())
        ui.perk_badge_text.setText.assert_called_with("[장착 퍽] 없음")

        # Explicit map
        ui.update_perk_badges({'ricochet', 'bullet_storm'}, {'ricochet': 3, 'bullet_storm': 2})
        text = ui.perk_badge_text.setText.call_args[0][0]
        self.assertIn("Lv.3", text)
        self.assertIn("Lv.2", text)

        # Fallback to player's perk_levels
        ui.shop_player = SimpleNamespace(perk_levels={'ricochet': 4})
        ui.update_perk_badges({'ricochet'})
        fallback_text = ui.perk_badge_text.setText.call_args[0][0]
        self.assertIn("Lv.4", fallback_text)

    def test_ui_select_perk_card_guards(self):
        ui = UIManager.__new__(UIManager)
        modal = Mock()
        modal.isHidden.return_value = False
        ui.shop_modal = modal
        ui.offered_perks = [{'id': 'ricochet', 'name': '도탄 사격'}]
        ui.perk_cards = [{'frame': {}, 'btn': {}}]
        ui.shop_msg_text = Mock()
        ui.shop_owned_perks_text = Mock()
        ui.perk_badge_text = Mock()
        ui.shop_combat = None

        player = Mock()
        player.perks = {'ricochet'}
        player.perk_levels = {'ricochet': 2}
        player.add_perk.return_value = 2
        ui.shop_player = player
        ui.selected_perk_idx = -1

        # Negative index guarded
        ui._select_perk_card(-1)
        self.assertEqual(ui.selected_perk_idx, -1)
        player.add_perk.assert_not_called()

        # Hidden modal guarded
        modal.isHidden.return_value = True
        ui._select_perk_card(0)
        self.assertEqual(ui.selected_perk_idx, -1)
        player.add_perk.assert_not_called()

        # Valid selection
        modal.isHidden.return_value = False
        ui._select_perk_card(0)
        self.assertEqual(ui.selected_perk_idx, 0)
        player.add_perk.assert_called_once_with('ricochet', None)

        # Repeated selection guarded against duplicate level grant
        ui._select_perk_card(0)
        self.assertEqual(player.add_perk.call_count, 1)

    def test_cluster_grenade_scales_sub_munitions_and_caps_at_twelve(self):
        render = NodePath('render')
        grenade = FragGrenade(render, Vec3(0, 5, 0), Vec3(0, 1, 0), None)

        # Level 1: min(12, 1 + 3) = 4
        player1 = SimpleNamespace(perks={'cluster_grenade'}, perk_levels={'cluster_grenade': 1},
                                  has_perk=lambda p: p in player1.perks)
        target1 = SimpleNamespace(pos=Vec3(0, 5, 0), hp=10000, take_damage=Mock(return_value=False), is_corpse=False)
        grenade.explode([target1], player1, None)
        self.assertEqual(target1.take_damage.call_count, 1 + 4)  # 1 main + 4 sub

        # Level 15: capped at 12
        grenade2 = FragGrenade(render, Vec3(0, 5, 0), Vec3(0, 1, 0), None)
        player15 = SimpleNamespace(perks={'cluster_grenade'}, perk_levels={'cluster_grenade': 15},
                                   has_perk=lambda p: p in player15.perks)
        target15 = SimpleNamespace(pos=Vec3(0, 5, 0), hp=10000, take_damage=Mock(return_value=False), is_corpse=False)
        grenade2.explode([target15], player15, None)
        self.assertEqual(target15.take_damage.call_count, 1 + 12)  # 1 main + 12 sub

    def test_bullet_storm_cooldown_mult_at_high_levels(self):
        combat = CombatSystem.__new__(CombatSystem)
        combat.combo_count = 0
        combat.bullet_storm_timer = 2.0
        combat.ammo = 10
        combat.current_weapon = 'PISTOL'
        combat.base = SimpleNamespace(player=SimpleNamespace(
            perks={'bullet_storm'}, perk_levels={'bullet_storm': 3},
            has_perk=lambda p: True
        ))
        stats = get_perk_stats('bullet_storm', 3)
        self.assertAlmostEqual(stats['duration'], 5.5)
        self.assertAlmostEqual(stats['cooldown_mult'], 1 / (1 + (1/.65 - 1)*3))


if __name__ == '__main__':
    unittest.main()
