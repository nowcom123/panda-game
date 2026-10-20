"""
elevation.py - 3D Multi-level Architecture (복층), Slopes/Ramps (경사로), and Elevation Navigation

Provides:
- 3D Platform and Ramp definitions with exact spatial interpolation
- Procedural placement of elevated mezzanines, battle platforms, catwalks, and ramps
- Multi-level ground height queries get_floor_height(x, y, current_z)
- Multi-level pathfinding goal resolution get_pursuit_goal(monster_pos, player_pos)
- Support pillars, railings, and collision geometry for chunks
"""

import math
import functools
from panda3d.core import Vec3
from constants import CELL_SIZE, MAP_MIN_CHUNK, MAP_MAX_CHUNK
from world_gen import get_zone_type, zone_hash


PLATFORM_HEIGHT = 3.0    # 복층 플랫폼 기본 바닥 높이 (3.0m: 아래 2.65m 통로 확보, 위 10.0m 개방 공간)
PLATFORM_THICKNESS = 0.35 # 복층 슬래브 두께 (0.35m 단단한 콘크리트/철골 구조)
RAILING_HEIGHT = 0.95    # 안전 난간 높이 (0.95m: 사격 가능 및 낙하 방지)


class Platform:
    """복층(2층) 플랫폼 영역: 바닥면, 천장면, 지지 기둥, 안전 난간 보유"""
    def __init__(self, id_str, min_x, min_y, max_x, max_y, z=PLATFORM_HEIGHT, thickness=PLATFORM_THICKNESS, open_edges=None):
        self.id = id_str
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.z = z
        self.thickness = thickness
        self.open_edges = set(open_edges or [])  # 'north', 'south', 'east', 'west' (경사로 연결부 등 난간 개방)
        self.center_x = (min_x + max_x) * 0.5
        self.center_y = (min_y + max_y) * 0.5

    def contains(self, x, y, margin=0.0):
        return (self.min_x - margin <= x <= self.max_x + margin and
                self.min_y - margin <= y <= self.max_y + margin)


class Ramp:
    """1층과 2층을 부드럽게 잇는 3D 경사로 (Sloped Ramp)"""
    def __init__(self, id_str, min_x, min_y, max_x, max_y, z_bottom=0.0, z_top=PLATFORM_HEIGHT, direction='+y'):
        self.id = id_str
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.z_bottom = z_bottom
        self.z_top = z_top
        self.direction = direction  # '+y', '-y', '+x', '-x' (올라가는 방향)
        self.width = (max_x - min_x) if direction in ('+y', '-y') else (max_y - min_y)
        self.length = (max_y - min_y) if direction in ('+y', '-y') else (max_x - min_x)
        self.slope_pitch = math.degrees(math.atan2(z_top - z_bottom, max(0.01, self.length)))

    def contains(self, x, y, margin=0.0):
        return (self.min_x - margin <= x <= self.max_x + margin and
                self.min_y - margin <= y <= self.max_y + margin)

    def get_z(self, x, y):
        """(x, y) 위치에서의 경사면 높이 계산"""
        if self.direction == '+y':
            t = (y - self.min_y) / max(0.01, self.max_y - self.min_y)
        elif self.direction == '-y':
            t = (self.max_y - y) / max(0.01, self.max_y - self.min_y)
        elif self.direction == '+x':
            t = (x - self.min_x) / max(0.01, self.max_x - self.min_x)
        else:  # '-x'
            t = (self.max_x - x) / max(0.01, self.max_x - self.min_x)
        t = max(0.0, min(1.0, t))
        return self.z_bottom + t * (self.z_top - self.z_bottom)

    def get_entrance_pos(self):
        """경사로 시작 진입점 (1층 지면 레벨)"""
        if self.direction == '+y':
            return ((self.min_x + self.max_x) * 0.5, self.min_y + 0.6)
        elif self.direction == '-y':
            return ((self.min_x + self.max_x) * 0.5, self.max_y - 0.6)
        elif self.direction == '+x':
            return (self.min_x + 0.6, (self.min_y + self.max_y) * 0.5)
        else:
            return (self.max_x - 0.6, (self.min_y + self.max_y) * 0.5)

    def get_exit_pos(self):
        """경사로 최상단 출구 (2층 복층 플랫폼 연결점)"""
        if self.direction == '+y':
            return ((self.min_x + self.max_x) * 0.5, self.max_y - 0.3)
        elif self.direction == '-y':
            return ((self.min_x + self.max_x) * 0.5, self.min_y + 0.3)
        elif self.direction == '+x':
            return (self.max_x - 0.3, (self.min_y + self.max_y) * 0.5)
        else:
            return (self.min_x + 0.3, (self.min_y + self.max_y) * 0.5)

    def get_side_wall_colliders(self, thickness=0.36):
        """경사로 좌우 양측의 전신 통행 차단벽 충돌체 (Ramp Side Walls) 반환"""
        half_t = thickness * 0.5
        cols = []
        if self.direction in ('+y', '-y'):
            # 좌측(서측) 벽: x around min_x, y from min_y to max_y
            cols.append((self.min_x - half_t, self.min_y, self.min_x + half_t, self.max_y))
            # 우측(동측) 벽: x around max_x, y from min_y to max_y
            cols.append((self.max_x - half_t, self.min_y, self.max_x + half_t, self.max_y))
        else:
            # 남측 벽: y around min_y, x from min_x to max_x
            cols.append((self.min_x, self.min_y - half_t, self.max_x, self.min_y + half_t))
            # 북측 벽: y around max_y, x from min_x to max_x
            cols.append((self.min_x, self.max_y - half_t, self.max_x, self.max_y + half_t))
        return cols


