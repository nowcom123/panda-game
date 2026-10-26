"""Offscreen UI verification and multi-resolution capture for Character Select and Inventory."""

import sys
import tempfile
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from panda3d.core import Filename, PNMImage, loadPrcFileData

loadPrcFileData(
    "",
    "window-type offscreen\n"
    "win-size 1600 900\n"
    "audio-library-name null\n"
    "sync-video false\n"
    "model-path assets\n"
)

from game import LiminalInfiniteLoop
from rpg.items import create_item, load_catalog
from rpg.characters import CharacterManager


def capture_expansion_ui() -> int:
    out_dir = Path(__file__).resolve().parent
    catalog = load_catalog()

    # =============================================================
    # 1. 1600x900 Character Selection Modal & Inventory UI Capture
    # =============================================================
    print("=== [1/2] Capturing 1600x900 UI Previews ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Setup 2 characters in temp directory
        char_mgr = CharacterManager(tmp_path, catalog)
        c1 = char_mgr.create_character("베테랑요원")
        c2 = char_mgr.create_character("신규탐험가")

        # Equip c1 with 40 permanent items
        store1 = char_mgr.get_character_save_store(c1.id)
        res = store1.load()
        prof1 = res.profile
        prof1.currencies["credits"] = 3500

        # Add 40 items
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        weapon_keys = ["weapon_pistol", "weapon_dual_pistol", "weapon_ar", "weapon_shotgun"]
        for i in range(40):
            r = rarities[i % len(rarities)]
            w = weapon_keys[i % len(weapon_keys)]
            item = create_item(catalog, w, rarity=r, item_level=(i % 10) + 1)
            prof1.add_item(item)

        # Equip first pistol and shotgun
        all_items = list(prof1.items.values())
        prof1.equip("primary", all_items[0].uid, catalog)
        prof1.equip("secondary", all_items[1].uid, catalog)
        store1.save(prof1)

        char_mgr.select_character(c1.id)

        # Launch game targeting temp save directory
        # Patch get_default_save_path to return temp directory so CharacterManager finds our characters
        from unittest.mock import patch
        with patch("game.get_default_save_path", return_value=tmp_path / "profile.json"):
            app = LiminalInfiniteLoop()
            try:
                assert app.switch_to_character(c2.id), app.character_error
                assert app.combat.rpg_session is app.rpg_session
                assert app.create_and_switch_character("검증탐험가"), app.character_error
                assert len(app.character_mgr.character_list.characters) == 3
                assert app.switch_to_character(c1.id), app.character_error
                assert app.rpg_session.profile.currencies['credits'] == 3500
                assert set(app.combat.item_states) <= set(app.rpg_session.profile.items)
                with patch.object(app.character_mgr, 'save_character_list', side_effect=OSError('review disk failure')):
                    previous = app.rpg_session
                    assert not app.switch_to_character(c2.id)
                    assert app.rpg_session is previous
                    assert app.character_mgr.character_list.active_character_id == c1.id
                # (1) Capture Character Select Modal
                app.ui_mgr.show_character_select_modal()
                for _ in range(5):
                    app.taskMgr.step()

                img_char = out_dir / "character_select_1600x900.png"
                pnm = PNMImage()
                app.win.getScreenshot(pnm)
                pnm.write(Filename.fromOsSpecific(str(img_char)))
                assert img_char.is_file(), f"Failed to save {img_char}"
                print(f"[OK] Captured 1600x900 Character Selection UI: {img_char} ({img_char.stat().st_size:,} bytes)")

                # (2) Start game and populate run loot bag with 24 items
                app.ui_mgr.hide_character_select_modal()
                app.start_game()
                assert app.game_state == "PLAYING"
                assert not app.switch_to_character(c2.id)

                for i in range(24):
                    r_item = create_item(catalog, "weapon_pistol", rarity="rare", item_level=i + 1)
                    app.run_loot_bag.add_item(r_item)

                # Open inventory
                app.open_inventory()
                assert app.game_state == "INVENTORY"

                # Switch to equipment tab
                app.ui_mgr._switch_inventory_tab("equipment")
                app.ui_mgr.equipment_ui.refresh()

                for _ in range(5):
                    app.taskMgr.step()

                img_inv = out_dir / "inventory_ui_1600x900.png"
                pnm2 = PNMImage()
                app.win.getScreenshot(pnm2)
                pnm2.write(Filename.fromOsSpecific(str(img_inv)))
                assert img_inv.is_file(), f"Failed to save {img_inv}"
                print(f"[OK] Captured 1600x900 Inventory UI: {img_inv} ({img_inv.stat().st_size:,} bytes)")

            finally:
                app.destroy()

    # =============================================================
    # 2. 1280x720 Inventory UI Capture
    # =============================================================
    print("\n=== [2/2] Capturing 1280x720 UI Preview ===")
    loadPrcFileData("", "win-size 1280 720\n")

    with tempfile.TemporaryDirectory() as tmp_dir720:
        tmp_path720 = Path(tmp_dir720)
        char_mgr720 = CharacterManager(tmp_path720, catalog)
        c = char_mgr720.create_character("탐험가720")
        store720 = char_mgr720.get_character_save_store(c.id)
        prof720 = store720.load().profile
        prof720.currencies["credits"] = 2400

        for i in range(40):
            item = create_item(catalog, "weapon_ar", rarity="epic", item_level=(i % 5) + 1)
            prof720.add_item(item)
        items720 = list(prof720.items.values())
        prof720.equip("primary", items720[0].uid, catalog)
        prof720.equip("secondary", items720[1].uid, catalog)
        store720.save(prof720)
        char_mgr720.select_character(c.id)

        with patch("game.get_default_save_path", return_value=tmp_path720 / "profile.json"):
            app720 = LiminalInfiniteLoop()
            try:
                app720.start_game()
                for i in range(24):
                    app720.run_loot_bag.add_item(create_item(catalog, "weapon_dual_pistol", rarity="uncommon", item_level=1))

                app720.open_inventory()
                app720.ui_mgr._switch_inventory_tab("equipment")
                app720.ui_mgr.equipment_ui.refresh()

                for _ in range(5):
                    app720.taskMgr.step()

                img_720 = out_dir / "inventory_ui_1280x720.png"
                pnm720 = PNMImage()
                app720.win.getScreenshot(pnm720)
                pnm720.write(Filename.fromOsSpecific(str(img_720)))
                assert img_720.is_file(), f"Failed to save {img_720}"
                print(f"[OK] Captured 1280x720 Inventory UI: {img_720} ({img_720.stat().st_size:,} bytes)")
            finally:
                app720.destroy()

    print("\n=== All Offscreen UI Captures Succeeded! ===")
    return 0


if __name__ == "__main__":
    sys.exit(capture_expansion_ui())

