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
    SkeletalDobermanHellhound, CableOverlordBoss
)
from interactive_objects import HazardBarrel, TacticalSupplyCrate


MONSTER_BASE_COLLISION_RADII = {
    TallSkeletonMonster: 0.40,
    AbominableMudOrc: 0.45,
    AlluringAshWitch: 0.38,
    SkeletalDobermanHellhound: 0.35,
    LongBlackSerpent: 0.38,
    CableOverlordBoss: 0.55,
}


def get_monster_collision_radius(cls_or_instance, is_elite=False):
    """생성 전/후 공유하는 몬스터 충돌 반경 조회 (정예 배율 1.25배 반영)"""
    if hasattr(cls_or_instance, '__mro__'):
        base_r = getattr(cls_or_instance, 'col_radius', MONSTER_BASE_COLLISION_RADII.get(cls_or_instance, 0.40))
        return round(base_r * 1.25, 4) if is_elite else base_r
    return getattr(cls_or_instance, 'col_radius', 0.40)


def apply_elite_mutation(monster, game):
    """18% 확률로 스폰되는 정예 변이종(Elite Mutated Monster) 강화
    - 1.25배 스케일업
    - 1.85배 체력, 1.25배 공격력, 3.0배 경험치
    - 고유 정예 칭호 및 자체 발광 스펙트럴 아우라 조명 부착
    """
    monster.is_elite = True
    if hasattr(monster, 'node') and not monster.node.isEmpty():
        monster.node.setScale(1.25)
    monster.col_radius = round(getattr(monster, 'col_radius', 0.40) * 1.25, 4)
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


from world_gen import cell_has_pillar, check_line_of_sight
from collision import get_nearby_colliders


def get_gate_corridor_candidates(escape_pos, min_dist=10.0, max_dist=30.0):
    """탈출 관문 주변 10~30m 복도 셀 후보 좌표 목록 반환"""
    if not escape_pos:
        return []
    ex = getattr(escape_pos, 'x', escape_pos[0])
    ey = getattr(escape_pos, 'y', escape_pos[1])
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


