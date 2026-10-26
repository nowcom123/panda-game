import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import NodePath

from direct.gui.DirectGui import DGG
from rpg.characters import CharacterManager
from rpg.items import load_catalog
from ui_manager import UIManager


class CharacterDeleteUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = load_catalog()
        self.manager = CharacterManager(Path(self.tmp.name), self.catalog)
        self.c1 = self.manager.create_character("Alpha")
        self.c2 = self.manager.create_character("Beta")

        self.root = NodePath("ui_root")
        self.addCleanup(self.root.removeNode)

        self.game = SimpleNamespace(
            game_state="INTRO",
            aspect2d=self.root,
            character_mgr=self.manager,
            rpg_session=SimpleNamespace(),
            combat=SimpleNamespace(active_item_uid=None, item_states={}),
            character_error=None,
            accept=Mock(),
            ignore=Mock(),
            taskMgr=None,
            switch_to_character=Mock(return_value=True),
        )

        # Standalone UIManager instance for testing modals
        self.ui = UIManager.__new__(UIManager)
        self.ui.base = self.game
        self.game.ui_mgr = self.ui
        self.ui.font_kw = {}
        self.ui.btn_font_kw = {}

        # Setup character cards and delete modal
        self.ui._setup_character_select_modal()
        self.ui.intro_frame = NodePath("intro_frame")
        self.ui.lbl_active_explorer = SimpleNamespace(setText=Mock(), setFg=Mock())

        # Show character select modal so parent is not hidden
        self.ui.show_character_select_modal()

    def tearDown(self):
        if hasattr(self.ui, "hide_character_delete_modal"):
            self.ui.hide_character_delete_modal()

    def test_delete_button_visibility_on_slots(self):
        self.ui._refresh_character_select_modal()

        # Slot 1 (Alpha): character exists -> del_btn shown
        card0 = self.ui.char_cards[0]
        self.assertFalse(card0["del_btn"].isHidden())
        self.assertEqual(card0["del_btn"]["extraArgs"], [self.c1.id])

        # Slot 2 (Beta): character exists -> del_btn shown
        card1 = self.ui.char_cards[1]
        self.assertFalse(card1["del_btn"].isHidden())
        self.assertEqual(card1["del_btn"]["extraArgs"], [self.c2.id])

        # Slot 3 (Empty): no character -> del_btn hidden
        card2 = self.ui.char_cards[2]
        self.assertTrue(card2["del_btn"].isHidden())

    def test_delete_modal_opens_with_accurate_info_and_esc_closes_it(self):
        self.ui._refresh_character_select_modal()

        # Click delete on Alpha (slot 1)
        self.ui._on_click_delete_character(self.c1.id)

        self.assertFalse(self.ui.char_delete_modal.isHidden())
        self.assertEqual(self.ui._deleting_char_id, self.c1.id)
        self.assertEqual(self.ui._deleting_char_name, "Alpha")
        self.assertIn("슬롯 1", self.ui.lbl_del_target_info.text)
        self.assertIn("Alpha", self.ui.lbl_del_target_info.text)
        self.assertIn("보존", self.ui.lbl_del_notice.text)  # Explains recovery preservation
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        # Closing modal via hide_character_delete_modal (ESC simulation)
        self.ui.hide_character_delete_modal()
        self.assertTrue(self.ui.char_delete_modal.isHidden())
        self.assertIsNone(self.ui._deleting_char_id)
        self.assertFalse(self.ui.char_select_modal.isHidden())

    def test_name_validation_enables_and_mismatches_disable_confirm_button(self):
        self.ui._refresh_character_select_modal()
        self.ui._on_click_delete_character(self.c1.id)

        # Wrong name typed
        self.ui.char_delete_entry.set("WrongName")
        self.ui._update_delete_confirm_btn_state()
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        # Empty name
        self.ui.char_delete_entry.set("")
        self.ui._update_delete_confirm_btn_state()
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        # Exact matching name typed
        self.ui.char_delete_entry.set("Alpha")
        self.ui._update_delete_confirm_btn_state()
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)

    def test_confirm_delete_execution_and_error_handling(self):
        from game import LiminalInfiniteLoop

        self.game.delete_character = lambda char_id, name: LiminalInfiniteLoop.delete_character(
            self.game, char_id, name
        )

        self.ui._refresh_character_select_modal()
        self.ui._on_click_delete_character(self.c1.id)

        # 1. Attempt delete with mismatch -> rejected
        self.ui.char_delete_entry.set("Wrong")
        self.ui._on_click_confirm_delete()
        self.assertIn("일치하지 않습니다", self.ui.lbl_del_err.text)
        self.assertFalse(self.ui.char_delete_modal.isHidden())

        # 2. Attempt delete with exact name -> success
        self.ui.char_delete_entry.set("Alpha")
        self.ui._on_click_confirm_delete()
        self.assertTrue(self.ui.char_delete_modal.isHidden())

        # Alpha is removed from roster
        roster = self.manager.load_character_list()
        self.assertEqual([c.name for c in roster.characters], ["Beta"])

        # 3. Delete remaining character Beta
        self.ui._on_click_delete_character(self.c2.id)
        self.ui.char_delete_entry.set("Beta")
        self.ui._on_click_confirm_delete()

        roster_empty = self.manager.load_character_list()
        self.assertEqual(roster_empty.characters, [])
        self.assertIsNone(roster_empty.active_character_id)


    def test_autofill_button_sets_name_and_enables_confirm(self):
        self.ui._refresh_character_select_modal()
        self.ui._on_click_delete_character(self.c1.id)

        self.assertEqual(self.ui.char_delete_entry.get(), "")
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        # Click the new autofill button
        self.ui._on_click_autofill_delete_name()

        # Should be auto-populated with target name and confirm button activated
        self.assertEqual(self.ui.char_delete_entry.get(), "Alpha")
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)

    def test_korean_name_deletion_via_autofill_and_hangul_matching(self):
        # Create a Korean named character
        korean_char = self.manager.create_character("기존 탐험가")
        self.ui._refresh_character_select_modal()

        from game import LiminalInfiniteLoop
        self.game.delete_character = lambda char_id, name: LiminalInfiniteLoop.delete_character(
            self.game, char_id, name
        )

        # 1. Test typing English QWERTY for Korean name: 'rlwhs xkagjark' -> '기존 탐험가'
        self.ui._on_click_delete_character(korean_char.id)
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        self.ui.char_delete_entry.set("rlwhs xkagjark")
        self.ui._update_delete_confirm_btn_state()

        # Should match and auto-convert to Korean syllable string!
        self.assertEqual(self.ui.char_delete_entry.get(), "기존 탐험가")
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)

        # 2. Test autofill button
        self.ui.char_delete_entry.set("")
        self.ui._update_delete_confirm_btn_state()
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        self.ui._on_click_autofill_delete_name()
        self.assertEqual(self.ui.char_delete_entry.get(), "기존 탐험가")
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)

        # 3. Confirm deletion execution
        self.ui._on_click_confirm_delete()
        self.assertTrue(self.ui.char_delete_modal.isHidden())
        roster = self.manager.load_character_list()
        self.assertNotIn(korean_char.id, [c.id for c in roster.characters])

    def test_paste_button_and_ctrl_v(self):
        from unittest.mock import patch
        self.ui._refresh_character_select_modal()
        self.ui._on_click_delete_character(self.c2.id)

        with patch("ui_manager.get_clipboard_text", return_value="Beta"):
            # Trigger paste button
            self.ui._on_paste_delete_entry()
            self.assertEqual(self.ui.char_delete_entry.get(), "Beta")
            self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)

        # Reset and trigger via global Ctrl+V handler
        self.ui.char_delete_entry.set("")
        self.ui._update_delete_confirm_btn_state()
        self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.DISABLED)

        with patch("ui_manager.get_clipboard_text", return_value="Beta"):
            self.ui._on_global_ctrl_v()
            self.assertEqual(self.ui.char_delete_entry.get(), "Beta")
            self.assertEqual(self.ui.btn_confirm_delete["state"], DGG.NORMAL)


if __name__ == "__main__":
    unittest.main()

