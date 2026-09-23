"""
Combat System Module
1인칭 듀얼 뷰모델(손전등/권총), 레이캐스트 사격, 재장전, 반동/밥빙 애니메이션,
발광 총알 궤적(Bullet Tracer) 및 필드 탄약 상자 드랍/습득 관리
"""

import math
import random
from panda3d.core import (
    PointLight, Spotlight, PerspectiveLens, LineSegs, LColor, Vec3,
    GeomVertexFormat, GeomVertexData, Geom, GeomNode, GeomTriangles, GeomVertexWriter,
    TransparencyAttrib, PNMImage, Texture, CardMaker
)
from constants import (
    CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import cell_has_pillar
from geometry import make_cube_to


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
        self.reserve_ammo = 0
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

        # 정전 및 대기 안개 효과 상태
        self.is_blackout = False
        self.beam_flicker_time = 0.0
        self.mist_particles = []
        self._setup_mist_particles()

        # 뷰모델 지오메트리 구축
        self._setup_viewmodel()

    def _setup_viewmodel(self):
        """1인칭 듀얼 뷰모델: 왼손 손전등 & 오른손 12발 권총"""
        if hasattr(self, 'vm_root') and self.vm_root:
            self.vm_root.removeNode()

        self.vm_root = self.camera.attachNewNode("viewmodel_root")

        # --- (A) 왼손: 택티컬 손전등 ---
        self.vm_flashlight = self.vm_root.attachNewNode("vm_flashlight")
        self.vm_flashlight.setPos(-0.32, 0.78, -0.28)
        self.vm_flashlight.setHpr(-3.5, 2.0, 0)

        fl_body_col = LColor(0.12, 0.12, 0.14, 1.0)
        fl_ring_col = LColor(0.28, 0.30, 0.34, 1.0)
        fl_lens_col = LColor(1.0, 0.98, 0.88, 1.0)

        make_cube_to(self.vm_flashlight, 0.08, 0.28, 0.08, fl_body_col, 0, 0, 0)
        make_cube_to(self.vm_flashlight, 0.11, 0.09, 0.11, fl_ring_col, 0, 0.17, 0)
        glass = make_cube_to(self.vm_flashlight, 0.095, 0.02, 0.095, fl_lens_col, 0, 0.22, 0)
        glass.setLightOff()

        # 손전등 Spotlight
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

        # 근거리 필라이트
        fill_light = PointLight('player_fill')
        fill_light.setColor((0.18, 0.16, 0.14, 1.0))
        fill_light.setAttenuation((1.0, 0.28, 0.08))
        self.fill_np = self.vm_flashlight.attachNewNode(fill_light)
        self.fill_np.setPos(0, 0.10, 0)
        self.render.setLight(self.fill_np)

        # 손전등 입체 안개 광선 (Volumetric Light Cone)
        self._setup_flashlight_beam()

        # --- (B) 오른손: 12발 권총 ---
        self.vm_pistol = self.vm_root.attachNewNode("vm_pistol")
        self.vm_pistol.setPos(0.30, 0.74, -0.26)
        self.vm_pistol.setHpr(3.0, 1.5, 0)

        self.recoil_node = self.vm_pistol.attachNewNode("recoil_node")

        steel_dark = LColor(0.10, 0.10, 0.12, 1.0)
        steel_slide = LColor(0.22, 0.23, 0.26, 1.0)
        grip_col = LColor(0.06, 0.06, 0.07, 1.0)
        tritium_green = LColor(0.35, 1.0, 0.40, 1.0)

        # 슬라이드, 총열, 그립, 방아쇠울
        make_cube_to(self.recoil_node, 0.065, 0.30, 0.09, steel_slide, 0, 0.05, 0.04)
        make_cube_to(self.recoil_node, 0.045, 0.08, 0.045, steel_dark, 0, 0.22, 0.035)
        grip = make_cube_to(self.recoil_node, 0.058, 0.11, 0.20, grip_col, 0, -0.06, -0.09)
        grip.setP(16)
        make_cube_to(self.recoil_node, 0.030, 0.08, 0.06, steel_dark, 0, 0.04, -0.04)

        # 트리튬 야광 가늠쇠/가늠자
        front_sight = make_cube_to(self.recoil_node, 0.012, 0.02, 0.02, tritium_green, 0, 0.19, 0.09)
        front_sight.setLightOff()
        r_sight1 = make_cube_to(self.recoil_node, 0.012, 0.015, 0.02, tritium_green, -0.022, -0.09, 0.09)
        r_sight2 = make_cube_to(self.recoil_node, 0.012, 0.015, 0.02, tritium_green, 0.022, -0.09, 0.09)
        r_sight1.setLightOff()
        r_sight2.setLightOff()

        # 총구 화염 지오메트리 & 조명
        self.muzzle_flash_geom = make_cube_to(self.recoil_node, 0.16, 0.22, 0.16, LColor(1.0, 0.85, 0.25, 1.0), 0, 0.34, 0.04, rot_h=45)
        self.muzzle_flash_geom.setLightOff()
        self.muzzle_flash_geom.hide()

        self.muzzle_light = PointLight('muzzle_light')
        self.muzzle_light.setColor((2.8, 2.2, 0.9, 1.0))
        self.muzzle_light.setAttenuation((1.0, 0.08, 0.015))
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)
        self.muzzle_light_np.setPos(0, 0.35, 0.04)

    def shoot(self, monsters, player=None, game_state="PLAYING"):
        """권총 사격 및 다중 몬스터 대상 레이캐스트 적중 판정"""
        if game_state != "PLAYING" or self.is_reloading or self.shoot_cooldown > 0.0:
            return

        if self.ammo <= 0:
            if self.reserve_ammo > 0:
                self.ui_mgr.show_hit_marker("탄약 소진! [R] 키를 눌러 재장전하세요!", (1.0, 0.4, 0.4, 1.0))
            else:
                self.ui_mgr.show_hit_marker("탄약 소진! (맵에서 탄약 상자를 찾으세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            self.shoot_cooldown = 0.35
            return

        self.ammo -= 1
        self.shoot_cooldown = 0.22
        self.recoil_timer = 0.10
        self.muzzle_timer = 0.04
        self.muzzle_flash_geom.show()
        self.render.setLight(self.muzzle_light_np)
        self.audio_mgr.play_gunshot()
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

        # 다중 몬스터 대상 레이캐스트 히트스캔
        ray_origin = self.camera.getPos()
        ray_dir = self.camera.getQuat().getForward()

        closest_monster = None
        min_hit_dist = 999.0

        monster_list = monsters if isinstance(monsters, (list, tuple)) else [monsters]
        for m in monster_list:
            if getattr(m, 'hp', 1) <= 0:
                continue
            is_hit, hit_dist = m.is_hit_by_ray(ray_origin, ray_dir)
            if is_hit and hit_dist < min_hit_dist:
                min_hit_dist = hit_dist
                closest_monster = m

        tracer_dist = min(55.0, min_hit_dist) if closest_monster is not None else 55.0
        impact_world = ray_origin + ray_dir * tracer_dist

        if closest_monster is not None:
            blackout_active = getattr(self.base, 'blackout_active', False)
            if player and hasattr(player, 'get_attack_power'):
                dmg = player.get_attack_power(blackout_active=blackout_active)
            else:
                dmg = getattr(player, 'attack_power', 35.0) if player else 35.0

            is_dead = closest_monster.take_damage(dmg)
            m_name = getattr(closest_monster, 'name', '괴물')

            # 몬스터 피격 효과: 크로스헤어 피격 마커 & 3D 핏빛 파티클 분출
            self.ui_mgr.trigger_crosshair_hit(is_kill=is_dead)
            self.spawn_hit_particles(impact_world, is_blood=True)

            if is_dead:
                exp_gain = getattr(closest_monster, 'exp_value', 35)
                # 정전 중 처치 시 경험치 2배 & 비상 탄약 보급 (+6발)
                if blackout_active:
                    exp_gain *= 2
                    self.reserve_ammo += 6
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

                # 피의 갈증 유물: 적 처치 시 체력 12 즉시 흡혈
                if player and hasattr(player, 'relics') and "blood_thirst" in player.relics:
                    player.heal(12.0)

                if hasattr(closest_monster, 'turn_into_corpse'):
                    closest_monster.turn_into_corpse()
                if player:
                    player.gain_exp(exp_gain)
            else:
                self.ui_mgr.show_hit_marker("")
                self.hit_marker_timer = 0.0

            if "뱀" in m_name:
                self.audio_mgr.play_serpent_hit()
            elif "해골" in m_name:
                self.audio_mgr.play_skeleton_hit()
            elif "오크" in m_name:
                self.audio_mgr.play_gunshot()
            else:
                self.audio_mgr.play_serpent_hit()

        # 발광 총알 궤적 (Bullet Tracer)
        cam_pos = self.camera.getPos()
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()

        muzzle_world = cam_pos + cam_fwd * 0.86 + cam_right * 0.30 - cam_up * 0.22
        tracer_dist = 55.0
        if closest_monster is not None:
            tracer_dist = min(tracer_dist, min_hit_dist)

        impact_world = cam_pos + ray_dir * tracer_dist

        ls = LineSegs("bullet_tracer")
        ls.setThickness(3.6)
        ls.setColor(1.0, 0.94, 0.35, 1.0)
        ls.moveTo(muzzle_world)
        ls.drawTo(impact_world)
        tracer_node = ls.create()
        tracer_np = self.world_root.attachNewNode(tracer_node)
        tracer_np.setLightOff()

        self.active_tracers.append({"np": tracer_np, "life": 0.09})

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
        """R 키 입력 시 권총 재장전"""
        if game_state != "PLAYING" or self.is_reloading or self.ammo >= self.max_ammo:
            return
        if self.reserve_ammo <= 0:
            self.ui_mgr.show_hit_marker("예비 탄약이 없습니다! (탄약 상자를 탐색하세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            return

        self.is_reloading = True
        self.reload_timer = 1.2
        self.ui_mgr.show_hit_marker("재장전 중...", (0.9, 0.9, 0.9, 1.0))
        self.hit_marker_timer = 1.3

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

    def reset_state(self, current_stage=1, keep_ammo=False):
        """게임 재시작 및 스테이지 리셋"""
        if not keep_ammo:
            self.ammo = self.max_ammo
            self.reserve_ammo = 0
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0

        for tr in self.active_tracers:
            if tr.get("np") and not tr["np"].isEmpty():
                tr["np"].removeNode()
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

    def update(self, dt, px, py, is_moving, is_sprinting):
        """프레임별 트레이서, 반동/재장전, 밥빙, 탄약 습득 갱신"""
        # 총알 궤적 수명 관리
        for tr in self.active_tracers[:]:
            tr["life"] -= dt
            if tr["life"] <= 0.0:
                tr["np"].removeNode()
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

        # 재장전 및 반동 애니메이션
        if self.is_reloading:
            self.reload_timer -= dt
            t_rel = max(0.0, self.reload_timer / 1.2)
            tilt = math.sin(t_rel * math.pi)
            self.recoil_node.setPos(0, -0.07 * tilt, -0.10 * tilt)
            self.recoil_node.setP(-26.0 * tilt)

            if self.reload_timer <= 0.0:
                self.is_reloading = False
                self.recoil_node.setPos(0, 0, 0)
                self.recoil_node.setP(0)
                needed = self.max_ammo - self.ammo
                transferred = min(needed, self.reserve_ammo)
                self.ammo += transferred
                self.reserve_ammo -= transferred
                self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)
                self.ui_mgr.show_hit_marker(f"재장전 완료! (+{transferred}발)", (0.35, 1.0, 0.5, 1.0))
                self.hit_marker_timer = 1.5
        elif self.recoil_timer > 0.0:
            self.recoil_timer -= dt
            t_norm = max(0.0, self.recoil_timer / 0.10)
            self.recoil_node.setPos(0, -0.05 * t_norm, 0.02 * t_norm)
            self.recoil_node.setP(12.0 * t_norm)
        else:
            self.recoil_node.setPos(0, 0, 0)
            self.recoil_node.setP(0)

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
                    self.ui_mgr.show_hit_marker("탄약 상자 획득! (+12발 예비탄)", (0.35, 1.0, 0.5, 1.0))
                    self.hit_marker_timer = 2.0
                    if "light_np" in drop and drop["light_np"] and not drop["light_np"].isEmpty():
                        self.render.clearLight(drop["light_np"])
                    if "node" in drop and drop["node"] and not drop["node"].isEmpty():
                        drop["node"].removeNode()
                    self.ammo_drops.remove(drop)
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

        # 뷰모델 보행 밥빙 & 호흡 스웨이
        if is_moving:
            self.bobbing_time += dt * (14.0 if is_sprinting else 8.5)
            bob_x = math.sin(self.bobbing_time * 0.5) * 0.012
            bob_y = abs(math.cos(self.bobbing_time)) * 0.014
            self.vm_root.setPos(bob_x, 0, -bob_y)
        else:
            self.bobbing_time += dt * 2.0
            sway_z = math.sin(self.bobbing_time) * 0.003
            self.vm_root.setPos(0, 0, sway_z)

        # 손전등 볼륨메트릭 안개 광선 및 공기 중 3D 미스트 입자 갱신
        self._update_flashlight_beam(dt)
        self._update_mist_particles(dt, px, py)

    def _setup_flashlight_beam(self):
        """손전등 빛줄기 및 볼륨메트릭 안개 원뿔 (Volumetric Light Cone)"""
        format = GeomVertexFormat.getV3c4()
        vdata = GeomVertexData('fl_beam', format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        color = GeomVertexWriter(vdata, 'color')

        # 5개 링: 손전등 렌즈(y=0.25)부터 28m 전방까지 점진적 부드러운 안개 빛줄기 형성
        rings = [
            (0.25, 0.06, 0.00),   # 렌즈 시작점 (투명)
            (1.20, 0.45, 0.16),   # 근거리 피크 광량 (살짝 밝은 중심부)
            (5.50, 1.90, 0.09),   # 중근거리 안개 산란
            (14.0, 4.80, 0.04),   # 원거리 감쇠
            (28.0, 9.80, 0.00),   # 최원거리 0 페이드아웃
        ]
        segments = 16

        for y, r, a in rings:
            for i in range(segments):
                angle = 2.0 * math.pi * i / segments
                x = r * math.cos(angle)
                z = r * math.sin(angle)
                vertex.addData3(x, y, z)
                color.addData4(1.0, 0.96, 0.88, a)

        tris = GeomTriangles(Geom.UHStatic)
        num_rings = len(rings)
        for ring_idx in range(num_rings - 1):
            r0 = ring_idx * segments
            r1 = (ring_idx + 1) * segments
            for i in range(segments):
                nxt = (i + 1) % segments
                tris.addVertices(r0 + i, r0 + nxt, r1 + nxt)
                tris.addVertices(r0 + i, r1 + nxt, r1 + i)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('volumetric_flashlight_beam')
        node.addGeom(geom)
        self.beam_np = self.vm_flashlight.attachNewNode(node)
        self.beam_np.setTransparency(TransparencyAttrib.M_alpha)
        self.beam_np.setTwoSided(True)
        self.beam_np.setLightOff()
        self.beam_np.setDepthWrite(False)
        self.beam_np.setBin('transparent', 20)

    def _setup_mist_particles(self):
        """플레이어 주변 공기 중에 떠다니는 3D 안개/미스트 입자 시스템"""
        pnm = PNMImage(64, 64, 4)
        for x in range(64):
            for y in range(64):
                dx = (x - 31.5) / 31.5
                dy = (y - 31.5) / 31.5
                r = math.hypot(dx, dy)
                a = max(0.0, min(1.0, 1.0 - r)) ** 1.8
                pnm.setXel(x, y, 1.0, 1.0, 1.0)
                pnm.setAlpha(x, y, a)
        self.mist_tex = Texture('procedural_mist')
        self.mist_tex.load(pnm)

        cm = CardMaker('mist_sprite')
        cm.setFrame(-2.0, 2.0, -2.0, 2.0)
        mist_geom = cm.generate()

        self.mist_root = self.render.attachNewNode("mist_particles_root")
        self.mist_root.setTransparency(TransparencyAttrib.M_alpha)
        self.mist_root.setLightOff()
        self.mist_root.setDepthWrite(False)
        self.mist_root.setBin('transparent', 21)

        self.mist_particles = []
        num_particles = 48

        for _ in range(num_particles):
            node = self.mist_root.attachNewNode(mist_geom)
            node.setTexture(self.mist_tex)
            node.setBillboardPointEye()

            rx = random.uniform(-18.0, 18.0)
            ry = random.uniform(-18.0, 18.0)
            rz = random.uniform(0.5, 3.2)
            node.setPos(rx, ry, rz)

            scale = random.uniform(1.2, 2.8)
            node.setScale(scale)

            p_data = {
                "node": node,
                "rel_x": rx,
                "rel_y": ry,
                "z": rz,
                "vx": random.uniform(-0.20, 0.20),
                "vy": random.uniform(-0.20, 0.20),
                "base_alpha": random.uniform(0.18, 0.38),
                "rot": random.uniform(0.0, 360.0),
                "rot_speed": random.uniform(-5.0, 5.0),
            }
            self.mist_particles.append(p_data)

    def _update_flashlight_beam(self, dt):
        """손전등 빛줄기 미세 흔들림 및 밥빙 연동"""
        if not hasattr(self, 'beam_np') or self.beam_np.isEmpty():
            return
        self.beam_flicker_time += dt * 5.0
        subtle_pulse = 1.0 + math.sin(self.beam_flicker_time) * 0.04
        if self.is_blackout:
            self.beam_np.setColorScale(1.10 * subtle_pulse, 0.22 * subtle_pulse, 0.18 * subtle_pulse, 1.25)
        else:
            self.beam_np.setColorScale(subtle_pulse, subtle_pulse, subtle_pulse, 1.0)

    def _update_mist_particles(self, dt, px, py):
        """플레이어 주변 안개 입자 부유 및 손전등 조명 반응 갱신"""
        if not hasattr(self, 'mist_particles') or not self.mist_particles:
            return
        cam_pos = self.camera.getPos(self.render)
        cam_fwd = self.camera.getQuat(self.render).getForward()

        wrap_dist = 20.0
        for p in self.mist_particles:
            p["rel_x"] += p["vx"] * dt
            p["rel_y"] += p["vy"] * dt
            p["rot"] += p["rot_speed"] * dt
            p["node"].setR(p["rot"])

            if p["rel_x"] > wrap_dist:
                p["rel_x"] -= wrap_dist * 2.0
            elif p["rel_x"] < -wrap_dist:
                p["rel_x"] += wrap_dist * 2.0

            if p["rel_y"] > wrap_dist:
                p["rel_y"] -= wrap_dist * 2.0
            elif p["rel_y"] < -wrap_dist:
                p["rel_y"] += wrap_dist * 2.0

            world_x = px + p["rel_x"]
            world_y = py + p["rel_y"]
            p["node"].setPos(world_x, world_y, p["z"])

            # 손전등 광선 안에 있는지 판정
            dx = world_x - cam_pos.x
            dy = world_y - cam_pos.y
            dz = p["z"] - cam_pos.z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist > 0.1:
                dir_x = dx / dist
                dir_y = dy / dist
                dir_z = dz / dist
                dot = dir_x * cam_fwd.x + dir_y * cam_fwd.y + dir_z * cam_fwd.z
            else:
                dot = 1.0

            # 손전등 원뿔(스포트라이트 fov 44도 = 반각 22도, cos(22) = 0.927. 주변산란 포함 dot > 0.70)
            in_light = max(0.0, (dot - 0.70) / 0.25) if dot > 0.70 else 0.0
            dist_fade = max(0.0, 1.0 - (dist / 26.0))
            light_boost = in_light * dist_fade

            if self.is_blackout:
                # 비상 정전 프로토콜: 핏빛 붉은 안개가 손전등 빛을 받아 붉게 산란
                r = 0.55 + 0.45 * light_boost
                g = 0.05 + 0.12 * light_boost
                b = 0.05 + 0.10 * light_boost
                alpha = p["base_alpha"] * (0.45 + 0.55 * light_boost)
            else:
                # 일반 모드: 스산하고 자욱한 차가운 백색 안개
                r = 0.40 + 0.60 * light_boost
                g = 0.38 + 0.58 * light_boost
                b = 0.35 + 0.55 * light_boost
                alpha = p["base_alpha"] * (0.35 + 0.65 * light_boost)

            p["node"].setColorScale(r, g, b, alpha)

    def set_blackout_mode(self, is_active: bool):
        """정전 비상등 핏빛 안개 모드 전환"""
        self.is_blackout = is_active
        if is_active:
            if hasattr(self, 'beam_np') and not self.beam_np.isEmpty():
                self.beam_np.setColorScale(1.10, 0.22, 0.18, 1.25)
            self.pl_np.node().setColor((2.70, 1.80, 1.60, 1.0))
        else:
            if hasattr(self, 'beam_np') and not self.beam_np.isEmpty():
                self.beam_np.setColorScale(1.0, 1.0, 1.0, 1.0)
            self.pl_np.node().setColor((2.85, 2.70, 2.35, 1.0))
