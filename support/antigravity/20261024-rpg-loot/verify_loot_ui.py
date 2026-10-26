"""Offscreen UI verification and 1600x900 resolution capture for In-run Loot UI."""

import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from direct.gui.DirectGui import DGG
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
from rpg import ItemAffix, create_item, load_catalog


def main() -> int:
    print("=== Running Offscreen Loot UI & Resolution Verification (1600x900) ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        save_path = Path(tmp_dir) / "profile.json"

        # Initialize game with injected temporary save path (never touching user data)
        app = LiminalInfiniteLoop(save_path=save_path)
        out_dir = Path(__file__).resolve().parent
        img_path = out_dir / "loot_ui_1600x900.png"

        try:
            # 1. Start game
            app.start_game()
            assert app.game_state == "PLAYING", "Game state should be PLAYING"

            # 2. Add sample in-run loot to the pending bag for visual inspection
            catalog = load_catalog()
            rare_ar = create_item(
                catalog,
                "weapon_ar",
                rarity="rare",
                item_level=1,
                quantity=1,
                affixes=[
                    ItemAffix(id="damage_mult", value=1.145),
                    ItemAffix(id="reload_time_mult", value=0.880),
                ],
            )
            epic_shotgun = create_item(
                catalog,
                "weapon_shotgun",
                rarity="epic",
                item_level=1,
                quantity=1,
                affixes=[
                    ItemAffix(id="damage_mult", value=1.185),
                    ItemAffix(id="weakpoint_mult", value=1.220),
                    ItemAffix(id="reload_time_mult", value=0.865),
                ],
            )
            scrap = create_item(catalog, "scrap_metal", quantity=5, item_level=1)

            app.run_loot_bag.add_item(rare_ar, session=app.rpg_session)
            app.run_loot_bag.add_item(epic_shotgun, session=app.rpg_session)
            app.run_loot_bag.add_item(scrap, session=app.rpg_session)
            assert app.run_loot_bag.count == 3

            # Update HUD
            app.ui_mgr.update_run_loot_hud(app.run_loot_bag.count, app.run_loot_bag.capacity)
            assert "3 / 24" in app.ui_mgr.loot_hud_text.getText()
            print("[OK] In-run bag populated and HUD text verified.")

            # 3. Open inventory and switch to 3rd tab: 'run_loot'
            app.open_inventory()
            assert app.game_state == "INVENTORY", "Game state should be INVENTORY"

            app.ui_mgr._switch_inventory_tab("run_loot")
            assert app.ui_mgr.active_inventory_tab == "run_loot"

            # Verify widget visibility separation (no overlapping panels)
            assert all(w.isHidden() for w in app.ui_mgr.consumables_widgets), "Consumables widgets must be hidden"
            assert app.ui_mgr.equipment_ui.frame.isHidden(), "Equipment UI must be hidden"
            assert not app.ui_mgr.run_loot_ui.frame.isHidden(), "Run Loot UI must be visible"

            # Verify panel contents
            panel = app.ui_mgr.run_loot_ui
            assert "3 / 24" in panel.lbl_bag_status.getText()
            assert panel.btn_equip_disabled["state"] == DGG.DISABLED
            print("[OK] 3-way inventory tab isolation verified (no widget overlap).")

            # 4. Render frames and capture 1600x900 screenshot
            for _ in range(5):
                app.taskMgr.step()

            image = PNMImage()
            captured = app.win.getScreenshot(image)
            assert captured, "Failed to capture screenshot"
            image.write(Filename.fromOsSpecific(str(img_path)))
            assert img_path.is_file(), f"Screenshot was not written: {img_path}"
            print(f"[OK] Captured 1600x900 In-Run Loot UI preview: {img_path} ({img_path.stat().st_size} bytes)")

            # 5. Verify tab switching back to consumables and equipment
            app.ui_mgr._switch_inventory_tab("consumables")
            assert panel.frame.isHidden(), "Run loot UI must be hidden on consumables tab"
            app.ui_mgr._switch_inventory_tab("equipment")
            assert panel.frame.isHidden(), "Run loot UI must be hidden on equipment tab"
            print("[OK] Tab return transitions verified.")
            # Real director hook: elite once, airborne boss drops on the floor.
            with patch.object(app.monster_director.gate_wave_mgr, 'update'):
                target = app.monsters[0]
                target.is_elite = True
                target.hp = 0
                before = len(app.loot_world.world_items)
                app.monster_director.update_monsters(0, app.camera.getX(), app.camera.getY())
                assert len(app.loot_world.world_items) == before + 1
                app.monster_director.update_monsters(0, app.camera.getX(), app.camera.getY())
                assert len(app.loot_world.world_items) == before + 1
                boss = app.spawn_boss(8, 8)
                boss.pos.z = 4
                boss.hp = 0
                app.monster_director.update_monsters(0, app.camera.getX(), app.camera.getY())
                assert len(app.loot_world.world_items) == before + 3
                assert all(item.base_z < 1 for item in app.loot_world.world_items[-2:])
            print('[OK] Production elite/boss death hooks drop once and airborne loot lands on floor.')

            # 6. Verify stage clear shop shows escape option with loot count
            app.handle_escape()  # close inventory
            app.ui_mgr.show_stage_clear_shop(
                stage=1,
                player=app.player,
                combat=app.combat,
                on_confirm_callback=lambda: None,
                on_victory_callback=app.trigger_victory,
            )
            assert not app.ui_mgr.btn_escape_victory.isHidden(), "Escape button must be visible"
            assert "3개" in app.ui_mgr.btn_escape_victory["text"] or "3" in app.ui_mgr.shop_desc.getText()
            print("[OK] Stage clear shop escape option and loot status verified.")
            owned = len(app.rpg_session.profile.items)
            with patch.object(app.ui_mgr, 'save_rank_record') as ranking:
                with patch.object(app.rpg_session.store, 'save', side_effect=OSError('disk failure')):
                    app.trigger_victory()
                    assert app.game_state == 'EXTRACTION_FAILED'
                    assert app.run_loot_bag.count == 3
                    for action in (app.handle_escape, app.return_to_intro, app.restart_game,
                                   app.advance_to_next_stage, app.trigger_game_over, app.start_test_mode):
                        action()
                        assert app.game_state == 'EXTRACTION_FAILED'
                        assert app.run_loot_bag.count == 3
                    app.update(None)
                    assert len(app.rpg_session.profile.items) == owned
                    ranking.assert_not_called()
                app.ui_mgr._on_click_extract_retry()
                assert app.game_won and app.run_loot_bag.count == 0
                assert len(app.rpg_session.profile.items) == owned + 3
                assert len(app.rpg_session.store.load().profile.items) == owned + 3
                app.trigger_victory()
                ranking.assert_called_once()
            print('[OK] Real game save failure freezes run, retry persists once, duplicate victory is harmless.')

            app.ui_mgr.hide_stage_clear_shop()

        finally:
            app.destroy()

    print("=== Offscreen Loot UI Verification Passed! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

