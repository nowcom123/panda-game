"""
Collision Detection & Resolution Module
그리드 공간 분할 해시 기반 주변 충돌체 고속 필터링 및 원형-AABB 연속 슬라이딩 해결
"""

import math
from constants import (
    CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, PLAYER_RADIUS,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK, WALL_THICKNESS
)


_CUSTOM_COLLIDERS = []


def register_custom_collider(box):
    """(min_x, min_y, max_x, max_y) 형태의 정적 충돌 박스 등록"""
    if box not in _CUSTOM_COLLIDERS:
        _CUSTOM_COLLIDERS.append(box)


def clear_custom_colliders():
    """등록된 모든 커스텀 충돌체 초기화"""
    _CUSTOM_COLLIDERS.clear()


def get_nearby_colliders(chunks, px, py, search_dist=2.5):
    """그리드 셀 해시 기반 주변 충돌체 추출 (600개 전수검사 -> 8~12개 즉시 반환) 및 커스텀 충돌체 결합"""
    min_gx = int(math.floor((px - search_dist) / CELL_SIZE))
    max_gx = int(math.floor((px + search_dist) / CELL_SIZE))
    min_gy = int(math.floor((py - search_dist) / CELL_SIZE))
    max_gy = int(math.floor((py + search_dist) / CELL_SIZE))

    nearby = []
    for gx in range(min_gx, max_gx + 1):
        for gy in range(min_gy, max_gy + 1):
            cx = gx // CHUNK_CELLS
            cy = gy // CHUNK_CELLS
            chunk = chunks.get((cx, cy))
            if chunk and hasattr(chunk, 'cell_colliders'):
                cols = chunk.cell_colliders.get((gx, gy))
                if cols:
                    nearby.extend(cols)

    # 탈출 관문 등 특수 오브젝트의 커스텀 AABB 충돌체 검사
    if _CUSTOM_COLLIDERS:
        for c in _CUSTOM_COLLIDERS:
            if not (c[2] < px - search_dist or c[0] > px + search_dist or c[3] < py - search_dist or c[1] > py + search_dist):
                nearby.append(c)

    return nearby


def resolve_collision(chunks, curr_x, curr_y, dx, dy, radius=PLAYER_RADIUS):
    """
    정밀 원형-AABB 최단거리 밀어내기(Push-out) 및 연속 벽면/모서리 슬라이딩 해결
    - 공간 분할 인덱스로 현재 위치 주변 충돌체만 즉각 필터링
    - 모서리(Corner) 접촉 시 법선 투영 기반 접선 슬라이딩(Deflection) 적용으로 모서리 쐐기 끼임 방지
    - 4회 완화(Relaxation) 반복 적용으로 벽 파고들기 및 끼임 완벽 차단
    - 반경 절반 이하의 이동 간격으로 얇은 벽 통과 방지, 맵 외곽 경계 클램핑
    """
    r = radius
    max_d = max(abs(dx), abs(dy))
    margin = r + max_d + 0.8
    colliders = get_nearby_colliders(chunks, curr_x, curr_y, search_dist=margin)
    if not colliders:
        # 외곽 절대 경계 클램핑
        min_bound = MAP_MIN_CHUNK * CHUNK_SIZE + WALL_THICKNESS * 0.5 + r
        max_bound = (MAP_MAX_CHUNK + 1) * CHUNK_SIZE - WALL_THICKNESS * 0.5 - r
        return max(min_bound, min(max_bound, curr_x + dx)), max(min_bound, min(max_bound, curr_y + dy))

    # Query once; short steps cannot jump over thin walls between endpoints.
    steps = max(1, math.ceil(math.hypot(dx, dy) / max(0.025, r * 0.5)))
    # Extreme frame stalls stop safely after a bounded amount of travel.
    count = min(steps, 512)
    step_x, step_y = dx / steps, dy / steps
    px, py = curr_x, curr_y
    colliders = list(dict.fromkeys(colliders))
    for _ in range(count):
        px, py = _resolve_collision_step(colliders, px, py, step_x, step_y, r)
    return px, py


