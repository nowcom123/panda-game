"""Exercise real game shooting, shotgun pump timing, reset and shutdown."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen\nwin-size 1600 900\naudio-library-name null\nsync-video false')
from game import LiminalInfiniteLoop

app = LiminalInfiniteLoop()
effects = app.combat.casing_effects
try:
    combat = app.combat
    app.player.reset_position(0, 0)
    app.game_state = 'SHOP'  # No game-loop/world spawning while verifying effects.
    app.render.setShaderInput('camera_world_position', app.camera.getPos(app.render))
    for weapon in ('PISTOL', 'DUAL_PISTOL', 'AR', 'SHOTGUN'):
        combat.switch_weapon(weapon)
        for ads in (False, True):
            effects.clear()
            combat.is_aiming = ads
            combat.ads_alpha = int(ads)
            combat.switch_timer = 0
            combat.update(.01)
            combat.shoot_cooldown = 0
            combat.dual_hand_toggle = 0
            with patch.object(combat, '_perform_raycast', return_value=(False, False, False)):
                combat.shoot([], player=app.player)
            assert effects.active_count == (0 if weapon == 'SHOTGUN' else 1)
            if weapon == 'SHOTGUN':
                combat.update(.10)
                assert effects.active_count == 0, 'Shotgun ejected before pump extraction'
                combat.update(.06)
                assert effects.active_count == 1
                combat.update(.28)
                assert effects.active_count == 1, 'Shotgun ejected twice'
            elif weapon == 'DUAL_PISTOL':
                combat.shoot_cooldown = 0
                with patch.object(combat, '_perform_raycast', return_value=(False, False, False)):
                    combat.shoot([], player=app.player)
                assert effects.active_count == 2
            active = [c for c in effects.pool if c['active']]
            assert all(c['current_weapon'] == weapon for c in active)
            for casing in active:
                # Bounds in local slot coordinates include the actual meshes,
                # independent of perspective or a rotating world transform.
                mesh = casing['meshes'][weapon]
                lo, hi = mesh.getTightBounds(mesh)
                assert max(hi.x-lo.x, hi.y-lo.y, hi.z-lo.z) < .05
            effects.update(1.0)
            assert effects.active_count == 0
    combat._eject_casing(is_shotgun=True)
    assert effects.active_count == 1
    combat.reset_state(keep_ammo=True)
    assert effects.active_count == 0 and effects.cursor == 0
    assert all(c['node'].isHidden() for c in effects.pool)
    print('PASS: four weapons hip/ADS, both hands, delayed single shotgun ejection, dimensions, expiration and reset.')
finally:
    app.destroy()
assert not effects.pool
print('PASS: game shutdown destroys the casing pool.')
