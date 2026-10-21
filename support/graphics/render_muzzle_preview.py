"""Check real shooting and render muzzle flames for every weapon, hip and ADS."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from panda3d.core import AmbientLight, DirectionalLight, Filename, Vec3, loadPrcFileData
loadPrcFileData('', 'window-type offscreen\nwin-size 1200 750\naudio-library-name null\nsync-video false')
from direct.showbase.ShowBase import ShowBase
from combat_system import CombatSystem

base = ShowBase()
try:
    base.setBackgroundColor(.38, .40, .43)
    base.camLens.setNearFar(.01, 100)
    base.camera.setZ(1.7)
    ambient = AmbientLight('preview_ambient')
    ambient.setColor((.55, .55, .58, 1))
    base.render.setLight(base.render.attachNewNode(ambient))
    key = DirectionalLight('preview_key')
    key.setColor((.9, .85, .75, 1))
    light = base.render.attachNewNode(key)
    light.setHpr(-35, -45, 0)
    base.render.setLight(light)
    combat = CombatSystem(base, base.render, base.camera, base.render, None, Mock())
    out = Path(__file__).resolve().parent
    setups = (
        ('PISTOL', combat.vm_pistol, combat.ads_hip_pos, combat.ads_aim_pos, combat.muzzle_flash_geom),
        ('DUAL_PISTOL', combat.vm_dual_right, combat.ads_hip_pos_dual_r, combat.ads_aim_pos_dual_r, combat.dual_right_flash_geom),
        ('AR', combat.vm_ar, combat.ads_hip_pos_ar, combat.ads_aim_pos_ar, combat.ar_muzzle_flash_geom),
        ('SHOTGUN', combat.vm_shotgun, combat.ads_hip_pos_sg, combat.ads_aim_pos_sg, combat.sg_muzzle_flash_geom),
    )
    for weapon, model, hip, aim, flash in setups:
        combat.switch_weapon(weapon)
        combat.switch_timer = 0
        for ads, position in ((0, hip), (1, aim)):
            combat.casing_effects.clear()
            model.setPos(position)
            model.setHpr(0, 0, 0)
            base.camLens.setFov(80 if ads else 96)
            combat.ads_alpha = ads
            combat.dual_hand_toggle = 0
            combat.shoot_cooldown = 0
            with patch.object(combat, '_perform_raycast', return_value=(False, False, False)):
                combat.shoot([])
            assert not flash.isHidden(), weapon
            assert sum(not v.isHidden() for v in flash.getChildren()) == 1
            low, high = flash.getTightBounds(combat.vm_root)
            assert high.x-low.x < .15 and high.z-low.z < .15, (weapon, low, high)
            assert combat.muzzle_timer <= .035
            combat.casing_effects.update(.025)
            for _ in range(3):
                base.graphicsEngine.renderFrame()
            base.win.saveScreenshot(Filename.fromOsSpecific(str(out / f'flash_{weapon.lower()}_{ads}.png')))
            combat.update(.04)
            assert flash.isHidden(), weapon
    print('PASS: all four weapons fired hip/ADS; narrow bounds, one flame variant, short lifetime and cleanup verified.')

finally:
    base.destroy()
