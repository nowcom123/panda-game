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
    정밀 원형-AABB 최단거리 밀어내기(Push-out) 및 연속 벽면 슬라이딩 해결
    - 공간 분할 인덱스로 현재 위치 주변 충돌체만 즉각 필터링
    - 3회 완화(Relaxation) 반복 적용으로 벽 파고들기 및 끼임 완벽 차단
    """
    max_d = max(abs(dx), abs(dy))
    margin = radius + max_d + 0.6
    colliders = get_nearby_colliders(chunks, curr_x, curr_y, search_dist=margin)
    px = curr_x + dx
    py = curr_y + dy
    r = radius

    min_xb = min(curr_x, px) - margin
    max_xb = max(curr_x, px) + margin
    min_yb = min(curr_y, py) - margin
    max_yb = max(curr_y, py) + margin

    active_colliders = [
        c for c in colliders
        if not (c[2] < min_xb or c[0] > max_xb or c[3] < min_yb or c[1] > max_yb)
    ]
    if not active_colliders:
        return px, py

    for _ in range(3):
        hit = False
        for min_x, min_y, max_x, max_y in active_colliders:
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

    # 맵 외곽 절대 경계 내부로 클램핑 (252m x 252m 경계 밖 추락/탈출 100% 차단)
    min_bound = MAP_MIN_CHUNK * CHUNK_SIZE + WALL_THICKNESS * 0.5 + radius
    max_bound = (MAP_MAX_CHUNK + 1) * CHUNK_SIZE - WALL_THICKNESS * 0.5 - radius
    px = max(min_bound, min(max_bound, px))
    py = max(min_bound, min(max_bound, py))

    return px, py


def raycast_walls(chunks, ray_origin, ray_dir, max_dist=55.0):
    """광선(Ray)과 월드 내 AABB 벽체 충돌체 간 최단 교차 거리 및 타격 지점 정밀 계산"""
    px, py = ray_origin.x, ray_origin.y
    dx, dy = ray_dir.x, ray_dir.y
    if math.hypot(dx, dy) < 1e-4:
        return max_dist, None

    colliders = set()
    step_samples = (0.0, 8.0, 16.0, 24.0, 32.0, max_dist)
    for s in step_samples:
        sx = px + dx * s
        sy = py + dy * s
        for col in get_nearby_colliders(chunks, sx, sy, search_dist=5.5):
            colliders.add(col)

    closest_t = max_dist
    for min_x, min_y, max_x, max_y in colliders:
        if (max_x - min_x) < 0.5 and (max_y - min_y) < 0.5:
            continue
        p = [-dx, dx, -dy, dy]
        q = [px - min_x, max_x - px, py - min_y, max_y - py]
        t0, t1 = 0.0, max_dist
        hit = True
        for i in range(4):
            if abs(p[i]) < 1e-6:
                if q[i] < 0:
                    hit = False
                    break
            else:
                t = q[i] / p[i]
                if p[i] < 0:
                    if t > t1:
                        hit = False
                        break
                    if t > t0:
                        t0 = t
                else:
                    if t < t0:
                        hit = False
                        break
                    if t < t1:
                        t1 = t
        if hit and 0.2 < t0 <= t1 and t0 < closest_t:
            hit_z = ray_origin.z + ray_dir.z * t0
            if 0.0 <= hit_z <= 13.0:
                closest_t = t0

    if closest_t < max_dist:
        return closest_t, ray_origin + ray_dir * closest_t
    return max_dist, None
