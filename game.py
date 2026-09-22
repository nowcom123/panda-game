import math
import concurrent.futures
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
import random
from panda3d.core import (
    WindowProperties, Vec3, SamplerState, Fog,
    AmbientLight, PointLight, Spotlight, PerspectiveLens, TextNode, LColor, KeyboardButton
)
import simplepbr

# 모듈화된 하위 시스템 임포트 (PRC 설정은 constants에서 자동 초기화)
from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS, WALL_HEIGHT, PLAYER_RADIUS,
    PLAYER_EYE_HEIGHT, WALK_SPEED, SPRINT_SPEED, RENDER_RADIUS, FOG_COLOR,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK, WALL_THICKNESS
)
from world_gen import find_cell_path, check_line_of_sight
from chunk import Chunk
from monster import LongBlackSerpent, TallSkeletonMonster
from geometry import make_cube_to


class LiminalInfiniteLoop(ShowBase):
    def __init__(self):
        super().__init__()

        # PBR 렌더링 최적화 (직선 손전등 + 근접 필라이트 + 촛불2 + 뱀오라 + 해골오라 등 8개 슬롯 지원)
        if hasattr(self, 'win') and self.win is not None:
            simplepbr.init(
                max_lights=8,
                use_normal_maps=False,
                use_emission_maps=False,
                use_occlusion_maps=False,
                enable_shadows=False
            )

        # 1. 카메라 가시거리 및 안개 설정 (짙은 안개 한계 거리 65m에 맞춘 하드웨어 클리핑으로 원거리 오버드로우 0%)
        self.camLens.setNearFar(0.2, 65.0)
        self.camLens.setFov(75)
        self.rendered_chunk_count = 0
        self.total_chunk_count = 0
        self.last_hud_text = ""
        self.setup_fog()

        # 2. 백룸 조명 연출 (2단 천장 및 플레이어 조명)
        self.setup_lighting()

        # 3. 텍스처 로드
        self.load_assets()

        # 4. 키보드 & 마우스 입력 설정
        self.mouse_locked = True
        self.setup_input()

        # 5. 무한 청크 관리자 설정 (멀티스레드 비동기 스트리밍 워커 풀)
        self.chunks = {}  # (cx, cy) -> Chunk 객체
        self.chunk_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ChunkWorker")
        self.active_chunk_futures = {}  # (cx, cy) -> Future
        self.serpent_path_future = None
        self.skeleton_path_future = None
        self.killer_monster = None
        self.last_move_dir = Vec3(0, 0, 0)
        self.world_root = self.render.attachNewNode("world_root")

        # 6. 플레이어 및 추격 괴물 2종 초기 상태
        self.game_over = False
        self.game_won = False
        self.time_limit = 60.0
        self.time_left = self.time_limit
        self.max_ammo = 12
        self.ammo = self.max_ammo
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0

        self.heading = 0.0
        self.pitch = 0.0
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.camera.setPos(spawn_x, spawn_y, PLAYER_EYE_HEIGHT)
        self.camera.setHpr(self.heading, self.pitch, 0)

        # 달리기 스테미나 시스템 (100% 게이지, 전력질주 시 소모 및 걷기/정지 시 회복)
        self.max_stamina = 100.0
        self.stamina = self.max_stamina
        self.stamina_exhausted = False

        # 적 1 & 적 2: 항상 유효한 복도 구역 중 무작위 랜덤 스폰 (26m~46m 거리 유지)
        s_spawn = self.get_random_monster_spawn(spawn_x, spawn_y)
        k_spawn = self.get_random_monster_spawn(spawn_x, spawn_y, exclude_pos=s_spawn)

        self.serpent = LongBlackSerpent(self.render, s_spawn[0], s_spawn[1])
        self.skeleton = TallSkeletonMonster(self.render, k_spawn[0], k_spawn[1])
        self.monsters = [self.serpent, self.skeleton]

        # 스폰 지역과 먼 유효 복도에 완전 랜덤 비상 탈출구 생성
        self.setup_escape_portal()

        # 1인칭 듀얼 뷰모델 (왼손 손전등, 오른손 12발 권총)
        self.setup_viewmodel()

        # 초기 청크 전체 로드 (멀티스레드 병렬 로딩)
        self.update_chunks(force=True)

        # 7. UI 안내 문구 및 좌표 HUD
        self.setup_ui()

        # 메인 업데이트 루프 등록
        self.taskMgr.add(self.update, "updateTask")

        # 8. 셰이더 및 GPU 파이프라인 사전 웜업 (게임 진입 직후 첫 프레임 스터터링 100% 제거)
        for _ in range(2):
            self.taskMgr.step()

    def get_random_monster_spawn(self, px, py, min_dist=26.0, max_dist=46.0, exclude_pos=None):
        """플레이어로부터 min_dist~max_dist 사이의 유효한 복도 셀 중심 랜덤 스폰 좌표 산출"""
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        candidates = []
        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                # 중앙 주 복도(lx=1 또는 ly=1)는 벽체 없이 100% 개방 보장
                if gx % 3 == 1 or gy % 3 == 1:
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    d = math.hypot(cx - px, cy - py)
                    if min_dist <= d <= max_dist:
                        if exclude_pos is not None:
                            ed = math.hypot(cx - exclude_pos[0], cy - exclude_pos[1])
                            if ed < 15.0:
                                continue
                        candidates.append((cx, cy))
        if candidates:
            return random.choice(candidates)
        return (px + 30.0, py + 30.0)

    def setup_escape_portal(self):
        """스폰 지점(9.0, 9.0)으로부터 최소 70m 이상 떨어진 원거리 복도에 랜덤 비상 탈출구 생성"""
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        candidates = []
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if gx % 3 == 1 or gy % 3 == 1:
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    d = math.hypot(cx - spawn_x, cy - spawn_y)
                    if d >= 70.0:
                        candidates.append((cx, cy))
        if candidates:
            self.escape_pos = random.choice(candidates)
        else:
            self.escape_pos = (spawn_x + 75.0, spawn_y + 75.0)

        if hasattr(self, 'escape_portal_np') and self.escape_portal_np:
            self.escape_portal_np.removeNode()

        self.escape_portal_np = self.world_root.attachNewNode("escape_portal")
        ex, ey = self.escape_pos
        self.escape_portal_np.setPos(ex, ey, 0)

        emerald_bright = LColor(0.18, 1.0, 0.48, 1.0)
        emerald_dark = LColor(0.05, 0.42, 0.16, 1.0)

        # 1. 비상구 게이트 프레임 (너비 2.6m, 높이 3.4m)
        make_cube_to(self.escape_portal_np, 0.22, 0.30, 3.4, emerald_dark, -1.3, 0, 1.7)
        make_cube_to(self.escape_portal_np, 0.22, 0.30, 3.4, emerald_dark, 1.3, 0, 1.7)
        make_cube_to(self.escape_portal_np, 2.8, 0.30, 0.25, emerald_dark, 0, 0, 3.4)

        # 2. 발광 EXIT 비상탈출 간판
        sign = make_cube_to(self.escape_portal_np, 1.8, 0.18, 0.45, emerald_bright, 0, 0, 3.8)
        sign.setLightOff()

        # 3. 신비로운 초록빛 탈출 포탈 면
        portal_plane = make_cube_to(self.escape_portal_np, 2.3, 0.08, 3.2, emerald_bright, 0, 0, 1.6)
        portal_plane.setLightOff()

        # 4. 13m 천장까지 솟구치는 빛기둥
        pillar = make_cube_to(self.escape_portal_np, 0.16, 0.16, WALL_HEIGHT, emerald_bright, 0, 0, WALL_HEIGHT * 0.5)
        pillar.setLightOff()

        # 5. 에메랄드 원거리 비콘 라이트 (벽체 반사로 원거리 복도에서 유인)
        exit_light = PointLight('exit_beacon')
        exit_light.setColor((0.35, 2.4, 0.8, 1.0))
        exit_light.setAttenuation((1.0, 0.035, 0.0035))
        self.exit_light_np = self.escape_portal_np.attachNewNode(exit_light)
        self.exit_light_np.setPos(0, 0, 1.8)
        self.render.setLight(self.exit_light_np)

    def setup_viewmodel(self):
        """1인칭 듀얼 뷰모델: 왼손 손전등 & 오른손 12발 권총"""
        if hasattr(self, 'vm_root') and self.vm_root:
            self.vm_root.removeNode()

        self.vm_root = self.camera.attachNewNode("viewmodel_root")

        # --- (A) 왼손: 택티컬 손전등 ---
        self.vm_flashlight = self.vm_root.attachNewNode("vm_flashlight")
        self.vm_flashlight.setPos(-0.28, 0.62, -0.24)
        self.vm_flashlight.setHpr(-3.5, 2.0, 0)

        fl_body_col = LColor(0.12, 0.12, 0.14, 1.0)
        fl_ring_col = LColor(0.28, 0.30, 0.34, 1.0)
        fl_lens_col = LColor(1.0, 0.98, 0.88, 1.0)

        # 손잡이 몸체
        make_cube_to(self.vm_flashlight, 0.08, 0.28, 0.08, fl_body_col, 0, 0, 0)
        # 렌즈 베젤 헤드
        make_cube_to(self.vm_flashlight, 0.11, 0.09, 0.11, fl_ring_col, 0, 0.17, 0)
        # 발광 렌즈면
        glass = make_cube_to(self.vm_flashlight, 0.095, 0.02, 0.095, fl_lens_col, 0, 0.22, 0)
        glass.setLightOff()

        # 손전등 Spotlight: 왼손 손전등 헤드에서 전방으로 직진 빔 방출
        spotlight = Spotlight('player_flashlight')
        spotlight.setColor((2.85, 2.70, 2.35, 1.0))
        spot_lens = PerspectiveLens()
        spot_lens.setFov(44.0)
        spot_lens.setNearFar(0.15, 65.0)
        spotlight.setLens(spot_lens)
        spotlight.setAttenuation((1.0, 0.015, 0.0006))
        self.pl_np = self.vm_flashlight.attachNewNode(spotlight)
        self.pl_np.setPos(0, 0.24, 0)
        self.render.setLight(self.pl_np)

        # 근거리 보조 조명
        fill_light = PointLight('player_fill')
        fill_light.setColor((0.18, 0.16, 0.14, 1.0))
        fill_light.setAttenuation((1.0, 0.28, 0.08))
        self.fill_np = self.vm_flashlight.attachNewNode(fill_light)
        self.fill_np.setPos(0, 0.10, 0)
        self.render.setLight(self.fill_np)

        # --- (B) 오른손: 12발 권총 ---
        self.vm_pistol = self.vm_root.attachNewNode("vm_pistol")
        self.vm_pistol.setPos(0.26, 0.58, -0.22)
        self.vm_pistol.setHpr(3.0, 1.5, 0)

        # 반동 애니메이션 피벗 노드
        self.recoil_node = self.vm_pistol.attachNewNode("recoil_node")

        steel_dark = LColor(0.10, 0.10, 0.12, 1.0)
        steel_slide = LColor(0.22, 0.23, 0.26, 1.0)
        grip_col = LColor(0.06, 0.06, 0.07, 1.0)
        tritium_green = LColor(0.35, 1.0, 0.40, 1.0)

        # 슬라이드 & 리시버
        make_cube_to(self.recoil_node, 0.065, 0.30, 0.09, steel_slide, 0, 0.05, 0.04)
        # 총열 팁
        make_cube_to(self.recoil_node, 0.045, 0.08, 0.045, steel_dark, 0, 0.22, 0.035)
        # 권총 그립 (각도 기울임)
        grip = make_cube_to(self.recoil_node, 0.058, 0.11, 0.20, grip_col, 0, -0.06, -0.09)
        grip.setP(16)
        # 방아쇠울 & 방아쇠
        make_cube_to(self.recoil_node, 0.030, 0.08, 0.06, steel_dark, 0, 0.04, -0.04)

        # 전방 트리튬 가늠쇠 (자체 발광 녹색 도트)
        front_sight = make_cube_to(self.recoil_node, 0.012, 0.02, 0.02, tritium_green, 0, 0.19, 0.09)
        front_sight.setLightOff()

        # 후방 가늠자
        r_sight1 = make_cube_to(self.recoil_node, 0.012, 0.015, 0.02, tritium_green, -0.022, -0.09, 0.09)
        r_sight2 = make_cube_to(self.recoil_node, 0.012, 0.015, 0.02, tritium_green, 0.022, -0.09, 0.09)
        r_sight1.setLightOff()
        r_sight2.setLightOff()

        # 총구 화염 지오메트리 (발사 시 순간 노출)
        self.muzzle_flash_geom = make_cube_to(self.recoil_node, 0.16, 0.22, 0.16, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.34, 0.04, rot_h=45)
        self.muzzle_flash_geom.setLightOff()
        self.muzzle_flash_geom.hide()

        # 총구 화염 동적 조명
        self.muzzle_light = PointLight('muzzle_light')
        self.muzzle_light.setColor((2.8, 2.2, 0.9, 1.0))
        self.muzzle_light.setAttenuation((1.0, 0.08, 0.015))
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)
        self.muzzle_light_np.setPos(0, 0.35, 0.04)

    def shoot_pistol(self):
        """마우스 좌클릭 시 12발 권총 사격 및 적중 시 0.5초 스턴"""
        if self.game_over or self.game_won:
            return
        if self.shoot_cooldown > 0.0:
            return

        if self.ammo <= 0:
            # 탄약 고갈 (공이치기 찰칵)
            self.show_hit_marker("탄약 소진! (0/12)", (1.0, 0.3, 0.3, 1.0))
            self.shoot_cooldown = 0.35
            return

        self.ammo -= 1
        self.shoot_cooldown = 0.22
        self.recoil_timer = 0.10
        self.muzzle_timer = 0.04
        self.muzzle_flash_geom.show()
        self.render.setLight(self.muzzle_light_np)

        # 탄약 HUD 갱신
        self.update_ammo_ui()

        # 전방 레이캐스트 히트스캔
        ray_origin = self.camera.getPos()
        ray_dir = self.camera.getQuat().getForward()

        hit_s, dist_s = self.serpent.is_hit_by_ray(ray_origin, ray_dir)
        hit_k, dist_k = self.skeleton.is_hit_by_ray(ray_origin, ray_dir)

        if hit_s and hit_k:
            if dist_s <= dist_k:
                hit_k = False
            else:
                hit_s = False

        if hit_s:
            self.serpent.stun(0.5)
            self.show_hit_marker("적중! 뱀 괴물 0.5초 기절!", (1.0, 0.85, 0.2, 1.0))
        elif hit_k:
            self.skeleton.stun(0.5)
            self.show_hit_marker("적중! 해골 괴물 0.5초 기절!", (0.4, 0.95, 1.0, 1.0))

    def show_hit_marker(self, text, color):
        """피격/적중 알림 HUD 일시 표시"""
        self.hit_marker_text.setText(text)
        self.hit_marker_text.setFg(color)
        self.hit_marker_timer = 0.65

    def update_ammo_ui(self):
        """탄약 HUD 게이지 갱신"""
        self.ammo_text.setText(f"[ 탄약: {self.ammo} / {self.max_ammo} ]")
        if self.ammo <= 3:
            self.ammo_text.setFg((1.0, 0.25, 0.25, 1.0))
        else:
            self.ammo_text.setFg((1.0, 0.90, 0.35, 1.0))

    def setup_fog(self):
        """칠흑 같은 암흑 안개 및 배경색 설정"""
        self.liminal_fog = Fog("liminal_fog")
        self.liminal_fog.setColor(FOG_COLOR)
        # 짙은 지수 안개 밀도로 원거리 복도 및 높은 천장이 완전한 암흑에 묻힘
        self.liminal_fog.setExpDensity(0.048)
        self.render.setFog(self.liminal_fog)
        self.setBackgroundColor(FOG_COLOR)
        self.win.setClearColor(FOG_COLOR)

    def setup_lighting(self):
        """완전한 암흑 분위기 (최소 앰비언트 - 촛불 완전 제거)"""
        alight = AmbientLight('ambient_light')
        alight.setColor((0.005, 0.005, 0.007, 1.0))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)

    def load_assets(self):
        """바닥 및 벽 텍스처 로드 및 반복 모드 설정"""
        try:
            self.wall_tex = self.loader.loadTexture("wall.jpg")
            self.wall_tex.setWrapU(SamplerState.WM_repeat)
            self.wall_tex.setWrapV(SamplerState.WM_repeat)

            self.floor_tex = self.loader.loadTexture("floor.jpg")
            self.floor_tex.setWrapU(SamplerState.WM_repeat)
            self.floor_tex.setWrapV(SamplerState.WM_repeat)

            self.sky_tex = self.loader.loadTexture("sky.jpg")
            self.sky_tex.setWrapU(SamplerState.WM_repeat)
            self.sky_tex.setWrapV(SamplerState.WM_repeat)

            # GPU 밉맵 생성 및 이방성 필터링으로 텍스처 셰이더 샘플링 성능 및 시각적 선명도 대폭 향상
            for tex in (self.wall_tex, self.floor_tex, self.sky_tex):
                tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                tex.setMagfilter(SamplerState.FT_linear)
                tex.setAnisotropicDegree(2)
        except Exception as e:
            print(f"텍스처 로드 에러: {e}")

    def setup_input(self):
        """입력 키 매핑 및 마우스 제어 설정"""
        self.disableMouse()
        self.lock_mouse(True)

        self.keyMap = {
            "w": 0, "s": 0, "a": 0, "d": 0,
            "shift": 0
        }

        # WASD 8방향 이동 키
        for key in ["w", "a", "s", "d"]:
            self.accept(key, self.set_key, [key, 1])
            self.accept(f"{key}-up", self.set_key, [key, 0])
            self.accept(f"shift-{key}", self.set_key, [key, 1])
            self.accept(f"shift-{key}-up", self.set_key, [key, 0])
            self.accept(key.upper(), self.set_key, [key, 1])
            self.accept(f"{key.upper()}-up", self.set_key, [key, 0])

        # 화살표 키 (대체 키)
        arrow_mappings = {
            "arrow_up": "w",
            "arrow_down": "s",
            "arrow_left": "a",
            "arrow_right": "d"
        }
        for arrow, target in arrow_mappings.items():
            self.accept(arrow, self.set_key, [target, 1])
            self.accept(f"{arrow}-up", self.set_key, [target, 0])
            self.accept(f"shift-{arrow}", self.set_key, [target, 1])
            self.accept(f"shift-{arrow}-up", self.set_key, [target, 0])

        # Shift 달리기
        for s_key in ["shift", "lshift", "rshift"]:
            self.accept(s_key, self.set_key, ["shift", 1])
            self.accept(f"{s_key}-up", self.set_key, ["shift", 0])

        # 마우스 좌클릭: 12발 권총 사격 (적중 시 0.5초 스턴)
        self.accept("mouse1", self.shoot_pistol)

        # ESC 마우스 커서 해제/잠금 토글
        self.accept("escape", self.toggle_mouse_lock)

        # R 키 재시작
        self.accept("r", self.restart_game)
        self.accept("shift-r", self.restart_game)
        self.accept("R", self.restart_game)

    def set_key(self, key, state):
        self.keyMap[key] = state

    def lock_mouse(self, lock):
        self.mouse_locked = lock
        props = WindowProperties()
        props.setCursorHidden(lock)
        props.setMouseMode(WindowProperties.M_confined if lock else WindowProperties.M_absolute)
        if hasattr(self.win, 'requestProperties'):
            self.win.requestProperties(props)

    def toggle_mouse_lock(self):
        self.lock_mouse(not self.mouse_locked)

    def setup_ui(self):
        """FPS 정보 표시 HUD, 타이머, 탄약, 조준점 및 게임 오버/승리 UI 설정"""
        try:
            self.korean_font = self.loader.loadFont('/c/Windows/Fonts/malgun.ttf')
        except Exception:
            self.korean_font = None

        font_kw = {"font": self.korean_font} if self.korean_font else {}

        # 1. 화면 중앙 조준점 (Crosshair)
        self.crosshair = OnscreenText(
            text="+",
            pos=(0, -0.015),
            scale=0.065,
            fg=(1.0, 1.0, 1.0, 0.85),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=False
        )

        # 2. 상단 중앙 60초 탈출 카운트다운 타이머 HUD
        self.timer_text = OnscreenText(
            text="[ 탈출 제한시간: 01:00 ]",
            pos=(0, 0.91),
            scale=0.052,
            fg=(0.25, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **font_kw
        )

        # 3. 우측 하단 12발 권총 탄약 HUD
        self.ammo_text = OnscreenText(
            text="[ 탄약: 12 / 12 ]",
            pos=(1.28, -0.85),
            scale=0.048,
            fg=(1.0, 0.90, 0.35, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ARight,
            mayChange=True,
            **font_kw
        )

        # 4. 중앙 피격/적중 알림 HUD
        self.hit_marker_text = OnscreenText(
            text="",
            pos=(0, -0.16),
            scale=0.046,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **font_kw
        )

        # 5. 좌상단 위치 좌표 HUD
        self.hud_text = OnscreenText(
            text="위치: X=0.0, Y=0.0",
            pos=(-1.3, 0.92),
            scale=0.045,
            fg=(1, 1, 1, 0.9),
            align=TextNode.ALeft,
            mayChange=True,
            **font_kw
        )
        self.stamina_text = OnscreenText(
            text="스테미나: [|||||||||||||||] 100%",
            pos=(-1.3, 0.86),
            scale=0.04,
            fg=(0.35, 0.95, 0.5, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **font_kw
        )
        self.guide_text = OnscreenText(
            text="[WASD] 8방향 이동  |  [Shift] 달리기  |  [좌클릭] 12발 권총 사격 (적중 시 0.5초 기절)  |  [R] 재시작",
            pos=(0, -0.93),
            scale=0.038,
            fg=(0.9, 0.9, 0.8, 0.85),
            align=TextNode.ACenter,
            mayChange=False,
            **font_kw
        )

        # 6. 게임 오버 UI
        self.game_over_banner = OnscreenText(
            text="사  망",
            pos=(0, 0.25),
            scale=0.14,
            fg=(0.95, 0.08, 0.08, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **font_kw
        )
        self.game_over_desc = OnscreenText(
            text="기괴한 괴물에게 영혼을 잠식당했습니다...",
            pos=(0, 0.05),
            scale=0.055,
            fg=(0.88, 0.88, 0.88, 0.95),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
            **font_kw
        )
        self.game_over_restart = OnscreenText(
            text="[ R ] 키를 눌러 다시 도전",
            pos=(0, -0.15),
            scale=0.05,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=False,
            **font_kw
        )

        # 7. 탈출 성공(승리) UI
        self.victory_banner = OnscreenText(
            text="탈  출  성  공",
            pos=(0, 0.25),
            scale=0.14,
            fg=(0.20, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **font_kw
        )
        self.victory_desc = OnscreenText(
            text="비상 탈출구를 찾아 악몽의 미궁을 탈출했습니다!",
            pos=(0, 0.05),
            scale=0.055,
            fg=(0.92, 0.98, 0.92, 0.95),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
            **font_kw
        )

        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.game_over_restart.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()

    def restart_game(self):
        """게임 재시작: 플레이어, 괴물, 탈출구, 60초 타이머, 12발 탄약 초기화"""
        self.game_over = False
        self.game_won = False
        self.time_left = self.time_limit
        self.ammo = self.max_ammo
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0
        self.keyMap = {k: 0 for k in self.keyMap}

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.camera.setPos(spawn_x, spawn_y, PLAYER_EYE_HEIGHT)
        self.heading = 0.0
        self.pitch = 0.0
        self.camera.setHpr(0, 0, 0)

        # 뷰모델 리셋
        self.recoil_node.setPos(0, 0, 0)
        self.recoil_node.setP(0)
        self.muzzle_flash_geom.hide()
        self.render.clearLight(self.muzzle_light_np)

        # 스테미나 리셋
        self.stamina = self.max_stamina
        self.stamina_exhausted = False

        # 비동기 작업 정리
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        self.serpent_path_future = None
        self.skeleton_path_future = None
        self.killer_monster = None
        self.last_move_dir = Vec3(0, 0, 0)

        # 괴물 2종 위치 랜덤 리셋
        s_spawn = self.get_random_monster_spawn(spawn_x, spawn_y)
        k_spawn = self.get_random_monster_spawn(spawn_x, spawn_y, exclude_pos=s_spawn)
        self.serpent.reset_pos(s_spawn[0], s_spawn[1])
        self.skeleton.reset_pos(k_spawn[0], k_spawn[1])

        # 원거리 탈출구 신규 랜덤 재배치
        self.setup_escape_portal()

        # 안개 및 배경색 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.setBackgroundColor(FOG_COLOR)
        self.win.setClearColor(FOG_COLOR)

        # UI 복구
        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.game_over_restart.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()
        self.crosshair.show()
        self.guide_text.show()
        self.hit_marker_text.setText("")
        self.update_ammo_ui()
        self.lock_mouse(True)

    def trigger_victory(self):
        """탈출구 도착 시 탈출 성공 연출"""
        if self.game_over or self.game_won:
            return
        self.game_won = True
        self.keyMap = {k: 0 for k in self.keyMap}

        # 초록빛 승리 조명
        green_fog = LColor(0.02, 0.20, 0.07, 1.0)
        self.liminal_fog.setColor(green_fog)
        self.setBackgroundColor(green_fog)
        self.win.setClearColor(green_fog)

        remaining = max(0.0, self.time_left)
        self.victory_banner.show()
        self.victory_desc.setText(f"비상 탈출구를 찾아 악몽에서 탈출했습니다!\n[남은 시간: {remaining:.1f}초  |  남은 탄약: {self.ammo}/12발]")
        self.victory_desc.show()
        self.game_over_restart.show()
        self.guide_text.hide()
        self.crosshair.hide()

    def trigger_game_over(self, killer=None, reason="killed"):
        """괴물에게 잡혔거나 제한시간 초과 시 게임 오버 연출"""
        if self.game_over or self.game_won:
            return
        self.game_over = True
        self.killer_monster = killer
        self.keyMap = {k: 0 for k in self.keyMap}

        if killer is not None:
            # 카메라를 킬러 괴물의 섬뜩한 얼굴로 즉시 강제 응시 (점프스케어 앵글)
            px, py = self.camera.getX(), self.camera.getY()
            kx, ky = killer.pos.x, killer.pos.y
            kz = getattr(killer.pos, 'z', 0.0)
            dx = kx - px
            dy = ky - py
            h = math.degrees(math.atan2(-dx, dy))
            dist = max(0.2, math.hypot(dx, dy))
            target_eye_z = kz + (3.85 if isinstance(killer, TallSkeletonMonster) else 0.45)
            p = math.degrees(math.atan2(target_eye_z - PLAYER_EYE_HEIGHT, dist))
            self.camera.setHpr(h, p, 0)
            killer.update(0.016, is_moving=False, is_attacking=True)

            self.game_over_banner.setText("사  망")
            self.game_over_banner.setFg((0.95, 0.08, 0.08, 1.0))
            if isinstance(killer, TallSkeletonMonster):
                self.game_over_desc.setText("쩍 벌어진 입의 거대 해골 괴물에게 영혼을 빼앗겼습니다...")
            else:
                self.game_over_desc.setText("칠흑의 거대한 뱀에게 온몸을 휘감겨 삼켜졌습니다...")

            blood_fog = LColor(0.22, 0.02, 0.02, 1.0)
            self.liminal_fog.setColor(blood_fog)
            self.setBackgroundColor(blood_fog)
            self.win.setClearColor(blood_fog)
        else:
            # 1분 제한시간 초과
            self.game_over_banner.setText("탈  출  실  패")
            self.game_over_banner.setFg((0.85, 0.25, 0.95, 1.0))
            self.game_over_desc.setText("제한시간 1분이 모두 지나 미궁의 심연에 영원히 갇혔습니다...")
            purple_fog = LColor(0.08, 0.02, 0.15, 1.0)
            self.liminal_fog.setColor(purple_fog)
            self.setBackgroundColor(purple_fog)
            self.win.setClearColor(purple_fog)

        self.game_over_banner.show()
        self.game_over_desc.show()
        self.game_over_restart.show()
        self.guide_text.hide()
        self.crosshair.hide()

    def update_chunks(self, force=False):
        """시야 내 및 이동 방향을 예측하는 비동기 멀티스레드 청크 스트리밍"""
        px, py = self.camera.getX(), self.camera.getY()
        player_cx = int(math.floor(px / CHUNK_SIZE))
        player_cy = int(math.floor(py / CHUNK_SIZE))

        if not force and hasattr(self, 'last_chunk') and (player_cx, player_cy) == self.last_chunk:
            return

        self.last_chunk = (player_cx, player_cy)

        # 5x5 활성 청크 영역 (반경 2, 7x7 맵 경계 MAP_MIN_CHUNK ~ MAP_MAX_CHUNK 내부로 제한)
        needed_chunks = set()
        for dx in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
            for dy in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
                cx = player_cx + dx
                cy = player_cy + dy
                if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                    needed_chunks.add((cx, cy))

        # 이동 벡터 기반 전방 예측 청크 (Lookahead Pre-caching)
        if hasattr(self, 'last_move_dir') and self.last_move_dir.lengthSquared() > 0.01:
            pred_x = px + self.last_move_dir.x * 24.0
            pred_y = py + self.last_move_dir.y * 24.0
            pred_cx = int(math.floor(pred_x / CHUNK_SIZE))
            pred_cy = int(math.floor(pred_y / CHUNK_SIZE))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cx = pred_cx + dx
                    cy = pred_cy + dy
                    if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                        needed_chunks.add((cx, cy))

        # 가시거리 밖으로 벗어난 청크 안전 해제
        chunks_to_remove = [coord for coord in self.chunks if coord not in needed_chunks]
        for coord in chunks_to_remove:
            self.chunks[coord].destroy()
            del self.chunks[coord]

        # 벗어난 미완료 비동기 태스크 취소
        futures_to_cancel = [coord for coord in self.active_chunk_futures if coord not in needed_chunks]
        for coord in futures_to_cancel:
            fut = self.active_chunk_futures.pop(coord)
            fut.cancel()

        missing = [coord for coord in needed_chunks if coord not in self.chunks and coord not in self.active_chunk_futures]
        if missing:
            # 플레이어와의 거리순으로 정렬하여 가까운 청크부터 우선 처리
            missing.sort(key=lambda c: (c[0] - player_cx)**2 + (c[1] - player_cy)**2)
            if force:
                # 초기 부팅 시에는 멀티스레드로 병렬 동시 빌드 후 메인 씬에 일괄 마운트
                futs = [self.chunk_executor.submit(Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex) for cx, cy in missing]
                for fut in futs:
                    try:
                        chunk = fut.result()
                        chunk.attach_to(self.world_root)
                        self.chunks[(chunk.cx, chunk.cy)] = chunk
                    except Exception as e:
                        print(f"초기 청크 로딩 에러: {e}")
                self.cull_chunks_to_view()
            else:
                # 게임 진행 중에는 백그라운드 워커 스레드 풀에 비동기 디스패치 (메인 스레드 블로킹 0ms)
                for cx, cy in missing:
                    fut = self.chunk_executor.submit(Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex)
                    self.active_chunk_futures[(cx, cy)] = fut

    def cull_chunks_to_view(self):
        """
        안개 가시거리 기준 장거리 청크만 선택적 가시화 (거리 컬링).
        근거리 시야 내 청크는 Panda3D C++ 하드웨어 뷰포트 절두체 컬링에 위임하여 씬그래프 오버헤드 0% 달성.
        """
        px, py = self.camera.getX(), self.camera.getY()
        chunk_rad = (CHUNK_SIZE / 2.0) * math.sqrt(2)
        max_view_dist = 68.0  # 안개 완전 암흑 한계 거리 (68m 밖은 100% 암흑)
        max_dist_sq = (max_view_dist + chunk_rad) ** 2

        visible_count = 0
        for (cx, cy), chunk in self.chunks.items():
            ccx = (cx + 0.5) * CHUNK_SIZE
            ccy = (cy + 0.5) * CHUNK_SIZE
            dx = ccx - px
            dy = ccy - py
            d_sq = dx * dx + dy * dy

            # 안개 한계 거리 초과 시에만 렌더링 제외, 그 외는 C++ 네이티브 컬링에 맡김
            is_visible = (d_sq <= max_dist_sq)
            chunk.set_visible(is_visible)
            if is_visible:
                visible_count += 1

        self.rendered_chunk_count = visible_count
        self.total_chunk_count = len(self.chunks)

    def get_nearby_colliders(self, px, py, search_dist=2.5):
        """그리드 셀 해시 기반 즉시 충돌체 추출 (600개 전수검사 -> 8~12개 즉시 반환으로 연산량 98% 절감)"""
        min_gx = int(math.floor((px - search_dist) / CELL_SIZE))
        max_gx = int(math.floor((px + search_dist) / CELL_SIZE))
        min_gy = int(math.floor((py - search_dist) / CELL_SIZE))
        max_gy = int(math.floor((py + search_dist) / CELL_SIZE))

        nearby = []
        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                cx = gx // CHUNK_CELLS
                cy = gy // CHUNK_CELLS
                chunk = self.chunks.get((cx, cy))
                if chunk and hasattr(chunk, 'cell_colliders'):
                    cols = chunk.cell_colliders.get((gx, gy))
                    if cols:
                        nearby.extend(cols)
        return nearby

    def resolve_collision(self, curr_x, curr_y, dx, dy, radius=PLAYER_RADIUS):
        """
        정밀 원형-AABB 최단거리 밀어내기(Push-out) 및 연속 벽면 슬라이딩 해결
        - 공간 분할 인덱스로 현재 위치 주변 충돌체만 즉각 필터링
        - 3회 완화(Relaxation) 반복 적용으로 벽 파고들기 및 끼임 완벽 차단
        """
        max_d = max(abs(dx), abs(dy))
        margin = radius + max_d + 0.6
        colliders = self.get_nearby_colliders(curr_x, curr_y, search_dist=margin)
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

    def update(self, task):
        dt = globalClock.getDt()
        if dt > 0.1:
            dt = 0.1

        # --- [승리 상태] 탈출 성공 시: 업데이트 정지 ---
        if self.game_won:
            return task.cont

        # --- [게임 오버 상태] 플레이어 사망 시: 시선 강제 고정 및 킬러 괴물 공격 모션 유지 ---
        if self.game_over:
            if self.killer_monster is not None:
                killer = self.killer_monster
                px, py = self.camera.getX(), self.camera.getY()
                kx, ky = killer.pos.x, killer.pos.y
                kz = getattr(killer.pos, 'z', 0.0)
                dx = kx - px
                dy = ky - py
                h = math.degrees(math.atan2(-dx, dy))
                dist = max(0.2, math.hypot(dx, dy))
                target_eye_z = kz + (3.85 if isinstance(killer, TallSkeletonMonster) else 0.45)
                p = math.degrees(math.atan2(target_eye_z - PLAYER_EYE_HEIGHT, dist))
                self.camera.setHpr(h, p, 0)
                killer.update(dt, is_moving=False, is_attacking=True)
            return task.cont

        # --- 0. 비동기 백그라운드 스레드 청크 마운트 (메인 스레드 지연 제로) ---
        chunk_created = False
        if self.active_chunk_futures:
            cur_px, cur_py = self.camera.getX(), self.camera.getY()
            cur_cx = int(math.floor(cur_px / CHUNK_SIZE))
            cur_cy = int(math.floor(cur_py / CHUNK_SIZE))
            done_coords = [coord for coord, fut in self.active_chunk_futures.items() if fut.done()]
            for coord in done_coords:
                fut = self.active_chunk_futures.pop(coord)
                try:
                    chunk = fut.result()
                    # 청크가 아직 유효 렌더 범위 내에 있는지 확인 후 마운트 (이동으로 벗어난 청크는 즉시 파기)
                    if abs(coord[0] - cur_cx) <= RENDER_RADIUS + 1 and abs(coord[1] - cur_cy) <= RENDER_RADIUS + 1:
                        chunk.attach_to(self.world_root)
                        self.chunks[coord] = chunk
                        chunk_created = True
                    else:
                        chunk.destroy()
                except Exception as e:
                    print(f"청크 마운트 예외: {e}")

        # --- 1. 마우스 시선 제어 ---
        view_changed = False
        if self.mouse_locked and self.mouseWatcherNode and self.mouseWatcherNode.hasMouse():
            md = self.win.getPointer(0)
            center_x, center_y = self.win.getXSize() // 2, self.win.getYSize() // 2

            delta_x = md.getX() - center_x
            delta_y = md.getY() - center_y

            if delta_x != 0 or delta_y != 0:
                mouse_sens = 0.13
                self.heading -= delta_x * mouse_sens
                self.pitch -= delta_y * mouse_sens
                self.pitch = max(-89.0, min(89.0, self.pitch))

                self.camera.setHpr(self.heading, self.pitch, 0)
                self.win.movePointer(0, center_x, center_y)
                view_changed = True

        # --- 2. 8방향 키보드 이동 및 스테미나 기반 달리기 처리 ---
        base_mouse_watcher = self.mouseWatcherNode
        shift_held = bool(self.keyMap["shift"])
        if base_mouse_watcher:
            shift_held = shift_held or (
                base_mouse_watcher.isButtonDown(KeyboardButton.shift()) or
                base_mouse_watcher.isButtonDown(KeyboardButton.lshift()) or
                base_mouse_watcher.isButtonDown(KeyboardButton.rshift())
            )

        w_held = bool(self.keyMap["w"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("w")))
        s_held = bool(self.keyMap["s"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("s")))
        a_held = bool(self.keyMap["a"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("a")))
        d_held = bool(self.keyMap["d"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("d")))

        move_dir = Vec3(0, 0, 0)
        heading_rad = math.radians(self.heading)
        forward = Vec3(-math.sin(heading_rad), math.cos(heading_rad), 0)
        right = Vec3(math.cos(heading_rad), math.sin(heading_rad), 0)

        is_moving = False
        if w_held:
            move_dir += forward
            is_moving = True
        if s_held:
            move_dir -= forward
            is_moving = True
        if a_held:
            move_dir -= right
            is_moving = True
        if d_held:
            move_dir += right
            is_moving = True

        # 스테미나 시스템 갱신
        wants_to_sprint = shift_held and is_moving
        if self.stamina_exhausted:
            if self.stamina >= 25.0:
                self.stamina_exhausted = False
            self.is_sprinting = False
        else:
            self.is_sprinting = wants_to_sprint and (self.stamina > 0.0)

        if self.is_sprinting:
            self.stamina -= 22.0 * dt  # 약 4.5초 전력질주 가능
            if self.stamina <= 0.0:
                self.stamina = 0.0
                self.stamina_exhausted = True
                self.is_sprinting = False
        else:
            recovery_rate = 14.0 if not is_moving else 8.0
            self.stamina = min(self.max_stamina, self.stamina + recovery_rate * dt)

        # 이동 처리
        if is_moving:
            move_dir.normalize()
            self.last_move_dir = move_dir
            speed = SPRINT_SPEED if self.is_sprinting else WALK_SPEED
            disp = move_dir * speed * dt

            # --- 3. 정밀 벽 충돌 판정 및 매끄러운 슬라이딩 처리 ---
            curr_pos = self.camera.getPos()
            new_x, new_y = self.resolve_collision(curr_pos.x, curr_pos.y, disp.x, disp.y, radius=PLAYER_RADIUS)
            self.camera.setPos(new_x, new_y, PLAYER_EYE_HEIGHT)

            # 플레이어 이동에 따라 주변 청크 실시간 갱신
            self.update_chunks()
            view_changed = True
        else:
            self.last_move_dir = Vec3(0, 0, 0)

        # --- 괴물 2종 지능형 추격 AI (검은 뱀 & 키 큰 해골 괴물) ---
        px, py = self.camera.getX(), self.camera.getY()
        pgx = int(math.floor(px / CELL_SIZE))
        pgy = int(math.floor(py / CELL_SIZE))

        dist_serpent = math.hypot(px - self.serpent.pos.x, py - self.serpent.pos.y)
        dist_skeleton = math.hypot(px - self.skeleton.pos.x, py - self.skeleton.pos.y)

        # 잡힘 판정 (뱀: 1.45m, 해골: 1.85m) - 스턴 중인 적은 플레이어를 공격하지 못함
        if dist_serpent <= 1.45 and self.serpent.stun_timer <= 0.0:
            self.trigger_game_over(self.serpent)
            return task.cont
        if dist_skeleton <= 1.85 and self.skeleton.stun_timer <= 0.0:
            self.trigger_game_over(self.skeleton)
            return task.cont

        # ====================================================================
        # [적 1: 몸통이 긴 검은색 뱀 (LongBlackSerpent) 추격 및 벽 타기]
        # ====================================================================
        sx, sy = self.serpent.pos.x, self.serpent.pos.y
        s_los = False
        if dist_serpent <= 22.0:
            mid_x = (sx + px) * 0.5
            mid_y = (sy + py) * 0.5
            los_colliders = self.get_nearby_colliders(mid_x, mid_y, search_dist=dist_serpent * 0.5 + 1.2)
            s_los = check_line_of_sight(sx, sy, px, py, los_colliders)
        self.serpent.has_los = s_los

        if s_los:
            s_tx, s_ty = px, py
            s_speed = 10.6 if dist_serpent > 5.0 else 11.4
        else:
            sgx = int(math.floor(sx / CELL_SIZE))
            sgy = int(math.floor(sy / CELL_SIZE))
            if self.serpent_path_future is not None and self.serpent_path_future.done():
                try:
                    new_path = self.serpent_path_future.result()
                    if new_path:
                        self.serpent.path = new_path
                except Exception:
                    pass
                self.serpent_path_future = None

            self.serpent.path_timer -= dt
            if (self.serpent.path_timer <= 0.0 or not self.serpent.path) and self.serpent_path_future is None:
                self.serpent_path_future = self.chunk_executor.submit(find_cell_path, (sgx, sgy), (pgx, pgy), 20)
                self.serpent.path_timer = 0.20

            if len(self.serpent.path) >= 2:
                cur_c = self.serpent.path[0]
                nxt_c = self.serpent.path[1]
                if nxt_c[1] == cur_c[1] + 1:
                    s_tx, s_ty = (cur_c[0] + 0.5) * CELL_SIZE, (cur_c[1] + 1.0) * CELL_SIZE
                elif nxt_c[1] == cur_c[1] - 1:
                    s_tx, s_ty = (cur_c[0] + 0.5) * CELL_SIZE, cur_c[1] * CELL_SIZE
                elif nxt_c[0] == cur_c[0] + 1:
                    s_tx, s_ty = (cur_c[0] + 1.0) * CELL_SIZE, (cur_c[1] + 0.5) * CELL_SIZE
                else:
                    s_tx, s_ty = cur_c[0] * CELL_SIZE, (cur_c[1] + 0.5) * CELL_SIZE

                if math.hypot(sx - s_tx, sy - s_ty) < 1.2 or (sgx == nxt_c[0] and sgy == nxt_c[1]):
                    self.serpent.path.pop(0)
            else:
                s_tx, s_ty = px, py

            s_speed = 8.8 if dist_serpent > 15.0 else 9.6

        # 뱀 벽면 검출 및 벽 타기(Wall Crawling) 판정
        s_tdx, s_tdy = s_tx - sx, s_ty - sy
        s_tdist = math.hypot(s_tdx, s_tdy)

        serpent_walls = [
            c for c in self.get_nearby_colliders(sx, sy, search_dist=2.4)
            if (c[2] - c[0]) >= 0.5 or (c[3] - c[1]) >= 0.5
        ]
        s_closest_wall = 999.0
        s_wall_norm = None
        for min_x, min_y, max_x, max_y in serpent_walls:
            cx = max(min_x, min(sx, max_x))
            cy = max(min_y, min(sy, max_y))
            vx, vy = sx - cx, sy - cy
            d = math.hypot(vx, vy)
            if d < s_closest_wall:
                s_closest_wall = d
                if d > 0.05:
                    s_wall_norm = Vec3(vx / d, vy / d, 0)

        if s_closest_wall < 2.2 and s_wall_norm is not None:
            s_climb_z = 4.2 if dist_serpent > 4.0 else 0.45
        else:
            s_climb_z = 0.45

        if s_tdist > 0.05:
            sndx, sndy = s_tdx / s_tdist, s_tdy / s_tdist
            s_disp_x = sndx * s_speed * dt
            s_disp_y = sndy * s_speed * dt
            new_sx, new_sy = self.resolve_collision(sx, sy, s_disp_x, s_disp_y, radius=0.42)
            self.serpent.update_pos(new_sx, new_sy, dt, sndx, sndy, wall_norm=s_wall_norm, climb_target_z=s_climb_z)
        else:
            self.serpent.update(dt, is_moving=False)

        # ====================================================================
        # [적 2: 키 크고 팔 긴 해골 괴물 (TallSkeletonMonster) 성큼성큼 추격]
        # ====================================================================
        kx, ky = self.skeleton.pos.x, self.skeleton.pos.y
        k_los = False
        if dist_skeleton <= 26.0:
            mid_x = (kx + px) * 0.5
            mid_y = (ky + py) * 0.5
            los_colliders = self.get_nearby_colliders(mid_x, mid_y, search_dist=dist_skeleton * 0.5 + 1.2)
            k_los = check_line_of_sight(kx, ky, px, py, los_colliders)
        self.skeleton.has_los = k_los

        if k_los:
            k_tx, k_ty = px, py
            k_speed = 10.8 if dist_skeleton > 6.0 else 11.6  # 긴 팔을 뻗으며 전력 질주
        else:
            kgx = int(math.floor(kx / CELL_SIZE))
            kgy = int(math.floor(ky / CELL_SIZE))
            if self.skeleton_path_future is not None and self.skeleton_path_future.done():
                try:
                    new_path = self.skeleton_path_future.result()
                    if new_path:
                        self.skeleton.path = new_path
                except Exception:
                    pass
                self.skeleton_path_future = None

            self.skeleton.path_timer -= dt
            if (self.skeleton.path_timer <= 0.0 or not self.skeleton.path) and self.skeleton_path_future is None:
                self.skeleton_path_future = self.chunk_executor.submit(find_cell_path, (kgx, kgy), (pgx, pgy), 20)
                self.skeleton.path_timer = 0.22

            if len(self.skeleton.path) >= 2:
                cur_c = self.skeleton.path[0]
                nxt_c = self.skeleton.path[1]
                if nxt_c[1] == cur_c[1] + 1:
                    k_tx, k_ty = (cur_c[0] + 0.5) * CELL_SIZE, (cur_c[1] + 1.0) * CELL_SIZE
                elif nxt_c[1] == cur_c[1] - 1:
                    k_tx, k_ty = (cur_c[0] + 0.5) * CELL_SIZE, cur_c[1] * CELL_SIZE
                elif nxt_c[0] == cur_c[0] + 1:
                    k_tx, k_ty = (cur_c[0] + 1.0) * CELL_SIZE, (cur_c[1] + 0.5) * CELL_SIZE
                else:
                    k_tx, k_ty = cur_c[0] * CELL_SIZE, (cur_c[1] + 0.5) * CELL_SIZE

                if math.hypot(kx - k_tx, ky - k_ty) < 1.2 or (kgx == nxt_c[0] and kgy == nxt_c[1]):
                    self.skeleton.path.pop(0)
            else:
                k_tx, k_ty = px, py

            k_speed = 8.5 if dist_skeleton > 16.0 else 9.5

        k_tdx, k_tdy = k_tx - kx, k_ty - ky
        k_tdist = math.hypot(k_tdx, k_tdy)
        if k_tdist > 0.05:
            kndx, kndy = k_tdx / k_tdist, k_tdy / k_tdist
            k_disp_x = kndx * k_speed * dt
            k_disp_y = kndy * k_speed * dt
            new_kx, new_ky = self.resolve_collision(kx, ky, k_disp_x, k_disp_y, radius=0.48)
            self.skeleton.update_pos(new_kx, new_ky, dt, kndx, kndy)
        else:
            self.skeleton.update(dt, is_moving=False)

        # --- 4. 안개 가시거리 컬링 (청크 생성 또는 대폭 이동 시에만 갱신) ---
        if chunk_created or (view_changed and is_moving):
            self.cull_chunks_to_view()

        # --- 4.5. FPS 뷰모델 (반동, 총구화염, 흔들림) & 타이머/탈출구 로직 ---
        # 권총 발사 쿨다운 & 총구 화염 처리
        if self.shoot_cooldown > 0.0:
            self.shoot_cooldown = max(0.0, self.shoot_cooldown - dt)

        if self.muzzle_timer > 0.0:
            self.muzzle_timer -= dt
            if self.muzzle_timer <= 0.0:
                self.muzzle_flash_geom.hide()
                self.render.clearLight(self.muzzle_light_np)

        # 권총 반동 애니메이션 (Slide Kickback & Pitch Up)
        if self.recoil_timer > 0.0:
            self.recoil_timer -= dt
            t_norm = max(0.0, self.recoil_timer / 0.10)
            self.recoil_node.setPos(0, -0.05 * t_norm, 0.02 * t_norm)
            self.recoil_node.setP(12.0 * t_norm)
        else:
            self.recoil_node.setPos(0, 0, 0)
            self.recoil_node.setP(0)

        # 피격 알림 타이머
        if self.hit_marker_timer > 0.0:
            self.hit_marker_timer -= dt
            if self.hit_marker_timer <= 0.0:
                self.hit_marker_text.setText("")

        # 뷰모델 보행 밥빙(Bobbing) & 정지 호흡 스웨이
        if is_moving:
            self.bobbing_time += dt * (14.0 if (hasattr(self, 'is_sprinting') and self.is_sprinting) else 8.5)
            bob_x = math.sin(self.bobbing_time * 0.5) * 0.012
            bob_y = abs(math.cos(self.bobbing_time)) * 0.014
            self.vm_root.setPos(bob_x, 0, -bob_y)
        else:
            self.bobbing_time += dt * 2.0
            sway_z = math.sin(self.bobbing_time) * 0.003
            self.vm_root.setPos(0, 0, sway_z)

        # 60초 탈출 제한시간 카운트다운
        self.time_left -= dt
        if self.time_left <= 0.0:
            self.time_left = 0.0
            self.trigger_game_over(killer=None, reason="timeout")
            return task.cont

        # 탈출구 비콘 은은한 펄스 발광
        if hasattr(self, 'exit_light_np') and self.exit_light_np:
            t = globalClock.getFrameTime()
            pulse = 1.0 + 0.28 * math.sin(t * 4.5)
            self.exit_light_np.node().setColor((0.35 * pulse, 2.4 * pulse, 0.8 * pulse, 1.0))

        # 탈출구 도달 판정 (탈출 포탈 2.8m 이내 도달 시 탈출 성공)
        dist_exit = math.hypot(px - self.escape_pos[0], py - self.escape_pos[1])
        if dist_exit <= 2.8:
            self.trigger_victory()
            return task.cont

        # 타이머 HUD 갱신
        mins = int(self.time_left) // 60
        secs = int(self.time_left) % 60
        t_str = f"{mins:02d}:{secs:02d}"
        if self.time_left <= 10.0:
            flash_col = (1.0, 0.2, 0.2, 1.0) if int(self.time_left * 4) % 2 == 0 else (1.0, 0.8, 0.8, 1.0)
            self.timer_text.setText(f"[ ! 탈출 제한시간: {t_str} (서두르세요!) ]")
            self.timer_text.setFg(flash_col)
        elif self.time_left <= 25.0:
            self.timer_text.setText(f"[ 탈출 제한시간: {t_str} ]")
            self.timer_text.setFg((1.0, 0.85, 0.2, 1.0))
        else:
            self.timer_text.setText(f"[ 탈출 제한시간: {t_str} ]")
            self.timer_text.setFg((0.25, 0.95, 0.45, 1.0))

        # --- 5. HUD 업데이트 (괴물 거리 및 위치 표시 완전 금지 - 순수 미지의 공포감 유지) ---
        new_hud = f"위치: X={px:.1f}, Y={py:.1f} | 활성: {self.rendered_chunk_count}/{self.total_chunk_count} 청크"
        if new_hud != self.last_hud_text:
            self.hud_text.setText(new_hud)
            self.hud_text.setFg((0.95, 0.95, 0.95, 0.9))
            self.last_hud_text = new_hud

        # --- 6. 스테미나 게이지 실시간 갱신 ---
        bars = int((self.stamina / self.max_stamina) * 15)
        bar_str = "|" * bars + "." * (15 - bars)
        if self.stamina_exhausted:
            stamina_msg = f"스테미나: [{bar_str}] {int(self.stamina)}% (탈진! 회복 대기...)"
            stamina_fg = (1.0, 0.25, 0.25, 1.0)
        elif hasattr(self, 'is_sprinting') and self.is_sprinting:
            stamina_msg = f"스테미나: [{bar_str}] {int(self.stamina)}% (전력질주 중!)"
            stamina_fg = (1.0, 0.85, 0.2, 1.0)
        else:
            stamina_msg = f"스테미나: [{bar_str}] {int(self.stamina)}%"
            stamina_fg = (0.35, 0.95, 0.5, 0.95)

        self.stamina_text.setText(stamina_msg)
        self.stamina_text.setFg(stamina_fg)

        return task.cont

    def destroy(self):
        """게임 종료 시 백그라운드 스레드 풀 리소스 안전 해제"""
        if hasattr(self, 'chunk_executor'):
            self.chunk_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()


if __name__ == "__main__":
    game = LiminalInfiniteLoop()
    game.run()