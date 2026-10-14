import math
import random
from panda3d.core import Vec3, LColor, PointLight, ClockObject, NodePath
from geometry import make_cube


def create_monster_explosion(parent, pos, monster_type, audio_mgr=None):
    """
    몬스터 사망 시 신체 파편화 3D 폭발 시뮬레이션
    - 두개골, 갈비뼈, 척추, 엄니, 비늘 마디, 살점, 갑주, 불타는 마력 불씨 등 35개 내외의 고체 파편 큐브 생성
    - 사방 360도 방사형 폭발 속도 (Horizontal 3.0~8.5 m/s, Upward 2.5~7.5 m/s) 및 3축 고속 텀블링 회전
    - 바닥 탄성 튕김 및 마찰 감쇠 물리 시뮬레이션
    - 순간 고광도 폭발 섬광 조명(PointLight) 및 바닥 핏자국 크레이터 생성
    - 파열 폭발 사운드 재생
    """
    if audio_mgr and hasattr(audio_mgr, 'play_monster_explode'):
        audio_mgr.play_monster_explode()

    # 1. 순간 폭발 섬광 라이트
    blast_light = PointLight(f"{monster_type}_blast_light")
    if monster_type == "skeleton":
        blast_light.setColor((1.4, 2.0, 2.8, 1.0))
    elif monster_type == "orc":
        blast_light.setColor((3.0, 1.4, 0.4, 1.0))
    elif monster_type == "serpent":
        blast_light.setColor((2.6, 0.4, 0.6, 1.0))
    else:  # witch
        blast_light.setColor((2.4, 0.6, 2.6, 1.0))
    blast_light.setAttenuation((1.0, 0.20, 0.08))
    blast_np = parent.attachNewNode(blast_light)
    blast_np.setPos(pos.x, pos.y, pos.z + 1.2)
    parent.setLight(blast_np)

    # 2. 바닥 핏자국 / 유혈 크레이터 생성
    if monster_type == "skeleton":
        blood_col = LColor(0.24, 0.03, 0.03, 0.95)
        pw, pd = 2.8, 2.8
    elif monster_type == "orc":
        blood_col = LColor(0.18, 0.08, 0.03, 0.95)
        pw, pd = 3.4, 3.4
    elif monster_type == "serpent":
        blood_col = LColor(0.16, 0.02, 0.02, 0.95)
        pw, pd = 3.0, 3.0
    else:
        blood_col = LColor(0.18, 0.04, 0.08, 0.95)
        pw, pd = 2.6, 2.6
    puddle = make_cube(f"{monster_type}_splatter", pw, pd, 0.015, blood_col)
    puddle.reparentTo(parent)
    puddle.setPos(pos.x, pos.y, 0.02)
    puddle.setLightOff()

    # 3. 몬스터 타입별 파편 청사진 (Blueprint)
    debris_blueprints = []
    if monster_type == "skeleton":
        ivory = LColor(0.88, 0.86, 0.78, 1.0)
        dark_bone = LColor(0.68, 0.65, 0.58, 1.0)
        cyan_spark = LColor(0.25, 0.85, 1.0, 1.0)
        debris_blueprints = [
            ("deb_skel_skull", 0.36, 0.40, 0.38, ivory, 1, False),
            ("deb_skel_jaw", 0.26, 0.20, 0.14, dark_bone, 1, False),
            ("deb_skel_pelvis", 0.44, 0.24, 0.30, ivory, 1, False),
            ("deb_skel_rib", 0.08, 0.36, 0.08, ivory, 6, False),
            ("deb_skel_vert", 0.14, 0.14, 0.14, dark_bone, 6, False),
            ("deb_skel_limb", 0.10, 0.52, 0.10, ivory, 4, False),
            ("deb_skel_claw", 0.12, 0.20, 0.08, dark_bone, 2, False),
            ("deb_skel_splinter", 0.06, 0.08, 0.06, ivory, 10, False),
            ("deb_skel_spark", 0.07, 0.07, 0.07, cyan_spark, 4, True),
        ]
    elif monster_type == "orc":
        mud_skin = LColor(0.26, 0.23, 0.17, 1.0)
        tusk_ivory = LColor(0.88, 0.85, 0.72, 1.0)
        iron_armor = LColor(0.20, 0.20, 0.22, 1.0)
        flesh_gore = LColor(0.35, 0.12, 0.10, 1.0)
        moss_col = LColor(0.18, 0.26, 0.14, 1.0)
        blood_red = LColor(0.42, 0.08, 0.08, 1.0)
        amber_col = LColor(1.0, 0.75, 0.15, 1.0)
        debris_blueprints = [
            ("deb_orc_head", 0.48, 0.44, 0.42, mud_skin, 1, False),
            ("deb_orc_tusk", 0.12, 0.30, 0.12, tusk_ivory, 2, False),
            ("deb_orc_armor", 0.40, 0.36, 0.24, iron_armor, 2, False),
            ("deb_orc_meat", 0.32, 0.42, 0.28, flesh_gore, 4, False),
            ("deb_orc_fist", 0.28, 0.28, 0.28, mud_skin, 2, False),
            ("deb_orc_torso", 0.42, 0.30, 0.24, moss_col, 2, False),
            ("deb_orc_gib", 0.12, 0.14, 0.12, blood_red, 18, False),
            ("deb_orc_ember", 0.08, 0.08, 0.08, amber_col, 4, True),
        ]
    elif monster_type == "serpent":
        black_scale = LColor(0.015, 0.015, 0.02, 1.0)
        mid_scale = LColor(0.025, 0.025, 0.035, 1.0)
        fang_ivory = LColor(0.92, 0.90, 0.82, 1.0)
        tongue_red = LColor(0.85, 0.03, 0.03, 1.0)
        venom_dark = LColor(0.35, 0.04, 0.04, 1.0)
        eye_red = LColor(1.0, 0.25, 0.05, 1.0)
        debris_blueprints = [
            ("deb_serp_head", 0.85, 1.10, 0.50, black_scale, 1, False),
            ("deb_serp_fang", 0.12, 0.38, 0.12, fang_ivory, 2, False),
            ("deb_serp_tongue", 0.18, 0.55, 0.05, tongue_red, 1, True),
            ("deb_serp_seg_big", 0.75, 0.70, 0.48, mid_scale, 6, False),
            ("deb_serp_seg_mid", 0.55, 0.55, 0.36, black_scale, 8, False),
            ("deb_serp_scale", 0.12, 0.14, 0.10, venom_dark, 14, False),
            ("deb_serp_spark", 0.07, 0.07, 0.07, eye_red, 4, True),
        ]
    else:  # witch
        mask_col = LColor(0.10, 0.09, 0.12, 1.0)
        flame_col = LColor(0.95, 0.35, 0.15, 1.0)
        veil_purple = LColor(0.50, 0.14, 0.55, 1.0)
        ash_grey = LColor(0.20, 0.18, 0.22, 1.0)
        ember_col = LColor(1.0, 0.35, 0.12, 1.0)
        spark_purple = LColor(0.85, 0.25, 1.0, 1.0)
        debris_blueprints = [
            ("deb_witch_mask", 0.32, 0.35, 0.35, mask_col, 1, False),
            ("deb_witch_hand", 0.18, 0.18, 0.18, flame_col, 2, True),
            ("deb_witch_veil", 0.24, 0.48, 0.06, veil_purple, 4, False),
            ("deb_witch_core", 0.26, 0.28, 0.22, ash_grey, 4, False),
            ("deb_witch_ember", 0.09, 0.09, 0.09, ember_col, 18, True),
            ("deb_witch_spark", 0.06, 0.06, 0.06, spark_purple, 6, True),
        ]

    debris_list = []
    piece_idx = 0
    for name, sx, sy, sz, col, count, is_spark in debris_blueprints:
        for _ in range(count):
            piece_idx += 1
            node_np = parent.attachNewNode(f"debris_{piece_idx}")
            cube = make_cube(name, sx, sy, sz, col)
            cube.reparentTo(node_np)
            if is_spark:
                cube.setLightOff()

            ox = random.uniform(-0.35, 0.35)
            oy = random.uniform(-0.35, 0.35)
            oz = random.uniform(0.3, 1.8)
            init_pos = Vec3(pos.x + ox, pos.y + oy, pos.z + oz)
            node_np.setPos(init_pos)

            theta = random.uniform(0, math.pi * 2.0)
            if is_spark:
                speed_xy = random.uniform(4.5, 11.5)
                speed_z = random.uniform(3.5, 9.0)
            else:
                speed_xy = random.uniform(2.8, 8.5)
                speed_z = random.uniform(2.5, 7.5)

            vx = math.cos(theta) * speed_xy
            vy = math.sin(theta) * speed_xy
            vz = speed_z

            spin = Vec3(
                random.uniform(-450, 450),
                random.uniform(-450, 450),
                random.uniform(-450, 450)
            )
            rot = Vec3(random.uniform(0, 360), random.uniform(0, 360), random.uniform(0, 360))
            node_np.setHpr(rot)

            life = random.uniform(9.0, 13.0)
            debris_list.append({
                "node": node_np,
                "pos": init_pos,
                "vel": Vec3(vx, vy, vz),
                "rot": rot,
                "spin": spin,
                "timer": life,
                "max_timer": life,
                "settled": False,
                "is_spark": is_spark
            })

    return debris_list, blast_np, puddle


