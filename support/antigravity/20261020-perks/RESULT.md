# Antigravity Task Completion: Repeatable Perk Upgrades

## 1. Overview
In accordance with `TASK.md` for duplicate perk upgrade scaling, Antigravity implemented numerical level-scaling in all owned combat, projectile, and UI systems without touching Codex-owned files (`perks.py`, `player_controller.py`) or repository history (`game.py`, `rankings.json`, ramp/elevation changes).

## 2. Modified Files
- `combat_system.py`:
  - Replaced hardcoded constants with dynamic stats via `get_player_perk_stats(player, perk_id)`:
    - **`headhunter`**: Scaled headshot crit damage by `damage_mult` (`1.0 + 0.45 * L`) and kill EXP by `xp_mult` (`1 + L`).
    - **`adrenaline_slide`**: Scaled slide shot damage by `damage_mult` (`1.0 + 0.5 * L`) and bullet time duration by `duration` (`1.8 + 0.4 * (L - 1)`).
    - **`dragons_breath`**: Scaled burn DPS (`25.0 + 10.0 * (L - 1)`) and duration (`3.0 + 0.5 * (L - 1)`).
    - **`vampiric_leech`**: Scaled headshot heal (`5.0 * L`) and kill heal (`12.0 * L`).
    - **`tesla_arc`**: Scaled chain lightning damage (`35.0 + 15.0 * (L - 1)`), radius (`7.5 + 0.5 * (L - 1)`), targets (`min(8, L + 1)`), shock duration (`0.85 + 0.1 * (L - 1)`), and stun duration (`0.4 + 0.05 * (L - 1)`).
    - **`armor_piercing`**: Scaled additional penetration targets (`L`), sorted candidate hits by distance, enforced wall occlusion checks (`pierce_wall_dist`), and awarded kill credit/EXP for each pierced monster.
    - **`shrapnel_burst`**: Scaled on-kill explosion damage (`75.0 + 25.0 * (L - 1)`) and radius (`3.8 + 0.4 * (L - 1)`).
    - **`bullet_storm`**: Scaled on-kill infinite ammo duration (`3.5 + (L - 1)`) and fire cooldown multiplier (`1 / (1 + (1 / 0.65 - 1) * L)`).
    - **`speed_demon`**: Scaled `reload_timer` and `reload_duration` property by `reload_mult` (`max(0.1, 0.65 ** L)`).
    - Guarded execution refund against uninitialized `self.max_ammo`.
- `projectiles.py`:
  - **`cluster_grenade`**: Scaled sub-munition count (`min(12, L + 3)`), sub-blast damage (`90.0 + 30.0 * (L - 1)`), and radius (`3.5 + 0.2 * (L - 1)`) with evenly distributed radial trajectories.
- `ui_manager.py`:
  - **`update_perk_badges(perk_ids, perk_levels=None)`**: Added support for optional `perk_levels` map, fallback resolution from `shop_player` or `base.player`, and formatted badges as `[퍽] {icon} {name} Lv.{lvl}` without stale caches.
  - **`_refresh_owned_perks_label`**: Formatted owned perk badges with level tags (`{name} Lv.{lvl}`).
  - **`_select_perk_card`**: Guarded against negative indexes (`card_idx < 0`), hidden modal, and repeat selection when `selected_perk_idx != -1` to prevent free level grants on keyboard repeats.
  - **Card progression display**: Both `show_stage_clear_shop` and `show_levelup_perk_modal` now display current to next level in card titles (`{name} (Lv.{cur_lvl} → Lv.{next_lvl})`) and call `describe_perk(pid, next_lvl)` for accurate next-level stat descriptions.
- `tests/test_perk_combat_scaling.py`:
  - Added unit regression tests covering UI badge level maps, card selection guards, cluster grenade sub-munition scaling/capping at 12, and bullet storm cooldown multipliers.

## 3. Verification & Test Results
- Syntax check: `python -m py_compile combat_system.py projectiles.py ui_manager.py tests/test_perk_combat_scaling.py` (exit code 0).
- Runtime & integration tests executed:
  - `tests/test_perk_runtime.py`: 10/10 tests passed (OK).
  - `tests/test_perk_ui.py`: 3/3 tests passed (OK).
  - `tests/test_perk_levels.py`: 7/7 tests passed (OK).
  - `tests/test_perk_selection.py`: 3/3 tests passed (OK).
  - `tests/test_perk_combat_scaling.py`: 4/4 tests passed (OK).
  - Full test suite: 56/56 tests passed across entire repository (`Ran 56 tests in 0.174s, OK`).
- Git status: No commits, pulls, pushes, or dependency installations performed. Ramp/elevation modifications and `rankings.json` strictly preserved.
