import math
import random
from panda3d.core import (
    Vec3, LColor, PointLight, ClockObject, NodePath,
    GeomVertexFormat, GeomVertexData, GeomVertexWriter,
    Geom, GeomTriangles, GeomNode, TransparencyAttrib, LineSegs
)
from collision import ray_spheres_hit
from geometry import make_cube


def make_warning_ring(parent, name, radius, color):
    """광원을 추가하지 않는 공격 예고 원. 벽의 깊이 검사와 안개를 유지합니다."""
    lines = LineSegs(name)
    lines.setThickness(3.0)
    lines.setColor(*color)
    for i in range(49):
        angle = i * math.tau / 48
        point = (math.cos(angle) * radius, math.sin(angle) * radius, 0)
        if i == 0:
            lines.moveTo(*point)
        else:
            lines.drawTo(*point)
    node = parent.attachNewNode(lines.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.M_alpha)
    node.hide()
    return node


def create_blood_disc_feathered(name, radius, center_col, mid_col, edge_alpha=0.0, num_pts=24, rng=None, elongation=1.0, stretch_angle=0.0):
    """
    유기적인 혈흔 다각형 메시 생성:
    - 중심부는 짙고 응고된 고농도 혈흔
    - 중간부는 붉은 핏빛 체액
    - 외곽 가장자리는 알파 0.0으로 부드럽게 페더링되어 던전 바닥 타일에 완벽 밀착
    """
    if rng is None:
        rng = random.Random()
    format = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, format, Geom.UHStatic)
    vwriter = GeomVertexWriter(vdata, 'vertex')
    cwriter = GeomVertexWriter(vdata, 'color')

    # 0: 중심 정점
    vwriter.addData3(0, 0, 0)
    cwriter.addData4(center_col)

    p1 = rng.uniform(0, 6.28)
    p2 = rng.uniform(0, 6.28)
    p3 = rng.uniform(0, 6.28)
    cos_s = math.cos(stretch_angle)
    sin_s = math.sin(stretch_angle)

    edge_col = LColor(mid_col[0] * 0.7, mid_col[1] * 0.7, mid_col[2] * 0.7, edge_alpha)

    # 1 ~ num_pts: 중간 밀집 고리
    for i in range(num_pts):
        th = (2.0 * math.pi * i) / num_pts
        r = radius * 0.72 * (1.0 + 0.28 * math.sin(2 * th + p1) + 0.16 * math.cos(3 * th + p2) + rng.uniform(-0.05, 0.05))
        lx = r * math.cos(th)
        ly = r * math.sin(th) * elongation
        gx = lx * cos_s - ly * sin_s
        gy = lx * sin_s + ly * cos_s
        vwriter.addData3(gx, gy, 0)
        cwriter.addData4(mid_col)

    # num_pts+1 ~ 2*num_pts: 외곽 페더링 가장자리 (바닥에 스며드는 연출)
    for i in range(num_pts):
        th = (2.0 * math.pi * i) / num_pts
        r = radius * (1.0 + 0.32 * math.sin(2 * th + p1) + 0.20 * math.cos(3 * th + p2) + 0.12 * math.sin(5 * th + p3) + rng.uniform(-0.06, 0.06))
        lx = r * math.cos(th)
        ly = r * math.sin(th) * elongation
        gx = lx * cos_s - ly * sin_s
        gy = lx * sin_s + ly * cos_s
        vwriter.addData3(gx, gy, 0)
        cwriter.addData4(edge_col)

    geom = Geom(vdata)
    tris = GeomTriangles(Geom.UHStatic)
    # 내부 팬
    for i in range(num_pts):
        tris.addVertices(0, 1 + i, 1 + ((i + 1) % num_pts))

    # 외부 띠
    for i in range(num_pts):
        m1 = 1 + i
        m2 = 1 + ((i + 1) % num_pts)
        o1 = 1 + num_pts + i
        o2 = 1 + num_pts + ((i + 1) % num_pts)
        tris.addVertices(m1, o1, m2)
        tris.addVertices(m2, o1, o2)

    tris.closePrimitive()
    geom.addPrimitive(tris)
    gnode = GeomNode(name)
    gnode.addGeom(geom)
    return gnode