@functools.lru_cache(maxsize=1024)
def get_zone_elevation(mx, my):
    """
    3x3 매크로 구역(18m x 18m)의 복층 및 경사로 구조 생성
    - 타입 4 (빈 공터), 타입 5 (사방 개방 초대형 공터), 타입 1 (대형 홀)에서 생성
    - 스폰 구역 (0, 0)은 플레이어가 즉시 복층과 경사로를 체험할 수 있도록 북측 메자닌 배치
    """
    # 맵 외곽 범위 체크
    min_zone = MAP_MIN_CHUNK * 2
    max_zone = (MAP_MAX_CHUNK + 1) * 2 - 1
    if mx < min_zone or mx > max_zone or my < min_zone or my > max_zone:
        return None

    zt = get_zone_type(mx, my)
    # 복층 구조는 넓은 공간(타입 1, 4, 5)에 배치
    if zt not in (1, 4, 5):
        return None

    ox = mx * 18.0
    oy = my * 18.0
    h = zone_hash(mx, my)

    platforms = []
    ramps = []
    pillars = []
    railings = []      # (min_x, min_y, max_x, max_y) 2층 난간 충돌체
    ramp_blockers = [] # (min_x, min_y, max_x, max_y) 1층 및 경사로 측면 통행 차단벽

    # 구역별 건축 스타일 결정 (스폰 구역 (0,0)은 스타일 0 고정)
    if mx == 0 and my == 0:
        style = 0
    else:
        style = h % 3

    if style == 0:
        # [스타일 0: 북측 메자닌 복층 플랫폼 & 서측 완만 경사로]
        # 플랫폼: 12m(가로) x 5.6m(세로), 높이 3.0m
        p_min_x, p_max_x = ox + 0.4, ox + 12.0
        p_min_y, p_max_y = oy + 12.0, oy + 17.6
        plat = Platform(f"plat_{mx}_{my}", p_min_x, p_min_y, p_max_x, p_max_y, z=PLATFORM_HEIGHT, open_edges={'south_west'})
        platforms.append(plat)

        # 경사로: 서측 x=[ox+0.6, ox+4.6], y=[oy+6.0, oy+12.0], 길이 6.0m 북향(+y)
        r_min_x, r_max_x = ox + 0.6, ox + 4.6
        r_min_y, r_max_y = oy + 6.0, oy + 12.0
        ramp = Ramp(f"ramp_{mx}_{my}", r_min_x, r_min_y, r_max_x, r_max_y, z_bottom=0.0, z_top=PLATFORM_HEIGHT, direction='+y')
        ramps.append(ramp)

        # 지지 기둥 4개 (1층 하부 통로 확보)
        pillars.append((ox + 5.6, oy + 12.4, 0.5, 0.5))
        pillars.append((ox + 11.4, oy + 12.4, 0.5, 0.5))
        pillars.append((ox + 5.6, oy + 17.0, 0.5, 0.5))
        pillars.append((ox + 11.4, oy + 17.0, 0.5, 0.5))

        # 2층 플랫폼 안전 난간 (남측 경사로 연결구 개방)
        railings.append((ox + 4.5, oy + 11.9, ox + 12.0, oy + 12.1)) # 남측 난간 (동쪽 절반, 경사로 우측 벽과 완벽 밀착)
        railings.append((ox + 11.9, oy + 12.0, ox + 12.1, oy + 17.6)) # 동측 난간
        railings.append((ox + 0.4, oy + 17.4, ox + 12.0, oy + 17.6))  # 북측 난간
        railings.append((ox + 0.3, oy + 12.0, ox + 0.5, oy + 17.6))   # 서측 난간

        # 경사로 옆면 가림벽 (1층 지면 및 경사로 양측 전신 통행 차단벽)
        ramp_blockers.extend(ramp.get_side_wall_colliders(thickness=0.36))

    elif style == 1:
        # [스타일 1: 중앙 사각 배틀 테라스 & 남측 광폭 진입 경사로]
        # 중앙 테라스: 9.6m x 7.0m, 높이 3.0m
        p_min_x, p_max_x = ox + 4.2, ox + 13.8
        p_min_y, p_max_y = oy + 9.5, oy + 16.5
        plat = Platform(f"plat_{mx}_{my}", p_min_x, p_min_y, p_max_x, p_max_y, z=PLATFORM_HEIGHT, open_edges={'south'})
        platforms.append(plat)

        # 남측 경사로: x=[ox+6.5, ox+11.5], y=[oy+3.5, oy+9.5], 길이 6.0m 북향(+y)
        r_min_x, r_max_x = ox + 6.5, ox + 11.5
        r_min_y, r_max_y = oy + 3.5, oy + 9.5
        ramp = Ramp(f"ramp_{mx}_{my}", r_min_x, r_min_y, r_max_x, r_max_y, z_bottom=0.0, z_top=PLATFORM_HEIGHT, direction='+y')
        ramps.append(ramp)

        # 4모서리 지지 기둥
        pillars.append((ox + 4.6, oy + 9.9, 0.5, 0.5))
        pillars.append((ox + 13.4, oy + 9.9, 0.5, 0.5))
        pillars.append((ox + 4.6, oy + 16.1, 0.5, 0.5))
        pillars.append((ox + 13.4, oy + 16.1, 0.5, 0.5))

        # 테라스 난간 (남측 경사로 연결구 개방)
        railings.append((ox + 4.2, oy + 9.4, ox + 6.6, oy + 9.6))   # 남측 좌 (경사로 좌측벽과 완벽 밀착)
        railings.append((ox + 11.4, oy + 9.4, ox + 13.8, oy + 9.6)) # 남측 우 (경사로 우측벽과 완벽 밀착)
        railings.append((ox + 4.1, oy + 9.5, ox + 4.3, oy + 16.5))  # 서측
        railings.append((ox + 13.7, oy + 9.5, ox + 13.9, oy + 16.5)) # 동측
        railings.append((ox + 4.2, oy + 16.3, ox + 13.8, oy + 16.5)) # 북측

        # 경사로 측면 가림벽
        ramp_blockers.extend(ramp.get_side_wall_colliders(thickness=0.36))

    else:
        # [스타일 2: 동측 런웨이 발코니 & 남향 직선 경사로]
        # 동측 발코니: 5.6m(가로) x 11.6m(세로), 높이 3.0m
        p_min_x, p_max_x = ox + 12.0, ox + 17.6
        p_min_y, p_max_y = oy + 6.0, oy + 17.6
        plat = Platform(f"plat_{mx}_{my}", p_min_x, p_min_y, p_max_x, p_max_y, z=PLATFORM_HEIGHT, open_edges={'south'})
        platforms.append(plat)

        # 남측 직선 경사로: x=[ox+12.6, ox+17.0], y=[oy+0.4, oy+6.0], 길이 5.6m 북향(+y)
        r_min_x, r_max_x = ox + 12.6, ox + 17.0
        r_min_y, r_max_y = oy + 0.4, oy + 6.0
        ramp = Ramp(f"ramp_{mx}_{my}", r_min_x, r_min_y, r_max_x, r_max_y, z_bottom=0.0, z_top=PLATFORM_HEIGHT, direction='+y')
        ramps.append(ramp)

        # 지지 기둥
        pillars.append((ox + 12.4, oy + 9.0, 0.5, 0.5))
        pillars.append((ox + 12.4, oy + 15.0, 0.5, 0.5))

        # 발코니 난간 (서측/북측/동측 및 남측 연결부 난간)
        railings.append((ox + 11.9, oy + 6.0, ox + 12.1, oy + 17.6)) # 서측 난간 (공터 조망)
        railings.append((ox + 12.0, oy + 17.4, ox + 17.6, oy + 17.6)) # 북측 난간
        railings.append((ox + 17.4, oy + 6.0, ox + 17.6, oy + 17.6)) # 동측 난간
        railings.append((ox + 12.0, oy + 5.9, ox + 12.7, oy + 6.1))  # 남측 서쪽 난간 (경사로 좌측벽 연결)
        railings.append((ox + 16.9, oy + 5.9, ox + 17.6, oy + 6.1))  # 남측 동쪽 난간 (경사로 우측벽 연결)

        # 경사로 서측/동측 가림벽
        ramp_blockers.extend(ramp.get_side_wall_colliders(thickness=0.36))

    return {
        "platforms": platforms,
        "ramps": ramps,
        "pillars": pillars,
        "railings": railings,
        "ramp_blockers": ramp_blockers
    }


