import os
import sys
import math
import random
import concurrent.futures
import gc

# Windows OS 스케줄러 프로세스 우선순위 승격 (High Priority) 및 1ms 고정밀 타이머 활성화
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000080) # HIGH_PRIORITY_CLASS
        ctypes.windll.winmm.timeBeginPeriod(1) # 1ms 고정밀 멀티미디어 타이머 (스터터링 방지)
    except Exception:
        pass

# 파이썬 가비지 컬렉터 최적화 (전투 중 15~50ms GC 스파이크 방지)
gc.set_threshold(60000, 20, 20)

# PyInstaller 번들 리소스 경로 및 작업 디렉토리 설정
if getattr(sys, 'frozen', False):
    basedir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    os.chdir(basedir)
else:
    basedir = os.path.dirname(os.path.abspath(__file__))

from direct.showbase.ShowBase import ShowBase
from direct.showbase.ShowBaseGlobal import globalClock
from panda3d.core import (
    SamplerState, LColor, WindowProperties,
    CardMaker, TextureStage, getModelPath, Filename, Vec3
)
import simplepbr

# Panda3D 리소스 탐색 경로에 번들 디렉토리 등록
getModelPath().prependDirectory(Filename.fromOsSpecific(basedir))
getModelPath().prependDirectory(Filename.fromOsSpecific(os.path.join(basedir, "assets")))

from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS,
    PLAYER_EYE_HEIGHT, RENDER_RADIUS, FOG_COLOR, BLACKOUT_FOG_COLOR,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import (
    check_line_of_sight, set_world_seed
)
from chunk import Chunk
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch,
    SkeletalDobermanHellhound, CableOverlordBoss
)

# 분리된 모듈 임포트
from navigation import pursuit_target
from collision import (
    get_nearby_colliders, resolve_collision
)
from audio_system import AudioManager
from ui_manager import UIManager
from combat_system import CombatSystem
from player_controller import PlayerController
from projectiles import (
    Fireball, GroundShockwave, ExplosionVisualEffect, FragGrenade
)
from interactive_objects import maybe_drop_monster_loot
from spawner import (
    get_gate_corridor_candidates, spawn_reinforcement_monster,
    spawn_monsters, spawn_hazard_barrels, spawn_supply_crates
)
from test_range import TestRangeManager
from monster_director import MonsterDirector
from escape_portal import EscapePortalManager
from lighting_manager import LightingManager


