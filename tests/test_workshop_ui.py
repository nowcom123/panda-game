import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from panda3d.core import NodePath

from rpg.items import create_item, load_catalog
from rpg.save_store import SaveStore
from rpg.session import RPGSession
from rpg.workshop import material_count
from rpg.workshop_ui import WorkshopUIPanel


class WorkshopUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = load_catalog()
        self.store = SaveStore(Path(self.tmp.name) / "profile.json", self.catalog)
        self.session = RPGSession(self.store, self.catalog)
        self.assertTrue(self.session.initialize())
        self.primary_weapon = self.session.get_equipped_item("primary")
        self.dummy_parent = NodePath("test_workshop_root")
        self.addCleanup(self.dummy_parent.removeNode)

        # Mock game object in INVENTORY state
        self.game = SimpleNamespace(
            game_state="INVENTORY",
            is_test_mode=False,
            _extraction_pending=False,
            rpg_session=self.session,
            combat=SimpleNamespace(rpg_session=self.session),
            upgrade_weapon=lambda quote: self.session.upgrade_weapon(quote),
            ui_mgr=SimpleNamespace(equipment_ui=SimpleNamespace(refresh=Mock())),
        )

    def add_material(self, defn_id, qty, locked=False):
        it = create_item(self.catalog, defn_id, quantity=qty)
        it.locked = locked
        self.session.profile.add_item(it)
        return it

    def test_workshop_panel_initialization_and_material_badges(self):
        self.add_material("scrap_metal", 10, locked=False)
        self.add_material("scrap_metal", 5, locked=True)
        self.add_material("bone_fragment", 8, locked=False)
        self.add_material("bone_fragment", 4, locked=True)

        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        self.assertEqual(panel.selected_recipe, "reinforce")

        # Verify material badges reflect total, usable, and locked
        panel.refresh()
        self.assertIsNotNone(panel.selected_uid)
        self.assertIn("총 15개 (사용 가능 10개 / 잠김 5개)", panel.lbl_mat_scrap.text)
        self.assertIn("총 12개 (사용 가능 8개 / 잠김 4개)", panel.lbl_mat_bone.text)

    def test_recipe_switching_and_preview_calculations(self):
        self.add_material("scrap_metal", 16)
        self.add_material("bone_fragment", 12)

        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()

        # reinforce recipe preview
        self.assertIn("기본 공격력", panel.lbl_preview_stats.text)
        self.assertIn("총열 보강", panel.btn_upgrade_execute["text"])
        self.assertEqual(panel.btn_upgrade_execute["state"], "normal")

        # switch to weakpoint recipe
        panel._select_recipe("weakpoint")
        self.assertEqual(panel.selected_recipe, "weakpoint")
        self.assertIn("약점 헤드샷", panel.lbl_preview_stats.text)
        self.assertIn("약점 각인", panel.btn_upgrade_execute["text"])
        self.assertEqual(panel.btn_upgrade_execute["state"], "normal")

    def test_shotgun_pellet_notice_in_preview(self):
        shotgun = create_item(self.catalog, "weapon_shotgun")
        self.session.profile.add_item(shotgun)
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = shotgun.uid
        panel.refresh()

        # Shotgun must display pellet count explicitly
        self.assertIn("펠릿당 피해량", panel.lbl_preview_stats.text)
        self.assertIn("총 8발", panel.lbl_preview_stats.text)

    def test_locked_weapon_blocks_upgrade_with_reason(self):
        self.add_material("scrap_metal", 20)
        self.primary_weapon.locked = True
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()

        self.assertEqual(panel.btn_upgrade_execute["state"], "disabled")
        self.assertIn("잠금을 해제", panel.lbl_fail_reason.text)

    def test_insufficient_materials_shows_cost_and_blocks_button(self):
        self.add_material("scrap_metal", 3)  # Need 8
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()

        self.assertEqual(panel.btn_upgrade_execute["state"], "disabled")
        self.assertIn("부족", panel.lbl_fail_reason.text)
        self.assertIn("고철", panel.lbl_cost_info.text)

    def test_test_mode_and_game_state_guards_block_upgrade(self):
        self.add_material("scrap_metal", 20)
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()
        self.assertEqual(panel.btn_upgrade_execute["state"], "normal")

        # In shooting range (test mode)
        self.game.is_test_mode = True
        panel.refresh()
        self.assertEqual(panel.btn_upgrade_execute["state"], "disabled")
        self.assertIn("사격장", panel.lbl_fail_reason.text)

        # In playing state
        self.game.is_test_mode = False
        self.game.game_state = "PLAYING"
        panel.refresh()
        self.assertEqual(panel.btn_upgrade_execute["state"], "disabled")
        self.assertIn("인벤토리", panel.lbl_fail_reason.text)

        # In extraction pending state
        self.game.game_state = "INVENTORY"
        self.game._extraction_pending = True
        panel.refresh()
        self.assertEqual(panel.btn_upgrade_execute["state"], "disabled")
        self.assertIn("탈출 대기", panel.lbl_fail_reason.text)

    def test_successful_upgrade_execution_updates_ui_and_saves_profile(self):
        self.add_material("scrap_metal", 20)
        on_change = Mock()
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game,
                                on_change_callback=on_change)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()
        self.assertEqual(panel.btn_upgrade_execute["state"], "normal")

        # Execute upgrade
        panel._on_click_upgrade()

        # Verify success message and callbacks
        self.assertFalse(panel.status_is_error)
        self.assertIn("강화 완료", panel.status_msg)
        on_change.assert_called_once()
        self.game.ui_mgr.equipment_ui.refresh.assert_called_once()

        # Material deducted from profile on disk
        saved = self.store.load().profile
        self.assertEqual(material_count(saved, "scrap_metal"), 12)
        upg_weapon = saved.items[self.primary_weapon.uid]
        damage_affix = next((a.value for a in upg_weapon.affixes if a.id == "damage_mult"), None)
        self.assertAlmostEqual(damage_affix, 1.02)

    def test_changed_preview_is_rejected_instead_of_silently_requoted(self):
        self.add_material('scrap_metal', 24)
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()
        shown_quote = panel._displayed_quote
        self.assertTrue(self.session.upgrade_weapon(shown_quote)[0])
        before = self.session.profile.to_dict()
        panel._on_click_upgrade()
        self.assertTrue(panel.status_is_error)
        self.assertEqual(self.session.profile.to_dict(), before)

    def test_ui_save_failure_keeps_materials_and_allows_retry(self):
        self.add_material('scrap_metal', 24)
        panel = WorkshopUIPanel(self.dummy_parent, session=self.session, game=self.game)
        panel.selected_uid = self.primary_weapon.uid
        panel.refresh()
        before = self.session.profile.to_dict()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            panel._on_click_upgrade()
        self.assertTrue(panel.status_is_error)
        self.assertEqual(self.session.profile.to_dict(), before)
        panel._on_click_upgrade()
        self.assertFalse(panel.status_is_error)
        self.assertEqual(material_count(self.session.profile, 'scrap_metal'), 16)


if __name__ == "__main__":
    unittest.main()

