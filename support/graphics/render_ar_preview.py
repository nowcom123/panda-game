"""Render the production AR viewmodel in hip-fire and iron-sight positions."""
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from panda3d.core import AmbientLight, DirectionalLight, Filename, Vec3, loadPrcFileData
loadPrcFileData('', 'window-type offscreen\nwin-size 1200 750\naudio-library-name null\nsync-video false')
from direct.showbase.ShowBase import ShowBase
from combat_system import CombatSystem

base = ShowBase()
try:
    base.setBackgroundColor(.38, .40, .43)
    base.camLens.setNearFar(.01, 100)
    ambient = AmbientLight('preview_ambient')
    ambient.setColor((.55, .55, .58, 1))
    base.render.setLight(base.render.attachNewNode(ambient))
    key = DirectionalLight('preview_key')
    key.setColor((.9, .85, .75, 1))
    light = base.render.attachNewNode(key)
    light.setHpr(-35, -45, 0)
    base.render.setLight(light)
    combat = CombatSystem(base, base.render, base.camera, base.render, None, Mock())
    combat.current_weapon = 'AR'
    combat._update_viewmodel_visibility()
    out = Path(__file__).resolve().parent
    for name, position, hpr, fov in (
        ('ar_hip', combat.ads_hip_pos_ar, Vec3(1.2, .6, -.6), 96),
        ('ar_ads', combat.ads_aim_pos_ar, Vec3(0), 80),
    ):
        combat.vm_ar.setPos(position)
        combat.vm_ar.setHpr(hpr)
        base.camLens.setFov(fov)
        if name == 'ar_ads':
            tip = base.camera.getRelativePoint(combat.ar_front_sight, Vec3(0, 0, .125))
            assert abs(tip.x) < 1e-6 and abs(tip.z) < 1e-6, tip
        for _ in range(3):
            base.graphicsEngine.renderFrame()
        base.win.saveScreenshot(Filename.fromOsSpecific(str(out / f'{name}.png')))
    print('PASS: AR hip/ADS rendered; front sight tip aligned with camera center.')
finally:
    base.destroy()
