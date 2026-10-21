import math
import random
from panda3d.core import PointLight
from constants import (
    CELL_SIZE, MAP_MIN_CHUNK, MAP_MAX_CHUNK, CHUNK_CELLS
)
from world_gen import cell_has_pillar
from monster import (
    AbominableMudOrc, AlluringAshWitch,
    TallSkeletonMonster, LongBlackSerpent,
    SkeletalDobermanHellhound
)
from interactive_objects import HazardBarrel, TacticalSupplyCrate


def apply_elite_mutation(monster, game):
    """18% 확률로 스폰되는 정예 변이종(Elite Mutated Monster) 강화
    - 1.25배 스케일업
    - 1.85배 체력, 1.25배 공격력, 3.0배 경험치
    - 고유 정예 칭호 및 자체 발광 스펙트럴 아우라 조명 부착
    """
    monster.is_elite = True
    if hasattr(monster, 'node') and not monster.node.isEmpty():
        monster.node.setScale(1.25)
    monster.max_hp = int(monster.max_hp * 1.85)
    monster.hp = monster.max_hp
    monster.exp_value = getattr(monster, 'exp_value', 45) * 3
    monster.attack_damage = int(getattr(monster, 'attack_damage', 30) * 1.25)

    if isinstance(monster, AbominableMudOrc):
        monster.name = "되살아난 거산 스룬달"
        aura_color = (2.8, 0.4, 0.4, 1.0)
    elif isinstance(monster, TallSkeletonMonster):
        monster.name = "휩쓰는 공포 스컬"
        aura_color = (0.4, 1.8, 2.8, 1.0)
    elif isinstance(monster, AlluringAshWitch):
        monster.name = "염마 스칼렛"
        aura_color = (2.5, 0.4, 2.8, 1.0)
    elif isinstance(monster, LongBlackSerpent):
        monster.name = "백골룡 우르보로스"
        aura_color = (0.4, 2.8, 0.8, 1.0)
    elif isinstance(monster, SkeletalDobermanHellhound):
        monster.name = "끝없는 고통의 켈베스"
        aura_color = (3.2, 0.8, 0.2, 1.0)
    else:
        monster.name = f"[정예] {monster.name}"
        aura_color = (2.8, 1.8, 0.3, 1.0)

    elite_pl = PointLight(f"elite_light_{id(monster)}")
    elite_pl.setColor(aura_color)
    elite_pl.setAttenuation((1.0, 0.08, 0.02))
    elite_np = monster.node.attachNewNode(elite_pl)
    elite_np.setPos(0, 0, 1.6)
    game.render.setLight(elite_np)
    monster.elite_light_np = elite_np
    return monster


def get_gate_corridor_candidates(escape_pos, min_dist=6.0, max_dist=32.0):
    """탈출 관문 주변의 복도 셀 후보 좌표 목록 반환"""
    if not escape_pos:
        return []
    ex, ey = escape_pos
    min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
    max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
    cands = []
    for gx in range(min_cell, max_cell + 1):
        for gy in range(min_cell, max_cell + 1):
            if gx % 3 == 1 or gy % 3 == 1:
                if cell_has_pillar(gx, gy):
                    continue
                cx = (gx + 0.5) * CELL_SIZE
                cy = (gy + 0.5) * CELL_SIZE
                d = math.hypot(cx - ex, cy - ey)
                if min_dist <= d <= max_dist:
                    cands.append((cx, cy))
    return cands


def spawn_reinforcement_monster(game, pos=None, near_gate=True):
    """관문 인근 또는 특정 위치에 증원 몬스터 단일 스폰"""
    if len(game.monsters) >= 22:
        return None

    if pos is None:
        if near_gate:
            cands = get_gate_corridor_candidates(getattr(game, 'escape_pos', None), min_dist=10.0, max_dist=30.0)
            if cands:
                pos = random.choice(cands)
            else:
                ex, ey = getattr(game, 'escape_pos', (0, 0))
                pos = (ex + random.choice([-16, 16]), ey + random.choice([-16, 16]))
        else:
            px, py = game.camera.getX(), game.camera.getY()
            pos = (px + random.choice([-22, 22]), py + random.choice([-22, 22]))

    types = [AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, LongBlackSerpent, SkeletalDobermanHellhound]
    weights = [0.28, 0.26, 0.18, 0.08, 0.20]
    cls = random.choices(types, weights=weights, k=1)[0]

    monster = cls(game.render, pos[0], pos[1])
    stage_hp_mult = 1.0 + (game.current_stage - 1) * 0.25
    monster.max_hp = int(monster.max_hp * stage_hp_mult)
    monster.hp = monster.max_hp
    if random.random() < 0.20:
        apply_elite_mutation(monster, game)
    game.monsters.append(monster)
    return monster


