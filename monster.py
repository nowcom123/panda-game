import math
import random
from panda3d.core import Vec3, LColor, PointLight, ClockObject
from geometry import make_cube, make_cube_to, make_sphere, make_sphere_to, make_cylinder, make_cylinder_to
from elemental_effects import ElementalMonsterMixin
from elevation import get_floor_height


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
    elif monster_type in ("hound", "hellhound"):
        blast_light.setColor((3.2, 1.2, 0.2, 1.0))
    elif monster_type == "boss":
        blast_light.setColor((4.2, 1.5, 4.5, 1.0))
    else:  # witch
        blast_light.setColor((2.4, 0.6, 2.6, 1.0))
    blast_light.setAttenuation((1.0, 0.20, 0.08))
    blast_np = parent.attachNewNode(blast_light)
    blast_np.setPos(pos.x, pos.y, pos.z + 1.2)
    parent.setLight(blast_np)

    # 2. 바닥 핏자국 노드 (사양상 미사용 슬롯 유지)
    puddle = None

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
        tusk_ivory = LColor(0.92, 0.90, 0.82, 1.0)
        bone_ivory = LColor(0.88, 0.86, 0.78, 1.0)
        bone_dark = LColor(0.58, 0.54, 0.46, 1.0)
        pale_flesh = LColor(0.82, 0.79, 0.74, 1.0)
        hair_col = LColor(0.04, 0.04, 0.05, 1.0)
        splinter_col = LColor(0.72, 0.70, 0.63, 1.0)
        debris_blueprints = [
            ("deb_orc_skull", 0.38, 0.40, 0.36, bone_ivory, 1, False), # 축소된 백골 두개골 파편
            ("deb_orc_jaw", 0.30, 0.28, 0.16, bone_dark, 1, False),    # 하악골 파편
            ("deb_orc_pelvis", 0.46, 0.32, 0.24, bone_ivory, 1, False), # 뼈 골반 파편
            ("deb_orc_rib", 0.10, 0.36, 0.08, bone_ivory, 8, False),   # 백골 갈비뼈 파편 8개
            ("deb_orc_vert", 0.16, 0.16, 0.16, bone_dark, 6, False),   # 척추뼈 마디 파편
            ("deb_orc_limb", 0.14, 0.48, 0.14, bone_ivory, 4, False),  # 뼈 사지 뼈대 파편
            ("deb_orc_trophy_head", 0.36, 0.36, 0.38, pale_flesh, 2, False), # 양손의 사람 머리통 파편
            ("deb_orc_trophy_hair", 0.24, 0.24, 0.20, hair_col, 2, False),
            ("deb_orc_tusk", 0.08, 0.20, 0.08, tusk_ivory, 2, False),  # 엄니 파편
            ("deb_orc_splinter", 0.08, 0.12, 0.08, splinter_col, 14, False), # 뼈 조각 파편
        ]
    elif monster_type == "serpent":
        bone_white = LColor(0.88, 0.86, 0.78, 1.0)
        bone_dark = LColor(0.60, 0.57, 0.49, 1.0)
        fang_ivory = LColor(0.92, 0.90, 0.82, 1.0)
        tongue_red = LColor(0.85, 0.03, 0.03, 1.0)
        splinter_col = LColor(0.72, 0.70, 0.63, 1.0)
        eye_red = LColor(1.0, 0.25, 0.05, 1.0)
        debris_blueprints = [
            ("deb_serp_skull", 0.70, 0.82, 0.50, bone_white, 1, False), # 뱀의 거대 해골 두개골 파편
            ("deb_serp_jaw", 0.52, 0.42, 0.20, bone_dark, 1, False),    # 하악골 파편
            ("deb_serp_rib", 0.10, 0.62, 0.10, bone_white, 8, False),    # 만곡 갈비뼈 뼈대 파편
            ("deb_serp_vert", 0.28, 0.28, 0.24, bone_dark, 6, False),    # 척추뼈 마디 파편
            ("deb_serp_fang", 0.12, 0.38, 0.12, fang_ivory, 2, False),
            ("deb_serp_tongue", 0.18, 0.55, 0.05, tongue_red, 1, True),
            ("deb_serp_splinter", 0.08, 0.14, 0.08, splinter_col, 14, False),
            ("deb_serp_spark", 0.07, 0.07, 0.07, eye_red, 4, True),
        ]
    elif monster_type in ("hound", "hellhound"):
        bone_ivory = LColor(0.88, 0.86, 0.78, 1.0)
        bone_dark = LColor(0.55, 0.52, 0.44, 1.0)
        fang_ivory = LColor(0.95, 0.93, 0.85, 1.0)
        hellfire_core = LColor(1.0, 0.32, 0.08, 1.0)
        claw_dark = LColor(0.20, 0.18, 0.16, 1.0)
        splinter_col = LColor(0.72, 0.70, 0.63, 1.0)
        debris_blueprints = [
            ("deb_hound_skull", 0.32, 0.46, 0.26, bone_ivory, 1, False), # 도베르만 두개골
            ("deb_hound_jaw", 0.20, 0.30, 0.12, bone_dark, 1, False),    # 하악골
            ("deb_hound_ear", 0.06, 0.12, 0.24, bone_dark, 2, False),    # 절단 뼈 귀
            ("deb_hound_rib", 0.08, 0.34, 0.08, bone_ivory, 6, False),   # 흉곽 갈비뼈
            ("deb_hound_spine", 0.14, 0.42, 0.14, bone_dark, 2, False),  # 척추 마디
            ("deb_hound_leg", 0.10, 0.38, 0.10, bone_ivory, 4, False),   # 사지 뼈대
            ("deb_hound_claw", 0.08, 0.12, 0.08, claw_dark, 4, False),   # 발골 발톱
            ("deb_hound_fang", 0.05, 0.15, 0.05, fang_ivory, 4, False),  # 날카로운 송곳니
            ("deb_hound_heart", 0.20, 0.22, 0.20, hellfire_core, 1, True), # 지옥불 심장 코어
            ("deb_hound_splinter", 0.07, 0.10, 0.07, splinter_col, 12, False),
            ("deb_hound_flame", 0.08, 0.08, 0.08, hellfire_core, 8, True),
        ]
    elif monster_type == "boss":
        cable_black = LColor(0.08, 0.08, 0.10, 1.0)
        cable_copper = LColor(0.72, 0.42, 0.18, 1.0)
        neon_cyan = LColor(0.20, 0.90, 1.0, 1.0)
        neon_red = LColor(1.0, 0.20, 0.20, 1.0)
        steel_plate = LColor(0.28, 0.30, 0.34, 1.0)
        debris_blueprints = [
            ("deb_boss_core", 0.55, 0.55, 0.55, neon_cyan, 2, True),
            ("deb_boss_tentacle_coil", 0.22, 0.75, 0.22, cable_black, 8, False),
            ("deb_boss_wire_bundle", 0.18, 0.50, 0.18, cable_copper, 10, False),
            ("deb_boss_armor_shard", 0.45, 0.45, 0.12, steel_plate, 6, False),
            ("deb_boss_spark", 0.10, 0.10, 0.10, neon_red, 16, True),
        ]
    else:  # witch
        melt_sludge = LColor(0.24, 0.14, 0.11, 1.0)
        molten_flesh = LColor(0.85, 0.32, 0.12, 1.0)
        charred_bone = LColor(0.12, 0.11, 0.12, 1.0)
        ember_col = LColor(1.0, 0.35, 0.12, 1.0)
        spark_purple = LColor(0.85, 0.25, 1.0, 1.0)
        debris_blueprints = [
            ("deb_witch_melt_core", 0.30, 0.32, 0.28, molten_flesh, 1, True), # 녹아내린 마그마 코어
            ("deb_witch_charred_rib", 0.08, 0.32, 0.08, charred_bone, 4, False), # 탄 갈비뼈 파편
            ("deb_witch_sludge", 0.26, 0.28, 0.22, melt_sludge, 6, False), # 흘러내리던 슬러지 살점
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


class LongBlackSerpent(ElementalMonsterMixin):
    col_radius = 0.38
    """
    몸통이 긴 칠흑의 대사(뱀) 괴물 엔티티
    - 14개의 마디형 세그먼트가 부드럽게 S자 파동(Sinusoidal Undulation)을 그리며 슬리더링
    - 날렵한 뱀 머리, 날름거리는 붉은 갈라진 혀(Forked Tongue), 날카로운 송곳니, 번뜩이는 뱀 안광
    - 바닥을 기어오다가 복도 벽면을 타고 수직으로 기어오르는 Wall-Climbing 물리 지원
    - 핏빛 암흑 오라 라이트
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("long_black_serpent")
        floor_z, _ = get_floor_height(start_x, start_y)
        self.climb_z = 0.45
        self.pos = Vec3(start_x, start_y, floor_z + self.climb_z)
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
        self.col_radius = 0.38
        self.is_striking = False
        self.strike_timer = 0.0
        self.strike_cooldown = 0.0
        self.strike_has_hit = False
        self.strike_duration = 0.85
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

        # 골격 및 해골 색상 팔레트
        bone_white = LColor(0.88, 0.86, 0.78, 1.0)
        bone_dark = LColor(0.60, 0.57, 0.49, 1.0)
        void_black = LColor(0.005, 0.005, 0.008, 1.0)
        eye_ember = LColor(1.0, 0.22, 0.06, 1.0)

        # 1. 뱀 머리 -> 거대 백골 해골 두개골 (Skeletal Skull Head: 폭 1.25m, 길이 1.45m, 높이 1.10m)
        self.head = make_sphere('serpent_skull_cranium', 1.25, 1.45, 1.10, bone_white)
        self.head.setPos(0, 0.40, 0)
        self.head.reparentTo(self.body_root)

        # 뼈 이마 및 안면 미간 능선
        brow = make_cube('skull_brow', 1.05, 0.40, 0.22, bone_dark)
        brow.setPos(0, 0.74, 0.24)
        brow.reparentTo(self.head)

        # (A) 크고 비어있는 눈동자 / 거대 안와 공동 (Large & Empty Orbital Sockets)
        eye_socket_l = make_sphere('skull_socket_l', 0.40, 0.32, 0.36, void_black)
        eye_socket_l.setPos(-0.36, 0.76, 0.14)
        eye_socket_l.setLightOff()
        eye_socket_l.reparentTo(self.head)

        eye_socket_r = make_sphere('skull_socket_r', 0.40, 0.32, 0.36, void_black)
        eye_socket_r.setPos(0.36, 0.76, 0.14)
        eye_socket_r.setLightOff()
        eye_socket_r.reparentTo(self.head)

        # 안와 외측 및 하단 골성 테두리
        orbit_rim_l = make_cube('orbit_rim_l', 0.12, 0.28, 0.36, bone_white)
        orbit_rim_l.setPos(-0.58, 0.74, 0.14)
        orbit_rim_l.reparentTo(self.head)

        orbit_rim_r = make_cube('orbit_rim_r', 0.12, 0.28, 0.36, bone_white)
        orbit_rim_r.setPos(0.58, 0.74, 0.14)
        orbit_rim_r.reparentTo(self.head)

        orbit_lower_l = make_cube('orbit_lower_l', 0.34, 0.22, 0.12, bone_white)
        orbit_lower_l.setPos(-0.36, 0.76, -0.06)
        orbit_lower_l.reparentTo(self.head)

        orbit_lower_r = make_cube('orbit_lower_r', 0.34, 0.22, 0.12, bone_white)
        orbit_lower_r.setPos(0.36, 0.76, -0.06)
        orbit_lower_r.reparentTo(self.head)

        # (B) 없어진 코뼈 / 배 모양 삼각 비강 결손 공동 (Missing Nasal Bone Void)
        nasal_void = make_cube('skull_nasal_void', 0.24, 0.28, 0.34, void_black)
        nasal_void.setPos(0, 0.84, -0.08)
        nasal_void.setP(-18)
        nasal_void.setLightOff()
        nasal_void.reparentTo(self.head)

        nasal_margin_l = make_cube('nasal_margin_l', 0.06, 0.22, 0.32, bone_dark)
        nasal_margin_l.setPos(-0.13, 0.83, -0.08)
        nasal_margin_l.setP(-18)
        nasal_margin_l.reparentTo(self.head)

        nasal_margin_r = make_cube('nasal_margin_r', 0.06, 0.22, 0.32, bone_dark)
        nasal_margin_r.setPos(0.13, 0.83, -0.08)
        nasal_margin_r.setP(-18)
        nasal_margin_r.reparentTo(self.head)

        nasal_septum = make_cube('skull_nasal_septum', 0.04, 0.22, 0.30, bone_white)
        nasal_septum.setPos(0, 0.82, -0.08)
        nasal_septum.setP(-18)
        nasal_septum.reparentTo(self.head)

        # (C) 구멍 뚫린 볼 / 관골궁 하부 관통 공동 (Perforated / Holed Cheeks)
        zygoma_l = make_cube('skull_zygoma_l', 0.16, 0.55, 0.16, bone_white)
        zygoma_l.setPos(-0.56, 0.58, 0.02)
        zygoma_l.reparentTo(self.head)

        zygoma_r = make_cube('skull_zygoma_r', 0.18, 0.55, 0.16, bone_white)
        zygoma_r.setPos(0.56, 0.58, 0.02)
        zygoma_r.reparentTo(self.head)

        serp_cheek_hole_l = make_cube('serp_cheek_hole_l', 0.22, 0.44, 0.28, void_black)
        serp_cheek_hole_l.setPos(-0.48, 0.52, -0.14)
        serp_cheek_hole_l.setLightOff()
        serp_cheek_hole_l.reparentTo(self.head)

        serp_cheek_hole_r = make_cube('serp_cheek_hole_r', 0.22, 0.44, 0.28, void_black)
        serp_cheek_hole_r.setPos(0.48, 0.52, -0.14)
        serp_cheek_hole_r.setLightOff()
        serp_cheek_hole_r.reparentTo(self.head)

        serp_cheek_rim_l = make_cube('serp_cheek_rim_l', 0.14, 0.12, 0.26, bone_dark)
        serp_cheek_rim_l.setPos(-0.48, 0.28, -0.14)
        serp_cheek_rim_l.reparentTo(self.head)

        serp_cheek_rim_r = make_cube('serp_cheek_rim_r', 0.14, 0.12, 0.26, bone_dark)
        serp_cheek_rim_r.setPos(0.48, 0.28, -0.14)
        serp_cheek_rim_r.reparentTo(self.head)

        # 상악골 치열(치골)
        maxilla = make_cube('skull_maxilla', 0.82, 0.35, 0.20, bone_white)
        maxilla.setPos(0, 0.80, -0.20)
        maxilla.reparentTo(self.head)

        teeth_upper = make_cube('skull_teeth_upper', 0.64, 0.14, 0.08, fang_ivory)
        teeth_upper.setPos(0, 0.86, -0.22)
        teeth_upper.reparentTo(self.head)

        # 2. 해골 턱 사이로 뻗은 거대한 포식 독니 (Giant Bone Fangs)
        self.fang_l = make_cube('fang_l', 0.10, 0.15, 0.42, fang_ivory)
        self.fang_l.setPos(-0.25, 0.88, -0.30)
        self.fang_l.setP(20)
        self.fang_l.reparentTo(self.head)

        self.fang_r = make_cube('fang_r', 0.10, 0.15, 0.42, fang_ivory)
        self.fang_r.setPos(0.25, 0.88, -0.30)
        self.fang_r.setP(20)
        self.fang_r.reparentTo(self.head)

        # 3. 해골 하악골(턱뼈) 및 하치열
        mandible = make_cube('skull_mandible', 0.82, 0.72, 0.22, bone_dark)
        mandible.setPos(0, 0.68, -0.42)
        mandible.setP(12)
        mandible.reparentTo(self.head)

        teeth_lower = make_cube('skull_teeth_lower', 0.56, 0.14, 0.08, fang_ivory)
        teeth_lower.setPos(0, 0.82, -0.34)
        teeth_lower.reparentTo(self.head)

        # 4. 해골 입안에서 날름거리는 핏빛 갈라진 혀 (Giant Forked Tongue)
        self.tongue = make_cube('tongue', 0.18, 0.85, 0.05, tongue_red)
        self.tongue.setPos(0, 0.95, -0.28)
        self.tongue.setLightOff()
        self.tongue.reparentTo(self.head)

        # 후두골 뼈 능선 (Occipital Bone Crest)
        crest = make_cube('skull_crest', 0.95, 0.45, 0.28, bone_dark)
        crest.setPos(0, -0.20, 0.42)
        crest.reparentTo(self.head)

        # 5. 14개의 거대 백골 척추 마디 및 만곡 갈비뼈 흉곽 (Skeletal Bone Vertebrae & Arched Ribs, 총 연장 ~13.5m)
        self.segments = []
        for i in range(14):
            t = i / 13.0
            thickness = math.sin((1.0 - t * 0.85) * math.pi * 0.5)

            seg_pivot = self.body_root.attachNewNode(f"seg_pivot_{i}")
            seg_pivot.setPos(0, -(i + 1) * 0.92, 0)

            # 중심 척추뼈 기둥 (Vertebral Centrum)
            vw = max(0.32, 0.48 * thickness)
            vl = max(0.42, 0.68 * (1.0 - t * 0.2))
            vh = max(0.24, 0.36 * thickness)
            vert_core = make_cube(f"vert_core_{i}", vw, vl, vh, bone_white)
            vert_core.reparentTo(seg_pivot)

            # 등 척추 극돌기 뼈 가시 (Dorsal Spinous Process)
            sp_h = max(0.18, 0.36 * thickness)
            sp_l = max(0.16, 0.32 * (1.0 - t * 0.2))
            vert_spine = make_cube(f"vert_sp_{i}", max(0.08, 0.11 * thickness), sp_l, sp_h, bone_dark)
            vert_spine.setPos(0, 0, vh * 0.5 + sp_h * 0.5)
            vert_spine.reparentTo(seg_pivot)

            # 몸체 상부~중부 (0~10번 마디): 좌우로 활처럼 굽어 내부를 감싸는 만곡 갈비뼈(Ribcage Bones)
            if i < 11:
                rib_w = max(0.36, 0.68 * thickness)
                rib_l = max(0.10, 0.16 * (1.0 - t * 0.2))
                rib_drop = max(0.20, 0.40 * thickness)
                rib_thick = max(0.065, 0.095 * thickness)

                # 좌측 갈비뼈
                rib_l_top = make_cube(f"rib_lt_{i}", rib_w, rib_l, rib_thick, bone_white)
                rib_l_top.setPos(-vw * 0.5 - rib_w * 0.45, 0, 0.03)
                rib_l_top.setR(24)
                rib_l_top.reparentTo(seg_pivot)

                rib_l_tip = make_cube(f"rib_lb_{i}", rib_thick, rib_l, rib_drop, bone_dark)
                rib_l_tip.setPos(-vw * 0.5 - rib_w * 0.88, 0, -rib_drop * 0.42)
                rib_l_tip.reparentTo(seg_pivot)

                # 우측 갈비뼈
                rib_r_top = make_cube(f"rib_rt_{i}", rib_w, rib_l, rib_thick, bone_white)
                rib_r_top.setPos(vw * 0.5 + rib_w * 0.45, 0, 0.03)
                rib_r_top.setR(-24)
                rib_r_top.reparentTo(seg_pivot)

                rib_r_tip = make_cube(f"rib_rb_{i}", rib_thick, rib_l, rib_drop, bone_dark)
                rib_r_tip.setPos(vw * 0.5 + rib_w * 0.88, 0, -rib_drop * 0.42)
                rib_r_tip.reparentTo(seg_pivot)
            else:
                # 꼬리 마디 (11~13번): 날카로운 후방 꼬리 뼈 가시 (Tail Bone Spurs)
                spur_w = max(0.14, 0.26 * thickness)
                spur_l = make_cube(f"tail_spur_l_{i}", spur_w, 0.18, 0.08, bone_dark)
                spur_l.setPos(-vw * 0.5 - spur_w * 0.45, -0.05, 0)
                spur_l.setH(25)
                spur_l.reparentTo(seg_pivot)

                spur_r = make_cube(f"tail_spur_r_{i}", spur_w, 0.18, 0.08, bone_dark)
                spur_r.setPos(vw * 0.5 + spur_w * 0.45, -0.05, 0)
                spur_r.setH(-25)
                spur_r.reparentTo(seg_pivot)

            self.segments.append({
                'pivot': seg_pivot,
                'geom': vert_core,
                'base_y': -(i + 1) * 0.92,
                'idx': i
            })

        # 6. 핏빛 암흑 오라 조명
        self.parent_ref = parent
        self.aura_is_lit = False
        aura_light = PointLight('serpent_aura')
        aura_light.setColor((0.95, 0.05, 0.05, 1.0))
        aura_light.setAttenuation((1.0, 0.025, 0.0035))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 0.95)

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
        self.is_striking = False
        self.strike_timer = 0.0
        self.strike_cooldown = 0.0
        self.strike_has_hit = False

        for seg in self.segments:
            seg['pivot'].setPos(0, seg['base_y'], 0)
            seg['pivot'].setH(0)

        self.head.setPos(0, 0.40, 0)
        self.head.setH(0)
        self.head.setP(0)
        self.aura_np.node().setColor((0.95, 0.05, 0.05, 1.0))

    def stun(self, duration=0.20):
        """총격 적중 시 0.20초간 경직/스턴 발동 (공격 모션 즉각 캔슬)"""
        self.stun_timer = duration
        self.is_striking = False
        self.strike_timer = 0.0
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 1.8, 0.4, 1.0))

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """피해 적용 및 사망 여부 반환 (기본 넉백 확률 적용)"""
        self.hp = max(0, self.hp - dmg)
        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        if apply_knockback is None:
            apply_knockback = (random.random() < 0.28)

        if apply_knockback:
            self.stun(0.20)
            if hit_dir is not None:
                self.pos.x += hit_dir.x * 0.28
                self.pos.y += hit_dir.y * 0.28
                self.node.setPos(self.pos)
        else:
            if hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((1.6, 1.0, 0.3, 1.0))

        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 14개 마디와 거대 송곳니/머리통이 사방으로 폭발 파편화"""
        self.is_corpse = True
        self.is_striking = False
        self.hp = 0
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
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
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
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
        """플레이어 사격 레이캐스트와 뱀 머리/14마디 마디별 충돌 판정 (기립 시 머리 높이 실시간 반영)"""
        self.last_hit_was_head = False
        h_rad = math.radians(self.node.getH())
        cos_h, sin_h = math.cos(h_rad), math.sin(h_rad)
        s = self.node.getScale()[0] if hasattr(self, 'node') and self.node and not self.node.isEmpty() else (1.25 if getattr(self, 'is_elite', False) else 1.0)

        head_z = self.head.getZ() if hasattr(self, 'head') and not self.head.isEmpty() else 0.0
        head_y = self.head.getY() if hasattr(self, 'head') and not self.head.isEmpty() else 0.40
        head_wx = self.pos.x + (-sin_h * (head_y * s))
        head_wy = self.pos.y + (cos_h * (head_y * s))
        targets = [(head_wx, head_wy, self.pos.z + (head_z + 0.35) * s, 1.15 * s, True)]

        for i in range(0, 14, 2):
            seg = self.segments[i]
            by = seg['pivot'].getY() if (hasattr(seg['pivot'], 'getY')) else seg['base_y']
            bz = seg['pivot'].getZ() if (hasattr(seg['pivot'], 'getZ')) else 0.0
            wx = self.pos.x + (-sin_h * (by * s))
            wy = self.pos.y + (cos_h * (by * s))
            targets.append((wx, wy, self.pos.z + bz * s, 0.95 * s, False))

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

    def strike_attack(self, dt):
        """
        몸 상부(머리 및 0~4번 마디)를 높이 치켜세워 코브라처럼 기립 후 전방 급습 찌르기 공격
        반환값: impact_hit (피격 순간 1회 True 반환)
        - 0.0s ~ 0.40s: [기립 위빙 (Rearing Up)] 머리와 목 5개 마디가 2.25m 높이로 솟구치며 사납게 기립, 턱을 쩍 벌리고 독니 돌출
        - 0.40s ~ 0.58s: [전방 돌진 강타 (Lunge Strike)] 상체를 전방으로 용수철처럼 내던지며 지면/플레이어를 향해 급강하 타격
        - 0.58s ~ 0.85s: [착지 및 회복 (Recovery)] 지면으로 부드럽게 상체를 복귀시키며 슬리더링 자세로 전환
        """
        if self.stun_timer > 0.0:
            self.is_striking = False
            return False

        self.strike_timer += dt
        t = self.strike_timer
        impact_hit = False

        # Phase 1: 0.0s ~ 0.40s [상체 기립 위빙 (Rearing Up)]
        if t < 0.40:
            p = t / 0.40
            rear = math.sin(p * math.pi * 0.5)
            # 머리 치켜들기 (최대 Z = 2.25m, 뒤로 살짝 젖힘)
            self.head.setZ(0.40 + rear * 1.85)
            self.head.setY(0.40 - rear * 0.45)
            self.head.setP(-rear * 28.0)
            self.head.setH(math.sin(t * 16.0) * (rear * 12.0))

            # 0~4번 마디 S자 곡선 수직 기립 (목과 상체 기립)
            seg_weights = [1.0, 0.85, 0.65, 0.40, 0.18]
            seg_pitches = [-22.0, -16.0, -8.0, 6.0, 12.0]
            for i in range(5):
                seg = self.segments[i]
                w = seg_weights[i]
                z_target = rear * w * 1.70
                y_offset = rear * w * 0.35
                h_weave = math.sin(t * 12.0 - i * 0.5) * (rear * 8.0)
                seg['pivot'].setPos(h_weave, seg['base_y'] + y_offset, z_target)
                seg['pivot'].setP(rear * seg_pitches[i])

            # 5~13번 마디: 지면 앵커
            for i in range(5, 14):
                seg = self.segments[i]
                seg['pivot'].setPos(math.sin(t * 5.0 + i * 0.3) * 0.22, seg['base_y'], 0)
                seg['pivot'].setP(0)

            # 독니 돌출 및 혀 날름거림
            self.fang_l.setP(22.0 + rear * 26.0)
            self.fang_r.setP(22.0 + rear * 26.0)
            tongue_flick = 1.10 + rear * 0.65 + abs(math.sin(t * 26.0)) * 0.40
            self.tongue.setPos(0, tongue_flick, -0.12)

        # Phase 2: 0.40s ~ 0.58s [전방 급습 돌진 강타 (Lunge Strike)]
        elif t < 0.58:
            sp = (t - 0.40) / 0.18
            # 머리 전방 급강하 찌르기 (Z: 2.25m -> 0.70m, Y: -0.05m -> 1.55m)
            self.head.setZ(2.25 - sp * 1.55)
            self.head.setY(-0.05 + sp * 1.60)
            self.head.setP(-28.0 + sp * 66.0)
            self.head.setH(0)

            # 상체 마디들이 머리의 돌진을 따라 전방으로 뻗어감
            seg_drop = [1.15, 0.95, 0.70, 0.42, 0.20]
            seg_thrust = [1.25, 0.95, 0.65, 0.38, 0.16]
            for i in range(5):
                seg = self.segments[i]
                base_z = [1.70, 1.45, 1.10, 0.68, 0.31][i]
                seg['pivot'].setPos(0, seg['base_y'] + seg_thrust[i] * sp, base_z - seg_drop[i] * sp)
                seg['pivot'].setP(math.sin(sp * math.pi) * 25.0)

            # 타격 판정 타이밍 (0.47초 ~ 0.52초)
            if t >= 0.47 and not self.strike_has_hit:
                self.strike_has_hit = True
                impact_hit = True

            self.fang_l.setP(48.0)
            self.fang_r.setP(48.0)
            self.tongue.setPos(0, 1.85, -0.12)

        # Phase 3: 0.58s ~ 0.85s [회복 및 지면 슬리더링 복귀 (Recovery)]
        else:
            rp = min(1.0, (t - 0.58) / 0.27)
            inv_rp = 1.0 - rp
            self.head.setZ(0.70 * inv_rp)
            self.head.setY(1.55 - rp * 1.15)
            self.head.setP(38.0 * inv_rp)
            self.head.setH(0)

            for i in range(5):
                seg = self.segments[i]
                seg['pivot'].setPos(0, seg['base_y'] + (1.25 - i * 0.25) * inv_rp, 0.55 * inv_rp)
                seg['pivot'].setP(20.0 * inv_rp)

            self.fang_l.setP(22.0 + 26.0 * inv_rp)
            self.fang_r.setP(22.0 + 26.0 * inv_rp)
            self.tongue.setPos(0, 1.10 + 0.75 * inv_rp, -0.12)

            if t >= 0.85:
                self.is_striking = False
                self.strike_timer = 0.0
                self.strike_has_hit = False
                self.head.setPos(0, 0.40, 0)
                self.head.setP(0)
                for seg in self.segments:
                    seg['pivot'].setPos(0, seg['base_y'], 0)
                    seg['pivot'].setP(0)

        return impact_hit

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

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.climb_z += (climb_target_z - self.climb_z) * min(1.0, dt * 4.5)
        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = floor_z + self.climb_z
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
        self.update_elemental(dt)
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.95, 0.05, 0.05, 1.0))

        if is_attacking:
            # 점프스케어/공격 태세: 몸 상부(머리 및 0~4번 마디)를 2.25m 높이로 치켜세우고 독니와 혀를 활짝 벌림
            self.head.setP(-28)
            self.head.setZ(2.25)
            self.head.setY(-0.05)
            self.tongue.setPos(0, 1.75, -0.12)
            self.fang_l.setP(48)
            self.fang_r.setP(48)

            seg_heights = [1.70, 1.45, 1.10, 0.68, 0.31]
            seg_pitches = [-22.0, -16.0, -8.0, 6.0, 12.0]
            for i in range(5):
                seg = self.segments[i]
                seg['pivot'].setPos(0, seg['base_y'] + 0.35, seg_heights[i])
                seg['pivot'].setP(seg_pitches[i])
            for i in range(5, 14):
                seg = self.segments[i]
                seg['pivot'].setPos(0, seg['base_y'], 0)
                seg['pivot'].setP(0)
            return

        if is_moving:
            self.anim_time += dt * 9.5
            phase = self.anim_time

            # 머리 좌우 위빙(Weaving)
            self.head.setH(math.sin(phase) * 14.0)
            self.head.setP(math.sin(phase * 0.5) * 4.0)
            self.head.setZ(0)
            self.head.setY(0.40)
            self.fang_l.setP(22)
            self.fang_r.setP(22)

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
                seg['pivot'].setP(0)

            # 날름거리는 혀 모션
            tongue_flick = 1.10 + abs(math.sin(phase * 2.2)) * 0.45
            self.tongue.setPos(0, tongue_flick, -0.12)
        else:
            # 정지 상태: 서서히 거대 몸체를 사리고 혀를 간헐적으로 날름거림
            t = ClockObject.getGlobalClock().getFrameTime()
            self.head.setH(math.sin(t * 1.8) * 5.0)
            self.head.setP(math.sin(t * 1.2) * 3.0)
            self.head.setZ(0)
            self.head.setY(0.40)
            self.fang_l.setP(22)
            self.fang_r.setP(22)
            tongue_flick = 1.10 + abs(math.sin(t * 3.5)) * 0.30
            self.tongue.setPos(0, tongue_flick, -0.12)
            for seg in self.segments:
                i = seg['idx']
                seg['pivot'].setPos(math.sin(t * 1.2 + i * 0.3) * 0.20, seg['base_y'], 0)
                seg['pivot'].setP(0)


