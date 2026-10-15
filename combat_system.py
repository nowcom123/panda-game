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
from collision import get_nearby_colliders, raycast_walls


class CombatSystem:
    def __init__(self, base, render, camera, world_root, audio_mgr, ui_mgr):
        self.base = base
        self.render = render
        self.camera = camera
        self.world_root = world_root
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 탄약 및 사격 상태
        self.max_ammo = 12
        self.ammo = self.max_ammo
        self.reserve_ammo = 36  # 초기 예비 탄약 36발 (몬스터 체력 증가 대응)
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0

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

        # 정밀 조준(ADS: Aim Down Sights) 상태
        self.is_aiming = False
        self.ads_alpha = 0.0
        # 총기가 화면 하단에 파묻히지 않고 또렷하게 보이도록 위치/높이 최적화 (양손 파지 및 웨폰라이트 일체형)
        self.ads_hip_pos = Vec3(0.18, 0.56, -0.165)
        self.ads_aim_pos = Vec3(0.00, 0.46, -0.118)
        self.ads_hip_hpr = Vec3(2.0, 1.0, -1.0)
        self.ads_aim_hpr = Vec3(0.0, 0.0, 0.0)

        # 지향사격(Hip-fire) 탄퍼짐 및 크로스헤어 흔들림 상태
        self.hipfire_bloom = 0.0
        self.is_moving = False
        self.is_sprinting = False

        # 뷰모델 지오메트리 구축
        self._setup_viewmodel()

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
        """1인칭 택티컬 뷰모델: 권총 하부 언더레일에 직결 장착된 택티컬 웨폰라이트(WML) 및 정밀 12발 권총"""
        if hasattr(self, 'vm_root') and self.vm_root:
            self.vm_root.removeNode()

        self.vm_root = self.camera.attachNewNode("viewmodel_root")

        # --- (A) 현실적 기계 구조 12발 권총 ---
        self.vm_pistol = self.vm_root.attachNewNode("vm_pistol")
        self.vm_pistol.setPos(self.ads_hip_pos)
        self.vm_pistol.setHpr(self.ads_hip_hpr)

        self.recoil_node = self.vm_pistol.attachNewNode("recoil_node")

        steel_dark = LColor(0.10, 0.10, 0.12, 1.0)
        steel_slide = LColor(0.22, 0.23, 0.26, 1.0)
        steel_barrel = LColor(0.16, 0.16, 0.18, 1.0)
        grip_col = LColor(0.06, 0.06, 0.07, 1.0)
        tritium_green = LColor(0.35, 1.0, 0.40, 1.0)

        # 1. 하부 프레임 (Frame) - 고정부 (리시버, 그립, 방아쇠, 슬라이드 멈치, 탄창 멈치)
        self.frame_node = self.recoil_node.attachNewNode("frame_node")
        grip = make_cube_to(self.frame_node, 0.058, 0.11, 0.20, grip_col, 0, -0.06, -0.09)
        grip.setP(16)
        # 하부 더스트커버 및 피카티니 레일
        make_cube_to(self.frame_node, 0.055, 0.20, 0.050, steel_dark, 0, 0.08, 0.005)
        # 방아쇠울 및 방아쇠
        make_cube_to(self.frame_node, 0.030, 0.08, 0.060, steel_dark, 0, 0.04, -0.04)
        make_cube_to(self.frame_node, 0.014, 0.02, 0.035, steel_dark, 0, 0.035, -0.025)
        # 좌측 슬라이드 스톱 레버 (Slide Catch Lever)
        make_cube_to(self.frame_node, 0.010, 0.035, 0.012, steel_dark, -0.032, 0.02, 0.045)
        # 좌측 탄창 분리 버튼 (Magazine Release)
        make_cube_to(self.frame_node, 0.012, 0.015, 0.015, steel_dark, -0.032, -0.03, -0.02)

        # --- (B) 권총 하부 언더레일 장착 택티컬 웨폰라이트 (Weapon-Mounted Light) ---
        # 권총 하부 피카티니 레일 체결 위치 (총열 아래, 방아쇠울 바로 앞)
        self.vm_flashlight = self.frame_node.attachNewNode("vm_flashlight")
        self.vm_flashlight.setPos(0, 0.13, -0.034)

        wml_clamp_col = LColor(0.20, 0.21, 0.24, 1.0)
        wml_body_col = LColor(0.12, 0.12, 0.14, 1.0)
        wml_bezel_col = LColor(0.26, 0.27, 0.30, 1.0)

        # 피카티니 레일 결합 클램프 및 잠금 스크루
        make_cube_to(self.vm_flashlight, 0.060, 0.14, 0.020, wml_clamp_col, 0, -0.012, 0.022)
        make_cube_to(self.vm_flashlight, 0.012, 0.026, 0.022, steel_slide, -0.033, -0.012, 0.022)

        # 웨폰라이트 메인 바디 하우징 (아노다이징 건메탈 알루미늄 본체)
        make_cube_to(self.vm_flashlight, 0.052, 0.16, 0.044, wml_body_col, 0, 0.0, 0.0)

        # 전방 프로젝터 베젤 헤드
        make_cube_to(self.vm_flashlight, 0.056, 0.028, 0.048, wml_bezel_col, 0, 0.092, 0.0)

        # 전방 고출력 발광 렌즈 (High-Output LED Projector Lens)
        lens = make_cube_to(self.vm_flashlight, 0.046, 0.008, 0.042, LColor(1.0, 0.96, 0.82, 0.95), 0, 0.108, 0.0)
        lens.setLightOff()

        # 후방 양손잡이 토글 스위치 (방아쇠울 전면 엄지 조작부)
        make_cube_to(self.vm_flashlight, 0.040, 0.020, 0.028, steel_dark, 0, -0.092, -0.006)

        # 손전등 전방 Spotlight (권총 총구/가늠쇠 지향선과 100% 일치)
        spotlight = Spotlight('player_flashlight')
        spotlight.setColor((2.85, 2.70, 2.35, 1.0))
        spot_lens = PerspectiveLens()
        spot_lens.setFov(50.0)
        spot_lens.setNearFar(0.15, 70.0)
        spotlight.setLens(spot_lens)
        spotlight.setAttenuation((1.0, 0.015, 0.0006))
        spotlight.setExponent(50.0)
        self.pl_np = self.vm_flashlight.attachNewNode(spotlight)
        self.pl_np.setPos(0, 0.12, 0.0)
        self.render.setLight(self.pl_np)

        # 근거리 보조 조명 (권총 및 시야각 은은한 반사광)
        fill_light = PointLight('player_fill')
        fill_light.setColor((0.18, 0.16, 0.14, 1.0))
        fill_light.setAttenuation((1.0, 0.30, 0.08))
        self.fill_np = self.vm_flashlight.attachNewNode(fill_light)
        self.fill_np.setPos(0, 0.05, 0.0)
        self.render.setLight(self.fill_np)

        # 2. 총열 및 약실 (Barrel & Chamber Hood) - 슬라이드 후퇴 시 내부 노출
        self.barrel_node = self.recoil_node.attachNewNode("barrel_node")
        # 메인 강선 총열
        make_cube_to(self.barrel_node, 0.042, 0.16, 0.042, steel_barrel, 0, 0.18, 0.04)
        # 총구 크라운 보어 홀
        make_cube_to(self.barrel_node, 0.028, 0.015, 0.028, LColor(0.02, 0.02, 0.02, 1.0), 0, 0.265, 0.04)
        # 사각 약실 후드 (Chamber Block) - 슬라이드 후퇴 시 탄피 배출구 사이로 적나라하게 노출
        make_cube_to(self.barrel_node, 0.048, 0.07, 0.046, steel_dark, 0, 0.04, 0.042)

        # 3. 왕복 슬라이드 (Reciprocating Slide) - 격발 시 -Y축으로 후퇴 후 복좌 (또는 탄 소진 시 고정)
        self.slide_node = self.recoil_node.attachNewNode("slide_node")
        # 슬라이드 전방/후방 바디
        make_cube_to(self.slide_node, 0.062, 0.30, 0.075, steel_slide, 0, 0.05, 0.045)
        # 우측 탄피 배출구 홈 (Ejection Port Cutout)
        make_cube_to(self.slide_node, 0.020, 0.07, 0.035, steel_dark, 0.026, 0.04, 0.055)
        # 후방 코킹 서레이션 (미끄럼 방지 홈)
        make_cube_to(self.slide_node, 0.064, 0.05, 0.055, steel_dark, 0, -0.05, 0.045)

        # 트리튬 야광 가늠쇠/가늠자 (슬라이드와 함께 움직임)
        front_sight = make_cube_to(self.slide_node, 0.012, 0.02, 0.02, tritium_green, 0, 0.19, 0.09)
        front_sight.setLightOff()
        r_sight1 = make_cube_to(self.slide_node, 0.012, 0.015, 0.02, tritium_green, -0.022, -0.09, 0.09)
        r_sight2 = make_cube_to(self.slide_node, 0.012, 0.015, 0.02, tritium_green, 0.022, -0.09, 0.09)
        r_sight1.setLightOff()
        r_sight2.setLightOff()

        # 4. 외부 해머 (Hammer / 공이치기) - 격발 및 슬라이드 후퇴 시 피벗 회전
        self.hammer_node = self.recoil_node.attachNewNode("hammer_node")
        self.hammer_node.setPos(0, -0.102, 0.038)
        self.hammer_node.setP(-42)  # 기본 코킹 완료 상태
        make_cube_to(self.hammer_node, 0.016, 0.030, 0.045, steel_dark, 0, -0.012, 0.018)

        # 5. 분리형 탄창 (Detachable Box Magazine)
        self.mag_node = self.frame_node.attachNewNode("mag_node")
        self.mag_node.setPos(0, -0.06, -0.09)
        self.mag_node.setP(16)
        # 탄창 스틸 바디
        make_cube_to(self.mag_node, 0.046, 0.082, 0.18, steel_dark, 0, 0, 0)
        # 탄창 범퍼 패드 (Baseplate)
        make_cube_to(self.mag_node, 0.056, 0.096, 0.024, grip_col, 0, -0.005, -0.095)
        # 최상단 장전 황동 실탄 (Brass Top Round)
        make_cube_to(self.mag_node, 0.024, 0.048, 0.024, LColor(0.85, 0.68, 0.22, 1.0), 0, 0.01, 0.08)

        # 6. 총구 화염 지오메트리 & 조명
        self.muzzle_flash_geom = make_cube_to(self.recoil_node, 0.16, 0.22, 0.16, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.34, 0.04, rot_h=45)
        self.muzzle_flash_geom.setLightOff()
        self.muzzle_flash_geom.hide()

        self.muzzle_light = PointLight('muzzle_light')
        self.muzzle_light.setColor((2.8, 2.2, 0.9, 1.0))
        self.muzzle_light.setAttenuation((1.0, 0.08, 0.015))
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)
        self.muzzle_light_np.setPos(0, 0.35, 0.04)

    def _eject_casing(self):
        """격발 시 우측 탄피 배출구에서 3D 황동 탄피가 회전하며 튀어나오는 물리 효과"""
        cam_quat = self.camera.getQuat()
        cam_right = cam_quat.getRight()
        cam_fwd = cam_quat.getForward()
        cam_up = cam_quat.getUp()

        if hasattr(self, 'slide_node') and self.slide_node and not self.slide_node.isEmpty():
            eject_pos = self.slide_node.getPos(self.render) + cam_right * 0.04 + cam_up * 0.02
        else:
            eject_pos = self.camera.getPos() + cam_fwd * 0.65 + cam_right * (0.22 * (1.0 - self.ads_alpha) + 0.04) - cam_up * 0.16

        c_node = self.world_root.attachNewNode("spent_casing")
        c_node.setPos(eject_pos)
        brass_col = LColor(0.92, 0.76, 0.24, 1.0)
        c_cube = make_cube_to(c_node, 0.016, 0.044, 0.016, brass_col, 0, 0, 0)
        c_cube.setLightOff()

        v_right = random.uniform(2.4, 3.6)
        v_up = random.uniform(1.8, 2.8)
        v_fwd = random.uniform(-0.8, -0.3)
        initial_vel = cam_right * v_right + cam_up * v_up + cam_fwd * v_fwd

        spin = Vec3(
            random.uniform(600, 1400),
            random.uniform(400, 1000),
            random.uniform(300, 800)
        )

        self.active_casings.append({
            "node": c_node,
            "pos": Vec3(eject_pos),
            "vel": initial_vel,
            "rot": Vec3(random.uniform(0, 360), random.uniform(0, 360), 0),
            "spin": spin,
            "life": 1.4
        })

        if len(self.active_casings) > 25:
            oldest = self.active_casings.pop(0)
            if not oldest["node"].isEmpty():
                oldest["node"].removeNode()

    def _spawn_barrel_smoke(self):
        """격발 직후 총구 및 약실에서 피어오르는 반투명 화약 가스 연기"""
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()

        if hasattr(self, 'muzzle_flash_geom') and self.muzzle_flash_geom and not self.muzzle_flash_geom.isEmpty():
            muzzle_pos = self.muzzle_flash_geom.getPos(self.render)
        else:
            muzzle_pos = self.camera.getPos() + cam_fwd * 0.80 + cam_right * (0.22 * (1.0 - self.ads_alpha)) - cam_up * 0.16

        smoke_col = LColor(0.75, 0.75, 0.78, 0.35)

        for _ in range(2):
            s_node = self.world_root.attachNewNode("barrel_smoke")
            s_node.setPos(muzzle_pos + Vec3(random.uniform(-0.02, 0.02), random.uniform(-0.02, 0.02), random.uniform(-0.02, 0.02)))
            cube = make_cube_to(s_node, 0.045, 0.045, 0.045, smoke_col, 0, 0, 0)
            cube.setLightOff()

            vel = cam_fwd * random.uniform(0.6, 1.4) + cam_up * random.uniform(0.2, 0.5) + cam_right * random.uniform(-0.1, 0.1)
            self.smoke_particles.append({
                "node": s_node,
                "cube": cube,
                "pos": Vec3(s_node.getPos()),
                "vel": vel,
                "scale": 0.045,
                "timer": 0.55,
                "max_timer": 0.55
            })

        if len(self.smoke_particles) > 20:
            oldest = self.smoke_particles.pop(0)
            if not oldest["node"].isEmpty():
                oldest["node"].removeNode()

    def shoot(self, monsters, player=None, game_state="PLAYING", hazard_barrels=None):
        """권총 사격 및 다중 몬스터 대상 레이캐스트 적중 판정 (벽체 엄폐 판정 및 폭발 드럼통 포함)"""
        if game_state != "PLAYING" or self.is_reloading or self.shoot_cooldown > 0.0:
            return

        if self.slide_locked or self.ammo <= 0:
            if self.audio_mgr:
                self.audio_mgr.play_empty_click()
            if self.reserve_ammo > 0:
                self.ui_mgr.show_hit_marker("슬라이드 후퇴 고정! [R] 키로 재장전하세요!", (1.0, 0.4, 0.4, 1.0))
            else:
                self.ui_mgr.show_hit_marker("탄약 소진! (맵에서 탄약 상자를 찾으세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            self.shoot_cooldown = 0.35
            return

        # 콤보 상태에 따른 탄약 절약 확률 (콤보 4 이상 시 30% 확률로 탄약 미소모)
        free_ammo = (self.combo_count >= 4 and random.random() < 0.30)
        if not free_ammo:
            self.ammo -= 1

        # 콤보 상태에 따른 연사 속도 가속 (기본 0.20s -> 콤보 2 이상 시 0.14s)
        self.shoot_cooldown = 0.14 if self.combo_count >= 2 else 0.20
        self.recoil_timer = 0.10
        self.muzzle_timer = 0.04

        # 1. 슬라이드 블로우백 및 공이치기 격발
        self.slide_timer = self.slide_blowback_duration
        self.hammer_timer = 0.04
        self.hammer_node.setP(0)

        # 2. 3D 황동 탄피 배출 및 총구 화약 가스 연기
        self._eject_casing()
        self._spawn_barrel_smoke()

        # 3. 다이내믹 총구 화염 및 조명
        self.muzzle_flash_geom.setR(random.uniform(0, 360))
        self.muzzle_flash_geom.setScale(random.uniform(0.9, 1.3))
        self.muzzle_flash_geom.show()
        self.render.setLight(self.muzzle_light_np)

        # 4. 마지막 탄약 격발 시 슬라이드 스톱 고정 (Slide Lock on Empty Chamber)
        if self.ammo <= 0:
            self.slide_locked = True
        if self.audio_mgr:
            self.audio_mgr.play_gunshot()
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

        # 지향사격(Hip-fire) vs 우클릭 정밀조준(ADS) 명중률 및 탄퍼짐(Spread) 산출
        # 우클릭 정밀조준(ADS) 시: 100% 핀포인트 정밀 레이저 명중률 (spread = 0.0)
        # 일반 지향사격(Hip-fire) 시: 크로스헤어 팽창 및 급격한 흔들림(Jitter Shake)과 함께 거리/이동에 따른 탄퍼짐 발생
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()

        is_moving = getattr(player, 'is_moving', False) or getattr(self, 'is_moving', False)
        is_sprinting = getattr(player, 'is_sprinting', False) or getattr(self, 'is_sprinting', False)
        is_sliding = getattr(player, 'is_sliding', False)

        if self.ads_alpha >= 0.85:
            # 우클릭 정밀조준(ADS): 핀포인트 레이저 사격
            spread = 0.0
            ray_dir = cam_fwd
        else:
            # 일반 지향사격: 조준 상태 및 이동 속도에 따른 탄퍼짐 각도 계산
            hip_factor = 1.0 - self.ads_alpha
            base_spread = 0.040  # 정지 상태 기본 탄퍼짐 (~2.3도 각도 편차)
            if is_sprinting or is_sliding:
                base_spread *= 2.40  # 전력질주 / 슬라이딩 중 (~5.5도)
            elif is_moving:
                base_spread *= 1.65  # 보행 이동 중 (~3.8도)

            # 연속 격발 시 탄퍼짐 누적 패널티
            base_spread += getattr(self, 'hipfire_bloom', 0.0)
            self.hipfire_bloom = min(0.080, getattr(self, 'hipfire_bloom', 0.0) + 0.022)

            spread = base_spread * hip_factor

            # 원형 디스크 탄퍼짐 편차 벡터 산출
            ang = random.uniform(0.0, 2.0 * math.pi)
            rad = (random.uniform(0.0, 1.0) ** 0.5) * spread
            def_x = math.cos(ang) * rad
            def_y = math.sin(ang) * rad

            ray_dir = (cam_fwd + cam_right * def_x + cam_up * def_y).normalized()

            # 크로스헤어 격발 팽창 및 고주파 전술 흔들림(Jitter Shake) 발동!
            if hasattr(self.ui_mgr, 'trigger_hipfire_kick'):
                self.ui_mgr.trigger_hipfire_kick(kick_bloom=0.72, shake_mag=0.024, shake_dur=0.18)
            elif hasattr(self.ui_mgr, 'crosshair') and hasattr(self.ui_mgr.crosshair, 'trigger_hipfire_kick'):
                self.ui_mgr.crosshair.trigger_hipfire_kick(kick_bloom=0.72, shake_mag=0.024, shake_dur=0.18)

        # 1. 벽체 충돌 레이캐스트 (벽 관통 사격 원천 차단)
        ray_origin = self.camera.getPos()
        chunks = getattr(self.base, 'chunks', {})
        wall_dist, wall_hit_pos = raycast_walls(chunks, ray_origin, ray_dir, max_dist=55.0)

        # 2. 다중 몬스터 및 유류 드럼통 대상 레이캐스트 히트스캔
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

        if closest_barrel is not None:
            # 폭발성 유류 드럼통 피격 -> 점화 카운트다운
            tracer_dist = min_hit_dist
            impact_world = ray_origin + ray_dir * tracer_dist
            self.ui_mgr.trigger_crosshair_hit(is_kill=True, is_crit=True)
            self.spawn_hit_particles(impact_world, is_blood=False)
            closest_barrel.ignite()

        elif closest_monster is not None:
            # 몬스터 타격
            tracer_dist = min_hit_dist
            impact_world = ray_origin + ray_dir * tracer_dist

            blackout_active = getattr(self.base, 'blackout_active', False)
            if player and hasattr(player, 'get_attack_power'):
                dmg = player.get_attack_power(blackout_active=blackout_active)
            else:
                dmg = getattr(player, 'attack_power', 35.0) if player else 35.0

            # 1. 슬라이드 샷(Slide Shot) 또는 헤드샷 치명타(Critical Hit) 판정
            is_sliding = bool(player and getattr(player, 'is_sliding', False))
            is_headshot = bool(getattr(closest_monster, 'last_hit_was_head', False))
            is_crit = is_headshot or is_sliding

            if is_crit:
                dmg *= 2.0 if is_headshot else 1.85

            # 넉백/경직 확률 판정: 일반 타격 28%, 크리티컬/슬라이드 샷 85%
            knockback_chance = 0.85 if is_crit else 0.28
            has_knockback = (random.random() < knockback_chance)

            # 피격 전 체력 기록 (처형 판정용)
            prev_m_hp = getattr(closest_monster, 'hp', 1)
            prev_max_hp = getattr(closest_monster, 'max_hp', 100)

            is_dead = closest_monster.take_damage(dmg, apply_knockback=has_knockback, hit_dir=ray_dir)
            m_name = getattr(closest_monster, 'name', '괴물')

            # 몬스터 피격 효과: 크로스헤어 피격 마커 & 3D 핏빛 파티클 분출
            self.ui_mgr.trigger_crosshair_hit(is_kill=is_dead, is_crit=is_crit)
            self.spawn_hit_particles(impact_world, is_blood=True)

            # 적 히트 시 스테미나 충전 (일반 적중 +12, 헤드샷/슬라이드샷 치명타 +24, 처치 추가 +16)
            if player and hasattr(player, 'recover_stamina'):
                stamina_gain = 24.0 if is_crit else 12.0
                if is_dead:
                    stamina_gain += 16.0
                player.recover_stamina(stamina_gain)

            if is_crit and self.audio_mgr:
                self.audio_mgr.play_crit_hit()

            if is_dead:
                # 콤보 스트릭 등록
                self.register_kill(player=player)

                # 처형(Execution) 판정: 낮은 체력 마무리, 치명타, 또는 5.5m 근접 마무리
                is_execution = (prev_m_hp <= prev_max_hp * 0.35) or is_crit or (min_hit_dist <= 5.5)
                if is_execution:
                    self.ammo = min(self.max_ammo, self.ammo + 2)
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)
                    if player and hasattr(player, 'recover_stamina'):
                        player.recover_stamina(60.0)
                    self.ui_mgr.show_hit_marker("! [처형!] 권총 탄약 +2발 환급 & 기력 충전 !", (0.35, 1.0, 0.65, 0.95))

                exp_gain = getattr(closest_monster, 'exp_value', 35)

                # 슬라이딩 킬 스타일 보너스 (추가 경험치)
                if is_sliding:
                    exp_gain += 75

                # 콤보 배수 보너스 경험치
                if self.combo_count >= 2:
                    exp_gain = int(exp_gain * (1.0 + 0.25 * min(self.combo_count, 6)))

                # 정전 중 처치 시 경험치 2배 & 비상 탄약 보급 (+6발)
                if blackout_active:
                    exp_gain *= 2
                    self.reserve_ammo += 6
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

                # 피의 갈증 유물: 적 처치 시 체력 12 즉시 흡혈
                if player and hasattr(player, 'relics') and "blood_thirst" in player.relics:
                    player.heal(12.0)

                if hasattr(closest_monster, 'turn_into_corpse'):
                    closest_monster.turn_into_corpse(audio_mgr=self.audio_mgr)
                if player:
                    player.gain_exp(exp_gain)
                    # 몬스터 처치 시 전술 전리품 보급품 드랍 (35% 확률로 응급키트/아드레날린/탄약팩/수류탄 획득)
                    if hasattr(player, 'add_item') and random.random() < 0.35:
                        drop_id = random.choice(["medkit", "adrenaline", "ammo_pack", "frag_grenade", "combat_stim"])
                        ok, item_name = player.add_item(drop_id, 1)
                        if ok:
                            self.ui_mgr.show_hit_marker(f"+ {item_name} 획득", (0.35, 1.0, 0.65, 0.9))
                            if hasattr(self.base, '_update_quickslot_hud'):
                                self.base._update_quickslot_hud()
            else:
                # 타격 텍스트 알림 제거 — 크로스헤어 히트마커(시각적)만 사용
                pass

            if self.audio_mgr:
                if "뱀" in m_name:
                    self.audio_mgr.play_serpent_hit()
                elif "해골" in m_name:
                    self.audio_mgr.play_skeleton_hit()
                elif "오크" in m_name:
                    self.audio_mgr.play_gunshot()
                else:
                    self.audio_mgr.play_serpent_hit()

        elif wall_hit_pos is not None:
            # 벽체 피격 (콘크리트 스파크 분출)
            tracer_dist = wall_dist
            impact_world = wall_hit_pos
            self.spawn_hit_particles(impact_world, is_blood=False)
        else:
            # 허공 사격 (최대 사거리 55m)
            tracer_dist = 55.0
            impact_world = ray_origin + ray_dir * tracer_dist

        # 실감나는 고시인성 비행 총알 궤적 (High-Visibility Kinetic Bullet Tracer)
        if hasattr(self, 'muzzle_flash_geom') and self.muzzle_flash_geom and not self.muzzle_flash_geom.isEmpty():
            muzzle_world = self.muzzle_flash_geom.getPos(self.render)
        else:
            cam_pos = self.camera.getPos()
            cam_quat_t = self.camera.getQuat()
            cam_fwd_t = cam_quat_t.getForward()
            cam_right_t = cam_quat_t.getRight()
            cam_up_t = cam_quat_t.getUp()
            muzzle_world = cam_pos + cam_fwd_t * 0.75 + cam_right_t * (0.22 * (1.0 - self.ads_alpha)) - cam_up_t * 0.16

        travel_vec = impact_world - muzzle_world
        total_dist = travel_vec.length()
        if total_dist > 0.1:
            travel_dir = travel_vec / total_dist
        else:
            travel_dir = ray_dir
            total_dist = 1.0

        # 3D 입체 발광 탄두 (Bullet Head - 사방 어디서나 입체적으로 또렷하게 보임)
        head_np = self.world_root.attachNewNode("tracer_head")
        head_np.setPos(muzzle_world)
        head_np.lookAt(muzzle_world + travel_dir)

        # 중심 발광 탄두
        head_geom = make_cube_to(head_np, 0.08, 0.38, 0.08, LColor(1.0, 1.0, 0.90, 1.0), 0, 0, 0)
        head_geom.setLightOff()
        head_geom.setTransparency(TransparencyAttrib.MAlpha)
        head_geom.setDepthWrite(False)
        head_geom.setBin("transparent", 105)

        # 전방/시점 정면에서도 뚜렷하게 보이도록 하는 3D 십자 섬광 날개 (Cross Flare)
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

        # 3단계 다층 발광 궤적 (코어 4.5px, 글로우 9.5px, 헤일로 18.0px)
        init_len = min(3.0, total_dist * 0.35)

        ls_core = LineSegs("tracer_core")
        ls_core.setThickness(4.5)
        ls_core.setColor(1.0, 1.0, 0.90, 0.98)
        ls_core.moveTo(muzzle_world)
        ls_core.drawTo(muzzle_world + travel_dir * init_len)
        core_np = self.world_root.attachNewNode(ls_core.create())
        core_np.setLightOff()
        core_np.setTransparency(TransparencyAttrib.MAlpha)
        core_np.setDepthWrite(False)
        core_np.setBin("transparent", 102)

        ls_glow = LineSegs("tracer_glow")
        ls_glow.setThickness(9.5)
        ls_glow.setColor(1.0, 0.75, 0.15, 0.75)
        ls_glow.moveTo(muzzle_world)
        ls_glow.drawTo(muzzle_world + travel_dir * (init_len * 0.85))
        glow_np = self.world_root.attachNewNode(ls_glow.create())
        glow_np.setLightOff()
        glow_np.setTransparency(TransparencyAttrib.MAlpha)
        glow_np.setDepthWrite(False)
        glow_np.setBin("transparent", 101)

        ls_halo = LineSegs("tracer_halo")
        ls_halo.setThickness(18.0)
        ls_halo.setColor(1.0, 0.35, 0.05, 0.35)
        ls_halo.moveTo(muzzle_world)
        ls_halo.drawTo(muzzle_world + travel_dir * (init_len * 0.65))
        halo_np = self.world_root.attachNewNode(ls_halo.create())
        halo_np.setLightOff()
        halo_np.setTransparency(TransparencyAttrib.MAlpha)
        halo_np.setDepthWrite(False)
        halo_np.setBin("transparent", 100)

        # 고속 비행 (145~195 m/s) 및 빠른 잔상 소멸 (0.08초)로 화면 깔끔하게 유지
        flight_speed = max(145.0, min(195.0, total_dist * 7.5))

        self.active_tracers.append({
            "head_node": head_np,
            "core": core_np,
            "glow": glow_np,
            "halo": halo_np,
            "flash": None,
            "np": core_np,  # 하위 호환성 유지
            "start": Vec3(muzzle_world),
            "end": Vec3(impact_world),
            "dir": travel_dir,
            "total_dist": total_dist,
            "tracer_len": init_len,
            "traveled": 0.0,
            "speed": flight_speed,
            "life": 0.30,
            "phase": "fly",
            "fade_timer": 0.08,
            "fade_duration": 0.08
        })

    def spawn_hit_particles(self, hit_pos, is_blood=True):
        """총탄이 몬스터에 적중했을 때 사방으로 분출되는 3D 핏빛/스파크 파티클 버스트"""
        col = LColor(0.72, 0.04, 0.04, 1.0) if is_blood else LColor(1.0, 0.85, 0.25, 1.0)
        for _ in range(12):
            p_node = self.world_root.attachNewNode("hit_particle")
            p_node.setPos(hit_pos)
            cube = make_cube_to(p_node, 0.08, 0.08, 0.08, col, 0, 0, 0)
            cube.setLightOff()

            vx = random.uniform(-3.2, 3.2)
            vy = random.uniform(-3.2, 3.2)
            vz = random.uniform(1.2, 4.2)
            self.hit_particles.append({
                "node": p_node,
                "pos": Vec3(hit_pos),
                "vel": Vec3(vx, vy, vz),
                "timer": 0.38
            })

    def apply_upgrade(self, upgrade_type):
        """탄약 계열 특성 강화"""
        if upgrade_type == "AMMO":
            self.max_ammo += 6
            self.ammo = self.max_ammo
            self.reserve_ammo += 36
            self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)
            self.ui_mgr.show_hit_marker("[특성 강화] 최대 탄창 +6발 및 예비탄 +36발 즉시 지급!", (1.0, 0.85, 0.2, 1.0))

    def reload(self, game_state="PLAYING"):
        """R 키 입력 시 권총 다단계 전술 재장전 (탄창 분리 -> 결합 -> 슬라이드 전진)"""
        if game_state != "PLAYING" or self.is_reloading or self.ammo >= self.max_ammo:
            return
        if self.reserve_ammo <= 0:
            if self.audio_mgr:
                self.audio_mgr.play_empty_click()
            self.ui_mgr.show_hit_marker("예비 탄약이 없습니다! (탄약 상자를 탐색하세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            return

        self.is_reloading = True
        self.reload_timer = 1.30
        self.was_slide_locked_before_reload = self.slide_locked
        if self.audio_mgr:
            self.audio_mgr.play_reload()
        status_msg = "빈 탄창 배출 및 슬라이드 장전 중..." if self.slide_locked else "전술 탄창 교체 중..."
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
            self.render.setLight(drop_light_np)

            self.ammo_drops.append({
                "node": drop_np,
                "light_np": drop_light_np,
                "pos": (x, y)
            })

    def register_kill(self, player=None):
        """적 처치 시 킬 콤보 스트릭 등록 및 버프 활성화"""
        self.combo_count += 1
        self.combo_timer = self.combo_window

        titles = {
            2: ("DOUBLE KILL!", (1.0, 0.90, 0.30, 1.0)),
            3: ("TRIPLE KILL!", (1.0, 0.70, 0.20, 1.0)),
            4: ("RAMPAGE!!", (1.0, 0.45, 0.15, 1.0)),
            5: ("CARNAGE!!!", (1.0, 0.20, 0.20, 1.0)),
        }
        if self.combo_count in titles:
            title, col = titles[self.combo_count]
        elif self.combo_count > 5:
            title = f"UNSTOPPABLE x{self.combo_count}!"
            col = (1.0, 0.15, 0.85, 1.0)
        else:
            title = None
            col = (1.0, 0.85, 0.2, 1.0)

        if title and hasattr(self.ui_mgr, 'show_style_kill'):
            self.ui_mgr.show_style_kill(f"[ 🔥 {title} 🔥 ]", f"연사/장전 가속 & 탄약 절약 버프!", color=col)

        if self.combo_count >= 2 and self.audio_mgr and hasattr(self.audio_mgr, 'play_combo_kill'):
            self.audio_mgr.play_combo_kill()

    def reset_state(self, current_stage=1, keep_ammo=False):
        """게임 재시작 및 스테이지 리셋"""
        if not keep_ammo:
            self.ammo = self.max_ammo
            self.reserve_ammo = 36  # 초기 예비 탄약 36발 (몬스터 체력 증가 대응)
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.hipfire_bloom = 0.0
        self.combo_count = 0
        self.combo_timer = 0.0

        for tr in self.active_tracers:
            for key in ("np", "core", "glow", "halo", "head_node", "flash"):
                node = tr.get(key)
                if node and not node.isEmpty():
                    node.removeNode()
        self.active_tracers = []

        for p in self.hit_particles:
            if not p["node"].isEmpty():
                p["node"].removeNode()
        self.hit_particles.clear()

        self.setup_ammo_drops(current_stage)
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

    def update_ammo_ui(self):
        """탄약 UI 실시간 동기화"""
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

    _update_ammo_ui = update_ammo_ui

    def update(self, dt, px=0.0, py=0.0, is_moving=False, is_sprinting=False):
        """프레임별 트레이서, 탄피 물리, 화약 연기, 슬라이드 블로우백, 반동/재장전, 밥빙, 탄약 습득 갱신"""
        self.is_moving = is_moving
        self.is_sprinting = is_sprinting

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

                ls_c = LineSegs("tracer_core")
                ls_c.setThickness(4.5)
                ls_c.setColor(1.0, 1.0, 0.90, 0.98)
                ls_c.moveTo(trail_tail)
                ls_c.drawTo(trail_head)
                tr["core"] = self.world_root.attachNewNode(ls_c.create())
                tr["core"].setLightOff()
                tr["core"].setTransparency(TransparencyAttrib.MAlpha)
                tr["core"].setDepthWrite(False)
                tr["core"].setBin("transparent", 102)
                tr["np"] = tr["core"]

                ls_g = LineSegs("tracer_glow")
                ls_g.setThickness(9.5)
                ls_g.setColor(1.0, 0.75, 0.15, 0.75)
                mid_tail = trail_tail + (trail_head - trail_tail) * 0.15
                ls_g.moveTo(mid_tail)
                ls_g.drawTo(trail_head)
                tr["glow"] = self.world_root.attachNewNode(ls_g.create())
                tr["glow"].setLightOff()
                tr["glow"].setTransparency(TransparencyAttrib.MAlpha)
                tr["glow"].setDepthWrite(False)
                tr["glow"].setBin("transparent", 101)

                ls_h = LineSegs("tracer_halo")
                ls_h.setThickness(18.0)
                ls_h.setColor(1.0, 0.35, 0.05, 0.35)
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

                    ls_c = LineSegs("tracer_core")
                    ls_c.setThickness(4.5 * fade_alpha)
                    ls_c.setColor(1.0, 1.0, 0.90, 0.98 * fade_alpha)
                    ls_c.moveTo(trail_tail)
                    ls_c.drawTo(trail_head)
                    tr["core"] = self.world_root.attachNewNode(ls_c.create())
                    tr["core"].setLightOff()
                    tr["core"].setTransparency(TransparencyAttrib.MAlpha)
                    tr["core"].setDepthWrite(False)
                    tr["core"].setBin("transparent", 102)
                    tr["np"] = tr["core"]

                    ls_g = LineSegs("tracer_glow")
                    ls_g.setThickness(9.5 * fade_alpha)
                    ls_g.setColor(1.0, 0.75, 0.15, 0.75 * fade_alpha)
                    mid_tail = trail_tail + (trail_head - trail_tail) * 0.15
                    ls_g.moveTo(mid_tail)
                    ls_g.drawTo(trail_head)
                    tr["glow"] = self.world_root.attachNewNode(ls_g.create())
                    tr["glow"].setLightOff()
                    tr["glow"].setTransparency(TransparencyAttrib.MAlpha)
                    tr["glow"].setDepthWrite(False)
                    tr["glow"].setBin("transparent", 101)

                    ls_h = LineSegs("tracer_halo")
                    ls_h.setThickness(18.0 * fade_alpha)
                    ls_h.setColor(1.0, 0.35, 0.05, 0.35 * fade_alpha)
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

        # 피격 파티클 갱신
        for p in self.hit_particles[:]:
            p["timer"] -= dt
            p["vel"].z -= 13.0 * dt  # 중력
            p["pos"] += p["vel"] * dt
            p["node"].setPos(p["pos"])
            scale = max(0.1, p["timer"] / 0.38)
            p["node"].setScale(scale)
            if p["timer"] <= 0.0:
                if not p["node"].isEmpty():
                    p["node"].removeNode()
                self.hit_particles.remove(p)

        # 사격 쿨다운 & 총구 화염 처리
        if self.shoot_cooldown > 0.0:
            self.shoot_cooldown = max(0.0, self.shoot_cooldown - dt)

        if self.muzzle_timer > 0.0:
            self.muzzle_timer -= dt
            if self.muzzle_timer <= 0.0:
                self.muzzle_flash_geom.hide()
                self.render.clearLight(self.muzzle_light_np)

        # 3D 탄피 물리 갱신 (중력, 궤적, 지면 튕김, 회전)
        for c in self.active_casings[:]:
            c["life"] -= dt
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

            if c["life"] <= 0.0:
                if not c["node"].isEmpty():
                    c["node"].removeNode()
                self.active_casings.remove(c)

        # 총구 잔여 가스 연기 갱신 (열상승, 팽창, 페이드아웃)
        for s in self.smoke_particles[:]:
            s["timer"] -= dt
            s["vel"].z += 0.35 * dt
            s["pos"] += s["vel"] * dt
            s["scale"] += dt * 0.12
            s["node"].setPos(s["pos"])
            s["node"].setScale(s["scale"])
            alpha = max(0.0, (s["timer"] / s["max_timer"]) * 0.35)
            s["cube"].setColorScale(1, 1, 1, alpha)

            if s["timer"] <= 0.0:
                if not s["node"].isEmpty():
                    s["node"].removeNode()
                self.smoke_particles.remove(s)

        # 현실적 슬라이드 블로우백 및 공이치기 애니메이션
        if self.slide_timer > 0.0:
            self.slide_timer = max(0.0, self.slide_timer - dt)
            half_dur = self.slide_blowback_duration * 0.5
            if self.slide_timer > half_dur:
                # 1단계: 슬라이드 급속 후퇴 (0.0 -> -0.055m)
                t_rear = (self.slide_blowback_duration - self.slide_timer) / half_dur
                self.slide_node.setPos(0, self.slide_max_travel * t_rear, 0)
                self.hammer_node.setP(-42 * t_rear)
            else:
                # 2단계: 복좌 전진 (잔탄 0이면 후퇴 고정 유지)
                if self.slide_locked:
                    self.slide_node.setPos(0, self.slide_max_travel, 0)
                    self.hammer_node.setP(-42)
                else:
                    t_fwd = self.slide_timer / half_dur
                    self.slide_node.setPos(0, self.slide_max_travel * t_fwd, 0)
                    self.hammer_node.setP(-42)
        elif not self.is_reloading:
            if self.slide_locked:
                self.slide_node.setPos(0, self.slide_max_travel, 0)
                self.hammer_node.setP(-42)
            else:
                self.slide_node.setPos(0, 0, 0)
                self.hammer_node.setP(-42)

        # 콤보 스트릭 타이머 감쇄
        if self.combo_timer > 0.0:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo_count = 0

        # 현실적 다단계 재장전 애니메이션 및 반동
        if self.is_reloading:
            # 콤보 상태일 때 재장전 속도 1.35배 가속!
            reload_step = dt * 1.35 if self.combo_count >= 2 else dt
            self.reload_timer = max(0.0, self.reload_timer - reload_step)
            total_dur = 1.30
            p = 1.0 - (self.reload_timer / total_dur)  # 0.0 -> 1.0

            # 1단계 (0.0 ~ 0.35): 총기 왼쪽 틸트 & 탄창 배출 낙하
            if p < 0.35:
                sub_p = p / 0.35
                self.recoil_node.setR(-22.0 * math.sin(sub_p * math.pi * 0.5))
                self.recoil_node.setP(-18.0 * math.sin(sub_p * math.pi * 0.5))
                drop_z = sub_p * 0.32
                self.mag_node.setPos(0, -drop_z * 0.28, -drop_z)
                self.mag_node.setScale(max(0.05, 1.0 - sub_p * 0.8))

            # 2단계 (0.35 ~ 0.78): 새 탄창 꺼내어 탄창구 삽입 및 찰칵 결합
            elif p < 0.78:
                sub_p = (p - 0.35) / 0.43
                self.recoil_node.setR(-22.0 * (1.0 - sub_p * 0.3))
                self.recoil_node.setP(-18.0 * (1.0 - sub_p * 0.3))
                rise_z = (1.0 - min(1.0, sub_p * 1.1)) * 0.28
                self.mag_node.setScale(1.0)
                self.mag_node.setPos(0, -rise_z * 0.28, -rise_z)

            # 3단계 (0.78 ~ 1.0): 슬라이드 전진 격발 준비 (슬라이드 스톱 릴리즈) 및 총기 복귀
            else:
                sub_p = (p - 0.78) / 0.22
                self.mag_node.setPos(0, 0, 0)
                self.mag_node.setScale(1.0)
                # 슬라이드가 걸려있던 경우 멈치를 눌러 전진!
                if self.was_slide_locked_before_reload:
                    self.slide_locked = False
                    self.slide_node.setPos(0, 0, 0)

                self.recoil_node.setR(-22.0 * 0.7 * (1.0 - sub_p))
                self.recoil_node.setP(-18.0 * 0.7 * (1.0 - sub_p))

            if self.reload_timer <= 0.0:
                self.is_reloading = False
                self.slide_locked = False
                self.slide_node.setPos(0, 0, 0)
                self.recoil_node.setPos(0, 0, 0)
                self.recoil_node.setP(0)
                self.recoil_node.setR(0)
                self.mag_node.setPos(0, 0, 0)
                self.mag_node.setScale(1.0)

                needed = self.max_ammo - self.ammo
                transferred = min(needed, self.reserve_ammo)
                self.ammo += transferred
                self.reserve_ammo -= transferred
                self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)
                self.ui_mgr.show_hit_marker(f"재장전 완료! (+{transferred}발 장전됨)", (0.35, 1.0, 0.5, 1.0))
                self.hit_marker_timer = 1.5
        elif self.recoil_timer > 0.0:
            self.recoil_timer -= dt
            t_norm = max(0.0, self.recoil_timer / 0.10)
            recoil_dist = 0.05 if not self.is_aiming else 0.024
            recoil_deg = 12.0 if not self.is_aiming else 5.5
            self.recoil_node.setPos(0, -recoil_dist * t_norm, (recoil_dist * 0.4) * t_norm)
            self.recoil_node.setP(recoil_deg * t_norm)
            self.recoil_node.setR(0)
        else:
            self.recoil_node.setPos(0, 0, 0)
            self.recoil_node.setP(0)
            self.recoil_node.setR(0)

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
                    self.reserve_ammo += 12
                    if self.audio_mgr:
                        self.audio_mgr.play_ammo_pickup()
                    self.ui_mgr.show_hit_marker("탄약 상자 획득! (+12발 예비탄)", (0.35, 1.0, 0.5, 1.0))
                    self.hit_marker_timer = 2.0
                    if "light_np" in drop and drop["light_np"] and not drop["light_np"].isEmpty():
                        self.render.clearLight(drop["light_np"])
                    if "node" in drop and drop["node"] and not drop["node"].isEmpty():
                        drop["node"].removeNode()
                    self.ammo_drops.remove(drop)
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

        # 정밀 조준(ADS) 부드러운 위치/화각 보간
        ads_speed = 10.0
        if self.is_aiming:
            self.ads_alpha = min(1.0, self.ads_alpha + ads_speed * dt)
        else:
            self.ads_alpha = max(0.0, self.ads_alpha - ads_speed * dt)

        cur_pos = self.ads_hip_pos * (1.0 - self.ads_alpha) + self.ads_aim_pos * self.ads_alpha
        cur_hpr = self.ads_hip_hpr * (1.0 - self.ads_alpha) + self.ads_aim_hpr * self.ads_alpha
        self.vm_pistol.setPos(cur_pos)
        self.vm_pistol.setHpr(cur_hpr)

        # 카메라 FOV 줌 (기본 88도 넓은 시야각 -> 정밀조준 시 72도로 자연스럽게 확대)
        if hasattr(self.base, 'camLens') and self.base.camLens:
            cur_fov = 88.0 * (1.0 - self.ads_alpha) + 72.0 * self.ads_alpha
            self.base.camLens.setFov(cur_fov)

        # 조준 중 크로스헤어 투명화 (가늠쇠 조준 유도)
        if hasattr(self.ui_mgr, 'set_crosshair_visible'):
            self.ui_mgr.set_crosshair_visible(self.ads_alpha < 0.45)

        # 뷰모델 보행 밥빙 & 호흡 스웨이 (조준 중에는 밥빙이 억제됨)
        bob_mult = 1.0 - self.ads_alpha * 0.75
        if is_moving:
            self.bobbing_time += dt * (14.0 if is_sprinting else 8.5)
            bob_x = math.sin(self.bobbing_time * 0.5) * 0.012 * bob_mult
            bob_y = abs(math.cos(self.bobbing_time)) * 0.014 * bob_mult
            self.vm_root.setPos(bob_x, 0, -bob_y)
        else:
            self.bobbing_time += dt * 2.0
            sway_z = math.sin(self.bobbing_time) * 0.003 * bob_mult
            self.vm_root.setPos(0, 0, sway_z)
    def set_blackout_mode(self, is_active: bool):
        """정전 비상등 핏빛 조명 모드 전환"""
        self.is_blackout = is_active
        if is_active:
            self.pl_np.node().setColor((2.70, 0.85, 0.70, 1.0))
        else:
            self.pl_np.node().setColor((2.85, 2.70, 2.35, 1.0))
