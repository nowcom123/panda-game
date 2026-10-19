import os
import sys
import math
import random
import concurrent.futures

# PyInstaller 번들 리소스 경로 및 작업 디렉토리 설정
if getattr(sys, 'frozen', False):
    basedir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    os.chdir(basedir)
else:
    basedir = os.path.dirname(os.path.abspath(__file__))

from direct.showbase.ShowBase import ShowBase
from direct.showbase.ShowBaseGlobal import globalClock
from panda3d.core import (
    SamplerState, Fog, AmbientLight, PointLight, LColor, WindowProperties,
    CardMaker, TextureStage, getModelPath, Filename
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
    find_cell_path, check_line_of_sight, cell_has_pillar, set_world_seed
)
from chunk import Chunk
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch,
    SkeletalDobermanHellhound, CableOverlordBoss
)
from geometry import make_cube_to

# 분리된 모듈 임포트
from collision import (
    get_nearby_colliders, resolve_collision,
    register_custom_collider, clear_custom_colliders
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
        self.bullet_time_heartbeat_timer = 0.0

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
        """[ESC] 키 입력 처리: 인벤토리 열려있으면 닫기, 테스트 모드면 인트로 복귀, 아니면 마우스 락 토글"""
        if self.game_state == "INVENTORY":
            self.close_inventory()
        elif getattr(self, 'is_test_mode', False):
            self.return_to_intro()
        else:
            self.player.lock_mouse(not self.player.mouse_locked)

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
        self.bullet_time_heartbeat_timer = 0.0
        self.ui_mgr.hide_blackout_warning()
        if hasattr(self.ui_mgr, 'set_bullet_time_hud'):
            self.ui_mgr.set_bullet_time_hud(False)

        # 테스트 모드 활성 상태 정리
        if getattr(self, 'is_test_mode', False):
            self.is_test_mode = False
            if hasattr(self, 'test_room_node') and self.test_room_node and not self.test_room_node.isEmpty():
                self.test_room_node.removeNode()
                self.test_room_node = None
            if hasattr(self, 'test_lights'):
                for l_np in self.test_lights:
                    self.render.clearLight(l_np)
                    l_np.removeNode()
                self.test_lights = []
            clear_custom_colliders()
            self.liminal_fog.setColor(FOG_COLOR)
            self.liminal_fog.setExpDensity(0.038)
            self.setBackgroundColor(FOG_COLOR)
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
            self.is_test_mode = False
            if hasattr(self, 'test_room_node') and self.test_room_node and not self.test_room_node.isEmpty():
                self.test_room_node.removeNode()
                self.test_room_node = None
            if hasattr(self, 'test_lights'):
                for l_np in self.test_lights:
                    self.render.clearLight(l_np)
                    l_np.removeNode()
                self.test_lights = []
            clear_custom_colliders()

        self.game_state = "PLAYING"
        self.restart_game()
        self.combat.vm_root.show()
        self.render.setLight(self.combat.pl_np)
        self.render.setLight(self.combat.fill_np)
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)
        self.audio_mgr.set_bgm_mode("PLAYING")

    def start_test_mode(self):
        """테스트 모드: 넓은 대형 시험장 룸, 4종 전 몬스터가 정지 상태로 대기 (자유 관찰 및 사격 테스트)"""
        self.is_test_mode = True
        self.game_state = "PLAYING"
        self.game_over = False
        self.game_won = False
        self.time_limit = 9999.0
        self.time_left = 9999.0
        self.door_hold_timer = 9999.0
        self.stage_banner_timer = 0.0

        # 기존 발사체, 몬스터, 시체, 청크 완전 정리
        self.clear_projectiles()
        for m in self.monsters:
            m.destroy()
        self.monsters.clear()
        for c in self.corpses:
            c.destroy()
        self.corpses.clear()

        # 청크 비동기 작업 및 기존 미로 청크 파괴
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        for chunk in self.chunks.values():
            chunk.destroy()
        self.chunks.clear()

        # 기존 관문 및 커스텀 충돌체 정리
        clear_custom_colliders()
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
            self.beacon_is_lit = False

        # 플레이어 스탯 및 위치 (사격선 x=0, y=-10, z=1.7)
        self.player.reset_position(0.0, -10.0, heading=0.0, pitch=0.0)
        self.player.level = 1
        self.player.exp = 0
        self.player.exp_to_next = 100
        self.player.pending_perk_picks = 0
        self.player.on_level_up = self._on_player_level_up
        self._is_level_up_modal = False
        self.player.max_hp = 100.0
        self.player.hp = 100.0
        self.player.attack_power = 35.0
        self.player.speed_mult = 1.0

        # 전투 시스템: 모든 무기 넉넉한 탄약 제공
        self.combat.stop_aim()
        self.combat._reserve_ammo = 999
        for w_id in self.combat.weapon_states:
            self.combat.weapon_states[w_id]["ammo"] = self.combat.weapon_states[w_id]["max_ammo"]
            self.combat.weapon_states[w_id]["reserve_ammo"] = 999
            self.combat.weapon_states[w_id]["slide_locked"] = False
        self.combat.ammo = self.combat.max_ammo
        self.combat.reset_state(1, keep_ammo=True)
        self.player.reset_inventory()
        for item in self.player.inventory:
            if item.get("id") == "frag_grenade":
                item['count'] = 50
            else:
                item['count'] = 10
        self._update_quickslot_hud()

        # 대형 테스트 룸 지오메트리 구축 (44m x 44m, 높이 7.5m)
        self._build_test_room()

        # 4종 몬스터 정지 대기 스폰
        self.respawn_test_monsters()

        # UI 활성화 및 테스트 모드 안내
        self.combat.vm_root.show()
        self.render.setLight(self.combat.pl_np)
        self.render.setLight(self.combat.fill_np)
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)
        self.audio_mgr.set_bgm_mode("PLAYING")

        # 상단 안내 배너
        self.ui_mgr.show_stage_banner(
            "[ TEST RANGE : 몬스터 사격 시험장 ]\n"
            "[Z] 권총 | [X] 쌍권총 | [C] 샷건 | [Q/휠] 무기 스왑\n"
            "[F5] 몬스터 재소환 | [1~4] 보급품 사용 | [ESC] 메뉴 복귀",
            color=(0.35, 0.90, 1.0, 1.0)
        )
        self.stage_banner_timer = 6.0

    def _build_test_room(self):
        """테스트 모드 전용 44m x 44m 대형 룸 생성 (바닥, 천장, 4면 벽체, 커스텀 충돌체, 스튜디오 조명)"""
        if hasattr(self, 'test_room_node') and self.test_room_node and not self.test_room_node.isEmpty():
            self.test_room_node.removeNode()

        self.test_room_node = self.world_root.attachNewNode("test_room_node")
        half_w = 22.0
        room_h = 7.5

        # 1. 바닥 (Floor)
        cm_floor = CardMaker('test_floor')
        cm_floor.setFrame(-half_w, half_w, -half_w, half_w)
        floor = self.test_room_node.attachNewNode(cm_floor.generate())
        floor.setP(-90)
        floor.setPos(0, 0, 0)
        floor.setTexture(self.floor_tex)
        floor.setTexScale(TextureStage.getDefault(), 12.0, 12.0)
        floor.setColorScale(0.70, 0.68, 0.62, 1.0)

        # 2. 천장 (Ceiling)
        cm_ceil = CardMaker('test_ceil')
        cm_ceil.setFrame(-half_w, half_w, -half_w, half_w)
        ceil_np = self.test_room_node.attachNewNode(cm_ceil.generate())
        ceil_np.setP(90)
        ceil_np.setPos(0, 0, room_h)
        ceil_np.setTexture(self.floor_tex)
        ceil_np.setTexScale(TextureStage.getDefault(), 12.0, 12.0)
        ceil_np.setColorScale(0.60, 0.58, 0.54, 1.0)
        ceil_np.setTwoSided(True)

        # 3. 4면 외곽 벽체 (Perimeter Walls)
        cm_wall_x = CardMaker('test_wall_x')
        cm_wall_x.setFrame(-half_w, half_w, 0, room_h)

        # 북쪽 벽 (y = half_w)
        wall_n = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_n.setPos(0, half_w, 0)
        wall_n.setH(180)
        wall_n.setTexture(self.wall_tex)
        wall_n.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 남쪽 벽 (y = -half_w)
        wall_s = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_s.setPos(0, -half_w, 0)
        wall_s.setH(0)
        wall_s.setTexture(self.wall_tex)
        wall_s.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 서쪽 벽 (x = -half_w)
        wall_w = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_w.setPos(-half_w, 0, 0)
        wall_w.setH(-90)
        wall_w.setTexture(self.wall_tex)
        wall_w.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 동쪽 벽 (x = half_w)
        wall_e = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_e.setPos(half_w, 0, 0)
        wall_e.setH(90)
        wall_e.setTexture(self.wall_tex)
        wall_e.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 4. 외곽 충돌체 등록 (플레이어가 벽 밖으로 나가지 못하도록 차단)
        register_custom_collider((-half_w - 2.0, half_w - 0.4, half_w + 2.0, half_w + 2.0))
        register_custom_collider((-half_w - 2.0, -half_w - 2.0, half_w + 2.0, -half_w + 0.4))
        register_custom_collider((-half_w - 2.0, -half_w - 2.0, -half_w + 0.4, half_w + 2.0))
        register_custom_collider((half_w - 0.4, -half_w - 2.0, half_w + 2.0, half_w + 2.0))

        # 5. 사격선 바닥 표시선 (Tactical Firing Line)
        cm_line = CardMaker('firing_line')
        cm_line.setFrame(-16.0, 16.0, -0.15, 0.15)
        f_line = self.test_room_node.attachNewNode(cm_line.generate())
        f_line.setP(-90)
        f_line.setPos(0, -9.5, 0.02)
        f_line.setColorScale(0.95, 0.75, 0.15, 0.85)

        # 6. 발밑 전시 패널 (Pedestals - 5개 스탠드)
        for x_pos in [-10.0, -5.0, 0.0, 5.0, 10.0]:
            make_cube_to(self.test_room_node, 3.2, 3.2, 0.10, LColor(0.12, 0.12, 0.14, 1.0), x_pos, 4.0, 0.05)
            make_cube_to(self.test_room_node, 3.3, 0.08, 0.12, LColor(0.92, 0.76, 0.20, 1.0), x_pos, 2.36, 0.06)

        # 7. 스튜디오 조명 배치 (몬스터 세부 디테일을 환하게 비추는 6개의 천장 라이트)
        if hasattr(self, 'test_lights'):
            for l_np in self.test_lights:
                self.render.clearLight(l_np)
                l_np.removeNode()
        self.test_lights = []

        light_positions = [
            (-10.0, 4.0, 5.5),
            (-5.0, 4.0, 5.5),
            (0.0, 4.0, 5.5),
            (5.0, 4.0, 5.5),
            (10.0, 4.0, 5.5),
            (0.0, -8.0, 5.5)
        ]
        for idx, (lx, ly, lz) in enumerate(light_positions):
            pl = PointLight(f"test_light_{idx}")
            pl.setColor((1.4, 1.35, 1.25, 1.0))
            pl.setAttenuation((1.0, 0.04, 0.005))
            pl_np = self.test_room_node.attachNewNode(pl)
            pl_np.setPos(lx, ly, lz)
            self.render.setLight(pl_np)
            self.test_lights.append(pl_np)

        # 8. 안개 완화 (시험장 전체가 또렷하게 보이도록 안개 원거리 조정)
        self.liminal_fog.setColor((0.15, 0.16, 0.18, 1.0))
        self.liminal_fog.setExpDensity(0.003)
        self.setBackgroundColor((0.15, 0.16, 0.18, 1.0))
        self.amb_np.node().setColor((0.25, 0.25, 0.28, 1.0))

    def respawn_test_monsters(self):
        """테스트 모드 5종 몬스터를 스탠드 위치에 정지 상태로 소환/재소환"""
        for m in self.monsters:
            m.destroy()
        self.monsters.clear()
        for c in self.corpses:
            c.destroy()
        self.corpses.clear()

        # 1. 잿더미 마녀 (Alluring Ash Witch)
        witch = AlluringAshWitch(self.world_root, -10.0, 4.0)
        witch.node.setH(180)

        # 2. 장신 해골 괴물 (Tall Skeleton Monster)
        skel = TallSkeletonMonster(self.world_root, -5.0, 4.0)
        skel.node.setH(180)

        # 3. 지옥의 파수견 (Skeletal Doberman Hellhound - 50% 회피 도약)
        hound = SkeletalDobermanHellhound(self.world_root, 0.0, 4.0)
        hound.node.setH(180)

        # 4. 혐오스런 진흙 오크 / 골렘 (Abominable Mud Orc)
        orc = AbominableMudOrc(self.world_root, 5.0, 4.0)
        orc.node.setH(180)

        # 5. 검은 뱀 괴물 / 백골 대사 (Long Black Serpent)
        serp = LongBlackSerpent(self.world_root, 10.0, 4.0)
        serp.node.setH(180)

        self.monsters = [witch, skel, hound, orc, serp]

        # 몬스터별 스폰 좌표 및 리스폰 속성 설정
        for m in self.monsters:
            m._test_spawn_pos = (m.pos.x, m.pos.y)
            m._test_respawn_timer = 3.0

        if hasattr(self, 'ui_mgr') and self.ui_mgr:
            self.ui_mgr.show_hit_marker("[ 몬스터 5종 정지 소환 완료 ]")

    def _on_f5_pressed(self):
        """[F5] 키 입력 시 테스트 모드 몬스터 즉시 재소환"""
        if getattr(self, 'is_test_mode', False):
            self.respawn_test_monsters()

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
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 5분 제한시간
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0
        self.bullet_time_timer = 0.0
        self.bullet_time_heartbeat_timer = 0.0
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
        prev_stage = self.current_stage
        self.current_stage += 1
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0

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
        self.last_cull_pos = None
        self.last_light_cull_pos = None
        self.update_chunks(force=True)
        return new_seed

    def setup_escape_portal(self):
        """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성 (동서남북 4개 사분면 균등 확률 무작위 스폰)"""
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        # 4개 사분면(NE, NW, SE, SW)별 도달 가능한 복도/광장 후보지 수집
        quads = {'NE': [], 'NW': [], 'SE': [], 'SW': []}
        all_cands = []

        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if not cell_has_pillar(gx, gy):
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    d = math.hypot(cx - spawn_x, cy - spawn_y)
                    if 60.0 <= d <= 115.0:
                        all_cands.append((cx, cy))
                        if cx >= spawn_x and cy >= spawn_y:
                            quads['NE'].append((cx, cy))
                        elif cx < spawn_x and cy >= spawn_y:
                            quads['NW'].append((cx, cy))
                        elif cx >= spawn_x and cy < spawn_y:
                            quads['SE'].append((cx, cy))
                        else:
                            quads['SW'].append((cx, cy))

        # 4개 방향(동북, 서북, 동남, 서남) 중 하나를 무작위 선택하여 전방위 균등 분산
        available_quads = [q for q, items in quads.items() if items]
        if available_quads:
            chosen_q = random.choice(available_quads)
            self.escape_pos = random.choice(quads[chosen_q])
        elif all_cands:
            self.escape_pos = random.choice(all_cands)
        else:
            rnd_ang = random.uniform(0, math.pi * 2)
            rnd_d = random.uniform(70.0, 95.0)
            self.escape_pos = (spawn_x + math.cos(rnd_ang) * rnd_d, spawn_y + math.sin(rnd_ang) * rnd_d)

        if hasattr(self, 'escape_portal_np') and self.escape_portal_np:
            self.escape_portal_np.removeNode()

        self.escape_portal_np = self.world_root.attachNewNode("escape_portal")
        self.escape_portal_np.setPos(self.escape_pos[0], self.escape_pos[1], 0)

        dark_metal_frame = LColor(0.12, 0.12, 0.14, 1.0)
        steel_door_plate = LColor(0.24, 0.25, 0.28, 1.0)
        lock_reinforce_col = LColor(0.38, 0.39, 0.43, 1.0)
        hazard_dim_stripe = LColor(0.45, 0.38, 0.12, 1.0)

        half_w = 1.35
        # 벙커 바닥 밀폐 플레이트
        make_cube_to(self.escape_portal_np, 3.0, 3.0, 0.20, dark_metal_frame, 0, 0, 0.10)
        # 벙커 내부 완전 차폐 솔리드 코어 (내부 빈 공간 노출 100% 원천 차단)
        make_cube_to(self.escape_portal_np, 2.70, 2.70, 5.20, LColor(0.08, 0.08, 0.09, 1.0), 0, 0, 2.60)

        for cx_sign in (-1, 1):
            for cy_sign in (-1, 1):
                make_cube_to(self.escape_portal_np, 0.30, 0.30, 5.4, dark_metal_frame, cx_sign * half_w, cy_sign * half_w, 2.7)

        make_cube_to(self.escape_portal_np, 3.0, 3.0, 0.35, dark_metal_frame, 0, 0, 5.4)

        self.door_lamps = []
        for h in (0, 90, 180, 270):
            face_np = self.escape_portal_np.attachNewNode(f"door_face_{h}")
            face_np.setH(h)

            # 상단 인방 및 강철 도어 플레이트: 기둥과 완벽 오버랩(너비 2.70m, 높이 5.20m)으로 틈새 밀폐
            make_cube_to(face_np, 2.70, 0.28, 0.40, dark_metal_frame, 0, half_w, 5.20)
            make_cube_to(face_np, 2.70, 0.16, 5.20, steel_door_plate, 0, half_w, 2.60)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 1.2)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 2.6)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 4.0)
            make_cube_to(face_np, 0.14, 0.22, 0.40, lock_reinforce_col, 0.85, half_w + 0.06, 2.5)
            make_cube_to(face_np, 2.3, 0.18, 0.20, hazard_dim_stripe, 0, half_w + 0.03, 0.30)

            make_cube_to(face_np, 0.40, 0.16, 0.16, dark_metal_frame, 0, half_w + 0.05, 5.5)
            lamp = make_cube_to(face_np, 0.28, 0.08, 0.10, LColor(0.35, 0.25, 0.08, 1.0), 0, half_w + 0.08, 5.5)
            lamp.setLightOff()
            self.door_lamps.append(lamp)

        # 벙커 상단 비상 유도 비콘등 (Emergency Beacon Strobe Light)
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
            self.beacon_light_np.removeNode()

        b_light = PointLight('escape_beacon_light')
        b_light.setColor((0.35, 1.5, 0.55, 1.0))
        b_light.setAttenuation((1.0, 0.05, 0.006))
        self.beacon_light_np = self.escape_portal_np.attachNewNode(b_light)
        self.beacon_light_np.setPos(0, 0, 4.3)
        self.beacon_is_lit = False

        # 비콘 발광 큐브
        beacon_bulb = make_cube_to(self.escape_portal_np, 0.45, 0.45, 0.55, LColor(0.2, 1.0, 0.4, 1.0), 0, 0, 4.3)
        beacon_bulb.setLightOff()
        self.beacon_bulb = beacon_bulb

        # 관문 벙커(3.0m x 3.0m) 견고한 AABB 충돌체 등록 - 플레이어 및 몬스터 통과 완벽 차단
        clear_custom_colliders()
        ex, ey = self.escape_pos[0], self.escape_pos[1]
        register_custom_collider((ex - 1.5, ey - 1.5, ex + 1.5, ey + 1.5))

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
        """이동 거리 임계치(2.0m) 기반 청크 가시거리 컬링 최적화 (안개 한계선 48m 정합)"""
        if getattr(self, 'is_test_mode', False):
            return
        px, py = self.camera.getX(), self.camera.getY()
        if not force and self.last_cull_pos is not None:
            if math.hypot(px - self.last_cull_pos[0], py - self.last_cull_pos[1]) < 2.0:
                return

        self.last_cull_pos = (px, py)
        chunk_rad = (CHUNK_SIZE / 2.0) * math.sqrt(2)
        max_visual_dist = 48.0
        max_dist_sq = (max_visual_dist + chunk_rad) ** 2

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

    def _update_dynamic_lights(self, px, py, dt):
        """
        동적 광원 가시거리 컬링 및 조명 슬롯 버짓 관리 (SimplePBR 8-Light 최적화)
        - 탈출구 비콘, 보급 상자, 탄약 상자, 몬스터 오라 중 플레이어 반경 내 최근접 4개 조명만 엄선 활성화
        - 시야 밖/원거리 조명은 render.clearLight()로 즉시 차단하여 GPU 픽셀 셰이더 루프 부하 0%화
        """
        if getattr(self, 'is_test_mode', False):
            return
        self.light_cull_timer -= dt
        if self.light_cull_timer > 0.0:
            if self.last_light_cull_pos is not None:
                dx = px - self.last_light_cull_pos[0]
                dy = py - self.last_light_cull_pos[1]
                if (dx * dx + dy * dy) < 1.0:
                    return
        self.light_cull_timer = 0.08
        self.last_light_cull_pos = (px, py)

        candidates = []

        # 1. 탈출 관문 비콘등 (최대 유효 반경 42m)
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            ex, ey = getattr(self, 'escape_pos', (0, 0))
            d_sq = (px - ex) ** 2 + (py - ey) ** 2
            if d_sq <= 42.0 * 42.0:
                candidates.append((d_sq, self.beacon_light_np, self.render, self, 'beacon_is_lit'))
            elif getattr(self, 'beacon_is_lit', False):
                self.render.clearLight(self.beacon_light_np)
                self.beacon_is_lit = False

        # 2. 전술 보급 상자 네온등 (최대 유효 반경 25m)
        for cr in self.supply_crates:
            if not getattr(cr, 'is_opened', False) and hasattr(cr, 'beacon_np') and not cr.beacon_np.isEmpty():
                d_sq = (px - cr.pos.x) ** 2 + (py - cr.pos.y) ** 2
                if d_sq <= 25.0 * 25.0:
                    candidates.append((d_sq, cr.beacon_np, self.render, cr, 'beacon_is_lit'))
                elif getattr(cr, 'beacon_is_lit', False):
                    self.render.clearLight(cr.beacon_np)
                    cr.beacon_is_lit = False

        # 3. 필드 탄약 드롭 발광 (최대 유효 반경 18m)
        if hasattr(self, 'combat') and hasattr(self.combat, 'ammo_drops'):
            for drop in self.combat.ammo_drops:
                l_np = drop.get("light_np")
                if l_np and not l_np.isEmpty():
                    dx = px - drop["pos"][0]
                    dy = py - drop["pos"][1]
                    d_sq = dx * dx + dy * dy
                    if d_sq <= 18.0 * 18.0:
                        candidates.append((d_sq, l_np, self.render, drop, 'is_lit'))
                    elif drop.get("is_lit", False):
                        self.render.clearLight(l_np)
                        drop["is_lit"] = False

        # 3-2. 필드 전술 전리품 드랍 아이템 발광 (최대 유효 반경 20m)
        for drop in getattr(self, 'item_drops', []):
            if not getattr(drop, 'is_collected', False) and hasattr(drop, 'beacon_np') and not drop.beacon_np.isEmpty():
                d_sq = (px - drop.pos.x) ** 2 + (py - drop.pos.y) ** 2
                if d_sq <= 20.0 * 20.0:
                    candidates.append((d_sq, drop.beacon_np, self.render, drop, 'is_lit'))
                elif getattr(drop, 'is_lit', False):
                    self.render.clearLight(drop.beacon_np)
                    drop.is_lit = False

        # 4. 활성 몬스터 고유 오라 조명 (최대 유효 반경 22m)
        for m in self.monsters:
            if not getattr(m, 'is_corpse', False) and hasattr(m, 'aura_np') and not m.aura_np.isEmpty():
                d_sq = (px - m.pos.x) ** 2 + (py - m.pos.y) ** 2
                if d_sq <= 22.0 * 22.0:
                    candidates.append((d_sq, m.aura_np, self.render, m, 'aura_is_lit'))
                elif getattr(m, 'aura_is_lit', False):
                    self.render.clearLight(m.aura_np)
                    m.aura_is_lit = False

        # 거리순 정렬 후 최상위 4개 조명만 엄선
        candidates.sort(key=lambda item: item[0])
        for idx, (d_sq, l_np, parent_node, obj, lit_attr) in enumerate(candidates):
            if idx < 4:
                if not (obj[lit_attr] if isinstance(obj, dict) else getattr(obj, lit_attr, False)):
                    parent_node.setLight(l_np)
                    if isinstance(obj, dict):
                        obj[lit_attr] = True
                    else:
                        setattr(obj, lit_attr, True)
            else:
                if (obj[lit_attr] if isinstance(obj, dict) else getattr(obj, lit_attr, False)):
                    parent_node.clearLight(l_np)
                    if isinstance(obj, dict):
                        obj[lit_attr] = False
                    else:
                        setattr(obj, lit_attr, False)

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
        if getattr(self, 'is_test_mode', False):
            # 테스트 모드: AI 이동/추적/공격 원천 차단, 정지 유휴(Idle) 애니메이션 및 리스폰만 처리
            # 탄약 자동 보충
            if self.combat.reserve_ammo < 60:
                self.combat.reserve_ammo = 999
                self.ui_mgr.update_ammo(self.combat.ammo, self.combat.max_ammo, self.combat.reserve_ammo)
            self.player.hp = self.player.max_hp

            if self.boss and getattr(self.boss, 'hp', 0) > 0 and self.boss in self.monsters:
                if hasattr(self.ui_mgr, 'update_boss_hp'):
                    self.ui_mgr.update_boss_hp(self.boss.hp, self.boss.max_hp, self.boss.phase)

            for m in self.monsters[:]:
                if getattr(m, 'hp', 1) <= 0:
                    m._test_respawn_timer = 3.0
                    if isinstance(m, CableOverlordBoss) and hasattr(self.ui_mgr, 'hide_boss_hp_bar'):
                        self.ui_mgr.hide_boss_hp_bar()
                    if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                        if hasattr(m, 'elite_light_np') and m.elite_light_np and not m.elite_light_np.isEmpty():
                            self.render.clearLight(m.elite_light_np)
                            m.elite_light_np.removeNode()
                            m.elite_light_np = None
                        m.turn_into_corpse(audio_mgr=self.audio_mgr)
                        drop = maybe_drop_monster_loot(self.world_root, m.pos.x, m.pos.y, m, self.audio_mgr)
                        if drop:
                            self.item_drops.append(drop)
                    self.monsters.remove(m)
                    self.corpses.append(m)
                    continue

                # 정지 상태 유휴 애니메이션 갱신 (제자리 정지, 자연스러운 숨쉬기/혀날름/부유)
                m.update(dt, is_moving=False, is_attacking=False)

            # 사망한 몬스터 파편 물리 갱신 및 3초 후 자동 리스폰
            for c in self.corpses[:]:
                if hasattr(c, 'update_debris'):
                    c.update_debris(dt)
                c._test_respawn_timer = getattr(c, '_test_respawn_timer', 3.0) - dt
                if c._test_respawn_timer <= 0.0:
                    spawn_x, spawn_y = getattr(c, '_test_spawn_pos', (0.0, 4.0))
                    if isinstance(c, AlluringAshWitch):
                        new_m = AlluringAshWitch(self.world_root, spawn_x, spawn_y)
                    elif isinstance(c, TallSkeletonMonster):
                        new_m = TallSkeletonMonster(self.world_root, spawn_x, spawn_y)
                    elif isinstance(c, AbominableMudOrc):
                        new_m = AbominableMudOrc(self.world_root, spawn_x, spawn_y)
                    elif isinstance(c, LongBlackSerpent):
                        new_m = LongBlackSerpent(self.world_root, spawn_x, spawn_y)
                    else:
                        new_m = None

                    if new_m:
                        new_m.node.setH(180)
                        new_m._test_spawn_pos = (spawn_x, spawn_y)
                        new_m._test_respawn_timer = 3.0
                        self.monsters.append(new_m)

                    if hasattr(c, 'destroy'):
                        c.destroy()
                    if c in self.corpses:
                        self.corpses.remove(c)

            return False, 999.0

        closest_dist = 999.0
        self.frame_count = getattr(self, 'frame_count', 0) + 1
        stage_mult = 1.0 + (self.current_stage - 1) * 0.15
        if self.blackout_active:
            stage_mult *= 1.25  # 정전 프로토콜: 몬스터 이동속도 25% 가속 (폭주 상태)

        # 관문 거리 계산 및 관문 접근 시 몬스터 가속 / 긴급 증원 트리거
        ex, ey = getattr(self, 'escape_pos', (px + 100, py + 100))
        dist_gate = math.hypot(px - ex, py - ey)

        # [관문 접근 가속] 관문 근처로 갈수록 몬스터들의 이동 속도 대폭 증가 (최대 +45% 가속)
        if dist_gate <= 50.0:
            prox_factor = max(0.0, min(1.0, (50.0 - dist_gate) / 50.0))
            stage_mult *= (1.0 + prox_factor * 0.45)

        # [관문 접근 1단계 경보 (45m 이내)] 몬스터 집결 및 2마리 즉시 증원
        if dist_gate <= 45.0 and getattr(self, 'gate_alarm_level', 0) < 1:
            self.gate_alarm_level = 1
            self.audio_mgr.play_door_alarm()
            self.ui_mgr.show_stage_banner("[ ! 경고: 탈출 관문 구역 접근 감지 ! ]\n주변 괴물들이 탈출구를 봉쇄하기 위해 몰려옵니다!", color=(1.0, 0.65, 0.1, 1.0))
            self.stage_banner_timer = 3.0
            for _ in range(2):
                self.spawn_reinforcement_monster(near_gate=True)

        # [관문 접근 2단계 경보 (25m 이내)] 대규모 긴급 증원 (3마리 추가 급습)
        if dist_gate <= 25.0 and getattr(self, 'gate_alarm_level', 0) < 2:
            self.gate_alarm_level = 2
            self.audio_mgr.play_door_alarm()
            self.ui_mgr.show_stage_banner("[ ! 비상: 관문 수호 방어선 진입 ! ]\n대규모 괴물 무리가 총공격을 시작합니다!", color=(1.0, 0.2, 0.2, 1.0))
            self.stage_banner_timer = 3.5
            for _ in range(3):
                self.spawn_reinforcement_monster(near_gate=True)

        # [관문 주변 지속 유입] 관문 32m 이내에 머무는 동안 4초마다 괴물 지속 보충
        if dist_gate <= 32.0:
            self.gate_reinforce_timer = getattr(self, 'gate_reinforce_timer', 0.0) + dt
            if self.gate_reinforce_timer >= 4.0:
                self.gate_reinforce_timer = 0.0
                if len(self.monsters) < 16:
                    self.spawn_reinforcement_monster(near_gate=True)

        # [Stage 3: 심연의 지배자 보스 출현] 3스테이지 이상에서 관문 38m 접근 시 보스 각성
        if self.current_stage >= 3 and not self.boss_spawned and dist_gate <= 38.0:
            self.spawn_boss()

        for m in self.monsters[:]:
            if getattr(m, 'hp', 1) <= 0:
                # 보스 격파 시 특별 연출 및 보상
                if isinstance(m, CableOverlordBoss) and not self.boss_defeat_handled:
                    self.boss_defeat_handled = True
                    if hasattr(self.ui_mgr, 'hide_boss_hp_bar'):
                        self.ui_mgr.hide_boss_hp_bar()
                    self.trigger_bullet_time(4.0)
                    self.ui_mgr.show_stage_banner(
                        "[ ★ BOSS DEFEATED ★ ]\n심연의 지배자 격파 성공!\n탈출 관문 보안 락이 영구 해제되었습니다!",
                        color=(0.2, 1.0, 0.4, 1.0)
                    )
                    self.stage_banner_timer = 5.0
                    self.player.add_exp(800, self.combat, self.ui_mgr, self)
                    for ox, oy in [(-1.5, 0.0), (1.5, 0.0), (0.0, 1.5)]:
                        dp = maybe_drop_monster_loot(self.world_root, m.pos.x + ox, m.pos.y + oy, m, self.audio_mgr)
                        if dp:
                            self.item_drops.append(dp)

                # 사망한 몬스터: 시체로 전환하고 활성 몬스터 목록에서 제외하여 시체 목록으로 이전
                if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                    if hasattr(m, 'elite_light_np') and m.elite_light_np and not m.elite_light_np.isEmpty():
                        self.render.clearLight(m.elite_light_np)
                        m.elite_light_np.removeNode()
                        m.elite_light_np = None
                    m.turn_into_corpse(audio_mgr=self.audio_mgr)
                    if not isinstance(m, CableOverlordBoss):
                        drop = maybe_drop_monster_loot(self.world_root, m.pos.x, m.pos.y, m, self.audio_mgr)
                        if drop:
                            self.item_drops.append(drop)
                self.monsters.remove(m)
                self.corpses.append(m)
                # 관문 근처에서 처치 시 후방에서 빠르게 추가 증원
                if dist_gate <= 35.0 and len(self.monsters) < 14 and not isinstance(m, CableOverlordBoss):
                    if random.random() < 0.65:
                        self.spawn_reinforcement_monster(near_gate=True)
                continue

            mx, my = m.pos.x, m.pos.y
            dist = math.hypot(px - mx, py - my)
            if dist < closest_dist:
                closest_dist = dist

            # 몬스터 고유 틱 오프셋 및 누적 dt 초기화
            if not hasattr(m, '_tick_id'):
                m._tick_id = id(m) % 6
                m._accum_dt = 0.0

            # --- CPU 몬스터 틱 인터리빙 (거리 기반 갱신 주기 분산) ---
            # 1) 근거리 (<= 14.0m), 보스 또는 특수 상태(시전/공격/스턴): 매 프레임(60fps) 100% 즉각 갱신
            # 2) 중거리 (14.0m < dist <= 26.0m): 2프레임에 1회(30fps) 교대 갱신
            # 3) 원거리 (> 26.0m): 3프레임에 1회(20fps) 교대 갱신
            is_critical = (dist <= 14.0 or isinstance(m, CableOverlordBoss) or getattr(m, 'is_casting', False) or getattr(m, 'is_slamming', False) or getattr(m, 'is_striking', False) or getattr(m, 'is_lashing', False) or m.stun_timer > 0.0)
            if not is_critical:
                skip_frame = False
                if dist <= 26.0:
                    if (self.frame_count + m._tick_id) % 2 != 0:
                        skip_frame = True
                else:
                    if (self.frame_count + m._tick_id) % 3 != 0:
                        skip_frame = True

                if skip_frame:
                    m._accum_dt += dt
                    continue

            eff_dt = dt + getattr(m, '_accum_dt', 0.0)
            m._accum_dt = 0.0

            # 0. 파수견 회피 기동 중 벽체 충돌 해결
            if getattr(m, 'is_dodging', False):
                m.update(eff_dt, is_moving=False, chunks=self.chunks)
                continue

            # 1. 일반 근접 공격 판정 (해골, 오크, 파수견) - 보스와 뱀은 고유 공격 사용
            if not isinstance(m, (LongBlackSerpent, CableOverlordBoss)):
                attack_range = 1.95 if isinstance(m, (TallSkeletonMonster, AbominableMudOrc)) else (1.75 if isinstance(m, SkeletalDobermanHellhound) else 1.45)
                if dist <= attack_range and m.stun_timer <= 0.0:
                    is_dead = self.player.take_damage(m.attack_damage, source_pos=(mx, my))
                    m.update(eff_dt, is_moving=False, is_attacking=True)
                    if is_dead:
                        self.trigger_game_over(killer=m, reason="killed")
                        return True, closest_dist
                    continue

            # 2. 스턴 상태 처리
            if m.stun_timer > 0.0:
                m.update_pos(mx, my, eff_dt, 0, 0)
                continue

            # 3-A. 진흙 오크: 땅을 울려서 플레이어 이동방해 (Ground Slam)
            if isinstance(m, AbominableMudOrc):
                m.slam_cooldown -= eff_dt
                if dist <= 12.0 and m.slam_cooldown <= 0.0 and not m.is_slamming and m.stun_timer <= 0.0:
                    m.is_slamming = True
                    m.slam_timer = 0.0
                    m.slam_has_impacted = False
                    m.slam_cooldown = 5.5

                if m.is_slamming:
                    impact = m.slam_ground(eff_dt)
                    if impact:
                        self.shockwaves.append(GroundShockwave(self.render, mx, my))
                        self.audio_mgr.play_orc_slam()
                        if dist <= 11.5:
                            self.player.apply_slow(duration=2.8, factor=0.40)
                            self.player.trigger_quake_shake(intensity=2.6, duration=0.85)
                    continue

            # 3-B. 거대 흑사(뱀): 몸 상부를 2.25m 치켜세워 코브라처럼 기립 후 전방 급습 강타 (Rearing Strike)
            if isinstance(m, LongBlackSerpent):
                m.strike_cooldown -= eff_dt
                if dist <= 3.8 and m.strike_cooldown <= 0.0 and not m.is_striking and m.stun_timer <= 0.0:
                    m.is_striking = True
                    m.strike_timer = 0.0
                    m.strike_has_hit = False
                    m.strike_cooldown = 2.4
                    if hasattr(self, 'audio_mgr') and self.audio_mgr:
                        self.audio_mgr.play_monster_3d("serp_hiss", m.node, volume_scale=1.15)

                if m.is_striking:
                    # 공격 중 플레이어를 정면 응시하며 상체 기립 급습 애니메이션 갱신
                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)

                    impact = m.strike_attack(eff_dt)
                    if impact:
                        if dist <= 4.2:
                            is_dead = self.player.take_damage(m.attack_damage, source_pos=(mx, my))
                            self.player.trigger_quake_shake(intensity=2.2, duration=0.40)
                            if is_dead:
                                self.trigger_game_over(killer=m, reason="killed")
                                return True, closest_dist
                    continue

            # 3-C. 심연의 지배자 (케이블 엔티티 보스) 2페이즈 전투 패턴 & 스킬 시전
            if isinstance(m, CableOverlordBoss):
                # UI 보스 체력바 실시간 동기화
                if hasattr(self.ui_mgr, 'update_boss_hp'):
                    self.ui_mgr.update_boss_hp(m.hp, m.max_hp, m.phase)

                # 2페이즈 전환 (체력 50% 이하 시 폭주 및 적색 발광)
                if m.hp <= m.max_hp * 0.5 and m.phase == 1:
                    m.phase = 2
                    m.speed = 6.2
                    self.ui_mgr.show_stage_banner(
                        "[ ! 경고: 심연의 지배자 2페이즈 폭주 돌입 ! ]\n심연의 코어가 적색으로 과부하되며 이동 속도 및 공격 빈도가 급증합니다!",
                        color=(1.0, 0.15, 0.15, 1.0)
                    )
                    self.stage_banner_timer = 3.5
                    if hasattr(self, 'audio_mgr') and self.audio_mgr:
                        self.audio_mgr.play_siren_alarm()
                    for _ in range(2):
                        self.spawn_reinforcement_monster(near_gate=True)

                # 1) 케이블 채찍 근접 강타 (Cable Lash, dist <= 5.8m)
                if dist <= 5.8 and m.cable_lash_cooldown <= 0.0 and not m.is_lashing and m.stun_timer <= 0.0:
                    m.is_lashing = True
                    m.lash_timer = 0.65
                    m.cable_lash_cooldown = 1.6 if m.phase == 2 else 2.5
                    is_dead = self.player.take_damage(38 if m.phase == 2 else 28, source_pos=(mx, my))
                    if hasattr(self, 'audio_mgr') and self.audio_mgr:
                        self.audio_mgr.play_monster_3d("serp_slither", m.node, volume_scale=1.4)
                    self.ui_mgr.show_hit_marker("보스 케이블 채찍 강타 피격!", (1.0, 0.2, 0.2, 1.0))
                    if is_dead:
                        self.trigger_game_over(killer=m, reason="killed")
                        return True, closest_dist

                # 2) 전방위 고전압 지진 충격파 (Ground Shockwave, dist <= 18m)
                if dist <= 18.0 and m.shockwave_cooldown <= 0.0 and m.stun_timer <= 0.0:
                    m.shockwave_cooldown = 4.2 if m.phase == 2 else 6.2
                    self.shockwaves.append(GroundShockwave(self.render, mx, my))
                    if hasattr(self, 'audio_mgr') and self.audio_mgr:
                        self.audio_mgr.play_orc_slam()
                    self.player.trigger_quake_shake(intensity=3.2, duration=1.0)
                    if dist <= 11.0:
                        self.player.take_damage(20, source_pos=(mx, my))
                        self.player.apply_slow(duration=2.5, factor=0.45)
                        self.ui_mgr.show_hit_marker("보스 지진 충격파 피격! (이동속도 저하)", (1.0, 0.45, 0.1, 1.0))

                # 3) 고압 와이어 다트 일제 투척 (Wire Darts, dist <= 32m)
                if dist <= 32.0 and m.dart_cooldown <= 0.0 and m.stun_timer <= 0.0:
                    m.dart_cooldown = 3.2 if m.phase == 2 else 5.2
                    if hasattr(self, 'audio_mgr') and self.audio_mgr:
                        self.audio_mgr.play_witch_cast()
                    start_pos = (mx, my, 2.8)
                    for spread_deg in (-14, 0, 14):
                        base_rad = math.atan2(py - my, px - mx) + math.radians(spread_deg)
                        target_p = (mx + math.cos(base_rad) * 22.0, my + math.sin(base_rad) * 22.0, PLAYER_EYE_HEIGHT)
                        self.spawn_fireball(start_pos, target_p)
                    self.ui_mgr.show_hit_marker("보스 고압 와이어 다트 사격!", (0.3, 0.9, 1.0, 1.0))

                # 4) 2페이즈 심연의 괴물 소환 (Minion Summon)
                if m.phase == 2 and getattr(m, 'summon_cooldown', 0.0) <= 0.0:
                    m.summon_cooldown = 14.0
                    if len(self.monsters) < 16:
                        for _ in range(2):
                            self.spawn_reinforcement_monster(near_gate=True)
                        self.ui_mgr.show_stage_banner("[ ! 보스 증원 소환 ! ]\n심연의 괴물들이 소환되었습니다!", color=(1.0, 0.3, 0.1, 1.0))
                        self.stage_banner_timer = 2.5

            # 4. 시선 검사 (Line of Sight)
            has_los = False
            if dist <= 28.0:
                mid_x, mid_y = (mx + px) * 0.5, (my + py) * 0.5
                cols = get_nearby_colliders(self.chunks, mid_x, mid_y, dist * 0.5 + 1.2)
                has_los = check_line_of_sight(mx, my, px, py, cols)

            # 5. 잿더미 마녀: 파이어볼 투척 (Fireball Cast)
            if isinstance(m, AlluringAshWitch):
                m.cast_cooldown -= eff_dt
                if has_los and dist <= 24.0 and m.cast_cooldown <= 0.0 and not m.is_casting and m.stun_timer <= 0.0:
                    m.is_casting = True
                    m.cast_timer = 0.0
                    m._fireball_fired = False
                    m.cast_cooldown = 3.2

                if m.is_casting:
                    fire = m.cast_fireball(eff_dt)
                    if fire:
                        orb_pos = (mx, my, m.pos.z + 1.5)
                        target_pos = (px, py, PLAYER_EYE_HEIGHT)
                        self.spawn_fireball(orb_pos, target_pos)
                        self.audio_mgr.play_witch_fireball()

                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)
                    continue

            # 6. 지능형 길찾기 및 장애물/기둥 회피 (Intelligent Pathfinding & Pillar Bypass)
            mgx = int(math.floor(mx / CELL_SIZE))
            mgy = int(math.floor(my / CELL_SIZE))
            pgx = int(math.floor(px / CELL_SIZE))
            pgy = int(math.floor(py / CELL_SIZE))

            stuck_timer = getattr(m, '_stuck_timer', 0.0)
            m.path_timer -= eff_dt

            in_same_cell = (mgx, mgy) == (pgx, pgy)

            # 플레이어 직접 돌진 판정: 동일 셀에 있거나, 근거리(<= 4.0m)에서 직선 시야가 명확히 확보된 경우에만 직접 추격
            can_direct_charge = False
            if in_same_cell:
                can_direct_charge = True
            elif dist <= 4.0 and has_los and stuck_timer <= 0.05:
                can_direct_charge = True

            if can_direct_charge:
                tx, ty = px, py
                m.path = []
            else:
                needs_repath = False
                if not m.path or m.path_timer <= 0.0 or stuck_timer > 0.18:
                    needs_repath = True
                elif len(m.path) > 0 and (mgx, mgy) != m.path[0]:
                    if len(m.path) > 1 and (mgx, mgy) == m.path[1]:
                        m.path.pop(0)
                    else:
                        needs_repath = True

                if needs_repath:
                    interval = 0.20 + random.random() * 0.08 if dist_gate <= 35.0 else 0.35 + random.random() * 0.10
                    m.path_timer = interval
                    m.path = find_cell_path((mgx, mgy), (pgx, pgy), max_depth=32)
                    if len(m.path) > 1 and m.path[0] == (mgx, mgy):
                        pass
                    elif not m.path:
                        tx, ty = (pgx + 0.5) * CELL_SIZE, (pgy + 0.5) * CELL_SIZE

                if len(m.path) >= 2:
                    c1 = m.path[0]
                    c2 = m.path[1]

                    # 중앙 지지 기둥 회피 라우팅 (Pillar Bypass Routing)
                    if cell_has_pillar(c1[0], c1[1]):
                        pil_x = (c1[0] + 0.5) * CELL_SIZE
                        pil_y = (c1[1] + 0.5) * CELL_SIZE
                        if c2[1] != c1[1]:
                            offset_x = 1.8 if mx >= pil_x else -1.8
                            if (c2[1] > c1[1] and my < pil_y + 1.2) or (c2[1] < c1[1] and my > pil_y - 1.2):
                                tx = pil_x + offset_x
                                ty = pil_y
                            else:
                                tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                                ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                        elif c2[0] != c1[0]:
                            offset_y = 1.8 if my >= pil_y else -1.8
                            if (c2[0] > c1[0] and mx < pil_x + 1.2) or (c2[0] < c1[0] and mx > pil_x - 1.2):
                                tx = pil_x
                                ty = pil_y + offset_y
                            else:
                                tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                                ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                        else:
                            tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                            ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                    else:
                        tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                        ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE

                    # 출입문/웨이포인트 통과 감지
                    if math.hypot(mx - tx, my - ty) < 0.7:
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
                step_dist = speed * eff_dt

                # 1차 시도: 목표 방향 이동
                best_nx, best_ny = resolve_collision(self.chunks, mx, my, ndx * step_dist, ndy * step_dist, radius=col_radius)
                actual_move = math.hypot(best_nx - mx, best_ny - my)

                # 2차 시도: 벽체/문틀 모서리 저지 시 다각도 접선 슬라이딩 탐색 (Tangential Sliding)
                if actual_move < 0.35 * step_dist:
                    base_angle = math.atan2(ndy, ndx)
                    best_progress = actual_move

                    probes = [
                        (ndx * step_dist, 0.0),
                        (0.0, ndy * step_dist),
                    ]
                    for ang_deg in (35, -35, 55, -55, 75, -75, 90, -90):
                        rad = base_angle + math.radians(ang_deg)
                        probes.append((math.cos(rad) * step_dist, math.sin(rad) * step_dist))

                    for pdx, pdy in probes:
                        cand_nx, cand_ny = resolve_collision(self.chunks, mx, my, pdx, pdy, radius=col_radius)
                        c_move = math.hypot(cand_nx - mx, cand_ny - my)
                        if c_move > 0.45 * step_dist:
                            dist_to_target = math.hypot(cand_nx - tx, cand_ny - ty)
                            orig_dist_to_target = math.hypot(mx - tx, my - ty)
                            progress = (orig_dist_to_target - dist_to_target) + c_move * 0.3
                            if progress > best_progress:
                                best_progress = progress
                                best_nx, best_ny = cand_nx, cand_ny

                # 3차 시도: 미세 끼임 발생 시 셀 중앙 방향 탈출 추진력 부여 (Active Unstuck Recovery)
                final_move = math.hypot(best_nx - mx, best_ny - my)
                if final_move < 0.01:
                    m._stuck_timer = stuck_timer + eff_dt
                    if m._stuck_timer > 0.20:
                        center_x = (mgx + 0.5) * CELL_SIZE
                        center_y = (mgy + 0.5) * CELL_SIZE
                        cdx = center_x - mx
                        cdy = center_y - my
                        cd = math.hypot(cdx, cdy)
                        if cd > 0.1:
                            esc_x, esc_y = resolve_collision(self.chunks, mx, my, (cdx / cd) * step_dist, (cdy / cd) * step_dist, radius=col_radius)
                            best_nx, best_ny = esc_x, esc_y
                        m.path = []
                else:
                    m._stuck_timer = max(0.0, stuck_timer - eff_dt * 2.0)

                face_dx = best_nx - mx
                face_dy = best_ny - my
                if math.hypot(face_dx, face_dy) > 0.001:
                    m.update_pos(best_nx, best_ny, eff_dt, face_dx, face_dy)
                else:
                    m.update_pos(best_nx, best_ny, eff_dt, ndx, ndy)
            else:
                m.update(eff_dt, is_moving=False)
                m._stuck_timer = 0.0

            # 7. 3D 입체 접근 사운드 (발소리 & 괴성/숨소리 360도 공간 음향)
            if dist <= 32.0 and not getattr(m, 'is_corpse', False) and hasattr(self, 'audio_mgr') and self.audio_mgr:
                # A. 3D 보행/슬리더 이동 발소리 (이동 중일 때 3D 위치에서 재생)
                m._step_timer = getattr(m, '_step_timer', random.uniform(0.05, 0.25)) - eff_dt
                if d > 0.05 and m._step_timer <= 0.0:
                    if isinstance(m, AbominableMudOrc):
                        self.audio_mgr.play_monster_3d("orc_step", m.node, volume_scale=random.uniform(0.85, 1.0))
                        m._step_timer = 0.38 + random.uniform(-0.04, 0.04)
                    elif isinstance(m, TallSkeletonMonster):
                        self.audio_mgr.play_monster_3d("skel_step", m.node, volume_scale=random.uniform(0.75, 0.95))
                        m._step_timer = 0.34 + random.uniform(-0.03, 0.03)
                    elif isinstance(m, LongBlackSerpent):
                        self.audio_mgr.play_monster_3d("serp_slither", m.node, volume_scale=random.uniform(0.80, 0.95))
                        m._step_timer = 0.44 + random.uniform(-0.04, 0.04)
                    elif isinstance(m, SkeletalDobermanHellhound):
                        self.audio_mgr.play_monster_3d("hound_step", m.node, volume_scale=random.uniform(0.70, 0.90))
                        m._step_timer = 0.22 + random.uniform(-0.03, 0.03)

                # B. 3D 접근 위협 괴성 / 포효 / 속삭임 공간 오디오 큐
                m._vocal_timer = getattr(m, '_vocal_timer', random.uniform(1.0, 3.5)) - eff_dt
                if m._vocal_timer <= 0.0:
                    if isinstance(m, AbominableMudOrc):
                        self.audio_mgr.play_monster_3d("orc_growl", m.node, volume_scale=random.uniform(0.90, 1.10))
                        m._vocal_timer = random.uniform(3.2, 5.5)
                    elif isinstance(m, TallSkeletonMonster):
                        self.audio_mgr.play_monster_3d("skel_groan", m.node, volume_scale=random.uniform(0.85, 1.05))
                        m._vocal_timer = random.uniform(3.5, 6.0)
                    elif isinstance(m, LongBlackSerpent):
                        self.audio_mgr.play_monster_3d("serp_hiss", m.node, volume_scale=random.uniform(0.90, 1.10))
                        m._vocal_timer = random.uniform(3.0, 5.0)
                    elif isinstance(m, AlluringAshWitch):
                        self.audio_mgr.play_monster_3d("witch_whisper", m.node, volume_scale=random.uniform(0.85, 1.05))
                        m._vocal_timer = random.uniform(3.4, 5.8)
                    elif isinstance(m, SkeletalDobermanHellhound):
                        self.audio_mgr.play_monster_3d("hound_growl", m.node, volume_scale=random.uniform(0.90, 1.15))
                        m._vocal_timer = random.uniform(2.8, 4.8)

        # 사망한 몬스터들의 비산 파편 물리 및 폭발 섬광 조명 갱신
        for c in self.corpses[:]:
            if hasattr(c, 'update_debris'):
                c.update_debris(dt)
            # 파편 및 섬광이 완전히 소멸된 시체는 메모리 해제 및 목록에서 정리
            has_debris = hasattr(c, 'debris_list') and len(c.debris_list) > 0
            has_blast = hasattr(c, 'blast_light_np') and c.blast_light_np is not None
            if not has_debris and not has_blast:
                if hasattr(c, 'destroy'):
                    c.destroy()
                if c in self.corpses:
                    self.corpses.remove(c)

        # 활성 시체 상한 관리 (최대 6구 초과 시 가장 오래된 시체 즉시 정리)
        while len(self.corpses) > 6:
            oldest = self.corpses.pop(0)
            if hasattr(oldest, 'destroy'):
                oldest.destroy()

        return False, closest_dist

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
            cols = get_nearby_colliders(self.chunks, fb.pos.x, fb.pos.y, search_dist=0.6)
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
        """탈출 관문 앞 3.8m 방어 판정 (관문 외벽에서 5초 사수 시 상점 모달 팝업)"""
        dist_exit = math.hypot(px - self.escape_pos[0], py - self.escape_pos[1])
        if dist_exit <= 3.8:
            # 3스테이지 이상인 경우 보스 [케이블 엔티티: 심연의 지배자] 격파 필수
            if self.current_stage >= 3:
                if not self.boss_spawned:
                    self.spawn_boss()
                if self.boss and getattr(self.boss, 'hp', 0) > 0 and self.boss in self.monsters:
                    self.ui_mgr.update_door_status(
                        f"[ 관문 비상 봉쇄: 심연의 지배자를 먼저 격파하십시오! ]\n보스 체력: {int(self.boss.hp)} / {int(self.boss.max_hp)}",
                        fg=(1.0, 0.25, 0.25, 1.0)
                    )
                    return False

            old_timer = self.door_hold_timer
            self.door_hold_timer -= dt
            progress_sec = 5.0 - max(0.0, self.door_hold_timer)

            # 매 1초마다 전자 보안 비프음 재생
            if int(progress_sec) != int(5.0 - max(0.0, old_timer)):
                self.audio_mgr.play_door_alarm()

            # 관문 개방 시도 중 괴물 긴급 유입 (2.0초마다 추가 괴물 증원)
            self.door_defense_spawn_timer = getattr(self, 'door_defense_spawn_timer', 0.0) + dt
            if self.door_defense_spawn_timer >= 2.0:
                self.door_defense_spawn_timer = 0.0
                if len(self.monsters) < 18:
                    self.spawn_reinforcement_monster(near_gate=True)

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
                self.audio_mgr.play_door_unlock()
                self.door_hold_timer = 5.0
                # 던전 크롤러: 스탯 분배 및 상점 모달 팝업 & 다음 스테이지 준비
                self.game_state = "SHOP"
                self.player.lock_mouse(False)
                self.combat.stop_aim()
                self.ui_mgr.show_stage_clear_shop(
                    self.current_stage, self.player, self.combat,
                    self.on_shop_closed, on_victory_callback=self.trigger_victory
                )
                return True
            else:
                msg = f"[ 비상문 개방 중: {progress_sec:.1f}s / 5.0s  [{bar_str}] ]\n[ 경고: 문이 열릴 때까지 쏟아지는 괴물의 접근을 저지하세요! ]"
                self.ui_mgr.update_door_status(msg, fg=(1.0, 0.85, 0.2, 1.0))
        else:
            if self.door_hold_timer < 5.0:
                self.door_hold_timer = 5.0
                idle_col = LColor(0.35, 0.25, 0.08, 1.0)
                for lamp in self.door_lamps:
                    lamp.setColor(idle_col)
                self.ui_mgr.update_door_status("[ 비상문 개방 중단! 탈출 관문 앞을 사수하세요! ]", fg=(1.0, 0.3, 0.3, 1.0))
            else:
                self.ui_mgr.update_door_status("", show=False)
        return False

    # --- 메인 틱 루프 (Main Update Loop) ---
    def update(self, task):
        raw_dt = min(0.1, globalClock.getDt())
        cont = task.cont if task is not None else 1

        # 0. 불릿 타임 (시간 감속) 연산: 몬스터 및 월드 발사체 속도를 0.35x로 감속 (플레이어는 실시간 유지)
        if self.bullet_time_timer > 0.0:
            self.bullet_time_timer = max(0.0, self.bullet_time_timer - raw_dt)
            world_dt = raw_dt * 0.35
            self.ui_mgr.set_bullet_time_hud(True, self.bullet_time_timer)
            self.bullet_time_heartbeat_timer -= raw_dt
            if self.bullet_time_heartbeat_timer <= 0.0:
                self.bullet_time_heartbeat_timer = 0.72
                if hasattr(self, 'audio_mgr') and self.audio_mgr:
                    if hasattr(self.audio_mgr, 'play_bullet_time_pulse'):
                        self.audio_mgr.play_bullet_time_pulse()
                    else:
                        self.audio_mgr.play_heartbeat()
            if self.bullet_time_timer <= 0.0:
                if hasattr(self, 'audio_mgr') and self.audio_mgr:
                    self.audio_mgr.play_bullet_time(is_start=False)
                self.ui_mgr.set_bullet_time_hud(False)
        else:
            world_dt = raw_dt
            self.bullet_time_heartbeat_timer = 0.0

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

        # 2. 상점 및 인벤토리 모달 상태 시 업데이트 정지
        if self.game_state in ("SHOP", "INVENTORY"):
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
        game_ended, closest_dist = self._update_monsters(world_dt, px, py)
        if game_ended:
            return cont

        # 6-1. 마녀 파이어볼 및 진흙오크 충격파 갱신 (불릿 타임 시 0.35x world_dt 적용)
        if not getattr(self, 'is_test_mode', False):
            if self._update_projectiles(world_dt, px, py, PLAYER_EYE_HEIGHT):
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
        else:
            # 테스트 모드 HUD
            self.ui_mgr.update(dt, player_pos=(px, py), camera_heading=getattr(self.player, 'heading', 0.0), is_moving=is_moving, is_sprinting=is_sprinting)
            self.ui_mgr.update_timer(9999.0)
            self.ui_mgr.update_hud(px, py, "TEST", getattr(self.player, 'heading', 0.0))

        # 전술 스킬 (슬라이드 / 수류탄) 및 필드 보급 상자 인터랙션 갱신
        if self.grenade_cooldown > 0.0:
            self.grenade_cooldown = max(0.0, self.grenade_cooldown - dt)

        # 드랍된 전술 아이템 애니메이션 및 자동 수거(Auto-pickup) 판정
        closest_interact_drop = None
        for drop in self.item_drops[:]:
            status = drop.update(dt, px, py)
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
            if cr.can_interact(px, py):
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