def _resolve_collision_step(colliders, curr_x, curr_y, dx, dy, radius):
    r = radius
    # 1. 초기 위치 침투 복구 (Penetration Recovery)
    sx, sy = curr_x, curr_y
    for min_x, min_y, max_x, max_y in colliders:
        cx = max(min_x, min(sx, max_x))
        cy = max(min_y, min(sy, max_y))
        vx = sx - cx
        vy = sy - cy
        d_sq = vx * vx + vy * vy
        if d_sq < r * r:
            if d_sq > 1e-8:
                d = math.sqrt(d_sq)
                push = r - d
                sx += (vx / d) * push
                sy += (vy / d) * push
            else:
                d_l = sx - (min_x - r)
                d_r = (max_x + r) - sx
                d_d = sy - (min_y - r)
                d_u = (max_y + r) - sy
                m = min(d_l, d_r, d_d, d_u)
                if m == d_l:
                    sx = min_x - r
                elif m == d_r:
                    sx = max_x + r
                elif m == d_d:
                    sy = min_y - r
                else:
                    sy = max_y + r

    # 2. 이동 벡터에 모서리/벽면 접선 슬라이딩(Tangential Deflection) 적용
    eff_dx, eff_dy = dx, dy
    if (dx * dx + dy * dy) > 1e-8:
        # 이동하려는 가상 위치에서 충돌체와의 접촉 법선 검사
        target_x = sx + dx
        target_y = sy + dy
        for min_x, min_y, max_x, max_y in colliders:
            cx = max(min_x, min(target_x, max_x))
            cy = max(min_y, min(target_y, max_y))
            vx = target_x - cx
            vy = target_y - cy
            d_sq = vx * vx + vy * vy
            if d_sq < r * r and d_sq > 1e-8:
                d = math.sqrt(d_sq)
                nx = vx / d
                ny = vy / d
                # 이동 벡터와 법선의 내적: 안쪽으로 향하는 성분 제거하여 슬라이딩
                dot = eff_dx * nx + eff_dy * ny
                if dot < 0.0:
                    eff_dx -= dot * nx
                    eff_dy -= dot * ny

    px = sx + eff_dx
    py = sy + eff_dy

    # 3. 4회 Relaxation 반복 적용으로 엄격한 AABB 겹침 해소
    for _ in range(4):
        hit = False
        for min_x, min_y, max_x, max_y in colliders:
            cx = max(min_x, min(px, max_x))
            cy = max(min_y, min(py, max_y))
            vx = px - cx
            vy = py - cy
            d_sq = vx * vx + vy * vy
            if d_sq < r * r:
                hit = True
                if d_sq > 1e-8:
                    d = math.sqrt(d_sq)
                    push = r - d
                    px += (vx / d) * push
                    py += (vy / d) * push
                else:
                    d_l = px - (min_x - r)
                    d_r = (max_x + r) - px
                    d_d = py - (min_y - r)
                    d_u = (max_y + r) - py
                    m = min(d_l, d_r, d_d, d_u)
                    if m == d_l:
                        px = min_x - r
                    elif m == d_r:
                        px = max_x + r
                    elif m == d_d:
                        py = min_y - r
                    else:
                        py = max_y + r
        if not hit:
            break

    # 4. 맵 외곽 절대 경계 내부로 클램핑 (252m x 252m 경계 밖 추락/탈출 100% 차단)
    min_bound = MAP_MIN_CHUNK * CHUNK_SIZE + WALL_THICKNESS * 0.5 + radius
    max_bound = (MAP_MAX_CHUNK + 1) * CHUNK_SIZE - WALL_THICKNESS * 0.5 - radius
    px = max(min_bound, min(max_bound, px))
    py = max(min_bound, min(max_bound, py))

    return px, py


def raycast_walls(chunks, ray_origin, ray_dir, max_dist=55.0):
    """광선(Ray)과 월드 내 AABB 벽체 충돌체 간 최단 교차 거리 및 타격 지점 고속 Slab 연산"""
    px, py = ray_origin.x, ray_origin.y
    dx, dy = ray_dir.x, ray_dir.y
    if (dx * dx + dy * dy) < 1e-8:
        return max_dist, None

    colliders = set()
    step_samples = (0.0, 8.0, 16.0, 24.0, 32.0, max_dist)
    for s in step_samples:
        sx = px + dx * s
        sy = py + dy * s
        for col in get_nearby_colliders(chunks, sx, sy, search_dist=5.5):
            colliders.add(col)

    inv_dx = (1.0 / dx) if abs(dx) >= 1e-6 else None
    inv_dy = (1.0 / dy) if abs(dy) >= 1e-6 else None
    closest_t = max_dist

    for min_x, min_y, max_x, max_y in colliders:
        if (max_x - min_x) < 0.5 and (max_y - min_y) < 0.5:
            continue

        # X축 Slab 판정
        if inv_dx is None:
            if px < min_x or px > max_x:
                continue
            tx_min, tx_max = 0.0, max_dist
        else:
            t1 = (min_x - px) * inv_dx
            t2 = (max_x - px) * inv_dx
            if t1 > t2:
                tx_min, tx_max = t2, t1
            else:
                tx_min, tx_max = t1, t2

        # Y축 Slab 판정
        if inv_dy is None:
            if py < min_y or py > max_y:
                continue
            ty_min, ty_max = 0.0, max_dist
        else:
            t1 = (min_y - py) * inv_dy
            t2 = (max_y - py) * inv_dy
            if t1 > t2:
                ty_min, ty_max = t2, t1
            else:
                ty_min, ty_max = t1, t2

        t0 = max(0.0, tx_min, ty_min)
        t1 = min(max_dist, tx_max, ty_max)

        if 0.2 < t0 <= t1 and t0 < closest_t:
            hit_z = ray_origin.z + ray_dir.z * t0
            if 0.0 <= hit_z <= 13.0:
                closest_t = t0

    if closest_t < max_dist:
        return closest_t, ray_origin + ray_dir * closest_t
    return max_dist, None
