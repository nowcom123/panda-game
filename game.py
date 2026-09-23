import os
import sys
import math
import random
import concurrent.futures
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Vec3, SamplerState, Fog, AmbientLight, PointLight, LColor
)
import simplepbr

from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS, WALL_HEIGHT,
    PLAYER_EYE_HEIGHT, RENDER_RADIUS, FOG_COLOR, BLACKOUT_FOG_COLOR,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import find_cell_path, check_line_of_sight, cell_has_pillar
from chunk import Chunk
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch
)
from geometry import make_cube_to, make_cube

# 분리된 모듈 임포트
from collision import get_nearby_colliders, resolve_collision
from audio_system import AudioManager
from ui_manager import UIManager
from combat_system import CombatSystem
from player_controller import PlayerController


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
            on_reload=self.reload_pistol
        )

        # 7. 게임 상태 및 5분(300초) 타이머 설정
        self.game_state = "INTRO"  # "INTRO", "PLAYING", "SHOP", "GAME_OVER", "VICTORY"
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 던전 크롤러 모드: 5분(300초)
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
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
        amb.setColor((0.005, 0.005, 0.006, 1.0))
        self.amb_np = self.render.attachNewNode(amb)
        self.render.setLight(self.amb_np)

    def load_assets(self):
        try:
            self.wall_tex = self.loader.loadTexture("wall.jpg")
            self.floor_tex = self.loader.loadTexture("floor.jpg")
            self.sky_tex = self.loader.loadTexture("sky.jpg")
            for t in (self.wall_tex, self.floor_tex, self.sky_tex):
                if t:
                    t.setMagfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setAnisotropicDegree(4)
        except Exception as e:
            print(f"텍스처 로드 실패: {e}")

    # --- 사용자 액션 포워딩 ---
    def shoot_pistol(self):
        self.combat.shoot(self.monsters, self.player, self.game_state)

    def reload_pistol(self):
        self.combat.reload(self.game_state)

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
    def show_intro_scene(self):
        """인트로 화면 전환"""
        self.clear_projectiles()
        for m in self.monsters:
            m.destroy()
        self.monsters = []
        for c in self.corpses:
            c.destroy()
        self.corpses = []
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
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.render.clearLight(self.combat.pl_np)
        self.render.clearLight(self.combat.fill_np)
        self.ui_mgr.show_intro()
        self.audio_mgr.set_bgm_mode("INTRO")

    def start_game(self):
        """START 버튼 클릭 시 1인칭 던전 크롤러 게임플레이 시작"""
        self.game_state = "PLAYING"
        self.restart_game()
        self.combat.vm_root.show()
        if hasattr(self.combat, 'mist_root') and self.combat.mist_root:
            self.combat.mist_root.show()
        self.render.setLight(self.combat.pl_np)
        self.render.setLight(self.combat.fill_np)
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)
        self.audio_mgr.set_bgm_mode("PLAYING")

    def return_to_intro(self):
        self.show_intro_scene()

    def spawn_monsters(self, stage=1):
        """스테이지별 다중 몬스터 군단 스폰 (진흙 오크, 잿더미 마녀, 칠흑 뱀, 거대 해골)"""
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

        # 몬스터 조합 산출: 오크, 마녀를 기본 다수 배치하고 뱀과 해골을 섞음
        spawn_plan = [
            AbominableMudOrc, AbominableMudOrc,
            AlluringAshWitch, AlluringAshWitch,
            LongBlackSerpent, TallSkeletonMonster
        ]
        # 스테이지가 올라갈수록 오크와 마녀 추가 스폰
        for _ in range(stage - 1):
            spawn_plan.append(AbominableMudOrc)
            spawn_plan.append(AlluringAshWitch)

        for i, cls in enumerate(spawn_plan):
            pos = candidates[i % len(candidates)] if candidates else (spawn_x + 30.0 + i * 10, spawn_y + 30.0)
            monster = cls(self.render, pos[0], pos[1])
            self.monsters.append(monster)

        # 오디오 관리자에 첫 번째 뱀/해골 부착
        first_serpent = next((m for m in self.monsters if isinstance(m, LongBlackSerpent)), None)
        first_skel = next((m for m in self.monsters if isinstance(m, TallSkeletonMonster)), None)
        if first_serpent and first_skel:
            self.audio_mgr.attach_monsters(first_serpent, first_skel)

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
        self.player.reset_position(spawn_x, spawn_y)
        self.player.level = 1
        self.player.exp = 0
        self.player.exp_to_next = 100
        self.player.max_hp = 100.0
        self.player.hp = self.player.max_hp
        self.player.attack_power = 35.0
        self.player.speed_mult = 1.0
        self.player.relics = []
        self.ui_mgr.update_relic_badges(self.player.relics)

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        # 전투 서브시스템 리셋
        self.combat.reset_state(self.current_stage, keep_ammo=False)

        # 비동기 작업 정리
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
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
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        self.killer_monster = None

        # 다중 몬스터 군단 재배치
        self.spawn_monsters(self.current_stage)

        # 새 탈출구
        self.setup_escape_portal()

        # 전투 서브시스템: 탄약 보급
        self.combat.ammo = self.combat.max_ammo
        self.combat.reserve_ammo += 24
        self.combat.reset_state(self.current_stage, keep_ammo=True)

        # 안개 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)

        # 배너 알림
        self.ui_mgr.show_stage_banner(f"[ STAGE {self.current_stage} START! ]\n던전 심연 진입: 몬스터 증가 & 탄약 완충!")
        self.stage_banner_timer = 3.0

    def on_shop_closed(self):
        """스탯 분배 및 상점 완료 후 다음 스테이지 진입"""
        self.advance_to_next_stage()
        self.game_state = "PLAYING"
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)

    def trigger_victory(self):
        """탈출구 방어 성공 시 승리"""
        if self.game_over or self.game_won:
            return
        self.game_won = True
        self.game_state = "VICTORY"

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
    def setup_escape_portal(self):
        """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성"""
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
                    if math.hypot(cx - spawn_x, cy - spawn_y) >= 70.0:
                        candidates.append((cx, cy))

        self.escape_pos = random.choice(candidates) if candidates else (spawn_x + 75.0, spawn_y + 75.0)

        if hasattr(self, 'escape_portal_np') and self.escape_portal_np:
            self.escape_portal_np.removeNode()

        self.escape_portal_np = self.world_root.attachNewNode("escape_portal")
        self.escape_portal_np.setPos(self.escape_pos[0], self.escape_pos[1], 0)

        dark_metal_frame = LColor(0.12, 0.12, 0.14, 1.0)
        steel_door_plate = LColor(0.24, 0.25, 0.28, 1.0)
        lock_reinforce_col = LColor(0.38, 0.39, 0.43, 1.0)
        hazard_dim_stripe = LColor(0.45, 0.38, 0.12, 1.0)

        half_w = 1.35
        for cx_sign in (-1, 1):
            for cy_sign in (-1, 1):
                make_cube_to(self.escape_portal_np, 0.30, 0.30, 3.8, dark_metal_frame, cx_sign * half_w, cy_sign * half_w, 1.9)

        make_cube_to(self.escape_portal_np, 3.0, 3.0, 0.35, dark_metal_frame, 0, 0, 3.8)

        self.door_lamps = []
        for h in (0, 90, 180, 270):
            face_np = self.escape_portal_np.attachNewNode(f"door_face_{h}")
            face_np.setH(h)

            make_cube_to(face_np, 2.70, 0.28, 0.30, dark_metal_frame, 0, half_w, 3.6)
            make_cube_to(face_np, 2.40, 0.12, 3.40, steel_door_plate, 0, half_w, 1.70)
            make_cube_to(face_np, 2.1, 0.16, 0.15, lock_reinforce_col, 0, half_w + 0.04, 1.0)
            make_cube_to(face_np, 2.1, 0.16, 0.15, lock_reinforce_col, 0, half_w + 0.04, 2.0)
            make_cube_to(face_np, 2.1, 0.16, 0.15, lock_reinforce_col, 0, half_w + 0.04, 2.9)
            make_cube_to(face_np, 0.14, 0.20, 0.40, lock_reinforce_col, 0.85, half_w + 0.06, 1.7)
            make_cube_to(face_np, 2.3, 0.14, 0.20, hazard_dim_stripe, 0, half_w + 0.03, 0.30)

            make_cube_to(face_np, 0.40, 0.16, 0.16, dark_metal_frame, 0, half_w + 0.05, 3.9)
            lamp = make_cube_to(face_np, 0.28, 0.08, 0.10, LColor(0.35, 0.25, 0.08, 1.0), 0, half_w + 0.08, 3.9)
            lamp.setLightOff()
            self.door_lamps.append(lamp)

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
                futs = [self.chunk_executor.submit(Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex) for cx, cy in missing]
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
                        Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex
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
            if dist <= attack_range and m.stun_timer <= 0.0:
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
                    m.is_slamming = True
                    m.slam_timer = 0.0
                    m.slam_has_impacted = False
                    m.slam_cooldown = 5.5

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
            has_los = False
            if dist <= 28.0:
                mid_x, mid_y = (mx + px) * 0.5, (my + py) * 0.5
                cols = get_nearby_colliders(self.chunks, mid_x, mid_y, dist * 0.5 + 1.2)
                has_los = check_line_of_sight(mx, my, px, py, cols)

            # 5. 잿더미 마녀: 파이어볼 투척 (Fireball Cast)
            if isinstance(m, AlluringAshWitch):
                m.cast_cooldown -= dt
                if has_los and dist <= 24.0 and m.cast_cooldown <= 0.0 and not m.is_casting and m.stun_timer <= 0.0:
                    m.is_casting = True
                    m.cast_timer = 0.0
                    m._fireball_fired = False
                    m.cast_cooldown = 3.2

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
        """탈출구 앞 2.8m 방어 판정 (5초 사수 시 상점 모달 팝업)"""
        dist_exit = math.hypot(px - self.escape_pos[0], py - self.escape_pos[1])
        if dist_exit <= 2.8:
            self.door_hold_timer -= dt
            progress_sec = 5.0 - max(0.0, self.door_hold_timer)
            pct = max(0.0, min(1.0, progress_sec / 5.0))
            bars = int(pct * 16)
            bar_str = "■" * bars + "□" * (16 - bars)

            blink = (int(globalClock.getFrameTime() * 8) % 2 == 0)
            blink_col = LColor(0.9, 0.15, 0.15, 1.0) if blink else LColor(0.3, 0.05, 0.05, 1.0)
            for lamp in self.door_lamps:
                lamp.setColor(blink_col)

            if self.door_hold_timer <= 0.0:
                for lamp in self.door_lamps:
                    lamp.setColor(LColor(0.2, 1.0, 0.4, 1.0))
                self.door_hold_timer = 5.0
                # 던전 크롤러: 스탯 분배 및 상점 모달 팝업 & 다음 스테이지 준비
                self.game_state = "SHOP"
                self.player.lock_mouse(False)
                self.ui_mgr.show_stage_clear_shop(self.current_stage, self.player, self.combat, self.on_shop_closed)
                return True
            else:
                msg = f"[ 비상문 개방 중: {progress_sec:.1f}s / 5.0s  [{bar_str}] ]\n[ 경고: 문이 열릴 때까지 괴물의 접근을 저지하세요! ]"
                self.ui_mgr.update_door_status(msg, fg=(1.0, 0.85, 0.2, 1.0))
        else:
            if self.door_hold_timer < 5.0:
                self.door_hold_timer = 5.0
                idle_col = LColor(0.35, 0.25, 0.08, 1.0)
                for lamp in self.door_lamps:
                    lamp.setColor(idle_col)
                self.ui_mgr.update_door_status("[ 비상문 개방 중단! 탈출구 앞(2.8m)을 사수하세요! ]", fg=(1.0, 0.3, 0.3, 1.0))
            else:
                self.ui_mgr.update_door_status("", show=False)
        return False

    # --- 메인 틱 루프 (Main Update Loop) ---
    def update(self, task):
        dt = min(0.1, globalClock.getDt())
        cont = task.cont if task is not None else 1

        # 1. 인트로 시네마틱 카메라 회전
        if self.game_state == "INTRO":
            t = globalClock.getFrameTime()
            cam_x = 45.0 + math.sin(t * 0.12) * 38.0
            cam_y = 45.0 + math.cos(t * 0.12) * 38.0
            self.camera.setPos(cam_x, cam_y, 11.5)
            self.camera.lookAt(45.0, 45.0, 1.5)
            self.update_chunks()
            return cont

        # 2. 상점 모달 상태 시 업데이트 정지
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

        # 9. 전투 및 뷰모델 갱신 (반동, 재장전, 탄약 습득, 밥빙)
        self.combat.update(dt, px, py, is_moving, is_sprinting)

        # 10. 배너 타이머
        if self.stage_banner_timer > 0.0:
            self.stage_banner_timer -= dt
            if self.stage_banner_timer <= 0.0:
                self.ui_mgr.hide_stage_banner()

        # 10-1. 정전 프로토콜 (Blackout & Crimson Protocol) 발동 및 타이머 갱신
        if self.time_left <= 200.0 and not self.blackout_triggered_this_stage:
            self.blackout_triggered_this_stage = True
            self.blackout_active = True
            b_duration = 18.0
            if "abyssal_reaper" in getattr(self.player, 'relics', []):
                b_duration += 10.0  # 심연의 수확자 유물: 정전 지속시간 10초 증가
            self.blackout_timer = b_duration
            self.audio_mgr.play_siren_alarm()
            self.ui_mgr.show_blackout_warning()
            self.liminal_fog.setColor(BLACKOUT_FOG_COLOR)
            self.liminal_fog.setExpDensity(0.052)  # 짙고 자욱한 핏빛 미스트 안개
            self.setBackgroundColor(BLACKOUT_FOG_COLOR)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(BLACKOUT_FOG_COLOR)
            self.amb_np.node().setColor((0.012, 0.002, 0.002, 1.0))
            self.combat.set_blackout_mode(True)

        if self.blackout_active:
            self.blackout_timer -= dt
            if self.blackout_timer <= 0.0:
                self.blackout_active = False
                self.audio_mgr.play_power_restored()
                self.ui_mgr.hide_blackout_warning()
                self.liminal_fog.setColor(FOG_COLOR)
                self.liminal_fog.setExpDensity(0.038)
                self.setBackgroundColor(FOG_COLOR)
                if hasattr(self, 'win') and self.win:
                    self.win.setClearColor(FOG_COLOR)
                self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
                self.combat.set_blackout_mode(False)
                self.ui_mgr.show_stage_banner("[ 전력 복구 완료 ]\n비상 조명 해제 및 기지 전력 정상화", color=(0.4, 0.9, 1.0, 1.0))
                self.stage_banner_timer = 2.5

        # 11. 5분 탈출 제한시간 카운트다운
        self.time_left -= dt
        if self.time_left <= 0.0:
            self.time_left = 0.0
            self.trigger_game_over(killer=None, reason="timeout")
            return cont

        # 12. 비상탈출문 5초 방어 판정 (성공 시 상점 모달 오픈)
        if self._update_door_defense(dt, px, py):
            return cont

        # 13. HUD 텍스트 캐싱 및 실시간 피격 효과 애니메이션 갱신
        self.ui_mgr.update(dt)
        self.ui_mgr.update_timer(self.time_left, self.current_stage)
        self.ui_mgr.update_hud(px, py, self.rendered_chunk_count, self.total_chunk_count)

        return cont

    def destroy(self):
        if hasattr(self, 'chunk_executor'):
            self.chunk_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()


if __name__ == "__main__":
    game = LiminalInfiniteLoop()
    game.run()