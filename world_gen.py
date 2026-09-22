import math
import collections
import functools

def zone_hash(mx, my):
    """3x3 매크로 구역 단위 고유 해시 생성"""
    return ((mx * 73856093) ^ (my * 19349663) ^ 0x5bd1e995) & 0x7FFFFFFF


@functools.lru_cache(maxsize=4096)
def get_edge_types(gx, gy):
    """
    셀 (gx, gy)의 북쪽 경계(h_edge) 및 동쪽 경계(v_edge) 타입 판정
    반환값: 0 = 완전 개방, 1 = 솔리드 2단 벽, 2 = 출입문 (1단 인방 + 2단 상단벽)
    
    [완전 닫힌 방 & 무한 복도 규칙]:
    1. 벽으로 방을 형성할 경우 사방이 벽체로 100% 둘러싸인 '완전한 닫힌 공간'을 형성하며,
       복도를 향해 정확히 1개의 출입문(2)을 둡니다. (고립벽/불완전 벽 0%)
    2. 중심 십자 복도(lx=1, ly=1)는 항상 사통팔달로 영구 개방됩니다.
    """
    mx, my = gx // 3, gy // 3
    lx, ly = gx % 3, gy % 3
    h = zone_hash(mx, my)

    # 코너별 방 구성 패턴 (0, 1, 3: 4개 코너 모두 닫힌 방, 2: 2개 닫힌 방 + 2개 개방)
    pattern = h % 4
    room_sw = True if pattern in (0, 1, 3) else False
    room_se = True if pattern in (0, 2, 3) else False
    room_nw = True if pattern in (0, 2, 3) else False
    room_ne = True if pattern in (0, 1, 3) else False

    # 문 위치 결정 (각 닫힌 방마다 복도 쪽 면 중 정확히 1개 면에 출입문 배치)
    door_sw = (h >> 2) & 1
    door_se = (h >> 3) & 1
    door_nw = (h >> 4) & 1
    door_ne = (h >> 5) & 1

    # 1. 북쪽 수평 경계 (Horizontal Edge: y = (gy + 1) * CELL_SIZE)
    h_edge = 0
    if ly == 2:
        # 매크로 구역 간 북쪽 경계: 중심 통로(lx=1)만 개방, 코너 방 상단은 솔리드 외벽
        h_edge = 0 if lx == 1 else 1
    elif ly == 0:
        if lx == 1:
            h_edge = 0  # 남북 메인 복도는 항상 개방
        elif lx == 0:
            # SW 코너 방 북쪽면 (문 또는 솔리드 벽)
            h_edge = (2 if door_sw == 0 else 1) if room_sw else 0
        elif lx == 2:
            # SE 코너 방 북쪽면
            h_edge = (2 if door_se == 0 else 1) if room_se else 0
    elif ly == 1:
        if lx == 1:
            h_edge = 0  # 남북 메인 복도는 항상 개방
        elif lx == 0:
            # NW 코너 방 남쪽면
            h_edge = (2 if door_nw == 0 else 1) if room_nw else 0
        elif lx == 2:
            # NE 코너 방 남쪽면
            h_edge = (2 if door_ne == 0 else 1) if room_ne else 0

    # 2. 동쪽 수직 경계 (Vertical Edge: x = (gx + 1) * CELL_SIZE)
    v_edge = 0
    if lx == 2:
        # 매크로 구역 간 동쪽 경계: 중심 통로(ly=1)만 개방, 코너 방 우측은 솔리드 외벽
        v_edge = 0 if ly == 1 else 1
    elif lx == 0:
        if ly == 1:
            v_edge = 0  # 동서 메인 복도는 항상 개방
        elif ly == 0:
            # SW 코너 방 동쪽면
            v_edge = (2 if door_sw == 1 else 1) if room_sw else 0
        elif ly == 2:
            # NW 코너 방 동쪽면
            v_edge = (2 if door_nw == 1 else 1) if room_nw else 0
    elif lx == 1:
        if ly == 1:
            v_edge = 0  # 동서 메인 복도는 항상 개방
        elif ly == 0:
            # SE 코너 방 서쪽면
            v_edge = (2 if door_se == 1 else 1) if room_se else 0
        elif ly == 2:
            # NE 코너 방 서쪽면
            v_edge = (2 if door_ne == 1 else 1) if room_ne else 0

    return h_edge, v_edge


def is_passable(gx1, gy1, gx2, gy2):
    """인접한 두 그리드 셀 간의 이동 가능 여부 (솔리드 벽(1) 차단, 개방(0) 및 문(2) 통과)"""
    if gx2 == gx1 and gy2 == gy1 + 1:
        he, _ = get_edge_types(gx1, gy1)
        return he != 1
    elif gx2 == gx1 and gy2 == gy1 - 1:
        he, _ = get_edge_types(gx2, gy2)
        return he != 1
    elif gx2 == gx1 + 1 and gy2 == gy1:
        _, ve = get_edge_types(gx1, gy1)
        return ve != 1
    elif gx2 == gx1 - 1 and gy2 == gy1:
        _, ve = get_edge_types(gx2, gy2)
        return ve != 1
    return False


def find_cell_path(start, goal, max_depth=20):
    """그리드 BFS 기반 최단 복도/출입문 경로 탐색 (0.1ms 초고속 연산)"""
    if start == goal:
        return [start]
    queue = collections.deque([start])
    came_from = {start: None}

    while queue:
        curr = queue.popleft()
        if curr == goal:
            break
        gx, gy = curr
        for nxt in ((gx, gy + 1), (gx, gy - 1), (gx + 1, gy), (gx - 1, gy)):
            if nxt not in came_from and abs(nxt[0] - start[0]) <= max_depth and abs(nxt[1] - start[1]) <= max_depth:
                if is_passable(gx, gy, nxt[0], nxt[1]):
                    came_from[nxt] = curr
                    queue.append(nxt)

    if goal not in came_from:
        return []

    path = []
    c = goal
    while c is not None:
        path.append(c)
        c = came_from[c]
    path.reverse()
    return path


def check_line_of_sight(x1, y1, x2, y2, colliders):
    """Liang-Barsky 고속 선분-AABB 교차 판정 (직선 시야 확보 여부 판정)"""
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 0.2:
        return True
    min_sx, max_sx = min(x1, x2), max(x1, x2)
    min_sy, max_sy = min(y1, y2), max(y1, y2)

    for min_x, min_y, max_x, max_y in colliders:
        # 촛대와 같은 소형 오브젝트(가로/세로 0.5m 미만)는 시선 차단 벽체가 아니므로 제외
        if (max_x - min_x) < 0.5 and (max_y - min_y) < 0.5:
            continue
        if min_sx > max_x or max_sx < min_x or min_sy > max_y or max_sy < min_y:
            continue
        p = [-dx, dx, -dy, dy]
        q = [x1 - min_x, max_x - x1, y1 - min_y, max_y - y1]
        t0, t1 = 0.0, 1.0
        hit = True
        for i in range(4):
            if p[i] == 0:
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
        if hit and t0 <= t1:
            return False
    return True
