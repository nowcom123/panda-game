"""Offscreen multi-resolution UI and reaction visual capture script for Quick-Use, Stats, and Monster Reactions."""

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
    from panda3d.core import Filename, PNMImage, loadPrcFileData, Vec3, Point3

    loadPrcFileData(
        "",
        f"window-type offscreen\n"
        f"win-size {width} {height}\n"
        f"audio-library-name null\n"
        f"sync-video false\n"
        f"model-path assets\n"
    )

    from game import LiminalInfiniteLoop
    loadPrcFileData("", f"win-size {width} {height}")
    from rpg.characters import CharacterManager
    from rpg.items import create_item, load_catalog

    out_dir = Path(__file__).resolve().parent
    catalog = load_catalog()
    res_str = f"{width}x{height}"
    print(f"\n=== Capturing {res_str} Previews ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Isolated character manager to preserve actual user saves
        char_mgr = CharacterManager(tmp_path, catalog)
        c_hero = char_mgr.create_character("대응전술요원")
        char_mgr.select_character(c_hero.id)

        app = LiminalInfiniteLoop(save_path=tmp_path / 'profile.json')
        try:
            # Overwrite character manager and save store with temp isolation
            app.ui_mgr.save_rank_record = lambda *a, **k: None
            app.character_mgr = char_mgr
            app._saved_rpg_session = None

            # 1. Start game in normal playing mode
            app.start_game()
            for _ in range(10):
                app.taskMgr.step()

            # Helper screenshot function
            def save_screen(filename_stem):
                for _ in range(6):
                    app.taskMgr.step()
                img_path = out_dir / f"{filename_stem}_{res_str}.png"
                pnm = PNMImage()
                app.win.getScreenshot(pnm)
                assert (pnm.getXSize(), pnm.getYSize()) == (width, height), (
                    f"Expected resolution {width}x{height}, got {pnm.getXSize()}x{pnm.getYSize()}"
                )
                pnm.write(Filename.fromOsSpecific(str(img_path)))
                assert img_path.is_file(), f"Screenshot failed: {img_path}"
                print(f"  [OK] Saved: {img_path.name} ({img_path.stat().st_size:,} bytes, {pnm.getXSize()}x{pnm.getYSize()})")

            # Setup player items and perks
            from player_controller import ITEM_CATALOG
            app.player.inventory = [
                dict(ITEM_CATALOG["medkit"], count=3),
                dict(ITEM_CATALOG["adrenaline"], count=2),
                dict(ITEM_CATALOG["combat_stim"], count=1),
                dict(ITEM_CATALOG["ammo_pack"], count=4),
                dict(ITEM_CATALOG["frag_grenade"], count=3),
            ]
            app.player.perk_levels = {
                "precision_training": 2,  # Evasion suppression: 10%p
                "guard_breaker": 3,       # Guard penetration: 30%
            }

            # --- Capture 1: Inventory UI with Counter Stats ---
            print("  Capturing Inventory UI with Evasion Suppression & Guard Penetration...")
            app.open_inventory()
            save_screen("inventory_stats")
            app.close_inventory()

            # --- Capture 2: Quick Use Radial/Card Panel (`) ---
            print("  Capturing Quick-Use Consumable Wheel/Panel...")
            app.quick_use_mgr.on_key_down()
            app.quick_use_mgr.selected_index = 0  # Select first card (Medkit)
            if app.quick_use_mgr.ui_panel:
                app.quick_use_mgr.ui_panel._update_highlight()
            save_screen("quick_use")
            app.quick_use_mgr.cancel()

            # --- Capture 3: Monster Reaction & Telegraph Visual ---
            print("  Capturing Monster Reaction & Guard Telegraph Visual...")
            from monster import LongBlackSerpent, AbominableMudOrc
            # Spawn serpent and mud orc in front of camera
            cam_pos = app.player.camera.getPos()
            cam_forward = app.player.camera.getQuat().getForward()

            serpent = LongBlackSerpent(
                app.render,
                cam_pos.x + cam_forward.x * 6.0,
                cam_pos.y + cam_forward.y * 6.0
            )
            serpent.game = app
            app.monsters.append(serpent)

            orc = AbominableMudOrc(
                app.render,
                cam_pos.x + cam_forward.x * 6.0 - 3.0,
                cam_pos.y + cam_forward.y * 6.0
            )
            orc.game = app
            app.monsters.append(orc)

            # Trigger guard on serpent (creates green fan telegraph) and orc (creates circle telegraph)
            serpent.trigger_guard(0.40, 6.0, app.player)
            orc.trigger_guard(0.60, 8.0, app.player)
            save_screen("monster_reaction")

        finally:
            app.destroy()

    return 0


def main():
    parser = argparse.ArgumentParser(description="Capture reaction and quick-use previews.")
    parser.add_argument("--worker", action="store_true", help="Internal worker mode")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    if args.worker:
        return run_capture_worker(args.width, args.height)

    print("=== [REACTION & QUICK-USE UI PREVIEW CAPTURE ORCHESTRATOR] ===")
    py_exec = sys.executable

    # 1. 1280x720
    cmd_720 = [py_exec, str(Path(__file__).resolve()), "--worker", "--width", "1280", "--height", "720"]
    ret1 = subprocess.run(cmd_720).returncode
    assert ret1 == 0, "1280x720 capture failed"

    # 2. 2294x1201
    cmd_hi = [py_exec, str(Path(__file__).resolve()), "--worker", "--width", "2294", "--height", "1201"]
    ret2 = subprocess.run(cmd_hi).returncode
    assert ret2 == 0, "2294x1201 capture failed"

    print("\n=== All Multi-Resolution Captures Successfully Created! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