class TallSkeletonMonster(ElementalMonsterMixin):
    col_radius = 0.40
    """
    비정상적으로 긴 두 팔로 바닥을 기어 다니며 턱이 쩍 벌어진 기괴한 해골 보행 괴물 엔티티
    - 두 다리를 뒤로 꺾어 치켜든 채, 2.7m에 달하는 거대한 두 팔로 바닥을 짚고 성큼성큼 기어 다니는 암 워커(Arm-Crawler) 형태
    - 아래턱이 비정상적으로 길게 쩍 벌어진(Unhinged Jaw) 영구적 비명의 두개골 (전방을 섬뜩하게 응시)
    - 안와 내부에 깊게 박힌 공허한 칠흑의 검은 눈동자 (Void Black Eyes)
    - 드러난 흉곽(갈비뼈), 척추뼈, 비틀린 채 공중에 들린 골반과 역관절 다리
    - 창백한 청백색 냉기 오라 라이트
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("tall_skeleton_monster")
        floor_z, _ = get_floor_height(start_x, start_y)
        self.pos = Vec3(start_x, start_y, floor_z)
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
        self.col_radius = 0.40
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        bone_col = LColor(0.85, 0.83, 0.76, 1.0)
        bone_dark = LColor(0.55, 0.52, 0.45, 1.0)
        void_black = LColor(0.002, 0.002, 0.002, 1.0)

        # 몸체 관절 루트 (신장 3.2m 이상의 압도적인 장신 실루엣을 유지하며 거대한 팔로 바닥을 짚는 포스처)
        self.body_root = self.node.attachNewNode("skel_body_root")
        self.body_root.setP(28)
        self.body_root.setPos(0, 0.20, -0.22)

        # 1. 골반 (Pelvis)
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

        # 4. 쇄골 & 어깨 (Shoulders - 지상 2.70m의 거대한 높이 유지)
        clavicle = make_cube('clavicle', 1.15, 0.28, 0.16, bone_col)
        clavicle.setPos(0, 0, 3.25)
        clavicle.reparentTo(self.body_root)

        # 5. 목 (Neck - 3.25m ~ 3.55m)
        neck = make_cube('neck', 0.18, 0.18, 0.35, bone_dark)
        neck.setPos(0, 0, 3.45)
        neck.reparentTo(self.body_root)

        # 6. 길쭉한 해골 두개골 (Elongated Skull - 고도 3.2m에서 플레이어를 위압적으로 내려다봄)
        self.skull_pivot = self.body_root.attachNewNode("skull_pivot")
        self.skull_pivot.setPos(0, 0, 3.85)
        self.skull_pivot.setP(-28)

        # (A) 두개골 본체 및 이마 뼈대 (Cranium & Forehead)
        cranium = make_sphere('cranium', 0.46, 0.48, 0.52, bone_col)
        cranium.setPos(0, 0.04, 0.14)
        cranium.reparentTo(self.skull_pivot)

        forehead = make_sphere('skel_forehead', 0.42, 0.20, 0.20, bone_col)
        forehead.setPos(0, 0.20, 0.26)
        forehead.reparentTo(self.skull_pivot)

        # 돌출된 안와 상단 눈썹 뼈 능선 (Supraorbital Brow Ridge)
        brow = make_cube('skel_brow', 0.46, 0.16, 0.08, bone_dark)
        brow.setPos(0, 0.28, 0.23)
        brow.reparentTo(self.skull_pivot)

        # (B) 크고 비어있는 눈동자 / 안와 공동 (Large & Empty Hollow Orbital Sockets)
        # 안구 없이 뻥 뚫린 거대한 칠흑빛 안와 구멍
        eye_socket_l = make_sphere('skel_socket_l', 0.16, 0.22, 0.20, void_black)
        eye_socket_l.setPos(-0.13, 0.24, 0.12)
        eye_socket_l.setLightOff()
        eye_socket_l.reparentTo(self.skull_pivot)

        eye_socket_r = make_sphere('skel_socket_r', 0.16, 0.22, 0.20, void_black)
        eye_socket_r.setPos(0.13, 0.24, 0.12)
        eye_socket_r.setLightOff()
        eye_socket_r.reparentTo(self.skull_pivot)

        # 안와 외측 및 하단 뼈 테두리 (Orbital Rims)
        orbit_rim_l = make_cube('orbit_rim_l', 0.05, 0.14, 0.20, bone_col)
        orbit_rim_l.setPos(-0.23, 0.26, 0.12)
        orbit_rim_l.reparentTo(self.skull_pivot)

        orbit_rim_r = make_cube('orbit_rim_r', 0.05, 0.14, 0.20, bone_col)
        orbit_rim_r.setPos(0.23, 0.26, 0.12)
        orbit_rim_r.reparentTo(self.skull_pivot)

        orbit_lower_l = make_cube('orbit_lower_l', 0.15, 0.12, 0.05, bone_col)
        orbit_lower_l.setPos(-0.13, 0.28, 0.01)
        orbit_lower_l.reparentTo(self.skull_pivot)

        orbit_lower_r = make_cube('orbit_lower_r', 0.15, 0.12, 0.05, bone_col)
        orbit_lower_r.setPos(0.13, 0.28, 0.01)
        orbit_lower_r.reparentTo(self.skull_pivot)

        glabella = make_cube('glabella', 0.08, 0.14, 0.18, bone_col)
        glabella.setPos(0, 0.28, 0.14)
        glabella.reparentTo(self.skull_pivot)

        # (C) 없어진 코뼈 / 배 모양 삼각 비강 결손 공동 (Missing Nasal Bone Void)
        # 코뼈가 완전히 소실되어 뻥 뚫려있는 역삼각형 암흑 비강 구멍
        nasal_void = make_cube('skel_nasal_void', 0.11, 0.22, 0.18, void_black)
        nasal_void.setPos(0, 0.27, -0.04)
        nasal_void.setP(-15)
        nasal_void.setLightOff()
        nasal_void.reparentTo(self.skull_pivot)

        nasal_edge_l = make_cube('nasal_edge_l', 0.035, 0.12, 0.16, bone_dark)
        nasal_edge_l.setPos(-0.065, 0.27, -0.04)
        nasal_edge_l.setP(-15)
        nasal_edge_l.reparentTo(self.skull_pivot)

        nasal_edge_r = make_cube('nasal_edge_r', 0.035, 0.12, 0.16, bone_dark)
        nasal_edge_r.setPos(0.065, 0.27, -0.04)
        nasal_edge_r.setP(-15)
        nasal_edge_r.reparentTo(self.skull_pivot)

        nasal_vomer = make_cube('nasal_vomer', 0.02, 0.14, 0.14, bone_dark)
        nasal_vomer.setPos(0, 0.25, -0.04)
        nasal_vomer.reparentTo(self.skull_pivot)

        # (D) 구멍 뚫린 볼 / 관골 하부 관통 공동 (Perforated / Holed Cheeks)
        # 광대뼈 아치(Zygomatic Arch) 아래 볼 부위가 뻥 뚫린 기괴한 해골 구조
        zygoma_l = make_cube('skel_zygoma_l', 0.06, 0.36, 0.07, bone_col)
        zygoma_l.setPos(-0.23, 0.14, 0.01)
        zygoma_l.reparentTo(self.skull_pivot)

        zygoma_r = make_cube('skel_zygoma_r', 0.06, 0.36, 0.07, bone_col)
        zygoma_r.setPos(0.23, 0.14, 0.01)
        zygoma_r.reparentTo(self.skull_pivot)

        cheek_hole_l = make_cube('skel_cheek_hole_l', 0.09, 0.26, 0.18, void_black)
        cheek_hole_l.setPos(-0.20, 0.16, -0.10)
        cheek_hole_l.setLightOff()
        cheek_hole_l.reparentTo(self.skull_pivot)

        cheek_hole_r = make_cube('skel_cheek_hole_r', 0.09, 0.26, 0.18, void_black)
        cheek_hole_r.setPos(0.20, 0.16, -0.10)
        cheek_hole_r.setLightOff()
        cheek_hole_r.reparentTo(self.skull_pivot)

        cheek_rim_back_l = make_cube('cheek_rim_back_l', 0.06, 0.06, 0.18, bone_dark)
        cheek_rim_back_l.setPos(-0.20, 0.02, -0.10)
        cheek_rim_back_l.reparentTo(self.skull_pivot)

        cheek_rim_back_r = make_cube('cheek_rim_back_r', 0.06, 0.06, 0.18, bone_dark)
        cheek_rim_back_r.setPos(0.20, 0.02, -0.10)
        cheek_rim_back_r.reparentTo(self.skull_pivot)

        # 상악골 (Maxilla) 및 상치열
        maxilla = make_cube('skel_maxilla', 0.26, 0.20, 0.14, bone_col)
        maxilla.setPos(0, 0.27, -0.13)
        maxilla.reparentTo(self.skull_pivot)

        upper_teeth = make_cube('skel_upper_teeth', 0.24, 0.10, 0.06, LColor(0.95, 0.95, 0.88, 1.0))
        upper_teeth.setPos(0, 0.30, -0.18)
        upper_teeth.reparentTo(self.skull_pivot)

        # 7. 쩍 벌어진 기괴한 아래턱 (Unhinged Dislocated Jaw & Lower Teeth)
        self.jaw_pivot = self.skull_pivot.attachNewNode("jaw_pivot")
        self.jaw_pivot.setPos(0, -0.05, -0.15)
        self.jaw_pivot.setP(35) # 영구적으로 길게 쩍 벌어진 턱

        jaw_geom = make_cube('jaw_geom', 0.34, 0.48, 0.22, bone_col)
        jaw_geom.setPos(0, 0.18, -0.12)
        jaw_geom.reparentTo(self.jaw_pivot)

        # 날카로운 하악 치아
        teeth = make_cube('teeth', 0.30, 0.38, 0.10, LColor(0.95, 0.95, 0.88, 1.0))
        teeth.setPos(0, 0.18, 0.03)
        teeth.reparentTo(self.jaw_pivot)

        # 9. 바닥을 짚고 걷는 비정상적으로 긴 해골 팔 (Long Skeletal Walking Arms - 총 연장 ~2.7m)
        self.arms = []
        for side, name in ((-1, "l"), (1, "r")):
            shoulder = self.body_root.attachNewNode(f"shoulder_{name}")
            shoulder.setPos(side * 0.65, 0.10, 3.25)

            # 상완 (Humerus: 길이 1.30m)
            upper_arm = shoulder.attachNewNode(f"upper_arm_{name}")
            upper_geom = make_cylinder(f"upper_geom_{name}", 0.14, 0.14, 1.30, bone_col)
            upper_geom.setPos(0, 0, -0.65)
            upper_geom.reparentTo(upper_arm)

            # 팔꿈치 관절 및 하완 (Forearm: 길이 1.40m, 바닥을 정확히 지탱)
            forearm_pivot = upper_arm.attachNewNode(f"forearm_{name}")
            forearm_pivot.setPos(0, 0, -1.25)
            fore_geom = make_cube(f"fore_geom_{name}", 0.11, 0.11, 1.40, bone_col)
            fore_geom.setPos(0, 0, -0.70)
            fore_geom.reparentTo(forearm_pivot)

            # 바닥을 움켜쥐는 뼈 손가락 갈퀴 (Claws - 바닥 위 접지 보장)
            claw = make_cube(f"claw_{name}", 0.18, 0.16, 0.35, bone_dark)
            claw.setPos(0, 0, -1.45)
            claw.reparentTo(forearm_pivot)

            # 초기 팔 자세 (지면 위 접지 자세)
            upper_arm.setP(-24)
            forearm_pivot.setP(22)

            self.arms.append({
                'shoulder': shoulder,
                'upper': upper_arm,
                'forearm': forearm_pivot,
                'side': side
            })

        # 10. 공중에 뒤틀린 채 끌려다니는 역관절 다리 (Contorted Trailing Hind Legs)
        self.legs = []
        for side, name in ((-1, "l"), (1, "r")):
            hip = self.body_root.attachNewNode(f"hip_{name}")
            hip.setPos(side * 0.26, 0, 1.85)

            femur = hip.attachNewNode(f"femur_{name}")
            fem_geom = make_cube(f"fem_geom_{name}", 0.13, 0.13, 0.95, bone_col)
            fem_geom.setPos(0, 0, -0.475)
            fem_geom.reparentTo(femur)

            knee = femur.attachNewNode(f"knee_{name}")
            knee.setPos(0, 0, -0.95)
            tibia_geom = make_cylinder(f"tibia_geom_{name}", 0.11, 0.11, 0.95, bone_col)
            tibia_geom.setPos(0, 0, -0.475)
            tibia_geom.reparentTo(knee)

            # 뒤틀린 역관절 초기 각도
            femur.setP(-45)
            knee.setP(75)

            self.legs.append({
                'hip': hip,
                'femur': femur,
                'knee': knee,
                'side': side
            })

        # 11. 창백하고 차가운 청백색 냉기 오라 조명
        self.parent_ref = parent
        self.aura_is_lit = False
        aura_light = PointLight('skeleton_aura')
        aura_light.setColor((0.15, 0.45, 0.75, 1.0))
        aura_light.setAttenuation((1.0, 0.05, 0.010))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0.1, 2.5)

    def reset_pos(self, x, y, z=0.0):
        """해골 위치 및 상태 초기화"""
        self.pos = Vec3(x, y, z)
        self.node.setPos(self.pos)
        self.node.setH(0)
        self.body_root.setHpr(0, 28, 0)
        self.body_root.setPos(0, 0.20, -0.22)
        self.skull_pivot.setHpr(0, -28, 0)
        self.jaw_pivot.setP(35)
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        for arm in self.arms:
            arm['upper'].setP(-24)
            arm['forearm'].setP(22)
        for leg in self.legs:
            leg['femur'].setP(-45)
            leg['knee'].setP(75)
        self.aura_np.node().setColor((0.35, 0.55, 0.95, 1.0))

    def stun(self, duration=0.20):
        """총격 적중 시 0.20초간 경직/스턴 발동 (과도한 무한 경직 완화)"""
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 2.0, 0.6, 1.0))

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """피해 적용 및 사망 여부 반환 (기본 넉백 확률 적용)"""
        self.hp = max(0, self.hp - dmg)
        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        if apply_knockback is None:
            apply_knockback = (random.random() < 0.28)

        if apply_knockback:
            self.stun(0.20)
            if hit_dir is not None:
                self.pos.x += hit_dir.x * 0.28
                self.pos.y += hit_dir.y * 0.28
                self.node.setPos(self.pos)
        else:
            if hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((1.8, 1.4, 0.5, 1.0))

        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 산산조각 폭발 파편화: 거대 두개골, 갈비뼈, 척추, 사지 장골 및 시안빛 안광 파편이 사방으로 비산"""
        self.is_corpse = True
        self.hp = 0
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
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
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
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

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=65.0):
        """플레이어 사격 레이캐스트와 3.2m 장신 암 워커 해골 괴물 충돌 판정"""
        self.last_hit_was_head = False
        h_rad = math.radians(self.node.getH())
        sin_h, cos_h = math.sin(h_rad), math.cos(h_rad)
        s = self.node.getScale()[0] if hasattr(self, 'node') and self.node and not self.node.isEmpty() else (1.25 if getattr(self, 'is_elite', False) else 1.0)

        # 실제 노드 좌표(skull_pivot)를 동적으로 참조하여 3.2m 상체 피치/애니메이션 및 회전/스케일과 100% 일치
        if hasattr(self, 'skull_pivot') and self.skull_pivot and not self.skull_pivot.isEmpty():
            head_y = self.skull_pivot.getY(self.node)
            head_z = self.skull_pivot.getZ(self.node)
        else:
            head_y = -1.607
            head_z = 3.179

        head_wx = self.pos.x - sin_h * (head_y * s)
        head_wy = self.pos.y + cos_h * (head_y * s)
        head_wz = self.pos.z + (head_z + 0.12) * s

        # 3.2m 높이의 위압적인 장신 실루엣에 맞춘 히트박스 좌표 (실제 몸체 피치 각도 반영)
        targets = [
            # 쩍 벌어진 두개골 (헤드샷! - skull_pivot 동적 연동, 반경 0.75m)
            (head_wx, head_wy, head_wz, 0.75 * s, True),
            # 쇄골 & 어깨 (상체 상단)
            (self.pos.x - sin_h * (-1.30 * s), self.pos.y + cos_h * (-1.30 * s), self.pos.z + 2.65 * s, 0.70 * s, False),
            # 흉곽 & 갈비뼈 (상체 중심)
            (self.pos.x - sin_h * (-0.95 * s), self.pos.y + cos_h * (-0.95 * s), self.pos.z + 2.00 * s, 0.75 * s, False),
            # 골반 & 하체 (후방)
            (self.pos.x - sin_h * (-0.65 * s), self.pos.y + cos_h * (-0.65 * s), self.pos.z + 1.40 * s, 0.70 * s, False),
            # 바닥을 짚는 두 팔 & 손
            (self.pos.x - sin_h * (-1.15 * s), self.pos.y + cos_h * (-1.15 * s), self.pos.z + 0.60 * s, 0.80 * s, False),
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
            self.skull_pivot.setP(-15)
            self.jaw_pivot.setP(15)
            if self.stun_timer <= 0.0:
                self.aura_np.node().setColor((0.35, 0.55, 0.95, 1.0))
            return

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.pos.x = new_x
        self.pos.y = new_y
        if self.pos.z < floor_z:
            self.pos.z = floor_z
        elif self.pos.z > floor_z:
            self.pos.z = max(floor_z, self.pos.z - dt * 24.0)
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))

        target_p = 14.0 if s_type == 'ramp' else 0.0
        curr_p = self.node.getP()
        self.node.setP(curr_p + (target_p - curr_p) * min(1.0, dt * 8.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """2.7m의 긴 팔로 바닥을 짚고 쇄도하는 암 워커(Arm-Walking) 기괴 보행 애니메이션 (바닥 관통 0%)"""
        self.update_elemental(dt)
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.15, 0.45, 1.0, 1.0))

        if is_attacking:
            # 한 팔로 지면을 지탱하고 다른 2.7m 팔을 크게 치켜들어 덮치는 점프스케어 공격
            self.arms[0]['upper'].setP(-75)
            self.arms[0]['forearm'].setP(-20)
            self.arms[1]['upper'].setP(15)
            self.arms[1]['forearm'].setP(40)
            self.jaw_pivot.setP(65) # 턱을 극한으로 쩍 벌림
            self.skull_pivot.setP(-15)
            self.body_root.setP(22)
            self.body_root.setZ(-0.10)
            return

        if is_moving:
            self.anim_time += dt * 6.0
            phase = self.anim_time

            # 2.7m의 긴 두 팔로 바닥을 교대로 짚고 당기며 전진 (Arm Walking Cycle - 지면 위 접지 보장)
            for arm in self.arms:
                side = arm['side']
                stride = math.sin(phase) * side
                if stride >= 0:
                    # 지면 접지 및 밀어내기 단계 (Z: 0.03m ~ 0.15m 지면 바로 위 슬라이딩)
                    up_p = -24.0 - stride * 20.0
                    fore_p = 22.0 - stride * 12.0
                else:
                    # 전방 도약 및 다음 발 짚기 준비 단계 (Z: 0.50m ~ 1.00m 높이로 들어올림)
                    up_p = -24.0 - stride * 22.0
                    fore_p = 22.0 + abs(stride) * 20.0
                arm['upper'].setP(up_p)
                arm['forearm'].setP(fore_p)

            # 뒤틀린 채 뒤따르는 역관절 다리의 음산한 흔들림
            for leg in self.legs:
                side = leg['side']
                leg['femur'].setP(-45.0 + math.sin(phase * 0.8 + side) * 12.0)
                leg['knee'].setP(75.0 + math.sin(phase * 1.2) * 10.0)

            # 3.2m 거대한 상체와 척추의 위압적인 스웨이 및 바운스
            self.body_root.setP(28.0 + math.cos(phase * 2.0) * 2.5)
            self.body_root.setR(math.sin(phase) * 6.5)
            self.body_root.setZ(-0.22 + abs(math.cos(phase)) * 0.08)

            # 3.2m 높이에서 내려다보며 덜컹거리는 두개골 틱 모션
            self.skull_pivot.setP(-28.0 + math.sin(phase * 1.5) * 4.0)
            self.skull_pivot.setH(math.sin(phase * 0.7) * 6.0)
            self.skull_pivot.setR(math.sin(phase * 1.2) * 4.0)
            self.jaw_pivot.setP(35 + math.sin(phase * 2.8) * 10.0) # 덜컹거리는 턱
        else:
            # 정지 상태: 양팔을 바닥에 짚고 가르릉거리며 턱을 미세하게 떨림
            t = ClockObject.getGlobalClock().getFrameTime()
            for arm in self.arms:
                arm['upper'].setP(-24.0 + math.sin(t * 1.6) * 3.0)
                arm['forearm'].setP(22.0)
            self.body_root.setP(28.0)
            self.body_root.setR(0)
            self.body_root.setZ(-0.22)
            self.skull_pivot.setP(-28.0 + math.sin(t * 1.4) * 3.0)
            self.jaw_pivot.setP(35 + math.sin(t * 2.5) * 5.0)


