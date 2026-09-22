import math
from panda3d.core import Vec3, LColor, PointLight, ClockObject
from geometry import make_cube

class TallShadowMonster:
    """
    칠흑의 키 큰 실루엣을 가진 백룸 추격 괴물 엔티티 (신장 ~2.5m, 붉은 안광)
    플레이어의 뒤쪽 복도에서 스폰되어 서서히 다가오며 쫓아옵니다.
    """
    def __init__(self, parent, start_x, start_y):
        self.node = parent.attachNewNode("tall_monster")
        self.pos = Vec3(start_x, start_y, 0)
        self.node.setPos(self.pos)
        self.anim_time = 0.0
        self.path = []
        self.path_timer = 0.0
        self.has_los = False

        black = LColor(0.015, 0.015, 0.015, 1.0)
        eye_red = LColor(1.0, 0.03, 0.03, 1.0)

        # 애니메이션 관절용 루트
        self.body_root = self.node.attachNewNode("body_root")

        # 1. 가늘고 긴 몸통 (Torso)
        torso = make_cube('torso', 0.42, 0.3, 1.05, black)
        torso.setPos(0, 0, 1.6)
        torso.reparentTo(self.body_root)

        # 2. 길쭉한 머리 (Head)
        head = make_cube('head', 0.3, 0.28, 0.38, black)
        head.setPos(0, 0, 2.32)
        head.reparentTo(self.body_root)

        # 3. 어둠 속에서 번뜩이는 붉은 눈 (Glowing Unlit Red Eyes)
        eye_l = make_cube('eye_l', 0.06, 0.03, 0.05, eye_red)
        eye_l.setPos(-0.08, 0.15, 2.36)
        eye_l.setLightOff()
        eye_l.reparentTo(self.body_root)

        eye_r = make_cube('eye_r', 0.06, 0.03, 0.05, eye_red)
        eye_r.setPos(0.08, 0.15, 2.36)
        eye_r.setLightOff()
        eye_r.reparentTo(self.body_root)

        # 4. 무릎 아래까지 길게 늘어진 기괴한 팔 (Long Creepy Arms)
        self.arm_l = make_cube('arm_l', 0.12, 0.12, 1.35, black)
        self.arm_l.setPos(-0.3, 0, 1.3)
        self.arm_l.reparentTo(self.body_root)

        self.arm_r = make_cube('arm_r', 0.12, 0.12, 1.35, black)
        self.arm_r.setPos(0.3, 0, 1.3)
        self.arm_r.reparentTo(self.body_root)

        # 5. 가늘고 긴 다리 (Legs)
        self.leg_l = make_cube('leg_l', 0.14, 0.14, 1.15, black)
        self.leg_l.setPos(-0.15, 0, 0.58)
        self.leg_l.reparentTo(self.body_root)

        self.leg_r = make_cube('leg_r', 0.14, 0.14, 1.15, black)
        self.leg_r.setPos(0.15, 0, 0.58)
        self.leg_r.reparentTo(self.body_root)

        # 6. 기괴한 붉은색 오라 조명 (접근 시 복도 벽면에 붉은 기운 투영)
        aura_light = PointLight('monster_aura')
        aura_light.setColor((0.7, 0.03, 0.03, 1.0))
        aura_light.setAttenuation((1.0, 0.06, 0.012))
        self.aura_np = self.node.attachNewNode(aura_light)
        self.aura_np.setPos(0, 0, 1.8)
        parent.setLight(self.aura_np)

    def reset_pos(self, x, y):
        """괴물 위치 및 상태 초기화"""
        self.pos = Vec3(x, y, 0)
        self.node.setPos(self.pos)
        self.node.setH(0)
        self.arm_l.setP(0)
        self.arm_r.setP(0)
        self.leg_l.setP(0)
        self.leg_r.setP(0)
        self.body_root.setR(0)
        self.body_root.setZ(0)
        self.path = []
        self.path_timer = 0.0
        self.has_los = False

    def update_pos(self, new_x, new_y, dt, dir_x, dir_y):
        """위치 갱신 및 이동 방향을 향한 부드러운 시선 회전"""
        self.pos.x = new_x
        self.pos.y = new_y
        self.node.setPos(self.pos)

        target_h = math.degrees(math.atan2(-dir_x, dir_y))
        curr_h = self.node.getH()
        diff_h = (target_h - curr_h + 180) % 360 - 180
        self.node.setH(curr_h + diff_h * min(1.0, dt * 10.0))
        self.update(dt, is_moving=True)

    def update(self, dt, is_moving, is_attacking=False):
        """기괴한 보행 및 공격 모션 애니메이션"""
        if is_attacking:
            # 점프스케어 덮치기 포즈
            self.arm_l.setP(-85)
            self.arm_r.setP(-85)
            self.body_root.setP(15)
            self.body_root.setZ(0.12)
            return

        if is_moving:
            self.anim_time += dt * 6.5
            self.arm_l.setP(math.sin(self.anim_time) * 22)
            self.arm_r.setP(-math.sin(self.anim_time) * 22)
            self.leg_l.setP(-math.sin(self.anim_time) * 25)
            self.leg_r.setP(math.sin(self.anim_time) * 25)
            # 섬뜩한 불규칙 목 기울임 및 걸음 상하 반동
            self.body_root.setR(math.sin(self.anim_time * 0.6) * 2.5)
            self.body_root.setZ(math.sin(self.anim_time * 2.0) * 0.035)
        else:
            t = ClockObject.getGlobalClock().getFrameTime()
            self.arm_l.setP(math.sin(t * 1.5) * 5)
            self.arm_r.setP(-math.sin(t * 1.5) * 5)
            self.body_root.setZ(math.sin(t * 2.0) * 0.02)