def spawn_monsters(game, stage=1):
    """스테이지별 다중 몬스터 군단 스폰 (관문 수호 호드 집중 배치 + 맵 순찰대)"""
    for m in game.monsters:
        if hasattr(m, 'elite_light_np') and m.elite_light_np and not m.elite_light_np.isEmpty():
            game.render.clearLight(m.elite_light_np)
            m.elite_light_np.removeNode()
            m.elite_light_np = None
        m.destroy()
    game.monsters = []
    for c in game.corpses:
        c.destroy()
    game.corpses = []

    spawn_x = 1.5 * CELL_SIZE
    spawn_y = 1.5 * CELL_SIZE
    ex, ey = getattr(game, 'escape_pos', (spawn_x + 75.0, spawn_y + 75.0))

    # 1. 맵 전체 복도 후보 및 관문 인근 복도 후보 분리
    min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
    max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
    map_candidates = []
    gate_candidates = []

    for gx in range(min_cell, max_cell + 1):
        for gy in range(min_cell, max_cell + 1):
            if gx % 3 == 1 or gy % 3 == 1:
                if cell_has_pillar(gx, gy):
                    continue
                cx = (gx + 0.5) * CELL_SIZE
                cy = (gy + 0.5) * CELL_SIZE
                dist_to_spawn = math.hypot(cx - spawn_x, cy - spawn_y)
                dist_to_gate = math.hypot(cx - ex, cy - ey)

                if dist_to_spawn >= 22.0:
                    map_candidates.append((cx, cy))
                if 6.0 <= dist_to_gate <= 28.0:
                    gate_candidates.append((cx, cy))

    random.shuffle(map_candidates)
    random.shuffle(gate_candidates)

    stage_hp_mult = 1.0 + (stage - 1) * 0.25

    # 2. [관문 수호 몬스터 군단 (Gate Guardians)] - 탈출 관문 근처에 집중 배치
    gate_monsters_count = 6 + (stage - 1) * 2
    gate_plan = [
        AbominableMudOrc, AbominableMudOrc,
        AlluringAshWitch, AlluringAshWitch,
        TallSkeletonMonster, LongBlackSerpent,
        SkeletalDobermanHellhound
    ]
    while len(gate_plan) < gate_monsters_count:
        gate_plan.append(random.choice([AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, SkeletalDobermanHellhound]))

    for i, cls in enumerate(gate_plan):
        pos = gate_candidates[i % len(gate_candidates)] if gate_candidates else (ex + (i + 1) * 4, ey + 4)
        monster = cls(game.render, pos[0], pos[1])
        if stage > 1:
            monster.max_hp = int(monster.max_hp * stage_hp_mult)
            monster.hp = monster.max_hp
        game.monsters.append(monster)

    # 3. [맵 전역 순찰 몬스터] - 맵 전역의 긴장감 유지 (5마리)
    patrol_plan = [AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, LongBlackSerpent, SkeletalDobermanHellhound]
    for i, cls in enumerate(patrol_plan):
        pos = map_candidates[i % len(map_candidates)] if map_candidates else (spawn_x + 30.0 + i * 10, spawn_y + 30.0)
        monster = cls(game.render, pos[0], pos[1])
        if stage > 1:
            monster.max_hp = int(monster.max_hp * stage_hp_mult)
            monster.hp = monster.max_hp
        game.monsters.append(monster)

    # 4. 정예 변이 몬스터 (최소 1마리 보장 + 18% 확률 추가 변이)
    has_elite = False
    for m in game.monsters:
        if random.random() < 0.18:
            apply_elite_mutation(m, game)
            has_elite = True

    if not has_elite and game.monsters:
        apply_elite_mutation(game.monsters[0], game)

    # 오디오 관리자에 첫 번째 뱀/해골 부착
    first_serpent = next((m for m in game.monsters if isinstance(m, LongBlackSerpent)), None)
    first_skel = next((m for m in game.monsters if isinstance(m, TallSkeletonMonster)), None)
    if first_serpent and first_skel:
        game.audio_mgr.attach_monsters(first_serpent, first_skel)

    # 복도 폭발성 유류 드럼통 배치
    spawn_hazard_barrels(game)


def spawn_hazard_barrels(game):
    """던전 복도 코너/교차로에 붉은색 고위험 유류 드럼통 6~8개 배치"""
    for b in game.hazard_barrels:
        b.destroy()
    game.hazard_barrels.clear()

    min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 2
    max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 3
    spawn_x = 1.5 * CELL_SIZE
    spawn_y = 1.5 * CELL_SIZE

    candidates = []
    for gx in range(min_cell, max_cell, 2):
        for gy in range(min_cell, max_cell, 2):
            if (gx % 3 == 1 or gy % 3 == 1) and not cell_has_pillar(gx, gy):
                bx = (gx + 0.35) * CELL_SIZE
                by = (gy + 0.35) * CELL_SIZE
                if math.hypot(bx - spawn_x, by - spawn_y) >= 16.0:
                    candidates.append((bx, by))

    selected = random.sample(candidates, min(len(candidates), 7)) if candidates else []
    for bx, by in selected:
        barrel = HazardBarrel(game.world_root, bx, by, game.audio_mgr)
        game.hazard_barrels.append(barrel)


def spawn_supply_crates(game):
    """던전 필드 곳곳에 전술 보급 상자 6~8개 배치"""
    for cr in game.supply_crates:
        cr.destroy()
    game.supply_crates.clear()

    min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 2
    max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 3
    spawn_x = 1.5 * CELL_SIZE
    spawn_y = 1.5 * CELL_SIZE

    candidates = []
    for gx in range(min_cell, max_cell, 2):
        for gy in range(min_cell, max_cell, 2):
            if not cell_has_pillar(gx, gy):
                cx = (gx + 0.45) * CELL_SIZE
                cy = (gy + 0.45) * CELL_SIZE
                dist_sp = math.hypot(cx - spawn_x, cy - spawn_y)
                if 14.0 <= dist_sp <= 110.0:
                    candidates.append((cx, cy))

    selected = random.sample(candidates, min(len(candidates), 8)) if candidates else []
    for cx, cy in selected:
        crate = TacticalSupplyCrate(game.world_root, cx, cy, game.audio_mgr)
        game.supply_crates.append(crate)
