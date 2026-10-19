"""
Combat System Module
1인칭 듀얼 뷰모델(손전등/권총), 레이캐스트 사격, 재장전, 반동/밥빙 애니메이션,
발광 총알 궤적(Bullet Tracer) 및 필드 탄약 상자 드랍/습득 관리
"""

import math
import random
from panda3d.core import (
    PointLight, Spotlight, PerspectiveLens, LineSegs, LColor, Vec3, TransparencyAttrib
)
from constants import (
    CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import cell_has_pillar
from geometry import make_cube_to
from collision import raycast_walls
from projectiles import ExplosionVisualEffect


WEAPON_CONFIGS = {
    "PISTOL": {
        "id": "PISTOL",
        "name": "9mm 택티컬 권총",
        "max_ammo": 12,
        "initial_reserve": 36,
        "damage": 62.0,
        "headshot_mult": 3.2,
        "cooldown": 0.36,
        "combo_cooldown": 0.26,
        "pellets": 1,
        "base_spread": 0.010,
        "ads_spread": 0.0,
        "recoil_time": 0.12,
        "recoil_deg": 14.0,
        "reload_time": 1.25,
        "description": "12발 탄창. 저연사 고위력·초정밀 헤드샷 특화 (헤드샷 198 피해 일격필살)."
    },
    "DUAL_PISTOL": {
        "id": "DUAL_PISTOL",
        "name": "아킴보 쌍권총",
        "max_ammo": 24,
        "initial_reserve": 48,
        "damage": 25.0,
        "headshot_mult": 2.0,
        "cooldown": 0.070,
        "combo_cooldown": 0.050,
        "pellets": 1,
        "base_spread": 0.054,
        "ads_spread": 0.022,
        "recoil_time": 0.065,
        "recoil_deg": 8.0,
        "reload_time": 2.60,
        "description": "24발 대용량(양손 12발x2). 0.07초 초고속 난사 특화 (양손 동시 장전 2.6초 지연)."
    },
    "SHOTGUN": {
        "id": "SHOTGUN",
        "name": "12게이지 전술 샷건",
        "max_ammo": 8,
        "initial_reserve": 24,
        "damage": 24.0,
        "headshot_mult": 1.6,
        "cooldown": 0.72,
        "combo_cooldown": 0.58,
        "pellets": 8,
        "base_spread": 0.175,
        "ads_spread": 0.110,
        "recoil_time": 0.20,
        "recoil_deg": 26.0,
        "reload_time": 1.75,
        "pump_time": 0.44,
        "description": "8발 튜브 탄창. 1격발당 8발 대구경 벅샷 산탄 (초근접 광역 섬멸, 원거리 산탄 분산 및 위력 감쇄)."
    }
}
WEAPON_ORDER = ["PISTOL", "DUAL_PISTOL", "SHOTGUN"]


class CombatSystem:
    def __init__(self, base, render, camera, world_root, audio_mgr, ui_mgr):
        self.base = base
        self.render = render
        self.camera = camera
        self.world_root = world_root
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 무기 인벤토리 및 장착 상태
        self.current_weapon = "PISTOL"
        self._reserve_ammo = 36
        self.weapon_states = {
            "PISTOL": {"ammo": 12, "max_ammo": 12, "reserve_ammo": 36, "slide_locked": False},
            "DUAL_PISTOL": {"ammo": 24, "max_ammo": 24, "reserve_ammo": 48, "slide_locked": False},
            "SHOTGUN": {"ammo": 8, "max_ammo": 8, "reserve_ammo": 24, "slide_locked": False},
        }

        # 탄약 및 사격 상태
        self.max_ammo = 12
        self.ammo = self.max_ammo
        self.overcharge_rounds = 0  # 오버차지 고폭 플라즈마 소이탄 탄환 수
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0

        # 쌍권총 & 샷건 특화 메커니즘 상태
        self.dual_hand_toggle = 0
        self.sg_pump_timer = 0.0
        self.sg_pump_cycled = False
        self.switch_timer = 0.0
        self.slide_timer_left = 0.0
        self.slide_timer_right = 0.0

        self.active_tracers = []
        self.ammo_drops = []
        self.hit_particles = []

        # 현실적 총기 메커니즘 상태 (슬라이드 블로우백, 탄피 배출, 탄창 분리, 슬라이드 락)
        self.slide_locked = False
        self.slide_timer = 0.0
        self.slide_blowback_duration = 0.08
        self.slide_max_travel = -0.055
        self.hammer_timer = 0.0
        self.active_casings = []
        self.smoke_particles = []
        self.was_slide_locked_before_reload = False

        # 정전 상태
        self.is_blackout = False

        # 킬 콤보 & 아드레날린 램페이지 상태
        self.combo_count = 0
        self.combo_timer = 0.0
        self.combo_window = 3.8
        self.bullet_storm_timer = 0.0  # 탄환 폭풍 퍽 활성화 타이머

        # 정밀 조준(ADS: Aim Down Sights) 상태
        self.is_aiming = False
        self.ads_alpha = 0.0
        # 1인칭 시점(POV) 쾌적화: 총기가 카메라에 너무 가깝지 않도록 전방 및 하단으로 거리 확보 (시야 개방감 극대화)
        self.ads_hip_pos = Vec3(0.20, 0.68, -0.195)
        self.ads_aim_pos = Vec3(0.00, 0.58, -0.118)
        self.ads_hip_hpr = Vec3(1.5, 0.8, -0.8)
        self.ads_aim_hpr = Vec3(0.0, 0.0, 0.0)

        # 샷건 및 쌍권총 POV 좌표
        self.ads_hip_pos_sg = Vec3(0.18, 0.68, -0.215)
        self.ads_aim_pos_sg = Vec3(0.00, 0.58, -0.134)
        self.ads_hip_pos_dual_l = Vec3(-0.17, 0.62, -0.21)
        self.ads_aim_pos_dual_l = Vec3(-0.07, 0.58, -0.15)
        self.ads_hip_pos_dual_r = Vec3(0.17, 0.62, -0.21)
        self.ads_aim_pos_dual_r = Vec3(0.07, 0.58, -0.15)

        # 지향사격(Hip-fire) 탄퍼짐 및 크로스헤어 흔들림 상태
        self.hipfire_bloom = 0.0
        self.is_moving = False
        self.is_sprinting = False

        # 뷰모델 지오메트리 구축
        self._setup_viewmodel()

        # 고성능 무할당(Zero-Allocation) 오브젝트 풀 구축 (GC 스파이크 원천 차단)
        self._init_pools()

    def _init_pools(self):
        """고속 렌더링을 위한 3D 피격 파티클, 황동 탄피 및 총구 연기 오브젝트 풀 (GC 방지)"""
        # 1. 피격 파티클 풀 (64개)
        self.hit_particle_pool = []
        for i in range(64):
            p_node = self.world_root.attachNewNode(f"pooled_hit_p_{i}")
            cube = make_cube_to(p_node, 0.08, 0.08, 0.08, LColor(1.0, 1.0, 1.0, 1.0), 0, 0, 0)
            cube.setLightOff()
            p_node.hide()
            self.hit_particle_pool.append({
                "node": p_node,
                "cube": cube,
                "pos": Vec3(0, 0, 0),
                "vel": Vec3(0, 0, 0),
                "timer": 0.0,
                "active": False
            })
        self.hit_particle_cursor = 0

        # 2. 황동 탄피 물리 풀 (24개)
        self.casing_pool = []
        brass_col = LColor(0.92, 0.76, 0.24, 1.0)
        for i in range(24):
            c_node = self.world_root.attachNewNode(f"pooled_casing_{i}")
            cube = make_cube_to(c_node, 0.016, 0.044, 0.016, brass_col, 0, 0, 0)
            cube.setLightOff()
            c_node.hide()
            self.casing_pool.append({
                "node": c_node,
                "cube": cube,
                "pos": Vec3(0, 0, 0),
                "vel": Vec3(0, 0, 0),
                "rot": Vec3(0, 0, 0),
                "spin": Vec3(0, 0, 0),
                "life": 0.0,
                "active": False
            })
        self.casing_cursor = 0

        # 3. 총구 화약 가스 연기 풀 (20개)
        self.smoke_pool = []
        smoke_col = LColor(0.75, 0.75, 0.78, 0.35)
        for i in range(20):
            s_node = self.world_root.attachNewNode(f"pooled_smoke_{i}")
            cube = make_cube_to(s_node, 0.045, 0.045, 0.045, smoke_col, 0, 0, 0)
            cube.setLightOff()
            s_node.hide()
            self.smoke_pool.append({
                "node": s_node,
                "cube": cube,
                "pos": Vec3(0, 0, 0),
                "vel": Vec3(0, 0, 0),
                "scale": 0.045,
                "timer": 0.0,
                "max_timer": 0.55,
                "active": False
            })
        self.smoke_cursor = 0

    @property
    def reserve_ammo(self):
        return self._reserve_ammo

    @reserve_ammo.setter
    def reserve_ammo(self, val):
        diff = val - getattr(self, '_reserve_ammo', 36)
        self._reserve_ammo = val
        if hasattr(self, 'weapon_states') and self.current_weapon in self.weapon_states:
            self.weapon_states[self.current_weapon]["reserve_ammo"] = val
            if diff > 0:
                for w_id, w_st in self.weapon_states.items():
                    if w_id != self.current_weapon:
                        if w_id == "SHOTGUN":
                            w_st["reserve_ammo"] += max(4, int(diff * 0.5))
                        else:
                            w_st["reserve_ammo"] += diff

    def get_weapon_display_name(self):
        """현재 장착된 활성 무기 한글 명칭 반환"""
        return WEAPON_CONFIGS.get(self.current_weapon, {}).get("name", "9mm 택티컬 권총")

    def switch_weapon(self, target_weapon):
        """[Z, X, C] 또는 [Q/휠]을 통한 실시간 무기 스왑"""
        if target_weapon not in WEAPON_CONFIGS:
            return
        if target_weapon == self.current_weapon:
            return

        # 현재 무기의 탄약 및 슬라이드 상태 캐싱
        self.weapon_states[self.current_weapon]["ammo"] = self.ammo
        self.weapon_states[self.current_weapon]["reserve_ammo"] = self._reserve_ammo
        self.weapon_states[self.current_weapon]["slide_locked"] = self.slide_locked

        # 재장전 중 무기 교체 시 재장전 즉시 안전 취소
        if self.is_reloading:
            self.is_reloading = False
            self.reload_timer = 0.0

        # 신규 무기 장착
        self.current_weapon = target_weapon
        st = self.weapon_states[self.current_weapon]
        cfg = WEAPON_CONFIGS[self.current_weapon]
        self.max_ammo = cfg["max_ammo"]
        self.ammo = st["ammo"]
        self._reserve_ammo = st["reserve_ammo"]
        self.slide_locked = st["slide_locked"]
        self.shoot_cooldown = max(self.shoot_cooldown, 0.22)
        self.switch_timer = 0.22

        # 3D 뷰모델 전환 및 효과음
        self._update_viewmodel_visibility()

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_weapon_switch'):
            self.audio_mgr.play_weapon_switch()

        self.ui_mgr.show_hit_marker(f"[ 무기 전환 : {cfg['name']} ]", (0.40, 0.95, 1.0, 1.0))
        self.update_ammo_ui()

    def next_weapon(self):
        """[Q] 또는 [마우스 휠 다운] 다음 무기 순환 스왑"""
        idx = WEAPON_ORDER.index(self.current_weapon)
        next_idx = (idx + 1) % len(WEAPON_ORDER)
        self.switch_weapon(WEAPON_ORDER[next_idx])

    def prev_weapon(self):
        """[마우스 휠 업] 이전 무기 순환 스왑"""
        idx = WEAPON_ORDER.index(self.current_weapon)
        prev_idx = (idx - 1) % len(WEAPON_ORDER)
        self.switch_weapon(WEAPON_ORDER[prev_idx])

    def _update_viewmodel_visibility(self):
        """현재 선택된 활성 무기의 3D 뷰모델만 표시하고 나머지는 숨김"""
        if hasattr(self, 'vm_pistol') and self.vm_pistol:
            if self.current_weapon == "PISTOL":
                self.vm_pistol.show()
            else:
                self.vm_pistol.hide()

        if hasattr(self, 'vm_dual') and self.vm_dual:
            if self.current_weapon == "DUAL_PISTOL":
                self.vm_dual.show()
            else:
                self.vm_dual.hide()

        if hasattr(self, 'vm_shotgun') and self.vm_shotgun:
            if self.current_weapon == "SHOTGUN":
                self.vm_shotgun.show()
            else:
                self.vm_shotgun.hide()

    def start_aim(self):
        """우클릭 정밀 조준(ADS) 시작"""
        if not self.is_aiming:
            self.is_aiming = True
            if self.audio_mgr:
                self.audio_mgr.play_ads(True)

    def stop_aim(self):
        """우클릭 정밀 조준(ADS) 해제"""
        if self.is_aiming:
            self.is_aiming = False
            if self.audio_mgr:
                self.audio_mgr.play_ads(False)

    def _setup_viewmodel(self):
        """1인칭 택티컬 뷰모델: 안정적 통합 전방 조명 및 3종 무기(9mm 권총, 아킴보 쌍권총, 12게이지 샷건) 지오메트리 구축"""
        if hasattr(self, 'vm_root') and self.vm_root:
            self.vm_root.removeNode()

        self.vm_root = self.camera.attachNewNode("viewmodel_root")

        # 전 무기 공용 안정적 택티컬 웨폰라이트 (WML) & 근거리 보조 조명
        spotlight = Spotlight('player_flashlight')
        spotlight.setColor((2.85, 2.70, 2.35, 1.0))
        spot_lens = PerspectiveLens()
        spot_lens.setFov(50.0)
        spot_lens.setNearFar(0.15, 70.0)
        spotlight.setLens(spot_lens)
        spotlight.setAttenuation((1.0, 0.015, 0.0006))
        spotlight.setExponent(50.0)
        self.pl_np = self.vm_root.attachNewNode(spotlight)
        self.pl_np.setPos(0.12, 0.20, -0.05)
        self.render.setLight(self.pl_np)

        fill_light = PointLight('player_fill')
        fill_light.setColor((0.18, 0.16, 0.14, 1.0))
        fill_light.setAttenuation((1.0, 0.30, 0.08))
        self.fill_np = self.vm_root.attachNewNode(fill_light)
        self.fill_np.setPos(0.08, 0.15, -0.05)
        self.render.setLight(self.fill_np)

        # 3종 무기 3D 지오메트리 개별 구축
        self._build_pistol_viewmodel()
        self._build_dual_viewmodel()
        self._build_shotgun_viewmodel()
        self._update_viewmodel_visibility()

    def _build_pistol_viewmodel(self):
        """1. 단일 9mm 택티컬 권총 뷰모델 지오메트리"""
        self.vm_pistol = self.vm_root.attachNewNode("vm_pistol")
        self.vm_pistol.setPos(self.ads_hip_pos)
        self.vm_pistol.setHpr(self.ads_hip_hpr)

        self.recoil_node = self.vm_pistol.attachNewNode("recoil_node")

        steel_dark = LColor(0.10, 0.10, 0.12, 1.0)
        steel_slide = LColor(0.22, 0.23, 0.26, 1.0)
        steel_barrel = LColor(0.16, 0.16, 0.18, 1.0)
        grip_col = LColor(0.06, 0.06, 0.07, 1.0)
        tritium_green = LColor(0.35, 1.0, 0.40, 1.0)

        # 하부 프레임 (Frame)
        self.frame_node = self.recoil_node.attachNewNode("frame_node")
        grip = make_cube_to(self.frame_node, 0.058, 0.11, 0.20, grip_col, 0, -0.06, -0.09)
        grip.setP(16)
        make_cube_to(self.frame_node, 0.055, 0.20, 0.050, steel_dark, 0, 0.08, 0.005)
        make_cube_to(self.frame_node, 0.030, 0.08, 0.060, steel_dark, 0, 0.04, -0.04)
        make_cube_to(self.frame_node, 0.014, 0.02, 0.035, steel_dark, 0, 0.035, -0.025)
        make_cube_to(self.frame_node, 0.010, 0.035, 0.012, steel_dark, -0.032, 0.02, 0.045)
        make_cube_to(self.frame_node, 0.012, 0.015, 0.015, steel_dark, -0.032, -0.03, -0.02)

        # 권총 하부 언더레일 웨폰라이트 바디
        vm_fl = self.frame_node.attachNewNode("vm_fl")
        vm_fl.setPos(0, 0.13, -0.034)
        make_cube_to(vm_fl, 0.060, 0.14, 0.020, steel_slide, 0, -0.012, 0.022)
        make_cube_to(vm_fl, 0.052, 0.16, 0.044, steel_dark, 0, 0.0, 0.0)
        make_cube_to(vm_fl, 0.056, 0.028, 0.048, steel_slide, 0, 0.092, 0.0)
        lens = make_cube_to(vm_fl, 0.046, 0.008, 0.042, LColor(1.0, 0.96, 0.82, 0.95), 0, 0.108, 0.0)
        lens.setLightOff()

        # 총열 및 약실
        self.barrel_node = self.recoil_node.attachNewNode("barrel_node")
        make_cube_to(self.barrel_node, 0.042, 0.16, 0.042, steel_barrel, 0, 0.18, 0.04)
        make_cube_to(self.barrel_node, 0.028, 0.015, 0.028, LColor(0.02, 0.02, 0.02, 1.0), 0, 0.265, 0.04)
        make_cube_to(self.barrel_node, 0.048, 0.07, 0.046, steel_dark, 0, 0.04, 0.042)

        # 왕복 슬라이드
        self.slide_node = self.recoil_node.attachNewNode("slide_node")
        make_cube_to(self.slide_node, 0.062, 0.30, 0.075, steel_slide, 0, 0.05, 0.045)
        make_cube_to(self.slide_node, 0.020, 0.07, 0.035, steel_dark, 0.026, 0.04, 0.055)
        make_cube_to(self.slide_node, 0.064, 0.05, 0.055, steel_dark, 0, -0.05, 0.045)

        front_sight = make_cube_to(self.slide_node, 0.012, 0.02, 0.02, tritium_green, 0, 0.19, 0.09)
        front_sight.setLightOff()
        r_sight1 = make_cube_to(self.slide_node, 0.012, 0.015, 0.02, tritium_green, -0.022, -0.09, 0.09)
        r_sight2 = make_cube_to(self.slide_node, 0.012, 0.015, 0.02, tritium_green, 0.022, -0.09, 0.09)
        r_sight1.setLightOff()
        r_sight2.setLightOff()

        # 해머 (공이치기)
        self.hammer_node = self.recoil_node.attachNewNode("hammer_node")
        self.hammer_node.setPos(0, -0.102, 0.038)
        self.hammer_node.setP(-42)
        make_cube_to(self.hammer_node, 0.016, 0.030, 0.045, steel_dark, 0, -0.012, 0.018)

        # 분리형 탄창
        self.mag_node = self.frame_node.attachNewNode("mag_node")
        self.mag_node.setPos(0, -0.06, -0.09)
        self.mag_node.setP(16)
        make_cube_to(self.mag_node, 0.046, 0.082, 0.18, steel_dark, 0, 0, 0)
        make_cube_to(self.mag_node, 0.056, 0.096, 0.024, grip_col, 0, -0.005, -0.095)
        make_cube_to(self.mag_node, 0.024, 0.048, 0.024, LColor(0.85, 0.68, 0.22, 1.0), 0, 0.01, 0.08)

        # 총구 화염 & 섬광 조명
        self.muzzle_flash_geom = make_cube_to(self.recoil_node, 0.16, 0.22, 0.16, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.34, 0.04, rot_h=45)
        self.muzzle_flash_geom.setLightOff()
        self.muzzle_flash_geom.hide()

        self.muzzle_light = PointLight('muzzle_light')
        self.muzzle_light.setColor((2.8, 2.2, 0.9, 1.0))
        self.muzzle_light.setAttenuation((1.0, 0.08, 0.015))
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)
        self.muzzle_light_np.setPos(0, 0.35, 0.04)

        # 1인칭 전술 장갑 및 손목 팔 (Tactical Hands & Arms - 권총 투핸드 파지법)
        glove_dark = LColor(0.12, 0.12, 0.14, 1.0)
        knuckle_col = LColor(0.20, 0.22, 0.25, 1.0)
        sleeve_col = LColor(0.08, 0.09, 0.11, 1.0)
        strap_col = LColor(0.05, 0.05, 0.06, 1.0)

        # (1) 오른손 (주무기 권총 그립 파지)
        r_hand = self.recoil_node.attachNewNode("pistol_r_hand")
        make_cube_to(r_hand, 0.075, 0.28, 0.075, sleeve_col, 0.065, -0.26, -0.20, rot_h=-12, rot_p=30, rot_r=-12)
        make_cube_to(r_hand, 0.068, 0.045, 0.068, strap_col, 0.038, -0.14, -0.13, rot_h=-10, rot_p=24, rot_r=-8)
        make_cube_to(r_hand, 0.064, 0.095, 0.064, glove_dark, 0.020, -0.075, -0.095, rot_p=16)
        make_cube_to(r_hand, 0.062, 0.040, 0.022, knuckle_col, 0.036, -0.065, -0.082, rot_p=16, rot_r=12)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.015, -0.062, rot_p=16)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.025, -0.098, rot_p=16)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.035, -0.134, rot_p=16)
        make_cube_to(r_hand, 0.022, 0.068, 0.022, glove_dark, 0.026, 0.012, -0.024, rot_h=-6, rot_p=8)
        make_cube_to(r_hand, 0.025, 0.058, 0.025, glove_dark, -0.026, -0.055, -0.032, rot_h=10, rot_p=-8)

        # (2) 왼손 (오른손 밑을 받쳐 감싸는 투핸드 전술 서포트)
        l_hand = self.recoil_node.attachNewNode("pistol_l_hand")
        make_cube_to(l_hand, 0.075, 0.28, 0.075, sleeve_col, -0.082, -0.24, -0.21, rot_h=16, rot_p=30, rot_r=16)
        make_cube_to(l_hand, 0.068, 0.045, 0.068, strap_col, -0.048, -0.13, -0.14, rot_h=14, rot_p=22, rot_r=10)
        make_cube_to(l_hand, 0.066, 0.088, 0.064, glove_dark, -0.024, -0.070, -0.120, rot_p=16, rot_r=-14)
        make_cube_to(l_hand, 0.056, 0.062, 0.032, knuckle_col, -0.012, -0.032, -0.128, rot_p=16, rot_h=12)
        make_cube_to(l_hand, 0.022, 0.072, 0.022, glove_dark, -0.032, -0.008, -0.024, rot_p=6)

    def _build_dual_viewmodel(self):
        """2. 아킴보 쌍권총 (Dual Akimbo Pistols) 좌/우 뷰모델 지오메트리"""
        self.vm_dual = self.vm_root.attachNewNode("vm_dual")

        steel_dark = LColor(0.10, 0.10, 0.12, 1.0)
        steel_slide = LColor(0.22, 0.23, 0.26, 1.0)
        grip_col = LColor(0.06, 0.06, 0.07, 1.0)
        tritium_cyan = LColor(0.25, 0.95, 1.0, 1.0)

        # (1) 좌측 권총 (Left Hand Pistol)
        self.vm_dual_left = self.vm_dual.attachNewNode("vm_dual_left")
        self.vm_dual_left.setPos(self.ads_hip_pos_dual_l)
        self.vm_dual_left.setHpr(Vec3(4.0, 1.0, 10.0))

        self.dual_left_recoil = self.vm_dual_left.attachNewNode("dual_left_recoil")
        left_frame = self.dual_left_recoil.attachNewNode("dual_left_frame")
        lgrip = make_cube_to(left_frame, 0.052, 0.10, 0.18, grip_col, 0, -0.05, -0.08)
        lgrip.setP(16)
        make_cube_to(left_frame, 0.050, 0.18, 0.046, steel_dark, 0, 0.07, 0.005)
        make_cube_to(left_frame, 0.026, 0.07, 0.055, steel_dark, 0, 0.035, -0.035)

        self.dual_left_slide = self.dual_left_recoil.attachNewNode("dual_left_slide")
        make_cube_to(self.dual_left_slide, 0.056, 0.28, 0.068, steel_slide, 0, 0.05, 0.040)
        make_cube_to(self.dual_left_slide, 0.018, 0.06, 0.030, steel_dark, -0.024, 0.04, 0.050)
        l_front = make_cube_to(self.dual_left_slide, 0.010, 0.018, 0.018, tritium_cyan, 0, 0.18, 0.08)
        l_front.setLightOff()

        self.dual_left_hammer = self.dual_left_recoil.attachNewNode("dual_left_hammer")
        self.dual_left_hammer.setPos(0, -0.095, 0.034)
        self.dual_left_hammer.setP(-42)
        make_cube_to(self.dual_left_hammer, 0.014, 0.028, 0.040, steel_dark, 0, -0.01, 0.016)

        self.dual_left_mag = left_frame.attachNewNode("dual_left_mag")
        self.dual_left_mag.setPos(0, -0.05, -0.08)
        self.dual_left_mag.setP(16)
        make_cube_to(self.dual_left_mag, 0.042, 0.075, 0.16, steel_dark, 0, 0, 0)

        self.dual_left_flash_geom = make_cube_to(self.dual_left_recoil, 0.15, 0.20, 0.15, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.32, 0.035, rot_h=45)
        self.dual_left_flash_geom.setLightOff()
        self.dual_left_flash_geom.hide()

        self.dual_left_flash_light = PointLight('dual_left_light')
        self.dual_left_flash_light.setColor((2.6, 2.0, 0.8, 1.0))
        self.dual_left_flash_light.setAttenuation((1.0, 0.09, 0.018))
        self.dual_left_flash_light_np = self.dual_left_recoil.attachNewNode(self.dual_left_flash_light)
        self.dual_left_flash_light_np.setPos(0, 0.32, 0.035)

        # 왼손 아킴보 권총 파지 전술 손 & 팔
        l_hand_dual = self.dual_left_recoil.attachNewNode("dual_l_hand")
        make_cube_to(l_hand_dual, 0.075, 0.26, 0.075, LColor(0.08, 0.09, 0.11, 1.0), -0.065, -0.25, -0.20, rot_h=12, rot_p=30, rot_r=12)
        make_cube_to(l_hand_dual, 0.068, 0.045, 0.068, LColor(0.05, 0.05, 0.06, 1.0), -0.038, -0.14, -0.13, rot_h=10, rot_p=24, rot_r=8)
        make_cube_to(l_hand_dual, 0.064, 0.095, 0.064, LColor(0.12, 0.12, 0.14, 1.0), -0.020, -0.075, -0.095, rot_p=16)
        make_cube_to(l_hand_dual, 0.062, 0.040, 0.022, LColor(0.20, 0.22, 0.25, 1.0), -0.036, -0.065, -0.082, rot_p=16, rot_r=-12)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.015, -0.062, rot_p=16)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.025, -0.098, rot_p=16)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.035, -0.134, rot_p=16)
        make_cube_to(l_hand_dual, 0.022, 0.068, 0.022, LColor(0.12, 0.12, 0.14, 1.0), -0.026, 0.012, -0.024, rot_h=6, rot_p=8)
        make_cube_to(l_hand_dual, 0.025, 0.058, 0.025, LColor(0.12, 0.12, 0.14, 1.0), 0.026, -0.055, -0.032, rot_h=-10, rot_p=-8)

        # (2) 우측 권총 (Right Hand Pistol)
        self.vm_dual_right = self.vm_dual.attachNewNode("vm_dual_right")
        self.vm_dual_right.setPos(self.ads_hip_pos_dual_r)
        self.vm_dual_right.setHpr(Vec3(-4.0, 1.0, -10.0))

        self.dual_right_recoil = self.vm_dual_right.attachNewNode("dual_right_recoil")
        right_frame = self.dual_right_recoil.attachNewNode("dual_right_frame")
        rgrip = make_cube_to(right_frame, 0.052, 0.10, 0.18, grip_col, 0, -0.05, -0.08)
        rgrip.setP(16)
        make_cube_to(right_frame, 0.050, 0.18, 0.046, steel_dark, 0, 0.07, 0.005)
        make_cube_to(right_frame, 0.026, 0.07, 0.055, steel_dark, 0, 0.035, -0.035)

        self.dual_right_slide = self.dual_right_recoil.attachNewNode("dual_right_slide")
        make_cube_to(self.dual_right_slide, 0.056, 0.28, 0.068, steel_slide, 0, 0.05, 0.040)
        make_cube_to(self.dual_right_slide, 0.018, 0.06, 0.030, steel_dark, 0.024, 0.04, 0.050)
        r_front = make_cube_to(self.dual_right_slide, 0.010, 0.018, 0.018, tritium_cyan, 0, 0.18, 0.08)
        r_front.setLightOff()

        self.dual_right_hammer = self.dual_right_recoil.attachNewNode("dual_right_hammer")
        self.dual_right_hammer.setPos(0, -0.095, 0.034)
        self.dual_right_hammer.setP(-42)
        make_cube_to(self.dual_right_hammer, 0.014, 0.028, 0.040, steel_dark, 0, -0.01, 0.016)

        self.dual_right_mag = right_frame.attachNewNode("dual_right_mag")
        self.dual_right_mag.setPos(0, -0.05, -0.08)
        self.dual_right_mag.setP(16)
        make_cube_to(self.dual_right_mag, 0.042, 0.075, 0.16, steel_dark, 0, 0, 0)

        self.dual_right_flash_geom = make_cube_to(self.dual_right_recoil, 0.15, 0.20, 0.15, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.32, 0.035, rot_h=45)
        self.dual_right_flash_geom.setLightOff()
        self.dual_right_flash_geom.hide()

        self.dual_right_flash_light = PointLight('dual_right_light')
        self.dual_right_flash_light.setColor((2.6, 2.0, 0.8, 1.0))
        self.dual_right_flash_light.setAttenuation((1.0, 0.09, 0.018))
        self.dual_right_flash_light_np = self.dual_right_recoil.attachNewNode(self.dual_right_flash_light)
        self.dual_right_flash_light_np.setPos(0, 0.32, 0.035)

        # 오른손 아킴보 권총 파지 전술 손 & 팔
        r_hand_dual = self.dual_right_recoil.attachNewNode("dual_r_hand")
        make_cube_to(r_hand_dual, 0.075, 0.26, 0.075, LColor(0.08, 0.09, 0.11, 1.0), 0.065, -0.25, -0.20, rot_h=-12, rot_p=30, rot_r=-12)
        make_cube_to(r_hand_dual, 0.068, 0.045, 0.068, LColor(0.05, 0.05, 0.06, 1.0), 0.038, -0.14, -0.13, rot_h=-10, rot_p=24, rot_r=-8)
        make_cube_to(r_hand_dual, 0.064, 0.095, 0.064, LColor(0.12, 0.12, 0.14, 1.0), 0.020, -0.075, -0.095, rot_p=16)
        make_cube_to(r_hand_dual, 0.062, 0.040, 0.022, LColor(0.20, 0.22, 0.25, 1.0), 0.036, -0.065, -0.082, rot_p=16, rot_r=12)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.015, -0.062, rot_p=16)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.025, -0.098, rot_p=16)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.035, -0.134, rot_p=16)
        make_cube_to(r_hand_dual, 0.022, 0.068, 0.022, LColor(0.12, 0.12, 0.14, 1.0), 0.026, 0.012, -0.024, rot_h=-6, rot_p=8)
        make_cube_to(r_hand_dual, 0.025, 0.058, 0.025, LColor(0.12, 0.12, 0.14, 1.0), -0.026, -0.055, -0.032, rot_h=10, rot_p=-8)

    def _build_shotgun_viewmodel(self):
        """3. 12게이지 전술 샷건 (Tactical Combat Shotgun) 뷰모델 지오메트리"""
        self.vm_shotgun = self.vm_root.attachNewNode("vm_shotgun")
        self.vm_shotgun.setPos(self.ads_hip_pos_sg)
        self.vm_shotgun.setHpr(Vec3(1.0, 0.5, -0.5))

        self.sg_recoil_node = self.vm_shotgun.attachNewNode("sg_recoil_node")

        steel_dark = LColor(0.09, 0.09, 0.11, 1.0)
        steel_slide = LColor(0.20, 0.21, 0.24, 1.0)
        steel_barrel = LColor(0.14, 0.14, 0.16, 1.0)
        grip_col = LColor(0.05, 0.05, 0.06, 1.0)
        fiber_red = LColor(1.0, 0.22, 0.12, 1.0)

        # 리시버 (Receiver)
        make_cube_to(self.sg_recoil_node, 0.070, 0.38, 0.090, steel_slide, 0, 0.02, 0.02)
        make_cube_to(self.sg_recoil_node, 0.025, 0.09, 0.040, steel_dark, 0.030, 0.04, 0.035)

        # 12게이지 강선 총열 및 방열판
        make_cube_to(self.sg_recoil_node, 0.044, 0.52, 0.044, steel_barrel, 0, 0.40, 0.045)
        make_cube_to(self.sg_recoil_node, 0.032, 0.015, 0.032, LColor(0.01, 0.01, 0.01, 1.0), 0, 0.665, 0.045)
        make_cube_to(self.sg_recoil_node, 0.054, 0.36, 0.054, steel_dark, 0, 0.32, 0.045)

        # 하부 8발 튜브 탄창
        make_cube_to(self.sg_recoil_node, 0.040, 0.48, 0.040, steel_dark, 0, 0.36, -0.010)
        make_cube_to(self.sg_recoil_node, 0.044, 0.03, 0.044, steel_slide, 0, 0.60, -0.010)

        # 펌프액션 슬라이드 포어엔드 (Pump Slide Handle)
        self.sg_pump_node = self.sg_recoil_node.attachNewNode("sg_pump_node")
        self.sg_pump_node.setPos(0, 0.28, -0.010)
        make_cube_to(self.sg_pump_node, 0.072, 0.20, 0.072, grip_col, 0, 0, 0)
        make_cube_to(self.sg_pump_node, 0.078, 0.16, 0.025, steel_dark, 0, 0, 0)
        # 펌프 하부 택티컬 라이트 바디
        make_cube_to(self.sg_pump_node, 0.038, 0.12, 0.038, steel_dark, 0, 0.04, -0.045)
        lens = make_cube_to(self.sg_pump_node, 0.032, 0.008, 0.032, LColor(1.0, 0.96, 0.82, 0.95), 0, 0.105, -0.045)
        lens.setLightOff()

        # 권총 손잡이 및 전술 개머리판
        make_cube_to(self.sg_recoil_node, 0.054, 0.11, 0.19, grip_col, 0, -0.14, -0.08, rot_p=22)
        make_cube_to(self.sg_recoil_node, 0.042, 0.30, 0.065, steel_dark, 0, -0.28, -0.01)
        make_cube_to(self.sg_recoil_node, 0.054, 0.045, 0.15, grip_col, 0, -0.43, -0.03)

        # 광섬유 가늠쇠 & 고스트링 가늠자
        front_bead = make_cube_to(self.sg_recoil_node, 0.010, 0.025, 0.014, fiber_red, 0, 0.64, 0.076)
        front_bead.setLightOff()
        make_cube_to(self.sg_recoil_node, 0.038, 0.020, 0.026, steel_dark, 0, -0.12, 0.076)

        # 샷건 대구경 총구 화염 및 조명
        self.sg_muzzle_flash_geom = make_cube_to(self.sg_recoil_node, 0.28, 0.38, 0.28, LColor(1.0, 0.82, 0.20, 1.0), 0, 0.74, 0.045, rot_h=45)
        self.sg_muzzle_flash_geom.setLightOff()
        self.sg_muzzle_flash_geom.hide()

        self.sg_muzzle_light = PointLight('sg_muzzle_light')
        self.sg_muzzle_light.setColor((4.2, 2.6, 0.7, 1.0))
        self.sg_muzzle_light.setAttenuation((1.0, 0.05, 0.01))
        self.sg_muzzle_light_np = self.sg_recoil_node.attachNewNode(self.sg_muzzle_light)
        self.sg_muzzle_light_np.setPos(0, 0.75, 0.045)

        # 샷건 1인칭 전술 손 & 팔 (Tactical Hands & Arms)
        sg_sleeve = LColor(0.08, 0.09, 0.11, 1.0)
        sg_strap = LColor(0.05, 0.05, 0.06, 1.0)
        sg_glove = LColor(0.12, 0.12, 0.14, 1.0)
        sg_knuckle = LColor(0.20, 0.22, 0.25, 1.0)

        # (1) 오른손: 샷건 후방 피스톨 그립 파지
        r_hand_sg = self.sg_recoil_node.attachNewNode("sg_r_hand")
        make_cube_to(r_hand_sg, 0.075, 0.32, 0.075, sg_sleeve, 0.065, -0.34, -0.21, rot_h=-12, rot_p=28, rot_r=-10)
        make_cube_to(r_hand_sg, 0.068, 0.045, 0.068, sg_strap, 0.036, -0.22, -0.13, rot_h=-10, rot_p=24, rot_r=-6)
        make_cube_to(r_hand_sg, 0.064, 0.095, 0.064, sg_glove, 0.020, -0.15, -0.09, rot_p=22)
        make_cube_to(r_hand_sg, 0.062, 0.040, 0.022, sg_knuckle, 0.036, -0.14, -0.08, rot_p=22, rot_r=12)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.095, -0.075, rot_p=22)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.108, -0.105, rot_p=22)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.120, -0.135, rot_p=22)
        make_cube_to(r_hand_sg, 0.022, 0.068, 0.022, sg_glove, 0.026, -0.065, -0.030, rot_p=10)
        make_cube_to(r_hand_sg, 0.025, 0.058, 0.025, sg_glove, -0.026, -0.135, -0.035, rot_h=10, rot_p=-10)

        # (2) 왼손: 샷건 펌프액션 슬라이드 손잡이(sg_pump_node)에 직접 결속 -> 펌프 당김 시 100% 동기화 슬라이딩
        l_hand_sg = self.sg_pump_node.attachNewNode("sg_l_hand")
        make_cube_to(l_hand_sg, 0.078, 0.32, 0.078, sg_sleeve, -0.095, -0.26, -0.21, rot_h=18, rot_p=32, rot_r=20)
        make_cube_to(l_hand_sg, 0.068, 0.055, 0.068, sg_strap, -0.048, -0.11, -0.10, rot_h=15, rot_p=24, rot_r=12)
        make_cube_to(l_hand_sg, 0.065, 0.11, 0.055, sg_glove, -0.015, -0.015, -0.050, rot_r=15)
        make_cube_to(l_hand_sg, 0.060, 0.05, 0.025, sg_knuckle, -0.038, -0.015, -0.052, rot_r=18)
        make_cube_to(l_hand_sg, 0.076, 0.12, 0.034, sg_glove, 0.006, 0.005, -0.042)
        make_cube_to(l_hand_sg, 0.032, 0.11, 0.044, sg_glove, 0.044, 0.005, -0.020)
        make_cube_to(l_hand_sg, 0.032, 0.072, 0.028, sg_glove, -0.042, 0.012, 0.018, rot_h=8, rot_p=6)

    def _eject_casing(self, is_left=False, is_shotgun=False):
        """격발 시 좌/우 탄피 배출구에서 3D 황동 탄피 또는 12게이지 샷건 셸이 회전하며 튀어나오는 물리 효과 (오브젝트 풀 재사용)"""
        cam_quat = self.camera.getQuat()
        cam_right = cam_quat.getRight()
        cam_fwd = cam_quat.getForward()
        cam_up = cam_quat.getUp()

        side_sign = -1.0 if is_left else 1.0
        eject_pos = self.camera.getPos() + cam_fwd * 0.65 + cam_right * (side_sign * 0.22 * (1.0 - self.ads_alpha) + side_sign * 0.05) - cam_up * 0.16

        v_right = random.uniform(2.4, 3.6) * side_sign
        v_up = random.uniform(1.8, 2.8)
        v_fwd = random.uniform(-0.8, -0.3)
        initial_vel = cam_right * v_right + cam_up * v_up + cam_fwd * v_fwd

        spin = Vec3(
            random.uniform(600, 1400) * side_sign,
            random.uniform(400, 1000),
            random.uniform(300, 800)
        )

        c = self.casing_pool[self.casing_cursor]
        self.casing_cursor = (self.casing_cursor + 1) % len(self.casing_pool)

        c["pos"] = Vec3(eject_pos)
        c["vel"] = initial_vel
        c["rot"] = Vec3(random.uniform(0, 360), random.uniform(0, 360), 0)
        c["spin"] = spin
        c["life"] = 1.4
        c["active"] = True

        c["node"].setPos(eject_pos)
        c["node"].setHpr(c["rot"])
        if is_shotgun:
            c["node"].setScale(1.4, 1.4, 1.4)
            c["cube"].setColorScale(0.85, 0.15, 0.15, 1.0)  # Red 12-gauge shotshell
        else:
            c["node"].setScale(1.0, 1.0, 1.0)
            c["cube"].setColorScale(0.92, 0.76, 0.24, 1.0)  # Brass 9mm casing
        c["node"].show()

    def _spawn_barrel_smoke(self, offset_x=0.0, offset_y=0.0):
        """격발 직후 총구 및 약실에서 피어오르는 반투명 화약 가스 연기 (오브젝트 풀 재사용)"""
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()

        muzzle_pos = self.camera.getPos() + cam_fwd * (0.80 + offset_y) + cam_right * (0.22 * (1.0 - self.ads_alpha) + offset_x) - cam_up * 0.16

        pool_len = len(self.smoke_pool)
        for _ in range(2):
            s = self.smoke_pool[self.smoke_cursor]
            self.smoke_cursor = (self.smoke_cursor + 1) % pool_len

            s["pos"] = muzzle_pos + Vec3(random.uniform(-0.02, 0.02), random.uniform(-0.02, 0.02), random.uniform(-0.02, 0.02))
            s["vel"] = cam_fwd * random.uniform(0.6, 1.4) + cam_up * random.uniform(0.2, 0.5) + cam_right * random.uniform(-0.1, 0.1)
            s["scale"] = 0.045
            s["timer"] = 0.55
            s["max_timer"] = 0.55
            s["active"] = True

            s["node"].setPos(s["pos"])
            s["node"].setScale(0.045)
            s["cube"].setColorScale(1, 1, 1, 0.35)
            s["node"].show()

    def _spawn_tracer_effect(self, muzzle_world, impact_world, travel_dir, total_dist, is_overcharge):
        """3D 입체 발광 탄두 및 다층 발광 궤적 생성"""
        head_np = self.world_root.attachNewNode("tracer_head")
        head_np.setPos(muzzle_world)
        head_np.lookAt(muzzle_world + travel_dir)

        head_geom = make_cube_to(head_np, 0.08, 0.38, 0.08, LColor(1.0, 1.0, 0.90, 1.0), 0, 0, 0)
        head_geom.setLightOff()
        head_geom.setTransparency(TransparencyAttrib.MAlpha)
        head_geom.setDepthWrite(False)
        head_geom.setBin("transparent", 105)

        head_w1 = make_cube_to(head_np, 0.20, 0.25, 0.02, LColor(1.0, 0.85, 0.25, 0.85), 0, 0, 0)
        head_w1.setLightOff()
        head_w1.setTransparency(TransparencyAttrib.MAlpha)
        head_w1.setDepthWrite(False)
        head_w1.setBin("transparent", 104)

        head_w2 = make_cube_to(head_np, 0.02, 0.25, 0.20, LColor(1.0, 0.85, 0.25, 0.85), 0, 0, 0)
        head_w2.setLightOff()
        head_w2.setTransparency(TransparencyAttrib.MAlpha)
        head_w2.setDepthWrite(False)
        head_w2.setBin("transparent", 104)

        init_len = min(3.0, total_dist * 0.35)
        c_core = (0.50, 0.95, 1.0, 0.98) if is_overcharge else (1.0, 1.0, 0.90, 0.98)
        c_glow = (0.15, 0.70, 1.0, 0.85) if is_overcharge else (1.0, 0.75, 0.15, 0.75)
        c_halo = (0.05, 0.45, 0.95, 0.45) if is_overcharge else (1.0, 0.35, 0.05, 0.35)
        th_core = 6.0 if is_overcharge else 4.5
        th_glow = 12.0 if is_overcharge else 9.5
        th_halo = 22.0 if is_overcharge else 18.0

        ls_core = LineSegs("tracer_core")
        ls_core.setThickness(th_core)
        ls_core.setColor(*c_core)
        ls_core.moveTo(muzzle_world)
        ls_core.drawTo(muzzle_world + travel_dir * init_len)
        core_np = self.world_root.attachNewNode(ls_core.create())
        core_np.setLightOff()
        core_np.setTransparency(TransparencyAttrib.MAlpha)
        core_np.setDepthWrite(False)
        core_np.setBin("transparent", 102)

        ls_glow = LineSegs("tracer_glow")
        ls_glow.setThickness(th_glow)
        ls_glow.setColor(*c_glow)
        ls_glow.moveTo(muzzle_world)
        ls_glow.drawTo(muzzle_world + travel_dir * (init_len * 0.85))
        glow_np = self.world_root.attachNewNode(ls_glow.create())
        glow_np.setLightOff()
        glow_np.setTransparency(TransparencyAttrib.MAlpha)
        glow_np.setDepthWrite(False)
        glow_np.setBin("transparent", 101)

        ls_halo = LineSegs("tracer_halo")
        ls_halo.setThickness(th_halo)
        ls_halo.setColor(*c_halo)
        ls_halo.moveTo(muzzle_world)
        ls_halo.drawTo(muzzle_world + travel_dir * (init_len * 0.65))
        halo_np = self.world_root.attachNewNode(ls_halo.create())
        halo_np.setLightOff()
        halo_np.setTransparency(TransparencyAttrib.MAlpha)
        halo_np.setDepthWrite(False)
        halo_np.setBin("transparent", 100)

        flight_speed = max(145.0, min(220.0, total_dist * 8.0))

        self.active_tracers.append({
            "is_overcharge": is_overcharge,
            "c_core": c_core,
            "c_glow": c_glow,
            "c_halo": c_halo,
            "th_core": th_core,
            "th_glow": th_glow,
            "th_halo": th_halo,
            "head_node": head_np,
            "core": core_np,
            "glow": glow_np,
            "halo": halo_np,
            "flash": None,
            "np": core_np,
            "start": Vec3(muzzle_world),
            "end": Vec3(impact_world),
            "dir": travel_dir,
            "total_dist": total_dist,
            "tracer_len": init_len,
            "traveled": 0.0,
            "speed": flight_speed,
            "life": 0.32,
            "phase": "fly",
            "fade_timer": 0.08,
            "fade_duration": 0.08
        })

    def _perform_raycast(self, ray_dir, muzzle_world, monsters, player, hazard_barrels, is_overcharge, cfg, p_idx=0):
        """단일 펠릿/탄환에 대한 레이캐스트, 적중 판정, 트레이서 생성 및 대미지 처리"""
        ray_origin = self.camera.getPos()
        chunks = getattr(self.base, 'chunks', {})
        wall_dist, wall_hit_pos = raycast_walls(chunks, ray_origin, ray_dir, max_dist=55.0)

        closest_monster = None
        closest_barrel = None
        min_hit_dist = wall_dist

        if hazard_barrels:
            for b in hazard_barrels:
                if getattr(b, 'is_destroyed', False):
                    continue
                is_hit, hit_dist = b.is_hit_by_ray(ray_origin, ray_dir)
                if is_hit and hit_dist < min_hit_dist:
                    min_hit_dist = hit_dist
                    closest_barrel = b

        monster_list = monsters if isinstance(monsters, (list, tuple)) else [monsters]
        for m in monster_list:
            if getattr(m, 'hp', 1) <= 0:
                continue
            is_hit, hit_dist = m.is_hit_by_ray(ray_origin, ray_dir)
            if is_hit and hit_dist < min_hit_dist:
                min_hit_dist = hit_dist
                closest_monster = m
                closest_barrel = None

        is_crit = False
        is_dead = False
        did_hit = False

        if closest_barrel is not None:
            tracer_dist = min_hit_dist
            impact_world = ray_origin + ray_dir * tracer_dist
            self.spawn_hit_particles(impact_world, is_blood=False)
            closest_barrel.ignite()
            did_hit = True
            is_crit = True
            is_dead = True

        elif closest_monster is not None:
            tracer_dist = min_hit_dist
            impact_world = ray_origin + ray_dir * tracer_dist
            did_hit = True

            blackout_active = getattr(self.base, 'blackout_active', False)
            if player and hasattr(player, 'get_attack_power'):
                base_atk = player.get_attack_power(blackout_active=blackout_active)
            else:
                base_atk = getattr(player, 'attack_power', 35.0) if player else 35.0

            # 무기별 고유 대미지 및 펠릿 계수 반영
            ratio = cfg["damage"] / 35.0
            dmg = base_atk * ratio

            is_sliding = bool(player and getattr(player, 'is_sliding', False))
            is_headshot = bool(getattr(closest_monster, 'last_hit_was_head', False))
            is_crit = is_headshot or is_sliding

            if is_crit:
                dmg *= cfg["headshot_mult"] if is_headshot else 1.85
                if is_headshot and player and hasattr(player, 'has_perk') and player.has_perk("headhunter"):
                    dmg *= 1.45  # 헤드헌터 퍽: 헤드샷 치명타 피해 +45% 증폭

            # 아드레날린 슬라이딩 퍽: 슬라이딩 중 사격 시 피해 1.5배 증폭 & 불릿타임
            if is_sliding and player and hasattr(player, 'has_perk') and player.has_perk("adrenaline_slide"):
                dmg *= 1.50
                game_inst = getattr(self.base, 'game', None) or self.base
                if hasattr(game_inst, 'trigger_bullet_time'):
                    game_inst.trigger_bullet_time(1.8)
                if p_idx == 0:
                    self.ui_mgr.show_hit_marker("⏱ [아드레날린 슬라이드 샷!] 피해 1.5x & 불릿타임!", (0.35, 1.0, 0.8, 1.0))

            # 샷건 원거리 탄속/운동에너지 감쇄 (7.0m 초과 시 점진적 감쇄, 22.0m 이상에서 최대 40%까지 감소)
            if cfg.get("pellets", 1) > 1 and tracer_dist > 7.0:
                falloff_factor = max(0.40, 1.0 - (tracer_dist - 7.0) / 25.0)
                dmg *= falloff_factor

            knockback_chance = 0.85 if is_crit else (0.50 if cfg["pellets"] > 1 else 0.28)
            has_knockback = (random.random() < knockback_chance)

            prev_m_hp = getattr(closest_monster, 'hp', 1)
            prev_max_hp = getattr(closest_monster, 'max_hp', 100)

            is_dead = closest_monster.take_damage(dmg, apply_knockback=has_knockback, hit_dir=ray_dir)
            m_name = getattr(closest_monster, 'name', '괴물')

            # 몬스터 회피 성공 판정 (지옥의 파수견 등)
            if getattr(closest_monster, 'last_action_dodged', False):
                closest_monster.last_action_dodged = False
                self.spawn_hit_particles(impact_world, is_blood=False)
                if p_idx == 0:
                    self.ui_mgr.show_hit_marker("<< [파수견 뼈 도약 회피!] DODGE >>", (0.35, 0.95, 1.0, 1.0))
                    if self.audio_mgr and hasattr(self.audio_mgr, 'play_hound_dodge'):
                        self.audio_mgr.play_hound_dodge()
                return did_hit, False, False

            self.spawn_hit_particles(impact_world, is_blood=True)

            # 드래곤 브레스 퍽: 지속 화염 피해 상태이상 부여
            if player and hasattr(player, 'has_perk') and player.has_perk("dragons_breath"):
                closest_monster.burn_timer = 3.0
                closest_monster.burn_dps = 25.0
                if p_idx == 0:
                    self.ui_mgr.show_hit_marker("🔥 [드래곤 브레스 착탄!] 지속 화염 피해!", (1.0, 0.45, 0.15, 1.0))

            # 흡혈 탄환 퍽: 헤드샷 치명타 적중 시 체력 +5 회복
            if is_headshot and player and hasattr(player, 'has_perk') and player.has_perk("vampiric_leech"):
                player.heal(5.0)

            # 테슬라 아크 퍽: 치명타 시 주변 2체 연쇄 감전
            if is_crit and player and hasattr(player, 'has_perk') and player.has_perk("tesla_arc") and p_idx == 0:
                shocked = 0
                for om in monster_list:
                    if om != closest_monster and getattr(om, 'hp', 0) > 0 and not getattr(om, 'is_corpse', False):
                        if (om.pos - impact_world).length() <= 6.0:
                            om.take_damage(35.0, apply_knockback=True, hit_dir=(om.pos - impact_world).normalized())
                            om.stun(0.40)
                            shocked += 1
                            if shocked >= 2:
                                break
                if shocked > 0:
                    self.ui_mgr.show_hit_marker(f"[★ 테슬라 아크!] {shocked}체 연쇄 방전 감전!", (0.4, 0.9, 1.0, 1.0))

            # 장갑 관통탄 퍽: 몬스터를 관통하여 후방의 적 추가 타격
            if player and hasattr(player, 'has_perk') and player.has_perk("armor_piercing"):
                pierce_origin = impact_world + ray_dir * 0.4
                sec_monster = None
                sec_dist = 20.0
                for m2 in monster_list:
                    if m2 != closest_monster and getattr(m2, 'hp', 0) > 0 and not getattr(m2, 'is_corpse', False):
                        hit2, dist2 = m2.is_hit_by_ray(pierce_origin, ray_dir)
                        if hit2 and dist2 < sec_dist:
                            sec_dist = dist2
                            sec_monster = m2
                if sec_monster is not None:
                    sec_dead = sec_monster.take_damage(dmg, apply_knockback=True, hit_dir=ray_dir)
                    sec_impact = pierce_origin + ray_dir * sec_dist
                    self.spawn_hit_particles(sec_impact, is_blood=True)
                    if sec_dead:
                        self.register_kill(player=player)
                        if hasattr(sec_monster, 'turn_into_corpse'):
                            sec_monster.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player:
                            player.gain_exp(getattr(sec_monster, 'exp_value', 35))
                    if p_idx == 0:
                        self.ui_mgr.show_hit_marker("🎯 [장갑 관통탄 적중!] 후방 적 관통 타격!", (0.4, 0.85, 1.0, 1.0))

            if player and hasattr(player, 'recover_stamina'):
                gain = 24.0 if is_crit else 10.0
                if is_dead:
                    gain += 16.0
                player.recover_stamina(gain / max(1, cfg["pellets"] if cfg["pellets"] > 1 else 1))

            if is_crit and p_idx == 0:
                if is_headshot and self.audio_mgr and hasattr(self.audio_mgr, 'play_headshot_crunch'):
                    self.audio_mgr.play_headshot_crunch()
                elif self.audio_mgr:
                    self.audio_mgr.play_crit_hit()
                if is_headshot and hasattr(closest_monster, 'stun_timer'):
                    closest_monster.stun_timer = max(closest_monster.stun_timer, 0.40)

            if is_dead:
                self.register_kill(player=player)
                is_execution = (prev_m_hp <= prev_max_hp * 0.35) or is_crit or (min_hit_dist <= 5.5)
                if is_execution:
                    self.ammo = min(self.max_ammo, self.ammo + (1 if cfg["pellets"] > 1 else 2))
                    self.update_ammo_ui()
                    if player and hasattr(player, 'recover_stamina'):
                        player.recover_stamina(60.0)
                    self.ui_mgr.show_hit_marker(f"! [처형!] {cfg['name']} 탄약 환급 & 기력 충전 !", (0.35, 1.0, 0.65, 0.95))

                exp_gain = getattr(closest_monster, 'exp_value', 35)
                if is_sliding:
                    exp_gain += 75
                    game_inst = getattr(self.base, 'game', None) or self.base
                    if hasattr(game_inst, 'trigger_bullet_time'):
                        game_inst.trigger_bullet_time(2.0)
                    self.ammo = min(self.max_ammo, self.ammo + 2)
                    self.update_ammo_ui()
                    if hasattr(self.ui_mgr, 'show_style_kill'):
                        self.ui_mgr.show_style_kill("[ ★ SLIDE EXECUTION! ★ ]", "슬라이드 킬! 불릿타임 2.0s & 탄약 환급!", color=(0.35, 1.0, 0.65, 1.0))

                if getattr(closest_monster, 'is_elite', False):
                    exp_gain += 150
                    self.activate_overcharge(6)
                    game_inst = getattr(self.base, 'game', None) or self.base
                    if hasattr(game_inst, 'trigger_bullet_time'):
                        game_inst.trigger_bullet_time(3.5)
                    if self.audio_mgr and hasattr(self.audio_mgr, 'play_elite_kill'):
                        self.audio_mgr.play_elite_kill()
                    if hasattr(self.ui_mgr, 'show_style_kill'):
                        self.ui_mgr.show_style_kill("[ ★ 정예 변이 괴물 토벌! ★ ]", f"{m_name} 격파! 오버차지 6발 & 불릿타임!", color=(1.0, 0.85, 0.15, 1.0))

                if self.combo_count >= 2:
                    exp_gain = int(exp_gain * (1.0 + 0.25 * min(self.combo_count, 6)))

                if blackout_active:
                    exp_gain *= 2
                    self._reserve_ammo += (4 if cfg["pellets"] > 1 else 6)
                    self.update_ammo_ui()

                if player and hasattr(player, 'relics') and "blood_thirst" in player.relics:
                    player.heal(12.0)

                # 흡혈 탄환 퍽: 처치 시 체력 +12 회복
                if player and hasattr(player, 'has_perk') and player.has_perk("vampiric_leech"):
                    player.heal(12.0)
                    self.ui_mgr.show_hit_marker("🩸 [흡혈 탄환!] 체력 +12 회복", (0.35, 1.0, 0.45, 1.0))

                # 탄환 폭풍 퍽: 처치 시 3.5초간 무한 연사 폭주
                if player and hasattr(player, 'has_perk') and player.has_perk("bullet_storm"):
                    self.bullet_storm_timer = 3.5
                    self.ui_mgr.show_hit_marker("🌪 [탄환 폭풍 발동!] 3.5초간 무한 연사 폭주! 🌪", (1.0, 0.85, 0.2, 1.0))

                # 파편 폭발 퍽: 처치 시 고열 파편 비산 범위 폭발
                if player and hasattr(player, 'has_perk') and player.has_perk("shrapnel_burst"):
                    game_inst = getattr(self.base, 'game', None) or self.base
                    exp_list = getattr(game_inst, 'explosions', None)
                    if exp_list is not None:
                        exp_list.append(ExplosionVisualEffect(self.world_root, impact_world, self.render))
                    for som in monster_list:
                        if som != closest_monster and getattr(som, 'hp', 0) > 0 and not getattr(som, 'is_corpse', False):
                            s_dist = (som.pos - impact_world).length()
                            if s_dist <= 3.8:
                                s_dmg = 75.0 * (1.0 - s_dist / 3.8 * 0.40)
                                s_dead = som.take_damage(s_dmg, apply_knockback=True, hit_dir=(som.pos - impact_world).normalized())
                                if s_dead:
                                    self.register_kill(player=player)
                                    if hasattr(som, 'turn_into_corpse'):
                                        som.turn_into_corpse(audio_mgr=self.audio_mgr)
                                    if player:
                                        player.gain_exp(getattr(som, 'exp_value', 35))
                    self.ui_mgr.show_hit_marker("💥 [파편 폭발!] 고열 파편 비산 범위 타격! 💥", (1.0, 0.55, 0.2, 1.0))

                # 헤드헌터 퍽: 헤드샷 처치 시 경험치 2배
                if is_headshot and player and hasattr(player, 'has_perk') and player.has_perk("headhunter"):
                    exp_gain *= 2

                if hasattr(closest_monster, 'turn_into_corpse'):
                    closest_monster.turn_into_corpse(audio_mgr=self.audio_mgr)
                if player:
                    player.gain_exp(exp_gain)

            if self.audio_mgr and p_idx == 0:
                if "뱀" in m_name:
                    self.audio_mgr.play_serpent_hit()
                elif "해골" in m_name:
                    self.audio_mgr.play_skeleton_hit()
                elif "오크" in m_name:
                    self.audio_mgr.play_gunshot()
                else:
                    self.audio_mgr.play_serpent_hit()

        elif wall_hit_pos is not None:
            tracer_dist = wall_dist
            impact_world = wall_hit_pos
            self.spawn_hit_particles(impact_world, is_blood=False)

            # 도탄 사격 퍽: 벽면에 맞은 탄환이 반경 14m 이내의 최근접 몬스터로 도탄
            if player and hasattr(player, 'has_perk') and player.has_perk("ricochet"):
                rico_target = None
                rico_min_d = 14.0
                for rm in monster_list:
                    if getattr(rm, 'hp', 0) > 0 and not getattr(rm, 'is_corpse', False):
                        d_rico = (rm.pos - wall_hit_pos).length()
                        if d_rico < rico_min_d:
                            rico_min_d = d_rico
                            rico_target = rm
                if rico_target is not None:
                    rico_dir = (rico_target.pos - wall_hit_pos).normalized()
                    rico_dmg = cfg["damage"] * 0.70
                    r_dead = rico_target.take_damage(rico_dmg, apply_knockback=True, hit_dir=rico_dir)
                    self.spawn_hit_particles(rico_target.pos, is_blood=True)
                    self._spawn_tracer_effect(wall_hit_pos, rico_target.pos, rico_dir, rico_min_d, is_overcharge=True)
                    if r_dead:
                        self.register_kill(player=player)
                        if hasattr(rico_target, 'turn_into_corpse'):
                            rico_target.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player:
                            player.gain_exp(getattr(rico_target, 'exp_value', 35))
                    if p_idx == 0:
                        self.ui_mgr.show_hit_marker("[◆ 도탄 사격 적중!] RICOCHET!", (0.3, 0.9, 1.0, 1.0))
        else:
            tracer_dist = 55.0
            impact_world = ray_origin + ray_dir * tracer_dist

        # 오버차지 고폭 플라즈마 소이탄 착탄 시 폭발
        if is_overcharge:
            game_inst = getattr(self.base, 'game', None) or self.base
            exp_list = getattr(game_inst, 'explosions', None)
            if exp_list is not None:
                exp_list.append(ExplosionVisualEffect(self.world_root, impact_world, self.render))
            if player and hasattr(player, 'trigger_quake_shake'):
                player.trigger_quake_shake(intensity=3.2, duration=0.45)

            for m in monster_list:
                if getattr(m, 'hp', 0) <= 0 or (m == closest_monster and is_dead):
                    continue
                m_dist = (m.pos - impact_world).length()
                if m_dist <= 3.4:
                    splash_dmg = 85.0 * (1.0 - m_dist / 3.4 * 0.45)
                    s_dead = m.take_damage(splash_dmg, apply_knockback=True, hit_dir=(m.pos - impact_world).normalized() if m_dist > 0.1 else ray_dir)
                    if s_dead:
                        self.register_kill(player=player)
                        if getattr(m, 'is_elite', False):
                            self.activate_overcharge(6)
                            if hasattr(game_inst, 'trigger_bullet_time'):
                                game_inst.trigger_bullet_time(3.5)
                            if self.audio_mgr and hasattr(self.audio_mgr, 'play_elite_kill'):
                                self.audio_mgr.play_elite_kill()
                        if hasattr(m, 'turn_into_corpse'):
                            m.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player:
                            player.gain_exp(getattr(m, 'exp_value', 35))

            if hazard_barrels:
                for b in hazard_barrels:
                    if not getattr(b, 'is_destroyed', False) and b != closest_barrel:
                        if (b.pos - impact_world).length() <= 3.8:
                            b.ignite()

        # 트레이서 생성
        travel_vec = impact_world - muzzle_world
        t_dist = travel_vec.length()
        t_dir = travel_vec / t_dist if t_dist > 0.1 else ray_dir
        self._spawn_tracer_effect(muzzle_world, impact_world, t_dir, max(1.0, t_dist), is_overcharge)

        return is_crit, is_dead, did_hit

    def shoot(self, monsters, player=None, game_state="PLAYING", hazard_barrels=None):
        """다양한 총기(권총, 아킴보 쌍권총, 12게이지 샷건) 사격 및 레이캐스트 적중 판정"""
        if game_state != "PLAYING" or self.is_reloading or self.shoot_cooldown > 0.0:
            return

        cfg = WEAPON_CONFIGS[self.current_weapon]

        # 탄약이 차 있는데 슬라이드가 잠겨있는 불일치 상태 자동 해제
        if self.ammo > 0 and self.slide_locked:
            self.slide_locked = False
            if hasattr(self, 'slide_node') and not self.slide_node.isEmpty():
                self.slide_node.setPos(0, 0, 0)

        if self.slide_locked or self.ammo <= 0:
            if self.audio_mgr:
                self.audio_mgr.play_empty_click()
            if self._reserve_ammo > 0:
                self.ui_mgr.show_hit_marker("탄약 소진! [R] 키로 재장전하세요!", (1.0, 0.4, 0.4, 1.0))
            else:
                self.ui_mgr.show_hit_marker("탄약 소진! (맵에서 탄약 상자를 찾으세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            self.shoot_cooldown = 0.35
            return

        # 오버차지 판정
        is_overcharge = (self.overcharge_rounds > 0)
        if is_overcharge:
            self.overcharge_rounds -= 1

        # 콤보 상태 및 탄환 폭풍 퍽에 따른 탄약 절약 판정
        in_bullet_storm = (getattr(self, 'bullet_storm_timer', 0.0) > 0.0)
        free_ammo = in_bullet_storm or (self.combo_count >= 4 and random.random() < 0.30)
        if not free_ammo:
            self.ammo -= 1

        # 쿨다운 & 반동 시간 설정
        cd = cfg["combo_cooldown"] if self.combo_count >= 2 else cfg["cooldown"]
        if in_bullet_storm:
            cd *= 0.65  # 탄환 폭풍 퍽 활성화 시 연사 속도 +35% 극대화
        self.shoot_cooldown = cd
        self.recoil_timer = cfg["recoil_time"]
        self.muzzle_timer = 0.05

        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()
        cam_pos = self.camera.getPos()

        # 1. 무기별 고유 격발 애니메이션, 탄피 배출, 음향
        if self.current_weapon == "PISTOL":
            self.slide_timer = self.slide_blowback_duration
            self.hammer_timer = 0.04
            if hasattr(self, 'hammer_node') and not self.hammer_node.isEmpty():
                self.hammer_node.setP(0)
            self._eject_casing(is_left=False, is_shotgun=False)
            self._spawn_barrel_smoke()

            if hasattr(self, 'muzzle_flash_geom') and not self.muzzle_flash_geom.isEmpty():
                self.muzzle_flash_geom.setR(random.uniform(0, 360))
                self.muzzle_flash_geom.setScale(random.uniform(0.9, 1.3) * (1.35 if is_overcharge else 1.0))
                self.muzzle_flash_geom.show()
            if is_overcharge:
                self.muzzle_light.setColor((1.2, 3.8, 5.0, 1.0))
            else:
                self.muzzle_light.setColor((3.5, 2.2, 0.6, 1.0))
            self.render.setLight(self.muzzle_light_np)

            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if is_overcharge and hasattr(self.audio_mgr, 'play_overcharge_shot'):
                    self.audio_mgr.play_overcharge_shot()
                else:
                    self.audio_mgr.play_gunshot()

            if hasattr(self, 'muzzle_flash_geom') and not self.muzzle_flash_geom.isEmpty():
                muzzle_world = self.muzzle_flash_geom.getPos(self.render)
            else:
                muzzle_world = cam_pos + cam_fwd * 0.75 + cam_right * (0.20 * (1.0 - self.ads_alpha)) - cam_up * 0.16

        elif self.current_weapon == "DUAL_PISTOL":
            hand = self.dual_hand_toggle
            self.dual_hand_toggle = 1 - self.dual_hand_toggle
            is_left = (hand == 1)

            if is_left:
                self.slide_timer_left = self.slide_blowback_duration
                self._eject_casing(is_left=True, is_shotgun=False)
                if hasattr(self, 'dual_left_flash_geom') and not self.dual_left_flash_geom.isEmpty():
                    self.dual_left_flash_geom.setR(random.uniform(0, 360))
                    self.dual_left_flash_geom.show()
                self.render.setLight(self.dual_left_flash_light_np)
                muzzle_world = self.dual_left_flash_geom.getPos(self.render) if (hasattr(self, 'dual_left_flash_geom') and not self.dual_left_flash_geom.isEmpty()) else (cam_pos + cam_fwd * 0.70 - cam_right * 0.16 - cam_up * 0.16)
            else:
                self.slide_timer_right = self.slide_blowback_duration
                self._eject_casing(is_left=False, is_shotgun=False)
                if hasattr(self, 'dual_right_flash_geom') and not self.dual_right_flash_geom.isEmpty():
                    self.dual_right_flash_geom.setR(random.uniform(0, 360))
                    self.dual_right_flash_geom.show()
                self.render.setLight(self.dual_right_flash_light_np)
                muzzle_world = self.dual_right_flash_geom.getPos(self.render) if (hasattr(self, 'dual_right_flash_geom') and not self.dual_right_flash_geom.isEmpty()) else (cam_pos + cam_fwd * 0.70 + cam_right * 0.16 - cam_up * 0.16)

            self._spawn_barrel_smoke(offset_x=-0.14 if is_left else 0.14)
            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if is_overcharge and hasattr(self.audio_mgr, 'play_overcharge_shot'):
                    self.audio_mgr.play_overcharge_shot()
                else:
                    self.audio_mgr.play_gunshot()

        elif self.current_weapon == "SHOTGUN":
            self.sg_pump_timer = 0.44
            self.sg_pump_cycled = False
            self._spawn_barrel_smoke(offset_y=0.45)

            if hasattr(self, 'sg_muzzle_flash_geom') and not self.sg_muzzle_flash_geom.isEmpty():
                self.sg_muzzle_flash_geom.setR(random.uniform(0, 360))
                self.sg_muzzle_flash_geom.setScale(random.uniform(1.2, 1.6) * (1.35 if is_overcharge else 1.0))
                self.sg_muzzle_flash_geom.show()
            if is_overcharge:
                self.sg_muzzle_light.setColor((1.5, 4.0, 5.5, 1.0))
            else:
                self.sg_muzzle_light.setColor((4.5, 2.8, 0.8, 1.0))
            self.render.setLight(self.sg_muzzle_light_np)

            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if is_overcharge and hasattr(self.audio_mgr, 'play_overcharge_shot'):
                    self.audio_mgr.play_overcharge_shot()
                elif hasattr(self.audio_mgr, 'play_shotgun_blast'):
                    self.audio_mgr.play_shotgun_blast()
                else:
                    self.audio_mgr.play_gunshot()

            if hasattr(self, 'sg_muzzle_flash_geom') and not self.sg_muzzle_flash_geom.isEmpty():
                muzzle_world = self.sg_muzzle_flash_geom.getPos(self.render)
            else:
                muzzle_world = cam_pos + cam_fwd * 0.85 + cam_right * (0.18 * (1.0 - self.ads_alpha)) - cam_up * 0.18

        # 상태 동기화 및 UI 갱신
        self.weapon_states[self.current_weapon]["ammo"] = self.ammo
        self.weapon_states[self.current_weapon]["reserve_ammo"] = self._reserve_ammo
        self.weapon_states[self.current_weapon]["slide_locked"] = self.slide_locked
        self.update_ammo_ui()

        # 2. 탄퍼짐 및 크로스헤어 킥
        is_moving = getattr(player, 'is_moving', False) or getattr(self, 'is_moving', False)
        is_sprinting = getattr(player, 'is_sprinting', False) or getattr(self, 'is_sprinting', False)
        is_sliding = getattr(player, 'is_sliding', False)

        base_spread = cfg["ads_spread"] if self.ads_alpha >= 0.85 else cfg["base_spread"]
        if self.ads_alpha < 0.85:
            if is_sprinting or is_sliding:
                base_spread *= 2.0 if self.current_weapon == "PISTOL" else 2.2
            elif is_moving:
                base_spread *= 1.2 if self.current_weapon == "PISTOL" else 1.5
            base_spread += getattr(self, 'hipfire_bloom', 0.0)

            # 무기별 블룸 증가량 차별화 (전술권총은 극도로 안정적, 아킴보는 난사 시 팽창)
            if self.current_weapon == "PISTOL":
                bloom_add = 0.005
                max_bloom = 0.035
            elif self.current_weapon == "DUAL_PISTOL":
                bloom_add = 0.024
                max_bloom = 0.095
            else: # SHOTGUN
                bloom_add = 0.015
                max_bloom = 0.080
            self.hipfire_bloom = min(max_bloom, getattr(self, 'hipfire_bloom', 0.0) + bloom_add)

        kick_bloom = 1.35 if cfg["pellets"] > 1 else (0.45 if self.current_weapon == "PISTOL" else 0.85)
        shake_mag = 0.048 if cfg["pellets"] > 1 else (0.018 if self.current_weapon == "PISTOL" else 0.028)
        if hasattr(self.ui_mgr, 'trigger_hipfire_kick'):
            self.ui_mgr.trigger_hipfire_kick(kick_bloom=kick_bloom, shake_mag=shake_mag, shake_dur=0.18)

        # 3. 펠릿별 레이캐스트 순회
        pellet_count = cfg["pellets"]
        any_crit = False
        any_kill = False
        any_hit = False

        for p_i in range(pellet_count):
            if base_spread <= 0.0:
                ray_dir = cam_fwd
            else:
                ang = random.uniform(0.0, 2.0 * math.pi)
                rad = (random.uniform(0.0, 1.0) ** 0.5) * base_spread
                def_x = math.cos(ang) * rad
                def_y = math.sin(ang) * rad
                ray_dir = (cam_fwd + cam_right * def_x + cam_up * def_y).normalized()

            h_crit, h_kill, d_hit = self._perform_raycast(
                ray_dir, muzzle_world, monsters, player, hazard_barrels, is_overcharge, cfg, p_i
            )
            if h_crit:
                any_crit = True
            if h_kill:
                any_kill = True
            if d_hit:
                any_hit = True

        if any_hit:
            self.ui_mgr.trigger_crosshair_hit(is_kill=any_kill, is_crit=any_crit)

    def spawn_hit_particles(self, hit_pos, is_blood=True):
        """총탄이 몬스터에 적중했을 때 사방으로 분출되는 3D 핏빛/스파크 파티클 버스트 (오브젝트 풀 재사용)"""
        col = LColor(0.72, 0.04, 0.04, 1.0) if is_blood else LColor(1.0, 0.85, 0.25, 1.0)
        pool_len = len(self.hit_particle_pool)
        for _ in range(12):
            p = self.hit_particle_pool[self.hit_particle_cursor]
            self.hit_particle_cursor = (self.hit_particle_cursor + 1) % pool_len

            p["cube"].setColor(col)
            p["pos"] = Vec3(hit_pos)
            p["vel"] = Vec3(random.uniform(-3.2, 3.2), random.uniform(-3.2, 3.2), random.uniform(1.2, 4.2))
            p["timer"] = 0.38
            p["active"] = True

            p["node"].setPos(hit_pos)
            p["node"].setScale(1.0)
            p["node"].show()

    def apply_upgrade(self, upgrade_type):
        """탄약 계열 특성 강화 (모든 무기 탄창 및 예비탄 대폭 증설)"""
        if upgrade_type == "AMMO":
            self.weapon_states["PISTOL"]["max_ammo"] += 6
            self.weapon_states["PISTOL"]["reserve_ammo"] += 36
            self.weapon_states["PISTOL"]["ammo"] = self.weapon_states["PISTOL"]["max_ammo"]

            self.weapon_states["DUAL_PISTOL"]["max_ammo"] += 12
            self.weapon_states["DUAL_PISTOL"]["reserve_ammo"] += 48
            self.weapon_states["DUAL_PISTOL"]["ammo"] = self.weapon_states["DUAL_PISTOL"]["max_ammo"]

            self.weapon_states["SHOTGUN"]["max_ammo"] += 4
            self.weapon_states["SHOTGUN"]["reserve_ammo"] += 16
            self.weapon_states["SHOTGUN"]["ammo"] = self.weapon_states["SHOTGUN"]["max_ammo"]

            cur_st = self.weapon_states[self.current_weapon]
            self.max_ammo = cur_st["max_ammo"]
            self.ammo = cur_st["ammo"]
            self._reserve_ammo = cur_st["reserve_ammo"]

            self.update_ammo_ui()
            self.ui_mgr.show_hit_marker("[특성 강화] 전 무기 최대 탄창 확장 및 전탄 즉시 보급!", (1.0, 0.85, 0.2, 1.0))

    def reload(self, game_state="PLAYING"):
        """R 키 입력 시 현재 무기 전술 재장전 (권총 / 아킴보 쌍권총 / 12게이지 샷건)"""
        if game_state != "PLAYING" or self.is_reloading:
            return

        cfg = WEAPON_CONFIGS[self.current_weapon]
        wstate = self.weapon_states[self.current_weapon]

        # 만약 슬라이드가 후퇴 고정된 상태인데 탄약이 이미 가득 차 있다면, 슬라이드 멈치만 즉시 전진 복구
        if self.slide_locked and self.ammo >= self.max_ammo:
            self.slide_locked = False
            wstate["slide_locked"] = False
            self.slide_timer = 0.0
            if hasattr(self, 'slide_node') and self.slide_node and not self.slide_node.isEmpty():
                self.slide_node.setPos(0, 0, 0)
            if hasattr(self, 'hammer_node') and self.hammer_node and not self.hammer_node.isEmpty():
                self.hammer_node.setP(-42)
            if self.audio_mgr:
                self.audio_mgr.play_reload()
            self.ui_mgr.show_hit_marker("슬라이드 전진 완료! 격발 준비 완료", (0.35, 1.0, 0.5, 1.0))
            self.hit_marker_timer = 1.0
            return

        if self.ammo >= self.max_ammo:
            return

        if self._reserve_ammo <= 0:
            if self.audio_mgr:
                self.audio_mgr.play_empty_click()
            self.ui_mgr.show_hit_marker("예비 탄약이 없습니다! (탄약 상자를 탐색하세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            return

        self.is_reloading = True
        base_reload_time = cfg.get("reload_time", 1.30)
        player = getattr(self.base, 'player', None)
        if player and hasattr(player, 'has_perk') and player.has_perk("speed_demon"):
            base_reload_time *= 0.65  # 스피드 데몬 퍽: 재장전 시간 35% 가속
        self.reload_timer = base_reload_time
        self.was_slide_locked_before_reload = self.slide_locked

        if self.audio_mgr:
            if self.current_weapon == "SHOTGUN" and hasattr(self.audio_mgr, 'play_shotgun_pump'):
                self.audio_mgr.play_shotgun_pump()
            else:
                self.audio_mgr.play_reload()

        if self.current_weapon == "SHOTGUN":
            status_msg = "12게이지 벅샷 쉘 연속 삽탄 및 펌프 장전 중..."
        elif self.current_weapon == "DUAL_PISTOL":
            status_msg = "아킴보 양손 탄창 동시 교체 중... (장전 지연 2.6s)"
        else:
            status_msg = "9mm 택티컬 전술 탄창 교체 중..."
        self.ui_mgr.show_hit_marker(status_msg, (0.9, 0.9, 0.9, 1.0))
        self.hit_marker_timer = 1.4

    def setup_ammo_drops(self, current_stage=1):
        """스테이지 2부터 맵 복도에 3D 밀리터리 탄약 상자 드랍"""
        for d in self.ammo_drops:
            if d.get("light_np") and not d["light_np"].isEmpty():
                self.render.clearLight(d["light_np"])
            if d.get("node") and not d["node"].isEmpty():
                d["node"].removeNode()
        self.ammo_drops = []

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
                    d = math.hypot(cx - spawn_x, cy - spawn_y)
                    if d >= 20.0:
                        candidates.append((cx, cy))

        if not candidates:
            return

        drop_count = min(6, len(candidates))
        chosen_positions = random.sample(candidates, drop_count)

        olive_box = LColor(0.20, 0.32, 0.18, 1.0)
        steel_latch = LColor(0.28, 0.28, 0.32, 1.0)
        brass_bullet = LColor(0.95, 0.82, 0.22, 1.0)

        for x, y in chosen_positions:
            drop_np = self.world_root.attachNewNode("ammo_crate")
            drop_np.setPos(x, y, 0.18)

            make_cube_to(drop_np, 0.50, 0.32, 0.28, olive_box, 0, 0, 0)
            make_cube_to(drop_np, 0.52, 0.34, 0.05, steel_latch, 0, 0, 0.16)
            make_cube_to(drop_np, 0.08, 0.36, 0.08, steel_latch, 0, 0, 0)
            b1 = make_cube_to(drop_np, 0.06, 0.06, 0.14, brass_bullet, -0.12, 0, 0.22)
            b2 = make_cube_to(drop_np, 0.06, 0.06, 0.14, brass_bullet, 0.12, 0, 0.22)
            b1.setLightOff()
            b2.setLightOff()

            drop_light = PointLight('ammo_glow')
            drop_light.setColor((0.65, 0.55, 0.18, 1.0))
            drop_light.setAttenuation((1.0, 0.15, 0.04))
            drop_light_np = drop_np.attachNewNode(drop_light)
            drop_light_np.setPos(0, 0, 0.3)

            self.ammo_drops.append({
                "node": drop_np,
                "light_np": drop_light_np,
                "pos": (x, y),
                "is_lit": False
            })

    def activate_overcharge(self, rounds=6):
        """오버차지 고폭 플라즈마 소이탄 장전"""
        self.overcharge_rounds += rounds
        if self.audio_mgr and hasattr(self.audio_mgr, 'play_power_restored'):
            self.audio_mgr.play_power_restored()
        self.update_ammo_ui()
        if hasattr(self.ui_mgr, 'show_style_kill'):
            self.ui_mgr.show_style_kill("[ ★ OVERCHARGE PROTOCOL ★ ]", f"고폭 플라즈마 소이탄 +{rounds}발 장전!", color=(0.25, 0.95, 1.0, 1.0))

    def register_kill(self, player=None):
        """적 처치 시 킬 콤보 스트릭 등록 및 다이내믹 퍽 활성화"""
        self.combo_count += 1
        self.combo_timer = self.combo_window
        game_inst = getattr(self.base, 'game', None) or self.base

        if self.combo_count == 2:
            if player:
                player.speed_boost_timer = 4.0
                player.recover_stamina(40.0)
            if hasattr(self.ui_mgr, 'show_style_kill'):
                self.ui_mgr.show_style_kill("[ ★ DOUBLE KILL! ★ ]", "이동속도 +30% 오버드라이브 & 기력 회복!", color=(1.0, 0.90, 0.30, 1.0))

        elif self.combo_count == 3:
            self.ammo = self.max_ammo
            self.update_ammo_ui()
            if hasattr(game_inst, 'trigger_bullet_time'):
                game_inst.trigger_bullet_time(2.0)
            if hasattr(self.ui_mgr, 'show_style_kill'):
                self.ui_mgr.show_style_kill("[ ★ TRIPLE KILL! ★ ]", "탄창 무료 완전 재장전 & 불릿타임 2초!", color=(1.0, 0.70, 0.20, 1.0))

        elif self.combo_count == 4:
            self.activate_overcharge(6)
            if hasattr(game_inst, 'trigger_bullet_time'):
                game_inst.trigger_bullet_time(3.5)
            if hasattr(self.ui_mgr, 'show_style_kill'):
                self.ui_mgr.show_style_kill("[ ★ RAMPAGE!! ★ ]", "오버차지 고폭탄 6발 장전 & 불릿타임 3.5초!", color=(1.0, 0.45, 0.15, 1.0))

        elif self.combo_count >= 5:
            self.activate_overcharge(4)
            if hasattr(game_inst, 'trigger_bullet_time'):
                game_inst.trigger_bullet_time(4.0)
            if hasattr(self.ui_mgr, 'show_style_kill'):
                self.ui_mgr.show_style_kill(f"[ ★ CARNAGE x{self.combo_count}!!! ★ ]", "오버차지 지속 & 불릿타임 4초!", color=(1.0, 0.20, 0.20, 1.0))

        if self.combo_count >= 2 and self.audio_mgr and hasattr(self.audio_mgr, 'play_combo_kill'):
            self.audio_mgr.play_combo_kill()

    def reset_state(self, current_stage=1, keep_ammo=False):
        """게임 재시작 및 스테이지 리셋 (모든 총기 상태 및 뷰모델 노드 완전 초기화)"""
        if not keep_ammo:
            for w_id, cfg in WEAPON_CONFIGS.items():
                self.weapon_states[w_id]["ammo"] = cfg["max_ammo"]
                self.weapon_states[w_id]["max_ammo"] = cfg["max_ammo"]
                self.weapon_states[w_id]["reserve_ammo"] = cfg["initial_reserve"]
                self.weapon_states[w_id]["slide_locked"] = False
            self.overcharge_rounds = 0

        cur_st = self.weapon_states[self.current_weapon]
        self.max_ammo = cur_st["max_ammo"]
        self.ammo = cur_st["ammo"]
        self._reserve_ammo = cur_st["reserve_ammo"]
        self.slide_locked = (self.ammo <= 0)
        cur_st["slide_locked"] = self.slide_locked

        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.hipfire_bloom = 0.0
        self.combo_count = 0
        self.combo_timer = 0.0
        self.is_aiming = False
        self.ads_alpha = 0.0
        self.slide_timer = 0.0
        self.slide_timer_left = 0.0
        self.slide_timer_right = 0.0
        self.sg_pump_timer = 0.0
        self.sg_pump_cycled = False
        self.switch_timer = 0.0
        self.dual_hand_toggle = 0
        self.hammer_timer = 0.0
        self.was_slide_locked_before_reload = False

        # 권총 3D 노드 복구
        if hasattr(self, 'slide_node') and self.slide_node and not self.slide_node.isEmpty():
            if self.slide_locked and self.ammo <= 0:
                self.slide_node.setPos(0, self.slide_max_travel, 0)
            else:
                self.slide_node.setPos(0, 0, 0)

        if hasattr(self, 'hammer_node') and self.hammer_node and not self.hammer_node.isEmpty():
            self.hammer_node.setP(-42)
            self.hammer_node.setPos(0, -0.102, 0.038)

        if hasattr(self, 'mag_node') and self.mag_node and not self.mag_node.isEmpty():
            self.mag_node.setPos(0, -0.06, -0.09)
            self.mag_node.setP(16)
            self.mag_node.setScale(1.0)

        if hasattr(self, 'recoil_node') and self.recoil_node and not self.recoil_node.isEmpty():
            self.recoil_node.setPos(0, 0, 0)
            self.recoil_node.setP(0)
            self.recoil_node.setR(0)

        if hasattr(self, 'vm_pistol') and self.vm_pistol and not self.vm_pistol.isEmpty():
            self.vm_pistol.setPos(self.ads_hip_pos)
            self.vm_pistol.setHpr(self.ads_hip_hpr)

        # 아킴보 쌍권총 노드 복구
        if hasattr(self, 'dual_left_slide') and self.dual_left_slide and not self.dual_left_slide.isEmpty():
            self.dual_left_slide.setPos(0, 0, 0)
        if hasattr(self, 'dual_right_slide') and self.dual_right_slide and not self.dual_right_slide.isEmpty():
            self.dual_right_slide.setPos(0, 0, 0)
        if hasattr(self, 'dual_left_recoil') and self.dual_left_recoil and not self.dual_left_recoil.isEmpty():
            self.dual_left_recoil.setPos(0, 0, 0)
            self.dual_left_recoil.setP(0)
            self.dual_left_recoil.setR(0)
        if hasattr(self, 'dual_right_recoil') and self.dual_right_recoil and not self.dual_right_recoil.isEmpty():
            self.dual_right_recoil.setPos(0, 0, 0)
            self.dual_right_recoil.setP(0)
            self.dual_right_recoil.setR(0)
        if hasattr(self, 'vm_dual_left') and self.vm_dual_left and not self.vm_dual_left.isEmpty():
            self.vm_dual_left.setPos(self.ads_hip_pos_dual_l)
            self.vm_dual_left.setHpr(Vec3(4.0, 1.0, 10.0))
        if hasattr(self, 'vm_dual_right') and self.vm_dual_right and not self.vm_dual_right.isEmpty():
            self.vm_dual_right.setPos(self.ads_hip_pos_dual_r)
            self.vm_dual_right.setHpr(Vec3(-4.0, 1.0, -10.0))

        # 샷건 노드 복구
        if hasattr(self, 'sg_pump_node') and self.sg_pump_node and not self.sg_pump_node.isEmpty():
            self.sg_pump_node.setPos(0, 0.28, -0.010)
        if hasattr(self, 'sg_recoil_node') and self.sg_recoil_node and not self.sg_recoil_node.isEmpty():
            self.sg_recoil_node.setPos(0, 0, 0)
            self.sg_recoil_node.setP(0)
            self.sg_recoil_node.setR(0)
        if hasattr(self, 'vm_shotgun') and self.vm_shotgun and not self.vm_shotgun.isEmpty():
            self.vm_shotgun.setPos(self.ads_hip_pos_sg)
            self.vm_shotgun.setHpr(Vec3(1.0, 0.5, -0.5))

        if hasattr(self, 'vm_root') and self.vm_root and not self.vm_root.isEmpty():
            self.vm_root.setPos(0, 0, 0)

        # 총구 화염 소등
        if hasattr(self, 'muzzle_flash_geom') and self.muzzle_flash_geom and not self.muzzle_flash_geom.isEmpty():
            self.muzzle_flash_geom.hide()
            if hasattr(self, 'muzzle_light_np') and self.muzzle_light_np and not self.muzzle_light_np.isEmpty():
                self.render.clearLight(self.muzzle_light_np)
        if hasattr(self, 'dual_left_flash_geom') and self.dual_left_flash_geom and not self.dual_left_flash_geom.isEmpty():
            self.dual_left_flash_geom.hide()
            if hasattr(self, 'dual_left_flash_light_np') and self.dual_left_flash_light_np and not self.dual_left_flash_light_np.isEmpty():
                self.render.clearLight(self.dual_left_flash_light_np)
        if hasattr(self, 'dual_right_flash_geom') and self.dual_right_flash_geom and not self.dual_right_flash_geom.isEmpty():
            self.dual_right_flash_geom.hide()
            if hasattr(self, 'dual_right_flash_light_np') and self.dual_right_flash_light_np and not self.dual_right_flash_light_np.isEmpty():
                self.render.clearLight(self.dual_right_flash_light_np)
        if hasattr(self, 'sg_muzzle_flash_geom') and self.sg_muzzle_flash_geom and not self.sg_muzzle_flash_geom.isEmpty():
            self.sg_muzzle_flash_geom.hide()
            if hasattr(self, 'sg_muzzle_light_np') and self.sg_muzzle_light_np and not self.sg_muzzle_light_np.isEmpty():
                self.render.clearLight(self.sg_muzzle_light_np)

        self._update_viewmodel_visibility()

        for tr in self.active_tracers:
            for key in ("np", "core", "glow", "halo", "head_node", "flash"):
                node = tr.get(key)
                if node and not node.isEmpty():
                    node.removeNode()
        self.active_tracers = []

        # 오브젝트 풀 완전 비활성화 및 화면 소등
        for p in getattr(self, 'hit_particle_pool', []):
            p["active"] = False
            p["node"].hide()
        for c in getattr(self, 'casing_pool', []):
            c["active"] = False
            c["node"].hide()
        for s in getattr(self, 'smoke_pool', []):
            s["active"] = False
            s["node"].hide()

        self.setup_ammo_drops(current_stage)
        self.update_ammo_ui()

    def update_ammo_ui(self):
        """탄약 UI 실시간 동기화 (현재 무기 명칭 및 잔탄 표시)"""
        self.ui_mgr.update_ammo(
            self.ammo,
            self.max_ammo,
            self._reserve_ammo,
            self.overcharge_rounds,
            weapon_name=self.get_weapon_display_name()
        )

    _update_ammo_ui = update_ammo_ui

    def update(self, dt, px=0.0, py=0.0, is_moving=False, is_sprinting=False):
        """프레임별 트레이서, 탄피 물리, 화약 연기, 슬라이드 블로우백, 펌프액션, 반동/재장전, 밥빙, 탄약 습득 갱신"""
        self.is_moving = is_moving
        self.is_sprinting = is_sprinting

        if getattr(self, 'bullet_storm_timer', 0.0) > 0.0:
            self.bullet_storm_timer = max(0.0, self.bullet_storm_timer - dt)

        # 지향사격 연사 탄퍼짐 블룸 부드러운 감쇠
        if hasattr(self, 'hipfire_bloom') and self.hipfire_bloom > 0.0:
            self.hipfire_bloom = max(0.0, self.hipfire_bloom - 0.12 * dt)

        # 실감나는 고시인성 비행 총알 궤적 물리 & 페이드 갱신
        for tr in self.active_tracers[:]:
            tr["life"] -= dt

            # 착탄 섬광 타이머 처리
            if tr.get("flash") and not tr["flash"].isEmpty():
                tr["flash_timer"] = max(0.0, tr.get("flash_timer", 0.0) - dt)
                if tr["flash_timer"] <= 0.0:
                    tr["flash"].removeNode()
                    tr["flash"] = None
                else:
                    scale = max(0.1, tr["flash_timer"] / 0.09)
                    tr["flash"].setScale(scale)

            if tr.get("phase") == "fly":
                move = tr["speed"] * dt
                tr["traveled"] += move
                head_pos = tr["traveled"]
                total_d = tr["total_dist"]

                if head_pos >= total_d:
                    # 착탄 도달 -> 착탄 섬광 및 빠른 페이드 아웃(Dissolve, 0.08s) 전환
                    tr["phase"] = "fade"
                    tr["fade_timer"] = 0.08
                    tr["fade_duration"] = 0.08
                    tr["life"] = max(tr["life"], 0.09)

                    # 탄두 제거
                    if tr.get("head_node") and not tr["head_node"].isEmpty():
                        tr["head_node"].removeNode()
                        tr["head_node"] = None

                    # 착탄점 발광 섬광 생성
                    flash_np = self.world_root.attachNewNode("impact_flash")
                    flash_np.setPos(tr["end"])
                    f_geom = make_cube_to(flash_np, 0.28, 0.28, 0.28, LColor(1.0, 0.95, 0.40, 0.95), 0, 0, 0, rot_h=45)
                    f_geom.setLightOff()
                    f_geom.setTransparency(TransparencyAttrib.MAlpha)
                    f_geom.setDepthWrite(False)
                    f_geom.setBin("transparent", 110)
                    tr["flash"] = flash_np
                    tr["flash_timer"] = 0.09

                    trail_head = tr["end"]
                    t_len = min(14.0, max(4.0, total_d * 0.85))
                    trail_tail = tr["start"] + tr["dir"] * max(0.0, total_d - t_len)
                else:
                    trail_head = tr["start"] + tr["dir"] * head_pos
                    t_len = min(14.0, max(3.5, head_pos * 0.85))
                    tr["tracer_len"] = t_len
                    trail_tail = tr["start"] + tr["dir"] * max(0.0, head_pos - t_len)

                    # 3D 탄두 위치 및 방향 갱신
                    if tr.get("head_node") and not tr["head_node"].isEmpty():
                        tr["head_node"].setPos(trail_head)
                        tr["head_node"].lookAt(trail_head + tr["dir"])

                # 라인 갱신 (Core, Glow, Halo)
                for key in ("core", "glow", "halo"):
                    node = tr.get(key)
                    if node and not node.isEmpty():
                        node.removeNode()

                th_c = tr.get("th_core", 4.5)
                th_g = tr.get("th_glow", 9.5)
                th_h = tr.get("th_halo", 18.0)
                col_c = tr.get("c_core", (1.0, 1.0, 0.90, 0.98))
                col_g = tr.get("c_glow", (1.0, 0.75, 0.15, 0.75))
                col_h = tr.get("c_halo", (1.0, 0.35, 0.05, 0.35))

                ls_c = LineSegs("tracer_core")
                ls_c.setThickness(th_c)
                ls_c.setColor(*col_c)
                ls_c.moveTo(trail_tail)
                ls_c.drawTo(trail_head)
                tr["core"] = self.world_root.attachNewNode(ls_c.create())
                tr["core"].setLightOff()
                tr["core"].setTransparency(TransparencyAttrib.MAlpha)
                tr["core"].setDepthWrite(False)
                tr["core"].setBin("transparent", 102)
                tr["np"] = tr["core"]

                ls_g = LineSegs("tracer_glow")
                ls_g.setThickness(th_g)
                ls_g.setColor(*col_g)
                mid_tail = trail_tail + (trail_head - trail_tail) * 0.15
                ls_g.moveTo(mid_tail)
                ls_g.drawTo(trail_head)
                tr["glow"] = self.world_root.attachNewNode(ls_g.create())
                tr["glow"].setLightOff()
                tr["glow"].setTransparency(TransparencyAttrib.MAlpha)
                tr["glow"].setDepthWrite(False)
                tr["glow"].setBin("transparent", 101)

                ls_h = LineSegs("tracer_halo")
                ls_h.setThickness(th_h)
                ls_h.setColor(*col_h)
                mid_tail2 = trail_tail + (trail_head - trail_tail) * 0.35
                ls_h.moveTo(mid_tail2)
                ls_h.drawTo(trail_head)
                tr["halo"] = self.world_root.attachNewNode(ls_h.create())
                tr["halo"].setLightOff()
                tr["halo"].setTransparency(TransparencyAttrib.MAlpha)
                tr["halo"].setDepthWrite(False)
                tr["halo"].setBin("transparent", 100)

            elif tr.get("phase") == "fade":
                tr["fade_timer"] = max(0.0, tr.get("fade_timer", 0.0) - dt)
                if tr["fade_timer"] <= 0.0:
                    tr["life"] = 0.0
                else:
                    fade_alpha = max(0.0, min(1.0, tr["fade_timer"] / tr["fade_duration"]))

                    # 라인 갱신 (부드럽게 투명해짐)
                    for key in ("core", "glow", "halo"):
                        node = tr.get(key)
                        if node and not node.isEmpty():
                            node.removeNode()

                    total_d = tr["total_dist"]
                    t_len = min(14.0, max(4.0, total_d * 0.85))
                    trail_tail = tr["start"] + tr["dir"] * max(0.0, total_d - t_len)
                    trail_head = tr["end"]

                    th_c = tr.get("th_core", 4.5) * fade_alpha
                    th_g = tr.get("th_glow", 9.5) * fade_alpha
                    th_h = tr.get("th_halo", 18.0) * fade_alpha
                    col_c_base = tr.get("c_core", (1.0, 1.0, 0.90, 0.98))
                    col_g_base = tr.get("c_glow", (1.0, 0.75, 0.15, 0.75))
                    col_h_base = tr.get("c_halo", (1.0, 0.35, 0.05, 0.35))

                    ls_c = LineSegs("tracer_core")
                    ls_c.setThickness(th_c)
                    ls_c.setColor(col_c_base[0], col_c_base[1], col_c_base[2], col_c_base[3] * fade_alpha)
                    ls_c.moveTo(trail_tail)
                    ls_c.drawTo(trail_head)
                    tr["core"] = self.world_root.attachNewNode(ls_c.create())
                    tr["core"].setLightOff()
                    tr["core"].setTransparency(TransparencyAttrib.MAlpha)
                    tr["core"].setDepthWrite(False)
                    tr["core"].setBin("transparent", 102)
                    tr["np"] = tr["core"]

                    ls_g = LineSegs("tracer_glow")
                    ls_g.setThickness(th_g)
                    ls_g.setColor(col_g_base[0], col_g_base[1], col_g_base[2], col_g_base[3] * fade_alpha)
                    mid_tail = trail_tail + (trail_head - trail_tail) * 0.15
                    ls_g.moveTo(mid_tail)
                    ls_g.drawTo(trail_head)
                    tr["glow"] = self.world_root.attachNewNode(ls_g.create())
                    tr["glow"].setLightOff()
                    tr["glow"].setTransparency(TransparencyAttrib.MAlpha)
                    tr["glow"].setDepthWrite(False)
                    tr["glow"].setBin("transparent", 101)

                    ls_h = LineSegs("tracer_halo")
                    ls_h.setThickness(th_h)
                    ls_h.setColor(col_h_base[0], col_h_base[1], col_h_base[2], col_h_base[3] * fade_alpha)
                    mid_tail2 = trail_tail + (trail_head - trail_tail) * 0.35
                    ls_h.moveTo(mid_tail2)
                    ls_h.drawTo(trail_head)
                    tr["halo"] = self.world_root.attachNewNode(ls_h.create())
                    tr["halo"].setLightOff()
                    tr["halo"].setTransparency(TransparencyAttrib.MAlpha)
                    tr["halo"].setDepthWrite(False)
                    tr["halo"].setBin("transparent", 100)

            if tr["life"] <= 0.0:
                for key in ("core", "glow", "halo", "head_node", "flash", "np"):
                    node = tr.get(key)
                    if node and not node.isEmpty():
                        node.removeNode()
                self.active_tracers.remove(tr)

        # 1. 피격 파티클 풀 갱신
        for p in self.hit_particle_pool:
            if not p["active"]:
                continue
            p["timer"] -= dt
            if p["timer"] <= 0.0:
                p["active"] = False
                p["node"].hide()
                continue
            p["vel"].z -= 13.0 * dt  # 중력
            p["pos"] += p["vel"] * dt
            p["node"].setPos(p["pos"])
            scale = max(0.1, p["timer"] / 0.38)
            p["node"].setScale(scale)

        # 2. 사격 쿨다운 & 총구 화염 처리
        if self.shoot_cooldown > 0.0:
            self.shoot_cooldown = max(0.0, self.shoot_cooldown - dt)

        if self.muzzle_timer > 0.0:
            self.muzzle_timer -= dt
            if self.muzzle_timer <= 0.0:
                if hasattr(self, 'muzzle_flash_geom') and not self.muzzle_flash_geom.isEmpty():
                    self.muzzle_flash_geom.hide()
                    self.render.clearLight(self.muzzle_light_np)
                if hasattr(self, 'dual_left_flash_geom') and not self.dual_left_flash_geom.isEmpty():
                    self.dual_left_flash_geom.hide()
                    self.render.clearLight(self.dual_left_flash_light_np)
                if hasattr(self, 'dual_right_flash_geom') and not self.dual_right_flash_geom.isEmpty():
                    self.dual_right_flash_geom.hide()
                    self.render.clearLight(self.dual_right_flash_light_np)
                if hasattr(self, 'sg_muzzle_flash_geom') and not self.sg_muzzle_flash_geom.isEmpty():
                    self.sg_muzzle_flash_geom.hide()
                    self.render.clearLight(self.sg_muzzle_light_np)

        # 3. 3D 탄피 물리 풀 갱신 (중력, 궤적, 지면 튕김, 회전)
        for c in self.casing_pool:
            if not c["active"]:
                continue
            c["life"] -= dt
            if c["life"] <= 0.0:
                c["active"] = False
                c["node"].hide()
                continue
            c["vel"].z -= 9.8 * dt
            c["pos"] += c["vel"] * dt
            c["rot"] += c["spin"] * dt
            if c["pos"].z <= 0.03:
                c["pos"].z = 0.03
                c["vel"].z = -c["vel"].z * 0.32
                c["vel"].x *= 0.60
                c["vel"].y *= 0.60
                c["spin"] *= 0.65

            c["node"].setPos(c["pos"])
            c["node"].setHpr(c["rot"])

        # 4. 총구 잔여 가스 연기 풀 갱신 (열상승, 팽창, 페이드아웃)
        for s in self.smoke_pool:
            if not s["active"]:
                continue
            s["timer"] -= dt
            if s["timer"] <= 0.0:
                s["active"] = False
                s["node"].hide()
                continue
            s["vel"].z += 0.35 * dt
            s["pos"] += s["vel"] * dt
            s["scale"] += dt * 0.12
            s["node"].setPos(s["pos"])
            s["node"].setScale(s["scale"])
            alpha = max(0.0, (s["timer"] / s["max_timer"]) * 0.35)
            s["cube"].setColorScale(1, 1, 1, alpha)

        # 5. 현실적 슬라이드 블로우백 애니메이션
        # (1) 9mm 권총
        if hasattr(self, 'slide_node') and self.slide_node and not self.slide_node.isEmpty():
            if self.slide_timer > 0.0:
                self.slide_timer = max(0.0, self.slide_timer - dt)
                half_dur = self.slide_blowback_duration * 0.5
                if self.slide_timer > half_dur:
                    t_rear = (self.slide_blowback_duration - self.slide_timer) / half_dur
                    self.slide_node.setPos(0, self.slide_max_travel * t_rear, 0)
                    if hasattr(self, 'hammer_node') and self.hammer_node and not self.hammer_node.isEmpty():
                        self.hammer_node.setP(-42 * t_rear)
                else:
                    if self.slide_locked and self.ammo <= 0:
                        self.slide_node.setPos(0, self.slide_max_travel, 0)
                        if hasattr(self, 'hammer_node') and self.hammer_node and not self.hammer_node.isEmpty():
                            self.hammer_node.setP(-42)
                    else:
                        t_fwd = self.slide_timer / half_dur
                        self.slide_node.setPos(0, self.slide_max_travel * t_fwd, 0)
                        if hasattr(self, 'hammer_node') and self.hammer_node and not self.hammer_node.isEmpty():
                            self.hammer_node.setP(-42)
            elif not self.is_reloading:
                if self.current_weapon == "PISTOL" and self.slide_locked and self.ammo <= 0:
                    self.slide_node.setPos(0, self.slide_max_travel, 0)
                else:
                    self.slide_locked = False
                    if hasattr(self, 'weapon_states') and self.current_weapon in self.weapon_states:
                        self.weapon_states[self.current_weapon]["slide_locked"] = False
                    self.slide_node.setPos(0, 0, 0)

        # (2) 아킴보 쌍권총 좌/우 슬라이드 블로우백
        half_dur = self.slide_blowback_duration * 0.5
        if hasattr(self, 'dual_left_slide') and self.dual_left_slide and not self.dual_left_slide.isEmpty():
            if self.slide_timer_left > 0.0:
                self.slide_timer_left = max(0.0, self.slide_timer_left - dt)
                if self.slide_timer_left > half_dur:
                    t_rear = (self.slide_blowback_duration - self.slide_timer_left) / half_dur
                    self.dual_left_slide.setPos(0, self.slide_max_travel * t_rear, 0)
                else:
                    t_fwd = self.slide_timer_left / half_dur
                    self.dual_left_slide.setPos(0, self.slide_max_travel * t_fwd, 0)
            elif not self.is_reloading:
                self.dual_left_slide.setPos(0, 0, 0)

        if hasattr(self, 'dual_right_slide') and self.dual_right_slide and not self.dual_right_slide.isEmpty():
            if self.slide_timer_right > 0.0:
                self.slide_timer_right = max(0.0, self.slide_timer_right - dt)
                if self.slide_timer_right > half_dur:
                    t_rear = (self.slide_blowback_duration - self.slide_timer_right) / half_dur
                    self.dual_right_slide.setPos(0, self.slide_max_travel * t_rear, 0)
                else:
                    t_fwd = self.slide_timer_right / half_dur
                    self.dual_right_slide.setPos(0, self.slide_max_travel * t_fwd, 0)
            elif not self.is_reloading:
                self.dual_right_slide.setPos(0, 0, 0)

        # (3) 12게이지 샷건 펌프액션 슬라이드 왕복 및 탄피 배출
        if hasattr(self, 'sg_pump_node') and self.sg_pump_node and not self.sg_pump_node.isEmpty():
            if self.sg_pump_timer > 0.0:
                self.sg_pump_timer = max(0.0, self.sg_pump_timer - dt)
                total_pump = 0.44
                p_pump = 1.0 - (self.sg_pump_timer / total_pump)
                if p_pump < 0.50:
                    pump_offset = (p_pump / 0.50) * -0.09
                    if p_pump >= 0.35 and not self.sg_pump_cycled:
                        self.sg_pump_cycled = True
                        if self.audio_mgr and hasattr(self.audio_mgr, 'play_shotgun_pump'):
                            self.audio_mgr.play_shotgun_pump()
                        self._eject_casing(is_left=False, is_shotgun=True)
                else:
                    pump_offset = ((1.0 - p_pump) / 0.50) * -0.09
                self.sg_pump_node.setPos(0, 0.28 + pump_offset, -0.010)
            else:
                self.sg_pump_node.setPos(0, 0.28, -0.010)

        # 콤보 스트릭 타이머 감쇄
        if self.combo_timer > 0.0:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo_count = 0

        # 무기 스왑 딥 애니메이션 타이머
        if self.switch_timer > 0.0:
            self.switch_timer = max(0.0, self.switch_timer - dt)

        # 6. 현실적 다단계 재장전 애니메이션 및 반동
        if self.is_reloading:
            # 콤보 상태일 때 재장전 속도 1.35배 가속!
            reload_step = dt * 1.35 if self.combo_count >= 2 else dt
            self.reload_timer = max(0.0, self.reload_timer - reload_step)
            cfg = WEAPON_CONFIGS[self.current_weapon]
            total_dur = cfg.get("reload_time", 1.30)
            p = max(0.0, min(1.0, 1.0 - (self.reload_timer / total_dur)))

            if self.current_weapon == "PISTOL":
                # 권총: 탄창 배출 -> 삽입 -> 슬라이드 전진
                if p < 0.35:
                    sub_p = p / 0.35
                    self.recoil_node.setR(-22.0 * math.sin(sub_p * math.pi * 0.5))
                    self.recoil_node.setP(-18.0 * math.sin(sub_p * math.pi * 0.5))
                    drop_z = sub_p * 0.32
                    self.mag_node.setPos(0, -drop_z * 0.28, -drop_z)
                    self.mag_node.setScale(max(0.05, 1.0 - sub_p * 0.8))
                elif p < 0.78:
                    sub_p = (p - 0.35) / 0.43
                    self.recoil_node.setR(-22.0 * (1.0 - sub_p * 0.3))
                    self.recoil_node.setP(-18.0 * (1.0 - sub_p * 0.3))
                    rise_z = (1.0 - min(1.0, sub_p * 1.1)) * 0.28
                    self.mag_node.setScale(1.0)
                    self.mag_node.setPos(0, -rise_z * 0.28, -rise_z)
                else:
                    sub_p = (p - 0.78) / 0.22
                    self.mag_node.setPos(0, 0, 0)
                    self.mag_node.setScale(1.0)
                    if self.was_slide_locked_before_reload:
                        self.slide_locked = False
                        self.slide_node.setPos(0, 0, 0)
                    self.recoil_node.setR(-22.0 * 0.7 * (1.0 - sub_p))
                    self.recoil_node.setP(-18.0 * 0.7 * (1.0 - sub_p))

            elif self.current_weapon == "DUAL_PISTOL":
                # 아킴보 쌍권총: 양손 바깥쪽 틸트 & 탄창 동시 교체
                tilt = math.sin(p * math.pi)
                if hasattr(self, 'dual_left_recoil') and not self.dual_left_recoil.isEmpty():
                    self.dual_left_recoil.setR(24.0 * tilt)
                    self.dual_left_recoil.setP(-16.0 * tilt)
                    self.dual_left_recoil.setPos(0, -0.06 * tilt, -0.04 * tilt)
                if hasattr(self, 'dual_right_recoil') and not self.dual_right_recoil.isEmpty():
                    self.dual_right_recoil.setR(-24.0 * tilt)
                    self.dual_right_recoil.setP(-16.0 * tilt)
                    self.dual_right_recoil.setPos(0, -0.06 * tilt, -0.04 * tilt)

            elif self.current_weapon == "SHOTGUN":
                # 샷건: 리시버를 살짝 들어 올리고 쉘을 아래에서 밀어 넣음
                lift = math.sin(p * math.pi)
                if hasattr(self, 'sg_recoil_node') and not self.sg_recoil_node.isEmpty():
                    self.sg_recoil_node.setP(18.0 * lift)
                    self.sg_recoil_node.setR(9.0 * lift)
                    self.sg_recoil_node.setPos(0, -0.08 * lift, 0.03 * lift)

            if self.reload_timer <= 0.0:
                self.is_reloading = False
                self.slide_locked = False

                # 노드 초기화
                if hasattr(self, 'slide_node') and not self.slide_node.isEmpty():
                    self.slide_node.setPos(0, 0, 0)
                if hasattr(self, 'recoil_node') and not self.recoil_node.isEmpty():
                    self.recoil_node.setPos(0, 0, 0)
                    self.recoil_node.setP(0)
                    self.recoil_node.setR(0)
                if hasattr(self, 'mag_node') and not self.mag_node.isEmpty():
                    self.mag_node.setPos(0, 0, 0)
                    self.mag_node.setScale(1.0)
                if hasattr(self, 'dual_left_recoil') and not self.dual_left_recoil.isEmpty():
                    self.dual_left_recoil.setPos(0, 0, 0)
                    self.dual_left_recoil.setP(0)
                    self.dual_left_recoil.setR(0)
                if hasattr(self, 'dual_right_recoil') and not self.dual_right_recoil.isEmpty():
                    self.dual_right_recoil.setPos(0, 0, 0)
                    self.dual_right_recoil.setP(0)
                    self.dual_right_recoil.setR(0)
                if hasattr(self, 'sg_recoil_node') and not self.sg_recoil_node.isEmpty():
                    self.sg_recoil_node.setPos(0, 0, 0)
                    self.sg_recoil_node.setP(0)
                    self.sg_recoil_node.setR(0)

                # 탄약 충전
                wstate = self.weapon_states[self.current_weapon]
                needed = wstate["max_ammo"] - wstate["ammo"]
                transferred = min(needed, wstate["reserve_ammo"])
                wstate["ammo"] += transferred
                wstate["reserve_ammo"] -= transferred
                wstate["slide_locked"] = False
                self.ammo = wstate["ammo"]
                self._reserve_ammo = wstate["reserve_ammo"]
                self.update_ammo_ui()
                self.ui_mgr.show_hit_marker(f"재장전 완료! (+{transferred}발 장전됨)", (0.35, 1.0, 0.5, 1.0))
                self.hit_marker_timer = 1.5

        # 7. 사격 반동 애니메이션
        elif self.recoil_timer > 0.0:
            self.recoil_timer -= dt
            if self.current_weapon == "PISTOL":
                t_norm = max(0.0, self.recoil_timer / 0.10)
                recoil_dist = 0.05 if not self.is_aiming else 0.024
                recoil_deg = 12.0 if not self.is_aiming else 5.5
                if hasattr(self, 'recoil_node') and not self.recoil_node.isEmpty():
                    self.recoil_node.setPos(0, -recoil_dist * t_norm, (recoil_dist * 0.4) * t_norm)
                    self.recoil_node.setP(recoil_deg * t_norm)
                    self.recoil_node.setR(0)

            elif self.current_weapon == "DUAL_PISTOL":
                t_norm = max(0.0, self.recoil_timer / 0.08)
                recoil_dist = 0.045 if not self.is_aiming else 0.022
                recoil_deg = 9.0 if not self.is_aiming else 4.5
                # 직전에 격발된 손에 반동 적용
                if self.dual_hand_toggle == 0:  # 방금 우측 격발
                    if hasattr(self, 'dual_right_recoil') and not self.dual_right_recoil.isEmpty():
                        self.dual_right_recoil.setPos(0, -recoil_dist * t_norm, (recoil_dist * 0.35) * t_norm)
                        self.dual_right_recoil.setP(recoil_deg * t_norm)
                        self.dual_right_recoil.setR(-3.0 * t_norm)
                else:  # 방금 좌측 격발
                    if hasattr(self, 'dual_left_recoil') and not self.dual_left_recoil.isEmpty():
                        self.dual_left_recoil.setPos(0, -recoil_dist * t_norm, (recoil_dist * 0.35) * t_norm)
                        self.dual_left_recoil.setP(recoil_deg * t_norm)
                        self.dual_left_recoil.setR(3.0 * t_norm)

            elif self.current_weapon == "SHOTGUN":
                t_norm = max(0.0, self.recoil_timer / 0.18)
                recoil_dist = 0.10 if not self.is_aiming else 0.048
                recoil_deg = 20.0 if not self.is_aiming else 9.5
                if hasattr(self, 'sg_recoil_node') and not self.sg_recoil_node.isEmpty():
                    self.sg_recoil_node.setPos(0, -recoil_dist * t_norm, (recoil_dist * 0.35) * t_norm)
                    self.sg_recoil_node.setP(recoil_deg * t_norm)
                    self.sg_recoil_node.setR(4.0 * t_norm)
        else:
            if hasattr(self, 'recoil_node') and not self.recoil_node.isEmpty():
                self.recoil_node.setPos(0, 0, 0)
                self.recoil_node.setP(0)
                self.recoil_node.setR(0)
            if hasattr(self, 'dual_left_recoil') and not self.dual_left_recoil.isEmpty():
                self.dual_left_recoil.setPos(0, 0, 0)
                self.dual_left_recoil.setP(0)
                self.dual_left_recoil.setR(0)
            if hasattr(self, 'dual_right_recoil') and not self.dual_right_recoil.isEmpty():
                self.dual_right_recoil.setPos(0, 0, 0)
                self.dual_right_recoil.setP(0)
                self.dual_right_recoil.setR(0)
            if hasattr(self, 'sg_recoil_node') and not self.sg_recoil_node.isEmpty():
                self.sg_recoil_node.setPos(0, 0, 0)
                self.sg_recoil_node.setP(0)
                self.sg_recoil_node.setR(0)

        # 피격/알림 타이머
        if self.hit_marker_timer > 0.0:
            self.hit_marker_timer -= dt
            if self.hit_marker_timer <= 0.0:
                self.ui_mgr.show_hit_marker("")

        # 탄약 상자 수거 판정 (플레이어 1.8m 이내)
        if self.ammo_drops:
            for drop in self.ammo_drops[:]:
                dx = px - drop["pos"][0]
                dy = py - drop["pos"][1]
                if math.hypot(dx, dy) <= 1.8:
                    self.reserve_ammo += 12  # setter를 통해 모든 무기에 균형 보급
                    if self.audio_mgr:
                        self.audio_mgr.play_ammo_pickup()
                    self.ui_mgr.show_hit_marker("탄약 상자 획득! (전 무기 탄약 보급)", (0.35, 1.0, 0.5, 1.0))
                    self.hit_marker_timer = 2.0
                    if "light_np" in drop and drop["light_np"] and not drop["light_np"].isEmpty():
                        self.render.clearLight(drop["light_np"])
                    if "node" in drop and drop["node"] and not drop["node"].isEmpty():
                        drop["node"].removeNode()
                    self.ammo_drops.remove(drop)
                    self.update_ammo_ui()

        # 정밀 조준(ADS) 부드러운 위치/화각 보간
        ads_speed = 10.0
        if self.is_aiming:
            self.ads_alpha = min(1.0, self.ads_alpha + ads_speed * dt)
        else:
            self.ads_alpha = max(0.0, self.ads_alpha - ads_speed * dt)

        # (1) 9mm 권총 ADS
        if hasattr(self, 'vm_pistol') and self.vm_pistol and not self.vm_pistol.isEmpty():
            cur_pos = self.ads_hip_pos * (1.0 - self.ads_alpha) + self.ads_aim_pos * self.ads_alpha
            cur_hpr = self.ads_hip_hpr * (1.0 - self.ads_alpha) + self.ads_aim_hpr * self.ads_alpha
            self.vm_pistol.setPos(cur_pos)
            self.vm_pistol.setHpr(cur_hpr)

        # (2) 아킴보 쌍권총 ADS (두 총기를 중앙으로 모아 지향사격 정확도 향상)
        if hasattr(self, 'vm_dual_left') and self.vm_dual_left and not self.vm_dual_left.isEmpty():
            cur_pos_l = self.ads_hip_pos_dual_l * (1.0 - self.ads_alpha) + self.ads_aim_pos_dual_l * self.ads_alpha
            cur_hpr_l = Vec3(4.0, 1.0, 10.0) * (1.0 - self.ads_alpha) + Vec3(1.0, 0.5, 4.0) * self.ads_alpha
            self.vm_dual_left.setPos(cur_pos_l)
            self.vm_dual_left.setHpr(cur_hpr_l)

        if hasattr(self, 'vm_dual_right') and self.vm_dual_right and not self.vm_dual_right.isEmpty():
            cur_pos_r = self.ads_hip_pos_dual_r * (1.0 - self.ads_alpha) + self.ads_aim_pos_dual_r * self.ads_alpha
            cur_hpr_r = Vec3(-4.0, 1.0, -10.0) * (1.0 - self.ads_alpha) + Vec3(-1.0, 0.5, -4.0) * self.ads_alpha
            self.vm_dual_right.setPos(cur_pos_r)
            self.vm_dual_right.setHpr(cur_hpr_r)

        # (3) 12게이지 샷건 ADS (총열 상단 리브와 빨간 광섬유 가늠쇠 정렬)
        if hasattr(self, 'vm_shotgun') and self.vm_shotgun and not self.vm_shotgun.isEmpty():
            cur_pos_sg = self.ads_hip_pos_sg * (1.0 - self.ads_alpha) + self.ads_aim_pos_sg * self.ads_alpha
            cur_hpr_sg = Vec3(1.0, 0.5, -0.5) * (1.0 - self.ads_alpha)
            self.vm_shotgun.setPos(cur_pos_sg)
            self.vm_shotgun.setHpr(cur_hpr_sg)

        # 카메라 FOV 줌 (기본 96도 쾌적한 와이드 시야각 -> 정밀조준 시 80도로 자연스럽게 확대) + 불릿타임 시 광각 시간왜곡 워프 (+6.5도)
        if hasattr(self.base, 'camLens') and self.base.camLens:
            cur_fov = 96.0 * (1.0 - self.ads_alpha) + 80.0 * self.ads_alpha
            game_inst = getattr(self.base, 'game', None) or self.base
            if getattr(game_inst, 'bullet_time_timer', 0.0) > 0.0:
                cur_fov += 6.5
            self.base.camLens.setFov(cur_fov)

        # 조준 중 크로스헤어 투명화 (권총 및 샷건 조준 시 가늠쇠/조준선 집중)
        if hasattr(self.ui_mgr, 'set_crosshair_visible'):
            self.ui_mgr.set_crosshair_visible(self.ads_alpha < 0.45 or self.current_weapon == "DUAL_PISTOL")

        # 뷰모델 보행 밥빙 & 호흡 스웨이 & 무기 스왑 딥
        bob_mult = 1.0 - self.ads_alpha * 0.75
        dip_z = math.sin((self.switch_timer / 0.22) * math.pi) * -0.07 if self.switch_timer > 0.0 else 0.0

        if is_moving:
            self.bobbing_time += dt * (14.0 if is_sprinting else 8.5)
            bob_x = math.sin(self.bobbing_time * 0.5) * 0.012 * bob_mult
            bob_y = abs(math.cos(self.bobbing_time)) * 0.014 * bob_mult
            self.vm_root.setPos(bob_x, 0, -bob_y + dip_z)
        else:
            self.bobbing_time += dt * 2.0
            sway_z = math.sin(self.bobbing_time) * 0.003 * bob_mult
            self.vm_root.setPos(0, 0, sway_z + dip_z)
    def set_blackout_mode(self, is_active: bool):
        """정전 비상등 핏빛 조명 모드 전환"""
        self.is_blackout = is_active
        if is_active:
            self.pl_np.node().setColor((2.70, 0.85, 0.70, 1.0))
        else:
            self.pl_np.node().setColor((2.85, 2.70, 2.35, 1.0))
