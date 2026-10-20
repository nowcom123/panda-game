# Shared task: repeatable perk upgrades

User explicitly requests duplicate perk picks increase actual numerical effects,
and collaboration with Antigravity. Work in this panda-game repository.

## File ownership
Antigravity: edit ONLY combat_system.py, projectiles.py, ui_manager.py and optionally
tests/test_perk_combat_scaling.py. Write completion notes in RESULT.md beside this file.
Codex: perks.py, player_controller.py, core scaling tests. Do not edit our files.
Preserve other existing edits, particularly removed ramps/elevation and rankings.json.
Do not commit, push, pull, install anything, or modify game.py. No broad refactors.

## Agreed API (Codex is implementing now)
Import from perks:
- get_perk_level(player, perk_id) -> integer level, 0 when absent; legacy owned set means L1.
- get_perk_stats(perk_id, level) -> dict of current stats.
- get_player_perk_stats(player, perk_id) -> dict (use inside existing has_perk branches).
- describe_perk(perk_id, level) -> Korean actual numbers for this level.
The following keys exist; level 1 preserves actual current gameplay values:
ricochet: damage_mult (.70 + .15*(L-1)), range (14+2*(L-1)).
shrapnel_burst: damage (75+25*(L-1)), radius (3.8+.4*(L-1)).
adrenaline_slide: damage_mult (1+.5*L), duration (1.8+.4*(L-1)).
vampiric_leech: kill_heal (12*L), headshot_heal (5*L).
armor_piercing: targets (L) additional monsters. Sort hits by distance, hit each once,
do not hit through walls. Keep kill/XP behavior for each pierced monster.
bullet_storm: duration (3.5+L-1), cooldown_mult (1/(1+.538461538*L)), L1=.65.
tesla_arc: damage (35+15*(L-1)), radius (7.5+.5*(L-1)), targets (min(8,L+1)),
 shock_duration (.85+.1*(L-1)), primary_duration (.65+.1*(L-1)), stun_duration (.4+.05*(L-1)).
dragons_breath: dps (25+10*(L-1)), duration (3+.5*(L-1)).
cluster_grenade: count (min(12,L+3)), damage (90+30*(L-1)), radius (3.5+.2*(L-1)).
titan_armor: Codex handles player effects.
speed_demon: reload_mult (max(.1,.65**L)); use for reload timer AND reload_duration.
headhunter: damage_mult (1+.45*L), xp_mult (1+L).

## Implementation
Replace EVERY hardcoded constant for perks in owned combat/projectiles files with
these stats; find bullet_storm fire cooldown too. Keep current level-1 functionality.
Prevent high-level visual-effect count explosions (cluster max12, tesla max8 already).

UI: Both level-up and stage-clear offers should show current -> next level and
actual next-level description via describe_perk. HUD and owned labels show Lv.N.
update_perk_badges(perk_ids, perk_levels=None) must accept optional map; Codex will
call with (self.perks, self.perk_levels). Existing one-argument callers should
resolve levels from base.player or shop_player. Store no stale level caches.
Guard _select_perk_card against negative indexes, hidden modal and repeat selection
when selected_perk_idx != -1; keyboard repeats must not grant free extra levels.
Each future offer may include owned perks; Codex updates draw_random_perks.

Run targeted compile/tests, report exactly which files changed and checks passed.