def get_floor_height(x, y, current_z=None):
    """
    (x, y) 위치에서의 3D 지면/경사면/복층 바닥 높이 반환
    반환값: (floor_z, surface_type)
    surface_type in ('ground', 'ramp', 'platform')
    """
    mx = int(math.floor(x / 18.0))
    my = int(math.floor(y / 18.0))

    # 현재 구역 및 인접 경계 구역 확인
    candidates = [(mx, my)]
    rx = x % 18.0
    ry = y % 18.0
    if rx < 1.0:
        candidates.append((mx - 1, my))
    elif rx > 17.0:
        candidates.append((mx + 1, my))
    if ry < 1.0:
        candidates.append((mx, my - 1))
    elif ry > 17.0:
        candidates.append((mx, my + 1))

    # 1. 경사로 우선 판정 (자연스러운 슬로프 경사 보행)
    for cx, cy in candidates:
        elev = get_zone_elevation(cx, cy)
        if not elev:
            continue
        for ramp in elev.get("ramps", []):
            if ramp.contains(x, y, margin=0.15):
                ramp_z = ramp.get_z(x, y)
                if current_z is None or abs(current_z - ramp_z) < 1.9 or current_z < ramp_z:
                    return ramp_z, 'ramp'

    # 2. 복층 플랫폼 판정
    for cx, cy in candidates:
        elev = get_zone_elevation(cx, cy)
        if not elev:
            continue
        for plat in elev.get("platforms", []):
            if plat.contains(x, y, margin=0.08):
                # 캐릭터가 플랫폼 높이 근처이거나 그 이상이면 2층 플랫폼 바닥 안착
                if current_z is None or current_z >= (plat.z - 0.75):
                    return plat.z, 'platform'
                else:
                    # 플랫폼 아래(1층)를 통과 중
                    return 0.0, 'underpass'

    return 0.0, 'ground'


