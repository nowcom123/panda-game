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

# 2단 벽체 구조 (1단: 0~4.5m, 2단: 4.5~9.0m)
TIER_HEIGHT = 4.5       # 1단 높이 (4.5m)
WALL_HEIGHT = TIER_HEIGHT * 2.0  # 총 2단 벽 및 천장 높이 (9.0m 높은 천장)
DOOR_HEIGHT = 2.4       # 출입문 통로 높이 (2.4m)
WALL_THICKNESS = 0.8    # 두꺼운 3D 벽체 두께 (0.8m 콘크리트/석고 보드 마감)

PLAYER_RADIUS = 0.4     # 플레이어 충돌 반경
PLAYER_EYE_HEIGHT = 1.7 # 플레이어 눈높이 (1.7m)
WALK_SPEED = 9.0        # 일반 걷기 속도 (광폭 복도에 맞춘 쾌적한 보행)
SPRINT_SPEED = 15.0     # Shift 달리기 속도
RENDER_RADIUS = 2       # 청크 렌더링 반경 (5x5 = 25청크)
FOG_COLOR = LColor(0.002, 0.002, 0.003, 1.0) # 칠흑 같은 암흑 톤 (완전한 어둠)