class AbominableMudOrc(ElementalMonsterMixin):
    col_radius = 0.45
    """
    1. 혐오스런 진흙 오크 (Abominable Mud Orc)
    - 진흙과 오물, 이끼로 뒤덮인 거대하고 육중한 야만 오크 괴물 (신장 약 2.6m, 폭 1.6m)
    - 굵은 상체, 진흙 덩어리 견갑(Spaulders), 날카롭게 튀어나온 아래턱 멧돼지 송곳니
    - 번뜩이는 유독성 황록색 안광, 거대한 가시 돋친 암석 몽둥이 (Spiked Stone Club)
    - 쿵쿵 울리는 육중한 보행 모션, 높은 체력(HP 110)과 묵직한 공격력
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("mud_orc")
        floor_z, _ = get_floor_height(start_x, start_y)
        self.pos = Vec3(start_x, start_y, floor_z)
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

        self.name = "뼈박살 오크"
        self.max_hp = 280
        self.hp = self.max_hp
        self.col_radius = 0.45
        self.exp_value = 65
        self.attack_damage = 35
        self.speed = 7.6
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        # 색상 팔레트 (전신 뼈 재질 팔레트)
        bone_ivory = LColor(0.88, 0.86, 0.78, 1.0)
        bone_white = LColor(0.92, 0.90, 0.82, 1.0)
        bone_dark = LColor(0.58, 0.54, 0.46, 1.0)
        bone_joint = LColor(0.68, 0.64, 0.55, 1.0)
        void_black = LColor(0.005, 0.005, 0.008, 1.0)
        tusk_ivory = LColor(0.92, 0.90, 0.82, 1.0)

        self.body_root = self.node.attachNewNode("orc_body_root")

        # 1. 전신 뼈 골반 (Massive Skeletal Pelvis)
        self.pelvis = self.body_root.attachNewNode("orc_pelvis")
        self.pelvis.setPos(0, 0, 0.90)

        # 천골(Sacrum) 척추 기저부
        sacrum = make_cube('orc_sacrum', 0.32, 0.22, 0.38, bone_dark)
        sacrum.setPos(0, -0.12, 0)
        sacrum.reparentTo(self.pelvis)

        # 좌우 거대 장골익(Ilium Pelvic Wings)
        ilium_l = make_cube('orc_ilium_l', 0.16, 0.46, 0.36, bone_ivory)
        ilium_l.setPos(-0.36, 0.02, 0.04)
        ilium_l.setR(12)
        ilium_l.reparentTo(self.pelvis)

        ilium_r = make_cube('orc_ilium_r', 0.16, 0.46, 0.36, bone_ivory)
        ilium_r.setPos(0.36, 0.02, 0.04)
        ilium_r.setR(-12)
        ilium_r.reparentTo(self.pelvis)

        # 전면 치골 결합 아치(Pubis)
        pubis = make_cube('orc_pubis', 0.44, 0.12, 0.14, bone_ivory)
        pubis.setPos(0, 0.16, -0.10)
        pubis.reparentTo(self.pelvis)

        # 2. 전신 뼈 토르소 (Skeletal Vertebral Column & Arched Ribcage)
        self.torso = self.body_root.attachNewNode("orc_torso_pivot")
        self.torso.setPos(0, 0.08, 1.50)

        # 굵은 척추 중심 기둥 (Massive Segmented Vertebral Column)
        spine_core = make_cube('orc_spine_core', 0.18, 0.20, 0.84, bone_dark)
        spine_core.setPos(0, -0.06, 0)
        spine_core.reparentTo(self.torso)

        # 등 뒤로 돌출된 척추 극돌기 가시들 (Dorsal Spinous Processes)
        for s in range(4):
            z_sp = 0.30 - s * 0.20
            spike = make_cube(f'orc_spine_spike_{s}', 0.06, 0.14, 0.08, bone_ivory)
            spike.setPos(0, -0.20, z_sp)
            spike.setP(-15)
            spike.reparentTo(self.torso)

        # 거대한 만곡 갈비뼈 흉곽 (5쌍의 백골 늑골)
        for r in range(5):
            z_rib = 0.28 - r * 0.14
            rib_len = 0.36 - r * 0.02
            # 좌측 갈비뼈
            rib_l = make_cube(f'orc_rib_l_{r}', rib_len, 0.09, 0.08, bone_ivory)
            rib_l.setPos(-0.20, 0.16, z_rib)
            rib_l.setR(18)
            rib_l.setP(-8)
            rib_l.reparentTo(self.torso)
            # 우측 갈비뼈
            rib_r = make_cube(f'orc_rib_r_{r}', rib_len, 0.09, 0.08, bone_ivory)
            rib_r.setPos(0.20, 0.16, z_rib)
            rib_r.setR(-18)
            rib_r.setP(-8)
            rib_r.reparentTo(self.torso)

        # 전면 흉골 뼈판 (Sternum)
        sternum = make_cube('orc_sternum', 0.12, 0.08, 0.50, bone_white)
        sternum.setPos(0, 0.26, 0.02)
        sternum.reparentTo(self.torso)

        # 흉곽 내부의 칠흑빛 공허 공동 (Hollow Thoracic Cavity)
        chest_void = make_cube('orc_chest_void', 0.44, 0.28, 0.68, void_black)
        chest_void.setPos(0, 0.04, 0)
        chest_void.setLightOff()
        chest_void.reparentTo(self.torso)

        # 쇄골 (Clavicles)
        clavicle_l = make_cube('orc_clavicle_l', 0.38, 0.10, 0.08, bone_ivory)
        clavicle_l.setPos(-0.30, 0.16, 0.38)
        clavicle_l.setR(10)
        clavicle_l.reparentTo(self.torso)

        clavicle_r = make_cube('orc_clavicle_r', 0.38, 0.10, 0.08, bone_ivory)
        clavicle_r.setPos(0.30, 0.16, 0.38)
        clavicle_r.setR(-10)
        clavicle_r.reparentTo(self.torso)

        # 후방 견갑골 뼈 날개 (Scapula Blades)
        scapula_l = make_cube('orc_scapula_l', 0.26, 0.08, 0.36, bone_dark)
        scapula_l.setPos(-0.36, -0.16, 0.24)
        scapula_l.setR(8)
        scapula_l.reparentTo(self.torso)

        scapula_r = make_cube('orc_scapula_r', 0.26, 0.08, 0.36, bone_dark)
        scapula_r.setPos(0.36, -0.16, 0.24)
        scapula_r.setR(-8)
        scapula_r.reparentTo(self.torso)

        # 거대한 뼈 어깨 구관절 (Shoulder Ball Joints)
        for side, name in ((-1, "l"), (1, "r")):
            shoulder_socket = make_sphere(f'shoulder_socket_{name}', 0.24, 0.24, 0.24, bone_ivory)
            shoulder_socket.setPos(side * 0.72, 0.06, 1.76)
            shoulder_socket.reparentTo(self.body_root)

        # 3. 머리 -> 적절한 비율로 축소되고 귀/뿔이 제거된 순수 백골 두개골 (Proportional Hornless Beast Skull)
        self.head_pivot = self.body_root.attachNewNode("orc_head_pivot")
        self.head_pivot.setPos(0, 0.20, 1.95)

        # 두개골 본체 (체형에 맞춘 균형 잡힌 크기: 폭 0.38m, 깊이 0.40m, 높이 0.36m)
        cranium = make_sphere('orc_skull_cranium', 0.38, 0.40, 0.36, bone_ivory)
        cranium.setPos(0, 0, 0.10)
        cranium.reparentTo(self.head_pivot)

        forehead = make_sphere('orc_forehead', 0.34, 0.18, 0.14, bone_ivory)
        forehead.setPos(0, 0.16, 0.18)
        forehead.reparentTo(self.head_pivot)

        # 돌출된 안와 상단 눈썹 뼈 능선 (Supraorbital Brow Ridge)
        skull_brow = make_cube('orc_skull_brow', 0.38, 0.14, 0.07, bone_dark)
        skull_brow.setPos(0, 0.22, 0.16)
        skull_brow.reparentTo(self.head_pivot)

        # (A) 크고 비어있는 눈동자 / 야수 안와 공동 (Large & Empty Hollow Beast Orbital Sockets)
        socket_l = make_cube('orc_socket_l', 0.14, 0.18, 0.16, void_black)
        socket_l.setPos(-0.11, 0.18, 0.10)
        socket_l.setLightOff()
        socket_l.reparentTo(self.head_pivot)

        socket_r = make_cube('orc_socket_r', 0.14, 0.18, 0.16, void_black)
        socket_r.setPos(0.11, 0.18, 0.10)
        socket_r.setLightOff()
        socket_r.reparentTo(self.head_pivot)

        orc_orbit_rim_l = make_cube('orc_orbit_rim_l', 0.04, 0.12, 0.14, bone_ivory)
        orc_orbit_rim_l.setPos(-0.18, 0.18, 0.10)
        orc_orbit_rim_l.reparentTo(self.head_pivot)

        orc_orbit_rim_r = make_cube('orc_orbit_rim_r', 0.04, 0.12, 0.14, bone_ivory)
        orc_orbit_rim_r.setPos(0.18, 0.18, 0.10)
        orc_orbit_rim_r.reparentTo(self.head_pivot)

        orc_orbit_lower_l = make_cube('orc_orbit_lower_l', 0.12, 0.12, 0.04, bone_ivory)
        orc_orbit_lower_l.setPos(-0.11, 0.19, 0.02)
        orc_orbit_lower_l.reparentTo(self.head_pivot)

        orc_orbit_lower_r = make_cube('orc_orbit_lower_r', 0.12, 0.12, 0.04, bone_ivory)
        orc_orbit_lower_r.setPos(0.11, 0.19, 0.02)
        orc_orbit_lower_r.reparentTo(self.head_pivot)

        glabella = make_cube('orc_glabella', 0.06, 0.10, 0.12, bone_ivory)
        glabella.setPos(0, 0.20, 0.11)
        glabella.reparentTo(self.head_pivot)

        # (B) 없어진 코뼈 / 배 모양 삼각 비강 결손 공동 (Missing Nasal Bone Void)
        nasal = make_cube('orc_nasal_cavity', 0.08, 0.14, 0.14, void_black)
        nasal.setPos(0, 0.21, 0.00)
        nasal.setP(-15)
        nasal.setLightOff()
        nasal.reparentTo(self.head_pivot)

        orc_nasal_margin_l = make_cube('orc_nasal_margin_l', 0.025, 0.10, 0.12, bone_dark)
        orc_nasal_margin_l.setPos(-0.05, 0.20, 0.00)
        orc_nasal_margin_l.setP(-15)
        orc_nasal_margin_l.reparentTo(self.head_pivot)

        orc_nasal_margin_r = make_cube('orc_nasal_margin_r', 0.025, 0.10, 0.12, bone_dark)
        orc_nasal_margin_r.setPos(0.05, 0.20, 0.00)
        orc_nasal_margin_r.setP(-15)
        orc_nasal_margin_r.reparentTo(self.head_pivot)

        # (C) 구멍 뚫린 볼 / 관골궁 하부 관통 공동 (Perforated / Holed Cheeks)
        zygoma_l = make_cube('orc_zygoma_l', 0.05, 0.26, 0.06, bone_ivory)
        zygoma_l.setPos(-0.19, 0.10, 0.02)
        zygoma_l.reparentTo(self.head_pivot)

        zygoma_r = make_cube('orc_zygoma_r', 0.05, 0.26, 0.06, bone_ivory)
        zygoma_r.setPos(0.19, 0.10, 0.02)
        zygoma_r.reparentTo(self.head_pivot)

        orc_cheek_hole_l = make_cube('orc_cheek_hole_l', 0.07, 0.18, 0.13, void_black)
        orc_cheek_hole_l.setPos(-0.16, 0.10, -0.06)
        orc_cheek_hole_l.setLightOff()
        orc_cheek_hole_l.reparentTo(self.head_pivot)

        orc_cheek_hole_r = make_cube('orc_cheek_hole_r', 0.07, 0.18, 0.13, void_black)
        orc_cheek_hole_r.setPos(0.16, 0.10, -0.06)
        orc_cheek_hole_r.setLightOff()
        orc_cheek_hole_r.reparentTo(self.head_pivot)

        cheek_rim_back_l = make_cube('orc_cheek_rim_back_l', 0.04, 0.05, 0.13, bone_dark)
        cheek_rim_back_l.setPos(-0.16, 0.00, -0.06)
        cheek_rim_back_l.reparentTo(self.head_pivot)

        cheek_rim_back_r = make_cube('orc_cheek_rim_back_r', 0.04, 0.05, 0.13, bone_dark)
        cheek_rim_back_r.setPos(0.16, 0.00, -0.06)
        cheek_rim_back_r.reparentTo(self.head_pivot)

        # 상악골 (Maxilla) 및 상치열
        maxilla = make_cube('orc_maxilla', 0.22, 0.16, 0.10, bone_ivory)
        maxilla.setPos(0, 0.20, -0.08)
        maxilla.reparentTo(self.head_pivot)

        upper_teeth = make_cube('orc_upper_teeth', 0.20, 0.08, 0.05, bone_white)
        upper_teeth.setPos(0, 0.22, -0.12)
        upper_teeth.reparentTo(self.head_pivot)

        # 쩍 벌어진 해골 하악골(턱뼈)
        jaw = make_cube('orc_skull_jaw', 0.32, 0.32, 0.16, bone_dark)
        jaw.setPos(0, 0.10, -0.13)
        jaw.reparentTo(self.head_pivot)

        # 하악 해골 치열
        teeth = make_cube('orc_skull_teeth', 0.24, 0.10, 0.06, bone_white)
        teeth.setPos(0, 0.20, -0.07)
        teeth.reparentTo(self.head_pivot)

        # 해골 턱에서 솟아난 날카로운 뼈 엄니 (Predatory Tusks)
        tusk_l = make_cube('orc_tusk_l', 0.06, 0.07, 0.18, bone_white)
        tusk_l.setPos(-0.11, 0.23, 0.01)
        tusk_l.setP(-18)
        tusk_l.reparentTo(self.head_pivot)

        tusk_r = make_cube('orc_tusk_r', 0.06, 0.07, 0.18, bone_white)
        tusk_r.setPos(0.11, 0.23, 0.01)
        tusk_r.setP(-18)
        tusk_r.reparentTo(self.head_pivot)

        # (귀/뿔 완전 제거: orc_horn_l, orc_horn_r 제거됨)

        # 4. 전신 뼈 왼팔 & 뼈 손가락 (Skeletal Left Arm & Fingers)
        self.arm_l = self.body_root.attachNewNode("orc_arm_l")
        self.arm_l.setPos(-0.75, 0.05, 1.70)

        # 상완골 (Humerus)
        humerus_l = make_cylinder('orc_humerus_l', 0.18, 0.18, 0.52, bone_ivory)
        humerus_l.setPos(0, 0, -0.26)
        humerus_l.reparentTo(self.arm_l)

        # 팔꿈치 관절 (Elbow Joint)
        elbow_l = make_sphere('orc_elbow_l', 0.20, 0.20, 0.16, bone_dark)
        elbow_l.setPos(0, 0.02, -0.52)
        elbow_l.reparentTo(self.arm_l)

        # 전완 이중 뼈 (Radius & Ulna)
        radius_l = make_cylinder('orc_radius_l', 0.09, 0.09, 0.44, bone_ivory)
        radius_l.setPos(-0.06, 0.06, -0.74)
        radius_l.reparentTo(self.arm_l)

        ulna_l = make_cylinder('orc_ulna_l', 0.09, 0.09, 0.44, bone_ivory)
        ulna_l.setPos(0.06, 0.06, -0.74)
        ulna_l.reparentTo(self.arm_l)

        # 손목 및 뼈 주먹/손가락 (Carpals & Bone Fingers)
        wrist_l = make_cube('orc_wrist_l', 0.18, 0.18, 0.10, bone_dark)
        wrist_l.setPos(0, 0.08, -0.96)
        wrist_l.reparentTo(self.arm_l)

        bone_hand_l = make_cube('orc_bone_hand_l', 0.24, 0.24, 0.18, bone_ivory)
        bone_hand_l.setPos(0, 0.12, -1.04)
        bone_hand_l.reparentTo(self.arm_l)

        # 왼손에 들린 참수된 사람 머리 (머리칼을 쥐고 있음)
        pale_dead_flesh = LColor(0.82, 0.79, 0.74, 1.0)
        gore_crimson = LColor(0.42, 0.05, 0.05, 1.0)
        hair_black = LColor(0.04, 0.04, 0.05, 1.0)
        eye_dead = LColor(0.28, 0.25, 0.24, 1.0)

        hair_grasp_l = make_sphere('hair_grasp_l', 0.28, 0.30, 0.22, hair_black)
        hair_grasp_l.setPos(0, 0.14, -1.02)
        hair_grasp_l.reparentTo(self.arm_l)

        trophy_head_l = make_sphere('trophy_head_l', 0.36, 0.38, 0.42, pale_dead_flesh)
        trophy_head_l.setPos(0, 0.16, -1.25)
        trophy_head_l.reparentTo(self.arm_l)

        trophy_face_l = make_cube('trophy_face_l', 0.32, 0.18, 0.34, pale_dead_flesh)
        trophy_face_l.setPos(0, 0.34, -1.25)
        trophy_face_l.reparentTo(self.arm_l)

        trophy_eye_l1 = make_sphere('trophy_eye_l1', 0.08, 0.04, 0.06, eye_dead)
        trophy_eye_l1.setPos(-0.09, 0.43, -1.20)
        trophy_eye_l1.reparentTo(self.arm_l)

        trophy_eye_l2 = make_sphere('trophy_eye_l2', 0.08, 0.04, 0.06, eye_dead)
        trophy_eye_l2.setPos(0.09, 0.43, -1.20)
        trophy_eye_l2.reparentTo(self.arm_l)

        trophy_nose_l = make_cube('trophy_nose_l', 0.08, 0.10, 0.14, pale_dead_flesh)
        trophy_nose_l.setPos(0, 0.44, -1.25)
        trophy_nose_l.reparentTo(self.arm_l)

        trophy_mouth_l = make_cube('trophy_mouth_l', 0.16, 0.06, 0.08, gore_crimson)
        trophy_mouth_l.setPos(0, 0.43, -1.34)
        trophy_mouth_l.reparentTo(self.arm_l)

        trophy_neck_l = make_cube('trophy_neck_l', 0.22, 0.22, 0.12, gore_crimson)
        trophy_neck_l.setPos(0, 0.16, -1.48)
        trophy_neck_l.reparentTo(self.arm_l)

        # 5. 전신 뼈 오른팔 & 뼈 손가락 (Skeletal Right Arm & Fingers)
        self.arm_r = self.body_root.attachNewNode("orc_arm_r")
        self.arm_r.setPos(0.75, 0.05, 1.70)

        # 상완골 (Humerus)
        humerus_r = make_cylinder('orc_humerus_r', 0.18, 0.18, 0.52, bone_ivory)
        humerus_r.setPos(0, 0, -0.26)
        humerus_r.reparentTo(self.arm_r)

        # 팔꿈치 관절
        elbow_r = make_sphere('orc_elbow_r', 0.20, 0.20, 0.16, bone_dark)
        elbow_r.setPos(0, 0.02, -0.52)
        elbow_r.reparentTo(self.arm_r)

        self.forearm_r = self.arm_r.attachNewNode("orc_forearm_r")
        self.forearm_r.setPos(0, 0.08, -0.60)

        # 전완 이중 뼈 (Radius & Ulna)
        radius_r = make_cylinder('orc_radius_r', 0.09, 0.09, 0.44, bone_ivory)
        radius_r.setPos(-0.06, 0, -0.16)
        radius_r.reparentTo(self.forearm_r)

        ulna_r = make_cylinder('orc_ulna_r', 0.09, 0.09, 0.44, bone_ivory)
        ulna_r.setPos(0.06, 0, -0.16)
        ulna_r.reparentTo(self.forearm_r)

        # 손목 및 뼈 주먹/손가락
        wrist_r = make_cube('orc_wrist_r', 0.18, 0.18, 0.10, bone_dark)
        wrist_r.setPos(0, 0.08, -0.38)
        wrist_r.reparentTo(self.forearm_r)

        bone_hand_r = make_cube('orc_bone_hand_r', 0.24, 0.24, 0.18, bone_ivory)
        bone_hand_r.setPos(0, 0.14, -0.44)
        bone_hand_r.reparentTo(self.forearm_r)

        # 오른손에 움켜쥔 머리칼
        hair_grasp_r = make_sphere('hair_grasp_r', 0.30, 0.30, 0.26, hair_black)
        hair_grasp_r.setPos(0, 0.22, -0.44)
        hair_grasp_r.reparentTo(self.forearm_r)

        # 비명지르는 또 다른 사람의 머리통 (타격 및 내리치기용)
        trophy_head_r = make_sphere('trophy_head_r', 0.42, 0.44, 0.48, pale_dead_flesh)
        trophy_head_r.setPos(0, 0.32, -0.72)
        trophy_head_r.setP(25)
        trophy_head_r.reparentTo(self.forearm_r)

        trophy_face_r = make_cube('trophy_face_r', 0.38, 0.22, 0.40, pale_dead_flesh)
        trophy_face_r.setPos(0, 0.52, -0.72)
        trophy_face_r.setP(25)
        trophy_face_r.reparentTo(self.forearm_r)

        eye_r1_w = make_sphere('trophy_eye_r1_w', 0.10, 0.05, 0.08, LColor(0.92, 0.90, 0.85, 1.0))
        eye_r1_w.setPos(-0.11, 0.62, -0.66)
        eye_r1_w.setP(25)
        eye_r1_w.setLightOff()
        eye_r1_w.reparentTo(self.forearm_r)

        eye_r2_w = make_sphere('trophy_eye_r2_w', 0.10, 0.05, 0.08, LColor(0.92, 0.90, 0.85, 1.0))
        eye_r2_w.setPos(0.11, 0.62, -0.66)
        eye_r2_w.setP(25)
        eye_r2_w.setLightOff()
        eye_r2_w.reparentTo(self.forearm_r)

        pupil_r1 = make_sphere('trophy_pupil_r1', 0.05, 0.03, 0.05, LColor(0.40, 0.05, 0.05, 1.0))
        pupil_r1.setPos(-0.11, 0.65, -0.66)
        pupil_r1.setP(25)
        pupil_r1.setLightOff()
        pupil_r1.reparentTo(self.forearm_r)

        pupil_r2 = make_sphere('trophy_pupil_r2', 0.05, 0.03, 0.05, LColor(0.40, 0.05, 0.05, 1.0))
        pupil_r2.setPos(0.11, 0.65, -0.66)
        pupil_r2.setP(25)
        pupil_r2.setLightOff()
        pupil_r2.reparentTo(self.forearm_r)

        trophy_nose_r = make_cube('trophy_nose_r', 0.09, 0.12, 0.15, pale_dead_flesh)
        trophy_nose_r.setPos(0, 0.64, -0.72)
        trophy_nose_r.setP(25)
        trophy_nose_r.reparentTo(self.forearm_r)

        # 경악으로 쩍 벌어진 사람 턱
        trophy_jaw_r = make_cube('trophy_jaw_r', 0.34, 0.28, 0.20, pale_dead_flesh)
        trophy_jaw_r.setPos(0, 0.56, -0.88)
        trophy_jaw_r.setP(45)
        trophy_jaw_r.reparentTo(self.forearm_r)

        trophy_mouth_r = make_cube('trophy_mouth_r', 0.26, 0.18, 0.14, gore_crimson)
        trophy_mouth_r.setPos(0, 0.58, -0.82)
        trophy_mouth_r.setP(45)
        trophy_mouth_r.reparentTo(self.forearm_r)

        trophy_neck_r = make_cube('trophy_neck_r', 0.26, 0.26, 0.14, gore_crimson)
        trophy_neck_r.setPos(0, 0.28, -0.96)
        trophy_neck_r.setP(25)
        trophy_neck_r.reparentTo(self.forearm_r)

        # 6. 전신 뼈 다리 및 뼈 발 (Skeletal Legs & Feet)
        self.legs = []
        for side, name in ((-1, "l"), (1, "r")):
            hip = self.body_root.attachNewNode(f"orc_hip_{name}")
            hip.setPos(side * 0.38, 0, 0.85)

            # 대퇴골 (Femur)
            thigh = make_cylinder(f'orc_thigh_{name}', 0.18, 0.18, 0.50, bone_ivory)
            thigh.setPos(0, 0, -0.25)
            thigh.reparentTo(hip)

            # 무릎뼈 (Patella)
            patella = make_sphere(f'orc_patella_{name}', 0.14, 0.12, 0.14, bone_dark)
            patella.setPos(0, 0.11, -0.50)
            patella.reparentTo(hip)

            # 하퇴 이중 뼈: 경골(Tibia) 및 비골(Fibula)
            shin = make_cylinder(f'orc_shin_{name}', 0.14, 0.14, 0.48, bone_ivory)
            shin.setPos(0, 0.04, -0.72)
            shin.reparentTo(hip)

            fibula = make_cylinder(f'orc_fibula_{name}', 0.07, 0.07, 0.46, bone_dark)
            fibula.setPos(side * 0.08, -0.04, -0.72)
            fibula.reparentTo(hip)

            # 발목 관절 (Ankle)
            ankle = make_sphere(f'orc_ankle_{name}', 0.18, 0.20, 0.12, bone_dark)
            ankle.setPos(0, 0.04, -0.94)
            ankle.reparentTo(hip)

            # 종골 발꿈치 (Calcaneus Heel)
            heel = make_cube(f'orc_heel_{name}', 0.14, 0.16, 0.14, bone_dark)
            heel.setPos(0, -0.08, -0.96)
            heel.reparentTo(hip)

            # 중족골 발등 뼈 (Metatarsals)
            foot = make_cube(f'orc_foot_{name}', 0.24, 0.32, 0.12, bone_ivory)
            foot.setPos(0, 0.14, -0.98)
            foot.reparentTo(hip)

            # 뼈 발가락 (Bone Toes)
            toes = make_cube(f'orc_toes_{name}', 0.22, 0.16, 0.08, bone_white)
            toes.setPos(0, 0.28, -0.98)
            toes.reparentTo(hip)

            self.legs.append({'hip': hip, 'side': side})

        # 거대 백골 오크 오라 라이트 (스펙트럴 백골 냉광)
        self.parent_ref = parent
        self.aura_is_lit = False
        pl = PointLight('mud_orc_aura')
        pl.setColor((0.65, 0.65, 0.60, 1.0))
        pl.setAttenuation((1.0, 0.18, 0.05))
        self.aura_np = self.node.attachNewNode(pl)
        self.aura_np.setPos(0, 0, 1.6)

    def stun(self, duration=0.18):
        """총격 적중 시 0.18초간 경직/스턴 발동 (오크 강인한 체형 반영)"""
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 1.8, 0.4, 1.0))

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """피해 적용 및 사망 여부 반환 (기본 넉백 확률 적용, 오크는 체형상 20% 확률)"""
        self.hp = max(0, self.hp - dmg)
        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        if apply_knockback is None:
            apply_knockback = (random.random() < 0.20)

        if apply_knockback:
            self.stun(0.18)
            if hit_dir is not None:
                self.pos.x += hit_dir.x * 0.20
                self.pos.y += hit_dir.y * 0.20
                self.node.setPos(self.pos)
        else:
            if hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((1.8, 1.2, 0.3, 1.0))

        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 유혈 진흙 폭발 파편화: 오크 머리통, 엄니, 철갑주 파편, 거대한 근육질 팔/다리 살점 덩어리가 사방으로 폭발 분출"""
        self.is_corpse = True
        self.hp = 0
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
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
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
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
        s = self.node.getScale()[0] if hasattr(self, 'node') and self.node and not self.node.isEmpty() else (1.25 if getattr(self, 'is_elite', False) else 1.0)
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 2.3 * s, 0.60 * s, True), # 턱/머리 (헤드샷!)
            (self.pos.x, self.pos.y, self.pos.z + 1.8 * s, 0.80 * s, False),
            (self.pos.x, self.pos.y, self.pos.z + 1.0 * s, 0.85 * s, False)
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
                self.aura_np.node().setColor((0.65, 0.65, 0.60, 1.0))
            return

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.pos.x = new_x
        self.pos.y = new_y
        if self.pos.z < floor_z:
            self.pos.z = floor_z
        elif self.pos.z > floor_z:
            self.pos.z = max(floor_z, self.pos.z - dt * 24.0)
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 8.0))

        target_p = 12.0 if s_type == 'ramp' else 0.0
        curr_p = self.node.getP()
        self.node.setP(curr_p + (target_p - curr_p) * min(1.0, dt * 8.0))

        self.update(dt, is_moving=True)

    def slam_ground(self, dt):
        """양손에 든 사람 머리통들을 높이 치켜들고 땅을 강하게 내리쳐 충격파를 발생시키는 스킬 애니메이션"""
        if not self.is_slamming:
            return False

        self.slam_timer += dt
        # 1단계 (0.0s ~ 0.5s): 양손의 참수된 사람 머리를 하늘 높이 치켜드는 준비 동작
        if self.slam_timer < 0.5:
            prog = self.slam_timer / 0.5
            self.arm_r.setP(-15 - prog * 95.0)  # -110도까지 번쩍 들어올림
            self.arm_l.setP(-prog * 95.0)       # 왼손 머리통도 함께 하늘 높이 치켜듬
            self.torso.setP(-prog * 18.0)
            return False

        # 2단계 (0.5s): 양팔의 사람 머리통을 지면에 쾅! 하고 내리치는 임팩트 순간 (충격파 발생)
        if self.slam_timer >= 0.5 and not self.slam_has_impacted:
            self.arm_r.setP(52)  # 바닥을 향해 수직 강타
            self.arm_l.setP(46)
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
        self.update_elemental(dt)
        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.stun_timer <= 0.0 and hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((0.65, 0.65, 0.60, 1.0))

        if self.is_slamming:
            return

        if is_attacking:
            self.arm_r.setP(-75)
            self.arm_l.setP(-60)
            self.torso.setP(18)
            return

        if is_moving:
            self.anim_time += dt * 4.6
            phase = self.anim_time

            for leg in self.legs:
                side = leg['side']
                stride = math.sin(phase) * 32.0 * (-side)
                leg['hip'].setP(stride)

            # 양손에 든 참수된 사람 머리가 쿵쿵 흔들리는 보행 모션
            self.arm_r.setP(math.sin(phase) * 26.0 - 15)
            self.arm_l.setP(-math.sin(phase) * 26.0)
            self.head_pivot.setH(math.sin(phase * 0.8) * 6.0)
            self.body_root.setZ(abs(math.sin(phase)) * 0.09)
        else:
            t = ClockObject.getGlobalClock().getFrameTime()
            self.arm_r.setP(math.sin(t * 1.5) * 5.0 - 10)
            self.arm_l.setP(math.sin(t * 1.5) * 4.0)
            self.head_pivot.setH(math.sin(t * 1.2) * 4.0)


