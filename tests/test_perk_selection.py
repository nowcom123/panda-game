"""Unit tests for perk selection and combat_system reload_duration compatibility."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from perks import PERK_CATALOG
from player_controller import PlayerController
from combat_system import CombatSystem


class PerkSelectionTests(unittest.TestCase):
    def setUp(self):
        self.ui_mgr = MagicMock()
        self.player = SimpleNamespace(
            perks=set(),
            perk_levels={},
            speed_mult=1.0,
            max_hp=100.0,
            hp=100.0,
            exp=0.0,
            exp_to_next=100.0,
            level=1,
            pending_perk_picks=0,
            ui_mgr=self.ui_mgr,
            has_perk=lambda perk_id: perk_id in self.player.perks,
        )

    def test_all_catalog_perks_can_be_added(self):
        """Verify that every perk in the catalog can be selected without AttributeError."""
        combat_mock = SimpleNamespace(is_reloading=False, reload_timer=0.0)

        for perk_id in PERK_CATALOG:
            with self.subTest(perk_id=perk_id):
                PlayerController.add_perk(self.player, perk_id, combat_mock)
                self.assertIn(perk_id, self.player.perks)

    def test_speed_demon_with_combat_system_reloading(self):
        """Verify speed_demon perk accelerates active reload timer without error."""
        combat_mock = SimpleNamespace(is_reloading=True, reload_timer=2.0)
        PlayerController.add_perk(self.player, "speed_demon", combat_mock)
        self.assertAlmostEqual(combat_mock.reload_timer, 2.0 * 0.65)

    def test_combat_system_reload_duration_property(self):
        """Verify CombatSystem reload_duration property works dynamically."""
        combat = SimpleNamespace(
            current_weapon="PISTOL",
            base=SimpleNamespace(player=self.player),
            is_reloading=False,
            reload_timer=0.0
        )
        # Check property getter on class
        duration = CombatSystem.reload_duration.fget(combat)
        self.assertAlmostEqual(duration, 1.25)

        # After speed_demon perk
        self.player.perks.add("speed_demon")
        duration_with_perk = CombatSystem.reload_duration.fget(combat)
        self.assertAlmostEqual(duration_with_perk, 1.25 * 0.65)


if __name__ == '__main__':
    unittest.main()
