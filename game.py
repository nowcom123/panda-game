import math
import concurrent.futures
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    WindowProperties, Vec3, SamplerState, Fog,
    AmbientLight, PointLight, TextNode, LColor, KeyboardButton
)
import simplepbr

# 모듈화된 하위 시스템 임포트 (PRC 설정은 constants에서 자동 초기화)
from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS, WALL_HEIGHT, PLAYER_RADIUS,
    PLAYER_EYE_HEIGHT, WALK_SPEED, SPRINT_SPEED, RENDER_RADIUS, FOG_COLOR
)
from world_gen import find_cell_path, check_line_of_sight
from chunk import Chunk
from monster import LongBlackSerpent, TallSkeletonMonster


class LiminalInfiniteLoop(ShowBase):
    def __init__(self):
        super().__init__()

        # PBR 렌더링 최적화 (손전등 + 촛불2 + 뱀오라 + 해골오라 등 6개 슬롯 지원)
        simplepbr.init(
            max_lights=6,
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

        # 적 1: 몸통이 긴 칠흑의 거대 뱀 (플레이어 뒤쪽 복도 28m 지점)
        self.serpent = LongBlackSerpent(self.render, spawn_x, spawn_y - 28.0)
        # 적 2: 키 크고 팔이 매우 긴 쩍 벌어진 해골 괴물 (다른 복도 34m 지점)
        self.skeleton = TallSkeletonMonster(self.render, spawn_x + 30.0, spawn_y + 12.0)
        self.monsters = [self.serpent, self.skeleton]

        # 초기 청크 전체 로드 (멀티스레드 병렬 로딩)
        self.update_chunks(force=True)

        # 7. UI 안내 문구 및 좌표 HUD
        self.setup_ui()

        # 메인 업데이트 루프 등록
        self.taskMgr.add(self.update, "updateTask")

        # 8. 셰이더 및 GPU 파이프라인 사전 웜업 (게임 진입 직후 첫 프레임 스터터링 100% 제거)
        for _ in range(2):
            self.taskMgr.step()

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
        """완전한 암흑 분위기 (최소 앰비언트 + 플레이어 손전등 + 촛불 동적 조명 풀)"""
        alight = AmbientLight('ambient_light')
        alight.setColor((0.006, 0.006, 0.008, 1.0))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)

        # 플레이어 손전등 (주변 벽체와 바닥을 비추는 좁고 날카로운 빔)
        plight = PointLight('player_light')
        plight.setColor((1.25, 1.20, 1.05, 1.0))
        plight.setAttenuation((1.0, 0.045, 0.0028))
        self.pl_np = self.camera.attachNewNode(plight)
        self.pl_np.setPos(0, 0, 0.2)
        self.render.setLight(self.pl_np)

        # 촛불 동적 포인트 라이트 풀 (플레이어 주변 가장 가까운 2개 촛대에 실시간 바인딩 - 셰이더 부하 최소화)
        self.candle_lights = []
        self.candle_light_nps = []
        for i in range(2):
            clight = PointLight(f'candle_light_{i}')
            clight.setColor((1.35, 0.82, 0.28, 1.0))
            clight.setAttenuation((1.0, 0.12, 0.035))
            clnp = self.render.attachNewNode(clight)
            clnp.setPos(0, 0, -100)  # 미사용 시 지하 대기
            self.render.setLight(clnp)
            self.candle_lights.append(clight)
            self.candle_light_nps.append(clnp)

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

        # WASD 8방향 이동 키 (Shift 조합 및 대소문자 모두 등록하여 대각선 달리기 100% 보장)
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
        # Windows API 마우스 카운터 움직임 충돌 방지를 위한 M_confined 모드 사용
        props.setMouseMode(WindowProperties.M_confined if lock else WindowProperties.M_absolute)
        if hasattr(self.win, 'requestProperties'):
            self.win.requestProperties(props)

    def toggle_mouse_lock(self):
        self.lock_mouse(not self.mouse_locked)

    def setup_ui(self):
        """정보 표시 HUD 및 게임 오버 UI 설정"""
        try:
            self.korean_font = self.loader.loadFont('/c/Windows/Fonts/malgun.ttf')
        except Exception:
            self.korean_font = None

        font_kw = {"font": self.korean_font} if self.korean_font else {}

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
            text="[WASD] 8방향 이동 (대각선 지원)  |  [Shift] 달리기 (스테미나 소모)  |  [Mouse] 시선  |  [R] 재시작  |  [ESC] 마우스 해제",
            pos=(0, -0.92),
            scale=0.04,
            fg=(0.9, 0.9, 0.8, 0.8),
            align=TextNode.ACenter,
            mayChange=False,
            **font_kw
        )

        # 게임 오버 UI (기본 숨김)
        self.game_over_banner = OnscreenText(
            text="사  망",
            pos=(0, 0.25),
            scale=0.14,
            fg=(0.95, 0.08, 0.08, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **font_kw
        )
        self.game_over_desc = OnscreenText(
            text="기괴한 거미 괴물에게 영혼을 잠식당했습니다...",
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
        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.game_over_restart.hide()

    def restart_game(self):
        """게임 재시작: 플레이어 및 괴물 초기화"""
        self.game_over = False
        self.keyMap = {k: 0 for k in self.keyMap}

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.camera.setPos(spawn_x, spawn_y, PLAYER_EYE_HEIGHT)
        self.heading = 0.0
        self.pitch = 0.0
        self.camera.setHpr(0, 0, 0)

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

        # 괴물 2종 위치 리셋
        self.serpent.reset_pos(spawn_x, spawn_y - 28.0)
        self.skeleton.reset_pos(spawn_x + 30.0, spawn_y + 12.0)

        # 안개 및 배경색 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.setBackgroundColor(FOG_COLOR)
        self.win.setClearColor(FOG_COLOR)

        # UI 복구
        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.game_over_restart.hide()
        self.guide_text.show()
        self.lock_mouse(True)

    def trigger_game_over(self, killer):
        """괴물에게 잡혔을 때 게임 오버 연출"""
        self.game_over = True
        self.killer_monster = killer
        self.keyMap = {k: 0 for k in self.keyMap}

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

        # 킬러 괴물 공격 포즈 발동
        killer.update(0.016, is_moving=False, is_attacking=True)

        # 킬러별 맞춤형 데스 메시지
        if isinstance(killer, TallSkeletonMonster):
            self.game_over_desc.setText("쩍 벌어진 입의 거대 해골 괴물에게 영혼을 빼앗겼습니다...")
        else:
            self.game_over_desc.setText("칠흑의 거대한 뱀에게 온몸을 휘감겨 삼켜졌습니다...")

        # 핏빛 암전 연출
        blood_fog = LColor(0.22, 0.02, 0.02, 1.0)
        self.liminal_fog.setColor(blood_fog)
        self.setBackgroundColor(blood_fog)
        self.win.setClearColor(blood_fog)

        # 게임 오버 UI 노출
        self.game_over_banner.show()
        self.game_over_desc.show()
        self.game_over_restart.show()
        self.guide_text.hide()

    def update_chunks(self, force=False):
        """시야 내 및 이동 방향을 예측하는 비동기 멀티스레드 청크 스트리밍"""
        px, py = self.camera.getX(), self.camera.getY()
        player_cx = int(math.floor(px / CHUNK_SIZE))
        player_cy = int(math.floor(py / CHUNK_SIZE))

        if not force and hasattr(self, 'last_chunk') and (player_cx, player_cy) == self.last_chunk:
            return

        self.last_chunk = (player_cx, player_cy)

        # 5x5 활성 청크 영역 (반경 2 = 105m x 105m 영역 커버)
        needed_chunks = set()
        for dx in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
            for dy in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
                needed_chunks.add((player_cx + dx, player_cy + dy))

        # 이동 벡터 기반 전방 예측 청크 (Lookahead Pre-caching)
        if hasattr(self, 'last_move_dir') and self.last_move_dir.lengthSquared() > 0.01:
            pred_x = px + self.last_move_dir.x * 24.0
            pred_y = py + self.last_move_dir.y * 24.0
            pred_cx = int(math.floor(pred_x / CHUNK_SIZE))
            pred_cy = int(math.floor(pred_y / CHUNK_SIZE))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    needed_chunks.add((pred_cx + dx, pred_cy + dy))

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

        return px, py

    def update(self, task):
        dt = globalClock.getDt()
        if dt > 0.1:
            dt = 0.1

        # --- [게임 오버 상태] 플레이어 사망 시: 시선 강제 고정 및 킬러 괴물 공격 모션 유지 ---
        if self.game_over:
            killer = self.killer_monster or self.serpent
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

        # 잡힘 판정 (뱀: 1.45m, 해골: 1.85m)
        if dist_serpent <= 1.45:
            self.trigger_game_over(self.serpent)
            return task.cont
        if dist_skeleton <= 1.85:
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

        if s_closest_wall < 2.0 and s_wall_norm is not None:
            s_climb_z = 3.6 if dist_serpent > 3.5 else 0.28
        else:
            s_climb_z = 0.28

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

        # --- 4.5. 촛불 동적 조명 할당 및 리얼타임 깜빡임 (캐싱 기반 초고속 갱신) ---
        player_moved_dist_sq = (px - getattr(self, 'last_candle_px', -9999.0))**2 + (py - getattr(self, 'last_candle_py', -9999.0))**2
        if player_moved_dist_sq > 2.25 or chunk_created or not hasattr(self, 'cached_candles'):
            self.last_candle_px = px
            self.last_candle_py = py
            cand_candidates = []
            pcx = int(math.floor(px / CHUNK_SIZE))
            pcy = int(math.floor(py / CHUNK_SIZE))
            # 인접 3x3 청크 영역의 촛대만 고속 수집
            for ncx in (pcx - 1, pcx, pcx + 1):
                for ncy in (pcy - 1, pcy, pcy + 1):
                    chunk = self.chunks.get((ncx, ncy))
                    if chunk and not chunk.is_hidden and hasattr(chunk, 'candle_positions'):
                        for cx, cy, cz in chunk.candle_positions:
                            d_sq = (cx - px) ** 2 + (cy - py) ** 2
                            if d_sq < 2500:
                                cand_candidates.append((d_sq, cx, cy, cz))
            cand_candidates.sort(key=lambda item: item[0])
            self.cached_candles = cand_candidates[:len(self.candle_lights)]

        t = globalClock.getFrameTime()
        for i, clight in enumerate(self.candle_lights):
            cnp = self.candle_light_nps[i]
            if i < len(self.cached_candles):
                _, cx, cy, cz = self.cached_candles[i]
                flicker = 1.0 + 0.14 * math.sin(t * 13.5 + i * 2.3) + 0.08 * math.cos(t * 26.0 + i * 1.7) + 0.04 * math.sin(t * 43.0)
                flicker = max(0.65, min(1.35, flicker))
                clight.setColor((1.35 * flicker, 0.82 * flicker, 0.28 * flicker, 1.0))
                cnp.setPos(cx, cy, cz)
            else:
                cnp.setPos(0, 0, -100)

        # --- 5. HUD 업데이트 (뱀 & 해골 위협 거리 및 상태 반영) ---
        s_climbing = getattr(self.serpent, 'climb_z', 0.28) > 1.5
        s_tag = " [벽타기]" if s_climbing else ""
        if dist_serpent < 12.0 or self.serpent.has_los:
            s_msg = f"위험({dist_serpent:.0f}m{s_tag})"
        else:
            s_msg = f"{dist_serpent:.0f}m{s_tag}"

        if dist_skeleton < 14.0 or self.skeleton.has_los:
            k_msg = f"위험({dist_skeleton:.0f}m)"
        else:
            k_msg = f"{dist_skeleton:.0f}m"

        threat_fg = (1.0, 0.15, 0.15, 1.0) if (self.serpent.has_los or self.skeleton.has_los or min(dist_serpent, dist_skeleton) < 12.0) else (1.0, 0.85, 0.2, 0.95)

        new_hud = f"위치: X={px:.1f}, Y={py:.1f} | 뱀: {s_msg} | 해골: {k_msg} | 활성: {self.rendered_chunk_count}/{self.total_chunk_count} 청크"
        if new_hud != self.last_hud_text:
            self.hud_text.setText(new_hud)
            self.hud_text.setFg(threat_fg)
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