def update_monster_debris_list(debris_list, dt):
    """3D 파편 물리 시뮬레이션: 중력, 탄성 튕김, 회전 및 잔여 수명 페이드아웃"""
    for d in debris_list[:]:
        d["timer"] -= dt
        if d["timer"] <= 0.0:
            if d.get("node") and not d["node"].isEmpty():
                d["node"].removeNode()
            debris_list.remove(d)
            continue

        if not d["settled"]:
            # 중력 적용 (초당 -11.8 m/s^2)
            d["vel"].z -= 11.8 * dt
            d["pos"] += d["vel"] * dt
            d["rot"] += d["spin"] * dt

            # 바닥 충돌 및 탄성 튕김 (Z <= 0.035)
            if d["pos"].z <= 0.035:
                d["pos"].z = 0.035
                d["vel"].z = -d["vel"].z * 0.28  # 반발 계수
                d["vel"].x *= 0.65               # 바닥 마찰
                d["vel"].y *= 0.65
                d["spin"] *= 0.70

                h_speed = math.hypot(d["vel"].x, d["vel"].y)
                if abs(d["vel"].z) < 0.25 and h_speed < 0.20:
                    d["settled"] = True
                    d["vel"] = Vec3(0, 0, 0)
                    d["spin"] = Vec3(0, 0, 0)

            if d.get("node") and not d["node"].isEmpty():
                d["node"].setPos(d["pos"])
                d["node"].setHpr(d["rot"])

        # 수명 종료 1.5초 전부터 바닥으로 서서히 축소되며 자연스럽게 소멸
        if d["timer"] <= 1.5:
            scale = max(0.01, d["timer"] / 1.5)
            if d.get("node") and not d["node"].isEmpty():
                d["node"].setScale(scale)


