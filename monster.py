import math
from panda3d.core import Vec3, LColor, PointLight, ClockObject, NodePath
from geometry import make_cube

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
        self.pos = Vec3(start_x, start_y, 0.28)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.wall_tilt = 0.0
        self.climb_z = 0.28

        black = LColor(0.015, 0.015, 0.02, 1.0)
        scale_black = LColor(0.025, 0.025, 0.035, 1.0)
        eye_yellow_red = LColor(1.0, 0.25, 0.05, 1.0)
        tongue_red = LColor(0.85, 0.03, 0.03, 1.0)
        fang_ivory = LColor(0.92, 0.90, 0.82, 1.0)

        # 틸트 및 몸체 루트
        self.tilt_root = self.node.attachNewNode("tilt_root")
        self.body_root = self.tilt_root.attachNewNode("body_root")

        # 1. 뱀 머리 (Head - 전방을 향해 쐐기형으로 뻗은 사나운 독사 머리)
        self.head = make_cube('serpent_head', 0.68, 0.88, 0.38, black)
        self.head.setPos(0, 0.20, 0)
        self.head.reparentTo(self.body_root)

        # 머리 상단 비늘 능선
        crest = make_cube('crest', 0.38, 0.70, 0.12, scale_black)
        crest.setPos(0, 0.15, 0.22)
        crest.reparentTo(self.head)

        # 2. 날카로운 송곳니 (Fangs)
        self.fang_l = make_cube('fang_l', 0.06, 0.08, 0.22, fang_ivory)
        self.fang_l.setPos(-0.18, 0.52, -0.15)
        self.fang_l.setP(18)
        self.fang_l.reparentTo(self.head)

        self.fang_r = make_cube('fang_r', 0.06, 0.08, 0.22, fang_ivory)
        self.fang_r.setPos(0.18, 0.52, -0.15)
        self.fang_r.setP(18)
        self.fang_r.reparentTo(self.head)

        # 3. 날름거리는 붉은 갈라진 혀 (Forked Tongue)
        self.tongue = make_cube('tongue', 0.10, 0.45, 0.03, tongue_red)
        self.tongue.setPos(0, 0.55, -0.06)
        self.tongue.setLightOff()
        self.tongue.reparentTo(self.head)

        # 4. 번뜩이는 뱀 눈 (Slit-pupil Eyes)
        eye_l = make_cube('eye_l', 0.07, 0.06, 0.08, eye_yellow_red)
        eye_l.setPos(-0.24, 0.32, 0.12)
        eye_l.setLightOff()
        eye_l.reparentTo(self.head)

        eye_r = make_cube('eye_r', 0.07, 0.06, 0.08, eye_yellow_red)
        eye_r.setPos(0.24, 0.32, 0.12)
        eye_r.setLightOff()
        eye_r.reparentTo(self.head)

        # 5. 14개의 유연한 몸통 마디 (Segmented Undulating Body, 총 연장 ~8.5m)
        self.segments = []
        for i in range(14):
            t = i / 13.0
            # 머리 뒤쪽에서 굵어졌다가 꼬리로 갈수록 자연스럽게 가늘어지는 비례
            thickness = math.sin((1.0 - t * 0.85) * math.pi * 0.5)
            sx = 0.62 * thickness
            sy = 0.62 * (1.0 - t * 0.25)
            sz = 0.38 * thickness

            seg_pivot = self.body_root.attachNewNode(f"seg_pivot_{i}")
            seg_pivot.setPos(0, -(i + 1) * 0.55, 0)
            seg_geom = make_cube(f"seg_geom_{i}", max(0.12, sx), max(0.20, sy), max(0.10, sz), black)
            seg_geom.reparentTo(seg_pivot)
            self.segments.append({
                'pivot': seg_pivot,
                'geom': seg_geom,
                'base_y': -(i + 1) * 0.55,
                'idx': i
            })

        # 6. 핏빛 암흑 오라 조명
        aura_light = PointLight('serpent_aura')
        aura_light.setColor((0.85, 0.05, 0.05, 1.0))
        aura_light.setAttenuation((1.0, 0.05, 0.010))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 0.6)
        parent.setLight(self.aura_np)

    def reset_pos(self, x, y, z=0.28):
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

        for seg in self.segments:
            seg['pivot'].setPos(0, seg['base_y'], 0)
            seg['pivot'].setH(0)

        self.head.setH(0)
        self.head.setP(0)

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y, wall_norm=None, climb_target_z=0.28):
        """위치 갱신 및 벽 타기(Wall Crawling) 슬리더링 물리 적용"""
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
        if is_attacking:
            # 점프스케어 공격 포즈: 머리를 바짝 쳐들고 독니와 혀를 활짝 벌림
            self.head.setP(-35)
            self.head.setZ(0.35)
            self.tongue.setPos(0, 0.85, -0.06)
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

            # 14개 마디 사인파 S자 파동 전파 (Sinusoidal Undulation)
            for seg in self.segments:
                i = seg['idx']
                seg_phase = phase - (i + 1) * 0.48
                # 꼬리로 갈수록 파동의 진폭이 유연하게 확장
                amplitude = 0.38 + (i / 14.0) * 0.32
                lateral_x = math.sin(seg_phase) * amplitude
                seg_angle = math.cos(seg_phase) * (26.0 + i * 1.5)

                seg['pivot'].setPos(lateral_x, seg['base_y'], math.sin(seg_phase * 0.5) * 0.04)
                seg['pivot'].setH(seg_angle)

            # 날름거리는 혀 모션
            tongue_flick = 0.55 + abs(math.sin(phase * 2.2)) * 0.28
            self.tongue.setPos(0, tongue_flick, -0.06)
        else:
            # 정지 상태: 서서히 몸체를 사리고 혀를 간헐적으로 날름거림
            t = ClockObject.getGlobalClock().getFrameTime()
            self.head.setH(math.sin(t * 1.8) * 5.0)
            self.head.setP(math.sin(t * 1.2) * 3.0)
            tongue_flick = 0.55 + abs(math.sin(t * 3.5)) * 0.18
            self.tongue.setPos(0, tongue_flick, -0.06)
            for seg in self.segments:
                i = seg['idx']
                seg['pivot'].setPos(math.sin(t * 1.2 + i * 0.3) * 0.12, seg['base_y'], 0)


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
        self.has_los = False

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

        for arm in self.arms:
            arm['upper'].setP(0)
            arm['forearm'].setP(0)
        for leg in self.legs:
            leg['femur'].setP(0)
            leg['knee'].setP(0)

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        """위치 갱신 및 시선 회전"""
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


# 기존 호환용 별칭
CreepySpiderMonster = LongBlackSerpent
TallShadowMonster = TallSkeletonMonster
