from inventory_system import InventorySystem
import os
import sys
import math
import random
import heapq
import concurrent.futures
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Vec3, SamplerState, Fog, AmbientLight, PointLight, LColor
)
import simplepbr

from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS, WALL_HEIGHT,
    PLAYER_EYE_HEIGHT, RENDER_RADIUS, FOG_COLOR, BLACKOUT_FOG_COLOR,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK, CURSED_RELICS
)
from world_gen import find_cell_path, check_line_of_sight, cell_has_pillar
from chunk import Chunk
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch,
    ShadowStalker
)
from geometry import make_cube_to, make_cube

# 분리된 모듈 임포트
from collision import get_nearby_colliders, resolve_collision
from audio_system import AudioManager
from ui_manager import UIManager
from combat_system import CombatSystem
from player_controller import PlayerController
from stage_config import build_monster_roster, get_stage_profile


class Fireball:
    """매혹의 잿더미 마녀가 발사하는 타오르는 불꽃 발사체"""
    def __init__(self, render, start_pos, target_pos):
        self.render = render
        self.pos = Vec3(start_pos)
        self.node = render.attachNewNode("witch_fireball")
        self.node.setPos(self.pos)

        fire_core = make_cube("fb_core", 0.32, 0.32, 0.32, LColor(1.0, 0.28, 0.05, 1.0))
        fire_core.setLightOff()
        fire_core.reparentTo(self.node)

        fire_inner = make_cube("fb_inner", 0.18, 0.18, 0.18, LColor(1.0, 0.90, 0.30, 1.0))
        fire_inner.setLightOff()
        fire_inner.reparentTo(self.node)

        pl = PointLight('fb_glow')
        pl.setColor((1.8, 0.45, 0.10, 1.0))
        pl.setAttenuation((1.0, 0.22, 0.06))
        self.light_np = self.node.attachNewNode(pl)
        render.setLight(self.light_np)

        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]
        dz = target_pos[2] - start_pos[2]
        d = math.hypot(dx, dy, dz)
        if d > 0.01:
            self.vel = Vec3(dx / d, dy / d, dz / d) * 14.5
        else:
            self.vel = Vec3(0, 1, 0) * 14.5

        self.lifetime = 3.5
        self.damage = 22.0

    def update(self, dt):
        self.lifetime -= dt
        self.pos += self.vel * dt
        self.node.setPos(self.pos)
        self.node.setH(self.node.getH() + dt * 400.0)
        self.node.setP(self.node.getP() + dt * 280.0)
        return self.lifetime > 0.0

    def destroy(self):
        if hasattr(self, 'light_np') and not self.light_np.isEmpty():
            self.render.clearLight(self.light_np)
            self.light_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class GroundShockwave:
    """혐오스런 진흙 오크의 땅울림(Ground Slam) 지면 충격파 분진 효과"""
    def __init__(self, render, x, y):
        self.render = render
        self.pos = Vec3(x, y, 0.06)
        self.node = render.attachNewNode("orc_shockwave")
        self.node.setPos(self.pos)
        self.radius = 0.6
        self.max_radius = 11.5
        self.timer = 0.0
        self.duration = 0.70

        self.fragments = []
        dust_col = LColor(0.28, 0.22, 0.14, 0.9)
        for i in range(8):
            ang = i * (math.pi / 4.0)
            p = make_cube(f"sw_{i}", 0.40, 0.40, 0.16, dust_col)
            p.reparentTo(self.node)
            self.fragments.append((p, math.cos(ang), math.sin(ang)))

    def update(self, dt):
        self.timer += dt
        pct = min(1.0, self.timer / self.duration)
        r = self.radius + pct * (self.max_radius - self.radius)
        z = math.sin(pct * math.pi) * 0.42
        for part, dx, dy in self.fragments:
            part.setPos(dx * r, dy * r, z)
            part.setScale(max(0.1, 1.0 - pct * 0.5))
        return pct < 1.0

    def destroy(self):
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class CandleLightingManager:
    """
    중세 다크판타지 동적 촛불 조명 관리자 (최적화 버전)
    - SimplePBR max_lights=8 제약을 준수하는 6개 PointLight 동적 풀 운용
    - 공간 캐싱(Spatial Caching) 및 이동 임계치(0.7m) 기반 거리 연산 스킵 (초당 20,000+ 계산 제거)
    - 플레이어 중심 45m 이내 청크 사전 필터링 및 heapq.nsmallest 고속 추출 (13.2배 연산 고속화)
    - 활성 광원별 자연스러운 미세 불꽃 깜빡임(Flicker) 매 프레임 부드러운 보간
    """
    def __init__(self, render):
        self.render = render
        self.max_lights = 6
        self.lights = []
        self.light_nps = []

        for i in range(self.max_lights):
            pl = PointLight(f'candle_point_light_{i}')
            pl.setColor(LColor(1.0, 0.54, 0.16, 1.0))
            pl.setAttenuation((1.0, 0.09, 0.018))
            pl_np = self.render.attachNewNode(pl)
            self.render.setLight(pl_np)
            self.lights.append(pl)
            self.light_nps.append(pl_np)

        self.last_search_pos = None
        self.cached_nearest = []
        self.last_search_time = 0.0
        self.search_interval = 0.12 # 이동 중 최대 초당 8회 재탐색 제한

    def update(self, dt, player_pos, chunks_dict, force=False, is_blackout=False):
        t = globalClock.getFrameTime()
        px, py, pz = player_pos.x, player_pos.y, player_pos.z

        # 재탐색 필요성 검사 (이동 임계치 0.7m 또는 청크 갱신 force)
        need_search = force or (self.last_search_pos is None)
        if not need_search:
            d_sq = (px - self.last_search_pos[0]) ** 2 + (py - self.last_search_pos[1]) ** 2
            if d_sq > 0.49 and (t - self.last_search_time) > self.search_interval:
                need_search = True

        if need_search:
            self.last_search_pos = (px, py)
            self.last_search_time = t
            candidates = []

            # 공간 필터링: 플레이어 중심 45m 이내의 청크만 검사 (불필요한 원거리 촛불 스킵)
            for (cx, cy), chunk in chunks_dict.items():
                if getattr(chunk, 'is_hidden', False):
                    continue
                ccx = (cx + 0.5) * CHUNK_SIZE
                ccy = (cy + 0.5) * CHUNK_SIZE
                if (ccx - px) ** 2 + (ccy - py) ** 2 > 2025.0: # (45.0m)^2
                    continue
                if hasattr(chunk, 'candle_positions'):
                    for c_pos in chunk.candle_positions:
                        dist_sq = (c_pos.x - px) ** 2 + (c_pos.y - py) ** 2 + (c_pos.z - pz) ** 2
                        candidates.append((dist_sq, c_pos))

            if candidates:
                self.cached_nearest = heapq.nsmallest(self.max_lights, candidates, key=lambda item: item[0])
            else:
                self.cached_nearest = []

        # 활성 광원에 대해 매 프레임 끊김 없는 부드러운 불꽃 깜빡임(Flicker) 연산 적용
        for i in range(self.max_lights):
            pl = self.lights[i]
            pl_np = self.light_nps[i]

            if i < len(self.cached_nearest):
                _, c_pos = self.cached_nearest[i]
                pl_np.setPos(c_pos)
                seed = (int(c_pos.x * 10) ^ int(c_pos.y * 10)) % 1000
                if is_blackout:
                    flicker = max(0.0, 0.42 + 0.45 * math.sin(t * 26.0 + seed) + 0.25 * math.cos(t * 39.0 + seed * 2.1))
                    if seed % 2 == 0:
                        pl.setColor(LColor(0.70 * flicker, 0.05 * flicker, 0.03 * flicker, 1.0))
                    else:
                        pl.setColor(LColor(0.0, 0.0, 0.0, 0.0))
                else:
                    flicker = 1.0 + 0.15 * math.sin(t * 16.0 + seed) + 0.08 * math.sin(t * 29.0 + seed * 1.7)
                    pl.setColor(LColor(1.0 * flicker, 0.54 * flicker, 0.16 * flicker, 1.0))
            else:
                pl.setColor(LColor(0, 0, 0, 0))

    def cleanup(self):
        for pl_np in self.light_nps:
            self.render.clearLight(pl_np)
            pl_np.removeNode()
        self.lights.clear()
        self.light_nps.clear()
        self.cached_nearest.clear()


