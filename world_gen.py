import math
import collections
import functools

def zone_hash(mx, my):
    """3x3 매크로 구역 단위 고유 해시 생성"""
    return ((mx * 73856093) ^ (my * 19349663) ^ 0x5bd1e995) & 0x7FFFFFFF


def get_zone_type(mx, my):
    """
    3x3 매크로 구역의 건축 유형 결정:
    - 0: 클래식 넓은 복도 및 1개의 독립 룸 (정사각형 중첩 기둥 현상 제거)
    - 1: 18m x 18m 대형 백룸 홀 (중앙 1기둥)
    - 2: 12m x 18m 와이드 백룸 룸 (lx=0,1 개방 공간)
    - 3: 18m x 12m 가로형 와이드 백룸 룸 (ly=0,1 개방 공간)
    - 4: 18m x 18m 완전 개방형 '빈 공터' (기둥 0개, 내부 벽 0개, 시원하게 트인 광장)
    - 5: 사방 연결 초대형 '빈 공터' (기둥 0개, 인접 구역과 통째로 이어지는 광활한 평지)
    """
    if mx == 0 and my == 0:
        return 4  # 초기 스폰 구역도 시원하고 쾌적한 빈 공터 보장
    h = zone_hash(mx, my)
    # 빈 공터(타입 4, 5)가 약 40% 이상 생성되도록 가중치 부여
    r = (h >> 4) % 10
    if r in (0, 1):
        return 0  # 클래식 넓은 복도 (20%)
    elif r == 2:
        return 1  # 중앙 1기둥 대형 홀 (10%)
    elif r == 3:
        return 2  # 와이드 룸 (10%)
    elif r == 4:
        return 3  # 가로 와이드 룸 (10%)
    elif r in (5, 6, 7):
        return 4  # 18m x 18m 빈 공터 (30%)
    else:
        return 5  # 사방 연결 초대형 빈 공터 (20%)


def cell_has_pillar(gx, gy):
    """대형 방 내부의 상징적인 백룸 콘크리트 지지 기둥 배치 판정 (빈 공터 및 복도는 기둥 절대 배제)"""
    if gx == 1 and gy == 1:
        return False  # 플레이어 초기 스폰 위치 기둥 배제
    mx, my = gx // 3, gy // 3
    lx, ly = gx % 3, gy % 3
    zt = get_zone_type(mx, my)

    # 빈 공터(타입 4, 5) 및 일반 복도(타입 0)는 기둥을 100% 배치하지 않음 (탁 트인 빈 공터 보장)
    if zt in (0, 4, 5):
        return False

    # 오직 타입 1, 2, 3에서만 정중앙에 1개의 얇은 기둥만 허용 (정사각형 중첩 방지)
    if zt == 1 and lx == 1 and ly == 1:
        return True  # 18m x 18m 대형 홀 정중앙 지지 기둥
    if zt == 2 and lx == 0 and ly == 1:
        return True  # 12m x 18m 와이드 룸 중앙 기둥
    if zt == 3 and lx == 1 and ly == 0:
        return True  # 18m x 12m 와이드 룸 중앙 기둥
    return False


