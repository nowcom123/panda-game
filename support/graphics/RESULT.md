# Rounded model update - 2026-10-20

Added shared 16-sided cylinder and 16 x 8 sphere meshes with normals/UVs.
Existing dimensions, model parents, colors and animation pivots are preserved.

- Weapons: barrels/muzzles, shell casings, flashlight bodies/lenses, shotgun
  magazine tube and pump, sleeve/cuff cross sections, muzzle flash and smoke.
- World props: cylindrical hazard drums/bands, rounded beacon bulb.
- Projectiles: grenade body/cap, fireballs, explosion cores/dust/smoke and
  circular shockwave disc.
- Monsters: craniums, eye sockets/eyes, bone joints, selected limb shafts,
  witch orb and boss/hound cores. Armor, walls and structural panels stay angular.
- No damage, pathfinding, collision, dodge chance or movement balance changes.

Validation: 20 unit tests pass, including outward triangle winding and shape
bounds. All six monster constructors and selected animation updates ran in the
Panda3D offscreen renderer. Actual updated objects and weapon models were
rendered and visually inspected in round_objects.png / round_weapons.png.
Regenerate these previews with python support/graphics/render_round_preview.py.

Antigravity collaboration was attempted through the computer-use plugin.
Both app/window discovery calls failed with native pipe unavailable (OS error 2).
No task was delivered to Antigravity this turn; implementation and verification
were completed by Codex. The antigravity command is also absent from PATH.