class AlluringAshWitch(ElementalMonsterMixin):
    col_radius = 0.38
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
        floor_z, _ = get_floor_height(start_x, start_y)
        self.pos = Vec3(start_x, start_y, floor_z + 0.85)
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
        self.col_radius = 0.38
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0

        ash_robe = LColor(0.16, 0.15, 0.18, 1.0)
        charred_rag = LColor(0.08, 0.07, 0.08, 1.0)
        melt_sludge = LColor(0.24, 0.14, 0.11, 1.0)
        molten_flesh = LColor(0.85, 0.32, 0.12, 1.0)
        charred_bone = LColor(0.12, 0.11, 0.12, 1.0)
        ember_crimson = LColor(1.0, 0.28, 0.10, 1.0)
        pale_skin = LColor(0.82, 0.80, 0.84, 1.0)
        hat_dark = LColor(0.08, 0.07, 0.10, 1.0)
        eye_ruby = LColor(1.0, 0.12, 0.35, 1.0)
        wood_char = LColor(0.14, 0.12, 0.10, 1.0)

        self.body_root = self.node.attachNewNode("witch_body_root")

        # 1. 녹아내리는 하체 및 불타 사라진 옷 잔해 (Melted Sludge Lower Body & Charred Rags)
        self.skirt_root = self.body_root.attachNewNode("witch_melt_lower")
        self.skirt_root.setPos(0, 0, 0.6)

        # 녹아내려 흘러내리는 진흙/슬러지 중심 기둥
        melt_core = make_cube('melt_core', 0.34, 0.30, 0.70, melt_sludge)
        melt_core.setPos(0, 0, 0.20)
        melt_core.reparentTo(self.skirt_root)

        # 바닥을 향해 뚝뚝 떨어지는 점성 있는 녹아내린 살점 종유석(Tendrils)
        self.drip_1 = make_cube('drip_1', 0.14, 0.14, 0.55, melt_sludge)
        self.drip_1.setPos(-0.16, 0.08, -0.15)
        self.drip_1.reparentTo(self.skirt_root)

        self.drip_2 = make_cube('drip_2', 0.15, 0.15, 0.72, molten_flesh)
        self.drip_2.setPos(0.12, -0.06, -0.22)
        self.drip_2.reparentTo(self.skirt_root)

        self.drip_3 = make_cube('drip_3', 0.10, 0.10, 0.45, melt_sludge)
        self.drip_3.setPos(0.02, 0.14, -0.10)
        self.drip_3.reparentTo(self.skirt_root)

        # 공중에 맺힌 채 뚝뚝 떨어지는 불타는 용암 방울들
        droplet_1 = make_cube('droplet_1', 0.08, 0.08, 0.12, ember_crimson)
        droplet_1.setPos(-0.12, 0.05, -0.48)
        droplet_1.setLightOff()
        droplet_1.reparentTo(self.skirt_root)

        droplet_2 = make_cube('droplet_2', 0.09, 0.09, 0.14, ember_crimson)
        droplet_2.setPos(0.14, -0.04, -0.55)
        droplet_2.setLightOff()
        droplet_2.reparentTo(self.skirt_root)

        # 옷이 타올라 거의 남지 않은 그을린 천 조각(Charred Rag scraps)
        rag_1 = make_cube('burned_rag_1', 0.42, 0.38, 0.18, charred_rag)
        rag_1.setPos(0, 0, 0.45)
        rag_1.reparentTo(self.skirt_root)

        rag_scrap = make_cube('rag_scrap', 0.16, 0.08, 0.32, charred_rag)
        rag_scrap.setPos(-0.20, 0.10, 0.25)
        rag_scrap.setP(18)
        rag_scrap.reparentTo(self.skirt_root)

        # 2. 녹아내린 흉곽과 드러난 갈비뼈 & 붉은 마그마 심장 (Exposed Charred Ribs & Molten Core)
        self.torso = make_cube('witch_melted_torso', 0.36, 0.28, 0.58, melt_sludge)
        self.torso.setPos(0, 0, 1.32)
        self.torso.reparentTo(self.body_root)

        # 살점이 녹아 밖으로 돌출된 검게 그을린 3쌍의 갈비뼈
        rib_1 = make_cube('witch_rib_1', 0.38, 0.30, 0.06, charred_bone)
        rib_1.setPos(0, 0.04, 1.25)
        rib_1.reparentTo(self.body_root)

        rib_2 = make_cube('witch_rib_2', 0.40, 0.32, 0.06, charred_bone)
        rib_2.setPos(0, 0.04, 1.35)
        rib_2.reparentTo(self.body_root)

        rib_3 = make_cube('witch_rib_3', 0.38, 0.30, 0.06, charred_bone)
        rib_3.setPos(0, 0.04, 1.45)
        rib_3.reparentTo(self.body_root)

        # 녹아내린 가슴 안에서 박동하는 진홍빛 마그마 코어 심장
        self.molten_core = make_sphere('molten_core', 0.18, 0.16, 0.22, ember_crimson)
        self.molten_core.setPos(0, 0.06, 1.35)
        self.molten_core.setLightOff()
        self.molten_core.reparentTo(self.body_root)

        # 어깨를 타고 흘러내리는 용암질 살점 덩어리
        melt_sh_l = make_cube('melt_sh_l', 0.16, 0.18, 0.32, molten_flesh)
        melt_sh_l.setPos(-0.24, 0.02, 1.48)
        melt_sh_l.reparentTo(self.body_root)

        melt_sh_r = make_cube('melt_sh_r', 0.14, 0.16, 0.28, melt_sludge)
        melt_sh_r.setPos(0.24, 0.02, 1.48)
        melt_sh_r.reparentTo(self.body_root)

        # 3. 반쯤 녹아내린 얼굴 & 타버린 마녀 모자 (Melted Face & Ruined Charred Hat)
        self.head_pivot = self.body_root.attachNewNode("witch_head_pivot")
        self.head_pivot.setPos(0, 0, 1.82)

        # 좌측은 창백한 피부, 우측은 녹아 흘러내린 슬러지 살점
        face_pale = make_cube('witch_face_pale', 0.16, 0.25, 0.30, pale_skin)
        face_pale.setPos(-0.07, 0.02, 0.05)
        face_pale.reparentTo(self.head_pivot)

        face_melt = make_cube('witch_face_melt', 0.16, 0.26, 0.36, melt_sludge)
        face_melt.setPos(0.07, 0.04, -0.02)
        face_melt.reparentTo(self.head_pivot)

        melt_jaw = make_cube('melt_jaw', 0.22, 0.22, 0.15, molten_flesh)
        melt_jaw.setPos(0.02, 0.10, -0.16)
        melt_jaw.setP(22)
        melt_jaw.reparentTo(self.head_pivot)

        # 좌측 루비 안광 / 우측 불타 녹아내린 검은 안와
        eye_l = make_sphere('witch_eye_l', 0.06, 0.04, 0.06, eye_ruby)
        eye_l.setPos(-0.08, 0.16, 0.08)
        eye_l.setLightOff()
        eye_l.reparentTo(self.head_pivot)

        eye_melt = make_sphere('witch_eye_melt', 0.08, 0.05, 0.08, charred_rag)
        eye_melt.setPos(0.08, 0.16, 0.06)
        eye_melt.reparentTo(self.head_pivot)

        # 불타서 거의 타버린 비대칭 찢겨진 마녀 모자 잔해
        hat_brim_ruin = make_cube('hat_brim_ruin', 0.55, 0.60, 0.06, hat_dark)
        hat_brim_ruin.setPos(-0.10, 0.02, 0.24)
        hat_brim_ruin.setP(14)
        hat_brim_ruin.reparentTo(self.head_pivot)

        hat_cone_charred = make_cube('hat_cone_charred', 0.32, 0.32, 0.26, hat_dark)
        hat_cone_charred.setPos(-0.06, 0.02, 0.38)
        hat_cone_charred.setP(20)
        hat_cone_charred.reparentTo(self.head_pivot)

        hat_ember_tip = make_cube('hat_ember_tip', 0.09, 0.09, 0.10, ember_crimson)
        hat_ember_tip.setPos(-0.04, 0.0, 0.52)
        hat_ember_tip.setLightOff()
        hat_ember_tip.reparentTo(self.head_pivot)

        # 4. 팔 & 스태프 (앙상하게 불탄 뼈대 팔과 타버린 소매 조각)
        self.arm_l = self.body_root.attachNewNode("witch_arm_l")
        self.arm_l.setPos(-0.30, 0, 1.55)
        sleeve_l = make_cube('sleeve_l', 0.12, 0.12, 0.42, charred_rag)
        sleeve_l.setPos(0, 0.08, -0.22)
        sleeve_l.setP(-25)
        sleeve_l.reparentTo(self.arm_l)

        self.arm_r = self.body_root.attachNewNode("witch_arm_r")
        self.arm_r.setPos(0.30, 0, 1.55)
        sleeve_r = make_cube('sleeve_r', 0.12, 0.12, 0.42, charred_rag)
        sleeve_r.setPos(0, 0.08, -0.22)
        sleeve_r.setP(-35)
        sleeve_r.reparentTo(self.arm_r)

        self.staff_node = self.arm_r.attachNewNode("witch_staff")
        self.staff_node.setPos(0.12, 0.42, -0.15)
        staff_rod = make_cube('staff_rod', 0.06, 0.06, 1.65, wood_char)
        staff_rod.reparentTo(self.staff_node)

        self.orb = make_sphere('ember_orb', 0.22, 0.22, 0.22, ember_crimson)
        self.orb.setPos(0, 0, 0.90)
        self.orb.setH(45)
        self.orb.setLightOff()
        self.orb.reparentTo(self.staff_node)

        self.parent_ref = parent
        self.aura_is_lit = False
        pl = PointLight('ash_witch_aura')
        pl.setColor((1.2, 0.35, 0.18, 1.0))
        pl.setAttenuation((1.0, 0.14, 0.035))
        self.aura_np = self.staff_node.attachNewNode(pl)
        self.aura_np.setPos(0, 0, 0.90)

    def stun(self, duration=0.20):
        """총격 적중 시 0.20초간 경직/스턴 발동"""
        self.stun_timer = duration
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.4, 2.0, 0.6, 1.0))

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """피해 적용 및 사망 여부 반환 (기본 넉백 확률 적용)"""
        self.hp = max(0, self.hp - dmg)
        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        if apply_knockback is None:
            apply_knockback = (random.random() < 0.28)

        if apply_knockback:
            self.stun(0.20)
            if hit_dir is not None:
                self.pos.x += hit_dir.x * 0.28
                self.pos.y += hit_dir.y * 0.28
                self.node.setPos(self.pos)
        else:
            if hasattr(self, 'aura_np') and self.aura_np:
                self.aura_np.node().setColor((1.8, 1.2, 0.5, 1.0))

        return self.hp <= 0

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 잿더미와 마력 화염 폭발 파편화: 마녀 가면, 찢겨진 베일 리본, 불타는 잿더미 마력 불씨가 사방으로 비산"""
        self.is_corpse = True
        self.hp = 0
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
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
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
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
        s = self.node.getScale()[0] if hasattr(self, 'node') and self.node and not self.node.isEmpty() else (1.25 if getattr(self, 'is_elite', False) else 1.0)
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 2.0 * s, 0.55 * s, True), # 마녀 머리 (헤드샷!)
            (self.pos.x, self.pos.y, self.pos.z + 1.4 * s, 0.55 * s, False),
            (self.pos.x, self.pos.y, self.pos.z + 0.6 * s, 0.65 * s, False)
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

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.pos.x = new_x
        self.pos.y = new_y
        # 공중 부유 높이 진동 (해당 지면/플랫폼 기준 +0.85m)
        target_z = floor_z + 0.85 + math.sin(self.anim_time * 2.8) * 0.22
        self.pos.z += (target_z - self.pos.z) * min(1.0, dt * 10.0)
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
        self.update_elemental(dt)
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
        # 녹아내린 하체 및 잔해 부유 스웨이 & 살점 종유석 신축
        self.skirt_root.setR(math.sin(t * 2.5) * 8.0)
        self.skirt_root.setP(math.cos(t * 2.2) * 6.0)
        if hasattr(self, 'drip_1') and hasattr(self, 'drip_2'):
            self.drip_1.setScale(1.0, 1.0, 1.0 + math.sin(t * 3.2) * 0.22)
            self.drip_2.setScale(1.0, 1.0, 1.0 - math.sin(t * 3.2) * 0.22)
        if hasattr(self, 'molten_core'):
            self.molten_core.setScale(1.0 + math.sin(t * 4.5) * 0.15)

        self.staff_node.setZ(-0.15 + math.sin(t * 3.0) * 0.06)
        self.head_pivot.setR(math.sin(t * 1.5) * 4.0)


# 기존 호환용 별칭
CreepySpiderMonster = LongBlackSerpent
TallShadowMonster = TallSkeletonMonster


class SkeletalDobermanHellhound(ElementalMonsterMixin):
    col_radius = 0.35
    """
    지옥의 파수견 (Skeletal Doberman Hellhound)
    - 뼈로만 이루어진 사나운 도베르만 골격 괴물
    - 쫑긋 세워진 단이(Cropped) 뼈 귀, 날카로운 두개골과 송곳니, 붉게 타오르는 안와
    - 흉곽 내부에서 맥동하는 지옥불 심장(Hellfire Core) 및 붉은 안광 오라
    - 4족 보행 역동적인 질주(Gallop Cycle) 애니메이션
    - 총알을 35% 확률로 횡방향 공중 회피(Evasive Dodge Roll / Leap)하며 무효화
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("skeletal_doberman_hellhound")
        floor_z, _ = get_floor_height(start_x, start_y)
        self.pos = Vec3(start_x, start_y, floor_z)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.stun_timer = 0.0
        self.is_corpse = False
        self.name = "지옥의 파수견"
        self.max_hp = 145
        self.hp = self.max_hp
        self.exp_value = 50
        self.attack_damage = 28
        self.speed = 12.0
        self.col_radius = 0.35
        self.debris_list = []
        self.blast_light_np = None
        self.puddle_np = None
        self.blast_timer = 0.0
        self.last_hit_was_head = False
        self.parent_ref = parent

        # 회피(Dodge) 메카닉 상태 변수
        self.is_dodging = False
        self.dodge_timer = 0.0
        self.dodge_vel = Vec3(0, 0, 0)
        self.last_action_dodged = False

        # 전신 맥동 붉은 혈관 선 (Hellfire Vein Lines) 노드 목록
        self.hellfire_vein_nodes = []

        bone_white = LColor(0.88, 0.86, 0.78, 1.0)
        bone_dark = LColor(0.55, 0.52, 0.44, 1.0)
        void_black = LColor(0.005, 0.005, 0.005, 1.0)
        hellfire_core = LColor(1.0, 0.35, 0.08, 1.0)
        eye_ember = LColor(1.0, 0.22, 0.04, 1.0)
        claw_col = LColor(0.18, 0.16, 0.15, 1.0)

        # 1. 몸통 메인 루트 (어깨 높이 기준 0.76m)
        self.body_root = self.node.attachNewNode("hound_body_root")
        self.body_root.setPos(0, 0, 0.76)

        # 척추뼈 기둥 (Spine Vertebrae)
        make_cube_to(self.body_root, 0.14, 0.78, 0.12, bone_dark, 0, -0.05, 0.06)
        # 등 척추 가시 돌기 (Dorsal Spine Ridges)
        for i in range(5):
            y_sp = 0.22 - i * 0.13
            make_cube_to(self.body_root, 0.05, 0.08, 0.14, bone_white, 0, y_sp, 0.16, rot_p=-16)
            # 가시 돌기 붉은 균열선
            self._add_vein(self.body_root, 0.018, 0.020, 0.15, 0, y_sp + 0.015, 0.17, rot_p=-16)

        # 등 척추 정중선 & 좌우 척추 도랑 붉은 혈관선
        self._add_vein(self.body_root, 0.026, 0.78, 0.024, 0, -0.05, 0.125)
        self._add_vein(self.body_root, 0.018, 0.72, 0.018, -0.065, -0.05, 0.08)
        self._add_vein(self.body_root, 0.018, 0.72, 0.018, 0.065, -0.05, 0.08)

        # 2. 흉곽 갈비뼈 (Ribcage)
        for i in range(5):
            y_rib = 0.20 - i * 0.11
            w_rib = 0.32 - i * 0.02
            # 좌측 갈비뼈
            make_cube_to(self.body_root, 0.05, 0.06, 0.26, bone_white, -w_rib * 0.5, y_rib, -0.06, rot_r=18)
            # 우측 갈비뼈
            make_cube_to(self.body_root, 0.05, 0.06, 0.26, bone_white, w_rib * 0.5, y_rib, -0.06, rot_r=-18)
            # 흉골 바닥 연결재
            make_cube_to(self.body_root, w_rib * 0.75, 0.05, 0.04, bone_dark, 0, y_rib, -0.20)

            # 갈비뼈 외측을 따라 흐르는 붉은 혈관선
            self._add_vein(self.body_root, 0.018, 0.024, 0.26, -w_rib * 0.52, y_rib, -0.06, rot_r=18)
            self._add_vein(self.body_root, 0.018, 0.024, 0.26, w_rib * 0.52, y_rib, -0.06, rot_r=-18)
        # 흉부 하단 중심선
        self._add_vein(self.body_root, 0.022, 0.55, 0.022, 0, -0.02, -0.21)

        # 3. 흉곽 내부 초소형 지옥불 심장 불씨 (거대 네모박스 완전 제거: 32cm 갈비뼈 내부 깊숙이 위치하는 3cm 미니멀 불씨)
        self.heart_pivot = self.body_root.attachNewNode("hound_heart_pivot")
        self.heart_pivot.setPos(0, 0.08, -0.06)
        self.heart_core = make_sphere_to(self.heart_pivot, 0.028, 0.035, 0.028, hellfire_core, 0, 0, 0)
        self.heart_core.setLightOff()

        # 4. 목 및 도베르만 해골 머리 (Neck & Cropped Doberman Skull)
        self.neck_pivot = self.body_root.attachNewNode("hound_neck_pivot")
        self.neck_pivot.setPos(0, 0.36, 0.10)
        make_cube_to(self.neck_pivot, 0.12, 0.26, 0.14, bone_dark, 0, 0.10, 0.08, rot_p=-32)
        # 목 경추 정중선 및 좌우 경정맥 뼈선
        self._add_vein(self.neck_pivot, 0.024, 0.26, 0.024, 0, 0.10, 0.155, rot_p=-32)
        self._add_vein(self.neck_pivot, 0.018, 0.24, 0.018, -0.065, 0.10, 0.07, rot_p=-32)
        self._add_vein(self.neck_pivot, 0.018, 0.24, 0.018, 0.065, 0.10, 0.07, rot_p=-32)

        self.head_pivot = self.neck_pivot.attachNewNode("hound_head_pivot")
        self.head_pivot.setPos(0, 0.22, 0.20)

        # 두개골 (Cranium)
        make_sphere_to(self.head_pivot, 0.26, 0.30, 0.20, bone_white, 0, 0.04, 0.02)
        # 길쭉하고 각진 뼈 주둥이 (Snout / Maxilla)
        make_cube_to(self.head_pivot, 0.16, 0.34, 0.13, bone_white, 0, 0.28, -0.02, rot_p=8)
        # 비강 결손 (Nasal Cavity Void)
        make_cube_to(self.head_pivot, 0.08, 0.10, 0.08, void_black, 0, 0.42, -0.03)

        # 두개골 정수리 중심선 & 주둥이 콧등 붉은 선
        self._add_vein(self.head_pivot, 0.024, 0.28, 0.024, 0, 0.04, 0.125)
        self._add_vein(self.head_pivot, 0.022, 0.32, 0.022, 0, 0.28, 0.05, rot_p=8)
        # 좌우 상악골 측면 혈관선
        self._add_vein(self.head_pivot, 0.018, 0.28, 0.018, -0.09, 0.25, -0.02, rot_p=8)
        self._add_vein(self.head_pivot, 0.018, 0.28, 0.018, 0.09, 0.25, -0.02, rot_p=8)

        # 도베르만 특유의 쫑긋 세워진 단이 뼈 귀 (Cropped Upright Bone Ears)
        make_cube_to(self.head_pivot, 0.035, 0.075, 0.24, bone_dark, -0.11, -0.04, 0.18, rot_h=-12, rot_p=-16, rot_r=-15)
        make_cube_to(self.head_pivot, 0.035, 0.075, 0.24, bone_dark, 0.11, -0.04, 0.18, rot_h=12, rot_p=-16, rot_r=15)
        # 귀 외곽 능선 붉은 선
        self._add_vein(self.head_pivot, 0.016, 0.035, 0.22, -0.115, -0.04, 0.18, rot_h=-12, rot_p=-16, rot_r=-15)
        self._add_vein(self.head_pivot, 0.016, 0.035, 0.22, 0.115, -0.04, 0.18, rot_h=12, rot_p=-16, rot_r=15)

        # 타오르는 지옥 안광 (Hellfire Ember Sockets)
        eye_l = make_sphere_to(self.head_pivot, 0.055, 0.075, 0.055, eye_ember, -0.095, 0.14, 0.05)
        eye_r = make_sphere_to(self.head_pivot, 0.055, 0.075, 0.055, eye_ember, 0.095, 0.14, 0.05)
        eye_l.setLightOff()
        eye_r.setLightOff()

        # 상악 송곳니 (Upper Sharp Fangs)
        make_cube_to(self.head_pivot, 0.028, 0.028, 0.095, bone_white, -0.065, 0.38, -0.095, rot_p=14)
        make_cube_to(self.head_pivot, 0.028, 0.028, 0.095, bone_white, 0.065, 0.38, -0.095, rot_p=14)

        # 하악골 피벗 (Lower Jaw)
        self.jaw_pivot = self.head_pivot.attachNewNode("hound_jaw_pivot")
        self.jaw_pivot.setPos(0, 0.04, -0.08)
        make_cube_to(self.jaw_pivot, 0.13, 0.32, 0.07, bone_dark, 0, 0.16, 0.0, rot_p=6)
        # 하악골 좌우 외곽 붉은 혈관선
        self._add_vein(self.jaw_pivot, 0.018, 0.28, 0.018, -0.068, 0.16, 0.01, rot_p=6)
        self._add_vein(self.jaw_pivot, 0.018, 0.28, 0.018, 0.068, 0.16, 0.01, rot_p=6)
        # 하악 송곳니
        make_cube_to(self.jaw_pivot, 0.025, 0.025, 0.085, bone_white, -0.055, 0.28, 0.055, rot_p=-12)
        make_cube_to(self.jaw_pivot, 0.025, 0.025, 0.085, bone_white, 0.055, 0.28, 0.055, rot_p=-12)

        # 5. 골반 및 단미 뼈 꼬리 (Pelvis & Docked Tail)
        make_cube_to(self.body_root, 0.25, 0.26, 0.16, bone_white, 0, -0.46, 0.03)
        # 골반 상단 및 좌우 날개 붉은 선
        self._add_vein(self.body_root, 0.26, 0.024, 0.024, 0, -0.46, 0.115)
        self._add_vein(self.body_root, 0.024, 0.24, 0.024, -0.12, -0.46, 0.04)
        self._add_vein(self.body_root, 0.024, 0.24, 0.024, 0.12, -0.46, 0.04)

        self.tail_pivot = self.body_root.attachNewNode("hound_tail_pivot")
        self.tail_pivot.setPos(0, -0.58, 0.08)
        make_cube_to(self.tail_pivot, 0.045, 0.16, 0.045, bone_dark, 0, -0.07, 0.05, rot_p=-45)
        # 꼬리 붉은 능선
        self._add_vein(self.tail_pivot, 0.022, 0.16, 0.022, 0, -0.07, 0.075, rot_p=-45)

        # 6. 4개의 지제보행(Digitigrade) 골격 다리
        # (1) 앞다리 좌/우 (Front Left / Front Right)
        self.leg_fl = self._build_front_leg(-0.19, 0.24, "fl", bone_white, bone_dark, claw_col)
        self.leg_fr = self._build_front_leg(0.19, 0.24, "fr", bone_white, bone_dark, claw_col)

        # (2) 뒷다리 좌/우 (Rear Left / Rear Right - 굵은 대퇴골과 꺾인 도베르만 비절)
        self.leg_bl = self._build_rear_leg(-0.18, -0.44, "bl", bone_white, bone_dark, claw_col)
        self.leg_br = self._build_rear_leg(0.18, -0.44, "br", bone_white, bone_dark, claw_col)

        # 7. 지옥불 아우라 조명 (Hellfire Aura Light)
        self.aura_is_lit = False
        aura_light = PointLight('hound_aura')
        aura_light.setColor((2.2, 0.65, 0.12, 1.0))
        aura_light.setAttenuation((1.0, 0.08, 0.025))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0.1, 0.8)

    def _add_vein(self, parent, sx, sy, sz, px, py, pz, rot_h=0, rot_p=0, rot_r=0):
        """몸체 부착용 맥동 붉은 지옥불 혈관/뼈선 생성 및 등록"""
        hellfire_core = LColor(1.0, 0.30, 0.06, 1.0)
        node = make_cube_to(parent, sx, sy, sz, hellfire_core, px, py, pz, rot_h, rot_p, rot_r)
        node.setLightOff()
        self.hellfire_vein_nodes.append(node)
        return node

    def _build_front_leg(self, x, y, name, b_col, d_col, c_col):
        shoulder = self.body_root.attachNewNode(f"hound_sh_{name}")
        shoulder.setPos(x, y, -0.06)
        make_sphere_to(shoulder, .11, .11, .11, b_col, 0, 0, 0)
        # 견갑골 붉은 선
        self._add_vein(shoulder, 0.022, 0.022, 0.14, 0, 0.03, -0.05)

        # 상완골 (Humerus)
        upper = shoulder.attachNewNode(f"hound_up_{name}")
        make_cylinder_to(upper, 0.08, 0.08, 0.35, b_col, 0, 0, -0.175)
        # 상완골 전면 붉은 선
        self._add_vein(upper, 0.022, 0.022, 0.35, 0, 0.042, -0.175)

        # 전완골 (Radius / Ulna)
        elbow = upper.attachNewNode(f"hound_elb_{name}")
        elbow.setPos(0, 0, -0.35)
        make_sphere_to(elbow, .09, .09, .09, d_col, 0, 0, 0)
        make_cylinder_to(elbow, 0.065, 0.065, 0.34, d_col, 0, 0.015, -0.17)
        # 전완골 전면 붉은 선
        self._add_vein(elbow, 0.020, 0.020, 0.34, 0, 0.048, -0.17)

        # 발목 및 3개 뼈 발톱 (Paw & Claws)
        paw = elbow.attachNewNode(f"hound_paw_{name}")
        paw.setPos(0, 0.02, -0.34)
        make_cube_to(paw, 0.09, 0.12, 0.05, d_col, 0, 0.04, -0.025)
        # 발등 붉은 선
        self._add_vein(paw, 0.055, 0.09, 0.020, 0, 0.04, 0.005)
        for c_idx in [-0.03, 0.0, 0.03]:
            make_cube_to(paw, 0.022, 0.055, 0.035, c_col, c_idx, 0.09, -0.025, rot_p=-15)

        return {'shoulder': shoulder, 'upper': upper, 'elbow': elbow, 'paw': paw}

    def _build_rear_leg(self, x, y, name, b_col, d_col, c_col):
        hip = self.body_root.attachNewNode(f"hound_hip_{name}")
        hip.setPos(x, y, 0.0)
        make_sphere_to(hip, .12, .12, .12, b_col, 0, 0, 0)

        # 대퇴골 (Femur - 전방 경사)
        femur = hip.attachNewNode(f"hound_fem_{name}")
        make_cylinder_to(femur, 0.095, 0.10, 0.38, b_col, 0, 0.05, -0.19, rot_p=-22)
        # 대퇴골 외측 붉은 선
        self._add_vein(femur, 0.022, 0.022, 0.38, 0, 0.055, -0.19, rot_p=-22)

        # 비절 / 경골 (Tibia / Hock - 후방 역관절 경사)
        knee = femur.attachNewNode(f"hound_knee_{name}")
        knee.setPos(0, 0.11, -0.36)
        make_sphere_to(knee, .10, .10, .10, d_col, 0, 0, 0)
        make_cylinder_to(knee, 0.075, 0.075, 0.36, d_col, 0, -0.06, -0.18, rot_p=32)
        # 경골 후면 붉은 선
        self._add_vein(knee, 0.020, 0.020, 0.36, 0, -0.075, -0.18, rot_p=32)

        # 뒷발목 및 발톱 (Rear Paw & Claws)
        paw = knee.attachNewNode(f"hound_rpaw_{name}")
        paw.setPos(0, -0.11, -0.34)
        make_cube_to(paw, 0.09, 0.12, 0.05, d_col, 0, 0.04, -0.025)
        # 뒷발등 붉은 선
        self._add_vein(paw, 0.055, 0.09, 0.020, 0, 0.04, 0.005)
        for c_idx in [-0.03, 0.0, 0.03]:
            make_cube_to(paw, 0.022, 0.055, 0.035, c_col, c_idx, 0.09, -0.025, rot_p=-15)

        return {'hip': hip, 'femur': femur, 'knee': knee, 'paw': paw}

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """총격 대미지 판정: 35% 확률로 횡방향 공중 회피 도약(Evasive Dodge Leap) 발동"""
        if self.hp <= 0 or self.is_corpse:
            return True

        # 이미 회피 무적 프레임(i-frame) 중이면 대미지 100% 무효 (지속 도트 피해 제외)
        if self.is_dodging and damage_type != 'dot':
            self.last_action_dodged = True
            return False

        # [35% 확률 회피 발동 (지속 도트 피해는 회피 불가)]
        if damage_type != 'dot' and random.random() < 0.35:
            self.is_dodging = True
            self.dodge_timer = 0.35
            self.last_action_dodged = True

            side = random.choice([-1.0, 1.0])
            if hit_dir is not None and (hit_dir.x != 0 or hit_dir.y != 0):
                # 총알 궤적과 수직인 횡방향으로 도약
                dodge_x = -hit_dir.y * side
                dodge_y = hit_dir.x * side
            else:
                h_rad = math.radians(self.node.getH() + 90.0 * side)
                dodge_x = math.cos(h_rad)
                dodge_y = math.sin(h_rad)

            d_mag = math.hypot(dodge_x, dodge_y)
            if d_mag > 0.01:
                dodge_x /= d_mag
                dodge_y /= d_mag

            self.dodge_vel = Vec3(dodge_x * 9.5, dodge_y * 9.5, 3.8)
            self.node.setR(side * 48.0)
            self.node.setP(-14.0)

            game_inst = getattr(self.node, 'game', None)
            if not game_inst:
                base = getattr(self.node, 'base', None)
            return False

        # 회피 실패: 정상 피해 적용
        self.hp = max(0, self.hp - dmg)
        self.last_action_dodged = False

        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        if hit_dir is not None and self.hp > 0:
            self.pos.x += hit_dir.x * 0.32
            self.pos.y += hit_dir.y * 0.32
            self.node.setPos(self.pos)

        return self.hp <= 0

    def stun(self, duration=0.20):
        self.stun_timer = duration

    def turn_into_corpse(self, audio_mgr=None):
        """사망 시 지옥불 폭발과 함께 전신 골격이 사방으로 산산조각 비산"""
        self.is_corpse = True
        self.is_dodging = False
        self.hp = 0
        self.cleanup_elemental()

        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()

        self.pos.z = 0.08
        self.node.setPos(self.pos)
        self.node.setP(-88)
        self.body_root.hide()

        if audio_mgr and hasattr(audio_mgr, 'play_hound_death'):
            audio_mgr.play_hound_death()

        parent = self.node.getParent() if (hasattr(self, 'node') and not self.node.isEmpty() and not self.node.getParent().isEmpty()) else self.node
        self.debris_list, self.blast_light_np, self.puddle_np = create_monster_explosion(parent, self.pos, "hound", audio_mgr)
        self.blast_timer = 0.14

    def update_debris(self, dt):
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
        self.cleanup_elemental()
        if getattr(self, 'aura_is_lit', False) and hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.aura_np)
            self.aura_is_lit = False
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.aura_np.removeNode()
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
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """사격 레이캐스트와 도베르만 골격 히트박스 판정"""
        self.last_hit_was_head = False
        if self.is_corpse:
            return False, 999.0

        h_rad = math.radians(self.node.getH())
        sin_h, cos_h = math.sin(h_rad), math.cos(h_rad)
        s = self.node.getScale()[0] if hasattr(self, 'node') and self.node and not self.node.isEmpty() else (1.25 if getattr(self, 'is_elite', False) else 1.0)

        # (머리, 목, 흉곽/심장, 골반/엉덩이, 다리)
        targets = [
            # 뼈 두개골 및 주둥이 (헤드샷! 전방 0.52m, 고도 0.95m)
            (self.pos.x - sin_h * (0.52 * s), self.pos.y + cos_h * (0.52 * s), self.pos.z + 0.95 * s, 0.45 * s, True),
            # 흉곽 및 지옥불 심장 코어 (중앙, 고도 0.74m)
            (self.pos.x, self.pos.y, self.pos.z + 0.74 * s, 0.52 * s, False),
            # 골반 및 둔부 (후방 0.44m, 고도 0.72m)
            (self.pos.x + sin_h * (0.44 * s), self.pos.y - cos_h * (0.44 * s), self.pos.z + 0.72 * s, 0.46 * s, False),
            # 앞/뒷다리 지면 부근 (고도 0.35m)
            (self.pos.x, self.pos.y, self.pos.z + 0.35 * s, 0.45 * s, False),
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
        """이동 시 위치 및 방향 회전 (회피 중에는 도약 물리 반영)"""
        if self.is_dodging:
            self.update(dt, is_moving=False)
            return

        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            shake = math.sin(self.stun_timer * 65.0) * 0.06
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            return

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.pos.x = new_x
        self.pos.y = new_y
        if self.pos.z < floor_z:
            self.pos.z = floor_z
        elif self.pos.z > floor_z:
            self.pos.z = max(floor_z, self.pos.z - dt * 26.0)
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 14.0))

        target_p = 15.0 if s_type == 'ramp' else 0.0
        curr_p = self.node.getP()
        self.node.setP(curr_p + (target_p - curr_p) * min(1.0, dt * 10.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False, chunks=None):
        """애니메이션 및 회피 물리 갱신"""
        self.update_elemental(dt)
        # 1. 회피 도약(Evasive Dodge) 물리 및 롤링 갱신
        if self.is_dodging:
            self.dodge_timer -= dt
            if chunks:
                from collision import resolve_collision
                new_x, new_y = resolve_collision(chunks, self.pos.x, self.pos.y, self.dodge_vel.x * dt, self.dodge_vel.y * dt, radius=getattr(self, 'col_radius', 0.35))
                self.pos.x = new_x
                self.pos.y = new_y
            else:
                self.pos.x += self.dodge_vel.x * dt
                self.pos.y += self.dodge_vel.y * dt
            self.pos.z += self.dodge_vel.z * dt
            self.dodge_vel.z -= 16.0 * dt
            if self.pos.z < 0.0:
                self.pos.z = 0.0
                self.dodge_vel.z = 0.0
            self.node.setPos(self.pos)

            p_left = max(0.0, self.dodge_timer / 0.35)
            self.node.setR(self.node.getR() * (0.92))
            if self.dodge_timer <= 0.0:
                self.is_dodging = False
                self.node.setR(0)
                self.node.setP(0)
                self.pos.z = 0.0
                self.node.setPos(self.pos)
            return

        if self.stun_timer > 0.0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            return

        # 2. 이동/질주 애니메이션 (Canine Gallop Cycle)
        if is_moving:
            self.anim_time += dt * 15.0
            t = self.anim_time

            # 4족 질주 사이클: 앞다리와 뒷다리의 역동적 교대 보행
            self.leg_fl['upper'].setP(math.sin(t) * 35.0)
            self.leg_fl['elbow'].setP(max(0.0, math.cos(t) * 42.0))
            self.leg_fr['upper'].setP(math.sin(t + math.pi) * 35.0)
            self.leg_fr['elbow'].setP(max(0.0, math.cos(t + math.pi) * 42.0))

            self.leg_bl['femur'].setP(math.sin(t + math.pi * 0.8) * 36.0)
            self.leg_bl['knee'].setP(-max(0.0, math.cos(t + math.pi * 0.8) * 42.0))
            self.leg_br['femur'].setP(math.sin(t - math.pi * 0.2) * 36.0)
            self.leg_br['knee'].setP(-max(0.0, math.cos(t - math.pi * 0.2) * 42.0))

            # 척추 탄성 바운스 & 머리 질주 피치
            self.body_root.setZ(0.76 + math.sin(t * 2.0) * 0.05)
            self.body_root.setP(math.sin(t) * 5.0)
            self.head_pivot.setP(math.sin(t) * 8.0)
            self.jaw_pivot.setP(10.0 + abs(math.sin(t * 0.9)) * 16.0)
            self.tail_pivot.setH(math.sin(t * 1.6) * 16.0)
        else:
            # 3. 대기 / 공격 애니메이션 (Idle Stance / Snapping Attack)
            self.anim_time += dt * 3.5
            t = self.anim_time

            if is_attacking:
                # 급습 물어뜯기 자세 (Lunge & Snap)
                self.jaw_pivot.setP(38.0)
                self.head_pivot.setP(16.0)
                self.body_root.setP(-8.0)
            else:
                self.body_root.setZ(0.76 + math.sin(t * 2.0) * 0.02)
                self.body_root.setP(0)
                self.head_pivot.setH(math.sin(t * 1.2) * 5.0)
                self.head_pivot.setP(-3.0 + math.sin(t * 1.8) * 4.0)
                self.jaw_pivot.setP(6.0 + abs(math.sin(t * 1.4)) * 12.0)
                self.tail_pivot.setH(math.sin(t * 2.6) * 10.0)

                # 다리 원위치
                self.leg_fl['upper'].setP(0)
                self.leg_fl['elbow'].setP(0)
                self.leg_fr['upper'].setP(0)
                self.leg_fr['elbow'].setP(0)
                self.leg_bl['femur'].setP(0)
                self.leg_bl['knee'].setP(0)
                self.leg_br['femur'].setP(0)
                self.leg_br['knee'].setP(0)

        # 지옥불 심장 및 전신 붉은색 혈관 선(Hellfire Veins) 전체 맥동 (Pulsing Hellfire Bloodlines)
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 6.5)

        # 1) 심장 코어: 갈비뼈 내부의 초소형 불씨 피벗만 미세하게 맥동 (절대 거대화되지 않고 3~4cm 유지)
        if hasattr(self, 'heart_pivot') and self.heart_pivot and not self.heart_pivot.isEmpty():
            self.heart_pivot.setScale(0.85 + pulse * 0.30)
        if hasattr(self, 'heart_core') and self.heart_core and not self.heart_core.isEmpty():
            self.heart_core.setColorScale(1.0, 0.18 + pulse * 0.35, 0.05 + pulse * 0.12, 1.0)

        # 2) 몸 전체 붉은색 혈관선 일제히 맥동 (어두운 주홍빛 -> 강렬한 핏빛 지옥불 발광)
        if hasattr(self, 'hellfire_vein_nodes') and self.hellfire_vein_nodes:
            r_glow = 1.0
            g_glow = 0.10 + pulse * 0.32
            b_glow = 0.02 + pulse * 0.08
            alpha = 0.65 + pulse * 0.35
            for vn in self.hellfire_vein_nodes:
                if vn and not vn.isEmpty():
                    vn.setColorScale(r_glow, g_glow, b_glow, alpha)