def get_ramp_for_pos(x, y):
    """해당 위치의 플랫폼으로 올라갈 수 있는 가장 적합한 경사로 검색"""
    mx = int(math.floor(x / 18.0))
    my = int(math.floor(y / 18.0))
    elev = get_zone_elevation(mx, my)
    if elev and elev.get("ramps"):
        return elev["ramps"][0]
    return None


def get_pursuit_goal(monster_pos, player_pos):
    """
    몬스터의 복층(2층) 및 1층 지능형 3D 추적 목표 지점 산출
    - 플레이어가 2층에 있고 몬스터가 1층에 있으면: 경사로 진입로를 경유하여 2층으로 진격
    - 몬스터가 경사로에 진입하면: 경사로 상단을 통해 2층으로 안착
    - 몬스터가 2층에 있고 플레이어가 1층에 있으면: 근거리일 경우 2층에서 1층으로 과감히 도약 급습, 원거리일 경우 경사로로 하강
    """
    mx, my, mz = monster_pos.x, monster_pos.y, monster_pos.z
    px, py, pz = player_pos.x, player_pos.y, player_pos.z

    p_floor, p_type = get_floor_height(px, py, pz)
    m_floor, m_type = get_floor_height(mx, my, mz)

    p_is_up = (p_floor > 1.2)
    m_is_up = (m_floor > 1.2)

    # 1. 플레이어가 2층 고지대에 있고, 몬스터가 1층에 있는 경우
    if p_is_up and not m_is_up:
        ramp = get_ramp_for_pos(px, py)
        if ramp:
            # 몬스터가 이미 경사로 위에 올라선 경우: 경사로 출구 및 플레이어를 향해 상승
            if ramp.contains(mx, my, margin=0.4):
                return ramp.get_exit_pos()
            else:
                # 1층 지면에서 경사로 진입로로 우선 이동
                return ramp.get_entrance_pos()

    # 2. 몬스터가 2층에 있고, 플레이어가 1층으로 내려간 경우
    elif not p_is_up and m_is_up:
        dist_2d = math.hypot(px - mx, py - my)
        # 4.5m 이내 근접 시: 난간/가장자리에서 1층으로 바로 뛰어내려 급습 (Drop-down Ambush)
        if dist_2d <= 4.8:
            return (px, py)
        else:
            # 원거리 시: 경사로를 타고 신속하게 1층으로 하강
            ramp = get_ramp_for_pos(mx, my)
            if ramp:
                if ramp.contains(mx, my, margin=0.4):
                    return ramp.get_entrance_pos()
                else:
                    return ramp.get_exit_pos()

    # 3. 같은 층(둘 다 1층이거나 둘 다 2층)에 있는 경우: 직접 추격
    return (px, py)


