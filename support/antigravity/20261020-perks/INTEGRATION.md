# Perk upgrade integration — 2026-10-21

Antigravity implemented combat/projectile scaling and card/HUD level displays.
Codex implemented shared perk statistics, repeatable offers, player upgrades,
regression coverage, and final integration review.

All 12 perks now gain a level on each legitimate repeat pick, with effects driven
by the same statistics used in card descriptions. Both selection screens show
current-to-next levels; HUD badges show the owned level. A single offer grants
only one pick even when selection keys repeat.

Final review removed an unnecessary missing-ammo fallback and preserved the
explicit player argument in bullet-storm shooting.

Validation on final code:
- `python -m unittest discover -s tests`: 56 tests passed.
- `python support/antigravity/20261020-perks/verify_ui.py`: passed using real
  Panda3D game/UI objects in an offscreen window. Checked L2/L3 upgrade cards,
  duplicate-input prevention, and L1–L3 bullet-storm firing intervals/free ammo.
- Visually inspected `perk_upgrade_cards.png`: Korean text, level progression,
  numerical descriptions, and buttons fit the cards.
- `git diff --check`: passed.

The offscreen harness supplies the camera shader input normally supplied during
the game update. No claim of a full manual playthrough or FPS benchmark is made.
Existing flat-world edits and user ranking data were preserved. No commit/push.