class LongBlackSerpent:
    """
    몸통이 긴 칠흑의 대사(뱀) 괴물 엔티티
    - 14개의 마디형 세그먼트가 부드럽게 S자 파동(Sinusoidal Undulation)을 그리며 슬리더링
    - 날렵한 뱀 머리, 날름거리는 붉은 갈라진 혀(Forked Tongue), 날카로운 송곳니, 번뜩이는 뱀 안광
    - 바닥을 기어오다가 복도 벽면을 타고 수직으로 기어오르는 Wall-Climbing 물리 지원
    - 핏빛 암흑 오라 라이트
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("long_black_serpent")
        self.pos = Vec3(start_x, start_y, 0.45)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.wall_tilt = 0.0
        self.climb_z = 0.45
        self.stun_timer = 0.0
        self.is_corpse = False
        self.name = "검은 뱀 괴물"
        self.max_hp = 220
        self.hp = self.max_hp
        self.exp_value = 55
        self.attack_damage = 30
        self.speed = 9.0
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        black = LColor(0.015, 0.015, 0.02, 1.0)
        scale_black = LColor(0.025, 0.025, 0.035, 1.0)
        eye_yellow_red = LColor(1.0, 0.25, 0.05, 1.0)
        tongue_red = LColor(0.85, 0.03, 0.03, 1.0)
        fang_ivory = LColor(0.92, 0.90, 0.82, 1.0)

        # 틸트 및 몸체 루트
        self.tilt_root = self.node.attachNewNode("tilt_root")
        self.body_root = self.tilt_root.attachNewNode("body_root")

        # 1. 뱀 머리 (Head - 거대하고 사나운 칠흑의 대사 머리: 폭 1.4m, 길이 1.8m)
        self.head = make_cube('serpent_head', 1.40, 1.80, 0.72, black)
        self.head.setPos(0, 0.40, 0)
        self.head.reparentTo(self.body_root)

        # 머리 상단 비늘 능선 (Crest)
        crest = make_cube('crest', 0.80, 1.40, 0.22, scale_black)
        crest.setPos(0, 0.30, 0.40)
        crest.reparentTo(self.head)

        # 2. 거대한 날카로운 송곳니 (Giant Fangs)
        self.fang_l = make_cube('fang_l', 0.12, 0.16, 0.42, fang_ivory)
        self.fang_l.setPos(-0.38, 1.05, -0.30)
        self.fang_l.setP(22)
        self.fang_l.reparentTo(self.head)

        self.fang_r = make_cube('fang_r', 0.12, 0.16, 0.42, fang_ivory)
        self.fang_r.setPos(0.38, 1.05, -0.30)
        self.fang_r.setP(22)
        self.fang_r.reparentTo(self.head)

        # 3. 날름거리는 거대 붉은 갈라진 혀 (Giant Forked Tongue)
        self.tongue = make_cube('tongue', 0.20, 0.85, 0.05, tongue_red)
        self.tongue.setPos(0, 1.10, -0.12)
        self.tongue.setLightOff()
        self.tongue.reparentTo(self.head)

        # 4. 번뜩이는 거대 뱀 눈 (Slit-pupil Eyes)
        eye_l = make_cube('eye_l', 0.14, 0.12, 0.16, eye_yellow_red)
        eye_l.setPos(-0.52, 0.65, 0.24)
        eye_l.setLightOff()
        eye_l.reparentTo(self.head)

        eye_r = make_cube('eye_r', 0.14, 0.12, 0.16, eye_yellow_red)
        eye_r.setPos(0.52, 0.65, 0.24)
        eye_r.setLightOff()
        eye_r.reparentTo(self.head)

        # 5. 14개의 거대 몸통 마디 (Segmented Undulating Body, 총 연장 ~13.5m 초대형 뱀)
        self.segments = []
        for i in range(14):
            t = i / 13.0
            # 머리 뒤쪽에서 굵어졌다가 꼬리로 갈수록 자연스럽게 가늘어지는 비례
            thickness = math.sin((1.0 - t * 0.85) * math.pi * 0.5)
            sx = 1.30 * thickness
            sy = 1.05 * (1.0 - t * 0.22)
            sz = 0.72 * thickness

            seg_pivot = self.body_root.attachNewNode(f"seg_pivot_{i}")
            seg_pivot.setPos(0, -(i + 1) * 0.92, 0)
            seg_geom = make_cube(f"seg_geom_{i}", max(0.24, sx), max(0.40, sy), max(0.20, sz), black)
            seg_geom.reparentTo(seg_pivot)
            self.segments.append({
                'pivot': seg_pivot,
                'geom': seg_geom,
                'base_y': -(i + 1) * 0.92,
                'idx': i
            })

        # 6. 핏빛 암흑 오라 조명
        aura_light = PointLight('serpent_aura')
        aura_light.setColor((0.95, 0.05, 0.05, 1.0))
        aura_light.setAttenuation((1.0, 0.025, 0.0035))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 0.95)
        parent.setLight(self.aura_np)

    def reset_pos(self, x, y, z=0.45):
        """뱀 위치 및 상태 초기화"""
        self.pos = Vec3(x, y, z)
        self.node.setPos(self.pos)
        self.node.setH(0)
        self.tilt_root.setHpr(0, 0, 0)
        self.wall_tilt = 0.0
        self.climb_z = z
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        for seg in self.segments:
            seg['pivot'].setPos(0, seg['base_y'], 0)
            seg['pivot'].setH(0)

        self.head.setH(0)
        self.head.setP(0)
        self.aura_np.node().setColor((0.95, 0.05, 0.05, 1.0))

    def stun(self, duration=0.5):
        """총격 적중 시 0.5초간 경직/스턴 발동"""
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 1.8, 0.4, 1.0))

    def take_damage(self, dmg):
        """피해 적용 및 사망 여부 반환"""
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 14개 마디와 거대 송곳니/머리통이 사방으로 폭발 파편화"""
        self.is_corpse = True
        self.hp = 0
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        self.climb_z = 0.12
        self.pos.z = 0.12
        self.node.setPos(self.pos)
        self.node.setP(-88)
        self.tilt_root.hide()

        parent = self.node.getParent() if (hasattr(self, 'node') and not self.node.isEmpty() and not self.node.getParent().isEmpty()) else self.node
        self.debris_list, self.blast_light_np, self.puddle_np = create_monster_explosion(parent, self.pos, "serpent", audio_mgr)
        self.blast_timer = 0.14

    def update_debris(self, dt):
        """사망 후 공중 비산 중인 3D 파편 물리 시뮬레이션 및 폭발 섬광 페이드 갱신"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            self.blast_timer -= dt
            if self.blast_timer <= 0.0:
                parent = self.blast_light_np.getParent()
                if not parent.isEmpty():
                    parent.clearLight(self.blast_light_np)
                self.blast_light_np.removeNode()
                self.blast_light_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            update_monster_debris_list(self.debris_list, dt)

    def destroy(self):
        """씬그래프, 조명, 파편 및 혈흔 리소스 완전 해제"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            parent = self.blast_light_np.getParent()
            if not parent.isEmpty():
                parent.clearLight(self.blast_light_np)
            self.blast_light_np.removeNode()
            self.blast_light_np = None
        if hasattr(self, 'puddle_np') and self.puddle_np and not self.puddle_np.isEmpty():
            self.puddle_np.removeNode()
            self.puddle_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            for d in self.debris_list:
                if d.get('node') and not d['node'].isEmpty():
                    d['node'].removeNode()
            self.debris_list = []
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """플레이어 사격 레이캐스트와 뱀 머리/14마디 마디별 충돌 판정"""
        self.last_hit_was_head = False
        # 머리 및 주요 마디들의 월드 좌표 수집 (is_head 플래그 포함)
        targets = [(self.pos.x, self.pos.y, self.pos.z + 0.3, 1.1, True)] # head: radius 1.1m
        h_rad = math.radians(self.node.getH())
        cos_h, sin_h = math.cos(h_rad), math.sin(h_rad)
        for i in range(0, 14, 2):
            seg = self.segments[i]
            by = seg['base_y']
            # 로컬 Y 오프셋을 월드 위치로 변환
            wx = self.pos.x + (-sin_h * by)
            wy = self.pos.y + (cos_h * by)
            targets.append((wx, wy, self.pos.z, 0.95, False))

        for tx, ty, tz, r, is_head in targets:
            vx = tx - ray_o.x
            vy = ty - ray_o.y
            vz = tz - ray_o.z
            t = vx * ray_d.x + vy * ray_d.y + vz * ray_d.z
            if 0.2 < t < max_dist:
                cx = ray_o.x + t * ray_d.x
                cy = ray_o.y + t * ray_d.y
                cz = ray_o.z + t * ray_d.z
                dist_sq = (tx - cx)**2 + (ty - cy)**2 + (tz - cz)**2
                if dist_sq <= r * r:
                    self.last_hit_was_head = is_head
                    return True, t
        return False, 999.0

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y, wall_norm=None, climb_target_z=0.45):
        """위치 갱신 및 벽 타기(Wall Crawling) 슬리더링 물리 적용 (스턴 처리 포함)"""
        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            # 스턴 경직 떨림 효과
            shake = math.sin(self.stun_timer * 65.0) * 0.08
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            self.head.setP(18)
            if self.stun_timer <= 0.0:
                self.aura_np.node().setColor((0.95, 0.05, 0.05, 1.0))
            return

        self.climb_z += (climb_target_z - self.climb_z) * min(1.0, dt * 4.5)
        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = self.climb_z
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))

        # 벽면 법선 기반 몸체 틸트 (Wall Crawling Tilt)
        target_wall_tilt = 1.0 if (wall_norm is not None and self.climb_z > 1.2) else 0.0
        self.wall_tilt += (target_wall_tilt - self.wall_tilt) * min(1.0, dt * 5.0)

        if self.wall_tilt > 0.02 and wall_norm is not None:
            h_rad = math.radians(self.node.getH())
            rgt_x = math.cos(h_rad)
            rgt_y = math.sin(h_rad)
            dot_rgt = wall_norm.x * rgt_x + wall_norm.y * rgt_y
            target_roll = -dot_rgt * 82.0 * self.wall_tilt
            curr_r = self.tilt_root.getR()
            self.tilt_root.setR(curr_r + (target_roll - curr_r) * min(1.0, dt * 6.0))
        else:
            curr_r = self.tilt_root.getR()
            self.tilt_root.setR(curr_r * max(0.0, 1.0 - dt * 6.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """14마디 S자 파동 슬리더링 및 혀 날름거림 애니메이션"""
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.95, 0.05, 0.05, 1.0))

        if is_attacking:
            # 점프스케어 공격 포즈: 머리를 바짝 쳐들고 독니와 혀를 활짝 벌림
            self.head.setP(-35)
            self.head.setZ(0.65)
            self.tongue.setPos(0, 1.65, -0.12)
            self.fang_l.setP(45)
            self.fang_r.setP(45)
            return

        if is_moving:
            self.anim_time += dt * 9.5
            phase = self.anim_time

            # 머리 좌우 위빙(Weaving)
            self.head.setH(math.sin(phase) * 14.0)
            self.head.setP(math.sin(phase * 0.5) * 4.0)
            self.head.setZ(0)

            # 14개 마디 사인파 S자 파동 전파 (Sinusoidal Undulation - 거대한 진폭)
            for seg in self.segments:
                i = seg['idx']
                seg_phase = phase - (i + 1) * 0.48
                # 거대한 몸집에 맞추어 꼬리로 갈수록 파동의 진폭 확장
                amplitude = 0.65 + (i / 14.0) * 0.55
                lateral_x = math.sin(seg_phase) * amplitude
                seg_angle = math.cos(seg_phase) * (26.0 + i * 1.5)

                seg['pivot'].setPos(lateral_x, seg['base_y'], math.sin(seg_phase * 0.5) * 0.08)
                seg['pivot'].setH(seg_angle)

            # 날름거리는 혀 모션
            tongue_flick = 1.10 + abs(math.sin(phase * 2.2)) * 0.45
            self.tongue.setPos(0, tongue_flick, -0.12)
        else:
            # 정지 상태: 서서히 거대 몸체를 사리고 혀를 간헐적으로 날름거림
            t = ClockObject.getGlobalClock().getFrameTime()
            self.head.setH(math.sin(t * 1.8) * 5.0)
            self.head.setP(math.sin(t * 1.2) * 3.0)
            tongue_flick = 1.10 + abs(math.sin(t * 3.5)) * 0.30
            self.tongue.setPos(0, tongue_flick, -0.12)
            for seg in self.segments:
                i = seg['idx']
                seg['pivot'].setPos(math.sin(t * 1.2 + i * 0.3) * 0.20, seg['base_y'], 0)


