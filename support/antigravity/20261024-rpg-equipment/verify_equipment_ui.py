"""Offscreen UI verification and 1600x900 resolution capture for Equipment UI."""

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


def main() -> int:
    print("=== Running Offscreen Equipment UI & Resolution Verification (1600x900) ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        save_path = Path(tmp_dir) / "profile.json"

        # Initialize game with injected temporary save path (never touching user data)
        app = LiminalInfiniteLoop(save_path=save_path)
        out_dir = Path(__file__).resolve().parent
        img_path = out_dir / "equipment_ui_1600x900.png"

        try:
            # 1. Start game and open inventory
            app.start_game()
            assert app.game_state == "PLAYING", "Game state should be PLAYING"

            combat = app.combat
            combat.ammo = 2
            combat.reserve_ammo = 3
            combat.reset_state(keep_ammo=True)
            assert (combat.ammo, combat.reserve_ammo) == (2, 3)
            combat.reset_state(keep_ammo=False)
            assert combat.reserve_ammo == combat.get_current_weapon_config()['initial_reserve']
            old_secondary = combat.reserve_ammo_pools['SHOTGUN']
            combat.reserve_ammo += 10
            combat.switch_to_slot('secondary')
            assert combat.reserve_ammo == old_secondary + 5
            combat.switch_to_slot('primary')
            print('[OK] New-run reserves, keep_ammo and cross-weapon ammo pickups.')

            app.open_inventory()
            assert app.game_state == "INVENTORY", "Game state should be INVENTORY"

            # 2. Switch to equipment tab
            app.ui_mgr._switch_inventory_tab("equipment")
            assert app.ui_mgr.active_inventory_tab == "equipment"
            assert all(w.isHidden() for w in app.ui_mgr.consumables_widgets)
            panel = app.ui_mgr.equipment_ui
            assert '재료 수량' not in panel.txt_detail_affixes.getText()
            saved = save_path.read_bytes()
            app.is_test_mode = True
            panel._on_click_lock_toggle()
            panel._on_click_unequip()
            assert save_path.read_bytes() == saved
            app.is_test_mode = False
            print('[OK] Consumable panel hidden and test mode cannot edit permanent gear.')
            print("[OK] Switched to equipment tab.")

            # 3. Step task manager and render frames
            for _ in range(5):
                app.taskMgr.step()

            image = PNMImage()
            captured = app.win.getScreenshot(image)
            assert captured, "Failed to capture screenshot"
            image.write(Filename.fromOsSpecific(str(img_path)))
            assert img_path.is_file(), f"Screenshot was not written: {img_path}"
            print(f"[OK] Captured 1600x900 Equipment UI preview: {img_path} ({img_path.stat().st_size} bytes)")

            # 4. Verify ESC/TAB closing
            app.handle_escape()
            assert app.game_state == "PLAYING", "ESC should close inventory and return to PLAYING"
            assert not app.ui_mgr.is_inventory_open(), "Inventory modal should be hidden"
            print("[OK] ESC / TAB closing verified.")

        finally:
            app.destroy()

    print("=== Offscreen Equipment UI Verification Passed! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