class LiminalInfiniteLoop(ShowBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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

        # 1. 카메라 가시거리 및 안개 설정 (FOV 96도 쾌적한 와이드 시야각, 안개 투과 한계 65m로 절두체 최적화)
        if hasattr(self, 'camLens') and self.camLens is not None:
            self.camLens.setNearFar(0.15, 65.0)
            self.camLens.setFov(96.0)
        self.rendered_chunk_count = 0
        self.total_chunk_count = 0
        self.light_cull_timer = 0.0
        self.last_light_cull_pos = None
        self.beacon_is_lit = False
        self.frame_count = 0
        self.is_test_mode = False
        self.lighting_mgr = LightingManager(self)
        self.setup_fog()

        # 2. 백룸 기본 조명 연출
        self.setup_lighting()

        # 3. 텍스처 로드
        self.load_assets()

        # 4. 무한 청크 관리자 설정 (PC 멀티코어 자원을 최대로 활용하는 병렬 워커 풀)
        cpu_cores = os.cpu_count() or 4
        worker_count = max(4, min(10, cpu_cores - 2))
        self.chunks = {}
        self.chunk_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="ChunkWorker"
        )
        self.active_chunk_futures = {}
        self.last_cull_pos = None
        self.world_root = self.render.attachNewNode("world_root")

        # 5. 던전 크롤러 몬스터 군단 관리자 및 발사체
        self.monsters = []
        self.corpses = []
        self.killer_monster = None
        self.fireballs = []
        self.fireball_pool = [Fireball(self.render) for _ in range(8)]
        self.shockwaves = []
        self.grenades = []
        self.explosions = []
        self.grenade_cooldown = 0.0
        self.hazard_barrels = []
        self.supply_crates = []
        self.nearby_crate = None
        self.item_drops = []
        self.nearby_item_drop = None

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
            on_exit=self.exit_game,
            on_test_mode=self.start_test_mode
        )

        self.combat = CombatSystem(
            self, self.render, self.camera, self.world_root,
            self.audio_mgr, self.ui_mgr
        )

        self.player = PlayerController(
            self, self.win, self.camera, self.mouseWatcherNode,
            self.audio_mgr, self.ui_mgr
        )
        self.player.world_root = self.world_root
        self.player.on_level_up = self._on_player_level_up
        self.test_range = TestRangeManager(self)
        self.monster_director = MonsterDirector(self)
        self.portal_mgr = EscapePortalManager(self)
        self.player.setup_input(
            on_shoot=self.shoot_pistol,
            on_reload=self.reload_pistol,
            on_aim_start=self.combat.start_aim,
            on_aim_stop=self.combat.stop_aim,
            on_grenade=self.throw_grenade,
            on_inventory=self.toggle_inventory,
            on_quick_use=self.use_quick_slot,
            on_escape=self.handle_escape,
            on_interact=self.handle_interaction,
            on_weapon_next=self.combat.next_weapon,
            on_weapon_prev=self.combat.prev_weapon,
            on_weapon_select=self.combat.switch_weapon
        )

        # 7. 게임 상태 및 5분(300초) 타이머 설정
        self.game_state = "INTRO"  # "INTRO", "PLAYING", "SHOP", "GAME_OVER", "VICTORY"
        self._is_level_up_modal = False
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 던전 크롤러 모드: 5분(300초)
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0
        self.bullet_time_timer = 0.0

        # 보스 [케이블 엔티티: 심연의 지배자] 상태 관리
        self.boss = None
        self.boss_spawned = False
        self.boss_defeat_handled = False

        # 초기 청크 및 인트로 씬 로드
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.escape_pos = (spawn_x + 75.0, spawn_y + 75.0)
        self.player.reset_position(spawn_x, spawn_y)
        self.update_chunks(force=True)

        self.show_intro_scene()
        self.taskMgr.add(self.update, "update_task")

        # 8. F11 전체화면 토글 설정, F1 테스트 모드, F5 몬스터 재소환, F6 보스 즉시 소환, F7 경험치 지급, Enter 확인
        self._is_fullscreen = False
        self._enforce_windowed_mode()
        self.accept("f11", self.toggle_fullscreen)
        self.accept("f1", self.start_test_mode)
        self.accept("f5", self._on_f5_pressed)
        self.accept("f6", self._on_f6_spawn_boss)
        self.accept("f7", self._on_f7_grant_exp)
        self.accept("f8", self._on_f8_test_elemental)
        self.accept("enter", self._on_enter_pressed)

    # --- 전체화면 토글 ---
    def _enforce_windowed_mode(self):
        """시작 시 창 모드를 강제 적용하여 전체화면 자동 진입 버그 방지"""
        if not hasattr(self, 'win') or self.win is None:
            return
        try:
            props = WindowProperties()
            props.setFullscreen(False)
            props.setSize(1600, 900)
            props.setUndecorated(False)
            self.win.requestProperties(props)
        except Exception:
            pass

    def toggle_fullscreen(self):
        """F11 키로 전체화면 / 창 모드를 전환"""
        if not hasattr(self, 'win') or self.win is None:
            return
        self._is_fullscreen = not self._is_fullscreen
        try:
            props = WindowProperties()
            props.setFullscreen(self._is_fullscreen)
            if not self._is_fullscreen:
                props.setSize(1600, 900)
                props.setUndecorated(False)
            self.win.requestProperties(props)
        except Exception:
            pass

    # --- 에셋 및 렌더링 설정 (LightingManager 위임) ---
    def setup_fog(self):
        return self.lighting_mgr.setup_fog()

    def setup_lighting(self):
        return self.lighting_mgr.setup_lighting()

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

    # --- 사용자 액션 및 게임플레이 시스템 ---
    def trigger_bullet_time(self, duration=3.0):
        """시간 감속 불릿 타임 (0.35x 월드 감속) 발동"""
        was_active = (self.bullet_time_timer > 0.0)
        self.bullet_time_timer = max(self.bullet_time_timer, duration)
        if not was_active and hasattr(self, 'audio_mgr') and self.audio_mgr:
            self.audio_mgr.play_bullet_time(is_start=True)
        if hasattr(self, 'ui_mgr') and self.ui_mgr:
            self.ui_mgr.set_bullet_time_hud(True, self.bullet_time_timer)

    def shoot_pistol(self):
        self.combat.shoot(self.monsters, self.player, self.game_state, hazard_barrels=self.hazard_barrels)

    def throw_grenade(self):
        """[G] 키 전술 파열 수류탄 투척 (쿨타임 없이 보유한 개수만큼 연속 투척)"""
        if self.game_state != "PLAYING":
            return False

        # 연속 투척 시 키 중복 트리거 방지용 최소 딜레이(0.15초)
        if getattr(self, 'grenade_cooldown', 0.0) > 0.0:
            return False

        # 수류탄 보유 수량 확인
        gr_count = self.player.get_item_count("frag_grenade") if hasattr(self.player, 'get_item_count') else 0
        if gr_count <= 0:
            if hasattr(self, 'ui_mgr') and self.ui_mgr:
                self.ui_mgr.show_hit_marker("수류탄 소진! [0개]", (1.0, 0.25, 0.25, 1.0))
            if hasattr(self, 'audio_mgr') and hasattr(self.audio_mgr, 'play_empty_click'):
                self.audio_mgr.play_empty_click()
            return False

        # 1개 소모
        self.player.consume_item("frag_grenade", 1)
        remaining = self.player.get_item_count("frag_grenade")

        # 쿨타임 완전 제거: 빠른 연속 투척을 위한 최소 프레임 간격(0.15s)만 적용
        self.grenade_cooldown = 0.15

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_grenade_throw'):
            self.audio_mgr.play_grenade_throw()
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        start_pos = self.camera.getPos() + cam_fwd * 0.45
        gr = FragGrenade(self.world_root, start_pos, cam_fwd, self.audio_mgr)
        self.grenades.append(gr)

        # UI 피드백 및 스킬 HUD 잔여 수량 갱신
        if hasattr(self, 'ui_mgr') and self.ui_mgr:
            self.ui_mgr.show_hit_marker(f"수류탄 투척! (잔여: {remaining}개)", (0.4, 1.0, 0.5, 1.0))
            slide_ready = getattr(self.player, 'slide_cooldown', 0.0) <= 0.0
            self.ui_mgr.update_skills_hud(slide_ready, grenade_count=remaining)

        return True

    def reload_pistol(self):
        self.combat.reload(self.game_state)

    def toggle_inventory(self):
        """[Tab] 또는 [I] 키로 전술 인벤토리 배낭 창 토글"""
        if self.game_state == "PLAYING":
            self.open_inventory()
        elif self.game_state == "INVENTORY":
            self.close_inventory()

    def open_inventory(self):
        """전술 인벤토리 오픈 및 마우스 잠금 해제, 게임 루프 일시정지"""
        if self.game_state != "PLAYING":
            return
        self.game_state = "INVENTORY"
        self.player.lock_mouse(False)
        self.combat.stop_aim()
        self.audio_mgr.play_inventory_toggle(True)
        self.ui_mgr.show_inventory(
            player=self.player,
            combat=self.combat,
            on_use_item_callback=self._on_inventory_use_item,
            on_close_callback=self.close_inventory
        )

    def close_inventory(self):
        """전술 인벤토리 닫기 및 마우스 잠금 복원, 게임 루프 재개"""
        if self.game_state != "INVENTORY":
            return
        self.game_state = "PLAYING"
        self.ui_mgr.hide_inventory()
        self.player.lock_mouse(True)
        self.audio_mgr.play_inventory_toggle(False)
        self._update_quickslot_hud()
        if getattr(self.player, 'pending_perk_picks', 0) > 0:
            self._on_player_level_up()

    def handle_escape(self):
        """[ESC] 키 입력 처리: 인벤토리 열려있으면 닫기, 일시정지/설정 메뉴 토글, 테스트 모드면 인트로 복귀"""
        if self.game_state == "INVENTORY":
            self.close_inventory()
        elif self.game_state == "PAUSED":
            self.resume_game()
        elif self.game_state == "PLAYING":
            self.pause_game()
        elif getattr(self, 'is_test_mode', False):
            self.return_to_intro()
        else:
            self.player.lock_mouse(not self.player.mouse_locked)

    def pause_game(self):
        """[ESC] 게임 일시정지 및 설정 모달 팝업"""
        if self.game_state != "PLAYING" or self.game_over or self.game_won:
            return
        self.game_state = "PAUSED"
        self.player.lock_mouse(False)
        self.combat.stop_aim()
        if hasattr(self, 'audio_mgr') and self.audio_mgr:
            self.audio_mgr.play_inventory_toggle(True)
        self.ui_mgr.show_pause_menu(
            player=self.player,
            combat=self.combat,
            audio_mgr=self.audio_mgr,
            on_resume_callback=self.resume_game,
            on_restart_callback=self.restart_game,
            on_title_callback=self.return_to_intro,
            on_exit_callback=self.exit_game
        )

    def resume_game(self):
        """일시정지 해제 및 게임플레이 현장 복귀"""
        if self.game_state != "PAUSED":
            return
        self.ui_mgr.hide_pause_menu()
        self.game_state = "PLAYING"
        self.player.lock_mouse(True)
        if hasattr(self, 'audio_mgr') and self.audio_mgr:
            self.audio_mgr.play_inventory_toggle(False)

    def trigger_stage_clear(self):
        """스테이지 클리어 시 작전 전투 결과 보고서(AAR) 표시 후 특성 퍽 상점으로 전환"""
        self.game_state = "AAR"
        self.player.lock_mouse(False)
        self.combat.stop_aim()

        stats = self.combat.get_stage_stats() if hasattr(self.combat, 'get_stage_stats') else {}
        stats["damage_taken"] = getattr(self.player, 'stage_damage_taken', 0.0)

        def on_aar_continue():
            self.game_state = "SHOP"
            self.ui_mgr.show_stage_clear_shop(
                self.current_stage, self.player, self.combat,
                self.on_shop_closed, on_victory_callback=self.trigger_victory
            )

        self.ui_mgr.show_after_action_report(
            stage=self.current_stage,
            stats=stats,
            on_continue_callback=on_aar_continue
        )

    def _on_inventory_use_item(self, item_id):
        """인벤토리 모달 내 [사용하기] 클릭 콜백"""
        success, msg = self.player.use_item(item_id, self.combat, self)
        if success:
            self.audio_mgr.play_item_use()
        self.ui_mgr.inv_msg_text.setText(msg)
        self.ui_mgr._refresh_inventory_ui()
        self._update_quickslot_hud()

    def use_quick_slot(self, slot_num):
        """[1~4] 키로 배낭을 열지 않고 전술 퀵슬롯 아이템 즉시 사용, 또는 특성 선택 모달에서 [1], [2], [3] 카드 선택"""
        if self.game_state == "SHOP" or (hasattr(self.ui_mgr, 'shop_modal') and self.ui_mgr.shop_modal and not self.ui_mgr.shop_modal.isHidden()):
            if hasattr(self.ui_mgr, 'select_perk_by_key'):
                self.ui_mgr.select_perk_by_key(slot_num)
            return

        if self.game_state != "PLAYING":
            return
        success, msg = self.player.use_quick_slot(slot_num, self.combat, self)
        if success:
            self.audio_mgr.play_item_use()
            self.ui_mgr.show_hit_marker(msg)
        else:
            self.ui_mgr.show_hit_marker(f"[ 사용 불가 ] {msg}")
        self._update_quickslot_hud()

    def _update_quickslot_hud(self):
        """하단 퀵슬롯 HUD 텍스트 갱신"""
        self.ui_mgr.update_quickslots_hud(self.player.inventory)

    def exit_game(self):
        self.destroy()
        sys.exit(0)


    def spawn_fireball(self, start_pos, target_pos):
        """파이어볼 오브젝트 풀에서 가용 인스턴스 활성화 (동적 할당 0%)"""
        for fb in self.fireball_pool:
            if not fb.is_active:
                fb.activate(start_pos, target_pos)
                if fb not in self.fireballs:
                    self.fireballs.append(fb)
                return fb
        fb = self.fireball_pool[0]
        fb.activate(start_pos, target_pos)
        if fb not in self.fireballs:
            self.fireballs.append(fb)
        return fb

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
        self.bullet_time_timer = 0.0
        self.audio_mgr.stop_bullet_time()
        self.ui_mgr.hide_blackout_warning()
        if hasattr(self.ui_mgr, 'set_bullet_time_hud'):
            self.ui_mgr.set_bullet_time_hud(False)

        # 테스트 모드 활성 상태 정리
        if getattr(self, 'is_test_mode', False):
            self.test_range.cleanup_test_room()
            self.update_chunks(force=True)

        if hasattr(self, 'combat') and self.combat:
            self.combat.reset_state(1, keep_ammo=False)

        self.game_state = "INTRO"
        self.player.lock_mouse(False)
        self.combat.vm_root.hide()
        self.combat.set_blackout_mode(False)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.render.clearLight(self.combat.pl_np)
        self.render.clearLight(self.combat.fill_np)
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
            self.beacon_is_lit = False
        self.ui_mgr.show_intro()
        self.audio_mgr.set_bgm_mode("INTRO")

    def start_game(self):
        """START 버튼 클릭 시 1인칭 던전 크롤러 게임플레이 시작"""
        if getattr(self, 'is_test_mode', False):
            self.test_range.cleanup_test_room()

        self.game_state = "PLAYING"
        self.restart_game()
        self.combat.vm_root.show()
        self.render.setLight(self.combat.pl_np)
        self.render.setLight(self.combat.fill_np)
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)
        self.audio_mgr.set_bgm_mode("PLAYING")

    def start_test_mode(self):
        """테스트 모드: 넓은 대형 시험장 룸, 5종 전 몬스터가 정지 상태로 대기 (자유 관찰 및 사격 테스트)"""
        self.test_range.start_test_mode()

    def _build_test_room(self):
        """테스트 모드 전용 44m x 44m 대형 룸 생성 (호환용 래퍼)"""
        self.test_range.build_test_room()

    def respawn_test_monsters(self):
        """테스트 모드 5종 몬스터를 스탠드 위치에 정지 상태로 소환/재소환 (호환용 래퍼)"""
        self.test_range.respawn_test_monsters()

    def _on_f5_pressed(self):
        """[F5] 키 입력 시 테스트 모드 몬스터 즉시 재소환"""
        self.test_range.on_f5_pressed()

    def _on_f6_spawn_boss(self):
        """[F6] 단축키: 보스 [케이블 엔티티: 심연의 지배자] 즉시 소환 (테스트 및 개발용)"""
        px, py = self.camera.getX(), self.camera.getY()
        h_rad = math.radians(getattr(self.player, 'heading', 0.0))
        bx = px - math.sin(h_rad) * 9.0
        by = py + math.cos(h_rad) * 9.0
        self.spawn_boss(bx, by)
        if hasattr(self, 'ui_mgr') and self.ui_mgr:
            self.ui_mgr.show_hit_marker("[ F6: 보스 엔티티 즉시 소환됨! ]", (1.0, 0.3, 0.3, 1.0))

    def spawn_boss(self, x=None, y=None):
        """[케이블 엔티티: 심연의 지배자] 대형 보스 몬스터 소환 및 UI 보스 체력바 활성화"""
        if self.boss and getattr(self.boss, 'hp', 0) > 0 and self.boss in self.monsters:
            return self.boss

        if x is None or y is None:
            ex, ey = getattr(self, 'escape_pos', (45.0, 45.0))
            x = ex + 4.0
            y = ey + 4.0

        self.boss = CableOverlordBoss(self.world_root, x, y)
        self.monsters.append(self.boss)
        self.boss_spawned = True
        self.boss_defeat_handled = False

        if hasattr(self, 'ui_mgr') and self.ui_mgr:
            self.ui_mgr.show_boss_hp_bar("케이블 엔티티 : 심연의 지배자", self.boss.hp, self.boss.max_hp)
            self.ui_mgr.show_stage_banner(
                "[ ! 긴급 경보: 심연의 지배자 각성 ! ]\n백룸 케이블 엔티티가 탈출 관문을 봉쇄했습니다! 보스를 격파하세요!",
                color=(1.0, 0.2, 0.2, 1.0)
            )
            self.stage_banner_timer = 4.5

        if hasattr(self, 'audio_mgr') and self.audio_mgr:
            self.audio_mgr.play_siren_alarm()

        return self.boss

    def return_to_intro(self):
        self.show_intro_scene()

    def get_gate_corridor_candidates(self, min_dist=6.0, max_dist=32.0):
        return get_gate_corridor_candidates(getattr(self, 'escape_pos', None), min_dist, max_dist)

    def spawn_reinforcement_monster(self, pos=None, near_gate=True):
        return spawn_reinforcement_monster(self, pos, near_gate)

    def spawn_monsters(self, stage=1):
        return spawn_monsters(self, stage)

    def spawn_hazard_barrels(self):
        return spawn_hazard_barrels(self)

    def spawn_supply_crates(self):
        return spawn_supply_crates(self)


    def handle_interaction(self):
        """[E] 키 상호작용: 접근한 전술 보급 상자 개봉 또는 드랍 아이템 습득"""
        if self.game_state != "PLAYING" or self.game_over or self.game_won:
            return
        if self.nearby_crate and not self.nearby_crate.is_opened:
            self.nearby_crate.open(self.player, self.combat, self.ui_mgr)
            self.ui_mgr.hide_interact_prompt()
            self.nearby_crate = None
        elif getattr(self, 'nearby_item_drop', None) and not self.nearby_item_drop.is_collected:
            drop = self.nearby_item_drop
            drop.collect(self.player, self.combat, self.ui_mgr)
            if drop in self.item_drops:
                self.item_drops.remove(drop)
            self.ui_mgr.hide_interact_prompt()
            self.nearby_item_drop = None
            if hasattr(self.player, 'inventory') and hasattr(self.ui_mgr, 'update_quickslots_hud'):
                self.ui_mgr.update_quickslots_hud(self.player.inventory)

    def clear_projectiles(self):
        """스테이지 전환/리셋 시 발사체, 충격파, 수류탄, 유류 드럼통, 보급 상자, 드랍 아이템 일괄 정리"""
        for fb in getattr(self, 'fireball_pool', []):
            fb.deactivate()
        self.fireballs.clear()
        for sw in self.shockwaves:
            sw.destroy()
        self.shockwaves.clear()
        for gr in self.grenades:
            gr.destroy()
        self.grenades.clear()
        for b in self.hazard_barrels:
            b.destroy()
        self.hazard_barrels.clear()
        for cr in self.supply_crates:
            cr.destroy()
        self.supply_crates.clear()
        for drop in getattr(self, 'item_drops', []):
            drop.destroy()
        self.item_drops.clear()
        self.nearby_item_drop = None
        for exp in self.explosions:
            exp.destroy()
        self.explosions.clear()

    def restart_game(self):
        """던전 게임 초기화 (체력, 몬스터 군단, 5분 타이머, 탈출구)"""
        self.clear_projectiles()
        gc.collect(1) # 유휴 타이밍에 메모리 수거로 인게임 프레임 드랍 차단
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 5분 제한시간
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0
        self.bullet_time_timer = 0.0
        self.audio_mgr.stop_bullet_time()
        if hasattr(self.ui_mgr, 'set_bullet_time_hud'):
            self.ui_mgr.set_bullet_time_hud(False)

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
        self.player.perks = set()
        self.player.perk_levels = {}
        self.player.pending_perk_picks = 0
        self.player.on_level_up = self._on_player_level_up
        self._is_level_up_modal = False
        if hasattr(self.ui_mgr, 'update_perk_badges'):
            self.ui_mgr.update_perk_badges(self.player.perks)
        self.ui_mgr.update_relic_badges(self.player.relics)
        self.player.stage_damage_taken = 0.0

        # 보스 상태 초기화
        self.boss = None
        self.boss_spawned = False
        self.boss_defeat_handled = False
        if hasattr(self.ui_mgr, 'hide_boss_hp_bar'):
            self.ui_mgr.hide_boss_hp_bar()

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        # 전투 서브시스템 리셋
        self.combat.stop_aim()
        self.combat.reset_state(self.current_stage, keep_ammo=False)
        self.player.reset_inventory()
        self._update_quickslot_hud()

        # 비동기 작업 정리
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        self.killer_monster = None

        # 맵 및 청크 완전 무작위 재생성 (새로운 월드 시드 적용)
        self.regenerate_map()

        # 탈출구 생성 (관문 위치 확정 및 단단한 관문 충돌체 등록)
        self.setup_escape_portal()

        # 관문 접근 경보 및 증원 상태 리셋
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0

        # 다중 몬스터 군단 스폰 (관문 주변 수호 몬스터 집중 배치)
        self.spawn_monsters(self.current_stage)
        self.spawn_hazard_barrels()
        self.spawn_supply_crates()

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
        """특성 획득 후 다음 스테이지로 진입"""
        self.clear_projectiles()
        gc.collect(1) # 스테이지 전환 시 가비지 수거로 전투 중 무스터터링 보장
        prev_stage = self.current_stage
        self.current_stage += 1
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.player.stage_damage_taken = 0.0

        # 보스 상태 초기화
        self.boss = None
        self.boss_spawned = False
        self.boss_defeat_handled = False
        if hasattr(self.ui_mgr, 'hide_boss_hp_bar'):
            self.ui_mgr.hide_boss_hp_bar()

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

        # 새 스테이지 진입: 새로운 미로 맵 및 청크 완전 무작위 재생성
        self.regenerate_map()

        # 새 탈출구 생성 (관문 위치 확정 및 관문 충돌체 등록)
        self.setup_escape_portal()

        # 관문 접근 경보 및 증원 상태 리셋
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0

        # 다중 몬스터 군단 재배치 (관문 주변 수호 몬스터 집중 배치)
        self.spawn_monsters(self.current_stage)
        self.spawn_hazard_barrels()
        self.spawn_supply_crates()

        # 전투 서브시스템: 탄약 보급
        self.combat.stop_aim()
        self.combat.ammo = self.combat.max_ammo
        self.combat.reserve_ammo += 24
        self.combat.reset_state(self.current_stage, keep_ammo=True)
        self._update_quickslot_hud()

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
        if getattr(self.player, 'pending_perk_picks', 0) > 0:
            self._on_player_level_up()

    def _on_player_level_up(self):
        """플레이어 레벨업 시 전술 퍽(Perk) 3-Card 선택 모달 호출"""
        if self.game_over or self.game_won:
            return
        if self.game_state == "INVENTORY":
            # 인벤토리 열려있을 때는 닫힌 후 처리
            return
        if self.game_state == "SHOP" or getattr(self, '_is_level_up_modal', False):
            return
        if self.game_state != "PLAYING":
            return

        self._trigger_level_up_modal()

    def _trigger_level_up_modal(self):
        """레벨업 퍽 선택 창 활성화 및 게임 일시정지"""
        if getattr(self.player, 'pending_perk_picks', 0) <= 0:
            return

        self.game_state = "SHOP"
        self._is_level_up_modal = True
        self.player.lock_mouse(False)
        self.combat.stop_aim()

        self.ui_mgr.show_levelup_perk_modal(
            level=self.player.level,
            player=self.player,
            combat=self.combat,
            on_confirm_callback=self._on_level_up_confirmed,
            pending_count=self.player.pending_perk_picks
        )

    def _on_level_up_confirmed(self):
        """레벨업 퍽 선택 완료 후 콜백: 잔여 퍽 선택이 있으면 재오픈, 없으면 전투 복귀"""
        if getattr(self.player, 'pending_perk_picks', 0) > 0:
            self.player.pending_perk_picks -= 1

        self.ui_mgr.update_hp_exp(
            self.player.hp, self.player.max_hp, self.player.exp, self.player.exp_to_next,
            level=self.player.level, pending_perks=self.player.pending_perk_picks
        )

        if getattr(self.player, 'pending_perk_picks', 0) > 0:
            # 연속 레벨업 등으로 퍽 포인트가 남아있는 경우 다음 퍽 카드 제시
            self._trigger_level_up_modal()
        else:
            # 모든 퍽 선택 완료: 게임 플레이 복귀
            gc.collect(1)
            self._is_level_up_modal = False
            self.game_state = "PLAYING"
            self.ui_mgr.start_game_ui()
            self.player.lock_mouse(True)
            self.ui_mgr.show_hit_marker("[ ★ 전술 퍽 장착 완료! 전투 재개 ★ ]", (0.35, 1.0, 0.65, 1.0))

    def _on_enter_pressed(self):
        """[Enter] 키로 퍽 선택 모달 확인 또는 다음 진행"""
        if self.game_state == "SHOP" and hasattr(self.ui_mgr, 'shop_modal') and not self.ui_mgr.shop_modal.isHidden():
            self.ui_mgr._confirm_shop_and_start()

    def _on_f7_grant_exp(self):
        """[F7] 단축키: 즉시 100 EXP 획득 (레벨업 및 전술 퍽 선택 테스트용)"""
        if getattr(self, 'is_test_mode', False) or self.game_state == "PLAYING":
            self.player.gain_exp(100)
            if hasattr(self.ui_mgr, 'show_hit_marker'):
                self.ui_mgr.show_hit_marker("[ F7: +100 EXP 획득! ]", (0.35, 1.0, 0.65, 1.0))

    def _on_f8_test_elemental(self):
        """[F8] 단축키: 원소 피해 효과(화염 지속 피해 & 전기 감전 아크) 테스트 및 특성 즉시 부여"""
        if not hasattr(self.player, 'acquired_perks') or self.player.acquired_perks is None:
            self.player.acquired_perks = set()
        self.player.acquired_perks.add("dragons_breath")
        self.player.acquired_perks.add("tesla_arc")

        target_m = None
        min_d = 999.0
        px, py = self.camera.getX(), self.camera.getY()
        for m in getattr(self, 'monsters', []):
            if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                d = math.hypot(m.pos.x - px, m.pos.y - py)
                if d < min_d:
                    min_d = d
                    target_m = m

        if target_m:
            burn_t = getattr(target_m, 'burn_timer', 0.0)
            shock_t = getattr(target_m, 'shock_timer', 0.0)
            m_h = getattr(target_m, 'height', 2.0)
            # 플레이어 시선 방향에서 바라본 몬스터 흉부 표면 피격점 계산
            dx = px - target_m.pos.x
            dy = py - target_m.pos.y
            dist_xy = math.hypot(dx, dy)
            if dist_xy > 0.01:
                hit_pos = Vec3(target_m.pos.x + (dx / dist_xy) * 0.45, target_m.pos.y + (dy / dist_xy) * 0.45, target_m.pos.z + m_h * 0.55)
            else:
                hit_pos = Vec3(target_m.pos.x, target_m.pos.y, target_m.pos.z + m_h * 0.55)

            if burn_t <= 0.0:
                target_m.apply_burn(dps=35.0, duration=4.5)
                self.ui_mgr.show_hit_marker("[화염] [F8 원소 테스트] 주변 몬스터 화염 피해 & 불길 효과 적용!", (1.0, 0.55, 0.15, 1.0))
            elif shock_t <= 0.0:
                target_m.apply_shock(damage=35.0, duration=2.5, hit_pos=hit_pos)
                self.ui_mgr.show_hit_marker("[전기] [F8] 번개 줄기 범위 대폭 확장(최대 7.5m) & 옆 몬스터 연쇄 방전!", (0.35, 0.88, 1.0, 1.0))
            else:
                target_m.apply_burn(dps=35.0, duration=4.5)
                target_m.apply_shock(damage=35.0, duration=2.5, hit_pos=hit_pos)
                self.ui_mgr.show_hit_marker("[화염+전기] [F8] 화염 불길 + 최대 7.5m 연쇄 번개 줄기 동시 발동!", (1.0, 0.9, 0.3, 1.0))
        else:
            self.ui_mgr.show_hit_marker("[F8] 드래곤 브레스(화염) & 테슬라 아크(전기) 특성 장착 완료!", (1.0, 0.85, 0.2, 1.0))

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
    def regenerate_map(self):
        """월드 맵 시드를 무작위로 재설정하고 기존 모든 청크를 파괴 후 새 맵으로 완전 재생성"""
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()

        for chunk in self.chunks.values():
            chunk.destroy()
        self.chunks.clear()

        new_seed = set_world_seed()
        self.last_chunk = None
        self.lighting_mgr.reset_cull_cache()
        self.update_chunks(force=True)
        return new_seed

    def setup_escape_portal(self):
        """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성 (EscapePortalManager 위임)"""
        return self.portal_mgr.setup_escape_portal()

    # --- 청크 스트리밍 및 컬링 최적화 ---
    def update_chunks(self, force=False):
        if getattr(self, 'is_test_mode', False):
            return
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
        """이동 거리 임계치(2.0m) 기반 청크 가시거리 컬링 최적화 (LightingManager 위임)"""
        return self.lighting_mgr.cull_chunks_to_view(force=force)

    def _update_dynamic_lights(self, px, py, dt):
        """동적 광원 가시거리 컬링 및 조명 슬롯 버짓 관리 (LightingManager 위임)"""
        return self.lighting_mgr.update_dynamic_lights(px, py, dt)

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

    # --- 몬스터 AI 제어 (MonsterDirector 위임) ---
    def _update_monsters(self, dt, px, py):
        """몬스터 집단 AI, 스킬, 충돌, 사운드, 시체 파편 갱신 (MonsterDirector 위임)"""
        return self.monster_director.update_monsters(dt, px, py)

    def _update_projectiles(self, dt, px, py, pz):
        """파이어볼 비행/벽체 및 플레이어 피격 충돌, 땅울림 분진 갱신"""
        # 1. 파이어볼 갱신 (오브젝트 풀 기반 비활성화)
        for fb in self.fireballs[:]:
            alive = fb.update(dt)
            if not alive:
                fb.deactivate()
                self.fireballs.remove(fb)
                continue

            # 벽체 충돌 검사
            cols = get_nearby_colliders(self.chunks, fb.pos.x, fb.pos.y, search_dist=0.6, curr_z=fb.pos.z)
            hit_wall = False
            for min_x, min_y, max_x, max_y in cols:
                if min_x <= fb.pos.x <= max_x and min_y <= fb.pos.y <= max_y:
                    hit_wall = True
                    break
            if hit_wall:
                self.explosions.append(ExplosionVisualEffect(self.world_root, fb.pos, self.render))
                fb.deactivate()
                self.fireballs.remove(fb)
                continue

            # 플레이어 충돌 검사
            dist_p = math.hypot(fb.pos.x - px, fb.pos.y - py)
            dz = abs(fb.pos.z - pz)
            if dist_p < 0.95 and dz < 1.6:
                is_dead = self.player.take_damage(fb.damage, source_pos=(fb.pos.x, fb.pos.y))
                fb.deactivate()
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

        # 3. 전술 파열 수류탄 갱신 및 폭발
        for gr in self.grenades[:]:
            alive = gr.update(dt, self.chunks, self.monsters)
            if not alive:
                gr.explode(self.monsters, self.player, self.ui_mgr, self.hazard_barrels, explosion_list=self.explosions)
                if gr in self.grenades:
                    self.grenades.remove(gr)

        # 4. 폭발성 유류 드럼통 점화 및 폭발 갱신
        for b in self.hazard_barrels[:]:
            alive = b.update(dt, self.monsters, self.player, self.ui_mgr, self.hazard_barrels, explosion_list=self.explosions)
            if not alive:
                if b in self.hazard_barrels:
                    self.hazard_barrels.remove(b)

        # 5. 수류탄 / 유류 드럼통 3D 폭발 비주얼 이펙트 갱신
        for exp in self.explosions[:]:
            if not exp.update(dt):
                if exp in self.explosions:
                    self.explosions.remove(exp)

        return False

    def _update_door_defense(self, dt, px, py):
        """탈출 관문 앞 3.8m 방어 판정 (EscapePortalManager 위임)"""
        return self.portal_mgr.update_door_defense(dt, px, py)

    # --- 메인 틱 루프 (Main Update Loop) ---
    def update(self, task):
        raw_dt = min(0.1, globalClock.getDt())
        cont = task.cont if task is not None else 1

        # 0. 불릿 타임 (시간 감속) 연산: 몬스터 및 월드 발사체 속도를 0.35x로 감속 (플레이어는 실시간 유지)
        if self.bullet_time_timer > 0.0:
            self.bullet_time_timer = max(0.0, self.bullet_time_timer - raw_dt)
            world_dt = raw_dt * 0.35
            self.ui_mgr.set_bullet_time_hud(True, self.bullet_time_timer)
            if self.bullet_time_timer <= 0.0:
                if hasattr(self, 'audio_mgr') and self.audio_mgr:
                    self.audio_mgr.play_bullet_time(is_start=False)
                self.ui_mgr.set_bullet_time_hud(False)
        else:
            world_dt = raw_dt

        if self.audio_mgr:
            self.audio_mgr.update_bullet_time(raw_dt)

        dt = raw_dt

        # 1. 인트로 시네마틱 카메라 회전
        if self.game_state == "INTRO":
            t = globalClock.getFrameTime()
            cam_x = 45.0 + math.sin(t * 0.12) * 38.0
            cam_y = 45.0 + math.cos(t * 0.12) * 38.0
            self.camera.setPos(cam_x, cam_y, 11.5)
            self.camera.lookAt(45.0, 45.0, 1.5)
            self.update_chunks()
            return cont

        # 2. 상점, 인벤토리, 일시정지, 결과보고서 모달 상태 시 월드 엔티티 정지
        if self.game_state in ("SHOP", "INVENTORY", "PAUSED", "AAR"):
            self.ui_mgr.update(dt)
            return cont

        # 3. 승리 및 게임 오버 상태 처리
        if self.game_won or self.game_state == "VICTORY":
            return cont

        if self.game_over or self.game_state == "GAME_OVER":
            self.ui_mgr.update(dt, player_pos=(self.camera.getX(), self.camera.getY()), camera_heading=getattr(self.player, 'heading', 0.0))
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
        chunk_created = self._mount_async_chunks() if not getattr(self, 'is_test_mode', False) else False

        # 5. 플레이어 시선 및 이동/충돌 처리 (실시간 raw_dt 유지로 신속한 전술 조준)
        is_moving, is_sprinting, view_changed = self.player.update(dt, self.chunks)
        if is_moving and not getattr(self, 'is_test_mode', False):
            self.update_chunks()

        # 6. 괴물 군단 AI 및 공격 판정 (불릿 타임 시 0.35x world_dt 적용)
        px, py = self.camera.getX(), self.camera.getY()
        pz = self.camera.getZ()
        game_ended, closest_dist = self._update_monsters(world_dt, px, py)
        if game_ended:
            return cont

        # 6-1. 마녀 파이어볼 및 진흙오크 충격파 갱신 (불릿 타임 시 0.35x world_dt 적용)
        if not getattr(self, 'is_test_mode', False):
            if self._update_projectiles(world_dt, px, py, pz):
                return cont

        # 7. 오디오 3D 위치 및 감쇠
        self.audio_mgr.update(dt, closest_dist, closest_dist, False, False)

        # 7-1. 동적 조명 컬링 (SimplePBR 8-Light 버짓 관리 및 거리별 자동 온/오프)
        if not getattr(self, 'is_test_mode', False):
            self._update_dynamic_lights(px, py, dt)

        # 8. 안개 가시거리 컬링 (임계치 2.0m 이동 또는 신규 청크 마운트 시만 실행)
        if not getattr(self, 'is_test_mode', False):
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
        if not getattr(self, 'is_test_mode', False):
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

            # 12-1. 비상 비콘 유도등 실시간 맥동
            if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
                t_now = globalClock.getFrameTime()
                pulse = 0.65 + 0.35 * math.sin(t_now * 4.5)
                self.beacon_light_np.node().setColor((0.35 * pulse, 1.5 * pulse, 0.55 * pulse, 1.0))

            # 13. HUD 텍스트 캐싱 및 실시간 피격 효과 애니메이션 갱신
            self.ui_mgr.update(dt, player_pos=(px, py), camera_heading=getattr(self.player, 'heading', 0.0), is_moving=is_moving, is_sprinting=is_sprinting)
            self.ui_mgr.update_timer(self.time_left, self.current_stage)
            self.ui_mgr.update_hud(px, py, getattr(self, 'escape_pos', None), getattr(self.player, 'heading', 0.0))
            if hasattr(self.ui_mgr, 'update_tactical_radar'):
                self.ui_mgr.update_tactical_radar((px, py), getattr(self.player, 'heading', 0.0), self.monsters, getattr(self, 'escape_pos', None), getattr(self, 'supply_crates', []))
        else:
            # 테스트 모드 HUD
            self.ui_mgr.update(dt, player_pos=(px, py), camera_heading=getattr(self.player, 'heading', 0.0), is_moving=is_moving, is_sprinting=is_sprinting)
            self.ui_mgr.update_timer(9999.0)
            self.ui_mgr.update_hud(px, py, "TEST", getattr(self.player, 'heading', 0.0))
            if hasattr(self.ui_mgr, 'update_tactical_radar'):
                self.ui_mgr.update_tactical_radar((px, py), getattr(self.player, 'heading', 0.0), self.monsters, None, getattr(self, 'supply_crates', []))

        # 전술 스킬 (슬라이드 / 수류탄) 및 필드 보급 상자 인터랙션 갱신
        if self.grenade_cooldown > 0.0:
            self.grenade_cooldown = max(0.0, self.grenade_cooldown - dt)

        # 드랍된 전술 아이템 애니메이션 및 자동 수거(Auto-pickup) 판정
        closest_interact_drop = None
        floor_pz = self.camera.getZ() - PLAYER_EYE_HEIGHT
        for drop in self.item_drops[:]:
            status = drop.update(dt, px, py, floor_pz)
            if status == "COLLECT":
                drop.collect(self.player, self.combat, self.ui_mgr)
                if drop in self.item_drops:
                    self.item_drops.remove(drop)
                if hasattr(self.player, 'inventory') and hasattr(self.ui_mgr, 'update_quickslots_hud'):
                    self.ui_mgr.update_quickslots_hud(self.player.inventory)
            elif status == "CAN_INTERACT":
                if closest_interact_drop is None:
                    closest_interact_drop = drop
            elif status == "DESTROYED":
                if drop in self.item_drops:
                    self.item_drops.remove(drop)

        # 필드 전술 보급 상자 또는 드랍 아이템 [E] 상호작용 프롬프트 검사
        closest_crate = None
        for cr in self.supply_crates:
            if cr.can_interact(px, py, floor_pz):
                closest_crate = cr
                break
        self.nearby_crate = closest_crate

        if closest_crate:
            self.ui_mgr.show_interact_prompt("[ E ] 전술 보급 상자 개봉")
            self.nearby_item_drop = None
        elif closest_interact_drop:
            self.nearby_item_drop = closest_interact_drop
            self.ui_mgr.show_interact_prompt(f"[ E ] {closest_interact_drop.name} 획득")
        else:
            self.nearby_item_drop = None
            self.ui_mgr.hide_interact_prompt()

        slide_ready = getattr(self.player, 'slide_cooldown', 0.0) <= 0.0
        gr_count = self.player.get_item_count("frag_grenade") if hasattr(self.player, 'get_item_count') else 0
        self.ui_mgr.update_skills_hud(slide_ready, grenade_count=gr_count)

        return cont

    def destroy(self):
        for fb in getattr(self, 'fireball_pool', []):
            fb.destroy()
        self.fireball_pool = []
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
        if hasattr(self, 'chunk_executor'):
            self.chunk_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()


if __name__ == "__main__":
    game = LiminalInfiniteLoop()
    if "--test" in sys.argv or "test" in sys.argv:
        game.start_test_mode()
    game.run()
