"""Comprehensive end-to-end verification script for Workshop UI and Character Deletion."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from panda3d.core import NodePath, loadPrcFileData

loadPrcFileData(
    "",
    "window-type offscreen\n"
    "win-size 1600 900\n"
    "audio-library-name null\n"
    "sync-video false\n"
    "model-path assets\n"
)

from game import LiminalInfiniteLoop
from rpg.characters import CharacterManager
from rpg.items import create_item, load_catalog, ValidationError
from rpg.save_store import SaveStore
from rpg.session import RPGSession
from rpg.workshop import RECIPES, material_count


def verify_workshop_and_deletion() -> int:
    print("=== [WORKSHOP & CHARACTER DELETION VERIFICATION SUITE] ===")
    catalog = load_catalog()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # -------------------------------------------------------------
        # 1. Character Management: Roster Setup, Long Names & Same Names
        # -------------------------------------------------------------
        print("\n--- [1. Character Roster & Creation Setup] ---")
        char_mgr = CharacterManager(tmp_path, catalog)
        # Create 2 characters with identical names (differentiated by UUID) and one long Korean name
        c_long = char_mgr.create_character("최강의탐험가대원")
        c_same1 = char_mgr.create_character("정예대원")
        c_same2 = char_mgr.create_character("정예대원")
        print(f"[OK] Created 3 characters: '{c_long.name}', '{c_same1.name}' ({c_same1.id[:8]}), '{c_same2.name}' ({c_same2.id[:8]})")
        assert len(char_mgr.character_list.characters) == 3

        # Prepare equipment & materials for c_long
        store_long = char_mgr.get_character_save_store(c_long.id)
        prof = store_long.load().profile
        prof.currencies["credits"] = 5000

        # Add 45 items (weapons and materials)
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        weapon_keys = ["weapon_pistol", "weapon_dual_pistol", "weapon_ar", "weapon_shotgun"]
        for i in range(40):
            r = rarities[i % len(rarities)]
            w = weapon_keys[i % len(weapon_keys)]
            it = create_item(catalog, w, rarity=r, item_level=(i % 10) + 1)
            prof.add_item(it)

        # Add scrap_metal (150 total, 10 locked) and bone_fragment (100 total, 6 locked)
        scrap_free = create_item(catalog, "scrap_metal", quantity=140)
        scrap_locked = create_item(catalog, "scrap_metal", quantity=10)
        scrap_locked.locked = True
        bone_free = create_item(catalog, "bone_fragment", quantity=94)
        bone_locked = create_item(catalog, "bone_fragment", quantity=6)
        bone_locked.locked = True
        prof.add_item(scrap_free)
        prof.add_item(scrap_locked)
        prof.add_item(bone_free)
        prof.add_item(bone_locked)

        # Equip first pistol and shotgun
        all_weapons = [it for it in prof.items.values() if catalog[it.definition_id].kind == "weapon"]
        prof.equip("primary", all_weapons[0].uid, catalog)
        prof.equip("secondary", all_weapons[1].uid, catalog)
        store_long.save(prof)
        char_mgr.select_character(c_long.id)

        # -------------------------------------------------------------
        # 2. Launch Real Game Instance with Patched Save Store
        # -------------------------------------------------------------
        print("\n--- [2. Real Game Workshop Upgrades & Guards] ---")
        with patch("game.get_default_save_path", return_value=tmp_path / "profile.json"):
            app = LiminalInfiniteLoop()
            assert app.character_mgr is not None
            assert app.character_mgr.character_list.active_character_id == c_long.id

            # (A) Verify Character Selection & Title Screen Guards
            app.ui_mgr.show_character_select_modal()
            app.taskMgr.step()
            assert not app.ui_mgr.char_select_modal.isHidden()

            # (B) Test Character Deletion Flow on Inactive Character (c_same1)
            app.ui_mgr._on_click_delete_character(c_same1.id)
            assert not app.ui_mgr.char_delete_modal.isHidden()
            assert app.ui_mgr._deleting_char_id == c_same1.id

            # Name mismatch check
            app.ui_mgr.char_delete_entry.set("틀린이름")
            app.ui_mgr._update_delete_confirm_btn_state()
            assert app.ui_mgr.btn_confirm_delete["state"] == "disabled"
            app.ui_mgr._on_click_confirm_delete()
            assert not app.ui_mgr.char_delete_modal.isHidden()
            assert "일치하지 않습니다" in app.ui_mgr.lbl_del_err.text

            # Exact name match
            app.ui_mgr.char_delete_entry.set("정예대원")
            app.ui_mgr._update_delete_confirm_btn_state()
            assert app.ui_mgr.btn_confirm_delete["state"] == "normal"
            previous_session = app.rpg_session
            with patch.object(app.character_mgr, 'save_character_list', side_effect=OSError('review disk full')):
                app.ui_mgr._on_click_confirm_delete()
                assert not app.ui_mgr.char_delete_modal.isHidden()
                assert app.rpg_session is previous_session
                assert c_same1.id in [c.id for c in app.character_mgr.character_list.characters]
            app.ui_mgr._on_click_confirm_delete()
            assert app.ui_mgr.char_delete_modal.isHidden()

            # Verify c_same1 removed, c_same2 preserved (same name, distinct ID)
            roster = app.character_mgr.load_character_list()
            char_ids = [c.id for c in roster.characters]
            assert c_same1.id not in char_ids
            assert c_same2.id in char_ids
            # Physical file is preserved
            assert char_mgr.get_character_save_store(c_same1.id).path.exists()
            print("[OK] Same-name deletion correctly targeted specific UUID and preserved physical file.")

            # (C) Start Game with c_long
            app.ui_mgr.hide_character_select_modal()
            app.start_game()
            assert app.game_state == "PLAYING"
            assert app.rpg_session is not None
            print("[OK] Game started in PLAYING state with active session.")

            # Deletion during PLAYING is blocked
            assert not app.delete_character(c_same2.id, "정예대원")
            assert "타이틀 화면" in app.character_error
            print("[OK] Character deletion blocked during active run.")

            # (D) Open Tactical Inventory and Switch to Workshop Tab
            app.open_inventory()
            assert app.game_state == "INVENTORY"
            app.ui_mgr._switch_inventory_tab("workshop")
            assert not app.ui_mgr.workshop_ui.is_hidden()
            ws = app.ui_mgr.workshop_ui
            ws.refresh()

            # Verify top material badges (150 scrap total, 140 usable, 10 locked)
            assert "총 150개 (사용 가능 140개 / 잠김 10개)" in ws.lbl_mat_scrap.text
            assert "총 100개 (사용 가능 94개 / 잠김 6개)" in ws.lbl_mat_bone.text
            print("[OK] Workshop material badges accurately reflect usable vs locked stocks.")

            # (E) Upgrade Equipped Primary Weapon
            primary_uid = app.rpg_session.profile.equipment["primary"]
            ws.selected_uid = primary_uid
            ws.selected_recipe = "reinforce"
            ws.refresh()

            # Before stats
            before_dmg = app.rpg_session.get_effective_config_for_slot("primary")["damage"]
            quote = app.rpg_session.quote_upgrade(primary_uid, "reinforce")
            assert quote.cost == 8
            assert quote.available == 140
            assert quote.after == 1.02

            # Execute upgrade via game.upgrade_weapon(quote)
            ok, msg = app.upgrade_weapon(quote)
            assert ok, f"Upgrade failed: {msg}"
            ws.refresh()

            # Verify ammunition preserved and damage mult updated
            after_dmg = app.rpg_session.get_effective_config_for_slot("primary")["damage"]
            assert abs(after_dmg - before_dmg * 1.02) < 1e-4
            assert material_count(app.rpg_session.profile, "scrap_metal") == 132
            # Locked scrap is intact (10)
            assert sum(it.quantity for it in app.rpg_session.profile.items.values() if it.definition_id == "scrap_metal") == 142
            print(f"[OK] Upgraded primary weapon: damage {before_dmg:.2f} -> {after_dmg:.2f} (+2%p), scrap spent: 8.")

            # (F) Upgrade Weakpoint (bone_fragment)
            ws.selected_recipe = "weakpoint"
            ws.refresh()
            quote_wp = app.rpg_session.quote_upgrade(primary_uid, "weakpoint")
            assert quote_wp.cost == 6
            assert quote_wp.after == 1.05
            ok_wp, msg_wp = app.upgrade_weapon(quote_wp)
            assert ok_wp, f"Weakpoint upgrade failed: {msg_wp}"
            assert material_count(app.rpg_session.profile, "bone_fragment") == 88
            print("[OK] Upgraded weakpoint multiplier: +5%p, bone spent: 6.")

            # (G) Test Quote Reuse Rejection
            ok_re, msg_re = app.upgrade_weapon(quote_wp)
            assert not ok_re
            print("[OK] Single-use quote reuse properly rejected.")

            # (H) Test Locked Weapon Rejection
            target_weapon = app.rpg_session.profile.items[primary_uid]
            target_weapon.locked = True
            app.rpg_session.store.save(app.rpg_session.profile)
            ws.refresh()
            assert ws.btn_upgrade_execute["state"] == "disabled"
            try:
                app.rpg_session.quote_upgrade(primary_uid, "reinforce")
                assert False, "Locked weapon should raise ValidationError"
            except ValidationError:
                pass
            target_weapon.locked = False
            app.rpg_session.store.save(app.rpg_session.profile)
            print("[OK] Locked weapon upgrade rejected with ValidationError.")

            # (I) Test Cap Enforcement
            # Push damage_mult to cap 1.30
            for _ in range(20):
                try:
                    q = app.rpg_session.quote_upgrade(primary_uid, "reinforce")
                    app.upgrade_weapon(q)
                except ValidationError:
                    break
            aff = next(a for a in app.rpg_session.profile.items[primary_uid].affixes if a.id == "damage_mult")
            assert aff.value == 1.30
            # Next quote must fail with cap reached
            try:
                app.rpg_session.quote_upgrade(primary_uid, "reinforce")
                assert False, "Should reject at cap"
            except ValidationError as err:
                assert "상한" in str(err)
            print("[OK] Reinforce cap 1.30 strictly enforced.")

            # (J) Verify Shooting Range / Test Mode Guards
            app.is_test_mode = True
            q_test = app.rpg_session.quote_upgrade(primary_uid, "weakpoint")
            ok_test, msg_test = app.upgrade_weapon(q_test)
            assert not ok_test
            assert "일반 탐험" in msg_test
            app.is_test_mode = False
            print("[OK] Shooting range (test mode) workshop execution blocked.")

            # (K) Verify Extraction Pending Guard
            app._extraction_pending = True
            ok_ext, msg_ext = app.upgrade_weapon(q_test)
            assert not ok_ext
            app._extraction_pending = False
            print("[OK] Extraction pending workshop execution blocked.")

            # (L) Reload profile from disk and verify persistence
            reloaded_prof = store_long.load().profile
            reloaded_wpn = reloaded_prof.items[primary_uid]
            dmg_aff = next(a for a in reloaded_wpn.affixes if a.id == "damage_mult")
            assert dmg_aff.value == 1.30
            print("[OK] Upgraded weapon and spent materials successfully re-loaded from disk.")

            # Delete the active and last character through the real UI, then recreate.
            app.close_inventory()
            app.return_to_intro()
            app.ui_mgr.show_character_select_modal()
            app.ui_mgr._on_click_delete_character(c_long.id)
            app.handle_escape()
            assert app.ui_mgr.char_delete_modal.isHidden()
            assert not app.ui_mgr.char_select_modal.isHidden()
            for char in list(app.character_mgr.character_list.characters):
                app.ui_mgr._on_click_delete_character(char.id)
                app.ui_mgr.char_delete_entry.set(char.name)
                app.ui_mgr._on_click_confirm_delete()
            assert not app.character_mgr.character_list.characters
            assert app.rpg_session is None and app.combat.rpg_session is None
            assert app.ui_mgr.workshop_ui.session is None
            assert app.create_and_switch_character('ReviewNew')
            app.ui_mgr.hide_character_select_modal()
            app.start_game()
            assert app.game_state == 'PLAYING'
            assert len(app.rpg_session.profile.items) == 4
            print('[OK] Deletion failure, ESC, active/last deletion, recreation and restart.')
            app.destroy()

    print("\n=== [ALL WORKSHOP & CHARACTER VERIFICATIONS PASSED] ===")
    return 0


if __name__ == "__main__":
    sys.exit(verify_workshop_and_deletion())

