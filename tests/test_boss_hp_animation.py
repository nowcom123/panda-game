import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from panda3d.core import NodePath
from ui_manager import UIManager


class BossHpAnimationTests(unittest.TestCase):
    def make_ui(self):
        ui = UIManager.__new__(UIManager)
        ui.base = SimpleNamespace(boss=None)
        ui.boss_hud_frame = NodePath('boss_hud')
        ui.boss_hud_frame.hide()
        ui.boss_bar_fill = MagicMock()
        ui.boss_name_text = Mock()
        ui.boss_hp_text = Mock()
        ui.show_boss_hp_bar('골해의 지배자', 3500, 3500)
        return ui

    def test_damage_changes_target_immediately_but_bar_moves_each_frame(self):
        ui = self.make_ui()
        ui.update_boss_hp(1750, 3500)
        self.assertEqual(ui._boss_hp_display_ratio, 1)
        ui.boss_hp_text.setText.assert_called_with('1750 / 3500 (50.0%)')
        for _ in range(12):
            previous = ui._boss_hp_display_ratio
            ui._animate_boss_hp(1/60)
            self.assertLess(ui._boss_hp_display_ratio, previous)
            self.assertGreater(ui._boss_hp_display_ratio, .5)
        # A second hit updates the destination without restarting from full HP.
        previous = ui._boss_hp_display_ratio
        ui.update_boss_hp(1000, 3500)
        self.assertEqual(ui._boss_hp_display_ratio, previous)
        ui._animate_boss_hp(1/60)
        self.assertLess(ui._boss_hp_display_ratio, previous)

    def test_frame_rate_independence_and_zero_hp(self):
        values = []
        for fps in (30, 60, 144):
            ui = self.make_ui()
            ui.update_boss_hp(0, 3500)
            for _ in range(fps // 6):
                ui._animate_boss_hp(1/fps)
            values.append(ui._boss_hp_display_ratio)
            ui._animate_boss_hp(2)
            self.assertEqual(ui._boss_hp_display_ratio, 0)
        self.assertAlmostEqual(values[0], values[1], places=10)
        self.assertAlmostEqual(values[1], values[2], places=10)

    def test_live_hp_is_read_without_an_ai_update_and_keeps_boss_name(self):
        ui = self.make_ui()
        ui.base.boss = SimpleNamespace(hp=1400, max_hp=3500, phase=2)
        ui._animate_boss_hp(1/60)
        self.assertEqual(ui._boss_hp_target_ratio, .4)
        self.assertLess(ui._boss_hp_display_ratio, 1)
        ui.boss_name_text.setText.assert_called_with('골해의 지배자 — 폭주')

    def test_hidden_bar_does_not_reappear_and_respawn_starts_at_current_hp(self):
        ui = self.make_ui()
        ui.base.boss = SimpleNamespace(hp=0, max_hp=3500, phase=2)
        ui.hide_boss_hp_bar()
        ui._animate_boss_hp(.1)
        self.assertTrue(ui.boss_hud_frame.isHidden())
        self.assertIsNone(ui._boss_hp_display_ratio)
        ui.show_boss_hp_bar('골해의 지배자', 4000, 5000)
        self.assertEqual(ui._boss_hp_display_ratio, .8)
        ui.boss_bar_fill.setSx.assert_called_with(.8)


if __name__ == '__main__':
    unittest.main()
