"""Offscreen checks of real perk cards, upgrade selection and firing cadence."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from panda3d.core import loadPrcFileData, Filename
loadPrcFileData('', 'window-type offscreen\nwin-size 1600 900\naudio-library-name null\nsync-video false')
from game import LiminalInfiniteLoop
from perks import PERK_CATALOG, describe_perk
from combat_system import WEAPON_CONFIGS
app = LiminalInfiniteLoop()
try:
    p, ui = app.player, app.ui_mgr
    app.game_state = 'SHOP'
    ids = ['vampiric_leech', 'speed_demon', 'titan_armor']
    for pid in ids:
        p.add_perk(pid, app.combat)
    offers = [PERK_CATALOG[pid] for pid in ids]
    with patch('ui_manager.draw_random_perks', return_value=offers):
        ui.show_levelup_perk_modal(2, p, app.combat, lambda: None)
    for card, pid in zip(ui.perk_cards, ids):
        assert describe_perk(pid, 2) in card['desc'].getText()
    app.render.setShaderInput('camera_world_position', app.camera.getPos(app.render))
    for _ in range(3):
        app.graphicsEngine.renderFrame()
    dest = Path(__file__).with_name('perk_upgrade_cards.png')
    app.win.saveScreenshot(Filename.fromOsSpecific(str(dest)))
    ui._select_perk_card(0)
    ui._select_perk_card(0)
    assert p.perk_levels[ids[0]] == 2
    with patch('ui_manager.draw_random_perks', return_value=offers):
        ui.show_stage_clear_shop(1, p, app.combat, lambda: None)
    assert describe_perk(ids[0], 3) in ui.perk_cards[0]['desc'].getText()
    ui._select_perk_card(0)
    assert p.perk_levels[ids[0]] == 3
    combat = app.combat
    for level in range(1, 4):
        p.add_perk('bullet_storm', combat)
        combat.bullet_storm_timer = 2.0
        combat.shoot_cooldown = 0.0
        combat.combo_count = 0
        ammo_before = combat.ammo
        with patch.object(combat, '_perform_raycast', return_value=(False, False, False)):
            combat.shoot([], player=p)
        expected = WEAPON_CONFIGS[combat.current_weapon]['cooldown'] / (1 + (1/.65 - 1)*level)
        assert abs(combat.shoot_cooldown - expected) < 1e-8
        assert combat.ammo == ammo_before
    print('PASS real UI: upgrade descriptions, duplicate-input guard, next-offer upgrade; real shoot: L1-L3 cooldown and free ammo.')
finally:
    app.destroy()