def get_chunk_elevation(cx, cy):
    """청크 (cx, cy) 범위와 겹치는 모든 복층 플랫폼 및 경사로 데이터 수집"""
    chunk_min_x = cx * 36.0
    chunk_max_x = (cx + 1) * 36.0
    chunk_min_y = cy * 36.0
    chunk_max_y = (cy + 1) * 36.0

    min_mx = cx * 2
    max_mx = cx * 2 + 1
    min_my = cy * 2
    max_my = cy * 2 + 1

    chunk_platforms = []
    chunk_ramps = []
    chunk_pillars = []
    chunk_railings = []
    chunk_ramp_blockers = []

    for mx in range(min_mx, max_mx + 1):
        for my in range(min_my, max_my + 1):
            elev = get_zone_elevation(mx, my)
            if not elev:
                continue
            for plat in elev.get("platforms", []):
                if not (plat.max_x < chunk_min_x or plat.min_x > chunk_max_x or
                        plat.max_y < chunk_min_y or plat.min_y > chunk_max_y):
                    chunk_platforms.append(plat)

            for ramp in elev.get("ramps", []):
                if not (ramp.max_x < chunk_min_x or ramp.min_x > chunk_max_x or
                        ramp.max_y < chunk_min_y or ramp.min_y > chunk_max_y):
                    chunk_ramps.append(ramp)

            for p in elev.get("pillars", []):
                px, py = p[0], p[1]
                if chunk_min_x <= px <= chunk_max_x and chunk_min_y <= py <= chunk_max_y:
                    chunk_pillars.append(p)

            for r in elev.get("railings", []):
                if not (r[2] < chunk_min_x or r[0] > chunk_max_x or r[3] < chunk_min_y or r[1] > chunk_max_y):
                    chunk_railings.append(r)

            for b in elev.get("ramp_blockers", []):
                if not (b[2] < chunk_min_x or b[0] > chunk_max_x or b[3] < chunk_min_y or b[1] > chunk_max_y):
                    chunk_ramp_blockers.append(b)

    return {
        "platforms": chunk_platforms,
        "ramps": chunk_ramps,
        "pillars": chunk_pillars,
        "railings": chunk_railings,
        "ramp_blockers": chunk_ramp_blockers
    }
