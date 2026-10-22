"""Render the production boss HUD and check its anchored animated geometry."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from panda3d.core import loadPrcFileData, Filename, Point3
loadPrcFileData('', 'window-type offscreen\nwin-size 1400 850\naudio-library-name null\nsync-video false')
from direct.showbase.ShowBase import ShowBase
from ui_manager import UIManager

base = ShowBase()
try:
    base.setBackgroundColor(.05, .06, .08)
    ui = UIManager(base, base.loader, lambda: None, lambda: None, lambda: None)
    for child in base.aspect2d.getChildren():
        child.hide()
    base.boss = SimpleNamespace(hp=3500, max_hp=3500, phase=1)
    ui.show_boss_hp_bar('골해의 지배자', 3500, 3500)
    left_before = ui.boss_hud_frame.getRelativePoint(ui.boss_bar_fill, Point3(0, 0, 0))
    base.boss.hp = 1400
    for _ in range(9):
        ui._animate_boss_hp(1/60)
    assert .4 < ui.boss_bar_fill.getSx() < 1
    left_after = ui.boss_hud_frame.getRelativePoint(ui.boss_bar_fill, Point3(0, 0, 0))
    assert (left_after-left_before).length() < 1e-6
    for _ in range(3):
        base.graphicsEngine.renderFrame()
    base.win.saveScreenshot(Filename.fromOsSpecific(str(Path(__file__).with_name('boss_hp_mid_animation.png'))))
    for _ in range(90):
        ui._animate_boss_hp(1/60)
    assert abs(ui.boss_bar_fill.getSx() - .4) < 1e-5
    print('PASS: real HUD interpolates damage, preserves left edge and settles at actual HP.')
finally:
    base.destroy()
