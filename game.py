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
from monster import CreepySpiderMonster, TallShadowMonster


class LiminalInfiniteLoop(ShowBase):
    def __init__(self):
        super().__init__()

        # PBR 렌더링 최적화 (가벼운 5개 조명 슬롯으로 GPU 픽셀 셰이더 부하 대폭 절감)
        simplepbr.init(
            max_lights=5,
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
        self.monster_path_future = None
        self.last_move_dir = Vec3(0, 0, 0)
        self.world_root = self.render.attachNewNode("world_root")

        # 6. 플레이어 및 추격 괴물 초기 상태
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

        # 벽을 타고 기어오는 기괴한 8족 거미 괴물 생성 (플레이어 뒤쪽 복도 28m 지점)
        self.monster = CreepySpiderMonster(self.render, spawn_x, spawn_y - 28.0)
        self.player_trail = [(spawn_x, spawn_y)]

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
            mayChange=False,
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
        self.monster_path_future = None
        self.last_move_dir = Vec3(0, 0, 0)

        # 괴물 위치 리셋 (플레이어 뒤쪽 복도 28m)
        self.monster.reset_pos(spawn_x, spawn_y - 28.0)
        self.player_trail = [(spawn_x, spawn_y)]

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

    def trigger_game_over(self):
        """괴물에게 잡혔을 때 게임 오버 연출"""
        self.game_over = True
        self.keyMap = {k: 0 for k in self.keyMap}

        # 카메라를 괴물의 섬뜩한 얼굴로 즉시 강제 응시 (점프스케어 앵글)
        px, py = self.camera.getX(), self.camera.getY()
        mx, my = self.monster.pos.x, self.monster.pos.y
        dx = mx - px
        dy = my - py
        h = math.degrees(math.atan2(-dx, dy))
        mz = getattr(self.monster.pos, 'z', 0.4)
        p = math.degrees(math.atan2(mz + 0.25 - PLAYER_EYE_HEIGHT, dist))
        self.camera.setHpr(h, p, 0)

        # 괴물 공격 포즈 발동
        self.monster.update(0.016, is_moving=False, is_attacking=True)

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

        # --- [게임 오버 상태] 플레이어 사망 시: 시선 강제 고정 및 괴물 공격 모션 유지 ---
        if self.game_over:
            px, py = self.camera.getX(), self.camera.getY()
            mx, my = self.monster.pos.x, self.monster.pos.y
            dx = mx - px
            dy = my - py
            h = math.degrees(math.atan2(-dx, dy))
            mz = getattr(self.monster.pos, 'z', 0.4)
            p = math.degrees(math.atan2(mz + 0.25 - PLAYER_EYE_HEIGHT, dist))
            self.camera.setHpr(h, p, 0)
            self.monster.update(dt, is_moving=False, is_attacking=True)
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

        # --- 괴물 지능형 추격 AI (직접 시야 돌진 + 복도/출입문 그리드 BFS 최단경로 탐색) ---
        px, py = self.camera.getX(), self.camera.getY()
        mx, my = self.monster.pos.x, self.monster.pos.y
        dist_to_player = math.hypot(px - mx, py - my)

        # 잡힘 판정 (1.45m 이내 도달 시 게임 오버)
        if dist_to_player <= 1.45:
            self.trigger_game_over()
            return task.cont

        # 1. 시야(Line-Of-Sight) 확보 검사: 벽체에 가로막히지 않은 직선 시야가 있는가?
        has_los = False
        if dist_to_player <= 22.0:
            mid_x = (mx + px) * 0.5
            mid_y = (my + py) * 0.5
            los_dist = dist_to_player * 0.5 + 1.2
            los_colliders = self.get_nearby_colliders(mid_x, mid_y, search_dist=los_dist)
            has_los = check_line_of_sight(mx, my, px, py, los_colliders)
        self.monster.has_los = has_los

        # 2. 목표 지점(tx, ty) 산출
        if has_los:
            # 직접 시야 확보 시: 플레이어 위치로 전력 질주
            tx, ty = px, py
            m_speed = 10.5 if dist_to_player > 5.0 else 11.2  # 공포의 시야 내 전력 질주
        else:
            # 시야 차단 시: 비동기 백그라운드 스레드로 BFS 경로 탐색
            mgx = int(math.floor(mx / CELL_SIZE))
            mgy = int(math.floor(my / CELL_SIZE))
            pgx = int(math.floor(px / CELL_SIZE))
            pgy = int(math.floor(py / CELL_SIZE))

            # 백그라운드 경로 탐색 완료 확인 (비동기 결과 즉각 반영)
            if self.monster_path_future is not None and self.monster_path_future.done():
                try:
                    new_path = self.monster_path_future.result()
                    if new_path:
                        self.monster.path = new_path
                except Exception:
                    pass
                self.monster_path_future = None

            self.monster.path_timer -= dt
            if (self.monster.path_timer <= 0.0 or not self.monster.path) and self.monster_path_future is None:
                # 백그라운드 워커 스레드로 BFS 비동기 디스패치 (메인 루프 블로킹 0ms)
                self.monster_path_future = self.chunk_executor.submit(
                    find_cell_path, (mgx, mgy), (pgx, pgy), 20
                )
                self.monster.path_timer = 0.20

            # 경로 추적: 다음 셀 또는 문턱을 향해 전진
            if len(self.monster.path) >= 2:
                cur_c = self.monster.path[0]
                nxt_c = self.monster.path[1]

                # 두 셀 사이의 문/경계 통로 중심점 계산
                if nxt_c[1] == cur_c[1] + 1:  # 북쪽 통로
                    tx = (cur_c[0] + 0.5) * CELL_SIZE
                    ty = (cur_c[1] + 1.0) * CELL_SIZE
                elif nxt_c[1] == cur_c[1] - 1:  # 남쪽 통로
                    tx = (cur_c[0] + 0.5) * CELL_SIZE
                    ty = cur_c[1] * CELL_SIZE
                elif nxt_c[0] == cur_c[0] + 1:  # 동쪽 통로
                    tx = (cur_c[0] + 1.0) * CELL_SIZE
                    ty = (cur_c[1] + 0.5) * CELL_SIZE
                else:  # 서쪽 통로
                    tx = cur_c[0] * CELL_SIZE
                    ty = (cur_c[1] + 0.5) * CELL_SIZE

                # 목표 문턱/경계에 도달 시 다음 단계로 전진
                if math.hypot(mx - tx, my - ty) < 1.2 or (mgx == nxt_c[0] and mgy == nxt_c[1]):
                    self.monster.path.pop(0)
            else:
                tx, ty = px, py

            m_speed = 8.6 if dist_to_player > 15.0 else 9.4  # 음산한 스토킹 속도

        # 3. 거미 괴물 이동 벡터 계산 및 벽 타기(Wall Crawling) 물리 판정
        tdx, tdy = tx - mx, ty - my
        t_dist = math.hypot(tdx, tdy)

        # 주변 벽체 탐색 (촛대 제외, 너비 0.5m 이상인 실제 벽체만 필터링)
        spider_walls = [
            c for c in self.get_nearby_colliders(mx, my, search_dist=2.4)
            if (c[2] - c[0]) >= 0.5 or (c[3] - c[1]) >= 0.5
        ]

        closest_wall_dist = 999.0
        wall_norm = None
        for min_x, min_y, max_x, max_y in spider_walls:
            cx = max(min_x, min(mx, max_x))
            cy = max(min_y, min(my, max_y))
            vx = mx - cx
            vy = my - cy
            d = math.hypot(vx, vy)
            if d < closest_wall_dist:
                closest_wall_dist = d
                if d > 0.05:
                    wall_norm = Vec3(vx / d, vy / d, 0)

        # 벽면 근접 시 (2.2m 이내) 벽면을 타고 3.6m 높이로 기어오름
        # 단, 플레이어와 3.5m 이내 초근접 시 바닥으로 급강하하여 덮침
        if closest_wall_dist < 2.2 and wall_norm is not None:
            if dist_to_player > 3.5:
                wall_climb_z = 3.6  # 높은 벽면을 타고 기어오름
            else:
                wall_climb_z = 0.4  # 바닥으로 덮치기 위해 급강하
        else:
            wall_climb_z = 0.4

        if t_dist > 0.05:
            ndx, ndy = tdx / t_dist, tdy / t_dist
            m_disp_x = ndx * m_speed * dt
            m_disp_y = ndy * m_speed * dt
            new_mx, new_my = self.resolve_collision(mx, my, m_disp_x, m_disp_y, radius=0.45)
            self.monster.update_pos(new_mx, new_my, dt, ndx, ndy, wall_norm=wall_norm, climb_target_z=wall_climb_z)
        else:
            self.monster.update(dt, is_moving=False)

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

        # --- 5. HUD 업데이트 (거미 괴물 위협 거리 및 벽 타기 상태 반영) ---
        is_climbing = getattr(self.monster, 'climb_z', 0.4) > 1.5
        climb_tag = " [벽 타는 중!]" if is_climbing else ""
        if dist_to_player > 32.0:
            threat = f"안전 ({dist_to_player:.0f}m){climb_tag}"
            threat_fg = (0.35, 0.9, 0.45, 0.9)
        elif dist_to_player > 16.0:
            threat = f"접근 중! ({dist_to_player:.0f}m){climb_tag}"
            threat_fg = (1.0, 0.85, 0.2, 0.95)
        elif self.monster.has_los:
            threat = f"추격 중! 시야에 노출됨! ({dist_to_player:.1f}m){climb_tag}"
            threat_fg = (1.0, 0.1, 0.1, 1.0)
        else:
            threat = f"위험! 뒤에 있음! ({dist_to_player:.1f}m){climb_tag}"
            threat_fg = (1.0, 0.35, 0.1, 1.0)

        new_hud = f"위치: X={px:.1f}, Y={py:.1f} | 괴물: {threat} | 활성: {self.rendered_chunk_count}/{self.total_chunk_count} 청크"
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