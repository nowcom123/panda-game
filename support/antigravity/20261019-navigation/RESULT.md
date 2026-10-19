# Monster Wall / Pillar Navigation Fix Report

## 1. Root Cause
1. **Doorway Waypoint Premature Pop & Rebound Oscillation (`game.py`)**:
   Cell boundary waypoints popped at `hypot < 0.75m` before the monster crossed the cell boundary into `c2`. On the very next frame, the monster's grid cell was still `c1`, but `path[0]` had become `c2`, triggering `needs_repath = True`. This caused the path to regenerate starting back at `c1`, pulling the target backwards to the previous doorway and locking the monster in an oscillation loop.
2. **Same-Cell Pillar Bypass Absence (`game.py`)**:
   `in_same_cell` activated unconditional straight-line charge towards the player, ignoring central pillars inside the 6m x 6m cell and wedging the monster directly into pillar faces.
3. **Corner Sticking & Lack of Body Radius Clearance (`collision.py`, `world_gen.py`)**:
   `resolve_collision` only pushed radially away from closest AABB vertices without tangential sliding projection, arresting corner velocity. `check_line_of_sight` evaluated zero-width rays, causing monsters to attempt direct charges through corner clearances narrower than their body radius (`col_radius`).
4. **Pillar Unstuck Bug (`game.py`)**:
   Active unstuck pushed towards `(mgx + 0.5) * CELL_SIZE`, which in pillar cells drove stuck monsters directly into the pillar center.

## 2. Minimal Changes Made
- `game.py`:
  - **Fixed doorway waypoint pop**: Cell boundary doorways now only pop when the monster actually crosses the threshold (`(m_pos - boundary) * dir >= 0.05`), preventing premature pop and rebound repaths.
  - **Added same-cell pillar bypass**: When player and monster share a pillar cell with no direct clearance LOS, 4 quadrant bypass waypoints route safely around the pillar.
  - **Integrated radius clearance**: `col_radius` scales pillar bypass offsets (`max(1.5, 0.6 + col_radius + 0.5)`) and line-of-sight checks.
  - **Repulsion unstuck**: Pushes outward from pillar centers and along collider surface normals.
- `collision.py`:
  - Added corner tangential deflection (`eff_dx -= dot * nx`, `eff_dy -= dot * ny`) and initial penetration recovery for seamless sliding around convex corners.
- `world_gen.py`:
  - Added `radius` clearance parameter to `check_line_of_sight` via Minkowski-expanded AABBs.
- `monster.py`:
  - Added explicit `col_radius` to monster classes (Hound: 0.35, Serpent/Witch: 0.38, Skeleton: 0.40, Orc: 0.45, Boss: 0.55).
- `tests/test_navigation_regression.py`:
  - Dedicated regression test suite covering same-cell bypass, doorway premature pop prevention, corner deflection sliding, radius clearance, and anti-tunneling.

*(Note: Audio files, combat system, generate_audio, rankings.json, and git commits were strictly untouched.)*

## 3. Validation Command & Results
- **Command**:
  ```powershell
  & "C:/Users/nowco/AppData/Local/Programs/Python/Python310/python.exe" -c "import sys; sys.path.insert(0, '.'); sys.path.insert(0, './tests'); import test_navigation_regression, unittest; suite = unittest.defaultTestLoader.loadTestsFromModule(test_navigation_regression); runner = unittest.TextTestRunner(verbosity=2); res = runner.run(suite); sys.exit(0 if res.wasSuccessful() else 1)"
  ```
- **Results**:
  ```
  test_boundary_containment_and_anti_tunneling ... ok
  test_doorway_waypoint_no_premature_pop_and_no_rebound ... ok
  test_hound_dodge_collision_consistency ... ok
  test_line_of_sight_radius_clearance ... ok
  test_pillar_corner_tangential_sliding ... ok
  test_pillar_corridor_forward_progress_no_oscillation ... ok
  test_radius_aware_pillar_clearance_routing ... ok
  test_same_cell_pillar_avoidance_waypoint ... ok
  test_unstuck_repulsion_pushes_away_from_pillar ... ok
  test_unstuck_repulsion_pushes_away_from_walls ... ok

  Ran 10 tests in 0.001s
  OK
  ```
- Syntax check passed: `python -m py_compile game.py collision.py world_gen.py monster.py tests/test_navigation_regression.py` (exit code 0).

## 4. Limitations
- Pathfinding remains cell-grid BFS with local continuous obstacle deflection. Very complex concatenated pillar clusters would require multi-node local sub-graphs if introduced in future designs.