class TallSkeletonMonster:
    """
    키가 매우 크고 팔이 매우 길며 턱이 쩍 벌어진 기괴한 해골 괴물 엔티티
    - 신장 약 4.2m의 초장신 뼈대 실루엣
    - 발목까지 늘어진 비정상적으로 긴 해골 팔 (~2.7m)
    - 아래턱이 비정상적으로 길게 쩍 벌어진(Unhinged Jaw) 영구적 비명의 두개골
    - 안와 내부에 깊게 박힌 공허한 칠흑의 검은 눈동자 (Void Black Eyes)
    - 드러난 흉곽(갈비뼈), 척추뼈, 골반 및 성큼성큼 걷는 음산한 보행 애니메이션
    - 창백한 청백색 냉기 오라 라이트
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("tall_skeleton_monster")
        self.pos = Vec3(start_x, start_y, 0.0)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.stun_timer = 0.0
        self.is_corpse = False
        self.name = "장신 해골 괴물"
        self.max_hp = 160
        self.hp = self.max_hp
        self.exp_value = 45
        self.attack_damage = 35
        self.speed = 9.5
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        bone_col = LColor(0.85, 0.83, 0.76, 1.0)
        bone_dark = LColor(0.55, 0.52, 0.45, 1.0)
        void_black = LColor(0.002, 0.002, 0.002, 1.0)

        # 몸체 관절 루트
        self.body_root = self.node.attachNewNode("skel_body_root")

        # 1. 골반 (Pelvis - 지상 1.85m 위치)
        self.pelvis = make_cube('pelvis', 0.65, 0.40, 0.38, bone_col)
        self.pelvis.setPos(0, 0, 1.85)
        self.pelvis.reparentTo(self.body_root)

        # 2. 척추뼈 (Spine - 1.85m ~ 3.10m)
        self.spine = make_cube('spine', 0.22, 0.22, 1.25, bone_dark)
        self.spine.setPos(0, 0, 2.50)
        self.spine.reparentTo(self.body_root)

        # 3. 드러난 흉곽 (6쌍의 갈비뼈 Ribcage)
        self.ribs = []
        for r in range(6):
            rib_w = 0.72 - r * 0.04
            rib_geom = make_cube(f"rib_{r}", rib_w, 0.42, 0.09, bone_col)
            rib_geom.setPos(0, 0, 2.15 + r * 0.18)
            rib_geom.reparentTo(self.body_root)
            self.ribs.append(rib_geom)

        # 4. 쇄골 & 어깨 (Shoulders - 3.25m 위치)
        clavicle = make_cube('clavicle', 1.05, 0.26, 0.16, bone_col)
        clavicle.setPos(0, 0, 3.25)
        clavicle.reparentTo(self.body_root)

        # 5. 목 (Neck - 3.25m ~ 3.55m)
        neck = make_cube('neck', 0.18, 0.18, 0.35, bone_dark)
        neck.setPos(0, 0, 3.45)
        neck.reparentTo(self.body_root)

        # 6. 길쭉한 해골 두개골 (Elongated Skull - 중심 고도 3.85m)
        self.skull_pivot = self.body_root.attachNewNode("skull_pivot")
        self.skull_pivot.setPos(0, 0, 3.85)

        cranium = make_cube('cranium', 0.48, 0.54, 0.56, bone_col)
        cranium.setPos(0, 0.05, 0.12)
        cranium.reparentTo(self.skull_pivot)

        # 7. 쩍 벌어진 기괴한 아래턱 (Unhinged Dislocated Jaw)
        self.jaw_pivot = self.skull_pivot.attachNewNode("jaw_pivot")
        self.jaw_pivot.setPos(0, -0.05, -0.15)
        self.jaw_pivot.setP(35) # 영구적으로 길게 쩍 벌어진 턱

        jaw_geom = make_cube('jaw_geom', 0.38, 0.52, 0.26, bone_col)
        jaw_geom.setPos(0, 0.18, -0.12)
        jaw_geom.reparentTo(self.jaw_pivot)

        # 날카로운 치아
        teeth = make_cube('teeth', 0.32, 0.42, 0.12, LColor(0.95, 0.95, 0.88, 1.0))
        teeth.setPos(0, 0.18, 0.04)
        teeth.reparentTo(self.jaw_pivot)

        # 8. 공허한 칠흑의 검은 눈동자 (Void Black Eyes - 안와 내부의 짙은 암흑)
        eye_l = make_cube('void_eye_l', 0.11, 0.06, 0.11, void_black)
        eye_l.setPos(-0.14, 0.30, 0.15)
        eye_l.setLightOff()
        eye_l.reparentTo(self.skull_pivot)

        eye_r = make_cube('void_eye_r', 0.11, 0.06, 0.11, void_black)
        eye_r.setPos(0.14, 0.30, 0.15)
        eye_r.setLightOff()
        eye_r.reparentTo(self.skull_pivot)

        # 9. 비정상적으로 긴 2단 해골 팔 (Long Skeletal Arms - 무릎 넘어 발목까지 도달, 총 연장 ~2.7m)
        self.arms = []
        for side, name in ((-1, "l"), (1, "r")):
            # 어깨 관절
            shoulder = self.body_root.attachNewNode(f"shoulder_{name}")
            shoulder.setPos(side * 0.52, 0, 3.25)

            # 상완 (Humerus: 길이 1.30m)
            upper_arm = shoulder.attachNewNode(f"upper_arm_{name}")
            upper_geom = make_cube(f"upper_geom_{name}", 0.12, 0.12, 1.30, bone_col)
            upper_geom.setPos(0, 0, -0.65)
            upper_geom.reparentTo(upper_arm)

            # 팔꿈치 관절 및 하완 (Forearm / Radius-Ulna: 길이 1.40m, 발목까지 축 늘어짐)
            forearm_pivot = upper_arm.attachNewNode(f"forearm_{name}")
            forearm_pivot.setPos(0, 0, -1.25)
            fore_geom = make_cube(f"fore_geom_{name}", 0.09, 0.09, 1.40, bone_col)
            fore_geom.setPos(0, 0, -0.70)
            fore_geom.reparentTo(forearm_pivot)

            # 길고 날카로운 뼈 손가락 (Claws)
            claw = make_cube(f"claw_{name}", 0.14, 0.10, 0.35, bone_dark)
            claw.setPos(0, 0, -1.45)
            claw.reparentTo(forearm_pivot)

            self.arms.append({
                'shoulder': shoulder,
                'upper': upper_arm,
                'forearm': forearm_pivot,
                'side': side
            })

        # 10. 4.2m 신장을 지탱하는 앙상하고 긴 다리 (Legs - 지상 0m ~ 1.85m)
        self.legs = []
        for side, name in ((-1, "l"), (1, "r")):
            hip = self.body_root.attachNewNode(f"hip_{name}")
            hip.setPos(side * 0.22, 0, 1.85)

            femur = hip.attachNewNode(f"femur_{name}")
            fem_geom = make_cube(f"fem_geom_{name}", 0.14, 0.14, 0.95, bone_col)
            fem_geom.setPos(0, 0, -0.475)
            fem_geom.reparentTo(femur)

            knee = femur.attachNewNode(f"knee_{name}")
            knee.setPos(0, 0, -0.95)
            tibia_geom = make_cube(f"tibia_geom_{name}", 0.12, 0.12, 0.95, bone_col)
            tibia_geom.setPos(0, 0, -0.475)
            tibia_geom.reparentTo(knee)

            self.legs.append({
                'hip': hip,
                'femur': femur,
                'knee': knee,
                'side': side
            })

        # 11. 창백하고 차가운 청백색 냉기 오라 조명
        aura_light = PointLight('skeleton_aura')
        aura_light.setColor((0.15, 0.45, 0.75, 1.0))
        aura_light.setAttenuation((1.0, 0.04, 0.007))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 2.8)
        parent.setLight(self.aura_np)

    def reset_pos(self, x, y, z=0.0):
        """해골 위치 및 상태 초기화"""
        self.pos = Vec3(x, y, z)
        self.node.setPos(self.pos)
        self.node.setH(0)
        self.body_root.setHpr(0, 0, 0)
        self.body_root.setPos(0, 0, 0)
        self.skull_pivot.setHpr(0, 0, 0)
        self.jaw_pivot.setP(35)
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        for arm in self.arms:
            arm['upper'].setP(0)
            arm['forearm'].setP(0)
        for leg in self.legs:
            leg['femur'].setP(0)
            leg['knee'].setP(0)
        self.aura_np.node().setColor((0.35, 0.55, 0.95, 1.0))

    def stun(self, duration=0.5):
        """총격 적중 시 0.5초간 경직/스턴 발동"""
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 2.0, 0.6, 1.0)) # 피격 시 번쩍임
    def take_damage(self, dmg):
        """피해 적용 및 사망 여부 반환"""
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 산산조각 폭발 파편화: 거대 두개골, 갈비뼈, 척추, 사지 장골 및 시안빛 안광 파편이 사방으로 비산"""
        self.is_corpse = True
        self.hp = 0
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.25)
        self.node.setP(-88)
        self.node.setR(12)
        if hasattr(self, 'body_root') and not self.body_root.isEmpty():
            self.body_root.hide()

        parent = self.node.getParent() if (hasattr(self, 'node') and not self.node.isEmpty() and not self.node.getParent().isEmpty()) else self.node
        self.debris_list, self.blast_light_np, self.puddle_np = create_monster_explosion(parent, self.pos, "skeleton", audio_mgr)
        self.blast_timer = 0.14

    def update_debris(self, dt):
        """사망 후 공중 비산 중인 3D 파편 물리 시뮬레이션 및 폭발 섬광 페이드 갱신"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            self.blast_timer -= dt
            if self.blast_timer <= 0.0:
                parent = self.blast_light_np.getParent()
                if not parent.isEmpty():
                    parent.clearLight(self.blast_light_np)
                self.blast_light_np.removeNode()
                self.blast_light_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            update_monster_debris_list(self.debris_list, dt)

    def destroy(self):
        """씬그래프, 조명, 파편 및 혈흔 리소스 완전 해제"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            parent = self.blast_light_np.getParent()
            if not parent.isEmpty():
                parent.clearLight(self.blast_light_np)
            self.blast_light_np.removeNode()
            self.blast_light_np = None
        if hasattr(self, 'puddle_np') and self.puddle_np and not self.puddle_np.isEmpty():
            self.puddle_np.removeNode()
            self.puddle_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            for d in self.debris_list:
                if d.get('node') and not d['node'].isEmpty():
                    d['node'].removeNode()
            self.debris_list = []
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """플레이어 사격 레이캐스트와 4.2m 해골 괴물 전신(두개골, 흉곽, 골반 등) 충돌 판정"""
        self.last_hit_was_head = False
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 3.85, 0.80, True), # 쩍 벌어진 두개골 (헤드샷!)
            (self.pos.x, self.pos.y, self.pos.z + 3.35, 0.70, False), # 쇄골/어깨
            (self.pos.x, self.pos.y, self.pos.z + 2.65, 0.80, False), # 흉곽/갈비뼈
            (self.pos.x, self.pos.y, self.pos.z + 1.85, 0.75, False), # 골반
            (self.pos.x, self.pos.y, self.pos.z + 1.0, 0.70, False), # 하체/다리
        ]
        for tx, ty, tz, r, is_head in targets:
            vx = tx - ray_o.x
            vy = ty - ray_o.y
            vz = tz - ray_o.z
            t = vx * ray_d.x + vy * ray_d.y + vz * ray_d.z
            if 0.2 < t < max_dist:
                cx = ray_o.x + t * ray_d.x
                cy = ray_o.y + t * ray_d.y
                cz = ray_o.z + t * ray_d.z
                dist_sq = (tx - cx)**2 + (ty - cy)**2 + (tz - cz)**2
                if dist_sq <= r * r:
                    self.last_hit_was_head = is_head
                    return True, t
        return False, 999.0

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        """위치 갱신 및 시선 회전 (스턴 처리 포함)"""
        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            # 스턴 경직 떨림 효과
            shake = math.sin(self.stun_timer * 65.0) * 0.08
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            self.skull_pivot.setP(-18)
            self.jaw_pivot.setP(15)
            if self.stun_timer <= 0.0:
                self.aura_np.node().setColor((0.35, 0.55, 0.95, 1.0))
            return

        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = 0.0
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """긴 팔 스윙 및 쩍 벌어진 턱의 덜컹거림 보행 애니메이션"""
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.15, 0.45, 1.0, 1.0))

        if is_attacking:
            # 점프스케어 공격 포즈: 2.7m의 긴 팔을 앞으로 쭉 뻗어 덮치고 턱을 쩍 벌림
            for arm in self.arms:
                arm['upper'].setP(-85)
                arm['forearm'].setP(-25)
            self.jaw_pivot.setP(60) # 턱을 극한으로 쩍 벌림
            self.skull_pivot.setP(22)
            self.body_root.setP(18)
            self.body_root.setZ(0.20)
            return

        if is_moving:
            self.anim_time += dt * 5.8
            phase = self.anim_time

            # 긴 팔이 발목 높이에서 앞뒤로 섬뜩하게 스윙
            for arm in self.arms:
                side = arm['side']
                swing = math.sin(phase) * 38.0 * side
                arm['upper'].setP(swing)
                arm['forearm'].setP(max(0.0, swing * 0.45))

            # 성큼성큼 다리 보행
            for leg in self.legs:
                side = leg['side']
                stride = math.sin(phase) * 28.0 * (-side)
                leg['femur'].setP(stride)
                leg['knee'].setP(max(0.0, -stride * 0.8))

            # 두개골 불규칙 틱 및 턱 떨림
            self.skull_pivot.setH(math.sin(phase * 0.7) * 4.5)
            self.skull_pivot.setR(math.sin(phase * 1.3) * 3.0)
            self.jaw_pivot.setP(35 + math.sin(phase * 2.5) * 8.0) # 덜컹거리는 턱

            # 걸을 때의 상하 리듬
            self.body_root.setZ(abs(math.sin(phase)) * 0.08)
        else:
            # 정지 상태: 음산하게 흔들리는 긴 팔과 불규칙하게 떨리는 턱
            t = ClockObject.getGlobalClock().getFrameTime()
            for arm in self.arms:
                side = arm['side']
                arm['upper'].setP(math.sin(t * 1.5) * 6.0 * side)
            self.jaw_pivot.setP(35 + math.sin(t * 2.2) * 5.0)
            self.skull_pivot.setZ(math.sin(t * 1.8) * 0.03)