@functools.lru_cache(maxsize=8192)
def get_edge_types(gx, gy):
    """
    셀 (gx, gy)의 북쪽 경계(h_edge) 및 동쪽 경계(v_edge) 타입 판정
    반환값: 0 = 완전 개방, 1 = 솔리드 2단 벽, 2 = 출입문 (1단 인방 + 2단 상단벽)
    
    [백룸 빈 공터 & 대형 홀 & 무한 복도 규칙]:
    1. 빈 공터(타입 4, 5)는 내부 벽을 완전 제거(0)하여 18m~36m 광활한 개방 공간을 형성합니다.
    2. 클래식 복도(타입 0)도 4개 모서리 정사각형 방이 겹치지 않도록 최대 1개 방만 배치합니다.
    3. 모든 구역은 중앙 연결 통로 및 출입문을 통해 100% 끊김 없이 사통팔달로 상호 연결됩니다.
    """
    mx, my = gx // 3, gy // 3
    lx, ly = gx % 3, gy % 3
    zt = get_zone_type(mx, my)
    h = zone_hash(mx, my)

    # 기본값
    h_edge = 1
    v_edge = 1

    if zt == 0:
        # [타입 0] 넓은 복도 & 최대 1개 독립 오피스 (정사각형 방 겹침 제거)
        pattern = h % 5
        room_sw = (pattern == 0)
        room_se = (pattern == 1)
        room_nw = (pattern == 2)
        room_ne = (pattern == 3)
        # pattern == 4 이면 방이 전혀 없는 완전 개방형 십자 대로

        door_sw = (h >> 2) & 1
        door_se = (h >> 3) & 1
        door_nw = (h >> 4) & 1
        door_ne = (h >> 5) & 1

        if ly == 2:
            h_edge = 0 if lx == 1 else (1 if room_nw or room_ne else 0)
        elif ly == 0:
            if lx == 1:
                h_edge = 0
            elif lx == 0:
                h_edge = (2 if door_sw == 0 else 1) if room_sw else 0
            elif lx == 2:
                h_edge = (2 if door_se == 0 else 1) if room_se else 0
        elif ly == 1:
            if lx == 1:
                h_edge = 0
            elif lx == 0:
                h_edge = (2 if door_nw == 0 else 1) if room_nw else 0
            elif lx == 2:
                h_edge = (2 if door_ne == 0 else 1) if room_ne else 0

        if lx == 2:
            v_edge = 0 if ly == 1 else (1 if room_se or room_ne else 0)
        elif lx == 0:
            if ly == 1:
                v_edge = 0
            elif ly == 0:
                v_edge = (2 if door_sw == 1 else 1) if room_sw else 0
            elif ly == 2:
                v_edge = (2 if door_nw == 1 else 1) if room_nw else 0
        elif lx == 1:
            if ly == 1:
                v_edge = 0
            elif ly == 0:
                v_edge = (2 if door_se == 1 else 1) if room_se else 0
            elif ly == 2:
                v_edge = (2 if door_ne == 1 else 1) if room_ne else 0

    elif zt == 1:
        # [타입 1] 18m x 18m 초대형 백룸 오픈 홀
        if ly == 2:
            h_edge = 2 if lx == 1 else 1
        else:
            h_edge = 0

        if lx == 2:
            v_edge = 2 if ly == 1 else 1
        else:
            v_edge = 0

    elif zt == 2:
        # [타입 2] 12m x 18m 와이드 백룸 룸 (lx=0,1) + 동쪽 연결 복도 (lx=2)
        if ly == 2:
            h_edge = 0 if lx == 2 else (2 if lx == 1 else 1)
        else:
            h_edge = 0

        if lx == 2:
            v_edge = 0 if ly == 1 else 1
        elif lx == 1:
            v_edge = 2 if ly == 1 else 1
        elif lx == 0:
            v_edge = 0

    elif zt == 3:
        # [타입 3] 18m x 12m 가로형 와이드 백룸 룸 (ly=0,1) + 북쪽 연결 복도 (ly=2)
        if lx == 2:
            v_edge = 0 if ly == 2 else (2 if ly == 1 else 1)
        else:
            v_edge = 0

        if ly == 2:
            h_edge = 0 if lx == 1 else 1
        elif ly == 1:
            h_edge = 2 if lx == 1 else 1
        elif ly == 0:
            h_edge = 0

    elif zt == 4:
        # [타입 4] 18m x 18m 완전 개방형 '빈 공터' (Empty Plaza)
        # 내부 벽 0개, 기둥 0개로 광활하고 시원하게 트인 평지
        if ly == 2:
            h_edge = 0 if lx == 1 else 1  # 북쪽 중앙 복도 개방
        else:
            h_edge = 0

        if lx == 2:
            v_edge = 0 if ly == 1 else 1  # 동쪽 중앙 복도 개방
        else:
            v_edge = 0

    elif zt == 5:
        # [타입 5] 사방 완전 개방 초대형 '빈 공터' (Grand Open Plaza)
        # 내부 벽 0개, 기둥 0개이며, 경계도 2칸씩 널찍하게 뚫려 인접 구역과 거대한 빈 공터 형성
        if ly == 2:
            h_edge = 0 if lx in (0, 1) else 1
        else:
            h_edge = 0

        if lx == 2:
            v_edge = 0 if ly in (0, 1) else 1
        else:
            v_edge = 0

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
