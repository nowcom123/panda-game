"""
Collision Detection & Resolution Module (Continuous & Border-Sealed)
- 그리드 기반 공간 해싱으로 주변 충돌체 고속 필터링
- 미로딩 청크 및 맵 경계 셀 자동 차단 배리어 생성 (맵 이탈 100% 원천 방지)
- 서브스텝 연속 충돌 검사(Continuous Collision Resolution)로 고속 이동 시 벽 관통 터널링 제거
- 3회 이완(Relaxation) 반복으로 얇은 벽 및 모서리 끼임 완전 해소
"""

import math
from constants import (
    CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, PLAYER_RADIUS,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK, WALL_THICKNESS, WALL_HEIGHT
)


def first_world_hit(chunks, start, end):
    """볼트 이동 선분의 첫 지형 충돌 위치를 0~1 비율로 반환합니다."""
    nearest = None
    floor_z, ceiling_z = 0.06, WALL_HEIGHT - 0.25
    if start.z <= floor_z or start.z >= ceiling_z:
        nearest = 0.0
    elif end.z <= floor_z:
        nearest = (floor_z - start.z) / (end.z - start.z)
    elif end.z >= ceiling_z:
        nearest = (ceiling_z - start.z) / (end.z - start.z)

    # 종점 주변만 검사하면 한 프레임 안에 통과한 얇은 벽을 놓치게 됩니다.
    if chunks is not None:
        dx, dy = end.x - start.x, end.y - start.y
        cols = get_nearby_colliders(
            chunks, (start.x + end.x) * 0.5, (start.y + end.y) * 0.5,
            search_dist=max(abs(dx), abs(dy)) * 0.5 + 0.01
        )
        for min_x, min_y, max_x, max_y in cols:
            entry, leave = 0.0, 1.0
            for origin, delta, low, high in (
                (start.x, dx, min_x, max_x), (start.y, dy, min_y, max_y)
            ):
                if abs(delta) < 1e-10:
                    if origin < low or origin > high:
                        break
                else:
                    a, b = (low - origin) / delta, (high - origin) / delta
                    entry = max(entry, min(a, b))
                    leave = min(leave, max(a, b))
                    if entry > leave:
                        break
            else:
                if nearest is None or entry < nearest:
                    nearest = entry
    return nearest


def ray_spheres_hit(ray_o, ray_d, targets, max_dist):
    """정규화된 광선과 피격 구체들의 가장 가까운 표면 교차 거리를 반환합니다."""
    nearest = math.inf
    for x, y, z, radius in targets:
        dx, dy, dz = x - ray_o.x, y - ray_o.y, z - ray_o.z
        projection = dx * ray_d.x + dy * ray_d.y + dz * ray_d.z
        offset_sq = dx * dx + dy * dy + dz * dz - radius * radius
        discriminant = projection * projection - offset_sq
        if discriminant < 0.0:
            continue
        half_chord = math.sqrt(discriminant)
        if projection + half_chord < 0.0:
            continue
        entry = max(0.0, projection - half_chord)
        if entry <= max_dist:
            nearest = min(nearest, entry)
    return (True, nearest) if math.isfinite(nearest) else (False, 999.0)