class AbominableMudOrc:
    """
    1. 혐오스런 진흙 오크 (Abominable Mud Orc)
    - 진흙과 오물, 이끼로 뒤덮인 거대하고 육중한 야만 오크 괴물 (신장 약 2.6m, 폭 1.6m)
    - 굵은 상체, 진흙 덩어리 견갑(Spaulders), 날카롭게 튀어나온 아래턱 멧돼지 송곳니
    - 번뜩이는 유독성 황록색 안광, 거대한 가시 돋친 암석 몽둥이 (Spiked Stone Club)
    - 쿵쿵 울리는 육중한 보행 모션, 높은 체력(HP 110)과 묵직한 공격력
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("mud_orc")
        self.pos = Vec3(start_x, start_y, 0.0)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        # 땅울림 스킬(Ground Slam) 상태
        self.slam_cooldown = 3.5
        self.is_slamming = False
        self.slam_timer = 0.0
        self.slam_has_impacted = False
        self.is_corpse = False

        self.name = "혐오스런 진흙 오크"
        self.max_hp = 280
        self.hp = self.max_hp
        self.exp_value = 65
        self.attack_damage = 35
        self.speed = 7.6
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        # 색상 팔레트
        mud_skin = LColor(0.25, 0.22, 0.16, 1.0)
        sludge_dark = LColor(0.12, 0.11, 0.08, 1.0)
        moss_green = LColor(0.18, 0.26, 0.14, 1.0)
        toxic_eye = LColor(0.85, 0.98, 0.15, 1.0)
        tusk_ivory = LColor(0.88, 0.85, 0.72, 1.0)
        stone_grey = LColor(0.32, 0.30, 0.28, 1.0)

        self.body_root = self.node.attachNewNode("orc_body_root")

        # 골반
        self.pelvis = make_cube('orc_pelvis', 0.85, 0.65, 0.45, sludge_dark)
        self.pelvis.setPos(0, 0, 0.90)
        self.pelvis.reparentTo(self.body_root)

        # 상체
        self.torso = make_cube('orc_torso', 1.25, 0.85, 0.80, mud_skin)
        self.torso.setPos(0, 0.08, 1.50)
        self.torso.reparentTo(self.body_root)

        moss_crust = make_cube('orc_moss', 1.15, 0.55, 0.25, moss_green)
        moss_crust.setPos(0, -0.18, 1.70)
        moss_crust.reparentTo(self.body_root)

        # 견갑
        for side, name in ((-1, "l"), (1, "r")):
            spaulder = make_cube(f'spaulder_{name}', 0.42, 0.48, 0.38, sludge_dark)
            spaulder.setPos(side * 0.78, 0.08, 1.82)
            spaulder.reparentTo(self.body_root)

        # 머리
        self.head_pivot = self.body_root.attachNewNode("orc_head_pivot")
        self.head_pivot.setPos(0, 0.25, 1.95)

        cranium = make_cube('orc_cranium', 0.58, 0.55, 0.48, mud_skin)
        cranium.setPos(0, 0, 0.12)
        cranium.reparentTo(self.head_pivot)

        jaw = make_cube('orc_jaw', 0.52, 0.45, 0.28, sludge_dark)
        jaw.setPos(0, 0.14, -0.10)
        jaw.reparentTo(self.head_pivot)

        tusk_l = make_cube('orc_tusk_l', 0.10, 0.12, 0.26, tusk_ivory)
        tusk_l.setPos(-0.18, 0.32, 0.06)
        tusk_l.setP(-20)
        tusk_l.reparentTo(self.head_pivot)

        tusk_r = make_cube('orc_tusk_r', 0.10, 0.12, 0.26, tusk_ivory)
        tusk_r.setPos(0.18, 0.32, 0.06)
        tusk_r.setP(-20)
        tusk_r.reparentTo(self.head_pivot)

        eye_l = make_cube('orc_eye_l', 0.10, 0.06, 0.08, toxic_eye)
        eye_l.setPos(-0.16, 0.28, 0.14)
        eye_l.setLightOff()
        eye_l.reparentTo(self.head_pivot)

        eye_r = make_cube('orc_eye_r', 0.10, 0.06, 0.08, toxic_eye)
        eye_r.setPos(0.16, 0.28, 0.14)
        eye_r.setLightOff()
        eye_r.reparentTo(self.head_pivot)

        # 왼팔
        self.arm_l = self.body_root.attachNewNode("orc_arm_l")
        self.arm_l.setPos(-0.75, 0.05, 1.70)
        bicep_l = make_cube('orc_bicep_l', 0.32, 0.35, 0.55, mud_skin)
        bicep_l.setPos(0, 0, -0.25)
        bicep_l.reparentTo(self.arm_l)
        forearm_l = make_cube('orc_forearm_l', 0.34, 0.36, 0.50, sludge_dark)
        forearm_l.setPos(0, 0.08, -0.65)
        forearm_l.reparentTo(self.arm_l)

        # 오른팔 & 몽둥이
        self.arm_r = self.body_root.attachNewNode("orc_arm_r")
        self.arm_r.setPos(0.75, 0.05, 1.70)
        bicep_r = make_cube('orc_bicep_r', 0.32, 0.35, 0.55, mud_skin)
        bicep_r.setPos(0, 0, -0.25)
        bicep_r.reparentTo(self.arm_r)
        self.forearm_r = self.arm_r.attachNewNode("orc_forearm_r")
        self.forearm_r.setPos(0, 0.08, -0.60)
        forearm_mesh = make_cube('orc_forearm_r_mesh', 0.34, 0.36, 0.50, sludge_dark)
        forearm_mesh.reparentTo(self.forearm_r)

        club_handle = make_cube('club_handle', 0.10, 0.10, 1.30, sludge_dark)
        club_handle.setPos(0, 0.20, -0.20)
        club_handle.setP(35)
        club_handle.reparentTo(self.forearm_r)

        club_head = make_cube('club_head', 0.38, 0.38, 0.65, stone_grey)
        club_head.setPos(0, 0.55, 0.30)
        club_head.setP(35)
        club_head.reparentTo(self.forearm_r)

        for sx, sy, sz in ((-0.22, 0.55, 0.30), (0.22, 0.55, 0.30), (0, 0.75, 0.30)):
            spike = make_cube('club_spike', 0.12, 0.12, 0.22, sludge_dark)
            spike.setPos(sx, sy, sz)
            spike.reparentTo(self.forearm_r)

        # 다리
        self.legs = []
        for side, name in ((-1, "l"), (1, "r")):
            hip = self.body_root.attachNewNode(f"orc_hip_{name}")
            hip.setPos(side * 0.38, 0, 0.85)

            thigh = make_cube(f'orc_thigh_{name}', 0.36, 0.40, 0.55, mud_skin)
            thigh.setPos(0, 0, -0.25)
            thigh.reparentTo(hip)

            shin = make_cube(f'orc_shin_{name}', 0.34, 0.38, 0.55, sludge_dark)
            shin.setPos(0, 0.04, -0.65)
            shin.reparentTo(hip)

            foot = make_cube(f'orc_foot_{name}', 0.38, 0.52, 0.20, sludge_dark)
            foot.setPos(0, 0.12, -0.90)
            foot.reparentTo(hip)

            self.legs.append({'hip': hip, 'side': side})

        # 진흙 오크 오라 라이트
        pl = PointLight('mud_orc_aura')
        pl.setColor((0.45, 0.55, 0.12, 1.0))
        pl.setAttenuation((1.0, 0.18, 0.05))
        self.aura_np = self.node.attachNewNode(pl)
        self.aura_np.setPos(0, 0, 1.6)
        parent.setLight(self.aura_np)

    def stun(self, duration=0.5):
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 1.8, 0.4, 1.0))

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 유혈 진흙 폭발 파편화: 오크 머리통, 엄니, 철갑주 파편, 거대한 근육질 팔/다리 살점 덩어리가 사방으로 폭발 분출"""
        self.is_corpse = True
        self.hp = 0
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.28)
        self.node.setP(-86)
        self.node.setR(-15)
        if hasattr(self, 'body_root') and not self.body_root.isEmpty():
            self.body_root.hide()

        parent = self.node.getParent() if (hasattr(self, 'node') and not self.node.isEmpty() and not self.node.getParent().isEmpty()) else self.node
        self.debris_list, self.blast_light_np, self.puddle_np = create_monster_explosion(parent, self.pos, "orc", audio_mgr)
        self.blast_timer = 0.14

    def update_debris(self, dt):
        """사망 후 공중 비산 중인 3D 파편 물리 시뮬레이션 및 폭발 섬광 페이드 갱신"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            self.blast_timer -= dt
            if self.blast_timer <= 0.0:
                parent = self.blast_light_np.getParent()
                if not parent.isEmpty():
                    parent.clearLight(self.blast_light_np)
                self.blast_light_np.removeNode()
                self.blast_light_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            update_monster_debris_list(self.debris_list, dt)

    def destroy(self):
        """씬그래프, 조명, 파편 및 혈흔 리소스 완전 해제"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            parent = self.blast_light_np.getParent()
            if not parent.isEmpty():
                parent.clearLight(self.blast_light_np)
            self.blast_light_np.removeNode()
            self.blast_light_np = None
        if hasattr(self, 'puddle_np') and self.puddle_np and not self.puddle_np.isEmpty():
            self.puddle_np.removeNode()
            self.puddle_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            for d in self.debris_list:
                if d.get('node') and not d['node'].isEmpty():
                    d['node'].removeNode()
            self.debris_list = []
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        self.last_hit_was_head = False
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 2.3, 0.60, True), # 턱/머리 (헤드샷!)
            (self.pos.x, self.pos.y, self.pos.z + 1.8, 0.80, False),
            (self.pos.x, self.pos.y, self.pos.z + 1.0, 0.85, False)
        ]
        for tx, ty, tz, r, is_head in targets:
            vx = tx - ray_o.x
            vy = ty - ray_o.y
            vz = tz - ray_o.z
            t = vx * ray_d.x + vy * ray_d.y + vz * ray_d.z
            if 0.2 < t < max_dist:
                cx = ray_o.x + t * ray_d.x
                cy = ray_o.y + t * ray_d.y
                cz = ray_o.z + t * ray_d.z
                if (tx - cx)**2 + (ty - cy)**2 + (tz - cz)**2 <= r * r:
                    self.last_hit_was_head = is_head
                    return True, t
        return False, 999.0

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            shake = math.sin(self.stun_timer * 60.0) * 0.08
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            if self.stun_timer <= 0.0:
                self.aura_np.node().setColor((0.45, 0.55, 0.12, 1.0))
            return

        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = 0.0
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 8.0))
        self.update(dt, is_moving=True)

    def slam_ground(self, dt):
        """땅을 강하게 내리쳐 지면을 울리고 충격파를 발생시키는 스킬 애니메이션"""
        if not self.is_slamming:
            return False

        self.slam_timer += dt
        # 1단계 (0.0s ~ 0.5s): 양팔과 거대한 돌 몽둥이를 하늘 높이 치켜드는 준비 동작
        if self.slam_timer < 0.5:
            prog = self.slam_timer / 0.5
            self.arm_r.setP(-15 - prog * 95.0)  # -110도까지 번쩍 들어올림
            self.arm_l.setP(-prog * 80.0)
            self.torso.setP(-prog * 18.0)
            return False

        # 2단계 (0.5s): 지면을 쾅! 하고 내리치는 임팩트 순간 (충격파 발생)
        if self.slam_timer >= 0.5 and not self.slam_has_impacted:
            self.arm_r.setP(48)  # 바닥을 향해 수직 강타
            self.arm_l.setP(40)
            self.torso.setP(28)
            self.head_pivot.setP(15)
            self.slam_has_impacted = True
            return True

        # 3단계 (0.5s ~ 1.0s): 여운 및 자세 복귀
        if self.slam_timer >= 1.0:
            self.is_slamming = False
            self.slam_has_impacted = False
            self.slam_timer = 0.0
            self.torso.setP(0)
            self.head_pivot.setP(0)
            self.arm_r.setP(-15)
            self.arm_l.setP(0)

        return False

    def update(self, dt, is_moving, is_attacking=False):
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.45, 0.55, 0.12, 1.0))

        if self.is_slamming:
            return

        if is_attacking:
            self.arm_r.setP(-75)
            self.arm_l.setP(-45)
            self.torso.setP(18)
            return

        if is_moving:
            self.anim_time += dt * 4.6
            phase = self.anim_time

            for leg in self.legs:
                side = leg['side']
                stride = math.sin(phase) * 32.0 * (-side)
                leg['hip'].setP(stride)

            # 팔 몽둥이 스윙
            self.arm_r.setP(math.sin(phase) * 26.0 - 15)
            self.arm_l.setP(-math.sin(phase) * 28.0)
            self.head_pivot.setH(math.sin(phase * 0.8) * 6.0)
            self.body_root.setZ(abs(math.sin(phase)) * 0.09)
        else:
            t = ClockObject.getGlobalClock().getFrameTime()
            self.arm_r.setP(math.sin(t * 1.5) * 5.0 - 10)
            self.head_pivot.setH(math.sin(t * 1.2) * 4.0)


