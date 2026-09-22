import math
from panda3d.core import Vec3, LColor, PointLight, ClockObject, NodePath
from geometry import make_cube

class CreepySpiderMonster:
    """
    벽을 타고 기어오르는 기괴한 8족 거미 형상의 백룸 추격 괴물 엔티티
    - 8개의 긴 2단 관절 다리, 기괴하게 들썩이는 복부, 번뜩이는 6개의 붉은 안광
    - 복도 벽면에 인접하거나 추격할 때 벽면(Z = 2.5 ~ 4.5m)을 타고 수직으로 올라가
      기괴하게 기어오르는 Wall-Crawling 물리 및 틸트(Roll/Pitch) 적용
    - 고속 스커틀링(Scuttling) 다리 교차 애니메이션
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("creepy_spider_monster")
        self.pos = Vec3(start_x, start_y, 1.25)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.wall_tilt = 0.0      # 0.0 = 바닥, 1.0 = 벽면 완전 밀착
        self.curr_wall_norm = Vec3(0, 0, 0)
        self.climb_z = 1.25       # 긴 다리로 공중에 부유하는 기준 고도 (1.25m)

        black = LColor(0.02, 0.02, 0.025, 1.0)
        chitin_dark = LColor(0.035, 0.025, 0.025, 1.0)
        eye_red = LColor(1.0, 0.03, 0.03, 1.0)

        # 1. 벽면 틸트 및 회전용 중간 노드 (Wall Tilt Pivot)
        self.tilt_root = self.node.attachNewNode("tilt_root")
        self.body_root = self.tilt_root.attachNewNode("body_root")

        # 2. 흉두부 (Cephalothorax / Carapace - 납작하고 각진 외골격)
        self.carapace = make_cube('carapace', 0.85, 0.95, 0.35, chitin_dark)
        self.carapace.setPos(0, 0.1, 0)
        self.carapace.reparentTo(self.body_root)

        # 3. 복부 (Abdomen - 뒤쪽으로 높게 치솟은 거대한 거미 배)
        self.abdomen = make_cube('abdomen', 1.15, 1.45, 0.75, black)
        self.abdomen.setPos(0, -1.05, 0.25)
        self.abdomen.setP(-14)
        self.abdomen.reparentTo(self.body_root)

        # 4. 앞쪽 치명적인 독니 (Chelicerae / Fangs)
        self.fang_l = make_cube('fang_l', 0.12, 0.16, 0.38, black)
        self.fang_l.setPos(-0.18, 0.62, -0.15)
        self.fang_l.setP(25)
        self.fang_l.reparentTo(self.body_root)

        self.fang_r = make_cube('fang_r', 0.12, 0.16, 0.38, black)
        self.fang_r.setPos(0.18, 0.62, -0.15)
        self.fang_r.setP(25)
        self.fang_r.reparentTo(self.body_root)

        # 5. 어둠 속에서 번뜩이는 6개의 붉은 거미 눈 클러스터 (Glowing Unlit Red Eyes)
        eye_coords = [
            (-0.14, 0.58, 0.16, 0.07),   # 전면 주안 좌
            (0.14, 0.58, 0.16, 0.07),    # 전면 주안 우
            (-0.30, 0.50, 0.12, 0.05),   # 측면 보조안 좌
            (0.30, 0.50, 0.12, 0.05),    # 측면 보조안 우
            (-0.20, 0.54, 0.06, 0.05),   # 하단 보조안 좌
            (0.20, 0.54, 0.06, 0.05)     # 하단 보조안 우
        ]
        self.eyes = []
        for ex, ey, ez, sz in eye_coords:
            eye = make_cube('spider_eye', sz, 0.04, sz, eye_red)
            eye.setPos(ex, ey, ez)
            eye.setLightOff()
            eye.reparentTo(self.body_root)
            self.eyes.append(eye)

        # 6. 기괴한 8개의 극도로 긴 2단 관절 다리 (Ultra-long Spindly Legs - 전폭 ~6m 초대형 거미 다리)
        # 좌측 4개 (L1, L2, L3, L4), 우측 4개 (R1, R2, R3, R4)
        self.legs = []  # [(coxa_pivot, femur_node, tibia_pivot, tibia_node, base_h, side_sign), ...]
        leg_configs = [
            # (side: -1=좌, 1=우, index, base_y, base_h, femur_p, tibia_p)
            (-1, 0, 0.38, 45, -35, 68),    # L1 (전방 좌)
            (1, 0, 0.38, -45, -35, 68),    # R1 (전방 우)
            (-1, 1, 0.12, 80, -38, 72),    # L2 (전측 좌)
            (1, 1, 0.12, -80, -38, 72),    # R2 (전측 우)
            (-1, 2, -0.15, 105, -40, 74),  # L3 (후측 좌)
            (1, 2, -0.15, -105, -40, 74),  # R3 (후측 우)
            (-1, 3, -0.42, 140, -36, 70),  # L4 (후방 좌)
            (1, 3, -0.42, -140, -36, 70),  # R4 (후방 우)
        ]

        for side, idx, by, base_h, fem_p, tib_p in leg_configs:
            # 기저부 관절 피벗 (몸체에 연결)
            coxa_pivot = self.body_root.attachNewNode(f"leg_coxa_{side}_{idx}")
            coxa_pivot.setPos(side * 0.42, by, 0.05)
            coxa_pivot.setH(base_h)

            # 1단 상완 허벅지 (Femur: 하늘 높이 치솟는 2.6m의 긴 다리 관절)
            femur_pivot = coxa_pivot.attachNewNode("femur_pivot")
            femur_pivot.setP(fem_p)
            femur_geom = make_cube("femur_geom", 0.09, 0.09, 2.60, chitin_dark)
            femur_geom.setPos(0, 0, 1.25)
            femur_geom.reparentTo(femur_pivot)

            # 2단 하완 종아리 (Tibia: 바닥과 벽면을 향해 날카롭게 꺾여 뻗는 3.6m의 극도로 긴 바늘 다리)
            tibia_pivot = femur_pivot.attachNewNode("tibia_pivot")
            tibia_pivot.setPos(0, 0, 2.50)
            tibia_pivot.setP(tib_p)
            tibia_geom = make_cube("tibia_geom", 0.06, 0.06, 3.60, black)
            tibia_geom.setPos(0, 0, -1.75)
            tibia_geom.reparentTo(tibia_pivot)

            self.legs.append({
                'coxa': coxa_pivot,
                'femur': femur_pivot,
                'tibia': tibia_pivot,
                'base_h': base_h,
                'fem_p': fem_p,
                'tib_p': tib_p,
                'side': side,
                'idx': idx
            })

        # 7. 기괴한 붉은색 오라 조명 (접근 시 복도 벽면에 핏빛 투영)
        aura_light = PointLight('monster_aura')
        aura_light.setColor((0.85, 0.04, 0.04, 1.0))
        aura_light.setAttenuation((1.0, 0.05, 0.009))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 0.8)
        parent.setLight(self.aura_np)

    def reset_pos(self, x, y, z=1.25):
        """괴물 위치 및 상태 초기화"""
        self.pos = Vec3(x, y, z)
        self.node.setPos(self.pos)
        self.node.setH(0)
        self.tilt_root.setHpr(0, 0, 0)
        self.wall_tilt = 0.0
        self.curr_wall_norm = Vec3(0, 0, 0)
        self.climb_z = z
        self.path = []
        self.path_timer = 0.0
        self.has_los = False

        for leg in self.legs:
            leg['coxa'].setH(leg['base_h'])
            leg['femur'].setP(leg['fem_p'])
            leg['tibia'].setP(leg['tib_p'])

        self.fang_l.setH(0)
        self.fang_r.setH(0)
        self.abdomen.setScale(1.0)

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y, wall_norm=None, climb_target_z=1.25):
        """
        위치 갱신 및 벽 타기(Wall Crawling) 물리 적용:
        - 벽면 인접 시 벽면 법선 방향으로 몸체를 틸트하고 높은 고도(2.5~4.5m)로 수직 기어오름
        - 이동 방향을 향한 부드러운 시선 회전
        """
        # 고도(Z축) 보간 (바닥 <-> 벽면 오르내리기)
        self.climb_z += (climb_target_z - self.climb_z) * min(1.0, dt * 4.5)
        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = self.climb_z
        self.node.setPos(self.pos)

        # 수평 이동 방향 회전
        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))

        # 벽면 법선 기반 몸체 기울임 (Wall Crawling Tilt)
        target_wall_tilt = 1.0 if (wall_norm is not None and self.climb_z > 1.2) else 0.0
        self.wall_tilt += (target_wall_tilt - self.wall_tilt) * min(1.0, dt * 5.0)

        if self.wall_tilt > 0.02 and wall_norm is not None:
            # 벽면의 배면에 달라붙는 롤/피치 각도 계산
            # 이동 방향 벡터와 벽면 법선 벡터의 외적으로 롤 각도 산출
            # 벽면이 좌측/우측일 때 옆으로 85도 기울여 벽에 붙음
            h_rad = math.radians(self.node.getH())
            fwd_x = -math.sin(h_rad)
            fwd_y = math.cos(h_rad)
            rgt_x = math.cos(h_rad)
            rgt_y = math.sin(h_rad)

            # 벽면 법선과 플레이어 우측 벡터의 내적
            dot_rgt = wall_norm.x * rgt_x + wall_norm.y * rgt_y
            target_roll = -dot_rgt * 82.0 * self.wall_tilt
            curr_r = self.tilt_root.getR()
            self.tilt_root.setR(curr_r + (target_roll - curr_r) * min(1.0, dt * 6.0))
        else:
            curr_r = self.tilt_root.getR()
            self.tilt_root.setR(curr_r * max(0.0, 1.0 - dt * 6.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """8개 다리의 고속 스커틀링(Scuttling) 보행 및 기괴한 호흡/공격 애니메이션"""
        if is_attacking:
            # 점프스케어 공격 포즈: 전방 다리를 높이 치켜들고 독니를 쩍 벌림
            for leg in self.legs:
                idx = leg['idx']
                if idx in (0, 1):
                    leg['femur'].setP(-65)
                    leg['tibia'].setP(-20)
                else:
                    leg['femur'].setP(15)
                    leg['tibia'].setP(75)
            self.fang_l.setH(-35)
            self.fang_r.setH(35)
            self.abdomen.setP(22)
            self.body_root.setZ(0.25)
            return

        if is_moving:
            # 8족 고속 교차 보행 (Tetrapod Scuttling Gait, 13Hz 속도감)
            self.anim_time += dt * 13.5
            phase = self.anim_time

            for leg in self.legs:
                side = leg['side']
                idx = leg['idx']
                base_h = leg['base_h']
                fem_p = leg['fem_p']
                tib_p = leg['tib_p']

                # 4개씩 엇갈리는 역위상 스텝 (Group A: (L0, R1, L2, R3) vs Group B: (R0, L1, R2, L3))
                is_group_a = ((side == -1 and idx % 2 == 0) or (side == 1 and idx % 2 == 1))
                step_val = math.sin(phase) if is_group_a else -math.sin(phase)
                lift_val = max(0.0, math.cos(phase)) if is_group_a else max(0.0, -math.cos(phase))

                # 허벅지 전후 및 상하 리프팅
                leg['coxa'].setH(base_h + step_val * 16.0)
                leg['femur'].setP(fem_p - lift_val * 18.0)
                leg['tibia'].setP(tib_p + step_val * 12.0 + lift_val * 15.0)

            # 독니 찌르기 틱 동작
            fang_twitch = math.sin(phase * 1.5) * 12.0
            self.fang_l.setH(fang_twitch)
            self.fang_r.setH(-fang_twitch)

            # 복부 상하 반동 및 호흡 팽창
            self.abdomen.setP(-14 + math.sin(phase * 0.8) * 4.5)
            self.body_root.setZ(math.sin(phase * 2.0) * 0.04)
        else:
            # 정지 상태: 붉은 눈을 번뜩이며 그르렁거리는 복부 호흡 및 촉각 떨림
            t = ClockObject.getGlobalClock().getFrameTime()
            breath = 1.0 + 0.04 * math.sin(t * 3.2)
            self.abdomen.setScale(breath, breath, 1.0 + 0.06 * math.sin(t * 3.2))
            self.fang_l.setH(math.sin(t * 2.5) * 6.0)
            self.fang_r.setH(-math.sin(t * 2.5) * 6.0)
            self.body_root.setZ(math.sin(t * 2.0) * 0.02)


# 기존 코드 호환용 별칭
TallShadowMonster = CreepySpiderMonster
