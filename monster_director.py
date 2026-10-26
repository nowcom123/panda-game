"""
monster_director.py - 몬스터 AI 제어, 스킬 시전, 길찾기/충돌 회피 및 시체/루팅 관리자

몬스터들의 거리 기반 틱 인터리빙, 근접/원거리 공격 및 고유 스킬(마녀 파이어볼,
오크 땅울림, 뱀 코브라 기립 강타, 케이블 보스 2페이즈 패턴), 지능형 추적 및
벽체 슬라이딩, 3D 공간 음향, 시체 파편 및 루팅 드랍을 총괄합니다.
"""

import math
import random

from constants import CELL_SIZE, PLAYER_EYE_HEIGHT
from world_gen import check_line_of_sight, cell_has_pillar
from navigation import pursuit_target
from enemy_approach import approach_goal
from collision import get_nearby_colliders, resolve_collision
from interactive_objects import maybe_drop_monster_loot
from rpg.loot import roll_loot
from projectiles import GroundShockwave
from boss_scaling import boss_damage, movement_multiplier
from elevation import get_pursuit_goal, get_floor_height
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch,
    SkeletalDobermanHellhound, CableOverlordBoss
)
from gate_wave import GateWaveManager, GateWaveConfig


class MonsterDirector:
    """몬스터 집단 AI, 스킬 시전, 이동/충돌 판정 및 시체/루팅 통합 관리 디렉터"""

    def __init__(self, game):
        self.game = game
        self._flank_side = 1
        self.gate_wave_mgr = GateWaveManager(game)

    def update_monsters(self, dt: float, px: float, py: float, raw_dt: float = None):
        """매 프레임 몬스터들의 AI, 스킬, 충돌, 사운드, 시체 파편 갱신 (반환: is_game_over, closest_dist)"""
        g = self.game
        pz = getattr(g.camera, 'getZ', lambda: PLAYER_EYE_HEIGHT)()

        # -------------------------------------------------------------
        # 1. 테스트 모드 전용 갱신: AI 이동/추적/공격 차단, 제자리 유휴 & 자동 리스폰
        # -------------------------------------------------------------
        if getattr(g, 'is_test_mode', False):
            if g.combat.reserve_ammo < 60:
                g.combat.reserve_ammo = 999
                g.ui_mgr.update_ammo(g.combat.ammo, g.combat.max_ammo, g.combat.reserve_ammo)
            g.player.hp = g.player.max_hp

            if g.boss and getattr(g.boss, 'hp', 0) > 0 and g.boss in g.monsters:
                if hasattr(g.ui_mgr, 'update_boss_hp'):
                    g.ui_mgr.update_boss_hp(g.boss.hp, g.boss.max_hp, g.boss.phase)

            for m in g.monsters[:]:
                if getattr(m, 'hp', 1) <= 0:
                    m._test_respawn_timer = 3.0
                    if isinstance(m, CableOverlordBoss) and hasattr(g.ui_mgr, 'hide_boss_hp_bar'):
                        g.ui_mgr.hide_boss_hp_bar()
                    if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                        if hasattr(m, 'elite_light_np') and m.elite_light_np and not m.elite_light_np.isEmpty():
                            g.render.clearLight(m.elite_light_np)
                            m.elite_light_np.removeNode()
                            m.elite_light_np = None
                        m.turn_into_corpse(audio_mgr=g.audio_mgr)
                        drop = maybe_drop_monster_loot(g.world_root, m.pos.x, m.pos.y, m, g.audio_mgr)
                        if drop:
                            g.item_drops.append(drop)
                    g.monsters.remove(m)
                    g.corpses.append(m)
                    continue

                # 정지 상태 유휴 애니메이션 (숨쉬기, 부유 등)
                m.update(dt, is_moving=False, is_attacking=False)

            # 사망한 몬스터 파편 물리 갱신 및 3초 후 자동 리스폰
            for c in g.corpses[:]:
                if hasattr(c, 'update_debris'):
                    c.update_debris(dt)
                c._test_respawn_timer = getattr(c, '_test_respawn_timer', 3.0) - dt
                if c._test_respawn_timer <= 0.0:
                    spawn_x, spawn_y = getattr(c, '_test_spawn_pos', (0.0, 4.0))
                    if isinstance(c, AlluringAshWitch):
                        new_m = AlluringAshWitch(g.world_root, spawn_x, spawn_y)
                    elif isinstance(c, TallSkeletonMonster):
                        new_m = TallSkeletonMonster(g.world_root, spawn_x, spawn_y)
                    elif isinstance(c, AbominableMudOrc):
                        new_m = AbominableMudOrc(g.world_root, spawn_x, spawn_y)
                    elif isinstance(c, LongBlackSerpent):
                        new_m = LongBlackSerpent(g.world_root, spawn_x, spawn_y)
                    elif isinstance(c, SkeletalDobermanHellhound):
                        new_m = SkeletalDobermanHellhound(g.world_root, spawn_x, spawn_y)
                    else:
                        new_m = None

                    if new_m:
                        new_m.node.setH(180)
                        new_m._test_spawn_pos = (spawn_x, spawn_y)
                        new_m._test_respawn_timer = 3.0
                        g.monsters.append(new_m)

                    if hasattr(c, 'destroy'):
                        c.destroy()
                    if c in g.corpses:
                        g.corpses.remove(c)

            return False, 999.0

        # -------------------------------------------------------------
        # 2. 일반 게임플레이 모드 몬스터 AI 및 행동 처리
        # -------------------------------------------------------------
        closest_dist = 999.0
        g.frame_count = getattr(g, 'frame_count', 0) + 1
        stage_mult = 1.0 + (g.current_stage - 1) * 0.15
        if getattr(g, 'blackout_active', False):
            stage_mult *= 1.25  # 정전 프로토콜: 몬스터 이동속도 25% 가속 (폭주 상태)

        # 관문 거리 계산 및 관문 접근 시 몬스터 가속 / 긴급 증원 트리거
        ex, ey = getattr(g, 'escape_pos', (px + 100, py + 100))
        dist_gate = math.hypot(px - ex, py - ey)

        # [관문 접근 가속] 관문 근처로 갈수록 몬스터들의 이동 속도 대폭 증가 (최대 +45% 가속)
        if dist_gate <= 50.0:
            prox_factor = max(0.0, min(1.0, (50.0 - dist_gate) / 50.0))
            stage_mult *= (1.0 + prox_factor * 0.45)

        # [Stage 3: 심연의 지배자 보스 출현] 3스테이지 이상에서 관문 38m 접근 시 보스 각성
        if g.current_stage >= 3 and not g.boss_spawned and dist_gate <= 38.0:
            g.spawn_boss()

        # [단일 관문 증원 웨이브 제어] 45m 이내 단일 웨이브 관리자 갱신 (raw_dt 유지)
        wave_dt = raw_dt if raw_dt is not None else dt
        self.gate_wave_mgr.update(wave_dt, px, py)

        for m in g.monsters[:]:
            if getattr(m, 'hp', 1) <= 0:
                # 보스 격파 시 특별 연출 및 보상
                if isinstance(m, CableOverlordBoss) and not g.boss_defeat_handled:
                    g.boss_defeat_handled = True
                    if hasattr(g.ui_mgr, 'hide_boss_hp_bar'):
                        g.ui_mgr.hide_boss_hp_bar()
                    g.trigger_bullet_time(4.0)
                    g.ui_mgr.show_stage_banner(
                        f"[ ★ BOSS DEFEATED ★ ]\n{m.name} 격파 성공!\n탈출 관문 보안 락이 영구 해제되었습니다!",
                        color=(0.2, 1.0, 0.4, 1.0)
                    )
                    g.stage_banner_timer = 5.0
                    g.player.add_exp(800, g.combat, g.ui_mgr, g)
                    for ox, oy in [(-1.5, 0.0), (1.5, 0.0), (0.0, 1.5)]:
                        dp = maybe_drop_monster_loot(g.world_root, m.pos.x + ox, m.pos.y + oy, m, g.audio_mgr)
                        if dp:
                            g.item_drops.append(dp)
                    if (
                        not getattr(g, 'is_test_mode', False)
                        and getattr(g, 'loot_world', None)
                        and not getattr(m, '_rpg_loot_dropped', False)
                    ):
                        m._rpg_loot_dropped = True
                        cat = getattr(getattr(g, 'rpg_session', None), 'catalog', None) or getattr(g, 'rpg_catalog', None)
                        if cat:
                            stg = getattr(g, 'current_stage', 1)
                            for r_item in roll_loot(cat, enemy_tier="boss", stage=stg):
                                g.loot_world.spawn_loot((m.pos.x, m.pos.y, get_floor_height(m.pos.x, m.pos.y, m.pos.z)[0] + .3), r_item)

                # 사망한 몬스터: 시체로 전환하고 활성 몬스터 목록에서 제외
                if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                    if hasattr(m, 'elite_light_np') and m.elite_light_np and not m.elite_light_np.isEmpty():
                        g.render.clearLight(m.elite_light_np)
                        m.elite_light_np.removeNode()
                        m.elite_light_np = None
                    m.turn_into_corpse(audio_mgr=g.audio_mgr)
                    if not isinstance(m, CableOverlordBoss):
                        drop = maybe_drop_monster_loot(g.world_root, m.pos.x, m.pos.y, m, g.audio_mgr)
                        if drop:
                            g.item_drops.append(drop)
                        if (
                            not getattr(g, 'is_test_mode', False)
                            and getattr(g, 'loot_world', None)
                            and not getattr(m, '_rpg_loot_dropped', False)
                        ):
                            m._rpg_loot_dropped = True
                            cat = getattr(getattr(g, 'rpg_session', None), 'catalog', None) or getattr(g, 'rpg_catalog', None)
                            if cat:
                                is_elite = getattr(m, 'is_elite', False)
                                tier = "elite" if is_elite else "normal"
                                stg = getattr(g, 'current_stage', 1)
                                for r_item in roll_loot(cat, enemy_tier=tier, stage=stg):
                                    g.loot_world.spawn_loot((m.pos.x, m.pos.y, get_floor_height(m.pos.x, m.pos.y, m.pos.z)[0] + .3), r_item)
                g.monsters.remove(m)
                g.corpses.append(m)
                continue

            mx, my = m.pos.x, m.pos.y
            dist = math.hypot(px - mx, py - my)
            dist_z = abs(pz - (m.pos.z + getattr(m, 'height', 2.0) * 0.5))
            if dist < closest_dist:
                closest_dist = dist

            # 몬스터 고유 틱 오프셋 및 누적 dt 초기화
            if not hasattr(m, '_tick_id'):
                m._tick_id = id(m) % 6
                m._accum_dt = 0.0

            # 새 타이머/독/반격은 애니메이션 LOD와 분리하여 매 논리 틱 world_dt로 갱신
            if hasattr(m, 'update_reactions'):
                m.update_reactions(dt, g, px, py, pz)
                if g.player.hp <= 0:
                    g.trigger_game_over(killer=m, reason='killed')
                    return True, closest_dist

            # CPU 몬스터 틱 인터리빙 (거리 기반 갱신 주기 분산 - 화염/전기 원소/반응 발동 중에는 100% 실시간 갱신)
            is_critical = (
                dist <= 14.0 or isinstance(m, CableOverlordBoss) or
                getattr(m, 'is_casting', False) or getattr(m, 'is_slamming', False) or
                getattr(m, 'is_striking', False) or getattr(m, 'is_lashing', False) or
                getattr(m, 'is_guarding', False) or getattr(m, 'counter_pending', False) or getattr(m, 'is_dodging', False) or
                getattr(m, 'stun_timer', 0.0) > 0.0 or getattr(m, 'burn_timer', 0.0) > 0.0 or getattr(m, 'shock_timer', 0.0) > 0.0
            )
            # Pose-only LOD is independent of the existing AI tick schedule.
            m._animation_interval = (0.0 if is_critical or dist <= 26.0
                                     else .05 if dist <= 40.0 else .10)
            if not is_critical:
                skip_frame = False
                if dist <= 26.0:
                    if (g.frame_count + m._tick_id) % 2 != 0:
                        skip_frame = True
                else:
                    if (g.frame_count + m._tick_id) % 3 != 0:
                        skip_frame = True

                if skip_frame:
                    m._accum_dt += dt
                    continue

            eff_dt = dt + getattr(m, '_accum_dt', 0.0)
            m._accum_dt = 0.0

            # 0. 회피 및 방어/반격 중인 몬스터: 일반 공격/캐스팅 중첩 차단 및 모션 갱신
            if getattr(m, 'is_dodging', False):
                if isinstance(m, SkeletalDobermanHellhound):
                    m.update(eff_dt, is_moving=False, chunks=g.chunks)
                else:
                    m.update(eff_dt, is_moving=False)
                continue
            if getattr(m, 'is_guarding', False) or getattr(m, 'counter_pending', False):
                m.update(eff_dt, is_moving=False)
                continue

            # 1. 일반 근접 공격 판정 (해골, 오크, 파수견) - 3D 수직 거리(dist_z <= 2.2m) 확인
            if not isinstance(m, (LongBlackSerpent, CableOverlordBoss)):
                attack_range = 1.95 if isinstance(m, (TallSkeletonMonster, AbominableMudOrc)) else (1.75 if isinstance(m, SkeletalDobermanHellhound) else 1.45)
                if dist <= attack_range and dist_z <= 2.2 and m.stun_timer <= 0.0:
                    is_dead = g.player.take_damage(m.attack_damage, source_pos=(mx, my))
                    m.update(eff_dt, is_moving=False, is_attacking=True)
                    if is_dead:
                        g.trigger_game_over(killer=m, reason="killed")
                        return True, closest_dist
                    continue

            # 2. 스턴 상태 처리
            if getattr(m, 'stun_timer', 0.0) > 0.0:
                m.update_pos(mx, my, eff_dt, 0, 0)
                continue

            # 3-A. 진흙 오크: 땅을 울려서 플레이어 이동방해 (Ground Slam)
            if isinstance(m, AbominableMudOrc):
                m.slam_cooldown -= eff_dt
                if dist <= 12.0 and m.slam_cooldown <= 0.0 and not m.is_slamming and m.stun_timer <= 0.0:
                    m.is_slamming = True
                    m.slam_timer = 0.0
                    m.slam_has_impacted = False
                    m.slam_cooldown = 5.5

                if m.is_slamming:
                    impact = m.slam_ground(eff_dt)
                    if impact:
                        g.shockwaves.append(GroundShockwave(g.render, mx, my))
                        g.audio_mgr.play_orc_slam()
                        if dist <= 11.5:
                            player_floor, _ = get_floor_height(px, py, pz - PLAYER_EYE_HEIGHT)
                            orc_floor, _ = get_floor_height(mx, my, m.pos.z)
                            if abs(player_floor - orc_floor) < 1.0:
                                g.player.apply_slow(duration=2.8, factor=0.40)
                                g.player.trigger_quake_shake(intensity=2.6, duration=0.85)
                    continue

            # 3-B. 거대 흑사(뱀): 상체 기립 후 전방 급습 강타 (Rearing Strike)
            if isinstance(m, LongBlackSerpent):
                m.strike_cooldown -= eff_dt
                if dist <= 3.8 and dist_z <= 2.8 and m.strike_cooldown <= 0.0 and not m.is_striking and m.stun_timer <= 0.0:
                    m.is_striking = True
                    m.strike_timer = 0.0
                    m.strike_has_hit = False
                    m.strike_cooldown = 2.4
                    if hasattr(g, 'audio_mgr') and g.audio_mgr:
                        g.audio_mgr.play_monster_3d("serp_hiss", m.node, volume_scale=1.15)

                if m.is_striking:
                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)

                    impact = m.strike_attack(eff_dt)
                    if impact:
                        if dist <= 4.2 and dist_z <= 2.8:
                            is_dead = g.player.take_damage(m.attack_damage, source_pos=(mx, my))
                            g.player.trigger_quake_shake(intensity=2.2, duration=0.40)
                            if is_dead:
                                g.trigger_game_over(killer=m, reason="killed")
                                return True, closest_dist
                    continue

            # 3-C. 골해의 지배자 (CableOverlordBoss) 전투 패턴 & 스킬 시전
            if isinstance(m, CableOverlordBoss):
                if hasattr(g.ui_mgr, 'update_boss_hp'):
                    g.ui_mgr.update_boss_hp(m.hp, m.max_hp, m.phase)

                # 신규 패턴 컨트롤러가 있는 경우 상태 머신 갱신
                if getattr(m, 'use_new_patterns', False) and hasattr(m, 'pattern_controller') and m.pattern_controller:
                    game_ended = m.pattern_controller.update(eff_dt, g, px, py, pz, dist, dist_z)
                    if game_ended:
                        return True, closest_dist
                    if m.pattern_controller.is_acting():
                        # 도약, 휩쓸기 등 패턴 동작 중에는 방향을 플레이어 쪽으로 바라보고 일반 경로탐색 보행은 건너뜀
                        # Keep the telegraphed orientation fixed throughout the attack.
                        m.update(eff_dt, is_moving=False)
                        continue
                else:
                    # 구버전 모의 객체 단위 테스트 호환용 레거시 분기
                    if m.hp <= m.max_hp * 0.5 and m.phase == 1:
                        m.phase = 2
                        m.speed = 6.2 * getattr(m, 'movement_scale', 1.0)
                        if hasattr(g.ui_mgr, 'show_stage_banner'):
                            g.ui_mgr.show_stage_banner(
                                "[ ! 경고: 심연의 지배자 2페이즈 폭주 돌입 ! ]\n심연의 코어가 적색으로 과부하되며 이동 속도 및 공격 빈도가 급증합니다!",
                                color=(1.0, 0.15, 0.15, 1.0)
                            )
                        g.stage_banner_timer = 3.5
                        if hasattr(g, 'audio_mgr') and g.audio_mgr:
                            g.audio_mgr.play_siren_alarm()
                        for _ in range(2):
                            g.spawn_reinforcement_monster(near_gate=True)

                    # 1) 케이블 채찍 근접 강타 (Cable Lash, dist <= 5.8m, dist_z <= 3.5m)
                    if dist <= 5.8 and dist_z <= 3.5 and getattr(m, 'cable_lash_cooldown', 99.0) <= 0.0 and not getattr(m, 'is_lashing', False) and getattr(m, 'stun_timer', 0.0) <= 0.0:
                        m.is_lashing = True
                        m.lash_timer = 0.65
                        m.cable_lash_cooldown = 1.6 if m.phase == 2 else 2.5
                        is_dead = g.player.take_damage(boss_damage(m, 38 if m.phase == 2 else 28), source_pos=(mx, my))
                        if hasattr(g, 'audio_mgr') and g.audio_mgr:
                            g.audio_mgr.play_monster_3d("serp_slither", m.node, volume_scale=1.4)
                        if hasattr(g.ui_mgr, 'show_hit_marker'):
                            g.ui_mgr.show_hit_marker("보스 케이블 채찍 강타 피격!", (1.0, 0.2, 0.2, 1.0))
                        if is_dead:
                            g.trigger_game_over(killer=m, reason="killed")
                            return True, closest_dist

                    # 2) 전방위 고전압 지진 충격파 (Ground Shockwave, dist <= 18m)
                    if dist <= 18.0 and getattr(m, 'shockwave_cooldown', 99.0) <= 0.0 and getattr(m, 'stun_timer', 0.0) <= 0.0:
                        m.shockwave_cooldown = 4.2 if m.phase == 2 else 6.2
                        g.shockwaves.append(GroundShockwave(g.render, mx, my))
                        if hasattr(g, 'audio_mgr') and g.audio_mgr:
                            g.audio_mgr.play_orc_slam()
                        g.player.trigger_quake_shake(intensity=3.2, duration=1.0)
                        if dist <= 11.0:
                            player_floor, _ = get_floor_height(px, py, pz - PLAYER_EYE_HEIGHT)
                            if player_floor < 1.2:
                                is_dead = g.player.take_damage(boss_damage(m, 20), source_pos=(mx, my))
                                if is_dead:
                                    g.trigger_game_over(killer=m, reason="killed")
                                    return True, closest_dist
                                g.player.apply_slow(duration=2.5, factor=0.45)
                                if hasattr(g.ui_mgr, 'show_hit_marker'):
                                    g.ui_mgr.show_hit_marker("보스 지진 충격파 피격! (이동속도 저하)", (1.0, 0.45, 0.1, 1.0))

                    # 3) 고압 와이어 다트 일제 투척 (Wire Darts, dist <= 32m)
                    if dist <= 32.0 and getattr(m, 'dart_cooldown', 99.0) <= 0.0 and getattr(m, 'stun_timer', 0.0) <= 0.0:
                        m.dart_cooldown = 3.2 if m.phase == 2 else 5.2
                        if hasattr(g, 'audio_mgr') and g.audio_mgr:
                            g.audio_mgr.play_witch_cast()
                        start_pos = (mx, my, m.pos.z + 2.8)
                        for spread_deg in (-14, 0, 14):
                            base_rad = math.atan2(py - my, px - mx) + math.radians(spread_deg)
                            target_p = (mx + math.cos(base_rad) * 22.0, my + math.sin(base_rad) * 22.0, pz)
                            g.spawn_fireball(start_pos, target_p, damage_scale=getattr(m, 'damage_scale', 1.0))
                        if hasattr(g.ui_mgr, 'show_hit_marker'):
                            g.ui_mgr.show_hit_marker("보스 고압 와이어 다트 사격!", (0.3, 0.9, 1.0, 1.0))

                    # 4) 2페이즈 심연의 괴물 소환 (Minion Summon)
                    if m.phase == 2 and getattr(m, 'summon_cooldown', 0.0) <= 0.0:
                        m.summon_cooldown = 14.0
                        if len(g.monsters) < 16:
                            for _ in range(2):
                                g.spawn_reinforcement_monster(near_gate=True)
                            if hasattr(g.ui_mgr, 'show_stage_banner'):
                                g.ui_mgr.show_stage_banner("[ ! 보스 증원 소환 ! ]\n심연의 괴물들이 소환되었습니다!", color=(1.0, 0.3, 0.1, 1.0))
                            g.stage_banner_timer = 2.5

            # 4. 시야(LOS) 확인
            has_los = False
            if dist <= 28.0:
                mid_x, mid_y = (mx + px) * 0.5, (my + py) * 0.5
                cols = get_nearby_colliders(g.chunks, mid_x, mid_y, dist * 0.5 + 1.2)
                has_los = check_line_of_sight(mx, my, px, py, cols)

            # 5. 잿더미 마녀: 파이어볼 투척 (Fireball Cast)
            if isinstance(m, AlluringAshWitch):
                m.cast_cooldown -= eff_dt
                if has_los and dist <= 24.0 and m.cast_cooldown <= 0.0 and not m.is_casting and m.stun_timer <= 0.0:
                    m.is_casting = True
                    m.cast_timer = 0.0
                    m._fireball_fired = False
                    m.cast_cooldown = 3.2

                if m.is_casting:
                    fire = m.cast_fireball(eff_dt)
                    if fire:
                        orb_pos = (mx, my, m.pos.z + 1.5)
                        target_pos = (px, py, pz)
                        g.spawn_fireball(orb_pos, target_pos)
                        g.audio_mgr.play_witch_fireball()

                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)
                    continue

            # 6. 지능형 길찾기 및 장애물/기둥 회피 (Intelligent Pathfinding & Collision Sliding)
            mgx = int(math.floor(mx / CELL_SIZE))
            mgy = int(math.floor(my / CELL_SIZE))
            stuck_timer = getattr(m, '_stuck_timer', 0.0)
            interval = 0.25 if dist_gate <= 35.0 else 0.40
            goal_x, goal_y = get_pursuit_goal(m.pos, g.camera.getPos())
            role = ('ranged' if isinstance(m, AlluringAshWitch) else
                    'flanker' if isinstance(m, SkeletalDobermanHellhound) else 'pressure')
            if role == 'flanker' and not hasattr(m, '_approach_side'):
                m._approach_side = self._flank_side
                self._flank_side *= -1
            if role != 'pressure':
                (goal_x, goal_y), holding = approach_goal(
                    m, role, g.chunks, (goal_x, goal_y), eff_dt, has_los)
                if getattr(m, '_approach_warning', False):
                    m._approach_warning = False
                    if getattr(g, 'audio_mgr', None):
                        g.audio_mgr.play_hound_growl(m.node)
                if holding:
                    m.node.setH(math.degrees(math.atan2(-(px-mx), py-my)))
                    m.update(eff_dt, is_moving=False)
                    continue
            tx, ty = pursuit_target(m, g.chunks, (goal_x, goal_y), eff_dt, interval)

            dx = tx - mx
            dy = ty - my
            d = math.hypot(dx, dy)
            if d > 0.01:
                ndx, ndy = dx / d, dy / d
                speed = getattr(m, 'speed', 8.5) * movement_multiplier(m, stage_mult)
                col_radius = getattr(m, 'col_radius', 0.40)
                step_dist = min(d, speed * eff_dt)

                # 1차 시도: 목표 방향 이동
                best_nx, best_ny = resolve_collision(g.chunks, mx, my, ndx * step_dist, ndy * step_dist, radius=col_radius, curr_z=m.pos.z)
                actual_move = math.hypot(best_nx - mx, best_ny - my)

                # 2차 시도: 벽체/문틀/기둥 모서리 저지 시 접선 슬라이딩 탐색 (최적화 6방향 및 조기 탈출)
                if actual_move < 0.35 * step_dist:
                    base_angle = math.atan2(ndy, ndx)
                    best_progress = actual_move
                    orig_dist_to_target = math.hypot(mx - tx, my - ty)

                    probes = [
                        (ndx * step_dist, 0.0),
                        (0.0, ndy * step_dist),
                    ]
                    # 고효율 6방향 스캔각: ±35도, ±75도, ±115도
                    for ang_deg in (35, -35, 75, -75, 115, -115):
                        rad = base_angle + math.radians(ang_deg)
                        probes.append((math.cos(rad) * step_dist, math.sin(rad) * step_dist))

                    for pdx, pdy in probes:
                        cand_nx, cand_ny = resolve_collision(g.chunks, mx, my, pdx, pdy, radius=col_radius, curr_z=m.pos.z)
                        c_move = math.hypot(cand_nx - mx, cand_ny - my)
                        if c_move > 0.20 * step_dist:
                            dist_to_target = math.hypot(cand_nx - tx, cand_ny - ty)
                            dist_diff = orig_dist_to_target - dist_to_target
                            progress = c_move * 1.2 + max(-0.25 * step_dist, dist_diff)
                            if progress > best_progress:
                                best_progress = progress
                                best_nx, best_ny = cand_nx, cand_ny
                                # 완전히 뚫린 궤적(85% 이상 이동 및 목표 접근) 발견 시 즉각 조기 탈출 (CPU 절감)
                                if c_move >= 0.85 * step_dist and dist_diff >= 0.0:
                                    break

                # 3차 시도: 미세 끼임 발생 시 반발 벡터 기반 능동 탈출 (Repulsion Unstuck Recovery)
                final_move = math.hypot(best_nx - mx, best_ny - my)
                if final_move < 0.015:
                    m._stuck_timer = stuck_timer + eff_dt
                    if m._stuck_timer > 0.16:
                        if cell_has_pillar(mgx, mgy):
                            pil_x = (mgx + 0.5) * CELL_SIZE
                            pil_y = (mgy + 0.5) * CELL_SIZE
                            cdx = mx - pil_x
                            cdy = my - pil_y
                            cd = math.hypot(cdx, cdy)
                            if cd < 0.01:
                                cdx, cdy, cd = 1.0, 0.0, 1.0
                            esc_x, esc_y = resolve_collision(g.chunks, mx, my, (cdx / cd) * step_dist * 1.5, (cdy / cd) * step_dist * 1.5, radius=col_radius, curr_z=m.pos.z)
                            best_nx, best_ny = esc_x, esc_y
                        else:
                            cols = get_nearby_colliders(g.chunks, mx, my, search_dist=col_radius + 0.8, curr_z=m.pos.z)
                            rep_x, rep_y = 0.0, 0.0
                            for min_x, min_y, max_x, max_y in cols:
                                cx = max(min_x, min(mx, max_x))
                                cy = max(min_y, min(my, max_y))
                                vx = mx - cx
                                vy = my - cy
                                vd = math.hypot(vx, vy)
                                if vd < col_radius + 0.5 and vd > 1e-6:
                                    rep_x += (vx / vd) * (col_radius + 0.5 - vd)
                                    rep_y += (vy / vd) * (col_radius + 0.5 - vd)
                            r_dist = math.hypot(rep_x, rep_y)
                            if r_dist > 1e-4:
                                esc_x, esc_y = resolve_collision(g.chunks, mx, my, (rep_x / r_dist) * step_dist * 1.5, (rep_y / r_dist) * step_dist * 1.5, radius=col_radius, curr_z=m.pos.z)
                                best_nx, best_ny = esc_x, esc_y
                            else:
                                center_x = (mgx + 0.5) * CELL_SIZE
                                center_y = (mgy + 0.5) * CELL_SIZE
                                cdx = center_x - mx
                                cdy = center_y - my
                                cd = math.hypot(cdx, cdy)
                                if cd > 0.1:
                                    esc_x, esc_y = resolve_collision(g.chunks, mx, my, (cdx / cd) * step_dist, (cdy / cd) * step_dist, radius=col_radius, curr_z=m.pos.z)
                                    best_nx, best_ny = esc_x, esc_y
                        m.path = []
                        m.path_timer = 0.0
                else:
                    m._stuck_timer = max(0.0, stuck_timer - eff_dt * 2.0)

                face_dx = best_nx - mx
                face_dy = best_ny - my
                if math.hypot(face_dx, face_dy) > 0.001:
                    m.update_pos(best_nx, best_ny, eff_dt, face_dx, face_dy)
                else:
                    m.update_pos(best_nx, best_ny, eff_dt, ndx, ndy)
            else:
                m.update(eff_dt, is_moving=False)
                m._stuck_timer = 0.0

            # 7. 3D 입체 접근 사운드 (발소리 & 괴성/숨소리 360도 공간 음향)
            if dist <= 32.0 and not getattr(m, 'is_corpse', False) and hasattr(g, 'audio_mgr') and g.audio_mgr:
                m._step_timer = getattr(m, '_step_timer', random.uniform(0.05, 0.25)) - eff_dt
                if d > 0.05 and m._step_timer <= 0.0:
                    if isinstance(m, AbominableMudOrc):
                        g.audio_mgr.play_monster_3d("orc_step", m.node, volume_scale=random.uniform(0.85, 1.0))
                        m._step_timer = 0.38 + random.uniform(-0.04, 0.04)
                    elif isinstance(m, TallSkeletonMonster):
                        g.audio_mgr.play_monster_3d("skel_step", m.node, volume_scale=random.uniform(0.75, 0.95))
                        m._step_timer = 0.34 + random.uniform(-0.03, 0.03)
                    elif isinstance(m, LongBlackSerpent):
                        g.audio_mgr.play_monster_3d("serp_slither", m.node, volume_scale=random.uniform(0.80, 0.95))
                        m._step_timer = 0.44 + random.uniform(-0.04, 0.04)
                    elif isinstance(m, SkeletalDobermanHellhound):
                        g.audio_mgr.play_monster_3d("hound_step", m.node, volume_scale=random.uniform(0.70, 0.90))
                        m._step_timer = 0.22 + random.uniform(-0.03, 0.03)

                m._vocal_timer = getattr(m, '_vocal_timer', random.uniform(1.0, 3.5)) - eff_dt
                if m._vocal_timer <= 0.0:
                    if isinstance(m, AbominableMudOrc):
                        g.audio_mgr.play_monster_3d("orc_growl", m.node, volume_scale=random.uniform(0.90, 1.10))
                        m._vocal_timer = random.uniform(3.2, 5.5)
                    elif isinstance(m, TallSkeletonMonster):
                        g.audio_mgr.play_monster_3d("skel_groan", m.node, volume_scale=random.uniform(0.85, 1.05))
                        m._vocal_timer = random.uniform(3.5, 6.0)
                    elif isinstance(m, LongBlackSerpent):
                        g.audio_mgr.play_monster_3d("serp_hiss", m.node, volume_scale=random.uniform(0.90, 1.10))
                        m._vocal_timer = random.uniform(3.0, 5.0)
                    elif isinstance(m, AlluringAshWitch):
                        g.audio_mgr.play_monster_3d("witch_whisper", m.node, volume_scale=random.uniform(0.85, 1.05))
                        m._vocal_timer = random.uniform(3.4, 5.8)
                    elif isinstance(m, SkeletalDobermanHellhound):
                        g.audio_mgr.play_monster_3d("hound_growl", m.node, volume_scale=random.uniform(0.90, 1.15))
                        m._vocal_timer = random.uniform(2.8, 4.8)

        # 8. 사망한 몬스터들의 비산 파편 물리 및 폭발 섬광 조명 갱신
        for c in g.corpses[:]:
            if hasattr(c, 'update_debris'):
                c.update_debris(dt)
            has_debris = hasattr(c, 'debris_list') and len(c.debris_list) > 0
            has_blast = hasattr(c, 'blast_light_np') and c.blast_light_np is not None
            if not has_debris and not has_blast:
                if hasattr(c, 'destroy'):
                    c.destroy()
                if c in g.corpses:
                    g.corpses.remove(c)

        # 활성 시체 상한 관리 (최대 6구 초과 시 가장 오래된 시체 즉시 정리)
        while len(g.corpses) > 6:
            oldest = g.corpses.pop(0)
            if hasattr(oldest, 'destroy'):
                oldest.destroy()

        return False, closest_dist
