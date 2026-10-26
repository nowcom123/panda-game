"""Exercise actual inventory callbacks with isolated saves and render the results."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from panda3d.core import loadPrcFileData, Filename, PNMImage
from game import LiminalInfiniteLoop
from ui_manager import CURSED_RELICS
from player_controller import ITEM_CATALOG

width, height = map(int, sys.argv[1:3]) if len(sys.argv) > 2 else (1280, 720)
loadPrcFileData('', f'window-type offscreen\nwin-size {width} {height}\naudio-library-name null\nsync-video false')


def verify():
    with tempfile.TemporaryDirectory() as temp:
        app = LiminalInfiniteLoop(save_path=Path(temp) / 'profile.json')
        try:
            app.ui_mgr.save_rank_record = lambda *a, **k: None
            app.start_game()
            for item_id in ITEM_CATALOG:
                app.player.add_item(item_id)
            app.open_inventory()
            ui = app.ui_mgr

            def capture(name):
                for _ in range(3):
                    app.taskMgr.step()
                picture = PNMImage()
                app.win.getScreenshot(picture)
                assert (picture.getXSize(), picture.getYSize()) == (width, height)
                picture.write(Filename.fromOsSpecific(str(Path(__file__).parent / f'{name}_{width}x{height}.png')))

            def assert_consumables_hidden():
                assert ui.consumables_root.isHidden()
                assert ui.inv_detail_icon.isHidden()
                assert all(widget.isHidden() for widget in ui.consumables_widgets)

            ui._switch_inventory_tab('equipment')
            panel = ui.equipment_ui
            rifle = next(it for it in app.rpg_session.profile.items.values() if it.definition_id == 'weapon_ar')
            panel.selected_uid = rifle.uid
            panel._on_click_equip('secondary')
            assert app.rpg_session.profile.equipment['secondary'] == rifle.uid
            assert_consumables_hidden()
            capture('after_equip')
            panel.target_slot = 'secondary'
            panel._on_click_unequip()
            assert_consumables_hidden()
            panel._on_click_lock_toggle()
            assert_consumables_hidden()
            panel._on_click_lock_toggle()

            for tab in ('workshop', 'run_loot', 'equipment'):
                ui._switch_inventory_tab(tab)
                ui._on_equipment_changed()
                assert_consumables_hidden()

            ui._switch_inventory_tab('consumables')
            assert not ui.consumables_root.isHidden()
            app.player.relics = list(CURSED_RELICS)[:4]
            for index in range(len(app.player.inventory)):
                ui._select_inventory_slot(index)
                assert not ui.inv_detail_icon.isHidden()
                capture(f'consumable_{index}')
            ui._select_inventory_slot(5)
            assert ui.inv_detail_icon.isHidden()
            capture('empty_slot')

            # The long adrenaline description must remain above the use button.
            ui._select_inventory_slot(1)
            low, high = ui.inv_detail_desc.getTightBounds(ui.consumables_root)
            assert low.z > -.38, (low, high)
            ui._select_inventory_slot(0)
            app.player.hp = 50
            before = app.player.get_item_count('medkit')
            ui._on_click_use_inventory_item()
            assert app.player.get_item_count('medkit') == before - 1
            assert not ui.inv_detail_icon.isHidden()
            print('PASS: equip, unequip, lock, background refresh, five consumables, empty slot and layout', width, height)
        finally:
            app.destroy()


if __name__ == '__main__':
    verify()
