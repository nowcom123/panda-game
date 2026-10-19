# Required integration corrections

Codex reviewed your result. The audio tests and game initialization pass. The
navigation tests currently mirror expressions instead of exercising the real
steering loop, so they miss these remaining defects. Fix these before marking done.

1. **Interior-wall tunneling reproducible**: fake chunk with cell_colliders
   {(0,0): [(2.9,0,3.1,6)]}, resolve_collision(chunks,1,3,4,0,radius=.4)
   returns (5,3), crossing the wall. Add bounded movement substeps (radius/2 or
   smaller) around a single collider query, or swept-circle collision. Keep cost
   bounded sensibly for game speeds. Test both axes, diagonal and real wall gaps.

2. **Boundary target stalls**: targeting exactly boundary_x/boundary_y leaves
   d <= .05 before the grid cell changes, so the monster idles. Example westbound
   x=6.03 towards x=6.0, or eastbound x=5.98 towards x=6.0. Target a point at least
   radius+0.1 INSIDE the destination cell, while popping only on actual cell entry.
   Test all four directions at multiple frame rates by iterating production code.

3. **Same-cell pillar corner selection loops**: choosing a reachable corner by
   distance-to-player doesn't establish a route past the pillar. Near that corner
   the code switches back to the still-blocked player. Use a small visibility graph
   over four radius-expanded pillar corners + current point + goal (or equivalent
   persistent two-corner route). Validate every segment with FULL body clearance,
   not radius*.8; don't revert to a blocked straight target on arrival. Also apply
   safe local corner routing to exiting a pillar cell, rather than changing to a
   diagonal that clips the pillar after merely crossing its centerline.

4. Same-cell direct charge must require clearance even without a procedural pillar
   (custom blockers exist). Keep visual/projectile LOS distinct from body clearance
   so the witch's casting behavior isn't unnecessarily changed.

5. Extract a small production steering helper if needed to test the actual logic;
   do not copy its equations into tests. Simulate south->north, east->west and
   diagonal pillar chases for .35/.40/.55 radii. Assert arrival, per-step clearance,
   and no oscillation. No extra dependency installation.

Update RESULT.md with actual findings and results. Keep your original file scope.