def get_nearby_colliders(chunks, px, py, search_dist=2.5):
    """그리드 공간 해싱 기반 주변 충돌체 검색 및 미로딩 경계 차단"""
    min_gx = int(math.floor((px - search_dist) / CELL_SIZE))
    max_gx = int(math.floor((px + search_dist) / CELL_SIZE))
    min_gy = int(math.floor((py - search_dist) / CELL_SIZE))
    max_gy = int(math.floor((py + search_dist) / CELL_SIZE))

    min_map_gx = MAP_MIN_CHUNK * CHUNK_CELLS
    max_map_gx = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1
    min_map_gy = MAP_MIN_CHUNK * CHUNK_CELLS
    max_map_gy = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1

    nearby = []
    for gx in range(min_gx, max_gx + 1):
        for gy in range(min_gy, max_gy + 1):
            # 맵 외부 또는 아직 로딩되지 않은 청크의 셀은 통행 불가 솔리드 박스로 차단
            if gx < min_map_gx or gx > max_map_gx or gy < min_map_gy or gy > max_map_gy:
                c_min_x = gx * CELL_SIZE
                c_max_x = (gx + 1) * CELL_SIZE
                c_min_y = gy * CELL_SIZE
                c_max_y = (gy + 1) * CELL_SIZE
                nearby.append((c_min_x, c_min_y, c_max_x, c_max_y))
                continue

            cx = gx // CHUNK_CELLS
            cy = gy // CHUNK_CELLS
            chunk = chunks.get((cx, cy))
            if chunk and hasattr(chunk, 'cell_colliders'):
                cols = chunk.cell_colliders.get((gx, gy))
                if cols:
                    nearby.extend(cols)
            elif chunk is None:
                # 미로딩 청크 경계면 진입 방지
                c_min_x = gx * CELL_SIZE
                c_max_x = (gx + 1) * CELL_SIZE
                c_min_y = gy * CELL_SIZE
                c_max_y = (gy + 1) * CELL_SIZE
                nearby.append((c_min_x, c_min_y, c_max_x, c_max_y))

    return nearby


def _resolve_single_step(active_colliders, curr_x, curr_y, dx, dy, radius):
    """단일 서브스텝 원-AABB 밀어내기 충돌 해석"""
    px = curr_x + dx
    py = curr_y + dy
    r = radius

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
                    # 박스 내부 침투 시 진입 반대 방향으로 즉시 복원
                    d_l = px - (min_x - r)
                    d_r = (max_x + r) - px
                    d_d = py - (min_y - r)
                    d_u = (max_y + r) - py
                    m = min(d_l, d_r, d_d, d_u)
                    if m == d_l: px = min_x - r
                    elif m == d_r: px = max_x + r
                    elif m == d_d: py = min_y - r
                    else: py = max_y + r
        if not hit:
            break
    return px, py


def resolve_collision(chunks, curr_x, curr_y, dx, dy, radius=PLAYER_RADIUS):
    """
    연속 충돌 해석(Continuous Collision Resolution) 및 맵 이탈 방지
    - 이동 거리에 따라 0.18m 이하의 세밀한 서브스텝으로 분할하여 벽 관통 터널링 100% 방지
    - 252m x 252m 맵 외곽 내벽 좌표로 엄격한 바운딩 클램핑
    """
    dist = math.hypot(dx, dy)
    margin = radius + max(abs(dx), abs(dy)) + 0.6
    colliders = get_nearby_colliders(chunks, curr_x, curr_y, search_dist=margin)

    min_xb = min(curr_x, curr_x + dx) - margin
    max_xb = max(curr_x, curr_x + dx) + margin
    min_yb = min(curr_y, curr_y + dy) - margin
    max_yb = max(curr_y, curr_y + dy) + margin

    active_colliders = [
        c for c in colliders
        if not (c[2] < min_xb or c[0] > max_xb or c[3] < min_yb or c[1] > max_yb)
    ]

    if not active_colliders:
        px = curr_x + dx
        py = curr_y + dy
    else:
        # 서브스텝 분할: 한 프레임에 벽 두께(0.8m)의 절반 이상을 순간 이동하지 못하도록 제어
        max_step = 0.18
        steps = max(1, int(math.ceil(dist / max_step)))
        step_dx = dx / steps
        step_dy = dy / steps
        px, py = curr_x, curr_y
        for _ in range(steps):
            px, py = _resolve_single_step(active_colliders, px, py, step_dx, step_dy, radius)

    # 맵 외곽 경계 벽 내로 클램핑 (252m x 252m 맵 외부 추락/탈출 100% 방지)
    min_bound = MAP_MIN_CHUNK * CHUNK_SIZE + WALL_THICKNESS * 0.5 + radius
    max_bound = (MAP_MAX_CHUNK + 1) * CHUNK_SIZE - WALL_THICKNESS * 0.5 - radius
    px = max(min_bound, min(max_bound, px))
    py = max(min_bound, min(max_bound, py))

    return px, py
