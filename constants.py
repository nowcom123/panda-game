from panda3d.core import loadPrcFileData, LColor

# --- 하드웨어 파이프라인 & 렌더링 프레임 페이싱 최적화 설정 ---
# 60 FPS 프레임 페이싱 고정 (GPU 큐 과부하, 지터링 및 드라이버 스터터링 완벽 차단)
loadPrcFileData('', 'clock-mode limited')
loadPrcFileData('', 'clock-frame-rate 60')
loadPrcFileData('', 'sync-video true')

# 텍스처 및 GPU 파이프라인 비동기 I/O
loadPrcFileData('', 'asynchronous-texture-loading true') # 텍스처 백그라운드 I/O 비동기 로딩
loadPrcFileData('', 'preload-textures true')            # VRAM 사전 업로드로 렌더링 중 스터터링 제거
loadPrcFileData('', 'gl-finish false')                  # GPU 파이프라인 지연/블로킹 방지
loadPrcFileData('', 'garbage-collect-states true')      # 렌더 스테이트 캐시 자동 메모리 회수
loadPrcFileData('', 'gl-check-errors false')             # 드로우콜마다 glGetError 폴링 오버헤드 제거
loadPrcFileData('', 'textures-auto-power-2 true')        # GPU 최적 텍스처 정렬
loadPrcFileData('', 'display-lists 0')                   # 레거시 디스플레이 리스트 대신 VBO 하드웨어 가속
loadPrcFileData('', 'yield-timeslice true')              # OS 스케줄러 스레드 기아 현상 방지
loadPrcFileData('', 'bounds-type box')                   # 바운딩 볼륨 O(1) 초고속 AABB 연산

# --- 시스템 상수 설정 ---
CELL_SIZE = 6.0         # 그리드 셀 크기 (6.0m x 6.0m: 광폭 리미널 복도 및 대형 홀)
CHUNK_CELLS = 6         # 한 청크당 셀 수 (6x6 = 36개 셀)
CHUNK_SIZE = CELL_SIZE * CHUNK_CELLS  # 청크 한 변 크기 (36.0m)

# 2단 벽체 구조 (1단: 0~6.5m, 2단: 6.5~13.0m)
TIER_HEIGHT = 6.5       # 1단 높이 (6.5m)
WALL_HEIGHT = TIER_HEIGHT * 2.0  # 총 2단 벽 및 천장 높이 (13.0m 초대형 심연 높이)
DOOR_HEIGHT = 3.0       # 출입문 통로 높이 (3.0m 웅장한 도어)
WALL_THICKNESS = 0.8    # 두꺼운 3D 벽체 두께 (0.8m 콘크리트/석고 보드 마감)

PLAYER_RADIUS = 0.4     # 플레이어 충돌 반경
PLAYER_EYE_HEIGHT = 1.7 # 플레이어 눈높이 (1.7m)
WALK_SPEED = 9.0        # 일반 걷기 속도 (광폭 복도에 맞춘 쾌적한 보행)
SPRINT_SPEED = 15.0     # Shift 달리기 속도
RENDER_RADIUS = 2       # 청크 렌더링 반경 (5x5 = 25청크)
FOG_COLOR = LColor(0.002, 0.002, 0.003, 1.0) # 칠흑 같은 암흑 톤 (완전한 어둠)

# 맵 크기 제한 (7x7 청크 = 252m x 252m, 총 1,764개 방/복도로 이루어진 광활한 폐쇄 시설)
MAP_MIN_CHUNK = -3
MAP_MAX_CHUNK = 3

BLACKOUT_FOG_COLOR = LColor(0.018, 0.003, 0.003, 1.0) # 정전 프로토콜 발동 시 핏빛 붉은 비상등 미스트 안개

CURSED_RELICS = {
    "glass_cannon": {
        "id": "glass_cannon",
        "name": "유리의 총열",
        "icon": "[유리]",
        "pro": "사격 공격력 +80%",
        "con": "받는 피해 +40%",
        "desc": "위험을 대가로 압도적인 화력을 얻습니다."
    },
    "blood_thirst": {
        "id": "blood_thirst",
        "name": "피의 갈증",
        "icon": "[흡혈]",
        "pro": "적 처치 시 체력 12 흡혈",
        "con": "최대 체력 25 영구 감소",
        "desc": "피를 갈망하며 살아있는 상태를 유지합니다."
    },
    "frenzy_drive": {
        "id": "frenzy_drive",
        "name": "광기의 가속",
        "icon": "[가속]",
        "pro": "이동 및 질주 속도 +30%",
        "con": "초당 체력 0.4 지속 감소",
        "desc": "생명을 불태워 초인적인 속도를 얻습니다."
    },
    "iron_colossus": {
        "id": "iron_colossus",
        "name": "철갑의 거인",
        "icon": "[철갑]",
        "pro": "최대 체력 +60 & 지진 면역",
        "con": "기본 이동 속도 15% 감소",
        "desc": "무거운 철갑으로 견고한 육체를 얻습니다."
    },
    "abyssal_reaper": {
        "id": "abyssal_reaper",
        "name": "심연의 수확자",
        "icon": "[심연]",
        "pro": "정전 중 공격력 2.5배",
        "con": "정전 지속 시간 10초 증가",
        "desc": "어둠이 짙어질수록 진정한 사신이 됩니다."
    }
}