class CableOverlordBoss(ElementalMonsterMixin):
    col_radius = 0.55
    """
    [ 백룸 거대 보스 엔티티: 케이블 엔티티 - 심연의 지배자 (Cable Overlord Boss) ]
    - 높이 약 4.5m의 거대한 고압 절연 케이블 타래, 구리 도선 코일 및 중장갑 골격체
    - 흉부 중앙에 맥동하는 심연의 코어 펄스 라이트 (PointLight)
      (페이즈 1: 청록/시안 발광 -> 페이즈 2 폭주: 타오르는 핏빛 진홍색 발광 및 방전)
    - 4개의 초대형 절연 관절 촉수 (상단 2개 4.2m 채찍 텐타클, 하단 2개 지주 보행 다리)
    - 2페이즈 전투 패턴:
      1) 촉수 강타 채찍질 (Cable Lash - 근접 5.8m)
      2) 지면 강타 충격파 (Ground Shockwave Slam - 반경 18m 지진/슬로우)
      3) 유도 전선 침 발사 (Homing Wire Darts - 3연장 고전압 투사체)
      4) [페이즈 2: 체력 50% 이하 폭주] 이동 속도 +45%, 사이렌 알람, 하수인 2체 소환, 주기적 EMP 방전
    """
    def __init__(self, parent, start_x, start_y):
        self.parent_ref = parent
        self.node = parent.attachNewNode("cable_overlord_boss")
        floor_z, _ = get_floor_height(start_x, start_y)
        self.pos = Vec3(start_x, start_y, floor_z)
        self.node.setPos(self.pos)
        self.name = "케이블 엔티티: 심연의 지배자"
        self.is_boss = True
        self.max_hp = 3500
        self.hp = self.max_hp
        self.phase = 1
        self.speed = 4.8
        self.col_radius = 0.55
        self.attack_damage = 32
        self.exp_value = 800
        self.anim_time = 0.0
        self.stun_timer = 0.0
        self.is_corpse = False
        self.is_dead = False
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.last_hit_was_head = False
        self.debris_list = []
        self.blast_light_np = None

        # 상태이상 타이머
        self.burn_timer = 0.0
        self.burn_dps = 0.0

        # 보스 특수 스킬 쿨다운
        self.cable_lash_cooldown = 2.0
        self.shockwave_cooldown = 5.0
        self.dart_cooldown = 4.0
        self.emp_cooldown = 10.0
        self.summon_cooldown = 15.0
        self.is_lashing = False
        self.lash_timer = 0.0

        # 색상 팔레트
        cable_black = LColor(0.06, 0.06, 0.08, 1.0)
        cable_dark_metal = LColor(0.14, 0.15, 0.18, 1.0)
        copper_coil = LColor(0.72, 0.44, 0.18, 1.0)
        core_cyan = LColor(0.20, 0.95, 1.0, 1.0)
        visor_glow = LColor(1.0, 0.25, 0.15, 1.0)
        steel_armor = LColor(0.26, 0.28, 0.32, 1.0)

        self.root_pivot = self.node.attachNewNode("boss_pivot")

        # 1. 흉부 및 몸통 골격 (Torso & Cable Bundles, Z=1.6 ~ 3.2m)
        self.torso = self.root_pivot.attachNewNode("boss_torso")
        self.torso.setPos(0, 0, 2.2)

        # 주 척추 기둥
        make_cube_to(self.torso, 0.85, 0.75, 1.70, cable_black, 0, 0, 0)
        # 구리 전선 코일 감개
        make_cube_to(self.torso, 0.98, 0.88, 0.35, copper_coil, 0, 0, 0.45)
        make_cube_to(self.torso, 0.98, 0.88, 0.35, copper_coil, 0, 0, -0.45)
        # 등 뒤 고전압 배전반 & 방열 핀
        make_cube_to(self.torso, 1.20, 0.40, 1.30, steel_armor, 0, -0.48, 0.10)
        make_cube_to(self.torso, 0.25, 0.50, 0.08, copper_coil, -0.40, -0.52, 0.35)
        make_cube_to(self.torso, 0.25, 0.50, 0.08, copper_coil, 0.40, -0.52, 0.35)

        # 2. 흉부 중앙 심연의 에너지 코어 (Abyssal Pulsating Core)
        self.core_geom = make_sphere_to(self.torso, 0.48, 0.48, 0.48, core_cyan, 0, 0.32, 0.05, rot_h=45, rot_p=45)
        self.core_geom.setLightOff()

        # 코어 자체 발광 포인트라이트
        self.core_light = PointLight("boss_core_light")
        self.core_light.setColor((1.2, 3.8, 5.0, 1.0))
        self.core_light.setAttenuation((1.0, 0.12, 0.025))
        self.core_light_np = self.torso.attachNewNode(self.core_light)
        self.core_light_np.setPos(0, 0.45, 0.05)
        parent.setLight(self.core_light_np)

        # 3. 흉포한 케이블 머리 & 투구 (Head & Menacing Visor, Z=3.3 ~ 4.4m)
        self.head_pivot = self.torso.attachNewNode("boss_head")
        self.head_pivot.setPos(0, 0.22, 1.15)
        make_cube_to(self.head_pivot, 0.65, 0.60, 0.70, cable_black, 0, 0, 0)
        # 뿔 형태의 강철 침 (Horns)
        horn_l = make_cube_to(self.head_pivot, 0.12, 0.12, 0.85, steel_armor, -0.35, -0.10, 0.45, rot_h=-18, rot_r=-24)
        horn_r = make_cube_to(self.head_pivot, 0.12, 0.12, 0.85, steel_armor, 0.35, -0.10, 0.45, rot_h=18, rot_r=24)
        # 발광 바이저 안광 (Visor Slit Eyes)
        self.visor_eye = make_cube_to(self.head_pivot, 0.48, 0.10, 0.12, visor_glow, 0, 0.32, 0.08)
        self.visor_eye.setLightOff()

        # 4. 상단 2개 거대 타격 촉수 채찍 (Upper Tentacle Lashers - Left & Right, 길이 ~4.2m)
        self.lash_l_segments = []
        self.lash_r_segments = []

        # (1) 좌측 상단 촉수
        prev_node = self.torso.attachNewNode("lash_l_root")
        prev_node.setPos(-0.75, 0.15, 0.55)
        for s in range(5):
            seg_node = prev_node.attachNewNode(f"lash_l_seg_{s}")
            seg_len = 0.80 - s * 0.06
            thick = 0.24 - s * 0.03
            col = copper_coil if (s % 2 == 1) else cable_black
            make_cube_to(seg_node, thick, seg_len, thick, col, 0, seg_len * 0.5, 0)
            self.lash_l_segments.append(seg_node)
            prev_node = seg_node.attachNewNode("next_joint")
            prev_node.setPos(0, seg_len, 0)

        # (2) 우측 상단 촉수
        prev_node = self.torso.attachNewNode("lash_r_root")
        prev_node.setPos(0.75, 0.15, 0.55)
        for s in range(5):
            seg_node = prev_node.attachNewNode(f"lash_r_seg_{s}")
            seg_len = 0.80 - s * 0.06
            thick = 0.24 - s * 0.03
            col = copper_coil if (s % 2 == 1) else cable_black
            make_cube_to(seg_node, thick, seg_len, thick, col, 0, seg_len * 0.5, 0)
            self.lash_r_segments.append(seg_node)
            prev_node = seg_node.attachNewNode("next_joint")
            prev_node.setPos(0, seg_len, 0)

        # 5. 하단 2개 중장갑 지주 보행 다리 (Lower Heavy Struts - Left & Right)
        self.strut_l = self.root_pivot.attachNewNode("strut_l")
        self.strut_l.setPos(-0.65, 0, 1.4)
        make_cube_to(self.strut_l, 0.32, 0.38, 1.35, cable_dark_metal, 0, 0, -0.65, rot_p=-12)
        make_cube_to(self.strut_l, 0.55, 0.70, 0.25, steel_armor, 0, 0.15, -1.35)

        self.strut_r = self.root_pivot.attachNewNode("strut_r")
        self.strut_r.setPos(0.65, 0, 1.4)
        make_cube_to(self.strut_r, 0.32, 0.38, 1.35, cable_dark_metal, 0, 0, -0.65, rot_p=-12)
        make_cube_to(self.strut_r, 0.55, 0.70, 0.25, steel_armor, 0, 0.15, -1.35)

    def stun(self, duration):
        """보스는 강력한 질량 저항으로 인해 스턴 시간이 70% 감쇄됨"""
        self.stun_timer = max(self.stun_timer, duration * 0.30)

    def apply_burn(self, dps=25.0, duration=3.0):
        """용의 숨결 특성 지속 화염 피해 적용 및 원소 시각 효과 연동"""
        super().apply_burn(dps, duration)

    def take_damage(self, dmg, apply_knockback=None, hit_dir=None, damage_type=None):
        """보스 피해 적용 및 UI 보스 체력바 갱신"""
        self.hp = max(0, self.hp - dmg)
        if damage_type == 'fire':
            self.apply_burn(dps=max(20.0, dmg * 0.4), duration=3.0)
        elif damage_type == 'electric':
            entry_pos = (self.pos - hit_dir * 0.25) if hit_dir is not None else None
            self.apply_shock(damage=0.0, duration=0.65, hit_pos=entry_pos)

        # 피격 순간 코어 라이트 섬광
        if hasattr(self, 'core_light') and self.core_light:
            self.core_light.setColor((5.0, 5.0, 5.0, 1.0))

        if self.hp <= 0:
            return True
        return False

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """보스 레이캐스트 적중 판정 (두부 헤드샷, 흉부 코어, 하단부 판정)"""
        self.last_hit_was_head = False
        targets = [
            # 1) 머리 (Headshot 영역)
            (self.pos.x, self.pos.y, self.pos.z + 3.85, 0.85, True),
            # 2) 흉부 코어 (Center Core 영역)
            (self.pos.x, self.pos.y, self.pos.z + 2.30, 1.40, False),
            # 3) 하단부 외골격
            (self.pos.x, self.pos.y, self.pos.z + 1.10, 1.55, False),
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

    def turn_into_corpse(self, audio_mgr=None):
        """보스 격파 시 대폭발 및 전선 파편 비산"""
        self.is_corpse = True
        self.is_dead = True
        self.hp = 0
        self.cleanup_elemental()

        if hasattr(self, 'core_light_np') and self.core_light_np and not self.core_light_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.core_light_np)
            self.core_light_np.removeNode()

        create_monster_explosion(self.parent_ref, self.pos, "boss", audio_mgr)
        self.node.hide()

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y, wall_norm=None, climb_target_z=0.0):
        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            return

        floor_z, s_type = get_floor_height(new_x, new_y, self.pos.z)
        self.pos.x = new_x
        self.pos.y = new_y
        if self.pos.z < floor_z:
            self.pos.z = floor_z
        elif self.pos.z > floor_z:
            self.pos.z = max(floor_z, self.pos.z - dt * 20.0)
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 6.0))
        self.update(dt, is_moving=True)

    def update(self, dt, is_moving=False, is_attacking=False):
        """보스 4.5m 촉수 파동, 코어 맥동 및 모션 갱신"""
        self.anim_time += dt * (7.5 if self.phase == 2 else 4.2)
        phase = self.anim_time

        # 화염 지속 피해 및 전기 원소 시각 효과 갱신
        self.update_elemental(dt)

        # 스킬 쿨다운 감소
        if self.cable_lash_cooldown > 0.0:
            self.cable_lash_cooldown -= dt
        if self.shockwave_cooldown > 0.0:
            self.shockwave_cooldown -= dt
        if self.dart_cooldown > 0.0:
            self.dart_cooldown -= dt

        # 머리 회전 및 호흡 바운스
        self.head_pivot.setH(math.sin(phase * 0.6) * 12.0)
        self.head_pivot.setP(math.sin(phase * 0.4) * 6.0)
        self.torso.setZ(2.2 + math.sin(phase * 0.8) * 0.08)

        # 흉부 코어 맥동 발광
        pulse = 0.5 + 0.5 * math.sin(phase * 3.5)
        if hasattr(self, 'core_light') and self.core_light:
            if self.phase == 2:
                self.core_light.setColor((2.8 + pulse * 1.5, 0.2 + pulse * 0.3, 0.2, 1.0))
                if hasattr(self, 'core_geom') and not self.core_geom.isEmpty():
                    self.core_geom.setColorScale(1.0, 0.15 + pulse * 0.3, 0.15, 1.0)
            else:
                self.core_light.setColor((0.8 + pulse * 0.6, 2.8 + pulse * 1.2, 4.0 + pulse * 1.5, 1.0))
                if hasattr(self, 'core_geom') and not self.core_geom.isEmpty():
                    self.core_geom.setColorScale(0.2, 0.9 + pulse * 0.1, 1.0, 1.0)

        # 상단 2개 촉수 사인파 파동 (Sinusoidal Writhing Motion)
        for i, seg in enumerate(self.lash_l_segments):
            seg_phase = phase + i * 0.65
            sway_h = math.sin(seg_phase) * (18.0 + i * 4.0)
            sway_p = math.cos(seg_phase * 0.8) * (14.0 + i * 3.5)
            if self.is_lashing:
                seg.setH(sway_h * 0.4 - 35.0)
                seg.setP(sway_p * 0.4 + 45.0)
            else:
                seg.setH(sway_h)
                seg.setP(sway_p)

        for i, seg in enumerate(self.lash_r_segments):
            seg_phase = phase - i * 0.65
            sway_h = -math.sin(seg_phase) * (18.0 + i * 4.0)
            sway_p = math.cos(seg_phase * 0.8) * (14.0 + i * 3.5)
            if self.is_lashing:
                seg.setH(sway_h * 0.4 + 35.0)
                seg.setP(sway_p * 0.4 + 45.0)
            else:
                seg.setH(sway_h)
                seg.setP(sway_p)

        # 채찍 공격 타이머 해제
        if self.is_lashing:
            self.lash_timer -= dt
            if self.lash_timer <= 0.0:
                self.is_lashing = False

        # 보행 시 하단 지주 다리 보행 애니메이션
        if is_moving:
            step_angle = math.sin(phase * 1.4) * 22.0
            self.strut_l.setP(step_angle)
            self.strut_r.setP(-step_angle)
        else:
            self.strut_l.setP(0)
            self.strut_r.setP(0)

    def destroy(self):
        """노드 및 라이트 자원 완전 해제"""
        self.cleanup_elemental()
        if hasattr(self, 'core_light_np') and self.core_light_np and not self.core_light_np.isEmpty():
            if hasattr(self, 'parent_ref') and self.parent_ref and not self.parent_ref.isEmpty():
                self.parent_ref.clearLight(self.core_light_np)
            self.core_light_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