def create_organic_blood_pool(parent, world_x, world_y, base_radius=1.35,
                              center_col=LColor(0.03, 0.003, 0.003, 0.99),
                              mid_col=LColor(0.08, 0.008, 0.008, 0.92),
                              num_sub=3, num_drops=14, seed=None):
    """
    바닥에 수평으로 완벽 안착되는 다크판타지 유기적 혈흔 웅덩이 생성
    - parent: 월드 루트 (시체 회전에 영향받지 않음)
    - z=0.016: 바닥 타일 바로 위에 위치하여 z-fighting 없이 수평 밀착
    - 중심 풀 + 상처에서 번진 다엽성 부속 풀 + 사방으로 튄 핏방울 스패터
    """
    rng = random.Random(seed)
    root = parent.attachNewNode("organic_blood_pool")
    root.setPos(world_x, world_y, 0.016)
    root.setHpr(rng.uniform(0, 360), 0, 0)

    # 1. 메인 웅덩이 코어
    core = create_blood_disc_feathered("core", base_radius, center_col, mid_col, num_pts=32, rng=rng)
    root.attachNewNode(core)

    # 2. 상처 부위에서 번져나온 부속 혈흔 엽 (Sub-lobes)
    for i in range(num_sub):
        ang = rng.uniform(0, math.pi * 2)
        dist = base_radius * rng.uniform(0.35, 0.82)
        r = base_radius * rng.uniform(0.38, 0.65)
        elong = rng.uniform(1.1, 1.5)
        g = create_blood_disc_feathered(f"lobe_{i}", r, center_col, mid_col, num_pts=20, rng=rng, elongation=elong, stretch_angle=ang)
        np = root.attachNewNode(g)
        np.setPos(dist * math.cos(ang), dist * math.sin(ang), 0.001 * (i + 1))

    # 3. 비산된 위성 핏방울 및 튀김 흔적 (Satellite Splatters)
    for j in range(num_drops):
        ang = rng.uniform(0, math.pi * 2)
        dist = base_radius * rng.uniform(0.9, 2.3)
        r = rng.uniform(0.04, 0.18)
        elong = rng.uniform(1.2, 2.2) if rng.random() < 0.65 else 1.0
        g = create_blood_disc_feathered(f"drop_{j}", r, center_col, mid_col, num_pts=12, rng=rng, elongation=elong, stretch_angle=ang)
        np = root.attachNewNode(g)
        np.setPos(dist * math.cos(ang), dist * math.sin(ang), 0.001 * (j + 4))

    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setLightOff()
    return root


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
        self.max_hp = 75
        self.hp = self.max_hp
        self.exp_value = 35
        self.attack_damage = 30
        self.speed = 9.0

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

    def turn_into_corpse(self):
        """사망 시 시체로 전환: 바닥에 축 늘어지며 검붉은 독혈 웅덩이가 스며나옴"""
        self.is_corpse = True
        self.hp = 0
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        self.climb_z = 0.08
        self.pos.z = 0.08
        self.node.setPos(self.pos)
        self.tilt_root.setHpr(0, 0, 0)
        self.head.setP(0)
        self.head.setZ(-0.25)
        # 바닥에 수평 밀착되는 유기적 뱀 혈흔
        self.blood_pool_np = create_organic_blood_pool(
            parent=self.node.getParent(),
            world_x=self.pos.x,
            world_y=self.pos.y,
            base_radius=1.35,
            center_col=LColor(0.02, 0.003, 0.015, 0.99),
            mid_col=LColor(0.05, 0.006, 0.035, 0.92),
            num_sub=3, num_drops=12
        )
        self.blood_expand_timer = 0.0
        self.blood_expand_duration = 0.95
        self.blood_pool_np.setScale(0.06, 0.06, 1.0)

    def update_corpse(self, dt):
        """시체 혈흔이 상처에서 서서히 번져나오는 애니메이션"""
        if hasattr(self, 'blood_expand_timer') and self.blood_expand_timer < self.blood_expand_duration:
            self.blood_expand_timer += dt
            prog = min(1.0, self.blood_expand_timer / self.blood_expand_duration)
            scale = 1.0 - (1.0 - prog) ** 3
            if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
                self.blood_pool_np.setScale(scale, scale, 1.0)

    def destroy(self):
        """그래픽 및 내부 리소스 해제"""
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
            self.blood_pool_np.removeNode()
            self.blood_pool_np = None
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """플레이어 사격 레이캐스트와 뱀 머리/14마디 마디별 충돌 판정"""
        # 머리 및 주요 마디들의 월드 좌표 수집
        targets = [(self.pos.x, self.pos.y, self.pos.z + 0.3, 1.1)] # head: radius 1.1m
        h_rad = math.radians(self.node.getH())
        cos_h, sin_h = math.cos(h_rad), math.sin(h_rad)
        for i in range(0, 14, 2):
            seg = self.segments[i]
            by = seg['base_y']
            # 로컬 Y 오프셋을 월드 위치로 변환
            wx = self.pos.x + (-sin_h * by)
            wy = self.pos.y + (cos_h * by)
            targets.append((wx, wy, self.pos.z, 0.95))

        return ray_spheres_hit(ray_o, ray_d, targets, max_dist)

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
        self.max_hp = 65
        self.hp = self.max_hp
        self.exp_value = 30
        self.attack_damage = 35
        self.speed = 9.5

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

    def turn_into_corpse(self):
        """사망 시 거구 바닥에 시체로 대자로 눕기 및 골수암혈 웅덩이 확장"""
        self.is_corpse = True
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.18)
        self.node.setP(-88)
        self.node.setR(12)
        # 바닥에 수평 밀착되는 거대 골수 암혈 웅덩이
        self.blood_pool_np = create_organic_blood_pool(
            parent=self.node.getParent(),
            world_x=self.pos.x,
            world_y=self.pos.y,
            base_radius=1.65,
            center_col=LColor(0.03, 0.003, 0.003, 0.99),
            mid_col=LColor(0.08, 0.008, 0.008, 0.92),
            num_sub=4, num_drops=16
        )
        self.blood_expand_timer = 0.0
        self.blood_expand_duration = 1.05
        self.blood_pool_np.setScale(0.05, 0.05, 1.0)

    def update_corpse(self, dt):
        """시체 혈흔이 상처에서 서서히 번져나오는 애니메이션"""
        if hasattr(self, 'blood_expand_timer') and self.blood_expand_timer < self.blood_expand_duration:
            self.blood_expand_timer += dt
            prog = min(1.0, self.blood_expand_timer / self.blood_expand_duration)
            scale = 1.0 - (1.0 - prog) ** 3
            if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
                self.blood_pool_np.setScale(scale, scale, 1.0)

    def destroy(self):
        """그래픽 및 내부 리소스 해제"""
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
            self.blood_pool_np.removeNode()
            self.blood_pool_np = None
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """플레이어 사격 레이캐스트와 4.2m 해골 괴물 전신(두개골, 흉곽, 골반 등) 충돌 판정"""
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 1.0, 0.70), # 하체/다리
            (self.pos.x, self.pos.y, self.pos.z + 1.85, 0.75), # 골반
            (self.pos.x, self.pos.y, self.pos.z + 2.65, 0.85), # 흉곽/갈비뼈
            (self.pos.x, self.pos.y, self.pos.z + 3.35, 0.80), # 쇄골/어깨
            (self.pos.x, self.pos.y, self.pos.z + 3.85, 0.80), # 쩍 벌어진 두개골
        ]
        return ray_spheres_hit(ray_o, ray_d, targets, max_dist)

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
        self.max_hp = 110
        self.hp = self.max_hp
        self.exp_value = 45
        self.attack_damage = 35
        self.speed = 7.6

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

        self.slam_warning = make_warning_ring(self.node, 'slam_radius', 11.5, (1.0, 0.65, 0.15, 0.9))
        self.slam_warning.setZ(0.05)
        self.slam_charge = make_warning_ring(self.node, 'slam_charge', 11.5, (1.0, 0.9, 0.4, 0.9))
        self.slam_charge.setZ(0.055)

    def begin_slam(self, audio_mgr=None):
        if self.is_slamming or self.is_corpse or self.stun_timer > 0 or self.slam_cooldown > 0:
            return False
        self.is_slamming = True
        self.slam_timer = 0.0
        self.slam_has_impacted = False
        self.slam_cooldown = 5.5
        self.slam_warning.show()
        self.slam_charge.setScale(0.05, 0.05, 1)
        self.slam_charge.show()
        if audio_mgr:
            audio_mgr.play_attack_warning('orc', self.pos)
        return True

    def cancel_slam(self):
        self.is_slamming = False
        self.slam_timer = 0.0
        self.slam_has_impacted = False
        self.slam_warning.hide()
        self.slam_charge.hide()
        self.torso.setP(0)
        self.head_pivot.setP(0)
        self.arm_r.setP(-15)
        self.arm_l.setP(0)

    def stun(self, duration=0.5):
        self.stun_timer = duration
        self.cancel_slam()
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.2, 1.8, 0.4, 1.0))

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self):
        """사망 시 거구 진흙/오크 웅크린 시체로 눕힘 및 걸쭉한 오염혈 웅덩이 형성"""
        self.cancel_slam()
        self.is_corpse = True
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.20)
        self.node.setP(-86)
        self.node.setR(-15)
        # 바닥에 수평 밀착되는 걸쭉한 진흙 혈흔
        self.blood_pool_np = create_organic_blood_pool(
            parent=self.node.getParent(),
            world_x=self.pos.x,
            world_y=self.pos.y,
            base_radius=1.55,
            center_col=LColor(0.04, 0.016, 0.004, 0.99),
            mid_col=LColor(0.09, 0.032, 0.009, 0.92),
            num_sub=3, num_drops=14
        )
        self.blood_expand_timer = 0.0
        self.blood_expand_duration = 1.10
        self.blood_pool_np.setScale(0.05, 0.05, 1.0)

    def update_corpse(self, dt):
        """시체 혈흔이 상처에서 서서히 번져나오는 애니메이션"""
        if hasattr(self, 'blood_expand_timer') and self.blood_expand_timer < self.blood_expand_duration:
            self.blood_expand_timer += dt
            prog = min(1.0, self.blood_expand_timer / self.blood_expand_duration)
            scale = 1.0 - (1.0 - prog) ** 3
            if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
                self.blood_pool_np.setScale(scale, scale, 1.0)

    def destroy(self):
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
            self.blood_pool_np.removeNode()
            self.blood_pool_np = None
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 1.0, 0.85),
            (self.pos.x, self.pos.y, self.pos.z + 1.8, 0.80),
            (self.pos.x, self.pos.y, self.pos.z + 2.3, 0.55)
        ]
        return ray_spheres_hit(ray_o, ray_d, targets, max_dist)

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
            self.slam_charge.setScale(max(0.05, prog), max(0.05, prog), 1)
            self.arm_r.setP(-15 - prog * 95.0)  # -110도까지 번쩍 들어올림
            self.arm_l.setP(-prog * 80.0)
            self.torso.setP(-prog * 18.0)
            return False

        # 2단계 (0.5s): 지면을 쾅! 하고 내리치는 임팩트 순간 (충격파 발생)
        if self.slam_timer >= 0.5 and not self.slam_has_impacted:
            self.slam_warning.hide()
            self.slam_charge.hide()
            self.arm_r.setP(48)  # 바닥을 향해 수직 강타
            self.arm_l.setP(40)
            self.torso.setP(28)
            self.head_pivot.setP(15)
            self.slam_has_impacted = True
            return True

        # 3단계 (0.5s ~ 1.0s): 여운 및 자세 복귀
        if self.slam_timer >= 1.0:
            self.cancel_slam()

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
        self.max_hp = 55
        self.hp = self.max_hp
        self.exp_value = 60
        self.attack_damage = 25
        self.speed = 10.5

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

        self.cast_warning = make_warning_ring(self.staff_node, 'witch_cast_warning', 0.48, (1.0, 0.35, 0.08, 1.0))
        self.cast_warning.setPos(0, 0, 0.9)
        self.cast_warning.setP(90)

    def begin_cast(self, audio_mgr=None):
        if self.is_casting or self.is_corpse or self.stun_timer > 0 or self.cast_cooldown > 0:
            return False
        self.is_casting = True
        self.cast_timer = 0.0
        self._fireball_fired = False
        self.cast_cooldown = 3.2
        self.cast_warning.setScale(1)
        self.cast_warning.show()
        if audio_mgr:
            audio_mgr.play_attack_warning('witch', self.pos)
        return True

    def cancel_cast(self):
        self.is_casting = False
        self.cast_timer = 0.0
        self._fireball_fired = False
        self.cast_warning.hide()
        self.orb.setScale(1.0)
        self.orb.clearColorScale()
        self.arm_r.setP(-35)

    def stun(self, duration=0.5):
        self.stun_timer = duration
        self.cancel_cast()
        if hasattr(self, 'aura_np') and self.aura_np:
            self.aura_np.node().setColor((2.4, 2.0, 0.6, 1.0))

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self.stun(0.4)
        return self.hp <= 0

    def turn_into_corpse(self):
        """사망 시 재와 잿빛 자주색 마법혈 웅덩이가 바닥에 퍼짐"""
        self.cancel_cast()
        self.is_corpse = True
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        self.node.setPos(self.pos.x, self.pos.y, 0.16)
        self.node.setP(-85)
        self.node.setR(8)
        # 바닥에 수평 밀착되는 마녀의 저주받은 자줏빛 핏물
        self.blood_pool_np = create_organic_blood_pool(
            parent=self.node.getParent(),
            world_x=self.pos.x,
            world_y=self.pos.y,
            base_radius=1.30,
            center_col=LColor(0.035, 0.004, 0.022, 0.99),
            mid_col=LColor(0.080, 0.008, 0.050, 0.92),
            num_sub=3, num_drops=14
        )
        self.blood_expand_timer = 0.0
        self.blood_expand_duration = 0.90
        self.blood_pool_np.setScale(0.06, 0.06, 1.0)

    def update_corpse(self, dt):
        """시체 혈흔이 상처에서 서서히 번져나오는 애니메이션"""
        if hasattr(self, 'blood_expand_timer') and self.blood_expand_timer < self.blood_expand_duration:
            self.blood_expand_timer += dt
            prog = min(1.0, self.blood_expand_timer / self.blood_expand_duration)
            scale = 1.0 - (1.0 - prog) ** 3
            if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
                self.blood_pool_np.setScale(scale, scale, 1.0)

    def destroy(self):
        if hasattr(self, 'aura_np') and not self.aura_np.isEmpty():
            self.node.getParent().clearLight(self.aura_np)
            self.aura_np.removeNode()
        if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
            self.blood_pool_np.removeNode()
            self.blood_pool_np = None
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 0.6, 0.65),
            (self.pos.x, self.pos.y, self.pos.z + 1.4, 0.55),
            (self.pos.x, self.pos.y, self.pos.z + 2.0, 0.55)
        ]
        return ray_spheres_hit(ray_o, ray_d, targets, max_dist)

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
            self.cast_warning.setScale(1.0 + prog * 0.8)
            self.orb.setColorScale(1.0 + prog, 1.0 + prog * 0.7, 1.0, 1.0)
            self.arm_r.setP(-35 - prog * 50.0)
            self.orb.setScale(1.0 + prog * 0.9)
            return False

        # 2단계 (0.4s): 파이어볼 발사 순간
        if self.cast_timer >= 0.4 and not getattr(self, '_fireball_fired', False):
            self.cast_warning.hide()
            self.orb.clearColorScale()
            self._fireball_fired = True
            self.arm_r.setP(-90)
            self.orb.setScale(1.6)
            return True

        # 3단계 (0.4s ~ 0.8s): 후딜레이 및 마력구 정상화
        if self.cast_timer >= 0.8:
            self.cancel_cast()

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




