# Panda-game navigation repair (Codex + Antigravity collaboration)

The user explicitly requested collaboration with Antigravity to reduce Codex usage.
Implement the monster wall/pillar sticking fix in this shared working tree.
Codex owns audio work in parallel; do not modify audio_system.py, combat_system.py,
generate_audio.py or assets/audio. Do not touch rankings.json or revert existing changes.

## Request

All monsters can get stuck against walls and pillars while pursuing the player.
The screenshot shows a skeletal hound by a pillar corner. Find and fix the root
cause for all monster types, not just a teleport workaround. Preserve wall collision,
abilities and reasonable per-frame cost. No broad gameplay redesign.

## Starting points

- game.py around 1730-1950: pursuit, cell path following, near-player direct movement,
  path_timer, col_radius, angled fallback, _stuck_timer.
- world_gen.py: find_cell_path (around 235), check_line_of_sight (around 270), pillars.
- collision.py: get_nearby_colliders, resolve_collision (around 54).
- monster.py: abilities such as hound dodge use resolve_collision.

Inspect actual collision geometry, waypoint changes at cell boundaries, clearance
for monster radius, obstacle penetration recovery, diagonal corners and time steps.
Add focused automated regression coverage that reproduces and verifies the fix,
including a pillar/corner chase, boundaries, and prevention of wall tunneling.
Run it. Avoid expensive whole-project rewrites and repeated large output.

## Delivery

Edit files directly here, no commit/push. Codex will review and integrate.
Write support/antigravity/20261019-navigation/RESULT.md when finished, including
root cause, modified files, validation command/results and limitations.
Keep that result concise. If blocked, put the precise blocker there.

The system Python (C:/Users/nowco/AppData/Local/Programs/Python/Python310/python.exe)
already has Panda3D, numpy and scipy; a recently created .venv may not.