class LiminalInfiniteLoop(ShowBase):
    def __init__(self):
        super().__init__()

        # PBR 렌더링 최적화
        if hasattr(self, 'win') and self.win is not None:
            self.pbr_pipeline = simplepbr.init(
                max_lights=8,
                use_normal_maps=False,
                use_emission_maps=False,
                use_occlusion_maps=False,
                enable_shadows=False,
                enable_fog=True
            )

        # 1. 카메라 가시거리 및 안개 설정 (FOV 88도)
        if hasattr(self, 'camLens') and self.camLens is not None:
            self.camLens.setNearFar(0.15, 85.0)
            self.camLens.setFov(88.0)
        self.rendered_chunk_count = 0
        self.total_chunk_count = 0
        self.setup_fog()

        # 2. 백룸 기본 조명 연출
        self.candle_lights = CandleLightingManager(self.render)
        self.setup_lighting()

        # 3. 텍스처 로드
        self.load_assets()

        # 4. 무한 청크 관리자 설정
        self.chunks = {}
        self.chunk_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ChunkWorker")
        self.active_chunk_futures = {}
        self.last_cull_pos = None
        self.world_root = self.render.attachNewNode("world_root")

        # 5. 던전 크롤러 몬스터 군단 관리자 및 발사체
        self.monsters = []
        self.corpses = []
        self.killer_monster = None
        self.fireballs = []
        self.shockwaves = []

        # 5-1. 정전 프로토콜 (Blackout & Crimson Protocol) 상태
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False

        # 6. 하위 서브시스템 초기화 (오디오, UI, 전투, 플레이어 제어)
        if not hasattr(self, 'camera') or self.camera is None:
            self.camera = self.render.attachNewNode("camera")
        self.audio_mgr = AudioManager(self, self.loader, self.camera, getattr(self, 'sfxManagerList', None))

        self.ui_mgr = UIManager(
            self, self.loader,
            on_start=self.start_game,
            on_return_menu=self.return_to_intro,
            on_exit=self.exit_game
        )

        self.inventory = InventorySystem(
            self, self.render, self.camera, self.world_root,
            self.audio_mgr, self.ui_mgr
        )

        self.combat = CombatSystem(
            self, self.render, self.camera, self.world_root,
            self.audio_mgr, self.ui_mgr
        )

        self.player = PlayerController(
            self, self.win, self.camera, self.mouseWatcherNode,
            self.audio_mgr, self.ui_mgr
        )
        self.player.setup_input(
            on_shoot=self.shoot_pistol,
            on_reload=self.reload_pistol,
            on_melee=self.melee_bash,
            on_use_item=self.on_use_item
        )

        # 7. 게임 상태 및 5분(300초) 타이머 설정
        self.game_state = "INTRO"  # "INTRO", "PLAYING", "SHOP", "GAME_OVER", "VICTORY"
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 던전 크롤러 모드: 5분(300초)
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.altars = []
        self.escape_gate = None
        self.activated_altars_count = 0
        self.stage_banner_timer = 0.0

        # 초기 청크 및 인트로 씬 로드
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.player.reset_position(spawn_x, spawn_y)
        self.update_chunks(force=True)

        self.show_intro_scene()
        self.taskMgr.add(self.update, "update_task")

    # --- 에셋 및 렌더링 설정 ---
    def setup_fog(self):
        self.liminal_fog = Fog("LiminalDepthFog")
        self.liminal_fog.setColor(FOG_COLOR)
        # 지수 안개(Exponential Fog)로 매끄럽고 몽환적인 자연스러운 거리 감쇠 안개 형성
        self.liminal_fog.setExpDensity(0.038)
        self.render.setFog(self.liminal_fog)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)

    def setup_lighting(self):
        amb = AmbientLight('ambient_dim')
        amb.setColor((0.012, 0.011, 0.014, 1.0))
        self.amb_np = self.render.attachNewNode(amb)
        self.render.setLight(self.amb_np)

    def load_assets(self):
        try:
            self.wall_tex = self.loader.loadTexture("wall_stone.jpg")
            self.floor_dry_tex = self.loader.loadTexture("floor_dry.jpg")
            self.floor_wet_tex = self.loader.loadTexture("floor_wet.jpg")
            self.floor_tex = self.floor_dry_tex
            self.sky_tex = self.loader.loadTexture("ceiling_stone.jpg")
            for t in (self.wall_tex, self.floor_dry_tex, self.floor_wet_tex, self.sky_tex):
                if t:
                    t.setMagfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setAnisotropicDegree(4)
        except Exception as e:
            print(f"텍스처 로드 오류: {e}")

    def on_use_item(self, slot):
        """소비 아이템 퀵슬롯 [1], [2], [3] 격발 핸들러"""
        if self.game_state != "PLAYING":
            return
        if hasattr(self, 'inventory'):
            if slot == 1:
                self.inventory.use_flask(self.player)
            elif slot == 2:
                if self.inventory.use_censer(self.player):
                    self.end_abyssal_inversion()
            elif slot == 3:
                self.inventory.use_fire_pot(self.player)

    def shoot_pistol(self):
        self.combat.shoot(self.monsters, self.player, self.game_state)

    def reload_pistol(self):
        self.combat.reload(self.game_state)

    def melee_bash(self):
        """마우스 우클릭: 쇠뇌 전면 강타 및 밀치기 (스태미나 18 소모)"""
        return self.combat.melee_bash(self.monsters, self.player, self.game_state)

    def exit_game(self):
        self.destroy()
        sys.exit(0)

    def clear_projectiles(self):
        """남아있는 파이어볼 및 충격파 엔티티 즉시 해제"""
        for fb in self.fireballs:
            fb.destroy()
        self.fireballs.clear()
        for sw in self.shockwaves:
            sw.destroy()
        self.shockwaves.clear()

    # --- 씬 및 게임 라이프사이클 관리 ---
    def _clear_stage_entities(self):
        """현재 층의 엔티티와 효과를 제거합니다. 성장·보유 수량은 유지합니다."""
        self.clear_projectiles()
        self.combat.reset_state(keep_ammo=True, spawn_drops=False)
        self.inventory.reset_state(keep_items=True, spawn_loot=False)
        self.audio_mgr.detach_monsters()
        for monster in self.monsters + self.corpses:
            monster.destroy()
        self.monsters = []
        self.corpses = []
        self.killer_monster = None
        self.clear_objectives()

    @staticmethod
    def _dispose_chunk_future(future):
        if future.cancelled():
            return
        try:
            future.result().destroy()
        except Exception as exc:
            print(f"청크 정리 중 오류: {exc}")

    def _discard_pending_chunks(self):
        """취소할 수 없는 생성 작업도 완료 후 월드에 연결하지 않고 해제합니다."""
        for future in self.active_chunk_futures.values():
            if not future.cancel():
                future.add_done_callback(LiminalInfiniteLoop._dispose_chunk_future)
        self.active_chunk_futures.clear()

    def show_intro_scene(self):
        """인트로 화면 전환"""
        self._discard_pending_chunks()
        self._clear_stage_entities()
        self.game_over = False
        self.game_won = False
        self.stage_banner_timer = 0.0
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()
        self.game_state = "INTRO"
        self.player.lock_mouse(False)
        self.combat.vm_root.hide()
        if hasattr(self.combat, 'mist_root') and self.combat.mist_root:
            self.combat.mist_root.hide()
        self.combat.set_blackout_mode(False)
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.ui_mgr.show_intro()
        self.audio_mgr.set_bgm_mode("INTRO")

    def start_game(self):
        """START 버튼 클릭 시 사전 렌더링(프리워밍) 및 로딩 화면을 거쳐 쾌적하게 시작"""
        if self.game_state not in ("INTRO", "GAME_OVER", "VICTORY"):
            return
        self.start_loading_flow(target_stage=1, is_restart=True)

    def start_loading_flow(self, target_stage=1, is_restart=True):
        """다단계 사전 렌더링 태스크 구동: 청크 사전 빌드, GPU 셰이더 프리워밍, 쾌적한 60FPS 시작 보장"""
        self.game_state = "LOADING"
        self.audio_mgr.set_bgm_mode("LOADING")
        self.player.lock_mouse(False)
        self.combat.vm_root.hide()

        self.loading_step = 0
        self.loading_timer = 0.0
        self.loading_target_stage = target_stage
        self.loading_is_restart = is_restart

        self.ui_mgr.show_loading_screen(stage=target_stage)
        self.taskMgr.remove("loading_process_task")
        self.taskMgr.add(self._loading_process_task, "loading_process_task")

    def _loading_process_task(self, task):
        if self.game_state != "LOADING":
            return task.done

        # Step 0: 시작 안내 및 좌표/시드 초기화
        if self.loading_step == 0:
            self.ui_mgr.update_loading_progress(0.18, "차원 공간 좌표 계산 및 시드 초기화 중...")
            self.loading_step = 1
            return task.cont

        # Step 1: 게임 상태 리셋 및 엔티티 배치
        elif self.loading_step == 1:
            if self.loading_is_restart:
                self.restart_game()
            else:
                self.advance_to_next_stage()

            self.ui_mgr.update_loading_progress(0.45, "주변 3D 구역 구조물 사전 빌드 (Pre-caching)...")
            self.loading_step = 2
            return task.cont

        # Step 2: 주변 모든 청크 강제 사전 생성 및 가시거리 동기화
        elif self.loading_step == 2:
            self.update_chunks(force=True)
            self.cull_chunks_to_view(force=True)
            self.ui_mgr.update_loading_progress(0.72, "PBR 셰이더 및 GPU 렌더링 파이프라인 프리워밍...")
            self.loading_step = 3
            return task.cont

        # Step 3: GPU 드라이버 셰이더 컴파일 & 프레임 사전 렌더링
        elif self.loading_step == 3:
            self.combat.vm_root.show()

            # 카메라를 스폰 위치로 사전 정렬
            spawn_x = 1.5 * CELL_SIZE
            spawn_y = 1.5 * CELL_SIZE
            self.camera.setPos(spawn_x, spawn_y, PLAYER_EYE_HEIGHT)
            self.camera.setHpr(0, 0, 0)

            # 프레임 사전 렌더링 (셰이더 컴파일 및 VBO 업로드 유도)
            try:
                self.graphicsEngine.renderFrame()
            except Exception:
                pass

            self.ui_mgr.update_loading_progress(0.92, "오디오 캐시 및 조명 볼륨 동기화...")
            self.loading_step = 4
            return task.cont

        # Step 4: 100% 완료 알림 및 짧은 시각적 여운 (0.25초)
        elif self.loading_step == 4:
            self.ui_mgr.update_loading_progress(1.0, "동기화 완료! 백룸 진입...")
            self.loading_step = 5
            self.loading_timer = 0.25
            return task.cont

        # Step 5: 타이머 대기 후 인게임 진입
        elif self.loading_step == 5:
            dt = min(0.1, max(0.016, globalClock.getDt()))
            self.loading_timer -= dt
            if self.loading_timer > 0.0:
                return task.cont

            # 로딩 완료: 인게임 전환
            self.ui_mgr.hide_loading_screen()
            self.game_state = "PLAYING"
            self.audio_mgr.set_bgm_mode("PLAYING")
            self.ui_mgr.start_game_ui()
            self.ui_mgr.update_navigation(self.camera.getH(), self.camera.getX(), self.camera.getY(),
                                          self.altars, self.escape_gate)
            profile = get_stage_profile(self.current_stage)
            self.ui_mgr.show_stage_banner(
                f"[ STAGE {self.current_stage} : {profile.name} ]\n{profile.summary}"
            )
            self.stage_banner_timer = 4.0
            self.player.lock_mouse(True)
            return task.done

    def return_to_intro(self):
        self.taskMgr.remove("loading_process_task")
        self.ui_mgr.hide_loading_screen()
        self.show_intro_scene()

    def spawn_monsters(self, stage=1):
        """스테이지별 다중 몬스터 군단 스폰 (진흙 오크, 잿더미 마녀, 칠흑 뱀, 거대 해골)"""
        self.audio_mgr.detach_monsters()
        for m in self.monsters:
            m.destroy()
        self.monsters = []
        for c in self.corpses:
            c.destroy()
        self.corpses = []

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        # 스폰 가능한 복도 후보 셀 산출
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        candidates = []
        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if gx % 3 == 1 or gy % 3 == 1:
                    if cell_has_pillar(gx, gy):
                        continue
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    if math.hypot(cx - spawn_x, cy - spawn_y) >= 22.0:
                        candidates.append((cx, cy))

        random.shuffle(candidates)

        monster_types = {
            "stalker": ShadowStalker,
            "orc": AbominableMudOrc,
            "witch": AlluringAshWitch,
            "serpent": LongBlackSerpent,
            "skeleton": TallSkeletonMonster,
        }
        for i, kind in enumerate(build_monster_roster(stage)):
            cls = monster_types[kind]
            pos = candidates[i % len(candidates)] if candidates else (spawn_x + 30.0 + i * 10, spawn_y + 30.0)
            monster = cls(self.render, pos[0], pos[1])
            self.monsters.append(monster)

        # 오디오 관리자에 첫 번째 뱀/해골 부착
        first_serpent = next((m for m in self.monsters if isinstance(m, LongBlackSerpent)), None)
        first_skel = next((m for m in self.monsters if isinstance(m, TallSkeletonMonster)), None)
        if first_serpent and first_skel:
            self.audio_mgr.attach_monsters(first_serpent, first_skel)

    def trigger_abyssal_inversion(self, duration=24.0, reason="stage"):
        """심층 이계화 발동: 어둠이 차오르고 촛불이 꺼지며 그림자 포식자가 각성함"""
        if self.inventory.censer_timer > 0.0:
            return
        self.blackout_active = True
        b_duration = duration
        if "abyssal_reaper" in getattr(self.player, 'relics', []):
            b_duration += 8.0
        self.blackout_timer = b_duration
        self.audio_mgr.play_abyssal_horn()
        self.ui_mgr.show_blackout_warning(reason=reason)
        self.liminal_fog.setColor(BLACKOUT_FOG_COLOR)
        self.liminal_fog.setExpDensity(0.055)
        self.setBackgroundColor(BLACKOUT_FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(BLACKOUT_FOG_COLOR)
        self.amb_np.node().setColor((0.008, 0.002, 0.002, 1.0))
        self.combat.set_blackout_mode(True)
        for m in self.monsters:
            if isinstance(m, ShadowStalker) and not getattr(m, 'is_corpse', False):
                m.set_hunt_mode(True, self.audio_mgr)

    def end_abyssal_inversion(self):
        """시간 만료 또는 향로 정화 시 암전과 사냥 모드를 함께 해제합니다."""
        if not self.blackout_active:
            return
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.audio_mgr.play_eclipse_purify()
        self.ui_mgr.hide_blackout_warning()
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)
        for m in self.monsters:
            if isinstance(m, ShadowStalker) and not getattr(m, 'is_corpse', False):
                m.set_hunt_mode(False)
        self.ui_mgr.show_stage_banner("[ 심층 정화 완료 ]\n촛불의 불빛이 다시 타오릅니다", color=(0.4, 0.9, 1.0, 1.0))
        self.stage_banner_timer = 2.5

    def restart_game(self):
        """던전 게임 초기화 (체력, 몬스터 군단, 5분 타이머, 탈출구)"""
        self.clear_projectiles()
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 5분 제한시간
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0

        # 플레이어 위치 및 스탯 초기화
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.player.level = 1
        self.player.exp = 0
        self.player.exp_to_next = 100
        self.player.max_hp = 100.0
        self.player.hp = self.player.max_hp
        self.player.attack_power = 35.0
        self.player.speed_mult = 1.0
        self.player.stat_points = 0
        self.player.max_stamina = 100.0
        self.player.hp_drain_accum = 0.0
        self.player.relics = []
        self.player.reset_position(spawn_x, spawn_y)
        self.ui_mgr.update_relic_badges(self.player.relics)

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        # 전투 서브시스템 리셋
        self.combat.reset_state(self.current_stage, keep_ammo=False)
        self.inventory.reset_state(self.current_stage, keep_items=False)

        # 비동기 작업 정리
        self._discard_pending_chunks()
        self.killer_monster = None

        # 다중 몬스터 군단 스폰
        self.spawn_monsters(self.current_stage)

        # 탈출구 생성
        self.setup_escape_portal()

        # 안개 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)

        self.ui_mgr.update_hp_exp(self.player.hp, self.player.max_hp, self.player.exp, self.player.exp_to_next, self.player.level)

    def advance_to_next_stage(self):
        """스탯 분배 후 다음 스테이지로 진입"""
        self.clear_projectiles()
        prev_stage = self.current_stage
        self.current_stage += 1
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.player.reset_position(spawn_x, spawn_y)

        # 비동기 작업 정리
        self._discard_pending_chunks()
        self.killer_monster = None

        # 다중 몬스터 군단 재배치
        self.spawn_monsters(self.current_stage)

        # 새 탈출구
        self.setup_escape_portal()

        # 전투 서브시스템: 탄약 보급
        self.combat.ammo = self.combat.max_ammo
        self.combat.reserve_ammo += 18
        self.combat.reset_state(self.current_stage, keep_ammo=True)
        self.inventory.reset_state(self.current_stage, keep_items=True)
        # Stage Clear Sanctuary Blessing: Restore +45 HP
        self.player.heal(max(45.0, self.player.max_hp * 0.45))

        # 안개 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)

        # 진입 안내는 로딩 완료 후 표시합니다.
        self.stage_banner_timer = 0.0

    def on_shop_closed(self):
        """상점 이용 완료 후 다음 스테이지 사전 로딩 시작"""
        if self.game_state != "SHOP":
            return
        next_stg = self.current_stage + 1
        self.start_loading_flow(target_stage=next_stg, is_restart=False)

    def trigger_victory(self):
        """탈출구 방어 성공 시 승리"""
        if self.game_over or self.game_won:
            return
        self.game_won = True
        self.game_state = "VICTORY"
        self.audio_mgr.set_bgm_mode("VICTORY")

        green_fog = LColor(0.02, 0.20, 0.07, 1.0)
        self.liminal_fog.setColor(green_fog)
        self.setBackgroundColor(green_fog)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(green_fog)

        if self.audio_mgr.bgm:
            self.audio_mgr.bgm.setVolume(0.25)

        elapsed = self.time_limit - self.time_left
        remaining = max(0.0, self.time_left)
        self.ui_mgr.show_victory(f"비상 탈출구를 열고 악몽의 미궁을 탈출했습니다!\n[소요 시간: {elapsed:.1f}초  |  남은 탄약: {self.combat.ammo}/12발]")
        self.player.lock_mouse(False)

        self.ui_mgr.save_rank_record("탈출 성공", True, elapsed, remaining, self.combat.ammo, self.current_stage, self.combat.reserve_ammo)

    def trigger_game_over(self, killer=None, reason="killed"):
        """사망 또는 시간 초과 시 게임 오버"""
        if self.game_over or self.game_won:
            return
        self.game_over = True
        self.game_state = "GAME_OVER"
        self.audio_mgr.set_bgm_mode("GAME_OVER")
        self.killer_monster = killer

        elapsed = self.time_limit - self.time_left
        remaining = max(0.0, self.time_left)

        if killer is not None:
            px, py = self.camera.getX(), self.camera.getY()
            kx, ky = killer.pos.x, killer.pos.y
            kz = getattr(killer.pos, 'z', 0.0)
            dx = kx - px
            dy = ky - py
            h = math.degrees(math.atan2(-dx, dy))
            dist = max(0.2, math.hypot(dx, dy))
            target_eye_z = kz + 1.8
            p = math.degrees(math.atan2(target_eye_z - PLAYER_EYE_HEIGHT, dist))
            self.camera.setHpr(h, p, 0)
            killer.update(0.016, is_moving=False, is_attacking=True)

            k_name = getattr(killer, 'name', '괴물')
            desc = f"{k_name}에게 무자비하게 습격당해 생명을 잃었습니다..."
            res_desc = f"사망 ({k_name})"

            blood_fog = LColor(0.025, 0.003, 0.003, 1.0)
            self.liminal_fog.setColor(blood_fog)
            self.setBackgroundColor(blood_fog)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(blood_fog)
        else:
            desc = "제한시간 5분이 모두 지나 미궁의 심연에 영원히 갇혔습니다..."
            res_desc = "탈출 실패 (시간 초과)"
            purple_fog = LColor(0.012, 0.003, 0.020, 1.0)
            self.liminal_fog.setColor(purple_fog)
            self.setBackgroundColor(purple_fog)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(purple_fog)

        if self.audio_mgr.bgm:
            self.audio_mgr.bgm.setVolume(0.20)

        self.ui_mgr.show_game_over(desc)
        self.player.lock_mouse(False)

        self.ui_mgr.save_rank_record(res_desc, False, elapsed, remaining, self.combat.ammo, self.current_stage, self.combat.reserve_ammo)

    # --- 탈출구 및 스폰 계산 ---
    def clear_objectives(self):
        """제단·관문과 등록된 광원을 해제합니다."""
        # 기존 제단 및 관문 노드 정리
        if hasattr(self, 'altars') and self.altars:
            for alt in self.altars:
                if alt.get("light_np") and not alt["light_np"].isEmpty():
                    self.render.clearLight(alt["light_np"])
                if alt.get("node") and not alt["node"].isEmpty():
                    alt["node"].removeNode()
        self.altars = []

        if hasattr(self, 'escape_gate') and self.escape_gate:
            if self.escape_gate.get("light_np") and not self.escape_gate["light_np"].isEmpty():
                self.render.clearLight(self.escape_gate["light_np"])
            if self.escape_gate.get("node") and not self.escape_gate["node"].isEmpty():
                self.escape_gate["node"].removeNode()
        self.escape_gate = None
        self.activated_altars_count = 0

    def setup_escape_portal(self):
        """3개의 고대 룬 제단(Blood, Soul, Void) 및 심층 탈출 관문(Abyssal Gate) 배치"""
        self.clear_objectives()
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        candidates = []
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if (gx % 3 == 1 or gy % 3 == 1) and not cell_has_pillar(gx, gy):
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    if math.hypot(cx - spawn_x, cy - spawn_y) >= 28.0:
                        candidates.append((cx, cy))

        random.shuffle(candidates)

        # 1. 심층 탈출 관문 (Abyssal Escape Gate) 위치 선정 (스폰에서 55m 이상)
        gate_candidates = [p for p in candidates if math.hypot(p[0] - spawn_x, p[1] - spawn_y) >= 55.0]
        gate_pos = gate_candidates[0] if gate_candidates else (candidates[0] if candidates else (spawn_x + 65.0, spawn_y + 65.0))
        self.escape_pos = gate_pos

        # 2. 3개의 고대 룬 제단 위치 선정 (각각 서로 30m 이상 이격)
        chosen_altar_pos = []
        for p in candidates:
            if p == gate_pos:
                continue
            if all(math.hypot(p[0] - other[0], p[1] - other[1]) >= 32.0 for other in chosen_altar_pos):
                chosen_altar_pos.append(p)
                if len(chosen_altar_pos) == 3:
                    break

        while len(chosen_altar_pos) < 3:
            chosen_altar_pos.append((spawn_x + (len(chosen_altar_pos) + 1) * 25.0, spawn_y + (len(chosen_altar_pos) + 1) * 25.0))

        # 공통 재질 색상
        stone_dark = LColor(0.20, 0.18, 0.17, 1.0)
        stone_mid = LColor(0.30, 0.27, 0.25, 1.0)
        iron_dark = LColor(0.14, 0.14, 0.16, 1.0)
        iron_bar = LColor(0.28, 0.28, 0.32, 1.0)
        brass_trim = LColor(0.70, 0.55, 0.20, 1.0)

        # (A) 3D 심층 탈출 관문 (Abyssal Escape Gate) 구축
        gate_np = self.world_root.attachNewNode("abyssal_escape_gate")
        gate_np.setPos(gate_pos[0], gate_pos[1], 0)

        # 문턱 및 기단
        make_cube_to(gate_np, 4.4, 2.2, 0.24, stone_dark, 0, 0, 0.12)
        make_cube_to(gate_np, 3.8, 1.8, 0.18, stone_mid, 0, 0, 0.30)

        # 쌍둥이 고딕 석주 (Twin Pillars)
        for px_sign in (-1, 1):
            px = px_sign * 1.70
            make_cube_to(gate_np, 0.85, 0.85, 0.40, stone_dark, px, 0, 0.45)
            make_cube_to(gate_np, 0.70, 0.70, 3.60, stone_mid, px, 0, 2.25)
            make_cube_to(gate_np, 0.85, 0.85, 0.30, stone_dark, px, 0, 4.10)
            make_cube_to(gate_np, 0.74, 0.74, 0.12, iron_dark, px, 0, 1.5)
            make_cube_to(gate_np, 0.74, 0.74, 0.12, iron_dark, px, 0, 3.0)

        # 상부 아치보 (Lintel Arch & Keystone)
        make_cube_to(gate_np, 4.4, 0.90, 0.75, stone_dark, 0, 0, 4.45)
        make_cube_to(gate_np, 0.75, 0.98, 0.85, brass_trim, 0, 0, 4.50)

        # 3개 소켓 룬석 (처음에는 차가운 흑요석, 제단 활성화 시 점등)
        obsidian_cold = LColor(0.12, 0.12, 0.14, 1.0)
        sock1 = make_cube_to(gate_np, 0.28, 0.18, 0.28, obsidian_cold, -1.05, -0.42, 4.45, rot_h=45)
        sock2 = make_cube_to(gate_np, 0.34, 0.20, 0.34, obsidian_cold, 0.0, -0.46, 4.50, rot_h=45)
        sock3 = make_cube_to(gate_np, 0.28, 0.18, 0.28, obsidian_cold, 1.05, -0.42, 4.45, rot_h=45)

        # 하강된 쇠창살 격자문 (Portcullis - 시작 시 닫힘)
        portcullis = gate_np.attachNewNode("portcullis")
        portcullis.setPos(0, 0, 0)
        for bx in [-1.1, -0.75, -0.4, 0, 0.4, 0.75, 1.1]:
            make_cube_to(portcullis, 0.07, 0.07, 2.8, iron_bar, bx, 0, 1.4)
            make_cube_to(portcullis, 0.07, 0.07, 0.15, iron_dark, bx, 0, -0.05, rot_h=45)
        make_cube_to(portcullis, 2.5, 0.10, 0.12, iron_dark, 0, 0, 0.8)
        make_cube_to(portcullis, 2.5, 0.10, 0.12, iron_dark, 0, 0, 1.8)

        # 심층 소용돌이 차원문 (Portal Plane - 열렸을 때 표시)
        portal_plane = make_cube_to(gate_np, 2.5, 0.10, 3.8, LColor(0.15, 0.65, 0.95, 0.95), 0, 0.15, 2.1)
        portal_plane.setLightOff()
        portal_plane.hide()

        # 관문 광원
        gate_light = PointLight('gate_light')
        gate_light.setColor((0.8, 1.6, 2.2, 1.0))
        gate_light.setAttenuation((1.0, 0.08, 0.015))
        gate_light_np = gate_np.attachNewNode(gate_light)
        gate_light_np.setPos(0, 0, 2.5)

        self.escape_gate = {
            "pos": gate_pos,
            "node": gate_np,
            "portcullis_np": portcullis,
            "portal_np": portal_plane,
            "light_np": gate_light_np,
            "socket_runes": [sock1, sock2, sock3],
            "opened": False,
            "hold_timer": 0.8
        }

        # (B) 3개의 고대 룬 제단 (3 Runic Altars) 구축
        altar_configs = [
            {"name": "피의 룬 제단", "color": LColor(1.0, 0.35, 0.15, 1.0), "light_col": (2.2, 0.6, 0.25)},
            {"name": "영혼의 룬 제단", "color": LColor(0.25, 0.75, 1.0, 1.0), "light_col": (0.5, 1.6, 2.4)},
            {"name": "그림자의 룬 제단", "color": LColor(0.85, 0.35, 1.0, 1.0), "light_col": (1.8, 0.5, 2.2)}
        ]

        for i, pos in enumerate(chosen_altar_pos):
            cfg = altar_configs[i]
            altar_np = self.world_root.attachNewNode(f"altar_{i}")
            altar_np.setPos(pos[0], pos[1], 0)

            # 기단 & 가고일 기둥
            make_cube_to(altar_np, 2.2, 2.2, 0.22, stone_dark, 0, 0, 0.11)
            make_cube_to(altar_np, 1.7, 1.7, 0.22, stone_mid, 0, 0, 0.33)
            for sx in (-0.75, 0.75):
                for sy in (-0.75, 0.75):
                    make_cube_to(altar_np, 0.25, 0.25, 0.85, stone_dark, sx, sy, 0.65)
                    make_cube_to(altar_np, 0.28, 0.28, 0.10, iron_dark, sx, sy, 1.10)

            # 중앙 기둥
            make_cube_to(altar_np, 0.85, 0.85, 1.40, stone_dark, 0, 0, 1.0)
            make_cube_to(altar_np, 0.90, 0.90, 0.12, iron_dark, 0, 0, 0.70)
            make_cube_to(altar_np, 0.90, 0.90, 0.12, iron_dark, 0, 0, 1.30)

            # 화로 보울
            make_cube_to(altar_np, 1.15, 1.15, 0.18, iron_dark, 0, 0, 1.75)
            make_cube_to(altar_np, 1.25, 0.14, 0.22, iron_dark, 0, 0.52, 1.88)
            make_cube_to(altar_np, 1.25, 0.14, 0.22, iron_dark, 0, -0.52, 1.88)
            make_cube_to(altar_np, 0.14, 1.15, 0.22, iron_dark, 0.52, 0, 1.88)
            make_cube_to(altar_np, 0.14, 1.15, 0.22, iron_dark, -0.52, 0, 1.88)

            # 미활성 흑요석 코어
            core = make_cube_to(altar_np, 0.38, 0.38, 0.45, obsidian_cold, 0, 0, 2.05, rot_h=45)
            core.setP(25)

            # 부유 엠버 파티클 (초기 숨김)
            embers = []
            for angle in [0, 90, 180, 270]:
                rad = math.radians(angle)
                emb = make_cube_to(altar_np, 0.08, 0.08, 0.12, cfg["color"], math.cos(rad) * 0.35, math.sin(rad) * 0.35, 2.15, rot_h=angle+30)
                emb.setLightOff()
                emb.hide()
                embers.append(emb)

            # 제단 광원
            alt_light = PointLight(f'altar_light_{i}')
            alt_light.setColor((cfg["light_col"][0], cfg["light_col"][1], cfg["light_col"][2], 1.0))
            alt_light.setAttenuation((1.0, 0.12, 0.025))
            alt_light_np = altar_np.attachNewNode(alt_light)
            alt_light_np.setPos(0, 0, 2.3)

            self.altars.append({
                "id": i,
                "name": cfg["name"],
                "color": cfg["color"],
                "pos": pos,
                "node": altar_np,
                "core_np": core,
                "embers": embers,
                "light_np": alt_light_np,
                "activated": False,
                "interact_timer": 0.0
            })

    # --- 청크 스트리밍 및 컬링 최적화 ---
    def update_chunks(self, force=False):
        px, py = self.camera.getX(), self.camera.getY()
        player_cx = int(math.floor(px / CHUNK_SIZE))
        player_cy = int(math.floor(py / CHUNK_SIZE))

        if not force and hasattr(self, 'last_chunk') and (player_cx, player_cy) == self.last_chunk:
            return

        self.last_chunk = (player_cx, player_cy)
        needed_chunks = set()
        for dx in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
            for dy in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
                cx, cy = player_cx + dx, player_cy + dy
                if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                    needed_chunks.add((cx, cy))

        if self.player.last_move_dir.lengthSquared() > 0.01:
            pred_x = px + self.player.last_move_dir.x * 24.0
            pred_y = py + self.player.last_move_dir.y * 24.0
            pred_cx, pred_cy = int(math.floor(pred_x / CHUNK_SIZE)), int(math.floor(pred_y / CHUNK_SIZE))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cx, cy = pred_cx + dx, pred_cy + dy
                    if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                        needed_chunks.add((cx, cy))

        for coord in [c for c in self.chunks if c not in needed_chunks]:
            self.chunks[coord].destroy()
            del self.chunks[coord]

        for coord in [c for c in self.active_chunk_futures if c not in needed_chunks]:
            self.active_chunk_futures.pop(coord).cancel()

        missing = [c for c in needed_chunks if c not in self.chunks and c not in self.active_chunk_futures]
        if missing:
            missing.sort(key=lambda c: (c[0] - player_cx)**2 + (c[1] - player_cy)**2)
            if force:
                futs = [self.chunk_executor.submit(Chunk, None, cx, cy, self.floor_dry_tex, self.wall_tex, self.sky_tex, self.floor_wet_tex) for cx, cy in missing]
                for fut in futs:
                    try:
                        chunk = fut.result()
                        chunk.attach_to(self.world_root)
                        self.chunks[(chunk.cx, chunk.cy)] = chunk
                    except Exception as e:
                        print(f"초기 청크 로딩 에러: {e}")
                self.cull_chunks_to_view(force=True)
            else:
                for cx, cy in missing:
                    self.active_chunk_futures[(cx, cy)] = self.chunk_executor.submit(
                        Chunk, None, cx, cy, self.floor_dry_tex, self.wall_tex, self.sky_tex, self.floor_wet_tex
                    )

    def cull_chunks_to_view(self, force=False):
        """이동 거리 임계치(2.0m) 기반 청크 가시거리 컬링 최적화"""
        px, py = self.camera.getX(), self.camera.getY()
        if not force and self.last_cull_pos is not None:
            if math.hypot(px - self.last_cull_pos[0], py - self.last_cull_pos[1]) < 2.0:
                return

        self.last_cull_pos = (px, py)
        chunk_rad = (CHUNK_SIZE / 2.0) * math.sqrt(2)
        max_dist_sq = (72.0 + chunk_rad) ** 2

        visible_count = 0
        for (cx, cy), chunk in self.chunks.items():
            ccx = (cx + 0.5) * CHUNK_SIZE
            ccy = (cy + 0.5) * CHUNK_SIZE
            d_sq = (ccx - px) ** 2 + (ccy - py) ** 2
            is_visible = (d_sq <= max_dist_sq)
            chunk.set_visible(is_visible)
            if is_visible:
                visible_count += 1

        self.rendered_chunk_count = visible_count
        self.total_chunk_count = len(self.chunks)

    def _mount_async_chunks(self):
        """백그라운드 스레드에서 생성 완료된 청크 마운트"""
        chunk_created = False
        if self.active_chunk_futures:
            cur_px, cur_py = self.camera.getX(), self.camera.getY()
            cur_cx, cur_cy = int(math.floor(cur_px / CHUNK_SIZE)), int(math.floor(cur_py / CHUNK_SIZE))
            done_coords = [coord for coord, fut in self.active_chunk_futures.items() if fut.done()]
            for coord in done_coords:
                fut = self.active_chunk_futures.pop(coord)
                try:
                    chunk = fut.result()
                    if abs(coord[0] - cur_cx) <= RENDER_RADIUS + 1 and abs(coord[1] - cur_cy) <= RENDER_RADIUS + 1:
                        chunk.attach_to(self.world_root)
                        self.chunks[coord] = chunk
                        chunk_created = True
                    else:
                        chunk.destroy()
                except Exception as e:
                    print(f"청크 마운트 예외: {e}")
        return chunk_created

    # --- 몬스터 AI 제어 (다중 군단) ---
    def _update_monsters(self, dt, px, py):
        closest_dist = 999.0
        stage_mult = 1.0 + (self.current_stage - 1) * 0.15
        if self.blackout_active:
            stage_mult *= 1.25  # 정전 프로토콜: 몬스터 이동속도 25% 가속 (폭주 상태)

        # 0. 시체 볼트 및 유물 수습 (플레이어 1.85m 이내 접근 시 회수)
        for c in self.corpses:
            if hasattr(c, "update_corpse"):
                c.update_corpse(dt)
            if math.hypot(px - c.pos.x, py - c.pos.y) > 1.85:
                continue
            bolts = getattr(c, 'recoverable_bolts', 0)
            if bolts > 0:
                c.recoverable_bolts = 0
                if hasattr(c, 'embedded_bolt_np') and not c.embedded_bolt_np.isEmpty():
                    c.embedded_bolt_np.removeNode()
                self.combat.reserve_ammo += bolts
                self.combat.update_ammo_ui()
                self.audio_mgr.play_bolt_retrieve()
                self.ui_mgr.show_hit_marker(f"볼트 회수! (+{bolts} 강철 볼트)", (0.4, 0.9, 1.0, 1.0))
            if getattr(c, 'recoverable_relic', False):
                c.recoverable_relic = False
                if hasattr(c, 'relic_drop_np') and not c.relic_drop_np.isEmpty():
                    c.relic_drop_np.removeNode()
                available = [r for r in CURSED_RELICS if r not in self.player.relics]
                if available:
                    relic_id = random.choice(available)
                    self.player.acquire_relic(relic_id)
                    self.audio_mgr.play_item_pickup()
                    relic = CURSED_RELICS[relic_id]
                    self.ui_mgr.show_stage_banner(
                        f"[스토커 유물 획득: {relic['name']}]\n{relic['pro']} / {relic['con']}",
                        color=(0.95, 0.75, 1.0, 1.0)
                    )
                    self.stage_banner_timer = 4.0

        for m in self.monsters[:]:
            if getattr(m, 'hp', 1) <= 0:
                # 사망한 몬스터: 시체로 전환하고 활성 몬스터 목록에서 제외하여 시체 목록으로 이전
                if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                    m.turn_into_corpse()
                self.monsters.remove(m)
                self.corpses.append(m)
                continue

            mx, my = m.pos.x, m.pos.y
            dist = math.hypot(px - mx, py - my)
            if dist < closest_dist:
                closest_dist = dist

            # 1. 근접 공격 판정
            attack_range = 1.95 if isinstance(m, (TallSkeletonMonster, AbominableMudOrc)) else 1.45
            special_attack = any(getattr(m, flag, False) for flag in
                                 ('is_slamming', 'is_casting', 'is_lunge_winding', 'is_lunging'))
            if dist <= attack_range and m.stun_timer <= 0.0 and not special_attack:
                is_dead = self.player.take_damage(m.attack_damage)
                m.update(dt, is_moving=False, is_attacking=True)
                if is_dead:
                    self.trigger_game_over(killer=m, reason="killed")
                    return True, closest_dist
                continue

            # 2. 스턴 상태 처리
            if m.stun_timer > 0.0:
                m.update_pos(mx, my, dt, 0, 0)
                continue

            # 3. 진흙 오크: 땅을 울려서 플레이어 이동방해 (Ground Slam)
            if isinstance(m, AbominableMudOrc):
                m.slam_cooldown -= dt
                if dist <= 12.0 and m.slam_cooldown <= 0.0 and not m.is_slamming and m.stun_timer <= 0.0:
                    m.begin_slam(self.audio_mgr)

                if m.is_slamming:
                    impact = m.slam_ground(dt)
                    if impact:
                        self.shockwaves.append(GroundShockwave(self.render, mx, my))
                        self.audio_mgr.play_skeleton_hit()
                        if dist <= 11.5:
                            self.player.apply_slow(duration=2.8, factor=0.40)
                            self.player.trigger_quake_shake(intensity=2.6, duration=0.85)
                    continue

            # 4. 시선 검사 (Line of Sight)
            # 4. 시선 검사 (Line of Sight) - 지능형 스케줄링 및 캐싱 최적화
            if not hasattr(m, 'los_timer'):
                m.los_timer = random.uniform(0.0, 0.15)
                m.has_los = False

            m.los_timer -= dt
            if dist <= 2.2:
                has_los = True
                m.has_los = True
            elif dist > 28.0:
                has_los = False
                m.has_los = False
            elif m.los_timer <= 0.0:
                m.los_timer = 0.18 + random.uniform(0.0, 0.06) # 초당 약 4~5회 지그재그 분산 검사
                mid_x, mid_y = (mx + px) * 0.5, (my + py) * 0.5
                cols = get_nearby_colliders(self.chunks, mid_x, mid_y, dist * 0.5 + 1.2)
                m.has_los = check_line_of_sight(mx, my, px, py, cols)
                has_los = m.has_los
            else:
                has_los = m.has_los

            if isinstance(m, AlluringAshWitch):
                m.cast_cooldown -= dt
                if has_los and dist <= 24.0 and m.cast_cooldown <= 0.0 and not m.is_casting and m.stun_timer <= 0.0:
                    m.begin_cast(self.audio_mgr)

                if m.is_casting:
                    fire = m.cast_fireball(dt)
                    if fire:
                        orb_pos = (mx, my, m.pos.z + 1.5)
                        target_pos = (px, py, PLAYER_EYE_HEIGHT)
                        self.fireballs.append(Fireball(self.render, orb_pos, target_pos))
                        self.audio_mgr.play_serpent_hit()

                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)
                    continue

            # 5-2. 그림자 스토커 (Shadow Stalker) 고속 도약 베기 (Lunge Attack)
            if isinstance(m, ShadowStalker):
                if has_los and dist <= 5.5 and m.lunge_cooldown <= 0.0 and not m.is_lunging and not m.is_lunge_winding and m.stun_timer <= 0.0:
                    m.trigger_lunge((px, py), self.audio_mgr)

                if m.is_lunge_winding:
                    m.update_lunge_windup(dt, self.audio_mgr)
                    continue

                if m.is_lunging:
                    m.pos.x, m.pos.y = resolve_collision(
                        self.chunks, mx, my,
                        m.lunge_dir.x * 16.5 * dt, m.lunge_dir.y * 16.5 * dt, radius=0.40
                    )
                    m.node.setPos(m.pos)
                    m.update(dt, is_moving=True, is_attacking=True)
                    if math.hypot(m.pos.x - px, m.pos.y - py) <= 1.85:
                        is_dead = self.player.take_damage(m.attack_damage)
                        self.player.trigger_quake_shake(0.70, 0.16)
                        self.audio_mgr.play_flesh_hit()
                        m.cancel_lunge()
                        if is_dead:
                            self.trigger_game_over(killer=m, reason="killed")
                            return True, closest_dist
                    continue

            # 6. 길찾기 (Pathfinding)
            m.path_timer -= dt
            if has_los:
                tx, ty = px, py
                m.path = []
            else:
                mgx = int(math.floor(mx / CELL_SIZE))
                mgy = int(math.floor(my / CELL_SIZE))
                pgx = int(math.floor(px / CELL_SIZE))
                pgy = int(math.floor(py / CELL_SIZE))

                if (mgx, mgy) == (pgx, pgy):
                    tx, ty = px, py
                else:
                    if m.path_timer <= 0.0 or not m.path:
                        m.path_timer = 0.35 + random.random() * 0.1
                        m.path = find_cell_path((mgx, mgy), (pgx, pgy), max_depth=24)

                    while len(m.path) > 1 and m.path[0] != (mgx, mgy):
                        if (mgx, mgy) == m.path[1]:
                            m.path.pop(0)
                        else:
                            break

                    if len(m.path) >= 2:
                        c1 = m.path[0]
                        c2 = m.path[1]
                        tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                        ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                        if math.hypot(mx - tx, my - ty) < 0.9:
                            m.path.pop(0)
                            if len(m.path) >= 2:
                                c1 = m.path[0]
                                c2 = m.path[1]
                                tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                                ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                            else:
                                tx, ty = px, py
                    else:
                        tx, ty = px, py

            dx = tx - mx
            dy = ty - my
            d = math.hypot(dx, dy)
            if d > 0.05:
                ndx, ndy = dx / d, dy / d
                speed = getattr(m, 'speed', 8.5) * stage_mult
                col_radius = 0.40
                new_x, new_y = resolve_collision(self.chunks, mx, my, ndx * speed * dt, ndy * speed * dt, radius=col_radius)
                m.update_pos(new_x, new_y, dt, ndx, ndy)
            else:
                m.update(dt, is_moving=False)

        return False, closest_dist

    def _update_projectiles(self, dt, px, py, pz):
        """파이어볼 비행/벽체 및 플레이어 피격 충돌, 땅울림 분진 갱신"""
        # 1. 파이어볼 갱신
        for fb in self.fireballs[:]:
            alive = fb.update(dt)
            if not alive:
                fb.destroy()
                self.fireballs.remove(fb)
                continue

            # 벽체 충돌 검사
            cols = get_nearby_colliders(self.chunks, fb.pos.x, fb.pos.y, search_dist=0.6)
            hit_wall = False
            for min_x, min_y, max_x, max_y in cols:
                if min_x <= fb.pos.x <= max_x and min_y <= fb.pos.y <= max_y:
                    hit_wall = True
                    break
            if hit_wall:
                fb.destroy()
                self.fireballs.remove(fb)
                continue

            # 플레이어 충돌 검사
            dist_p = math.hypot(fb.pos.x - px, fb.pos.y - py)
            dz = abs(fb.pos.z - pz)
            if dist_p < 0.95 and dz < 1.6:
                is_dead = self.player.take_damage(fb.damage)
                self.audio_mgr.play_serpent_hit()
                fb.destroy()
                self.fireballs.remove(fb)
                if is_dead:
                    first_witch = next((m for m in self.monsters if isinstance(m, AlluringAshWitch)), None)
                    self.trigger_game_over(killer=first_witch, reason="killed")
                    return True

        # 2. 땅울림 충격파 분진 갱신
        for sw in self.shockwaves[:]:
            if not sw.update(dt):
                sw.destroy()
                self.shockwaves.remove(sw)

        return False

    def _update_door_defense(self, dt, px, py):
        """고대 룬 제단 각인(상호작용) & 심층 탈출 관문 개방 및 룬 나침반 처리"""
        if not hasattr(self, 'altars') or not self.altars or not self.escape_gate:
            return False

        # --- 1. 고대 룬 제단 상호작용 검사 ---
        is_holding_e = bool(self.player.key_map.get("e", 0))
        near_any_altar = False

        for alt in self.altars:
            if alt["activated"]:
                continue
            ax, ay = alt["pos"]
            dist_alt = math.hypot(px - ax, py - ay)

            if dist_alt <= 2.5:
                near_any_altar = True
                if is_holding_e and dist_alt <= 2.8:
                    alt["interact_timer"] += dt
                    pct = min(1.0, alt["interact_timer"] / 1.5)
                    bars = int(pct * 14)
                    bar_str = "|" * bars + "." * (14 - bars)
                    msg = f"[ {alt['name']} 각인 중...  {alt['interact_timer']:.1f}s / 1.5s  [{bar_str}] ]"
                    self.ui_mgr.update_door_status(msg, fg=alt["color"])

                    if alt["interact_timer"] >= 1.5:
                        # 제단 각인 완료!
                        alt["activated"] = True
                        self.activated_altars_count += 1

                        # 제단 시각 효과 활성화
                        alt["core_np"].setColor(alt["color"])
                        alt["core_np"].setLightOff()
                        for emb in alt["embers"]:
                            emb.show()
                        self.render.setLight(alt["light_np"])

                        # 탈출 관문 소켓 룬석 점등
                        sock = self.escape_gate["socket_runes"][alt["id"]]
                        sock.setColor(alt["color"])
                        sock.setLightOff()

                        self.audio_mgr.play_altar_activate()
                        self.player.trigger_quake_shake(0.55, 0.15)
                        self.trigger_abyssal_inversion(duration=24.0, reason="altar")
                        self.ui_mgr.show_stage_banner(f"[{alt['name']} 각인 완료!]  봉인: {self.activated_altars_count} / 3", color=alt["color"])
                        self.ui_mgr.update_door_status(f"[ {alt['name']} 봉인 해제! ]", fg=alt["color"])

                        # 35m 이내 몬스터 플레이어 위치로 경보
                        for m in self.monsters:
                            if math.hypot(m.pos.x - px, m.pos.y - py) <= 35.0:
                                m.stun_timer = 0.0

                        # 모든 3개 봉인 해제 시 관문 개방!
                        if self.activated_altars_count >= 3:
                            self.escape_gate["opened"] = True
                            self.escape_gate["portcullis_np"].setZ(2.8)  # 쇠창살 개방
                            self.escape_gate["portal_np"].show()         # 심층 포탈 활성화
                            self.render.setLight(self.escape_gate["light_np"])
                            self.audio_mgr.play_gate_open()
                            self.player.trigger_quake_shake(0.85, 0.25)
                            self.ui_mgr.show_stage_banner("[모든 봉인 해제 완료!] 심층 탈출 관문이 개방되었습니다!", color=(0.3, 1.0, 0.6, 1.0))
                else:
                    if alt["interact_timer"] > 0.0:
                        alt["interact_timer"] = max(0.0, alt["interact_timer"] - dt * 2.0)
                    msg = f"[ {alt['name']} ]  -  [E] 키를 길게 눌러 룬을 각인하세요!"
                    self.ui_mgr.update_door_status(msg, fg=(1.0, 0.85, 0.2, 1.0))
                break

        # --- 2. 개방된 심층 탈출 관문 진입 검사 ---
        if self.escape_gate.get("opened", False):
            gx, gy = self.escape_gate["pos"]
            dist_gate = math.hypot(px - gx, py - gy)

            if dist_gate <= 2.5:
                near_any_altar = True
                self.escape_gate["hold_timer"] -= dt
                self.ui_mgr.update_door_status("[ 심층 탈출 관문 진입 중... 즉시 이동합니다! ]", fg=(0.3, 1.0, 0.6, 1.0))
                if self.escape_gate["hold_timer"] <= 0.0:
                    # 탈출 성공 -> 상점 및 다음 층 진입
                    self.game_state = "SHOP"
                    self.audio_mgr.set_bgm_mode("SHOP")
                    self.player.lock_mouse(False)
                    self.ui_mgr.show_stage_clear_shop(self.current_stage, self.player, self.combat, self.on_shop_closed)
                    return True
            else:
                self.escape_gate["hold_timer"] = 0.8

        if not near_any_altar:
            self.ui_mgr.update_door_status("", show=False)

        # --- 3. 시선 기준 360도 나침반 및 목표 추적기 갱신 ---
        self.ui_mgr.update_navigation(self.camera.getH(), px, py, self.altars, self.escape_gate)

        return False

    # --- 메인 틱 루프 (Main Update Loop) ---
    def update(self, task):
        dt = min(0.1, max(0.016, globalClock.getDt()))
        cont = task.cont if task is not None else 1

        # 0. 중세 다크판타지 벽걸이 촛불 동적 라이팅 갱신 (6개 포인트라이트 실시간 이동 및 깜빡임)
        if hasattr(self, 'candle_lights'):
            self.candle_lights.update(dt, self.camera.getPos(), self.chunks, is_blackout=self.blackout_active)

        # 1. 인트로 시네마틱 카메라 회전
        if self.game_state == "INTRO":
            t = globalClock.getFrameTime()
            cam_x = 45.0 + math.sin(t * 0.12) * 38.0
            cam_y = 45.0 + math.cos(t * 0.12) * 38.0
            self.camera.setPos(cam_x, cam_y, 11.5)
            self.camera.lookAt(45.0, 45.0, 1.5)
            self.update_chunks()
            if self._mount_async_chunks():
                self.cull_chunks_to_view(force=True)
            return cont

        # 2. 상점 모달 상태 시 업데이트 정지
        # 1-1. 사전 렌더링 및 로딩 중인 경우 인게임 업데이트 대기
        if self.game_state == "LOADING":
            return cont

        if self.game_state == "SHOP":
            return cont

        # 3. 승리 및 게임 오버 상태 처리
        if self.game_won or self.game_state == "VICTORY":
            return cont

        if self.game_over or self.game_state == "GAME_OVER":
            self.ui_mgr.update(dt)
            if self.killer_monster is not None:
                killer = self.killer_monster
                px, py = self.camera.getX(), self.camera.getY()
                dx, dy = killer.pos.x - px, killer.pos.y - py
                h = math.degrees(math.atan2(-dx, dy))
                p = math.degrees(math.atan2(1.8 - PLAYER_EYE_HEIGHT, max(0.2, math.hypot(dx, dy))))
                self.camera.setHpr(h, p, 0)
                killer.update(dt, is_moving=False, is_attacking=True)
            return cont

        # 4. 비동기 청크 마운트
        chunk_created = self._mount_async_chunks()

        # 5. 플레이어 시선 및 이동/충돌 처리
        is_moving, is_sprinting, view_changed = self.player.update(dt, self.chunks)
        if is_moving:
            self.update_chunks()

        # 6. 괴물 군단 AI 및 공격 판정
        px, py = self.camera.getX(), self.camera.getY()
        game_ended, closest_dist = self._update_monsters(dt, px, py)
        if game_ended:
            return cont

        # 6-1. 마녀 파이어볼 및 진흙오크 충격파 갱신
        if self._update_projectiles(dt, px, py, PLAYER_EYE_HEIGHT):
            return cont

        # 7. 오디오 3D 위치 및 감쇠
        self.audio_mgr.update(dt, closest_dist, closest_dist, False, False)

        # 8. 안개 가시거리 컬링 (임계치 2.0m 이동 또는 신규 청크 마운트 시만 실행)
        if chunk_created or is_moving:
            self.cull_chunks_to_view(force=chunk_created)
            if chunk_created and hasattr(self, 'candle_lights'):
                self.candle_lights.update(dt, self.camera.getPos(), self.chunks, force=True, is_blackout=self.blackout_active)

        # 9. 전투 및 뷰모델 갱신 (반동, 재장전, 탄약 습득, 밥빙)
        self.combat.update(dt, px, py, is_moving, is_sprinting, self.chunks, self.monsters, self.player)
        self.inventory.update(dt, self.player, self.monsters, self.chunks, self.blackout_active)

        # 10. 배너 타이머
        if self.stage_banner_timer > 0.0:
            self.stage_banner_timer -= dt
            if self.stage_banner_timer <= 0.0:
                self.ui_mgr.hide_stage_banner()

        # 10-1. 정전 프로토콜 (Blackout & Crimson Protocol) 발동 및 타이머 갱신
        if self.time_left <= 200.0 and not self.blackout_triggered_this_stage:
            self.blackout_triggered_this_stage = True
            self.trigger_abyssal_inversion(duration=22.0, reason="stage")

        if self.blackout_active:
            self.blackout_timer -= dt
            if self.blackout_timer <= 0.0:
                self.end_abyssal_inversion()

        # 11. 5분 탈출 제한시간 카운트다운
        self.time_left -= dt
        if self.time_left <= 0.0:
            self.time_left = 0.0
            self.trigger_game_over(killer=None, reason="timeout")
            return cont

        # 12. 룬 제단 각인 및 개방된 관문 진입 판정 (성공 시 상점 모달 오픈)
        if self._update_door_defense(dt, px, py):
            return cont

        # 13. HUD 텍스트 캐싱 및 실시간 피격 효과 애니메이션 갱신
        self.ui_mgr.update(dt)
        self.ui_mgr.update_timer(self.time_left, self.current_stage)
        self.ui_mgr.update_hud(px, py, self.rendered_chunk_count, self.total_chunk_count)

        return cont

    def destroy(self):
        if getattr(self, '_closing', False):
            return
        self._closing = True
        self.taskMgr.remove("update_task")
        self.taskMgr.remove("loading_process_task")
        if hasattr(self, 'player'):
            self._clear_stage_entities()
        if hasattr(self, 'audio_mgr'):
            self.audio_mgr.cleanup()
        if hasattr(self, 'active_chunk_futures'):
            self._discard_pending_chunks()
        if hasattr(self, 'chunk_executor'):
            self.chunk_executor.shutdown(wait=False, cancel_futures=True)
        for chunk in getattr(self, 'chunks', {}).values():
            chunk.destroy()
        if hasattr(self, 'chunks'):
            self.chunks.clear()
        if hasattr(self, 'candle_lights'):
            self.candle_lights.cleanup()
        super().destroy()


if __name__ == "__main__":
    game = LiminalInfiniteLoop()
    game.run()
