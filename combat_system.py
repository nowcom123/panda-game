"""
Combat System Module
1인칭 듀얼 뷰모델(손전등/권총), 레이캐스트 사격, 재장전, 반동/밥빙 애니메이션,
발광 총알 궤적(Bullet Tracer) 및 필드 탄약 상자 드랍/습득 관리
"""

import math
import random
import time
from panda3d.core import (
    PointLight, Spotlight, PerspectiveLens, LineSegs, LColor, Vec3, TransparencyAttrib, MouseButton
)
from constants import (
    CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import cell_has_pillar
from geometry import make_cube_to, make_sphere_to, make_cylinder_to, make_muzzle_flash_to
from collision import raycast_walls
from projectiles import ExplosionVisualEffect
from perks import get_player_perk_stats
from weapon_recoil import WeaponRecoil, RECOIL_PROFILES
from casing_effects import CasingEffects


WEAPON_CONFIGS = {
    "PISTOL": {
        "id": "PISTOL",
        "name": ".50 매그넘 데저트 이글",
        "max_ammo": 7,
        "initial_reserve": 28,
        "damage": 120.0,
        "headshot_mult": 3.2,
        "cooldown": 0.44,
        "combo_cooldown": 0.32,
        "pellets": 1,
        "base_spread": 0.012,
        "ads_spread": 0.0,
        "recoil_time": 0.18,
        "recoil_deg": 22.0,
        "reload_time": 1.45,
        "description": "7발 탄창. .50 Action Express 매그넘탄. 뼈를 부수는 파괴적인 단발 저지력과 관통력."
    },
    "DUAL_PISTOL": {
        "id": "DUAL_PISTOL",
        "name": "9mm 듀얼 글록 (아킴보)",
        "max_ammo": 34,
        "initial_reserve": 68,
        "damage": 26.0,
        "headshot_mult": 2.0,
        "cooldown": 0.065,
        "combo_cooldown": 0.048,
        "pellets": 1,
        "base_spread": 0.050,
        "ads_spread": 0.020,
        "recoil_time": 0.060,
        "recoil_deg": 7.5,
        "reload_time": 2.50,
        "description": "34발 대용량(양손 17발x2). 9mm 파라블럼 탄을 사용하는 듀얼 글록. 빠른 단발 클릭으로 뿜어져 나오는 양손 속사 화력."
    },
    "AR": {
        "id": "AR",
        "name": "5.56mm HK416 돌격소총 (AR)",
        "max_ammo": 30,
        "initial_reserve": 90,
        "damage": 38.0,
        "headshot_mult": 2.4,
        "cooldown": 0.082,
        "combo_cooldown": 0.065,
        "pellets": 1,
        "base_spread": 0.030,
        "ads_spread": 0.008,
        "recoil_time": 0.075,
        "recoil_deg": 14.0,
        "reload_time": 3.20,
        "description": "30발 탄창. 5.56x45mm NATO. 단행정 가스 피스톤 방식을 채용한 독일 H&K사의 하이엔드 돌격소총 HK416. 분당 730발 초고속 연사 화력(재장전 지연 3.2s)."
    },
    "SHOTGUN": {
        "id": "SHOTGUN",
        "name": "12게이지 펌프 샷건",
        "max_ammo": 8,
        "initial_reserve": 24,
        "damage": 25.0,
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
        "description": "8발 튜브 탄창. 1격발당 8발 대구경 벅샷 산탄과 펌프 액션 (초근접 광역 섬멸, 원거리 산탄 분산 및 위력 감쇄)."
    }
}
WEAPON_ORDER = ["PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"]


class CombatSystem:
    # 스테이지 전투 통계 기본값 (CombatSystem.__new__ 테스트 호환성 확보)
    stage_kills = 0
    stage_headshots = 0
    stage_shots_fired = 0
    stage_shots_hit = 0
    stage_damage_dealt = 0.0
    stage_damage_taken = 0.0
    stage_max_combo = 0
    stage_start_time = 0.0

    def __init__(self, base, render, camera, world_root, audio_mgr, ui_mgr):
        self.base = base
        self.render = render
        self.camera = camera
        self.world_root = world_root
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 무기 인벤토리 및 장착 상태
        self.current_weapon = "PISTOL"
        self._reserve_ammo = 28
        self.weapon_states = {
            "PISTOL": {"ammo": 7, "max_ammo": 7, "reserve_ammo": 28, "slide_locked": False},
            "DUAL_PISTOL": {"ammo": 34, "max_ammo": 34, "reserve_ammo": 68, "slide_locked": False},
            "AR": {"ammo": 30, "max_ammo": 30, "reserve_ammo": 90, "slide_locked": False},
            "SHOTGUN": {"ammo": 8, "max_ammo": 8, "reserve_ammo": 24, "slide_locked": False},
        }

        # 탄약 및 사격 상태
        self.max_ammo = 7
        self.ammo = self.max_ammo
        self.overcharge_rounds = 0  # 오버차지 고폭 플라즈마 소이탄 탄환 수
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.weapon_recoil = WeaponRecoil()
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
        self.smoke_particles = []
        self.was_slide_locked_before_reload = False

        # 정전 상태
        self.is_blackout = False

        # 킬 콤보 & 아드레날린 램페이지 상태
        self.combo_count = 0
        self.combo_timer = 0.0
        self.combo_window = 3.8
        self.bullet_storm_timer = 0.0  # 탄환 폭풍 퍽 활성화 타이머

        # 스테이지 전투 결과 보고서 (After-Action Report) 통계 추적
        self.stage_kills = 0
        self.stage_headshots = 0
        self.stage_shots_fired = 0
        self.stage_shots_hit = 0
        self.stage_damage_dealt = 0.0
        self.stage_damage_taken = 0.0
        self.stage_max_combo = 0
        self.stage_start_time = 0.0

        # 정밀 조준(ADS: Aim Down Sights) 상태
        self.is_aiming = False
        self.ads_alpha = 0.0
        # 1인칭 시점(POV) 쾌적화: 총기가 카메라에 너무 가깝지 않도록 전방 및 하단으로 거리 확보 (시야 개방감 극대화)
        self.ads_hip_pos = Vec3(0.20, 0.68, -0.195)
        self.ads_aim_pos = Vec3(0.00, 0.58, -0.118)
        self.ads_hip_hpr = Vec3(1.5, 0.8, -0.8)
        self.ads_aim_hpr = Vec3(0.0, 0.0, 0.0)

        # AR, 샷건 및 듀얼 글록 POV 좌표
        self.ads_hip_pos_ar = Vec3(0.18, 0.65, -0.210)
        self.ads_aim_pos_ar = Vec3(0.00, 0.55, -0.125)
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
        self.casing_effects = CasingEffects(self.world_root, capacity=24)

        # 3. 총구 화약 가스 연기 풀 (20개)
        self.smoke_pool = []
        smoke_col = LColor(0.75, 0.75, 0.78, 0.35)
        for i in range(20):
            s_node = self.world_root.attachNewNode(f"pooled_smoke_{i}")
            cube = make_sphere_to(s_node, 0.045, 0.045, 0.045, smoke_col, 0, 0, 0)
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
        self.sg_pump_timer = 0.0
        self.sg_pump_cycled = False
        if self.audio_mgr:
            self.audio_mgr.stop_weapon_actions()
        self.current_weapon = target_weapon
        self._reset_weapon_recoil()
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

        if hasattr(self, 'vm_ar') and self.vm_ar:
            if self.current_weapon == "AR":
                self.vm_ar.show()
            else:
                self.vm_ar.hide()

        if hasattr(self, 'vm_shotgun') and self.vm_shotgun:
            if self.current_weapon == "SHOTGUN":
                self.vm_shotgun.show()
            else:
                self.vm_shotgun.hide()

    def start_aim(self):
        """우클릭 정밀 조준(ADS) 시작"""
        if not self.is_aiming:
            self.is_aiming = True

    def stop_aim(self):
        """우클릭 정밀 조준(ADS) 해제"""
        if self.is_aiming:
            self.is_aiming = False

    def _setup_viewmodel(self):
        """1인칭 택티컬 뷰모델: 안정적 통합 전방 조명 및 4종 무기(데저트 이글, 듀얼 글록, AR, 펌프 샷건) 지오메트리 구축"""
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

        # 4종 무기 3D 지오메트리 개별 구축
        self._build_pistol_viewmodel()
        self._build_dual_viewmodel()
        self._build_ar_viewmodel()
        self._build_shotgun_viewmodel()
        self._update_viewmodel_visibility()

    def _build_pistol_viewmodel(self):
        """1. .50 매그넘 데저트 이글 (Desert Eagle .50 AE) 핸드캐논 뷰모델 지오메트리"""
        self.vm_pistol = self.vm_root.attachNewNode("vm_pistol")
        self.vm_pistol.setPos(self.ads_hip_pos)
        self.vm_pistol.setHpr(self.ads_hip_hpr)

        self.recoil_node = self.vm_pistol.attachNewNode("recoil_node")

        # 데저트 이글 시그니처 크롬/브러시드 스테인리스 실버 & 블랙 투톤 마감
        chrome_slide = LColor(0.72, 0.74, 0.78, 1.0)
        frame_steel = LColor(0.18, 0.19, 0.22, 1.0)
        barrel_steel = LColor(0.68, 0.70, 0.74, 1.0)
        grip_polymer = LColor(0.06, 0.06, 0.07, 1.0)
        medallion_gold = LColor(0.82, 0.68, 0.20, 1.0)
        sight_orange = LColor(1.0, 0.45, 0.15, 1.0)

        # 하부 프레임 (Desert Eagle Frame & Heavy Grip)
        self.frame_node = self.recoil_node.attachNewNode("frame_node")
        grip = make_cube_to(self.frame_node, 0.064, 0.13, 0.22, grip_polymer, 0, -0.07, -0.09)
        grip.setP(18)
        # 데저트 이글 메달리온 인서트
        make_cylinder_to(self.frame_node, 0.016, 0.068, 0.016, medallion_gold, 0, -0.07, -0.08, rot_p=18, axis='x')
        make_cube_to(self.frame_node, 0.060, 0.22, 0.056, frame_steel, 0, 0.08, 0.005)
        make_cube_to(self.frame_node, 0.034, 0.09, 0.065, frame_steel, 0, 0.04, -0.04)
        make_cube_to(self.frame_node, 0.016, 0.024, 0.040, frame_steel, 0, 0.035, -0.025)
        # 묵직한 트리거 가드 및 안전장치
        make_cube_to(self.frame_node, 0.014, 0.040, 0.014, frame_steel, -0.034, 0.02, 0.048)
        make_cube_to(self.frame_node, 0.014, 0.020, 0.018, frame_steel, -0.034, -0.035, -0.02)

        # 하부 언더레일 웨폰라이트 바디
        vm_fl = self.frame_node.attachNewNode("vm_fl")
        vm_fl.setPos(0, 0.14, -0.038)
        make_cube_to(vm_fl, 0.062, 0.15, 0.022, frame_steel, 0, -0.012, 0.022)
        make_cylinder_to(vm_fl, 0.054, 0.17, 0.046, frame_steel, 0, 0.0, 0.0, axis='y')
        make_cylinder_to(vm_fl, 0.058, 0.030, 0.050, chrome_slide, 0, 0.096, 0.0, axis='y')
        lens = make_cylinder_to(vm_fl, 0.048, 0.008, 0.044, LColor(1.0, 0.96, 0.82, 0.95), 0, 0.112, 0.0, axis='y')
        lens.setLightOff()

        # 고정식 대구경 .50 AE 총열 (상단 피카티니 레일 일체형 삼각형 총열)
        self.barrel_node = self.recoil_node.attachNewNode("barrel_node")
        make_cube_to(self.barrel_node, 0.064, 0.22, 0.075, barrel_steel, 0, 0.18, 0.045)
        make_cube_to(self.barrel_node, 0.038, 0.24, 0.016, frame_steel, 0, 0.18, 0.088) # 상단 스코프 레일
        # 대구경 .50 AE 총구 내경 (12.7mm 구경의 위압감)
        make_cylinder_to(self.barrel_node, 0.048, 0.18, 0.048, barrel_steel, 0, 0.19, 0.042, axis='y')
        make_cylinder_to(self.barrel_node, 0.036, 0.018, 0.036, LColor(0.01, 0.01, 0.01, 1.0), 0, 0.292, 0.042, axis='y')

        # 크롬 왕복 슬라이드 (Desert Eagle 후방 슬라이드 & 볼트)
        self.slide_node = self.recoil_node.attachNewNode("slide_node")
        make_cube_to(self.slide_node, 0.068, 0.24, 0.078, chrome_slide, 0, -0.01, 0.045)
        # 슬라이드 서레이션 (코킹 그루브)
        make_cube_to(self.slide_node, 0.072, 0.07, 0.045, frame_steel, 0, -0.06, 0.045)
        make_cube_to(self.slide_node, 0.024, 0.07, 0.040, frame_steel, 0.028, 0.03, 0.055) # 약실 배출창

        # 형광 가늠쇠 & 타겟 가늠자
        front_sight = make_cube_to(self.barrel_node, 0.012, 0.024, 0.022, sight_orange, 0, 0.275, 0.10)
        front_sight.setLightOff()
        r_sight1 = make_cube_to(self.slide_node, 0.012, 0.018, 0.022, sight_orange, -0.024, -0.11, 0.095)
        r_sight2 = make_cube_to(self.slide_node, 0.012, 0.018, 0.022, sight_orange, 0.024, -0.11, 0.095)
        r_sight1.setLightOff()
        r_sight2.setLightOff()

        # 대형 스퍼 해머 (공이치기)
        self.hammer_node = self.recoil_node.attachNewNode("hammer_node")
        self.hammer_node.setPos(0, -0.125, 0.042)
        self.hammer_node.setP(-42)
        make_cube_to(self.hammer_node, 0.020, 0.035, 0.052, chrome_slide, 0, -0.014, 0.020)

        # .50 AE 7발 대형 탄창
        self.mag_node = self.frame_node.attachNewNode("mag_node")
        self.mag_node.setPos(0, -0.07, -0.09)
        self.mag_node.setP(18)
        make_cube_to(self.mag_node, 0.052, 0.095, 0.20, frame_steel, 0, 0, 0)
        make_cube_to(self.mag_node, 0.062, 0.11, 0.028, grip_polymer, 0, -0.005, -0.105)
        # .50 매그넘 대구경 황동 탄두 노출
        make_cylinder_to(self.mag_node, 0.028, 0.050, 0.028, LColor(0.92, 0.76, 0.22, 1.0), 0, 0.01, 0.09, axis='y')

        # 매그넘 대구경 총구 화염 & 섬광 조명
        self.muzzle_flash_geom = make_muzzle_flash_to(self.recoil_node, 0.075, 0.19, 0, 0.38, 0.042)
        self.muzzle_flash_geom.setLightOff()
        self.muzzle_flash_geom.hide()

        self.muzzle_light = PointLight('muzzle_light')
        self.muzzle_light.setColor((4.2, 2.8, 1.0, 1.0))
        self.muzzle_light.setAttenuation((1.0, 0.06, 0.012))
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)
        self.muzzle_light_np.setPos(0, 0.40, 0.042)

        # 1인칭 전술 장갑 및 손목 팔 (Tactical Hands & Arms - 데저트 이글 투핸드 파지법)
        glove_dark = LColor(0.12, 0.12, 0.14, 1.0)
        knuckle_col = LColor(0.20, 0.22, 0.25, 1.0)
        sleeve_col = LColor(0.08, 0.09, 0.11, 1.0)
        strap_col = LColor(0.05, 0.05, 0.06, 1.0)

        # (1) 오른손 (주무기 권총 그립 파지)
        r_hand = self.recoil_node.attachNewNode("pistol_r_hand")
        make_cylinder_to(r_hand, 0.075, 0.28, 0.075, sleeve_col, 0.065, -0.26, -0.20, rot_h=-12, rot_p=30, rot_r=-12, axis='y')
        make_cylinder_to(r_hand, 0.068, 0.045, 0.068, strap_col, 0.038, -0.14, -0.13, rot_h=-10, rot_p=24, rot_r=-8, axis='y')
        make_cube_to(r_hand, 0.064, 0.095, 0.064, glove_dark, 0.020, -0.075, -0.095, rot_p=18)
        make_cube_to(r_hand, 0.062, 0.040, 0.022, knuckle_col, 0.036, -0.065, -0.082, rot_p=18, rot_r=12)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.015, -0.062, rot_p=18)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.025, -0.098, rot_p=18)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.035, -0.134, rot_p=18)
        make_cube_to(r_hand, 0.022, 0.068, 0.022, glove_dark, 0.026, 0.012, -0.024, rot_h=-6, rot_p=8)
        make_cube_to(r_hand, 0.025, 0.058, 0.025, glove_dark, -0.026, -0.055, -0.032, rot_h=10, rot_p=-8)

        # (2) 왼손 (오른손 밑을 받쳐 감싸는 투핸드 전술 서포트)
        l_hand = self.recoil_node.attachNewNode("pistol_l_hand")
        make_cylinder_to(l_hand, 0.075, 0.28, 0.075, sleeve_col, -0.082, -0.24, -0.21, rot_h=16, rot_p=30, rot_r=16, axis='y')
        make_cylinder_to(l_hand, 0.068, 0.045, 0.068, strap_col, -0.048, -0.13, -0.14, rot_h=14, rot_p=22, rot_r=10, axis='y')
        make_cube_to(l_hand, 0.066, 0.088, 0.064, glove_dark, -0.024, -0.070, -0.120, rot_p=18, rot_r=-14)
        make_cube_to(l_hand, 0.056, 0.062, 0.032, knuckle_col, -0.012, -0.032, -0.128, rot_p=18, rot_h=12)
        make_cube_to(l_hand, 0.022, 0.072, 0.022, glove_dark, -0.032, -0.008, -0.024, rot_p=6)

    def _build_dual_viewmodel(self):
        """2. 9mm 듀얼 글록 아킴보 (Dual 9mm Glocks) 좌/우 뷰모델 지오메트리"""
        self.vm_dual = self.vm_root.attachNewNode("vm_dual")

        glock_polymer = LColor(0.08, 0.08, 0.09, 1.0)
        glock_slide = LColor(0.18, 0.19, 0.21, 1.0)
        steel_barrel = LColor(0.13, 0.13, 0.15, 1.0)
        glock_white = LColor(0.96, 0.96, 0.98, 1.0)

        # (1) 좌측 9mm 글록 (Left Hand Glock)
        self.vm_dual_left = self.vm_dual.attachNewNode("vm_dual_left")
        self.vm_dual_left.setPos(self.ads_hip_pos_dual_l)
        self.vm_dual_left.setHpr(Vec3(4.0, 1.0, 10.0))

        self.dual_left_recoil = self.vm_dual_left.attachNewNode("dual_left_recoil")
        left_frame = self.dual_left_recoil.attachNewNode("dual_left_frame")
        lgrip = make_cube_to(left_frame, 0.050, 0.10, 0.18, glock_polymer, 0, -0.05, -0.08)
        lgrip.setP(20)
        make_cube_to(left_frame, 0.048, 0.18, 0.044, glock_polymer, 0, 0.07, 0.005)
        make_cube_to(left_frame, 0.024, 0.07, 0.052, glock_polymer, 0, 0.035, -0.035)

        self.dual_left_slide = self.dual_left_recoil.attachNewNode("dual_left_slide")
        make_cylinder_to(self.dual_left_recoil, .032, .10, .032, steel_barrel, 0, .20, .035, axis='y')
        make_cylinder_to(self.dual_left_recoil, .020, .01, .020, LColor(.01, .01, .01, 1), 0, .254, .035, axis='y')
        # 각진 글록 사각 슬라이드 및 전후방 서레이션
        make_cube_to(self.dual_left_slide, 0.052, 0.26, 0.064, glock_slide, 0, 0.05, 0.040)
        make_cube_to(self.dual_left_slide, 0.054, 0.05, 0.062, glock_polymer, 0, -0.04, 0.040)
        make_cube_to(self.dual_left_slide, 0.018, 0.06, 0.030, glock_polymer, -0.022, 0.04, 0.050)
        # 글록 시그니처 화이트 도트 가늠쇠
        l_front = make_cube_to(self.dual_left_slide, 0.010, 0.016, 0.016, glock_white, 0, 0.17, 0.076)
        l_front.setLightOff()

        self.dual_left_hammer = self.dual_left_recoil.attachNewNode("dual_left_hammer")
        self.dual_left_hammer.setPos(0, -0.085, 0.034)
        make_cube_to(self.dual_left_hammer, 0.014, 0.018, 0.035, glock_slide, 0, -0.005, 0.010)

        self.dual_left_mag = left_frame.attachNewNode("dual_left_mag")
        self.dual_left_mag.setPos(0, -0.05, -0.08)
        self.dual_left_mag.setP(20)
        make_cube_to(self.dual_left_mag, 0.040, 0.075, 0.16, glock_polymer, 0, 0, 0)

        self.dual_left_flash_geom = make_muzzle_flash_to(self.dual_left_recoil, 0.055, 0.14, 0, 0.32, 0.035)
        self.dual_left_flash_geom.setLightOff()
        self.dual_left_flash_geom.hide()

        self.dual_left_flash_light = PointLight('dual_left_light')
        self.dual_left_flash_light.setColor((2.6, 2.0, 0.8, 1.0))
        self.dual_left_flash_light.setAttenuation((1.0, 0.09, 0.018))
        self.dual_left_flash_light_np = self.dual_left_recoil.attachNewNode(self.dual_left_flash_light)
        self.dual_left_flash_light_np.setPos(0, 0.32, 0.035)

        # 왼손 아킴보 권총 파지 전술 손 & 팔
        l_hand_dual = self.dual_left_recoil.attachNewNode("dual_l_hand")
        make_cylinder_to(l_hand_dual, 0.075, 0.26, 0.075, LColor(0.08, 0.09, 0.11, 1.0), -0.065, -0.25, -0.20, rot_h=12, rot_p=30, rot_r=12, axis='y')
        make_cylinder_to(l_hand_dual, 0.068, 0.045, 0.068, LColor(0.05, 0.05, 0.06, 1.0), -0.038, -0.14, -0.13, rot_h=10, rot_p=24, rot_r=8, axis='y')
        make_cube_to(l_hand_dual, 0.064, 0.095, 0.064, LColor(0.12, 0.12, 0.14, 1.0), -0.020, -0.075, -0.095, rot_p=16)
        make_cube_to(l_hand_dual, 0.062, 0.040, 0.022, LColor(0.20, 0.22, 0.25, 1.0), -0.036, -0.065, -0.082, rot_p=16, rot_r=-12)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.015, -0.062, rot_p=16)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.025, -0.098, rot_p=16)
        make_cube_to(l_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), -0.005, -0.035, -0.134, rot_p=16)
        make_cube_to(l_hand_dual, 0.022, 0.068, 0.022, LColor(0.12, 0.12, 0.14, 1.0), -0.026, 0.012, -0.024, rot_h=6, rot_p=8)
        make_cube_to(l_hand_dual, 0.025, 0.058, 0.025, LColor(0.12, 0.12, 0.14, 1.0), 0.026, -0.055, -0.032, rot_h=-10, rot_p=-8)

        # (2) 우측 9mm 글록 (Right Hand Glock)
        self.vm_dual_right = self.vm_dual.attachNewNode("vm_dual_right")
        self.vm_dual_right.setPos(self.ads_hip_pos_dual_r)
        self.vm_dual_right.setHpr(Vec3(-4.0, 1.0, -10.0))

        self.dual_right_recoil = self.vm_dual_right.attachNewNode("dual_right_recoil")
        right_frame = self.dual_right_recoil.attachNewNode("dual_right_frame")
        rgrip = make_cube_to(right_frame, 0.050, 0.10, 0.18, glock_polymer, 0, -0.05, -0.08)
        rgrip.setP(20)
        make_cube_to(right_frame, 0.048, 0.18, 0.044, glock_polymer, 0, 0.07, 0.005)
        make_cube_to(right_frame, 0.024, 0.07, 0.052, glock_polymer, 0, 0.035, -0.035)

        self.dual_right_slide = self.dual_right_recoil.attachNewNode("dual_right_slide")
        make_cylinder_to(self.dual_right_recoil, .032, .10, .032, steel_barrel, 0, .20, .035, axis='y')
        make_cylinder_to(self.dual_right_recoil, .020, .01, .020, LColor(.01, .01, .01, 1), 0, .254, .035, axis='y')
        make_cube_to(self.dual_right_slide, 0.052, 0.26, 0.064, glock_slide, 0, 0.05, 0.040)
        make_cube_to(self.dual_right_slide, 0.054, 0.05, 0.062, glock_polymer, 0, -0.04, 0.040)
        make_cube_to(self.dual_right_slide, 0.018, 0.06, 0.030, glock_polymer, 0.022, 0.04, 0.050)
        r_front = make_cube_to(self.dual_right_slide, 0.010, 0.016, 0.016, glock_white, 0, 0.17, 0.076)
        r_front.setLightOff()

        self.dual_right_hammer = self.dual_right_recoil.attachNewNode("dual_right_hammer")
        self.dual_right_hammer.setPos(0, -0.085, 0.034)
        make_cube_to(self.dual_right_hammer, 0.014, 0.018, 0.035, glock_slide, 0, -0.005, 0.010)

        self.dual_right_mag = right_frame.attachNewNode("dual_right_mag")
        self.dual_right_mag.setPos(0, -0.05, -0.08)
        self.dual_right_mag.setP(20)
        make_cube_to(self.dual_right_mag, 0.040, 0.075, 0.16, glock_polymer, 0, 0, 0)

        self.dual_right_flash_geom = make_muzzle_flash_to(self.dual_right_recoil, 0.055, 0.14, 0, 0.32, 0.035)
        self.dual_right_flash_geom.setLightOff()
        self.dual_right_flash_geom.hide()

        self.dual_right_flash_light = PointLight('dual_right_light')
        self.dual_right_flash_light.setColor((2.6, 2.0, 0.8, 1.0))
        self.dual_right_flash_light.setAttenuation((1.0, 0.09, 0.018))
        self.dual_right_flash_light_np = self.dual_right_recoil.attachNewNode(self.dual_right_flash_light)
        self.dual_right_flash_light_np.setPos(0, 0.32, 0.035)

        # 오른손 아킴보 권총 파지 전술 손 & 팔
        r_hand_dual = self.dual_right_recoil.attachNewNode("dual_r_hand")
        make_cylinder_to(r_hand_dual, 0.075, 0.26, 0.075, LColor(0.08, 0.09, 0.11, 1.0), 0.065, -0.25, -0.20, rot_h=-12, rot_p=30, rot_r=-12, axis='y')
        make_cylinder_to(r_hand_dual, 0.068, 0.045, 0.068, LColor(0.05, 0.05, 0.06, 1.0), 0.038, -0.14, -0.13, rot_h=-10, rot_p=24, rot_r=-8, axis='y')
        make_cube_to(r_hand_dual, 0.064, 0.095, 0.064, LColor(0.12, 0.12, 0.14, 1.0), 0.020, -0.075, -0.095, rot_p=16)
        make_cube_to(r_hand_dual, 0.062, 0.040, 0.022, LColor(0.20, 0.22, 0.25, 1.0), 0.036, -0.065, -0.082, rot_p=16, rot_r=12)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.015, -0.062, rot_p=16)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.025, -0.098, rot_p=16)
        make_cube_to(r_hand_dual, 0.060, 0.036, 0.032, LColor(0.12, 0.12, 0.14, 1.0), 0.005, -0.035, -0.134, rot_p=16)
        make_cube_to(r_hand_dual, 0.022, 0.068, 0.022, LColor(0.12, 0.12, 0.14, 1.0), 0.026, 0.012, -0.024, rot_h=-6, rot_p=8)
        make_cube_to(r_hand_dual, 0.025, 0.058, 0.025, LColor(0.12, 0.12, 0.14, 1.0), -0.026, -0.055, -0.032, rot_h=10, rot_p=-8)

    def _build_ar_viewmodel(self):
        """3. 5.56mm H&K HK416 (hk16) 하이엔드 전술 돌격소총 정밀 뷰모델 지오메트리"""
        self.vm_ar = self.vm_root.attachNewNode("vm_ar")
        self.vm_ar.setPos(self.ads_hip_pos_ar)
        self.vm_ar.setHpr(Vec3(1.2, 0.6, -0.6))

        self.ar_recoil_node = self.vm_ar.attachNewNode("ar_recoil_node")

        # H&K 특유의 하드코트 아노다이징 & 밀스펙 파츠 색상 팔레트
        hk_black = LColor(0.12, 0.13, 0.15, 1.0)        # 상/하부 리시버 & 쿼드 레일 알루미늄
        hk_steel = LColor(0.08, 0.08, 0.09, 1.0)        # 총열, 볼트 캐리어, 가스 블록, 소염기
        hk_furniture = LColor(0.05, 0.05, 0.06, 1.0)    # HK 배틀 그립, E1 개머리판, 수직 손잡이 폴리머
        hk_accent_metal = LColor(0.24, 0.26, 0.28, 1.0) # 크로스볼트 고정나사, 핀, 셀렉터 레버
        hk_red = LColor(0.85, 0.15, 0.12, 1.0)          # HK 연발 셀렉터 레드 각인
        hk_white = LColor(0.90, 0.90, 0.92, 1.0)        # HK 안전 셀렉터 화이트 각인
        hk_follower = LColor(0.95, 0.40, 0.05, 1.0)     # 고시인성 오렌지색 안티틸트 팔로워

        # -------------------------------------------------------------
        # 1) HK416 상부 리시버 (Upper Receiver - 피스톤 통과를 위한 시그니처 하이 레일 프로파일)
        # -------------------------------------------------------------
        # 상부 리시버 본체 (M4보다 전고가 높은 HK 고유 형상)
        make_cube_to(self.ar_recoil_node, 0.056, 0.28, 0.088, hk_black, 0, 0.04, 0.024)
        # 상단 일체형 피카티니 레일 베이스
        make_cube_to(self.ar_recoil_node, 0.034, 0.28, 0.016, hk_black, 0, 0.04, 0.076)
        # 피카티니 레일 슬롯 텍스처 (상부 리시버)
        for ry in (-0.08, -0.04, 0.0, 0.04, 0.08, 0.12, 0.16):
            make_cube_to(self.ar_recoil_node, 0.036, 0.008, 0.005, hk_steel, 0, ry, 0.082)

        # 탄피 배출구 및 HK 크롬/스틸 볼트 캐리어
        make_cube_to(self.ar_recoil_node, 0.048, 0.11, 0.032, hk_steel, 0.027, 0.06, 0.038)
        # HK 폴리머 더스트 커버 (하향 개방)
        make_cube_to(self.ar_recoil_node, 0.010, 0.11, 0.030, hk_furniture, 0.030, 0.06, 0.018, rot_r=25)
        # HK 포워드 어시스트 (우측 후방 원통형 하우징 & 플런저)
        make_cylinder_to(self.ar_recoil_node, 0.020, 0.045, 0.020, hk_black, 0.032, -0.045, 0.046, rot_h=20, rot_p=12, axis='y')
        make_cylinder_to(self.ar_recoil_node, 0.014, 0.012, 0.014, hk_accent_metal, 0.038, -0.068, 0.050, rot_h=20, rot_p=12, axis='y')
        # 케이스 디플렉터 (황동 탄피 편향 쐐기 돌기)
        make_cube_to(self.ar_recoil_node, 0.022, 0.030, 0.028, hk_black, 0.032, -0.015, 0.040, rot_h=-18)
        # HK 양손잡이용 장전손잡이 (대형 전술 래치 장착)
        make_cube_to(self.ar_recoil_node, 0.038, 0.035, 0.014, hk_steel, 0, -0.105, 0.066)
        make_cube_to(self.ar_recoil_node, 0.020, 0.022, 0.016, hk_furniture, -0.025, -0.105, 0.066)

        # -------------------------------------------------------------
        # 2) HK416 하부 리시버 & 유러피언 스트레이트 탄창 삽입구 (Magwell)
        # -------------------------------------------------------------
        # 하부 리시버 본체 (M4의 경사진 형상과 달리 직각에 가까운 HK 고유 스트레이트 탄창 하우징)
        make_cube_to(self.ar_recoil_node, 0.054, 0.115, 0.098, hk_black, 0, 0.105, -0.030)
        # 탄창 삽입구 플레어 베벨 립
        make_cube_to(self.ar_recoil_node, 0.056, 0.118, 0.016, hk_black, 0, 0.105, -0.076)
        # 탄창 멈치 (우측) & 노리쇠 멈치 패들 (좌측)
        make_cube_to(self.ar_recoil_node, 0.008, 0.022, 0.022, hk_accent_metal, 0.029, 0.07, -0.010)
        make_cube_to(self.ar_recoil_node, 0.010, 0.020, 0.034, hk_accent_metal, -0.029, 0.055, 0.018)
        # 분해 조립 테이크다운 핀 (전방/후방)
        make_cylinder_to(self.ar_recoil_node, 0.014, 0.060, 0.014, hk_accent_metal, 0, -0.07, -0.008, axis='x')
        make_cylinder_to(self.ar_recoil_node, 0.014, 0.060, 0.014, hk_accent_metal, 0, 0.155, 0.008, axis='x')
        # HK 양방향 안전/단발/연발 셀렉터 스위치 및 레드/화이트 픽토그램 각인
        make_cylinder_to(self.ar_recoil_node, 0.016, 0.062, 0.016, hk_steel, 0, -0.035, -0.012, axis='x')
        make_cube_to(self.ar_recoil_node, 0.006, 0.026, 0.010, hk_steel, -0.031, -0.022, -0.012, rot_p=-15)
        make_cube_to(self.ar_recoil_node, 0.004, 0.006, 0.006, hk_white, -0.030, -0.042, -0.004)
        make_cube_to(self.ar_recoil_node, 0.004, 0.012, 0.006, hk_red, -0.030, -0.024, 0.002)
        # 확장형 윈터 트리거 가드 (장갑 착용 시에도 넉넉한 하향 곡선)
        make_cube_to(self.ar_recoil_node, 0.022, 0.082, 0.010, hk_steel, 0, -0.020, -0.072)
        # 정밀 곡면 매치 트리거 (방아쇠)
        make_cube_to(self.ar_recoil_node, 0.010, 0.016, 0.042, hk_accent_metal, 0, -0.020, -0.045, rot_p=18)

        # -------------------------------------------------------------
        # 3) HK 프리플로팅 쿼드 레일 핸드가드 & 아이코닉 크로스볼트 (Cross-Bolt)
        # -------------------------------------------------------------
        # 핸드가드 본체 (팔각형 단면 프리플로팅 알루미늄)
        make_cube_to(self.ar_recoil_node, 0.054, 0.34, 0.072, hk_black, 0, 0.33, 0.025)
        # 상부 레일 (리시버와 단차 없이 연결되는 연속형 피카티니 레일)
        make_cube_to(self.ar_recoil_node, 0.034, 0.34, 0.016, hk_black, 0, 0.33, 0.076)
        for ry in (0.20, 0.24, 0.28, 0.32, 0.36, 0.40, 0.44, 0.48):
            make_cube_to(self.ar_recoil_node, 0.036, 0.008, 0.005, hk_steel, 0, ry, 0.082)
        # 하부 레일
        make_cube_to(self.ar_recoil_node, 0.030, 0.32, 0.014, hk_black, 0, 0.33, -0.018)
        # 좌우측 측면 피카티니 레일
        make_cube_to(self.ar_recoil_node, 0.014, 0.32, 0.028, hk_black, -0.028, 0.33, 0.025)
        make_cube_to(self.ar_recoil_node, 0.014, 0.32, 0.028, hk_black, 0.028, 0.33, 0.025)
        # ★ HK416의 가장 상징적인 외형 특징: 대형 핸드가드 고정 크로스볼트 (Cross-Bolt Screw)
        make_cylinder_to(self.ar_recoil_node, 0.024, 0.064, 0.024, hk_accent_metal, 0, 0.185, 0.018, axis='x')
        make_cube_to(self.ar_recoil_node, 0.008, 0.026, 0.026, hk_steel, 0.032, 0.185, 0.018)
        # 배럴 너트 연결 링 칼라
        make_cylinder_to(self.ar_recoil_node, 0.052, 0.035, 0.052, hk_steel, 0, 0.165, 0.025, axis='y')
        # 핸드가드 통풍 냉각 홀 (내부 피스톤 및 배럴 노출)
        for vy in (0.24, 0.32, 0.40):
            make_cube_to(self.ar_recoil_node, 0.056, 0.040, 0.016, hk_steel, 0, vy, 0.025)
        # 좌측 레일 보호용 고무 래더 커버
        make_cube_to(self.ar_recoil_node, 0.006, 0.22, 0.024, hk_furniture, -0.033, 0.34, 0.025)

        # -------------------------------------------------------------
        # 4) 단행정 가스 피스톤 시스템 (Short-Stroke Gas Piston) & 접이식 가늠쇠
        # -------------------------------------------------------------
        # 가스 블록 (총열에 핀 고정되는 강철 가스 블록)
        make_cube_to(self.ar_recoil_node, 0.032, 0.048, 0.068, hk_steel, 0, 0.505, 0.038)
        # 가스 조절기 노브 (Normal / Suppressed 전방 플러그)
        make_cylinder_to(self.ar_recoil_node, 0.020, 0.032, 0.020, hk_accent_metal, 0, 0.535, 0.058, axis='y')
        # 가스 피스톤 작동 로드 (상부 채널 내부 관통)
        make_cylinder_to(self.ar_recoil_node, 0.016, 0.32, 0.016, hk_accent_metal, 0, 0.34, 0.055, axis='y')
        # 개방형 가늠쇠: 얇은 중앙 기둥과 좌우 보호 날개. 기둥 끝은 z=0.125.
        self.ar_front_sight = self.ar_recoil_node.attachNewNode("ar_front_sight")
        self.ar_front_sight.setY(0.505)
        make_cube_to(self.ar_front_sight, 0.036, 0.024, 0.010, hk_steel, 0, 0, 0.087)
        make_cube_to(self.ar_front_sight, 0.006, 0.009, 0.033, hk_accent_metal, 0, 0, 0.1085)
        for side in (-1, 1):
            make_cube_to(self.ar_front_sight, 0.005, 0.014, 0.035, hk_steel,
                         side * 0.017, 0, 0.109, rot_r=side * 20)

        # -------------------------------------------------------------
        # 5) 14.5" 헤비 냉간단조 총열 & HK 버드케이지 소염기 (Birdcage Flash Hider)
        # -------------------------------------------------------------
        # 14.5인치 헤비 컨투어 카본 스틸 총열
        make_cylinder_to(self.ar_recoil_node, 0.028, 0.52, 0.028, hk_steel, 0, 0.46, 0.022, axis='y')
        # 5방향 가스 분출 포트를 가진 HK 정밀 소염기
        make_cylinder_to(self.ar_recoil_node, 0.036, 0.065, 0.036, hk_steel, 0, 0.725, 0.022, axis='y')
        # 총구 보어 및 크라운
        make_cylinder_to(self.ar_recoil_node, 0.020, 0.010, 0.020, LColor(0.02, 0.02, 0.02, 1.0), 0, 0.758, 0.022, axis='y')

        # -------------------------------------------------------------
        # 6) 개방형 가늠자: 중앙 홈으로 전방 가늠쇠를 정렬
        # -------------------------------------------------------------
        self.ar_rear_sight = self.ar_recoil_node.attachNewNode("ar_rear_sight")
        self.ar_rear_sight.setY(-0.075)
        make_cube_to(self.ar_rear_sight, 0.040, 0.022, 0.014, hk_steel, 0, 0, 0.091)
        for side in (-1, 1):
            make_cube_to(self.ar_rear_sight, 0.011, 0.012, 0.027, hk_steel,
                         side * 0.0145, 0, 0.1115)

        # -------------------------------------------------------------
        # 7) HK 고유 인체공학 배틀 그립 (HK Ergonomic Battle Grip)
        # -------------------------------------------------------------
        # A2 그립 대비 가파른 18도 경사각과 팜스웰(Palm-Swell), 비버테일
        make_cube_to(self.ar_recoil_node, 0.046, 0.088, 0.175, hk_furniture, 0, -0.095, -0.098, rot_p=18)
        # 리시버 후방 지지 비버테일 탕
        make_cube_to(self.ar_recoil_node, 0.038, 0.055, 0.055, hk_furniture, 0, -0.075, -0.035, rot_p=28)
        # 그립 좌우 엠보싱 팜스웰
        make_cube_to(self.ar_recoil_node, 0.052, 0.072, 0.120, hk_furniture, 0, -0.095, -0.100, rot_p=18)
        # 바닥 스토리지 컴파트먼트 캡 & 잠금 래치
        make_cube_to(self.ar_recoil_node, 0.048, 0.090, 0.022, hk_steel, 0, -0.122, -0.178, rot_p=18)

        # -------------------------------------------------------------
        # 8) HK 30발 스틸 해상탄창 (Curved 30-Round Maritime Steel Magazine)
        # -------------------------------------------------------------
        self.ar_mag_node = self.ar_recoil_node.attachNewNode("ar_mag_node")
        self.ar_mag_node.setPos(0, 0.12, -0.06)
        self.ar_mag_node.setP(12)
        # 삽입구 직선 진입부
        make_cube_to(self.ar_mag_node, 0.044, 0.090, 0.090, hk_steel, 0, 0.005, -0.015)
        # 고시인성 오렌지색 안티틸트 팔로워 (Anti-Tilt Follower)
        make_cube_to(self.ar_mag_node, 0.036, 0.072, 0.015, hk_follower, 0, 0.010, 0.025)
        # HK 강철 탄창의 매끄러운 곡면 바나나형 하부 본체
        make_cube_to(self.ar_mag_node, 0.044, 0.092, 0.160, hk_steel, 0, 0.020, -0.105, rot_p=14)
        # 탄창 하단 스틸 바닥판 (Floorplate)
        make_cube_to(self.ar_mag_node, 0.048, 0.096, 0.020, hk_furniture, 0, 0.046, -0.180, rot_p=14)

        # -------------------------------------------------------------
        # 9) HK E1 텔레스코픽 인체공학 신축식 개머리판 (Retractable Stock)
        # -------------------------------------------------------------
        # 밀스펙 버퍼 튜브 (Receiver Extension)
        make_cylinder_to(self.ar_recoil_node, 0.036, 0.22, 0.036, hk_steel, 0, -0.20, 0.022, axis='y')
        # 캐슬 너트 (Castle Nut) & 슬링 엔드플레이트
        make_cylinder_to(self.ar_recoil_node, 0.042, 0.020, 0.042, hk_accent_metal, 0, -0.095, 0.022, axis='y')
        # HK E1 개머리판 메인 슬리브
        make_cube_to(self.ar_recoil_node, 0.048, 0.19, 0.052, hk_furniture, 0, -0.25, 0.022)
        # 좌우 배터리 수납 뺨 받침 플레어 튜브 (Dual Flared Cheek Rests)
        make_cylinder_to(self.ar_recoil_node, 0.028, 0.16, 0.028, hk_furniture, -0.022, -0.25, 0.028, axis='y')
        make_cylinder_to(self.ar_recoil_node, 0.028, 0.16, 0.028, hk_furniture, 0.022, -0.25, 0.028, axis='y')
        # 하단 신축 조절 레버 (Adjustment Latch)
        make_cube_to(self.ar_recoil_node, 0.022, 0.080, 0.025, hk_furniture, 0, -0.23, -0.015)
        # 하단 스트럿 및 양방향 슬링 고리
        make_cube_to(self.ar_recoil_node, 0.040, 0.16, 0.095, hk_furniture, 0, -0.27, -0.045)
        # ★ HK 특유의 볼록형 두터운 고무 버트패드 (Convex Rubber Buttpad)
        make_cube_to(self.ar_recoil_node, 0.048, 0.028, 0.145, hk_furniture, 0, -0.345, -0.035)

        # -------------------------------------------------------------
        # 10) 전술 액세서리: 스타비 포어그립 & AN/PEQ-15 전술 표적지시기
        # -------------------------------------------------------------
        # 하부 레일 장착 TangoDown / HK 택티컬 스타비 수직 손잡이
        make_cylinder_to(self.ar_recoil_node, 0.036, 0.036, 0.125, hk_furniture, 0, 0.32, -0.082, axis='z')
        make_cube_to(self.ar_recoil_node, 0.040, 0.055, 0.020, hk_steel, 0, 0.32, -0.025)
        # 우측 레일 장착 AN/PEQ-15 ATPIAL 레이저 모듈 (다크 코요테/블랙 복합 하우징)
        make_cube_to(self.ar_recoil_node, 0.024, 0.090, 0.032, hk_furniture, 0.032, 0.36, 0.046)
        make_cylinder_to(self.ar_recoil_node, 0.014, 0.015, 0.014, hk_steel, 0.032, 0.408, 0.048, axis='y')
        make_cylinder_to(self.ar_recoil_node, 0.016, 0.016, 0.010, hk_accent_metal, 0.032, 0.34, 0.064, axis='z')

        # -------------------------------------------------------------
        # 11) 5.56mm 총구 화염 및 동적 포인트 라이트
        # -------------------------------------------------------------
        self.ar_muzzle_flash_geom = make_muzzle_flash_to(self.ar_recoil_node, 0.065, 0.21, 0, 0.77, 0.022)
        self.ar_muzzle_flash_geom.setLightOff()
        self.ar_muzzle_flash_geom.hide()

        self.ar_muzzle_light = PointLight('ar_muzzle_light')
        self.ar_muzzle_light.setColor((3.8, 2.5, 0.8, 1.0))
        self.ar_muzzle_light.setAttenuation((1.0, 0.06, 0.012))
        self.ar_muzzle_light_np = self.ar_recoil_node.attachNewNode(self.ar_muzzle_light)
        self.ar_muzzle_light_np.setPos(0, 0.78, 0.022)

        # -------------------------------------------------------------
        # 12) 1인칭 전술 장갑 및 손/팔 (특수전 대원 파지 모델링)
        # -------------------------------------------------------------
        sleeve_col = LColor(0.08, 0.09, 0.11, 1.0)
        strap_col = LColor(0.05, 0.05, 0.06, 1.0)
        glove_dark = LColor(0.12, 0.12, 0.14, 1.0)
        knuckle_col = LColor(0.20, 0.22, 0.25, 1.0)

        # 오른손: HK 배틀 그립 파지 & 검지 방아쇠 위치
        r_hand = self.ar_recoil_node.attachNewNode("ar_r_hand")
        make_cylinder_to(r_hand, 0.075, 0.30, 0.075, sleeve_col, 0.065, -0.28, -0.21, rot_h=-12, rot_p=28, rot_r=-10, axis='y')
        make_cylinder_to(r_hand, 0.068, 0.045, 0.068, strap_col, 0.036, -0.16, -0.13, rot_h=-10, rot_p=24, rot_r=-6, axis='y')
        make_cube_to(r_hand, 0.064, 0.095, 0.064, glove_dark, 0.020, -0.10, -0.09, rot_p=22)
        make_cube_to(r_hand, 0.062, 0.040, 0.022, knuckle_col, 0.036, -0.09, -0.08, rot_p=22, rot_r=12)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.045, -0.075, rot_p=22)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.058, -0.105, rot_p=22)
        make_cube_to(r_hand, 0.060, 0.036, 0.032, glove_dark, 0.005, -0.070, -0.135, rot_p=22)
        make_cube_to(r_hand, 0.022, 0.068, 0.022, glove_dark, 0.026, -0.015, -0.030, rot_p=10)
        make_cube_to(r_hand, 0.025, 0.058, 0.025, glove_dark, -0.026, -0.085, -0.035, rot_h=10, rot_p=-10)

        # 왼손: 전방 스타비 수직 손잡이 견착 파지
        l_hand = self.ar_recoil_node.attachNewNode("ar_l_hand")
        make_cylinder_to(l_hand, 0.075, 0.32, 0.075, sleeve_col, -0.085, 0.08, -0.22, rot_h=16, rot_p=32, rot_r=16, axis='y')
        make_cylinder_to(l_hand, 0.068, 0.045, 0.068, strap_col, -0.048, 0.18, -0.14, rot_h=14, rot_p=26, rot_r=10, axis='y')
        make_cube_to(l_hand, 0.066, 0.095, 0.064, glove_dark, -0.018, 0.28, -0.09, rot_p=8, rot_r=-10)
        make_cube_to(l_hand, 0.060, 0.050, 0.026, knuckle_col, -0.032, 0.30, -0.09, rot_p=8, rot_r=-10)
        make_cube_to(l_hand, 0.036, 0.070, 0.070, glove_dark, 0.005, 0.31, -0.075)

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
        make_cylinder_to(self.sg_recoil_node, 0.044, 0.52, 0.044, steel_barrel, 0, 0.40, 0.045, axis='y')
        make_cylinder_to(self.sg_recoil_node, 0.032, 0.015, 0.032, LColor(0.01, 0.01, 0.01, 1.0), 0, 0.665, 0.045, axis='y')
        make_cylinder_to(self.sg_recoil_node, 0.054, 0.36, 0.054, steel_dark, 0, 0.32, 0.045, axis='y')

        # 하부 8발 튜브 탄창
        make_cylinder_to(self.sg_recoil_node, 0.040, 0.48, 0.040, steel_dark, 0, 0.36, -0.010, axis='y')
        make_cylinder_to(self.sg_recoil_node, 0.044, 0.03, 0.044, steel_slide, 0, 0.60, -0.010, axis='y')

        # 펌프액션 슬라이드 포어엔드 (Pump Slide Handle)
        self.sg_pump_node = self.sg_recoil_node.attachNewNode("sg_pump_node")
        self.sg_pump_node.setPos(0, 0.28, -0.010)
        make_cylinder_to(self.sg_pump_node, 0.072, 0.20, 0.072, grip_col, 0, 0, 0, axis='y')
        make_cube_to(self.sg_pump_node, 0.078, 0.16, 0.025, steel_dark, 0, 0, 0)
        # 펌프 하부 택티컬 라이트 바디
        make_cylinder_to(self.sg_pump_node, 0.038, 0.12, 0.038, steel_dark, 0, 0.04, -0.045, axis='y')
        lens = make_cylinder_to(self.sg_pump_node, 0.032, 0.008, 0.032, LColor(1.0, 0.96, 0.82, 0.95), 0, 0.105, -0.045, axis='y')
        lens.setLightOff()

        # 권총 손잡이 및 전술 개머리판
        make_cube_to(self.sg_recoil_node, 0.054, 0.11, 0.19, grip_col, 0, -0.14, -0.08, rot_p=22)
        make_cube_to(self.sg_recoil_node, 0.042, 0.30, 0.065, steel_dark, 0, -0.28, -0.01)
        make_cube_to(self.sg_recoil_node, 0.054, 0.045, 0.15, grip_col, 0, -0.43, -0.03)

        # 광섬유 가늠쇠 & 고스트링 가늠자
        front_bead = make_sphere_to(self.sg_recoil_node, 0.010, 0.025, 0.014, fiber_red, 0, 0.64, 0.076)
        front_bead.setLightOff()
        make_cube_to(self.sg_recoil_node, 0.038, 0.020, 0.026, steel_dark, 0, -0.12, 0.076)

        # 샷건 대구경 총구 화염 및 조명
        self.sg_muzzle_flash_geom = make_muzzle_flash_to(self.sg_recoil_node, 0.105, 0.26, 0, 0.74, 0.045)
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
        make_cylinder_to(r_hand_sg, 0.075, 0.32, 0.075, sg_sleeve, 0.065, -0.34, -0.21, rot_h=-12, rot_p=28, rot_r=-10, axis='y')
        make_cylinder_to(r_hand_sg, 0.068, 0.045, 0.068, sg_strap, 0.036, -0.22, -0.13, rot_h=-10, rot_p=24, rot_r=-6, axis='y')
        make_cube_to(r_hand_sg, 0.064, 0.095, 0.064, sg_glove, 0.020, -0.15, -0.09, rot_p=22)
        make_cube_to(r_hand_sg, 0.062, 0.040, 0.022, sg_knuckle, 0.036, -0.14, -0.08, rot_p=22, rot_r=12)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.095, -0.075, rot_p=22)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.108, -0.105, rot_p=22)
        make_cube_to(r_hand_sg, 0.060, 0.036, 0.032, sg_glove, 0.005, -0.120, -0.135, rot_p=22)
        make_cube_to(r_hand_sg, 0.022, 0.068, 0.022, sg_glove, 0.026, -0.065, -0.030, rot_p=10)
        make_cube_to(r_hand_sg, 0.025, 0.058, 0.025, sg_glove, -0.026, -0.135, -0.035, rot_h=10, rot_p=-10)

        # (2) 왼손: 샷건 펌프액션 슬라이드 손잡이(sg_pump_node)에 직접 결속 -> 펌프 당김 시 100% 동기화 슬라이딩
        l_hand_sg = self.sg_pump_node.attachNewNode("sg_l_hand")
        make_cylinder_to(l_hand_sg, 0.078, 0.32, 0.078, sg_sleeve, -0.095, -0.26, -0.21, rot_h=18, rot_p=32, rot_r=20, axis='y')
        make_cylinder_to(l_hand_sg, 0.068, 0.055, 0.068, sg_strap, -0.048, -0.11, -0.10, rot_h=15, rot_p=24, rot_r=12, axis='y')
        make_cube_to(l_hand_sg, 0.065, 0.11, 0.055, sg_glove, -0.015, -0.015, -0.050, rot_r=15)
        make_cube_to(l_hand_sg, 0.060, 0.05, 0.025, sg_knuckle, -0.038, -0.015, -0.052, rot_r=18)
        make_cube_to(l_hand_sg, 0.076, 0.12, 0.034, sg_glove, 0.006, 0.005, -0.042)
        make_cube_to(l_hand_sg, 0.032, 0.11, 0.044, sg_glove, 0.044, 0.005, -0.020)
        make_cube_to(l_hand_sg, 0.032, 0.072, 0.028, sg_glove, -0.042, 0.012, 0.018, rot_h=8, rot_p=6)

    def _eject_casing(self, is_left=False, is_shotgun=False):
        """Eject from the moving weapon port in world-root coordinates."""
        weapon = 'SHOTGUN' if is_shotgun else self.current_weapon
        side = -1 if weapon == 'DUAL_PISTOL' and is_left else 1
        profiles = {
            'PISTOL': ('recoil_node', (.040, .040, .055), (2.2, 3.2), (1.2, 2.0), (-.5, -.1)),
            'DUAL_PISTOL': ('dual_left_recoil' if is_left else 'dual_right_recoil',
                            (.030 * side, .045, .045), (2.0, 3.0), (1.2, 1.8), (-.4, -.1)),
            'AR': ('ar_recoil_node', (.042, .050, .038), (2.4, 3.4), (1.4, 2.2), (-.3, .2)),
            'SHOTGUN': ('sg_recoil_node', (.045, .040, .035), (1.8, 2.6), (1.0, 1.8), (-.6, -.2)),
        }
        node_name, port, sideways, upwards, forwards = profiles[weapon]
        node = getattr(self, node_name)
        position = self.world_root.getRelativePoint(node, Vec3(*port))
        right = self.world_root.getRelativeVector(node, Vec3(side, 0, 0)).normalized()
        up = self.world_root.getRelativeVector(node, Vec3(0, 0, 1)).normalized()
        forward = self.world_root.getRelativeVector(node, Vec3(0, 1, 0)).normalized()
        velocity = (right * random.uniform(*sideways) + up * random.uniform(*upwards)
                    + forward * random.uniform(*forwards))
        self.casing_effects.emit(weapon, position, velocity, is_left=side < 0)

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
        wall_dist, wall_hit_pos = raycast_walls(chunks, ray_origin, ray_dir, max_dist=65.0)

        closest_monster = None
        closest_barrel = None
        min_hit_dist = wall_dist if wall_hit_pos is not None else 65.0

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
                    hh_stats = get_player_perk_stats(player, "headhunter")
                    dmg *= hh_stats.get("damage_mult", 1.45)  # 헤드헌터 퍽: 헤드샷 치명타 피해 증폭

            # 아드레날린 슬라이딩 퍽: 슬라이딩 중 사격 시 피해 증폭 & 불릿타임
            if is_sliding and player and hasattr(player, 'has_perk') and player.has_perk("adrenaline_slide"):
                as_stats = get_player_perk_stats(player, "adrenaline_slide")
                as_mult = as_stats.get("damage_mult", 1.50)
                as_dur = as_stats.get("duration", 1.8)
                dmg *= as_mult
                game_inst = getattr(self.base, 'game', None) or self.base
                if hasattr(game_inst, 'trigger_bullet_time'):
                    game_inst.trigger_bullet_time(as_dur)
                if p_idx == 0:
                    self.ui_mgr.show_hit_marker(f">> [아드레날린 슬라이드 샷!] 피해 {as_mult:.1f}x & 불릿타임!", (0.35, 1.0, 0.8, 1.0))

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

            # 전투 통계 누적 및 3D 플로팅 대미지 폰트 투영
            actual_hit_dmg = min(prev_m_hp, dmg)
            self.record_combat_hit(actual_hit_dmg, is_headshot=is_headshot)
            if hasattr(self.ui_mgr, 'spawn_floating_damage'):
                self.ui_mgr.spawn_floating_damage(dmg, impact_world, is_crit=is_crit, is_headshot=is_headshot)

            # 드래곤 브레스 퍽: 지속 화염 피해 상태이상 부여
            if player and hasattr(player, 'has_perk') and player.has_perk("dragons_breath"):
                db_stats = get_player_perk_stats(player, "dragons_breath")
                db_dps = db_stats.get("dps", 25.0)
                db_dur = db_stats.get("duration", 3.0)
                if hasattr(closest_monster, 'apply_burn'):
                    closest_monster.apply_burn(dps=db_dps, duration=db_dur)
                else:
                    closest_monster.burn_timer = db_dur
                    closest_monster.burn_dps = db_dps
                if p_idx == 0:
                    self.ui_mgr.show_hit_marker("[화염] [드래곤 브레스 착탄!] 지속 화염 피해!", (1.0, 0.45, 0.15, 1.0))

            # 흡혈 탄환 퍽: 헤드샷 치명타 적중 시 체력 회복
            if is_headshot and player and hasattr(player, 'has_perk') and player.has_perk("vampiric_leech"):
                vl_stats = get_player_perk_stats(player, "vampiric_leech")
                player.heal(vl_stats.get("headshot_heal", 5.0))

            # 테슬라 아크 퍽: 치명타 시 주변 연쇄 감전 (착탄 생성지 기준 방사형 번개 방출)
            if is_crit and player and hasattr(player, 'has_perk') and player.has_perk("tesla_arc") and p_idx == 0:
                tesla_stats = get_player_perk_stats(player, "tesla_arc")
                t_dmg = tesla_stats.get("damage", 35.0)
                t_radius = tesla_stats.get("radius", 7.5)
                max_targets = min(8, int(tesla_stats.get("targets", 2)))
                t_shock_dur = tesla_stats.get("shock_duration", 0.85)
                t_prim_dur = tesla_stats.get("primary_duration", 0.65)
                t_stun_dur = tesla_stats.get("stun_duration", 0.40)

                if hasattr(closest_monster, 'apply_shock'):
                    closest_monster.apply_shock(damage=0.0, duration=t_prim_dur, hit_pos=impact_world)

                shocked = 0
                for om in monster_list:
                    if om != closest_monster and getattr(om, 'hp', 0) > 0 and not getattr(om, 'is_corpse', False):
                        if (om.pos - impact_world).length() <= t_radius:
                            if hasattr(om, 'apply_shock'):
                                om.apply_shock(damage=t_dmg, duration=t_shock_dur, hit_pos=impact_world)
                            else:
                                om.take_damage(t_dmg, apply_knockback=True, hit_dir=(om.pos - impact_world).normalized())
                                om.stun(t_stun_dur)
                            shocked += 1
                            if shocked >= max_targets:
                                break
                if shocked > 0:
                    self.ui_mgr.show_hit_marker(f"[★ 테슬라 아크!] {shocked}체 연쇄 방전 감전!", (0.4, 0.9, 1.0, 1.0))

            # 장갑 관통탄 퍽: 몬스터를 관통하여 후방의 적 추가 타격
            if player and hasattr(player, 'has_perk') and player.has_perk("armor_piercing"):
                ap_stats = get_player_perk_stats(player, "armor_piercing")
                max_targets = int(ap_stats.get("targets", 1))
                pierce_origin = impact_world + ray_dir * 0.4
                chunks = getattr(self.base, 'chunks', {})
                pierce_wall_dist, _ = raycast_walls(chunks, pierce_origin, ray_dir, max_dist=55.0)

                pierce_candidates = []
                for m2 in monster_list:
                    if m2 != closest_monster and getattr(m2, 'hp', 0) > 0 and not getattr(m2, 'is_corpse', False):
                        hit2, dist2 = m2.is_hit_by_ray(pierce_origin, ray_dir)
                        if hit2 and 0.0 < dist2 < pierce_wall_dist:
                            pierce_candidates.append((dist2, m2))

                pierce_candidates.sort(key=lambda item: item[0])
                hit_count = 0
                for sec_dist, sec_monster in pierce_candidates[:max_targets]:
                    sec_prev_hp = getattr(sec_monster, 'hp', 1)
                    sec_dead = sec_monster.take_damage(dmg, apply_knockback=True, hit_dir=ray_dir)
                    sec_impact = pierce_origin + ray_dir * sec_dist
                    self.spawn_hit_particles(sec_impact, is_blood=True)
                    self.record_combat_hit(min(sec_prev_hp, dmg), is_headshot=False)
                    if hasattr(self.ui_mgr, 'spawn_floating_damage'):
                        self.ui_mgr.spawn_floating_damage(dmg, sec_impact, is_crit=False, is_headshot=False)
                    if self.audio_mgr and hasattr(self.audio_mgr, 'play_flesh_hit'):
                        self.audio_mgr.play_flesh_hit()
                    if sec_dead:
                        self.register_kill(player=player)
                        if hasattr(sec_monster, 'turn_into_corpse'):
                            sec_monster.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player:
                            player.gain_exp(getattr(sec_monster, 'exp_value', 35))
                    hit_count += 1
                if hit_count > 0 and p_idx == 0:
                    self.ui_mgr.show_hit_marker(f">> [장갑 관통탄!] 후방 적 {hit_count}체 관통 타격!", (0.4, 0.85, 1.0, 1.0))

            if player and hasattr(player, 'recover_stamina'):
                gain = 24.0 if is_crit else 10.0
                if is_dead:
                    gain += 16.0
                player.recover_stamina(gain / max(1, cfg["pellets"] if cfg["pellets"] > 1 else 1))

            if p_idx == 0:
                if is_crit:
                    if is_headshot and self.audio_mgr and hasattr(self.audio_mgr, 'play_headshot_crunch'):
                        self.audio_mgr.play_headshot_crunch()
                    elif self.audio_mgr and hasattr(self.audio_mgr, 'play_crit_hit'):
                        self.audio_mgr.play_crit_hit()
                else:
                    # 몸통 피격 시 유기물 타격음 (Flesh Impact SFX)
                    if self.audio_mgr and hasattr(self.audio_mgr, 'play_flesh_hit'):
                        self.audio_mgr.play_flesh_hit()

                if is_headshot and hasattr(closest_monster, 'stun_timer') and isinstance(getattr(closest_monster, 'stun_timer', None), (int, float)):
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

                # 흡혈 탄환 퍽: 처치 시 체력 회복
                if player and hasattr(player, 'has_perk') and player.has_perk("vampiric_leech"):
                    vl_stats = get_player_perk_stats(player, "vampiric_leech")
                    k_heal = vl_stats.get("kill_heal", 12.0)
                    player.heal(k_heal)
                    self.ui_mgr.show_hit_marker(f"🩸 [흡혈 탄환!] 체력 +{int(k_heal)} 회복", (0.35, 1.0, 0.45, 1.0))

                # 탄환 폭풍 퍽: 처치 시 무한 연사 폭주
                if player and hasattr(player, 'has_perk') and player.has_perk("bullet_storm"):
                    bs_stats = get_player_perk_stats(player, "bullet_storm")
                    dur = bs_stats.get("duration", 3.5)
                    self.bullet_storm_timer = dur
                    self.ui_mgr.show_hit_marker(f"🌪 [탄환 폭풍 발동!] {dur:.1f}초간 무한 연사 폭주! 🌪", (1.0, 0.85, 0.2, 1.0))

                # 파편 폭발 퍽: 처치 시 고열 파편 비산 범위 폭발
                if player and hasattr(player, 'has_perk') and player.has_perk("shrapnel_burst"):
                    sb_stats = get_player_perk_stats(player, "shrapnel_burst")
                    sb_dmg = sb_stats.get("damage", 75.0)
                    sb_rad = sb_stats.get("radius", 3.8)
                    game_inst = getattr(self.base, 'game', None) or self.base
                    exp_list = getattr(game_inst, 'explosions', None)
                    if exp_list is not None:
                        exp_list.append(ExplosionVisualEffect(self.world_root, impact_world, self.render))
                    for som in monster_list:
                        if som != closest_monster and getattr(som, 'hp', 0) > 0 and not getattr(som, 'is_corpse', False):
                            s_dist = (som.pos - impact_world).length()
                            if s_dist <= sb_rad:
                                s_dmg = sb_dmg * (1.0 - s_dist / sb_rad * 0.40)
                                s_dead = som.take_damage(s_dmg, apply_knockback=True, hit_dir=(som.pos - impact_world).normalized())
                                if s_dead:
                                    self.register_kill(player=player)
                                    if hasattr(som, 'turn_into_corpse'):
                                        som.turn_into_corpse(audio_mgr=self.audio_mgr)
                                    if player:
                                        player.gain_exp(getattr(som, 'exp_value', 35))
                    self.ui_mgr.show_hit_marker("💥 [파편 폭발!] 고열 파편 비산 범위 타격! 💥", (1.0, 0.55, 0.2, 1.0))

                # 헤드헌터 퍽: 헤드샷 처치 시 경험치 증폭
                if is_headshot and player and hasattr(player, 'has_perk') and player.has_perk("headhunter"):
                    hh_stats = get_player_perk_stats(player, "headhunter")
                    exp_gain = int(exp_gain * hh_stats.get("xp_mult", 2.0))

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

            # 도탄 사격 퍽: 벽면에 맞은 탄환이 이내의 최근접 몬스터로 도탄
            if player and hasattr(player, 'has_perk') and player.has_perk("ricochet"):
                rico_stats = get_player_perk_stats(player, "ricochet")
                rico_range = rico_stats.get("range", 14.0)
                rico_dmg_mult = rico_stats.get("damage_mult", 0.70)
                rico_target = None
                rico_min_d = rico_range
                for rm in monster_list:
                    if getattr(rm, 'hp', 0) > 0 and not getattr(rm, 'is_corpse', False):
                        d_rico = (rm.pos - wall_hit_pos).length()
                        if d_rico < rico_min_d:
                            rico_min_d = d_rico
                            rico_target = rm
                if rico_target is not None:
                    rico_dir = (rico_target.pos - wall_hit_pos).normalized()
                    rico_dmg = cfg["damage"] * rico_dmg_mult
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
            tracer_dist = 65.0
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

    def _reset_weapon_recoil(self):
        self.weapon_recoil.reset()
        self.recoil_timer = 0.0
        for name in ('recoil_node', 'dual_left_recoil', 'dual_right_recoil',
                     'ar_recoil_node', 'sg_recoil_node'):
            node = getattr(self, name, None)
            if node is not None and not node.isEmpty():
                node.setPos(0, 0, 0)
                node.setHpr(0, 0, 0)

    def _show_muzzle_flash(self, flash, is_overcharge=False):
        variants = flash.getChildren()
        chosen = random.randrange(len(variants))
        for index, variant in enumerate(variants):
            variant.show() if index == chosen else variant.hide()
        flash.setR(random.uniform(0, 360))
        size = random.uniform(.85, 1.1) * (1.1 if is_overcharge else 1.0)
        size *= 1.0 - .35 * self.ads_alpha
        flash.setScale(size, size * random.uniform(.85, 1.15), size)
        flash.show()

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

        self.stage_shots_fired += 1

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
            bs_stats = get_player_perk_stats(player, "bullet_storm")
            cd *= bs_stats.get("cooldown_mult", 0.65)  # 탄환 폭풍 퍽 활성화 시 연사 속도 극대화
        self.shoot_cooldown = cd
        self.recoil_timer = cfg["recoil_time"]
        self.weapon_recoil.kick(self.current_weapon, left=self.dual_hand_toggle == 1)
        if player and hasattr(player, 'add_weapon_recoil'):
            if self.current_weapon == "AR":
                # AR 조준사격 시 반동 소폭 강화 (안정적이고 쾌적한 수동 제어)
                strength = RECOIL_PROFILES["AR"][4] * (1.0 + 0.65 * self.ads_alpha)
                yaw_kick = random.uniform(-0.14, 0.14) * strength
            else:
                strength = RECOIL_PROFILES[self.current_weapon][4] * (1.0 - .35 * self.ads_alpha)
                yaw_kick = random.uniform(-.08, .08) * strength
            try:
                player.add_weapon_recoil(strength, yaw_kick, weapon=self.current_weapon, is_ads=(self.ads_alpha >= 0.5))
            except TypeError:
                player.add_weapon_recoil(strength, yaw_kick)
        self.muzzle_timer = 0.035 if self.current_weapon == "SHOTGUN" else 0.025

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
                self._show_muzzle_flash(self.muzzle_flash_geom, is_overcharge)
            if is_overcharge:
                self.muzzle_light.setColor((1.4, 4.0, 5.2, 1.0))
            else:
                self.muzzle_light.setColor((4.2, 2.8, 1.0, 1.0))
            self.render.setLight(self.muzzle_light_np)

            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if hasattr(self.audio_mgr, 'play_magnum_shot'):
                    self.audio_mgr.play_magnum_shot()
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
                    self._show_muzzle_flash(self.dual_left_flash_geom, is_overcharge)
                self.render.setLight(self.dual_left_flash_light_np)
                muzzle_world = self.dual_left_flash_geom.getPos(self.render) if (hasattr(self, 'dual_left_flash_geom') and not self.dual_left_flash_geom.isEmpty()) else (cam_pos + cam_fwd * 0.70 - cam_right * 0.16 - cam_up * 0.16)
            else:
                self.slide_timer_right = self.slide_blowback_duration
                self._eject_casing(is_left=False, is_shotgun=False)
                if hasattr(self, 'dual_right_flash_geom') and not self.dual_right_flash_geom.isEmpty():
                    self._show_muzzle_flash(self.dual_right_flash_geom, is_overcharge)
                self.render.setLight(self.dual_right_flash_light_np)
                muzzle_world = self.dual_right_flash_geom.getPos(self.render) if (hasattr(self, 'dual_right_flash_geom') and not self.dual_right_flash_geom.isEmpty()) else (cam_pos + cam_fwd * 0.70 + cam_right * 0.16 - cam_up * 0.16)

            self._spawn_barrel_smoke(offset_x=-0.14 if is_left else 0.14)
            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                self.audio_mgr.play_gunshot()

        elif self.current_weapon == "AR":
            self.recoil_timer = cfg["recoil_time"]
            self._eject_casing(is_left=False, is_shotgun=False)
            self._spawn_barrel_smoke(offset_y=0.45)

            if hasattr(self, 'ar_muzzle_flash_geom') and not self.ar_muzzle_flash_geom.isEmpty():
                self._show_muzzle_flash(self.ar_muzzle_flash_geom, is_overcharge)
            if is_overcharge:
                self.ar_muzzle_light.setColor((1.4, 3.8, 5.2, 1.0))
            else:
                self.ar_muzzle_light.setColor((3.8, 2.5, 0.8, 1.0))
            self.render.setLight(self.ar_muzzle_light_np)

            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if hasattr(self.audio_mgr, 'play_ar_shot'):
                    self.audio_mgr.play_ar_shot()
                else:
                    self.audio_mgr.play_gunshot()

            if hasattr(self, 'ar_muzzle_flash_geom') and not self.ar_muzzle_flash_geom.isEmpty():
                muzzle_world = self.ar_muzzle_flash_geom.getPos(self.render)
            else:
                muzzle_world = cam_pos + cam_fwd * 0.82 + cam_right * (0.18 * (1.0 - self.ads_alpha)) - cam_up * 0.16

        elif self.current_weapon == "SHOTGUN":
            self.sg_pump_timer = 0.44
            self.sg_pump_cycled = False
            self._spawn_barrel_smoke(offset_y=0.45)

            if hasattr(self, 'sg_muzzle_flash_geom') and not self.sg_muzzle_flash_geom.isEmpty():
                self._show_muzzle_flash(self.sg_muzzle_flash_geom, is_overcharge)
            if is_overcharge:
                self.sg_muzzle_light.setColor((1.5, 4.0, 5.5, 1.0))
            else:
                self.sg_muzzle_light.setColor((4.5, 2.8, 0.8, 1.0))
            self.render.setLight(self.sg_muzzle_light_np)

            if self.ammo <= 0:
                self.slide_locked = True
            if self.audio_mgr:
                if hasattr(self.audio_mgr, 'play_shotgun_blast'):
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
                base_spread *= 2.0 if self.current_weapon in ("PISTOL", "AR") else 2.2
            elif is_moving:
                base_spread *= 1.2 if self.current_weapon in ("PISTOL", "AR") else 1.5
            base_spread += getattr(self, 'hipfire_bloom', 0.0)

            # 무기별 블룸 증가량 차별화 (데저트 이글 단발 묵직함, AR 급격한 연사 탄퍼짐)
            if self.current_weapon == "PISTOL":
                bloom_add = 0.016
                max_bloom = 0.065
            elif self.current_weapon == "DUAL_PISTOL":
                bloom_add = 0.024
                max_bloom = 0.095
            elif self.current_weapon == "AR":
                bloom_add = 0.018
                max_bloom = 0.085
            else: # SHOTGUN
                bloom_add = 0.015
                max_bloom = 0.080
            self.hipfire_bloom = min(max_bloom, getattr(self, 'hipfire_bloom', 0.0) + bloom_add)

        if self.current_weapon == "AR":
            kick_bloom = 1.10 * (1.0 + 0.25 * self.ads_alpha)
            shake_mag = 0.036 * (1.0 + 0.35 * self.ads_alpha)
        elif self.current_weapon == "PISTOL":
            kick_bloom = 1.10
            shake_mag = 0.045
        elif self.current_weapon == "SHOTGUN":
            kick_bloom = 1.35
            shake_mag = 0.048
        else: # DUAL_PISTOL
            kick_bloom = 0.85
            shake_mag = 0.028
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
            self.stage_shots_hit += 1
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

            if "AR" in self.weapon_states:
                self.weapon_states["AR"]["max_ammo"] += 10
                self.weapon_states["AR"]["reserve_ammo"] += 60
                self.weapon_states["AR"]["ammo"] = self.weapon_states["AR"]["max_ammo"]

            cur_st = self.weapon_states[self.current_weapon]
            self.max_ammo = cur_st["max_ammo"]
            self.ammo = cur_st["ammo"]
            self._reserve_ammo = cur_st["reserve_ammo"]

            self.update_ammo_ui()
            self.ui_mgr.show_hit_marker("[특성 강화] 전 무기 최대 탄창 확장 및 전탄 즉시 보급!", (1.0, 0.85, 0.2, 1.0))

    def reload(self, game_state="PLAYING"):
        """R 키 입력 시 현재 무기 전술 재장전 (데저트 이글 / 듀얼 글록 / AR / 12게이지 샷건)"""
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
                self.audio_mgr.play_slide_release()
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

        self._reset_weapon_recoil()
        self.is_reloading = True
        base_reload_time = cfg.get("reload_time", 1.30)
        player = getattr(self.base, 'player', None)
        if player and hasattr(player, 'has_perk') and player.has_perk("speed_demon"):
            sd_stats = get_player_perk_stats(player, "speed_demon")
            base_reload_time *= sd_stats.get("reload_mult", 0.65)  # 스피드 데몬 퍽: 재장전 시간 가속
        self.reload_timer = base_reload_time
        self.was_slide_locked_before_reload = self.slide_locked

        self.sg_pump_timer = 0.0
        self.sg_pump_cycled = False
        if self.audio_mgr:
            playback_duration = base_reload_time / (1.35 if self.combo_count >= 2 else 1.0)
            self.audio_mgr.play_reload(self.current_weapon, duration=playback_duration)

        if self.current_weapon == "SHOTGUN":
            status_msg = "12게이지 벅샷 쉘 연속 삽탄 및 펌프 장전 중..."
        elif self.current_weapon == "DUAL_PISTOL":
            status_msg = "9mm 듀얼 글록 양손 탄창 동시 교체 중... (장전 지연 2.5s)"
        elif self.current_weapon == "AR":
            status_msg = f"5.56mm HK416 탄창 교체 및 노리쇠 전진 중... (장전 {base_reload_time:.1f}s)"
        else:
            status_msg = ".50 매그넘 대구경 탄창 교체 중..."
        self.ui_mgr.show_hit_marker(status_msg, (0.9, 0.9, 0.9, 1.0))
        self.hit_marker_timer = 1.4

    @property
    def reload_duration(self):
        """현재 무기의 기본 재장전 시간 (스피드 데몬 퍽 적용 반영)"""
        cfg = WEAPON_CONFIGS.get(self.current_weapon, {})
        base_time = cfg.get("reload_time", 1.30)
        player = getattr(self.base, 'player', None)
        if player and hasattr(player, 'has_perk') and player.has_perk("speed_demon"):
            sd_stats = get_player_perk_stats(player, "speed_demon")
            base_time *= sd_stats.get("reload_mult", 0.65)
        return base_time

    @reload_duration.setter
    def reload_duration(self, value):
        if self.is_reloading:
            self.reload_timer = min(self.reload_timer, value)

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
        self.stage_kills += 1
        self.combo_count += 1
        if self.combo_count > self.stage_max_combo:
            self.stage_max_combo = self.combo_count
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
        self._reset_weapon_recoil()
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
        if self.audio_mgr:
            self.audio_mgr.stop_weapon_actions()

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

        # AR 노드 복구
        if hasattr(self, 'ar_recoil_node') and self.ar_recoil_node and not self.ar_recoil_node.isEmpty():
            self.ar_recoil_node.setPos(0, 0, 0)
            self.ar_recoil_node.setP(0)
            self.ar_recoil_node.setR(0)
        if hasattr(self, 'ar_mag_node') and self.ar_mag_node and not self.ar_mag_node.isEmpty():
            self.ar_mag_node.setPos(0, 0.12, -0.06)
            self.ar_mag_node.setScale(1.0)
        if hasattr(self, 'vm_ar') and self.vm_ar and not self.vm_ar.isEmpty():
            self.vm_ar.setPos(self.ads_hip_pos_ar)
            self.vm_ar.setHpr(Vec3(1.2, 0.6, -0.6))

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
        if hasattr(self, 'ar_muzzle_flash_geom') and self.ar_muzzle_flash_geom and not self.ar_muzzle_flash_geom.isEmpty():
            self.ar_muzzle_flash_geom.hide()
            if hasattr(self, 'ar_muzzle_light_np') and self.ar_muzzle_light_np and not self.ar_muzzle_light_np.isEmpty():
                self.render.clearLight(self.ar_muzzle_light_np)
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
        self.casing_effects.clear()
        for s in getattr(self, 'smoke_pool', []):
            s["active"] = False
            s["node"].hide()

        self.setup_ammo_drops(current_stage)
        self.update_ammo_ui()

        # 스테이지 전투 통계 초기화
        self.stage_kills = 0
        self.stage_headshots = 0
        self.stage_shots_fired = 0
        self.stage_shots_hit = 0
        self.stage_damage_dealt = 0.0
        self.stage_damage_taken = 0.0
        self.stage_max_combo = 0
        try:
            from panda3d.core import ClockObject
            self.stage_start_time = ClockObject.getGlobalClock().getFrameTime()
        except Exception:
            self.stage_start_time = time.time()

    def record_combat_hit(self, dmg, is_headshot=False):
        """탄환 적중 시 피해량 및 헤드샷 카운트 누적"""
        self.stage_damage_dealt = getattr(self, 'stage_damage_dealt', 0.0) + float(dmg)
        if is_headshot:
            self.stage_headshots = getattr(self, 'stage_headshots', 0) + 1

    def get_stage_stats(self):
        """현재 스테이지 종합 전투 결과 통계 반환 (After-Action Report용)"""
        try:
            from panda3d.core import ClockObject
            now = ClockObject.getGlobalClock().getFrameTime()
        except Exception:
            now = time.time()
        start = getattr(self, 'stage_start_time', 0.0)
        elapsed = max(1.0, now - start) if start > 0.0 else 0.0
        shots_f = max(1, self.stage_shots_fired)
        accuracy = min(100.0, (self.stage_shots_hit / shots_f) * 100.0) if self.stage_shots_fired > 0 else 0.0
        shots_h = max(1, self.stage_shots_hit)
        headshot_pct = min(100.0, (self.stage_headshots / shots_h) * 100.0) if self.stage_shots_hit > 0 else 0.0
        return {
            "kills": self.stage_kills,
            "headshots": self.stage_headshots,
            "shots_fired": self.stage_shots_fired,
            "shots_hit": self.stage_shots_hit,
            "accuracy": accuracy,
            "headshot_ratio": headshot_pct,
            "damage_dealt": self.stage_damage_dealt,
            "damage_taken": self.stage_damage_taken,
            "max_combo": self.stage_max_combo,
            "clear_time": elapsed,
        }

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

    def _update_shotgun_pump(self, dt):
        """Keep recorded action and ejection in sync, including skipped frames."""
        if not getattr(self, "sg_pump_node", None) or self.sg_pump_node.isEmpty():
            return
        if self.sg_pump_timer <= 0.0:
            self.sg_pump_node.setPos(0, 0.28, -0.010)
            return
        total = WEAPON_CONFIGS["SHOTGUN"]["pump_time"]
        previous_elapsed = total - self.sg_pump_timer
        self.sg_pump_timer = max(0.0, self.sg_pump_timer - dt)
        elapsed = total - self.sg_pump_timer
        # The recording's rear/forward impacts occur at ~0.09/~0.38 s.
        if previous_elapsed < 0.04 <= elapsed and self.audio_mgr:
            self.audio_mgr.play_shotgun_pump()
        progress = elapsed / total
        if progress >= 0.35 and not self.sg_pump_cycled:
            self.sg_pump_cycled = True
            self._eject_casing(is_left=False, is_shotgun=True)
        offset = -0.09 * (progress / 0.5 if progress < 0.5 else (1.0 - progress) / 0.5)
        self.sg_pump_node.setPos(0, 0.28 + offset, -0.010)

    def update(self, dt, px=0.0, py=0.0, is_moving=False, is_sprinting=False):
        """프레임별 트레이서, 탄피 물리, 화약 연기, 슬라이드 블로우백, 펌프액션, 반동/재장전, 밥빙, 탄약 습득 갱신"""
        self.is_moving = is_moving
        self.is_sprinting = is_sprinting

        # 풀오토 연사 지원 (AR 전용: 좌클릭 유지 시 연속 격발 / 권총 및 아킴보는 단발 클릭 격발)
        if hasattr(self.base, 'mouseWatcherNode') and self.base.mouseWatcherNode and self.base.mouseWatcherNode.isButtonDown(MouseButton.one()):
            if self.current_weapon == "AR" and self.shoot_cooldown <= 0.0 and not self.is_reloading:
                game_inst = getattr(self.base, 'game', None) or self.base
                monsters = getattr(game_inst, 'monsters', [])
                player = getattr(game_inst, 'player', None)
                hazard_barrels = getattr(game_inst, 'hazard_barrels', None)
                self.shoot(monsters, player=player, game_state="PLAYING", hazard_barrels=hazard_barrels)

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
                    # 지오메트리 파괴 및 재생성 없이 노드 컬러 스케일만 즉시 감쇠 (드로우콜 및 메모리 스파이크 방지)
                    for key in ("core", "glow", "halo"):
                        node = tr.get(key)
                        if node and not node.isEmpty():
                            node.setColorScale(1.0, 1.0, 1.0, fade_alpha)

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
                if hasattr(self, 'ar_muzzle_flash_geom') and not self.ar_muzzle_flash_geom.isEmpty():
                    self.ar_muzzle_flash_geom.hide()
                    self.render.clearLight(self.ar_muzzle_light_np)
                if hasattr(self, 'sg_muzzle_flash_geom') and not self.sg_muzzle_flash_geom.isEmpty():
                    self.sg_muzzle_flash_geom.hide()
                    self.render.clearLight(self.sg_muzzle_light_np)

        # 3. 3D 탄피 물리 풀 갱신 (중력, 궤적, 지면 튕김, 회전)
        self.casing_effects.update(dt)

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
        self._update_shotgun_pump(dt)

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

            elif self.current_weapon == "AR":
                # 돌격소총: 탄창 분리(하단 낙하) -> 신규 탄창 삽입 -> 상단 노리쇠/장전손잡이 전진
                if p < 0.35:
                    sub_p = p / 0.35
                    if hasattr(self, 'ar_recoil_node') and not self.ar_recoil_node.isEmpty():
                        self.ar_recoil_node.setR(-14.0 * math.sin(sub_p * math.pi * 0.5))
                        self.ar_recoil_node.setP(-12.0 * math.sin(sub_p * math.pi * 0.5))
                    if hasattr(self, 'ar_mag_node') and not self.ar_mag_node.isEmpty():
                        drop_z = sub_p * 0.35
                        self.ar_mag_node.setPos(0, 0.12 - drop_z * 0.20, -0.06 - drop_z)
                        self.ar_mag_node.setScale(max(0.05, 1.0 - sub_p * 0.8))
                elif p < 0.78:
                    sub_p = (p - 0.35) / 0.43
                    if hasattr(self, 'ar_recoil_node') and not self.ar_recoil_node.isEmpty():
                        self.ar_recoil_node.setR(-14.0 * (1.0 - sub_p * 0.3))
                        self.ar_recoil_node.setP(-12.0 * (1.0 - sub_p * 0.3))
                    if hasattr(self, 'ar_mag_node') and not self.ar_mag_node.isEmpty():
                        rise_z = (1.0 - min(1.0, sub_p * 1.1)) * 0.32
                        self.ar_mag_node.setScale(1.0)
                        self.ar_mag_node.setPos(0, 0.12 - rise_z * 0.20, -0.06 - rise_z)
                else:
                    sub_p = (p - 0.78) / 0.22
                    if hasattr(self, 'ar_mag_node') and not self.ar_mag_node.isEmpty():
                        self.ar_mag_node.setPos(0, 0.12, -0.06)
                        self.ar_mag_node.setScale(1.0)
                    if hasattr(self, 'ar_recoil_node') and not self.ar_recoil_node.isEmpty():
                        self.ar_recoil_node.setR(-14.0 * 0.7 * (1.0 - sub_p))
                        self.ar_recoil_node.setP(-12.0 * 0.7 * (1.0 - sub_p))

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
                if hasattr(self, 'ar_recoil_node') and not self.ar_recoil_node.isEmpty():
                    self.ar_recoil_node.setPos(0, 0, 0)
                    self.ar_recoil_node.setP(0)
                    self.ar_recoil_node.setR(0)
                if hasattr(self, 'ar_mag_node') and not self.ar_mag_node.isEmpty():
                    self.ar_mag_node.setPos(0, 0.12, -0.06)
                    self.ar_mag_node.setScale(1.0)
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
        else:
            self.recoil_timer = max(0.0, self.recoil_timer - dt)
            for name, (back, lift, pitch, roll) in self.weapon_recoil.update(dt, self.ads_alpha).items():
                node = getattr(self, name, None)
                if node is not None and not node.isEmpty():
                    node.setPos(0, back, lift)
                    node.setHpr(0, pitch, roll)

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

        # (1) 데저트 이글 ADS
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

        # (3) 5.56mm AR ADS (가늠자 홈과 가늠쇠 끝을 화면 중앙에 정렬)
        if hasattr(self, 'vm_ar') and self.vm_ar and not self.vm_ar.isEmpty():
            cur_pos_ar = self.ads_hip_pos_ar * (1.0 - self.ads_alpha) + self.ads_aim_pos_ar * self.ads_alpha
            cur_hpr_ar = Vec3(1.2, 0.6, -0.6) * (1.0 - self.ads_alpha)
            self.vm_ar.setPos(cur_pos_ar)
            self.vm_ar.setHpr(cur_hpr_ar)

        # (4) 12게이지 샷건 ADS (총열 상단 리브와 빨간 광섬유 가늠쇠 정렬)
        if hasattr(self, 'vm_shotgun') and self.vm_shotgun and not self.vm_shotgun.isEmpty():
            cur_pos_sg = self.ads_hip_pos_sg * (1.0 - self.ads_alpha) + self.ads_aim_pos_sg * self.ads_alpha
            cur_hpr_sg = Vec3(1.0, 0.5, -0.5) * (1.0 - self.ads_alpha)
            self.vm_shotgun.setPos(cur_pos_sg)
            self.vm_shotgun.setHpr(cur_hpr_sg)

        # 카메라 FOV 줌 (사용자 기본 FOV -> 정밀조준 시 기본 FOV * (80 / 96)로 자연스럽게 확대) + 불릿타임 시 광각 시간왜곡 워프 (+6.5도)
        if hasattr(self.base, 'camLens') and self.base.camLens:
            game_inst = getattr(self.base, 'game', None) or self.base
            base_fov = getattr(self.base, 'base_fov', getattr(game_inst, 'base_fov', 96.0))
            ads_fov = base_fov * (80.0 / 96.0)
            cur_fov = base_fov * (1.0 - self.ads_alpha) + ads_fov * self.ads_alpha
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
