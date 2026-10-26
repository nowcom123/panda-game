"""Offscreen multi-resolution UI capture script for Workshop, Character Deletion, Equipment, and Run Loot."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_capture_worker(width: int, height: int) -> int:
    from panda3d.core import Filename, PNMImage, loadPrcFileData

    loadPrcFileData(
        "",
        f"window-type offscreen\n"
        f"win-size {width} {height}\n"
        f"audio-library-name null\n"
        f"sync-video false\n"
        f"model-path assets\n"
    )

    from game import LiminalInfiniteLoop
    # constants.py sets its own default during import; override afterwards.
    loadPrcFileData('', f'win-size {width} {height}')
    from rpg.characters import CharacterManager
    from rpg.items import create_item, load_catalog, ItemAffix

    out_dir = Path(__file__).resolve().parent
    catalog = load_catalog()
    res_str = f"{width}x{height}"
    print(f"\n=== Capturing {res_str} Previews ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Setup 3 characters: 1 long Korean name + 2 duplicate names
        char_mgr = CharacterManager(tmp_path, catalog)
        c_long = char_mgr.create_character("최강의탐험가대원")
        c_same1 = char_mgr.create_character("정예대원")
        c_same2 = char_mgr.create_character("정예대원")

        store1 = char_mgr.get_character_save_store(c_long.id)
        prof1 = store1.load().profile
        prof1.currencies["credits"] = 7500

        # Add 42 permanent items
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        weapon_keys = ["weapon_pistol", "weapon_dual_pistol", "weapon_ar", "weapon_shotgun"]
        for i in range(40):
            r = rarities[i % len(rarities)]
            w = weapon_keys[i % len(weapon_keys)]
            it = create_item(catalog, w, rarity=r, item_level=(i % 10) + 1)
            prof1.add_item(it)

        # Add materials (scrap_metal & bone_fragment)
        scrap_free = create_item(catalog, "scrap_metal", quantity=80)
        scrap_locked = create_item(catalog, "scrap_metal", quantity=20)
        scrap_locked.locked = True
        bone_free = create_item(catalog, "bone_fragment", quantity=48)
        bone_locked = create_item(catalog, "bone_fragment", quantity=12)
        bone_locked.locked = True
        prof1.add_item(scrap_free)
        prof1.add_item(scrap_locked)
        prof1.add_item(bone_free)
        prof1.add_item(bone_locked)

        # Primary weapon with 3 affixes (damage_mult, reload_time_mult, weakpoint_mult)
        primary_wpn = create_item(catalog, "weapon_ar", rarity="legendary", item_level=12)
        primary_wpn.affixes = [
            ItemAffix(id="damage_mult", value=1.06),
            ItemAffix(id="reload_time_mult", value=0.88),
            ItemAffix(id="weakpoint_mult", value=1.15),
        ]
        prof1.add_item(primary_wpn)

        # Secondary weapon: shotgun
        sec_wpn = create_item(catalog, "weapon_shotgun", rarity="epic", item_level=10)
        prof1.add_item(sec_wpn)

        prof1.equip("primary", primary_wpn.uid, catalog)
        prof1.equip("secondary", sec_wpn.uid, catalog)
        store1.save(prof1)
        char_mgr.select_character(c_long.id)

        # Helper screenshot function
        def save_screen(app, filename_stem):
            for _ in range(6):
                app.taskMgr.step()
            img_path = out_dir / f"{filename_stem}_{res_str}.png"
            pnm = PNMImage()
            app.win.getScreenshot(pnm)
            assert (pnm.getXSize(), pnm.getYSize()) == (width, height)
            pnm.write(Filename.fromOsSpecific(str(img_path)))
            assert img_path.is_file(), f"Screenshot failed: {img_path}"
            print(f"  [OK] Saved: {img_path.name} ({img_path.stat().st_size:,} bytes)")

        with patch("game.get_default_save_path", return_value=tmp_path / "profile.json"):
            app = LiminalInfiniteLoop()
            try:
                # ---------------------------------------------------------
                # Screen 1: Character Select Modal
                # ---------------------------------------------------------
                app.ui_mgr.show_character_select_modal()
                save_screen(app, "character_select")

                # ---------------------------------------------------------
                # Screen 2: Character Deletion Confirmation Modal
                # ---------------------------------------------------------
                app.ui_mgr._on_click_delete_character(c_same1.id)
                app.ui_mgr.char_delete_entry.set("정예대원")
                app.ui_mgr._update_delete_confirm_btn_state()
                save_screen(app, "character_delete_modal")

                # Close delete modal and character select modal
                app.ui_mgr.hide_character_delete_modal()
                app.ui_mgr.hide_character_select_modal()

                # Start game with active character
                app.start_game()
                assert app.game_state == "PLAYING"

                # Populate run loot bag with 24 items (full 24/24 bag)
                for i in range(16):
                    app.run_loot_bag.add_item(
                        create_item(catalog, "weapon_dual_pistol", rarity=rarities[i % 5], item_level=(i % 5) + 1)
                    )
                for _ in range(4):
                    app.run_loot_bag.add_item(create_item(catalog, "scrap_metal", quantity=5))
                for _ in range(4):
                    app.run_loot_bag.add_item(create_item(catalog, "bone_fragment", quantity=3))
                assert len(app.run_loot_bag.pending_items) == 24

                # Open inventory
                app.open_inventory()
                assert app.game_state == "INVENTORY"

                # ---------------------------------------------------------
                # Screen 3: Equipment UI (Stash & Selected Material Item)
                # ---------------------------------------------------------
                app.ui_mgr._switch_inventory_tab("equipment")
                # Select scrap_metal material to show usage guide and workshop redirect button
                app.ui_mgr.equipment_ui.selected_uid = scrap_free.uid
                app.ui_mgr.equipment_ui.refresh()
                save_screen(app, "equipment_ui")

                # ---------------------------------------------------------
                # Screen 4: Workshop UI (Upgrades & Stats Comparison)
                # ---------------------------------------------------------
                app.ui_mgr._switch_inventory_tab("workshop")
                app.ui_mgr.workshop_ui.selected_uid = primary_wpn.uid
                app.ui_mgr.workshop_ui.selected_recipe = "reinforce"
                app.ui_mgr.workshop_ui.refresh()
                save_screen(app, "workshop_ui")

                # ---------------------------------------------------------
                # Screen 5: Run Loot Bag UI (24/24 Full Capacity & Notice)
                # ---------------------------------------------------------
                app.ui_mgr._switch_inventory_tab("run_loot")
                # Select a material item in run bag to display "탈출로 확보 후 작업대에서 사용"
                mat_in_run = next(it for it in app.run_loot_bag.pending_items if it.definition_id == "bone_fragment")
                app.ui_mgr.run_loot_ui.selected_uid = mat_in_run.uid
                app.ui_mgr.run_loot_ui.refresh()
                save_screen(app, "run_loot_24")

            finally:
                app.destroy()

    return 0


def main():
    parser = argparse.ArgumentParser(description="Capture workshop and character UI previews.")
    parser.add_argument("--worker", action="store_true", help="Internal worker mode")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    if args.worker:
        return run_capture_worker(args.width, args.height)

    # Master orchestrator: run workers in independent processes for clean GPU pipeline contexts
    print("=== [UI PREVIEW CAPTURE ORCHESTRATOR] ===")
    py_exec = sys.executable

    # 1. 1600x900
    cmd_1600 = [py_exec, str(Path(__file__).resolve()), "--worker", "--width", "1600", "--height", "900"]
    ret1 = subprocess.run(cmd_1600).returncode
    assert ret1 == 0, "1600x900 capture failed"

    # 2. 1280x720
    cmd_720 = [py_exec, str(Path(__file__).resolve()), "--worker", "--width", "1280", "--height", "720"]
    ret2 = subprocess.run(cmd_720).returncode
    assert ret2 == 0, "1280x720 capture failed"

    print("\n=== All Multi-Resolution Captures Successfully Created! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