class ShadowStalker:
    """
    3. 심층의 그림자 스토커 (Abyssal Shadow Stalker)
    - 백룸의 어둠 속 틈새에서 솟아난 심층 포식자 엔티티
    - 칠흑의 공허 실루엣(Void Black), 4연 척추 및 튀어나온 흑요석 갈비뼈 가시
    - 어둠 속에서 번뜩이는 붉은 슬릿 안광(Piercing Crimson Eyes)
    - 흉부 중심에 박힌 '공허의 심장(Void Heart)' - 평시에는 보호막으로 가려져 있으나 우클릭 밀치기 피격 시 1.3초간 노출되어 2.5배 치명타 허용!
    - 평상시: 복도와 어둠 속을 은신하여 배회 (Stalking 모드, 6.8 m/s)
    - 이계화/암전 시: 포식 사냥 돌입 (Hunt 모드, 11.2 m/s), 비명과 함께 고속 돌진 및 발톱 도약 베기 (Lunge Attack)
    - 처치 시: +5발 대용량 볼트 회수 및 저주받은 유물(Relic) 100% 드랍
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("shadow_stalker")
        self.pos = Vec3(start_x, start_y, 0.0)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False
        self.stun_timer = 0.0

        # 포식자 상태 머신
        self.name = "그림자 스토커"
        self.max_hp = 135
        self.hp = self.max_hp
        self.exp_value = 85
        self.attack_damage = 28
        self.stalk_speed = 6.8
        self.hunt_speed = 11.2
        self.speed = self.stalk_speed
        self.hunt_mode = False

        # 약점 기믹 (공허의 심장)
        self.heart_exposed = False
        self.heart_exposed_timer = 0.0

        # 도약 베기 (Lunge Attack)
        self.lunge_cooldown = 3.5
        self.is_lunge_winding = False
        self.lunge_windup_timer = 0.0
        self.is_lunging = False
        self.lunge_timer = 0.0
        self.lunge_dir = Vec3(0, 0, 0)
        self.is_corpse = False

        # 색상 팔레트
        void_black = LColor(0.012, 0.012, 0.018, 1.0)
        obsidian_spine = LColor(0.035, 0.035, 0.048, 1.0)
        bone_spike = LColor(0.09, 0.08, 0.11, 1.0)
        claw_grey = LColor(0.18, 0.18, 0.22, 1.0)
        eye_crimson = LColor(1.6, 0.03, 0.03, 1.0)
        self.heart_dormant_col = LColor(0.35, 0.04, 0.45, 1.0)
        self.heart_exposed_col = LColor(1.7, 0.25, 1.9, 1.0)

        self.body_root = self.node.attachNewNode("stalker_body_root")

        # 1. 둔부 및 척추 베이스
        self.pelvis = make_cube('stalker_pelvis', 0.65, 0.55, 0.40, void_black)
        self.pelvis.setPos(0, 0, 0.85)
        self.pelvis.reparentTo(self.body_root)

        # 2. 4연절 굽은 척추 (Hunched Spine)
        self.spine_segments = []
        parent_bone = self.pelvis
        for i in range(4):
            z_offset = 0.28
            y_offset = 0.16
            seg = make_cube(f'stalker_spine_{i}', 0.48 - i * 0.04, 0.42, 0.32, obsidian_spine)
            seg.setPos(0, y_offset, z_offset)
            seg.setP(-14)  # 공격적으로 앞으로 굽은 자세
            seg.reparentTo(parent_bone)
            self.spine_segments.append(seg)
            parent_bone = seg

            # 양옆 흑요석 갈비뼈 가시
            for side in (-1, 1):
                rib = make_cube(f'stalker_rib_{i}_{side}', 0.08, 0.35, 0.08, bone_spike)
                rib.setPos(side * 0.32, 0.05, 0.0)
                rib.setR(side * 35)
                rib.setP(18)
                rib.reparentTo(seg)

        # 3. 공허의 심장 (Void Heart - 가슴 정중앙 약점 코어)
        self.heart_core = make_cube('stalker_void_heart', 0.24, 0.22, 0.24, self.heart_dormant_col)
        self.heart_core.setPos(0, 0.15, 0.0)
        self.heart_core.reparentTo(self.spine_segments[1])
        self.heart_core.setLightOff()

        # 4. 기다란 포식자 머리 및 붉은 안광
        top_spine = self.spine_segments[-1]
        self.head_pivot = top_spine.attachNewNode("stalker_head_pivot")
        self.head_pivot.setPos(0, 0.28, 0.15)

        cranium = make_cube('stalker_cranium', 0.42, 0.65, 0.32, void_black)
        cranium.setPos(0, 0.18, 0.05)
        cranium.setP(-12)
        cranium.reparentTo(self.head_pivot)

        # 뒤로 뻗은 2개의 공허 뿔
        for side in (-1, 1):
            horn = make_cube(f'stalker_horn_{side}', 0.07, 0.45, 0.07, bone_spike)
            horn.setPos(side * 0.16, -0.22, 0.16)
            horn.setP(35)
            horn.setH(side * -15)
            horn.reparentTo(self.head_pivot)

        # 턱
        self.jaw = make_cube('stalker_jaw', 0.34, 0.52, 0.18, obsidian_spine)
        self.jaw.setPos(0, 0.22, -0.16)
        self.jaw.reparentTo(self.head_pivot)

        # 붉은 슬릿 안광 (어둠 속에서도 밝게 발광)
        for side in (-1, 1):
            eye = make_cube(f'stalker_eye_{side}', 0.06, 0.12, 0.04, eye_crimson)
            eye.setPos(side * 0.14, 0.44, 0.06)
            eye.setLightOff()
            eye.reparentTo(self.head_pivot)

        # 붉은 안광 전용 포인트 라이트 (주변 벽에 으스스한 붉은 광원 투영)
        self.eye_light = PointLight("stalker_eye_glow")
        self.eye_light.setColor(LColor(0.55, 0.02, 0.02, 1.0))
        self.eye_light.setAttenuation(Vec3(0.1, 0.05, 0.08))
        self.eye_light_np = self.head_pivot.attachNewNode(self.eye_light)
        self.eye_light_np.setPos(0, 0.5, 0.0)
        parent.setLight(self.eye_light_np)

        # 5. 앞다리 / 손톱 (Long Stalking Forearms & Razor Claws)
        self.arm_l_pivot = top_spine.attachNewNode("stalker_arm_l_pivot")
        self.arm_l_pivot.setPos(-0.36, 0.10, -0.05)
        self.arm_r_pivot = top_spine.attachNewNode("stalker_arm_r_pivot")
        self.arm_r_pivot.setPos(0.36, 0.10, -0.05)

        for pivot, side in ((self.arm_l_pivot, -1), (self.arm_r_pivot, 1)):
            # 상완
            upper_arm = make_cube('stalker_upper_arm', 0.16, 0.18, 0.72, void_black)
            upper_arm.setPos(0, 0.12, -0.32)
            upper_arm.setP(-25)
            upper_arm.reparentTo(pivot)

            # 전완
            forearm = make_cube('stalker_forearm', 0.14, 0.15, 0.85, obsidian_spine)
            forearm.setPos(0, 0.32, -0.85)
            forearm.setP(45)
            forearm.reparentTo(pivot)

            # 3연 손톱 (Razor Talons)
            for c_i, c_offset in enumerate((-0.07, 0.0, 0.07)):
                claw = make_cube(f'stalker_claw_{side}_{c_i}', 0.04, 0.28, 0.04, claw_grey)
                claw.setPos(c_offset, 0.52, -1.25)
                claw.setP(60)
                claw.reparentTo(pivot)

        # 6. 뒷다리 (Hind Digitigrade Legs)
        self.leg_l_pivot = self.pelvis.attachNewNode("stalker_leg_l_pivot")
        self.leg_l_pivot.setPos(-0.32, -0.05, 0.0)
        self.leg_r_pivot = self.pelvis.attachNewNode("stalker_leg_r_pivot")
        self.leg_r_pivot.setPos(0.32, -0.05, 0.0)

        for pivot, side in ((self.leg_l_pivot, -1), (self.leg_r_pivot, 1)):
            thigh = make_cube('stalker_thigh', 0.20, 0.22, 0.65, void_black)
            thigh.setPos(0, -0.15, -0.28)
            thigh.setP(35)
            thigh.reparentTo(pivot)

            shin = make_cube('stalker_shin', 0.16, 0.18, 0.70, obsidian_spine)
            shin.setPos(0, 0.12, -0.65)
            shin.setP(-42)
            shin.reparentTo(pivot)

            foot = make_cube('stalker_foot', 0.18, 0.32, 0.12, claw_grey)
            foot.setPos(0, 0.22, -0.88)
            foot.reparentTo(pivot)

        # 7. 등 뒤를 맴도는 공허 촉수/파편 (Floating Void Tendril Shards)
        self.wisps = []
        for w_i in range(6):
            wisp = make_cube(f'stalker_wisp_{w_i}', 0.06, 0.06, 0.42, obsidian_spine)
            wisp.reparentTo(self.body_root)
            wisp.setLightOff()
            self.wisps.append(wisp)

        arrow = LineSegs('stalker_lunge_direction')
        arrow.setThickness(3.0)
        arrow.setColor(0.85, 0.35, 1.0, 0.9)
        arrow.moveTo(0, 0.3, 0.05)
        arrow.drawTo(0, 6.27, 0.05)
        arrow.moveTo(-0.55, 5.4, 0.05)
        arrow.drawTo(0, 6.27, 0.05)
        arrow.drawTo(0.55, 5.4, 0.05)
        self.lunge_warning = self.node.attachNewNode(arrow.create())
        self.lunge_warning.setLightOff()
        self.lunge_warning.setTransparency(TransparencyAttrib.M_alpha)
        self.lunge_warning.hide()

    def set_hunt_mode(self, enabled=True, audio_mgr=None):
        """사냥 모드 전환 (이계화 암전 시 눈이 붉게 타오르며 광폭화)"""
        self.hunt_mode = enabled
        self.speed = self.hunt_speed if enabled else self.stalk_speed
        if enabled:
            if hasattr(self, 'eye_light') and self.eye_light:
                self.eye_light.setColor(LColor(1.2, 0.05, 0.05, 1.0))
            if audio_mgr and hasattr(audio_mgr, 'play_stalker_shriek'):
                audio_mgr.play_stalker_shriek()
        else:
            if hasattr(self, 'eye_light') and self.eye_light:
                self.eye_light.setColor(LColor(0.45, 0.02, 0.02, 1.0))

    def stun(self, duration=1.2):
        """밀치기 또는 강력한 충격 피격 시 심장 노출 및 경직"""
        self.cancel_lunge()
        self.stun_timer = duration
        self.heart_exposed = True
        self.heart_exposed_timer = duration + 0.3
        if hasattr(self, 'heart_core') and self.heart_core:
            self.heart_core.setColor(self.heart_exposed_col)
            self.heart_core.setScale(1.55)

    def take_damage(self, dmg):
        """약점 노출 상태에선 2.5배 치명타, 일반 상태에선 공허 장막으로 30% 피해 감소"""
        if self.heart_exposed or self.stun_timer > 0.0:
            final_dmg = dmg * 2.5
        else:
            final_dmg = dmg * 0.70

        self.hp = max(0, self.hp - final_dmg)
        if self.hp <= 0:
            return True

        if self.stun_timer <= 0.0:
            self.stun_timer = 0.22  # 짧은 피격 경직
        return False

    def trigger_lunge(self, target_pos, audio_mgr=None):
        """방향을 고정하고 0.45초 준비한 뒤 도약합니다."""
        if self.lunge_cooldown > 0.0 or self.stun_timer > 0.0 or self.is_corpse or self.is_lunge_winding or self.is_lunging:
            return False

        dx = target_pos[0] - self.pos.x
        dy = target_pos[1] - self.pos.y
        dist = math.hypot(dx, dy)
        if dist < 0.1:
            return False

        self.is_lunge_winding = True
        self.lunge_windup_timer = 0.45
        self.lunge_cooldown = 4.2
        self.lunge_dir = Vec3(dx / dist, dy / dist, 0.0)
        self.node.setH(math.degrees(math.atan2(-dx, dy)))
        self.lunge_warning.show()
        if audio_mgr:
            audio_mgr.play_attack_warning('stalker', self.pos)
        return True

    def update_lunge_windup(self, dt, audio_mgr=None):
        if not self.is_lunge_winding:
            return False
        self.lunge_windup_timer = max(0.0, self.lunge_windup_timer - dt)
        progress = 1.0 - self.lunge_windup_timer / 0.45
        self.body_root.setZ(-0.18 * progress)
        self.arm_l_pivot.setP(25 + 25 * progress)
        self.arm_r_pivot.setP(25 + 25 * progress)
        self.head_pivot.setP(15)
        if self.lunge_windup_timer > 1e-6:
            return False
        self.is_lunge_winding = False
        self.lunge_warning.hide()
        self.body_root.setZ(0)
        self.is_lunging = True
        self.lunge_timer = 0.38
        if audio_mgr:
            audio_mgr.play_stalker_lunge()
        return True

    def cancel_lunge(self):
        self.is_lunge_winding = False
        self.lunge_windup_timer = 0.0
        self.is_lunging = False
        self.lunge_timer = 0.0
        self.lunge_warning.hide()
        self.body_root.setZ(0)
        self.arm_l_pivot.setP(-15)
        self.arm_r_pivot.setP(-15)
        self.head_pivot.setP(0)

    def turn_into_corpse(self):
        """처치 시 공허 웅덩이 바닥 안착 및 5발 볼트 회수 기능"""
        if self.is_corpse:
            return
        self.cancel_lunge()
        self.is_corpse = True
        self.recoverable_bolts = 5
        self.recoverable_relic = True

        if hasattr(self, 'eye_light_np') and not self.eye_light_np.isEmpty():
            self.node.getParent().clearLight(self.eye_light_np)
            self.eye_light_np.removeNode()

        # 바닥에 쓰러진 자세
        self.node.setPos(self.pos.x, self.pos.y, 0.14)
        self.node.setP(-85)
        self.node.setR(25)

        # 바닥에 수평 밀착되는 칠흑의 공허 웅덩이
        self.blood_pool_np = create_organic_blood_pool(
            parent=self.node.getParent(),
            world_x=self.pos.x,
            world_y=self.pos.y,
            base_radius=1.75,
            center_col=LColor(0.01, 0.002, 0.018, 0.99),
            mid_col=LColor(0.03, 0.005, 0.055, 0.92),
            num_sub=4, num_drops=18
        )
        self.blood_expand_timer = 0.0
        self.blood_expand_duration = 1.25
        self.blood_pool_np.setScale(0.05, 0.05, 1.0)

        # 유물 코어 드롭 노드
        self.relic_drop_np = make_cube('stalker_relic_drop', 0.28, 0.28, 0.28, LColor(0.85, 0.2, 1.0, 1.0))
        self.relic_drop_np.reparentTo(self.node)
        self.relic_drop_np.setPos(0, 0.2, 0.15)
        self.relic_drop_np.setLightOff()

    def update_corpse(self, dt):
        """공허 체액이 바닥에 서서히 퍼져나가는 애니메이션"""
        if hasattr(self, 'blood_expand_timer') and self.blood_expand_timer < self.blood_expand_duration:
            self.blood_expand_timer += dt
            prog = min(1.0, self.blood_expand_timer / self.blood_expand_duration)
            scale = 1.0 - (1.0 - prog) ** 3
            if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
                self.blood_pool_np.setScale(scale, scale, 1.0)

    def destroy(self):
        if hasattr(self, 'eye_light_np') and not self.eye_light_np.isEmpty():
            self.node.getParent().clearLight(self.eye_light_np)
            self.eye_light_np.removeNode()
        if hasattr(self, 'blood_pool_np') and self.blood_pool_np and not self.blood_pool_np.isEmpty():
            self.blood_pool_np.removeNode()
            self.blood_pool_np = None
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        """다중 구체 피격 판정 (머리, 흉부 심장 약점, 척추, 팔다리)"""
        targets = [
            (self.pos.x, self.pos.y, self.pos.z + 0.65, 0.65),  # 둔부/하체
            (self.pos.x, self.pos.y, self.pos.z + 1.25, 0.70),  # 가슴 & 공허의 심장 약점
            (self.pos.x, self.pos.y, self.pos.z + 1.75, 0.60),  # 상부 척추/목
            (self.pos.x, self.pos.y, self.pos.z + 2.05, 0.55),  # 머리 및 뿔
        ]
        return ray_spheres_hit(ray_o, ray_d, targets, max_dist)

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        """위치 갱신 및 회전"""
        if self.is_corpse:
            return

        if self.stun_timer > 0.0:
            self.stun_timer -= dt
            shake = math.sin(self.stun_timer * 55.0) * 0.06
            self.node.setPos(self.pos.x + shake, self.pos.y, self.pos.z)
            self.head_pivot.setP(25)  # 고개를 뒤로 젖히며 고통스러워함
            self.jaw.setP(-20)
            return

        self.pos.x = new_x
        self.pos.y = new_y
        self.pos.z = 0.0
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 12.0))

        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """역동적인 유기적 기어다니기 및 공허 촉수 휘감김 애니메이션"""
        if self.is_corpse:
            return

        self.anim_time += dt * (5.5 if self.hunt_mode else 3.2)
        t = self.anim_time

        # 약점 노출 타이머 관리
        if self.heart_exposed:
            self.heart_exposed_timer -= dt
            # 맥동하는 빛
            pulse = 1.0 + 0.35 * math.sin(t * 18.0)
            if hasattr(self, 'heart_core') and self.heart_core:
                self.heart_core.setScale(1.4 * pulse)
            if self.heart_exposed_timer <= 0.0:
                self.heart_exposed = False
                if hasattr(self, 'heart_core') and self.heart_core:
                    self.heart_core.setColor(self.heart_dormant_col)
                    self.heart_core.setScale(1.0)

        # 도약 베기 상태 업데이트
        if self.is_lunge_winding:
            return
        if self.is_lunging:
            self.lunge_timer -= dt
            self.arm_l_pivot.setP(-65)
            self.arm_r_pivot.setP(-65)
            self.head_pivot.setP(-28)
            if self.lunge_timer <= 0.0:
                self.is_lunging = False
            return

        if self.lunge_cooldown > 0.0:
            self.lunge_cooldown -= dt

        # 척추 호흡/경련
        spine_wave = math.sin(t * 2.2) * 5.0
        for i, seg in enumerate(self.spine_segments):
            seg.setP(-14 + spine_wave * (0.4 + i * 0.25))

        # 걷기/기어다니기 앞다리 & 뒷다리 엇갈림 스윙
        stride = 28.0 if self.hunt_mode else 18.0
        leg_phase = math.sin(t * 3.5)
        self.arm_l_pivot.setP(leg_phase * stride - 15)
        self.arm_r_pivot.setP(-leg_phase * stride - 15)
        self.leg_l_pivot.setP(-leg_phase * stride)
        self.leg_r_pivot.setP(leg_phase * stride)

        # 머리 주시 움직임
        head_sway = math.sin(t * 1.8) * 6.0
        self.head_pivot.setH(head_sway)

        # 공허 촉수/파편들의 소용돌이 움직임
        for w_i, wisp in enumerate(self.wisps):
            angle = t * 1.8 + w_i * (2 * math.pi / 6)
            rad = 0.55 + 0.15 * math.sin(t * 3.0 + w_i)
            height = 1.1 + 0.35 * math.cos(t * 2.5 + w_i * 1.5)
            wisp.setPos(math.cos(angle) * rad, math.sin(angle) * rad, height)
            wisp.setP(math.sin(t * 4.0 + w_i) * 25.0)
            wisp.setR(math.cos(t * 4.0 + w_i) * 25.0)


# 기존 호환용 별칭
CreepySpiderMonster = LongBlackSerpent
TallShadowMonster = TallSkeletonMonster