def is_spawn_position_safe(game, cx, cy, radius, px, py, pz=0.0, cam_h=0.0, hfov=96.0, wave_spawned_positions=None):
    """관문 증원 출현 위치의 8가지 실시간 안전 조건 검증
    1. 관문에서 10~30m
    2. 플레이어에서 최소 12m 이상
    3. 로드된 청크 안
    4. 맵 경계 내
    5. 기둥(Pillar) 셀 배제
    6. 벽 및 관문 충돌체와 정예 반경을 포함한 몸체 중첩 배제
    7. 기존 생존 몬스터 및 동일 웨이브 기선정 위치와 몸체 중첩 배제
    8. 플레이어 수평 시야각(FOV) 안이고 가리지 않은 위치 배제 (벽 뒤 또는 시야각 밖 허용)
    """
    # 1. 관문 거리 10~30m
    escape_pos = getattr(game, 'escape_pos', None)
    if not escape_pos:
        return False
    ex = getattr(escape_pos, 'x', escape_pos[0])
    ey = getattr(escape_pos, 'y', escape_pos[1])
    dist_gate = math.hypot(cx - ex, cy - ey)
    if not (10.0 <= dist_gate <= 30.0):
        return False

    # 2. 플레이어 거리 최소 12m
    dist_player = math.hypot(cx - px, cy - py)
    if dist_player < 12.0:
        return False

    # 3 & 4. 맵 경계 및 로드된 청크 검사
    margin = radius + 0.2
    min_bound = MAP_MIN_CHUNK * CHUNK_CELLS * CELL_SIZE + margin
    max_bound = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS * CELL_SIZE - margin
    if not (min_bound <= cx <= max_bound and min_bound <= cy <= max_bound):
        return False

    cgx = int(math.floor(cx / CELL_SIZE))
    cgy = int(math.floor(cy / CELL_SIZE))
    chunk_coord = (cgx // CHUNK_CELLS, cgy // CHUNK_CELLS)
    chunks = getattr(game, 'chunks', None)
    if chunks is None or not isinstance(chunks, dict) or len(chunks) == 0:
        return False
    if chunk_coord not in chunks:
        return False

    # 5. 기둥 셀 배제
    if cell_has_pillar(cgx, cgy):
        return False

    # 6. 벽 및 관문 충돌체 몸체 중첩 검사
    nearby_cols = get_nearby_colliders(chunks, cx, cy, search_dist=radius + 0.6, curr_z=0.0)

    for min_x, min_y, max_x, max_y in nearby_cols:
        qx = max(min_x, min(cx, max_x))
        qy = max(min_y, min(cy, max_y))
        if (cx - qx)**2 + (cy - qy)**2 < radius**2:
            return False

    # 7. 기존 생존 몬스터 및 동일 웨이브 생성 위치 중첩 검사
    for m in getattr(game, 'monsters', []):
        if getattr(m, 'hp', 1) <= 0 or getattr(m, 'is_corpse', False):
            continue
        m_rad = getattr(m, 'col_radius', 0.40)
        mx = getattr(m.pos, 'x', m.pos[0] if hasattr(m.pos, '__getitem__') else 0.0)
        my = getattr(m.pos, 'y', m.pos[1] if hasattr(m.pos, '__getitem__') else 0.0)
        if (cx - mx)**2 + (cy - my)**2 < (radius + m_rad)**2:
            return False

    if wave_spawned_positions:
        for sx, sy, s_rad in wave_spawned_positions:
            if (cx - sx)**2 + (cy - sy)**2 < (radius + s_rad)**2:
                return False

    # 8. FOV 및 벽 차폐(Line-of-Sight) 검사
    rad = math.radians(cam_h)
    fwd_x = -math.sin(rad)
    fwd_y = math.cos(rad)
    dx = cx - px
    dy = cy - py
    dist_p = math.hypot(dx, dy)
    if dist_p < 1e-4:
        return False
    dir_x = dx / dist_p
    dir_y = dy / dist_p
    dot = max(-1.0, min(1.0, fwd_x * dir_x + fwd_y * dir_y))
    angle_deg = math.degrees(math.acos(dot))
    in_fov = (angle_deg <= (hfov * 0.5))

    if in_fov:
        # 시야각 안이면 반드시 벽 뒤(차폐)여야만 허용
        # 플레이어-후보 사이 선분이 미로드 청크를 통과하는지 검사
        steps = max(2, int(math.ceil(dist_p / (CELL_SIZE * 0.5))))
        for s in range(steps + 1):
            t = s / steps
            sx = px + t * dx
            sy = py + t * dy
            sgx = int(math.floor(sx / CELL_SIZE))
            sgy = int(math.floor(sy / CELL_SIZE))
            sc = (sgx // CHUNK_CELLS, sgy // CHUNK_CELLS)
            if sc not in chunks:
                return False

        mid_x = (px + cx) * 0.5
        mid_y = (py + cy) * 0.5
        segment_colliders = get_nearby_colliders(chunks, mid_x, mid_y, search_dist=dist_p * 0.5 + 2.0, curr_z=0.0)

        if segment_colliders:
            has_los = check_line_of_sight(px, py, cx, cy, segment_colliders)
            if has_los:
                # 벽에 가려지지 않고 직접 보이는 위치 -> 시야 내 급습 방지를 위해 제외
                return False
        else:
            # 차단 충돌체가 전혀 없는 열린 공간에서 플레이어 시야 정면 -> 제외
            return False

    return True


def spawn_reinforcement_monster(game, pos=None, near_gate=True, wave_spawned_positions=None, candidate_cache=None):
    """안전 조건(거리·시야·충돌체)을 통과한 증원 몬스터 단일 스폰 (상한 16마리 준수, 임의 좌표 fallback 배제)"""
    # 1. 생존 몬스터 상한(16마리, 보스 포함, 시체 제외) 검사
    alive_monsters = [m for m in getattr(game, 'monsters', []) if getattr(m, 'hp', 1) > 0 and not getattr(m, 'is_corpse', False)]
    if len(alive_monsters) >= 16:
        return None

    # 2. 플레이어 시점 및 FOV 정보 조회
    px, py, pz = 0.0, 0.0, 0.0
    cam_h = getattr(getattr(game, 'player', None), 'heading', 0.0)
    hfov = getattr(game, 'base_fov', 96.0)

    if hasattr(game, 'camera') and game.camera:
        if hasattr(game.camera, 'getX'):
            px, py, pz = game.camera.getX(), game.camera.getY(), game.camera.getZ()
        if hasattr(game.camera, 'getH'):
            try:
                cam_h = game.camera.getH()
            except Exception:
                pass
    elif hasattr(game, 'player') and hasattr(game.player, 'pos'):
        px, py = game.player.pos.x, game.player.pos.y

    if hasattr(game, 'camLens') and game.camLens and hasattr(game.camLens, 'getFov'):
        try:
            f = game.camLens.getFov()
            hfov = f[0] if hasattr(f, '__getitem__') else f
        except Exception:
            pass

    # 3. 몬스터 종 및 정예 여부 결정 (기존 가중치 28%, 26%, 18%, 8%, 20% 및 정예 20% 유지)
    types = [AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, LongBlackSerpent, SkeletalDobermanHellhound]
    weights = [0.28, 0.26, 0.18, 0.08, 0.20]
    cls = random.choices(types, weights=weights, k=1)[0]
    is_elite = (random.random() < 0.20)
    col_radius = get_monster_collision_radius(cls, is_elite=is_elite)

    # 4. 위치 결정
    chosen_pos = None
    if pos is not None:
        if is_spawn_position_safe(game, pos[0], pos[1], col_radius, px, py, pz, cam_h, hfov, wave_spawned_positions):
            chosen_pos = pos
        else:
            return None
    else:
        if near_gate:
            if candidate_cache is not None:
                cands = list(candidate_cache)
            else:
                cands = get_gate_corridor_candidates(getattr(game, 'escape_pos', None), min_dist=10.0, max_dist=30.0)
        else:
            cands = []

        if not cands:
            return None

        # 후보들을 셔플하여 첫 번째 안전한 후보 선정
        shuffled = list(cands)
        random.shuffle(shuffled)
        for cand in shuffled:
            if is_spawn_position_safe(game, cand[0], cand[1], col_radius, px, py, pz, cam_h, hfov, wave_spawned_positions):
                chosen_pos = cand
                break

    if chosen_pos is None:
        # 안전한 후보가 없을 시 임의 좌표 강제 출현 없이 None 반환 (정상 실패 처리)
        return None

    # 5. 안전 위치에 실제 몬스터 모델 생성
    render_node = getattr(game, 'render', None)
    monster = cls(render_node, chosen_pos[0], chosen_pos[1])
    stage = getattr(game, 'current_stage', 1)
    stage_hp_mult = 1.0 + (stage - 1) * 0.25
    monster.max_hp = int(monster.max_hp * stage_hp_mult)
    monster.hp = monster.max_hp
    if is_elite:
        apply_elite_mutation(monster, game)
    if hasattr(game, 'monsters'):
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
