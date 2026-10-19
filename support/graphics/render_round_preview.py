"""Render the actual updated models offscreen for visual review."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock
from panda3d.core import loadPrcFileData, AmbientLight, DirectionalLight, OrthographicLens, Filename, Vec3
loadPrcFileData('', 'window-type offscreen\nwin-size 1400 850\naudio-library-name null\nsync-video false')
from direct.showbase.ShowBase import ShowBase
from geometry import make_cube_to
from interactive_objects import HazardBarrel
from monster import (SkeletalDobermanHellhound, AbominableMudOrc, LongBlackSerpent,
                     TallSkeletonMonster, AlluringAshWitch, CableOverlordBoss)
from projectiles import FragGrenade, Fireball, ExplosionVisualEffect
from combat_system import CombatSystem
base = ShowBase()
base.setBackgroundColor(.12, .14, .18)
ambient = AmbientLight('preview_ambient'); ambient.setColor((.55, .55, .58, 1))
base.render.setLight(base.render.attachNewNode(ambient))
key = DirectionalLight('preview_key'); key.setColor((.9, .85, .75, 1))
key_np = base.render.attachNewNode(key); key_np.setHpr(-35, -45, 0); base.render.setLight(key_np)
scene = base.render.attachNewNode('preview_scene')
barrel = HazardBarrel(scene, -2, 0, None)
hound = SkeletalDobermanHellhound(scene, 0, 0); hound.node.setH(155)
orc = AbominableMudOrc(scene, 2, 0); orc.node.setH(165)
# Construct every monster once to catch model/animation compatibility errors.
for cls in (LongBlackSerpent, TallSkeletonMonster, AlluringAshWitch, CableOverlordBoss):
    model = cls(scene, 20, 20); model.update(1/60, False); model.node.hide()
grenade = FragGrenade(scene, Vec3(-1, -1, .4), Vec3(0, 1, 0), None); grenade.node.setScale(3)
fireball = Fireball(scene); fireball.activate(Vec3(1, -1, .6), (1, 0, .6)); fireball.node.setScale(2)
make_cube_to(scene, 12, 6, .1, (.22, .24, .28, 1), 0, 0, -.08)
lens = OrthographicLens(); lens.setFilmSize(8, 8*850/1400); base.cam.node().setLens(lens)
base.camera.setPos(6, -11, 6); base.camera.lookAt(0, 0, 1)
out = Path(__file__).resolve().parent
for _ in range(3): base.graphicsEngine.renderFrame()
base.win.saveScreenshot(Filename.fromOsSpecific(str(out/'round_objects.png')))
scene.hide()
combat = CombatSystem(base, base.render, base.camera, base.render, None, Mock())
combat.vm_root.detachNode()
weapons = base.render.attachNewNode('weapon_preview')
for model, pos, scale in ((combat.vm_pistol, (-2, 0, 0), 6), (combat.vm_shotgun, (1, 0, 0), 4)):
    model.reparentTo(weapons); model.show(); model.setPos(*pos); model.setHpr(130, 0, 0); model.setScale(scale)
base.camera.setPos(5, -10, 6); base.camera.lookAt(0, 0, -.2)
for _ in range(3): base.graphicsEngine.renderFrame()
base.win.saveScreenshot(Filename.fromOsSpecific(str(out/'round_weapons.png')))
print('Rendered round_objects.png and round_weapons.png; all six monster constructors passed.')
base.destroy()