class AlluringAshWitch:
    """
    2. 매혹의 잿더미 마녀 (Alluring Ash Witch)
    - 칠흑과 잿더미 로브를 휘감고 공중에 부유(Levitation)하는 날렵하고 매혹적인 마녀 괴물
    - 챙이 넓고 끝이 뾰족한 클래식 마녀 모자(Witch Hat), 붉은 리본 띠
    - 흩날리는 잿빛 옷자락 밑으로 일렁이는 진홍빛 불씨와 잿더미 파티클 오라
    - 공중 부유 스태프와 붉은 불씨 마력구 (Floating Ember Orb)
    - 날렵한 이동속도(Speed 10.5), 체력 55 HP, 높은 경험치(60 EXP)
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("ash_witch")
        self.pos = Vec3(start_x, start_y, 0.85)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        # 파이어볼 투척(Fireball Cast) 상태
        self.cast_cooldown = 2.2
        self.is_casting = False
        self.cast_timer = 0.0
        self._fireball_fired = False
        self.is_corpse = False

        self.name = "매혹의 잿더미 마녀"
        self.max_hp = 140
        self.hp = self.max_hp
        self.exp_value = 55
        self.attack_damage = 25
        self.speed = 10.5
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        ash_robe = LColor(0.16, 0.15, 0.18, 1.0)
        ember_crimson = LColor(0.95, 0.28, 0.12, 1.0)
        pale_skin = LColor(0.82, 0.80, 0.84, 1.0)
        hat_dark = LColor(0.08, 0.07, 0.10, 1.0)
        eye_ruby = LColor(1.0, 0.12, 0.35, 1.0)
        wood_char = LColor(0.14, 0.12, 0.10, 1.0)

        self.body_root = self.node.attachNewNode("witch_body_root")

        # 1. 로브
        self.skirt_root = self.body_root.attachNewNode("witch_skirt")
        self.skirt_root.setPos(0, 0, 0.6)

        skirt_1 = make_cube('skirt_1', 0.55, 0.50, 0.45, ash_robe)
        skirt_1.setPos(0, 0, 0.2)
        skirt_1.reparentTo(self.skirt_root)

        skirt_2 = make_cube('skirt_2', 0.72, 0.65, 0.50, ash_robe)
        skirt_2.setPos(0, 0, -0.22)
        skirt_2.reparentTo(self.skirt_root)

        skirt_3 = make_cube('skirt_3', 0.90, 0.80, 0.40, ash_robe)
        skirt_3.setPos(0, 0, -0.58)
        skirt_3.reparentTo(self.skirt_root)

        skirt_trim = make_cube('skirt_trim', 0.95, 0.85, 0.08, ember_crimson)
        skirt_trim.setPos(0, 0, -0.75)
        skirt_trim.setLightOff()
        skirt_trim.reparentTo(self.skirt_root)

        # 2. 상체
        self.torso = make_cube('witch_torso', 0.42, 0.32, 0.60, ash_robe)
        self.torso.setPos(0, 0, 1.35)
        self.torso.reparentTo(self.body_root)

        corset = make_cube('witch_corset', 0.44, 0.34, 0.35, ember_crimson)
        corset.setPos(0, 0.02, 1.32)
        corset.reparentTo(self.body_root)

        # 3. 머리 & 마녀 모자
        self.head_pivot = self.body_root.attachNewNode("witch_head_pivot")
        self.head_pivot.setPos(0, 0, 1.82)

        face = make_cube('witch_face', 0.28, 0.26, 0.32, pale_skin)
        face.setPos(0, 0.02, 0.05)
        face.reparentTo(self.head_pivot)

        eye_l = make_cube('witch_eye_l', 0.06, 0.04, 0.06, eye_ruby)
        eye_l.setPos(-0.08, 0.16, 0.08)
        eye_l.setLightOff()
        eye_l.reparentTo(self.head_pivot)

        eye_r = make_cube('witch_eye_r', 0.06, 0.04, 0.06, eye_ruby)
        eye_r.setPos(0.08, 0.16, 0.08)
        eye_r.setLightOff()
        eye_r.reparentTo(self.head_pivot)

        hat_brim = make_cube('hat_brim', 0.95, 0.95, 0.06, hat_dark)
        hat_brim.setPos(0, 0.02, 0.24)
        hat_brim.setP(8)
        hat_brim.reparentTo(self.head_pivot)

        hat_ribbon = make_cube('hat_ribbon', 0.46, 0.46, 0.10, ember_crimson)
        hat_ribbon.setPos(0, 0.02, 0.31)
        hat_ribbon.setP(8)
        hat_ribbon.reparentTo(self.head_pivot)

        hat_cone1 = make_cube('hat_cone1', 0.42, 0.42, 0.28, hat_dark)
        hat_cone1.setPos(0, 0.02, 0.48)
        hat_cone1.setP(8)
        hat_cone1.reparentTo(self.head_pivot)

        hat_cone2 = make_cube('hat_cone2', 0.26, 0.26, 0.28, hat_dark)
        hat_cone2.setPos(0, -0.02, 0.72)
        hat_cone2.setP(18)
        hat_cone2.reparentTo(self.head_pivot)

        hat_tip = make_cube('hat_tip', 0.12, 0.12, 0.25, hat_dark)
        hat_tip.setPos(0, -0.10, 0.92)
        hat_tip.setP(32)
        hat_tip.reparentTo(self.head_pivot)

        # 4. 팔 & 스태프
        self.arm_l = self.body_root.attachNewNode("witch_arm_l")
        self.arm_l.setPos(-0.32, 0, 1.55)
        sleeve_l = make_cube('sleeve_l', 0.16, 0.16, 0.45, ash_robe)
        sleeve_l.setPos(0, 0.08, -0.22)
        sleeve_l.setP(-25)
        sleeve_l.reparentTo(self.arm_l)

        self.arm_r = self.body_root.attachNewNode("witch_arm_r")
        self.arm_r.setPos(0.32, 0, 1.55)
        sleeve_r = make_cube('sleeve_r', 0.16, 0.16, 0.45, ash_robe)
        sleeve_r.setPos(0, 0.08, -0.22)
        sleeve_r.setP(-35)
        sleeve_r.reparentTo(self.arm_r)

        self.staff_node = self.arm_r.attachNewNode("witch_staff")
        self.staff_node.setPos(0.12, 0.42, -0.15)
        staff_rod = make_cube('staff_rod', 0.06, 0.06, 1.65, wood_char)
        staff_rod.reparentTo(self.staff_node)

        self.orb = make_cube('ember_orb', 0.22, 0.22, 0.22, ember_crimson)
        self.orb.setPos(0, 0, 0.90)
        self.orb.setH(45)
        self.orb.setLightOff()
        self.orb.reparentTo(self.staff_node)

        pl = PointLight('ash_witch_aura')
        pl.setColor((1.2, 0.35, 0.18, 1.0))
        pl.setAttenuation((1.0, 0.14, 0.035))
        self.aura_np = self.staff_node.attachNewNode(pl)
        self.aura_np.setPos(0, 0, 0.90)
        parent.setLight(self.aura_np)

    def stun(self, duration=0.5):
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.4, 2.0, 0.6, 1.0))

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 잿더미와 마력 화염 폭발 파편화: 마녀 가면, 찢겨진 베일 리본, 불타는 잿더미 마력 불씨가 사방으로 비산"""
        self.is_corpse = True
        self.hp = 0
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.22)
        self.node.setP(-85)
        self.node.setR(8)
        if hasattr(self, 'body_root') and not self.body_root.isEmpty():
            self.body_root.hide()

        parent = self.node.getParent() if (hasattr(self, 'node') and not self.node.isEmpty() and not self.node.getParent().isEmpty()) else self.node
        self.debris_list, self.blast_light_np, self.puddle_np = create_monster_explosion(parent, self.pos, "witch", audio_mgr)
        self.blast_timer = 0.14

    def update_debris(self, dt):
        """사망 후 공중 비산 중인 3D 파편 물리 시뮬레이션 및 폭발 섬광 페이드 갱신"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            self.blast_timer -= dt
            if self.blast_timer <= 0.0:
                parent = self.blast_light_np.getParent()
                if not parent.isEmpty():
                    parent.clearLight(self.blast_light_np)
                self.blast_light_np.removeNode()
                self.blast_light_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            update_monster_debris_list(self.debris_list, dt)

    def destroy(self):
        """씬그래프, 조명, 파편 및 혈흔 리소스 완전 해제"""
        if hasattr(self, 'blast_light_np') and self.blast_light_np and not self.blast_light_np.isEmpty():
            parent = self.blast_light_np.getParent()
            if not parent.isEmpty():
                parent.clearLight(self.blast_light_np)
            self.blast_light_np.removeNode()
            self.blast_light_np = None
        if hasattr(self, 'puddle_np') and self.puddle_np and not self.puddle_np.isEmpty():
            self.puddle_np.removeNode()
            self.puddle_np = None
        if hasattr(self, 'debris_list') and self.debris_list:
            for d in self.debris_list:
                if d.get('node') and not d['node'].isEmpty():
                    d['node'].removeNode()
            self.debris_list = []
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        self.last_hit_was_head = False
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 2.0, 0.55, True), # 마녀 머리 (헤드샷!)
            (self.pos.x, self.pos.y, self.pos.z + 1.4, 0.55, False),
            (self.pos.x, self.pos.y, self.pos.z + 0.6, 0.65, False)
        ]
        for tx, ty, tz, r, is_head in targets:
            vx = tx - ray_o.x
            vy = ty - ray_o.y
            vz = tz - ray_o.z
            t = vx * ray_d.x + vy * ray_d.y + vz * ray_d.z
            if 0.2 < t < max_dist:
                cx = ray_o.x + t * ray_d.x
                cy = ray_o.y + t * ray_d.y
                cz = ray_o.z + t * ray_d.z
                if (tx - cx)**2 + (ty - cy)**2 + (tz - cz)**2 <= r * r:
                    self.last_hit_was_head = is_head
                    return True, t
        return False, 999.0

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            shake = math.sin(self.stun_timer * 60.0) * 0.08
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            if self.stun_timer <= 0.0:
                self.aura_np.node().setColor((1.2, 0.35, 0.18, 1.0))
            return

        self.pos.x = new_x
        self.pos.y = new_y
        # 공중 부유 높이 진동
        self.pos.z = 0.85 + math.sin(self.anim_time * 2.8) * 0.22
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))
        self.update(dt, is_moving=True)

    def cast_fireball(self, dt):
        """공중에서 스태프를 치켜들고 파이어볼을 시전/발사하는 모션"""
        if not self.is_casting:
            return False

        self.cast_timer += dt
        # 1단계 (0.0s ~ 0.4s): 스태프를 들어올리며 불씨 마력구 팽창
        if self.cast_timer < 0.4:
            prog = self.cast_timer / 0.4
            self.arm_r.setP(-35 - prog * 50.0)
            self.orb.setScale(1.0 + prog * 0.9)
            return False

        # 2단계 (0.4s): 파이어볼 발사 순간
        if self.cast_timer >= 0.4 and not getattr(self, '_fireball_fired', False):
            self._fireball_fired = True
            self.arm_r.setP(-90)
            self.orb.setScale(1.6)
            return True

        # 3단계 (0.4s ~ 0.8s): 후딜레이 및 마력구 정상화
        if self.cast_timer >= 0.8:
            self.is_casting = False
            self._fireball_fired = False
            self.cast_timer = 0.0
            self.orb.setScale(1.0)
            self.arm_r.setP(-35)

        return False

    def update(self, dt, is_moving, is_attacking=False):
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((1.0, 0.25, 0.10, 1.0))

        if self.is_casting:
            return

        self.anim_time += dt * 3.5
        t = self.anim_time

        if is_attacking:
            self.arm_r.setP(-65)
            self.orb.setScale(1.4)
            return

        self.orb.setScale(1.0 + math.sin(t * 5.0) * 0.15)
        # 로브 부유 스웨이
        self.skirt_root.setR(math.sin(t * 2.5) * 8.0)
        self.skirt_root.setP(math.cos(t * 2.2) * 6.0)
        self.staff_node.setZ(-0.15 + math.sin(t * 3.0) * 0.06)
        self.head_pivot.setR(math.sin(t * 1.5) * 4.0)


# 기존 호환용 별칭
CreepySpiderMonster = LongBlackSerpent
TallShadowMonster = TallSkeletonMonster

