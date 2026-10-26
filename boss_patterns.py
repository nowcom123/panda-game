"""
[ 골해의 지배자 (CableOverlordBoss) 전투 기믹 & 패턴 제어 시스템 ]
- 상태 머신: IDLE -> TELEGRAPH(예고) -> ACTIVE(발동) -> RECOVERY(회복)
- 공정성 원칙:
  1) 모든 위협적인 광역/근접 공격은 명확한 바닥 시각 예고(원/선/부채꼴) 제공
  2) 예고 시간(0.8초 이상) 동안 피해 없음
  3) 발동당 최대 1회 피해 (프레임 단위 중복 타격 방지, 큰 dt 내성)
  4) 명확한 회피 조건 (거리 이탈, 점프, 걸어서 이탈)
  5) 회복 중 해골 머리 취약 노출
  6) 사망/파괴 시 모든 시각 인디케이터 및 공격 즉각 정리
"""
import math
import random
from panda3d.core import Vec3, LColor, TransparencyAttrib, LineSegs
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter
from geometry import make_cube_to, make_cylinder_to, make_sphere_to, make_sphere
from projectiles import GroundShockwave
from boss_scaling import boss_damage
from constants import PLAYER_EYE_HEIGHT
from collision import get_nearby_colliders, resolve_collision
from world_gen import check_line_of_sight


def clear_attack_path(g, sx, sy, tx, ty, padding=0.0):
    distance = math.hypot(tx - sx, ty - sy)
    colliders = get_nearby_colliders(getattr(g, 'chunks', {}),
                                    (sx + tx) * .5, (sy + ty) * .5,
                                    search_dist=distance * .5 + padding + 1.0, curr_z=0.0)
    if padding:
        colliders = [(a-padding, b-padding, c+padding, d+padding) for a, b, c, d in colliders]
    return check_line_of_sight(sx, sy, tx, ty, colliders)


class GroundDangerIndicator:
    """바닥 위험 영역 시각 인디케이터 (원형 링 및 맥동 위험 구역)"""
    def __init__(self, render, x, y, radius, color=None, z_offset=0.04):
        self.render = render
        self.pos = Vec3(x, y, z_offset)
        self.radius = max(0.5, radius)
        self.color = color or LColor(1.0, 0.2, 0.2, 0.65)
        self.node = render.attachNewNode("danger_indicator")
        self.node.setPos(self.pos)
        self.node.setTransparency(TransparencyAttrib.MAlpha)
        self.node.setDepthWrite(False)
        self.node.setLightOff()

        # 외곽 경계 링 (16개 각기둥 조각으로 링 형성)
        self.segments = []
        seg_count = 24
        thick = 0.12
        for i in range(seg_count):
            ang = (i / seg_count) * math.tau
            next_ang = ((i + 1) / seg_count) * math.tau
            mx = math.cos((ang + next_ang) * 0.5) * self.radius
            my = math.sin((ang + next_ang) * 0.5) * self.radius
            seg_len = 2.0 * self.radius * math.sin(math.pi / seg_count)
            seg = make_cube_to(self.node, thick, seg_len, 0.03, self.color, mx, my, 0,
                               rot_h=math.degrees(ang + next_ang) * 0.5)
            self.segments.append(seg)

        # 중심 십자 / 방사형 선 (위험 반경 인지 지원)
        for i in range(4):
            ang = i * (math.pi / 2.0)
            hx = math.cos(ang) * (self.radius * 0.5)
            hy = math.sin(ang) * (self.radius * 0.5)
            line = make_cube_to(self.node, 0.06, self.radius * 0.85, 0.02,
                                LColor(self.color.x, self.color.y, self.color.z, 0.40),
                                hx, hy, 0, rot_h=math.degrees(ang) + 90)
            self.segments.append(line)

        # 내부 맥동 중심 구
        self.center_disk = make_sphere_to(self.node, self.radius * 0.25, self.radius * 0.25, 0.02,
                                          LColor(self.color.x, self.color.y, self.color.z, 0.45),
                                          0, 0, 0.01)

        self.progress = 0.0

    def set_progress(self, pct):
        """0.0(예고 시작) ~ 1.0(발동 직전) 진행도에 따른 시각 피드백"""
        self.progress = max(0.0, min(1.0, pct))
        pulse = 0.75 + 0.25 * math.sin(self.progress * math.pi * 6.0)
        alpha = (0.35 + self.progress * 0.55) * pulse
        self.node.setColorScale(1.0, 1.0, 1.0, alpha)
        # 중심 디스크가 예고 시간에 맞춰 바깥으로 팽창
        expansion = 0.15 + 0.85 * self.progress
        self.center_disk.setScale(self.radius * expansion, self.radius * expansion, 0.02)

    def destroy(self):
        if hasattr(self, 'node') and self.node and not self.node.isEmpty():
            self.node.removeNode()


class GroundBoneSpike:
    """순차 뼈 가시 분출 시 바닥에서 솟구치는 3D 뼈 침 객체"""
    def __init__(self, render, x, y, max_height=2.4):
        self.render = render
        self.pos = Vec3(x, y, 0.0)
        self.max_height = max_height
        self.node = render.attachNewNode("bone_spike_group")
        self.node.setPos(self.pos)
        self.spikes = []

        bone_col = LColor(0.92, 0.88, 0.82, 1.0)
        dark_bone = LColor(0.52, 0.45, 0.40, 1.0)

        # 중앙 대형 뼈 가시
        spike_main = make_cylinder_to(self.node, 0.22, 0.22, max_height, bone_col, 0, 0, max_height * 0.5, axis='z')
        make_cube_to(spike_main, 0.28, 0.28, 0.45, dark_bone, 0, 0, -max_height * 0.35)
        self.spikes.append(spike_main)

        # 주변 작은 보조 뼈 가시 4개 (사방으로 비스듬히 돌출)
        offsets = [(-0.45, -0.40, 18, 15), (0.45, -0.40, -18, 15),
                   (-0.40, 0.45, 18, -15), (0.40, 0.45, -18, -15)]
        for ox, oy, rh, rp in offsets:
            sub_h = max_height * 0.65
            sub = make_cylinder_to(self.node, 0.14, 0.14, sub_h, bone_col, ox, oy, sub_h * 0.4,
                                   rot_h=rh, rot_p=rp, axis='z')
            self.spikes.append(sub)

        # 시작 시 지하(Z축 아래)에 위치
        self.current_height_ratio = 0.0
        self.node.setZ(-max_height)

    def set_height_ratio(self, ratio):
        self.current_height_ratio = max(0.0, min(1.0, ratio))
        self.node.setZ(-self.max_height * (1.0 - self.current_height_ratio))

    def destroy(self):
        if hasattr(self, 'node') and self.node and not self.node.isEmpty():
            self.node.removeNode()



class FanWaveIndicator:
    """바닥 뼈 부채꼴 파동 예고 인디케이터: 좌우 위험 부채꼴 윙과 중앙 안전 통로 표시"""
    def __init__(self, render, x, y, radius=14.0, angle=0.0, z_offset=0.04):
        self.render = render
        self.pos = Vec3(x, y, z_offset)
        self.radius = radius
        self.angle = angle
        self.segments = []
        self.node = None
        if render is not None:
            self.node = render.attachNewNode("fan_wave_indicator")
            self.node.setPos(self.pos)
            self.node.setTransparency(TransparencyAttrib.MAlpha)
            self.node.setDepthWrite(False)
            self.node.setLightOff()

            danger_col = LColor(1.0, 0.22, 0.15, 0.65)
            safe_col = LColor(0.20, 1.0, 0.45, 0.55)

            # Filled sectors use the same 12/60 degree boundaries as damage.
            vertices = GeomVertexData('fan_sectors', GeomVertexFormat.getV3(), Geom.UHStatic)
            writer = GeomVertexWriter(vertices, 'vertex')
            triangles = GeomTriangles(Geom.UHStatic)
            index = 0
            for side in (-1, 1):
                for i in range(16):
                    a = angle + math.radians(side * (12 + 3 * i))
                    b = angle + math.radians(side * (15 + 3 * i))
                    writer.addData3(0, 0, 0)
                    writer.addData3(radius * math.cos(a), radius * math.sin(a), 0)
                    writer.addData3(radius * math.cos(b), radius * math.sin(b), 0)
                    triangles.addVertices(index, index + 1, index + 2)
                    index += 3
            mesh = Geom(vertices)
            mesh.addPrimitive(triangles)
            sector_node = GeomNode('fan_danger_sectors')
            sector_node.addGeom(mesh)
            sectors = self.node.attachNewNode(sector_node)
            sectors.setTwoSided(True)
            sectors.setColor(1, .12, .06, .3)

            # 좌우 위험 부채꼴 날개 (각도 12도 ~ 60도)
            for side in (-1, 1):
                for i in range(5):
                    deg = side * (14.0 + i * 9.0)
                    rad = angle + math.radians(deg)
                    mx = math.cos(rad) * (self.radius * 0.55)
                    my = math.sin(rad) * (self.radius * 0.55)
                    seg = make_cube_to(self.node, 0.14, self.radius * 0.85, 0.03, danger_col,
                                       mx, my, 0, rot_h=math.degrees(rad) + 90)
                    self.segments.append(seg)

            # 중앙 안전 통로 경계선 및 안내선 (-8도, 0도, +8도)
            for deg in (-12.0, 0.0, 12.0):
                rad = angle + math.radians(deg)
                mx = math.cos(rad) * (self.radius * 0.5)
                my = math.sin(rad) * (self.radius * 0.5)
                line = make_cube_to(self.node, 0.08, self.radius * 0.9, 0.02, safe_col,
                                    mx, my, 0.01, rot_h=math.degrees(rad) + 90)
                self.segments.append(line)

        self.progress = 0.0

    def set_progress(self, pct):
        self.progress = max(0.0, min(1.0, pct))
        if self.node and not self.node.isEmpty():
            pulse = 0.75 + 0.25 * math.sin(self.progress * math.pi * 6.0)
            alpha = (0.35 + self.progress * 0.55) * pulse
            self.node.setColorScale(1.0, 1.0, 1.0, alpha)

    def destroy(self):
        if self.node and not self.node.isEmpty():
            self.node.removeNode()
            self.node = None


class BoneHeartSeal:
    """보스가 생성하는 파괴 가능한 뼈 심장 봉인체"""
    def __init__(self, render, x, y, z=0.0, hp=120.0):
        self.render = render
        self.pos = Vec3(x, y, z)
        self.max_hp = hp
        self.hp = hp
        self.is_destroyed = False
        self.col_radius = 0.55
        self.height = 1.4
        self.node = None
        self.core = None

        if render is not None:
            self.node = render.attachNewNode("bone_heart_seal")
            self.node.setPos(self.pos)
            bone_ivory = LColor(0.92, 0.88, 0.82, 1.0)
            dark_bone = LColor(0.40, 0.35, 0.32, 1.0)
            core_cyan = LColor(0.20, 0.90, 1.0, 1.0)

            make_cylinder_to(self.node, 0.45, 0.45, 0.30, dark_bone, 0, 0, 0.15, axis='z')
            for ang in (0, 72, 144, 216, 288):
                rad = math.radians(ang)
                rx = math.cos(rad) * 0.30
                ry = math.sin(rad) * 0.30
                make_cylinder_to(self.node, 0.10, 0.10, 0.85, bone_ivory, rx, ry, 0.65, axis='z')
            self.core = make_sphere_to(self.node, 0.35, 0.35, 0.45, core_cyan, 0, 0, 0.70)
            self.core.setLightOff()

    def is_hit_by_ray(self, ray_o, ray_d, max_dist=55.0):
        if self.is_destroyed or self.hp <= 0:
            return False, 0.0
        center = Vec3(self.pos.x, self.pos.y, self.pos.z + 0.70)
        radius = 0.65
        origin = ray_o - center
        direction = ray_d
        aa = direction.dot(direction)
        bb = origin.dot(direction)
        cc = origin.dot(origin) - radius * radius
        discriminant = bb * bb - aa * cc
        if aa <= 1e-12 or discriminant < 0:
            return False, 0.0
        entry = (-bb - math.sqrt(discriminant)) / aa
        if 0.1 < entry < max_dist:
            return True, entry
        return False, 0.0

    def take_damage(self, dmg, hit_dir=None):
        if self.is_destroyed:
            return True
        self.hp = max(0.0, self.hp - dmg)
        if self.core and not self.core.isEmpty():
            self.core.setColor(LColor(1.0, 0.25, 0.25, 1.0))
        if self.hp <= 0:
            self.is_destroyed = True
            self.destroy()
            return True
        return False

    def update(self, dt):
        pass

    def destroy(self):
        self.is_destroyed = True
        if self.node and not self.node.isEmpty():
            self.node.removeNode()
            self.node = None

class BossPatternState:
    IDLE = "IDLE"
    TELEGRAPH = "TELEGRAPH"
    ACTIVE = "ACTIVE"
    RECOVERY = "RECOVERY"


class BossPatternController:
    """
    골해의 지배자 패턴 컨트롤러
    - 360도 뼈팔 휩쓸기
    - 순차 뼈 가시 분출
    - 거미 다리 도약 강타
    - 뼈 파편 일제사격
    - 2페이즈 전환 및 관리
    """
    def __init__(self, boss):
        self.boss = boss
        self.current_pattern = None
        self.state = BossPatternState.IDLE
        self.timer = 0.0
        self.telegraph_duration = 0.0
        self.active_duration = 0.0
        self.recovery_duration = 0.0

        # 개별 스킬 쿨다운
        self.sweep_cooldown = 2.0
        self.spikes_cooldown = 4.0
        self.leap_cooldown = 6.0
        self.volley_cooldown = 5.0
        self.fan_wave_cooldown = 0.0
        self.seal_cooldown = 0.0
        self.is_protecting = False
        self.active_seals = []
        self.seal_timer = 0.0
        self.fan_wave_hit_done = False
        self.fan_wave_angle = 0.0
        self.phase2_triggered = False
        self.pending_chain = False

        # 활성 인디케이터 및 효과 노드 목록
        self.indicators = []
        self.bone_spikes = []

        # 패턴별 실행 상태 데이터
        self.sweep_angle = 0.0
        self.sweep_hit_done = False
        self.sweep_radius = 4.5

        self.spike_targets = []  # [(x, y, erupt_time, erupted, hit_applied), ...]
        self.leap_start = Vec3(0, 0, 0)
        self.leap_target = Vec3(0, 0, 0)
        self.leap_radius = 3.5
        self.leap_hit_done = False

        self.is_skull_exposed = False

    def is_acting(self):
        """보스가 패턴(예고/발동/회복)을 수행 중인지 여부"""
        return self.state != BossPatternState.IDLE

    def cleanup(self):
        """모든 바닥 인디케이터 및 스파이크 노드 정리 (사망/파괴/초기화 시)"""
        for ind in self.indicators:
            try:
                ind.destroy()
            except Exception:
                pass
        self.indicators.clear()

        for sp in self.bone_spikes:
            try:
                sp.destroy()
            except Exception:
                pass
        self.bone_spikes.clear()

        for seal in getattr(self, 'active_seals', []):
            try:
                seal.destroy()
            except Exception:
                pass
        self.active_seals = []
        self.is_protecting = False
        if hasattr(self.boss, 'set_bone_shield'):
            self.boss.set_bone_shield(False)

        self.state = BossPatternState.IDLE
        self.current_pattern = None
        self.pending_chain = False
        self.timer = 0.0
        self.is_skull_exposed = False
        if hasattr(self.boss, 'is_lashing'):
            self.boss.is_lashing = False

    def update(self, dt, g, px, py, pz, dist, dist_z):
        """
        보스 패턴 갱신 루틴
        반환값: game_ended (True이면 플레이어 사망으로 게임 오버)
        """
        if self.boss.hp <= 0 or getattr(self.boss, 'is_corpse', False):
            self.cleanup()
            return False
        if dt <= 0 or getattr(g, 'is_test_mode', False):
            return False
        # 스턴 상태 시 쿨다운 및 패턴 진행 정지
        if getattr(self.boss, 'stun_timer', 0.0) > 0.0:
            return False

        # 2페이즈 전환 검사 (체력 50% 이하 1회만 처리)
        if self.boss.hp <= self.boss.max_hp * 0.5 and not self.phase2_triggered and self.boss.phase == 1:
            self._enter_phase_2(g)

        # 쿨다운 감소 (유휴 상태이거나 패턴 중에도 쿨다운은 정상 감소)
        if self.sweep_cooldown > 0.0:
            self.sweep_cooldown -= dt
        if self.spikes_cooldown > 0.0:
            self.spikes_cooldown -= dt
        if self.leap_cooldown > 0.0:
            self.leap_cooldown -= dt
        if self.volley_cooldown > 0.0:
            self.volley_cooldown -= dt
        if self.fan_wave_cooldown > 0.0:
            self.fan_wave_cooldown -= dt
        if self.seal_cooldown > 0.0:
            self.seal_cooldown -= dt

        # 상태별 처리
        if self.state == BossPatternState.IDLE:
            self._select_next_pattern(g, px, py, pz, dist, dist_z)
            return False

        elif self.state == BossPatternState.TELEGRAPH:
            return self._update_telegraph(dt, g, px, py, pz, dist, dist_z)

        elif self.state == BossPatternState.ACTIVE:
            return self._update_active(dt, g, px, py, pz, dist, dist_z)

        elif self.state == BossPatternState.RECOVERY:
            self.timer += dt
            return self._update_recovery(dt, g, px, py, pz)

        return False

    def _enter_phase_2(self, g):
        """체력 50% 이하 2페이즈 진입"""
        self.phase2_triggered = True
        self.boss.phase = 2
        self.boss.speed = 5.8 * getattr(self.boss, 'movement_scale', 1.0)
        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_stage_banner(
                "[ ! 경고: 골해의 지배자 2페이즈 폭주 돌입 ! ]\n핏빛 안광이 점등되며 공격 연계와 속도가 빨라집니다!",
                color=(1.0, 0.2, 0.15, 1.0)
            )
            g.stage_banner_timer = 3.5

        if hasattr(g, 'audio_mgr') and g.audio_mgr:
            g.audio_mgr.play_siren_alarm()

        # 몬스터 상한(16마리)을 준수하며 최대 2마리 소환
        if hasattr(g, 'monsters') and len(g.monsters) < 16:
            for _ in range(min(2, 16 - len(g.monsters))):
                if hasattr(g, 'spawn_reinforcement_monster'):
                    g.spawn_reinforcement_monster(near_gate=True)

        # 2페이즈 안광 및 코어색 변경
        if hasattr(self.boss, 'apply_phase_2_visuals'):
            self.boss.apply_phase_2_visuals()

    def _select_next_pattern(self, g, px, py, pz, dist, dist_z):
        """거리 및 우선순위에 따른 다음 패턴 개시"""
        bx, by = self.boss.pos.x, self.boss.pos.y
        stage_lvl = getattr(self.boss, 'stage_level', getattr(g, 'current_stage', 1))

        # 1순위: 실제 팔 길이와 예고 반경 안에서 360도 휩쓸기
        if dist <= self.sweep_radius and dist_z <= 3.5 and self.sweep_cooldown <= 0.0:
            self._start_bone_arm_sweep(g)
            return

        # 2순위 (5층부터): 뼈 심장 봉인 (dist <= 22.0m, 보호 상태 아닐 때)
        if stage_lvl >= 5 and self.seal_cooldown <= 0.0 and not self.is_protecting:
            if self._can_spawn_seals(g, px, py):
                self._start_bone_heart_seal(g, px, py)
                return

        # 3순위 (3층부터): 뼈 부채꼴 파동 (5.0m <= dist <= 18.0m, 안전 통로 개방 시)
        if stage_lvl >= 3 and 5.0 <= dist <= 18.0 and self.fan_wave_cooldown <= 0.0:
            if self._can_start_fan_wave(g, px, py):
                self._start_bone_fan_wave(g, px, py)
                return

        # 4순위: 중거리에서 거미 다리 도약 강타 (6.0m <= dist <= 16.0m)
        if 5.5 <= dist <= 16.0 and self.leap_cooldown <= 0.0:
            if self._can_leap_to_target(g, px, py):
                self._start_spider_leap_slam(g, px, py)
                return

        # 5순위: 순차 뼈 가시 분출 (dist <= 26.0m)
        if dist <= 26.0 and self.spikes_cooldown <= 0.0:
            self._start_bone_spikes(g, px, py)
            return

        # 6순위: 뼈 파편 일제사격 (dist <= 30.0m)
        if dist <= 30.0 and self.volley_cooldown <= 0.0:
            self._start_bone_volley(g, px, py, pz)
            return

    # --------------------------------------------------------------------------
    # 1. 360도 뼈팔 휩쓸기 (Bone Arm Sweep)
    # --------------------------------------------------------------------------
    def _start_bone_arm_sweep(self, g):
        self.current_pattern = "sweep"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 0.85 if self.boss.phase == 1 else 0.80
        self.active_duration = 0.70 if self.boss.phase == 1 else 0.55
        self.recovery_duration = 1.10
        self.sweep_angle = 0.0
        self.sweep_hit_done = False

        # 바닥 위험 예고 링 생성 (보스 위치 고정)
        bx, by = self.boss.pos.x, self.boss.pos.y
        ind = GroundDangerIndicator(g.render, bx, by, self.sweep_radius, LColor(1.0, 0.22, 0.18, 0.70))
        self.indicators.append(ind)

        if hasattr(self.boss, 'set_sweep_telegraph_pose'):
            self.boss.set_sweep_telegraph_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 360도 뼈팔 휩쓸기 예고!", (1.0, 0.35, 0.2, 1.0))

    def _update_sweep_telegraph(self, dt, g):
        pct = min(1.0, self.timer / self.telegraph_duration)
        for ind in self.indicators:
            ind.set_progress(pct)

        # 예고 종료 -> 발동 전환
        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0
            if hasattr(self.boss, 'set_sweep_telegraph_pose'):
                self.boss.set_sweep_telegraph_pose(False)
            if hasattr(g, 'audio_mgr') and g.audio_mgr:
                g.audio_mgr.play_monster_3d("serp_slither", self.boss.node, volume_scale=1.5)

    def _update_sweep_active(self, dt, g, px, py, pz, dist, dist_z):
        pct = min(1.0, self.timer / self.active_duration)
        previous_angle = self.sweep_angle
        # 360도 연속 회전각 (0도 ~ 360도)
        self.sweep_angle = pct * 360.0
        if hasattr(self.boss, 'set_sweep_arm_angle'):
            self.boss.set_sweep_arm_angle(self.sweep_angle)

        # 발 높이와 회전 구간을 기준으로 점프 회피 및 단일 타격 판정
        feet_z = pz - PLAYER_EYE_HEIGHT
        local = self.boss.node.getRelativePoint(g.render, Vec3(px, py, pz))
        if (not self.sweep_hit_done and math.hypot(local.x, local.y) <= self.sweep_radius
                and feet_z <= self.boss.pos.z + .78
                and clear_attack_path(g, self.boss.pos.x, self.boss.pos.y, px, py)):
            # 두 팔의 실제 회전 구간을 검사하여 낮은 FPS에서도 건너뛴 각도를 처리한다.
            player_angle = math.degrees(math.atan2(local.y, local.x)) % 180.0
            crossed = any(previous_angle - 12 <= player_angle + k * 180 <= self.sweep_angle + 12
                          for k in range(-1, 3))
            if crossed:
                self.sweep_hit_done = True
                damage = boss_damage(self.boss, 36 if self.boss.phase == 2 else 28)
                is_dead = g.player.take_damage(damage, source_pos=(self.boss.pos.x, self.boss.pos.y))
                if hasattr(g, 'player'):
                    g.player.trigger_quake_shake(intensity=2.0, duration=0.35)
                if hasattr(g, 'ui_mgr') and g.ui_mgr:
                    g.ui_mgr.show_hit_marker("골해의 지배자: 360도 뼈팔 강타 피격!", (1.0, 0.15, 0.15, 1.0))
                if is_dead:
                    g.trigger_game_over(killer=self.boss, reason="killed")
                    return True

        # 발동 완료 -> 회복 전환
        if self.timer >= self.active_duration:
            self._enter_recovery(1.10)
            self.sweep_cooldown = 4.2 if self.boss.phase == 2 else 5.8
        return False

    # --------------------------------------------------------------------------
    # 2. 순차 뼈 가시 분출 (Sequential Bone Spike Eruption)
    # --------------------------------------------------------------------------
    def _start_bone_spikes(self, g, px, py):
        self.current_pattern = "spikes"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 0.90 if self.boss.phase == 1 else 0.80
        self.active_duration = 1.30
        self.recovery_duration = 1.00

        # 시전 시작 당시 플레이어 위치를 기반으로 3개 위치 고정 (플레이어가 걸어서 회피 가능)
        offsets = [
            (0.0, 0.0),             # 지점 1: 플레이어 현재 위치
            (2.2, 1.0),             # 지점 2: 인접 위치 A
            (-1.8, 1.8),            # 지점 3: 인접 위치 B
        ]
        self.spike_targets.clear()
        for i, (ox, oy) in enumerate(offsets):
            tx = px + ox
            ty = py + oy
            # 예고 인디케이터 생성
            ind = GroundDangerIndicator(g.render, tx, ty, radius=1.75, color=LColor(1.0, 0.40, 0.10, 0.70))
            self.indicators.append(ind)
            # 분출 시각 (0.0초, 0.35초, 0.70초 간격 순차 분출)
            erupt_time = i * 0.35
            self.spike_targets.append({
                'x': tx, 'y': ty, 'erupt_time': erupt_time,
                'erupted': False, 'hit_done': False, 'spike_obj': None,
                'ind_idx': i
            })

        if hasattr(self.boss, 'set_cast_roar_pose'):
            self.boss.set_cast_roar_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 뼈 가시 분출 예고! (범위 이탈 요망)", (1.0, 0.5, 0.1, 1.0))

    def _update_spikes_telegraph(self, dt, g):
        pct = min(1.0, self.timer / self.telegraph_duration)
        for ind in self.indicators:
            ind.set_progress(pct)

        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0
            if hasattr(self.boss, 'set_cast_roar_pose'):
                self.boss.set_cast_roar_pose(False)

    def _update_spikes_active(self, dt, g, px, py, pz):
        for target in self.spike_targets:
            # 순차 분출 타이밍 도달
            if self.timer >= target['erupt_time'] and not target['erupted']:
                target['erupted'] = True
                # 3D 뼈 침 소환 및 솟구침
                spike = GroundBoneSpike(g.render, target['x'], target['y'], max_height=2.3)
                spike.set_height_ratio(1.0)
                self.bone_spikes.append(spike)
                target['spike_obj'] = spike

                if hasattr(g, 'audio_mgr') and g.audio_mgr:
                    g.audio_mgr.play_orc_slam()

                # 타격 판정: 해당 지점 반경 1.75m 이내에 있는 경우만 단일 피격
                dist_to_spike = math.hypot(px - target['x'], py - target['y'])
                if (dist_to_spike <= 1.75 and not target['hit_done']
                        and pz - PLAYER_EYE_HEIGHT <= 2.3
                        and clear_attack_path(g, self.boss.pos.x, self.boss.pos.y, px, py)
                        and clear_attack_path(g, target['x'], target['y'], px, py)):
                    target['hit_done'] = True
                    damage = boss_damage(self.boss, 26 if self.boss.phase == 2 else 20)
                    is_dead = g.player.take_damage(damage, source_pos=(target['x'], target['y']))
                    if hasattr(g, 'player'):
                        g.player.apply_slow(duration=1.8, factor=0.55)
                        g.player.trigger_quake_shake(intensity=1.8, duration=0.30)
                    if hasattr(g, 'ui_mgr') and g.ui_mgr:
                        g.ui_mgr.show_hit_marker("뼈 가시 피격! (이동속도 둔화)", (1.0, 0.4, 0.1, 1.0))
                    if is_dead:
                        g.trigger_game_over(killer=self.boss, reason="killed")
                        return True

        if self.timer >= self.active_duration:
            self._enter_recovery(1.00)
            self.spikes_cooldown = 5.2 if self.boss.phase == 2 else 6.8
        return False

    # --------------------------------------------------------------------------
    # 3. 거미 다리 도약 강타 (Spider Leap Slam)
    # --------------------------------------------------------------------------
    def _can_leap_to_target(self, g, px, py):
        """기존 resolve_collision을 활용하여 벽 너머가 아닌 안전한 착지점 확인"""
        broken_legs = sum(1 for hp in getattr(self.boss, 'leg_hp', []) if hp <= 0)
        if broken_legs >= 4:
            return False
        bx, by = self.boss.pos.x, self.boss.pos.y
        dx = px - bx
        dy = py - by
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return False

        # 최대 11.0m 도약 거리 제한
        jump_dist = min(dist, 11.0)
        ndx = dx / dist
        ndy = dy / dist

        desired_x, desired_y = bx + ndx * jump_dist, by + ndy * jump_dist
        if not clear_attack_path(g, bx, by, desired_x, desired_y,
                                 padding=self.boss.col_radius):
            return False
        cand_x, cand_y = resolve_collision(
            getattr(g, 'chunks', {}),
            bx, by,
            ndx * jump_dist, ndy * jump_dist,
            radius=getattr(self.boss, 'col_radius', 0.55),
            curr_z=self.boss.pos.z
        )
        actual_reach = math.hypot(cand_x - bx, cand_y - by)
        # 장애물에 바로 막혀 1.5m도 못 뛰면 도약 취소
        if actual_reach < 1.8 or math.hypot(cand_x-desired_x, cand_y-desired_y) > .05:
            return False

        self.leap_start = Vec3(bx, by, self.boss.pos.z)
        self.leap_target = Vec3(cand_x, cand_y, self.boss.pos.z)
        return True

    def _start_spider_leap_slam(self, g, px, py):
        self.current_pattern = "leap"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 0.90 if self.boss.phase == 1 else 0.80
        self.active_duration = 0.65
        self.recovery_duration = 1.35
        self.leap_hit_done = False

        # 고정된 착지 위치에 위험 예고 링 생성
        ind = GroundDangerIndicator(g.render, self.leap_target.x, self.leap_target.y,
                                    radius=self.leap_radius, color=LColor(1.0, 0.18, 0.18, 0.75))
        self.indicators.append(ind)

        if hasattr(self.boss, 'set_crouch_pose'):
            self.boss.set_crouch_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 거미 다리 도약 강타 예고!", (1.0, 0.2, 0.2, 1.0))

    def _update_leap_telegraph(self, dt, g):
        pct = min(1.0, self.timer / self.telegraph_duration)
        for ind in self.indicators:
            ind.set_progress(pct)

        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0
            if hasattr(self.boss, 'set_crouch_pose'):
                self.boss.set_crouch_pose(False)

    def _update_leap_active(self, dt, g, px, py, pz):
        pct = min(1.0, self.timer / self.active_duration)

        # 포물선 도약 이동 (X, Y는 선형 보간, Z는 호를 그리며 최대 3.0m 솟구침)
        curr_x = self.leap_start.x + (self.leap_target.x - self.leap_start.x) * pct
        curr_y = self.leap_start.y + (self.leap_target.y - self.leap_start.y) * pct
        arc_z = math.sin(pct * math.pi) * 3.0
        floor_z = self.leap_target.z

        safe_x, safe_y = resolve_collision(getattr(g, 'chunks', {}),
            self.boss.pos.x, self.boss.pos.y, curr_x-self.boss.pos.x, curr_y-self.boss.pos.y,
            radius=self.boss.col_radius, curr_z=floor_z)
        if math.hypot(safe_x-curr_x, safe_y-curr_y) > .05:
            self.boss.pos.set(safe_x, safe_y, floor_z)
            self.boss.node.setPos(self.boss.pos)
            self.leap_hit_done = True
            self.leap_cooldown = 6.5
            self._enter_recovery(1.0)
            return False

        self.boss.pos.x = curr_x
        self.boss.pos.y = curr_y
        self.boss.pos.z = floor_z + arc_z
        self.boss.node.setPos(self.boss.pos)

        # 착지 순간 충격파 및 단일 타격 적용
        if pct >= 1.0 and not self.leap_hit_done:
            self.leap_hit_done = True
            self.boss.pos.z = floor_z
            self.boss.node.setPos(self.boss.pos)

            # 지진 충격파 이펙트 생성
            if hasattr(g, 'shockwaves') and g.shockwaves is not None:
                g.shockwaves.append(GroundShockwave(g.render, self.leap_target.x, self.leap_target.y))

            if hasattr(g, 'audio_mgr') and g.audio_mgr:
                g.audio_mgr.play_orc_slam()

            # 착지점 반경 3.5m 이내 플레이어에게 피해
            dist_to_impact = math.hypot(px - self.leap_target.x, py - self.leap_target.y)
            if (dist_to_impact <= self.leap_radius
                    and pz - PLAYER_EYE_HEIGHT <= floor_z + .78
                    and clear_attack_path(g, self.leap_target.x, self.leap_target.y, px, py)):
                damage = boss_damage(self.boss, 38 if self.boss.phase == 2 else 30)
                is_dead = g.player.take_damage(damage, source_pos=(self.leap_target.x, self.leap_target.y))
                if hasattr(g, 'player'):
                    g.player.trigger_quake_shake(intensity=3.4, duration=0.85)
                    g.player.apply_slow(duration=2.2, factor=0.45)
                if hasattr(g, 'ui_mgr') and g.ui_mgr:
                    g.ui_mgr.show_hit_marker("도약 강타 충격파 피격!", (1.0, 0.2, 0.2, 1.0))
                if is_dead:
                    g.trigger_game_over(killer=self.boss, reason="killed")
                    return True

        if self.timer >= self.active_duration:
            self._enter_recovery(1.35)
            self.leap_cooldown = 6.5 if self.boss.phase == 2 else 8.5
        return False

    # --------------------------------------------------------------------------
    # 4. 뼈 파편 일제사격 (Bone Shard Volley)
    # --------------------------------------------------------------------------
    def _start_bone_volley(self, g, px, py, pz):
        self.current_pattern = "volley"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 0.80
        self.active_duration = 0.35
        self.recovery_duration = 0.85
        bx, by = self.boss.pos.x, self.boss.pos.y
        base_rad = math.atan2(py-by, px-bx)
        angles = (-18, -9, 0, 9, 18) if self.boss.phase == 2 else (-14, 0, 14)
        self.volley_targets = []
        indicator = GroundDangerIndicator(g.render, bx, by, 1.0)
        lines = LineSegs('volley_warning')
        lines.setColor(1, .55, .12, .7)
        lines.setThickness(2)
        for spread in angles:
            rad = base_rad + math.radians(spread)
            dx, dy = math.cos(rad)*25, math.sin(rad)*25
            self.volley_targets.append((bx+dx, by+dy, pz))
            lines.moveTo(0, 0, .02)
            lines.drawTo(dx, dy, .02)
        indicator.node.attachNewNode(lines.create())
        self.indicators.append(indicator)

        if hasattr(self.boss, 'set_rib_flare_pose'):
            self.boss.set_rib_flare_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 원거리 일제사격 준비!", (0.9, 0.8, 0.3, 1.0))

    def _update_volley_telegraph(self, dt, g):
        for indicator in self.indicators:
            indicator.set_progress(min(1.0, self.timer / self.telegraph_duration))
        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0

    def _update_volley_active(self, dt, g, px, py, pz):
        bx, by, bz = self.boss.pos.x, self.boss.pos.y, self.boss.pos.z
        start_pos = (bx, by, bz + 2.5)

        for target_p in self.volley_targets:
            if hasattr(g, 'spawn_fireball'):
                g.spawn_fireball(start_pos, target_p,
                                 damage_scale=getattr(self.boss, 'damage_scale', 1.0))

        if hasattr(g, 'audio_mgr') and g.audio_mgr:
            g.audio_mgr.play_witch_cast()

        if hasattr(self.boss, 'set_rib_flare_pose'):
            self.boss.set_rib_flare_pose(False)

        self._enter_recovery(0.85)
        self.volley_cooldown = 4.0 if self.boss.phase == 2 else 5.5
        return False

    # --------------------------------------------------------------------------
    # 회복(Recovery) 상태 처리 (해골 두개골 약점 노출 기회)
    # --------------------------------------------------------------------------
    def _enter_recovery(self, duration):
        self.pending_chain = self.boss.phase == 2 and self.current_pattern == 'spikes'
        if self.pending_chain:
            duration = .40
        self.state = BossPatternState.RECOVERY
        self.timer = 0.0
        self.recovery_duration = duration
        self.is_skull_exposed = True

        # 바닥 위험 인디케이터 정리
        for ind in self.indicators:
            try:
                ind.destroy()
            except Exception:
                pass
        self.indicators.clear()

        if hasattr(self.boss, 'set_recovery_pose'):
            self.boss.set_recovery_pose(True)

    def _update_recovery(self, dt, g, px, py, pz):
        # 스파이크 노드 잔류 시간 경과 시 정리
        if self.timer > 0.45 and self.bone_spikes:
            for sp in self.bone_spikes:
                try:
                    sp.destroy()
                except Exception:
                    pass
            self.bone_spikes.clear()

        if self.timer >= self.recovery_duration:
            chain = self.pending_chain
            self.cleanup()
            self.boss.set_recovery_pose(False)
            if chain:
                if self._can_leap_to_target(g, px, py):
                    self._start_spider_leap_slam(g, px, py)
                else:
                    self._start_bone_volley(g, px, py, pz)
                return False
            self.state = BossPatternState.IDLE
            self.current_pattern = None
            self.timer = 0.0
            self.is_skull_exposed = False
            if hasattr(self.boss, 'set_recovery_pose'):
                self.boss.set_recovery_pose(False)
        return False

    # --------------------------------------------------------------------------
    # 메인 스테이트 머신 디스패처
    # --------------------------------------------------------------------------
    def _update_telegraph(self, dt, g, px, py, pz, dist, dist_z):
        self.timer += dt
        if self.current_pattern == "sweep":
            self._update_sweep_telegraph(dt, g)
        elif self.current_pattern == "spikes":
            self._update_spikes_telegraph(dt, g)
        elif self.current_pattern == "leap":
            self._update_leap_telegraph(dt, g)
        elif self.current_pattern == "volley":
            self._update_volley_telegraph(dt, g)
        elif self.current_pattern == "fan_wave":
            self._update_fan_wave_telegraph(dt, g)
        elif self.current_pattern == "seal":
            self._update_seal_telegraph(dt, g)
        return False

    def _update_active(self, dt, g, px, py, pz, dist, dist_z):
        self.timer += dt
        if self.current_pattern == "sweep":
            return self._update_sweep_active(dt, g, px, py, pz, dist, dist_z)
        elif self.current_pattern == "spikes":
            return self._update_spikes_active(dt, g, px, py, pz)
        elif self.current_pattern == "leap":
            return self._update_leap_active(dt, g, px, py, pz)
        elif self.current_pattern == "volley":
            return self._update_volley_active(dt, g, px, py, pz)
        elif self.current_pattern == "fan_wave":
            return self._update_fan_wave_active(dt, g, px, py, pz)
        elif self.current_pattern == "seal":
            return self._update_seal_active(dt, g, px, py, pz)
        return False


    # --------------------------------------------------------------------------
    # 5. 뼈 부채꼴 파동 (Bone Fan Wave - 3층부터)
    # --------------------------------------------------------------------------
    def _can_start_fan_wave(self, g, px, py):
        bx, by = self.boss.pos.x, self.boss.pos.y
        dx = px - bx
        dy = py - by
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return False
        ang = math.atan2(dy, dx)
        safe_x = bx + math.cos(ang) * 6.0
        safe_y = by + math.sin(ang) * 6.0
        if not clear_attack_path(g, bx, by, safe_x, safe_y, padding=0.5):
            return False
        return True

    def _start_bone_fan_wave(self, g, px, py):
        self.current_pattern = "fan_wave"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 1.10
        self.active_duration = 0.50
        self.recovery_duration = 0.90
        self.fan_wave_hit_done = False
        self.fan_wave_angle = math.atan2(py - self.boss.pos.y, px - self.boss.pos.x)

        ind = FanWaveIndicator(getattr(g, 'render', None), self.boss.pos.x, self.boss.pos.y,
                               radius=14.0, angle=self.fan_wave_angle)
        self.indicators.append(ind)

        if hasattr(self.boss, 'set_cast_roar_pose'):
            self.boss.set_cast_roar_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 뼈 부채꼴 파동 예고! (중앙 통로로 회피하세요)", (1.0, 0.45, 0.2, 1.0))

    def _update_fan_wave_telegraph(self, dt, g):
        pct = min(1.0, self.timer / self.telegraph_duration)
        for ind in self.indicators:
            ind.set_progress(pct)

        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0
            if hasattr(self.boss, 'set_cast_roar_pose'):
                self.boss.set_cast_roar_pose(False)
            if hasattr(g, 'audio_mgr') and g.audio_mgr:
                g.audio_mgr.play_orc_slam()

    def _update_fan_wave_active(self, dt, g, px, py, pz):
        if not self.fan_wave_hit_done:
            self.fan_wave_hit_done = True
            bx, by = self.boss.pos.x, self.boss.pos.y
            dist_p = math.hypot(px - bx, py - by)
            boss_z = getattr(self.boss.pos, 'z', 0.0)
            if dist_p <= 14.0 and abs(pz - PLAYER_EYE_HEIGHT - boss_z) <= 2.2:
                p_angle = math.atan2(py - by, px - bx)
                diff = (p_angle - self.fan_wave_angle + math.pi) % (2 * math.pi) - math.pi
                diff_deg = abs(math.degrees(diff))
                # 12도 ~ 60도 사이 위험 영역 판정
                if 12.0 <= diff_deg <= 60.0:
                    if clear_attack_path(g, bx, by, px, py, padding=0.2):
                        damage = boss_damage(self.boss, 34 if self.boss.phase == 2 else 28)
                        is_dead = g.player.take_damage(damage, source_pos=(bx, by))
                        if hasattr(g, 'player') and hasattr(g.player, 'trigger_quake_shake'):
                            g.player.trigger_quake_shake(intensity=2.5, duration=0.6)
                        if hasattr(g, 'ui_mgr') and g.ui_mgr:
                            g.ui_mgr.show_hit_marker("뼈 부채꼴 파동 피격!", (1.0, 0.2, 0.2, 1.0))
                        if is_dead:
                            g.trigger_game_over(killer=self.boss, reason="killed")
                            return True

        if self.timer >= self.active_duration:
            self._enter_recovery(self.recovery_duration)
            self.fan_wave_cooldown = 6.0 if self.boss.phase == 2 else 8.0
        return False

    # --------------------------------------------------------------------------
    # 6. 뼈 심장 봉인 (Bone Heart Seal - 5층부터)
    # --------------------------------------------------------------------------
    def _can_spawn_seals(self, g, px, py):
        if getattr(self.boss, 'stage_level', getattr(g, 'current_stage', 1)) < 5:
            return False
        if self.seal_cooldown > 0.0 or self.is_protecting or self.active_seals:
            return False
        bx, by = self.boss.pos.x, self.boss.pos.y
        dx = px - bx
        dy = py - by
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return False
        nx = -dy / dist
        ny = dx / dist

        positions = []
        for side in (-1, 1):
            cand_x = bx + nx * (3.8 * side)
            cand_y = by + ny * (3.8 * side)
            if clear_attack_path(g, bx, by, cand_x, cand_y, padding=0.5):
                cand_resolved_x, cand_resolved_y = resolve_collision(
                    getattr(g, 'chunks', {}), bx, by, cand_x - bx, cand_y - by,
                    radius=0.6, curr_z=self.boss.pos.z
                )
                if math.hypot(cand_resolved_x - cand_x, cand_resolved_y - cand_y) < 0.2:
                    positions.append((cand_x, cand_y))
        self.seal_positions = positions
        return len(positions) >= 1

    def _start_bone_heart_seal(self, g, px, py):
        if not self._can_spawn_seals(g, px, py):
            return
        self.current_pattern = "seal"
        self.state = BossPatternState.TELEGRAPH
        self.timer = 0.0
        self.telegraph_duration = 0.85
        self.active_duration = 8.0
        self.seal_timer = 8.0
        self.is_protecting = False

        bx, by = self.boss.pos.x, self.boss.pos.y
        ind = GroundDangerIndicator(getattr(g, 'render', None), bx, by, radius=4.0, color=LColor(0.2, 0.8, 1.0, 0.6))
        self.indicators.append(ind)

        if hasattr(self.boss, 'set_cast_roar_pose'):
            self.boss.set_cast_roar_pose(True)

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("골해의 지배자: 뼈 심장 봉인 시전 중!", (0.35, 0.9, 1.0, 1.0))

    def _update_seal_telegraph(self, dt, g):
        pct = min(1.0, self.timer / self.telegraph_duration)
        for ind in self.indicators:
            ind.set_progress(pct)

        if self.timer >= self.telegraph_duration:
            self.state = BossPatternState.ACTIVE
            self.timer = 0.0
            self.is_protecting = True
            if hasattr(self.boss, 'set_cast_roar_pose'):
                self.boss.set_cast_roar_pose(False)
            if hasattr(self.boss, 'set_bone_shield'):
                self.boss.set_bone_shield(True)

            bx, by = self.boss.pos.x, self.boss.pos.y

            limb_scale = getattr(self.boss, 'limb_health_scale', 1.0)
            seal_hp = 120.0 * limb_scale

            for cand_x, cand_y in self.seal_positions:
                if clear_attack_path(g, bx, by, cand_x, cand_y, padding=0.5):
                    seal = BoneHeartSeal(getattr(g, 'render', None), cand_x, cand_y, self.boss.pos.z, hp=seal_hp)
                    self.active_seals.append(seal)
                    if len(self.active_seals) >= 2:
                        break

            if not self.active_seals:
                self.cleanup()
                self.seal_cooldown = 4.0
                if hasattr(self.boss, 'set_cast_roar_pose'):
                    self.boss.set_cast_roar_pose(False)
                return

            if hasattr(g, 'ui_mgr') and g.ui_mgr:
                g.ui_mgr.show_hit_marker("골해의 지배자: 뼈 심장 봉인 활성화! (피해 60% 감소 / 봉인을 파괴하세요)", (0.4, 0.9, 1.0, 1.0))

    def _update_seal_active(self, dt, g, px, py, pz):
        self.seal_timer -= dt

        self.active_seals = [s for s in self.active_seals if not s.is_destroyed and s.hp > 0]
        for s in self.active_seals:
            s.update(dt)

        # 조건 1: 모든 봉인 파괴 성공 -> 방어막 해제 및 2초 스턴/약점 노출
        if len(self.active_seals) == 0:
            self.is_protecting = False
            if hasattr(self.boss, 'set_bone_shield'):
                self.boss.set_bone_shield(False)
            self.boss.stun_timer = 2.0
            self.is_skull_exposed = True
            if hasattr(g, 'ui_mgr') and g.ui_mgr:
                g.ui_mgr.show_hit_marker("[봉인 해제!] 보스 방어막 파괴 & 2초간 두개골 취약 노출!", (0.2, 1.0, 0.4, 1.0))
            # The director pauses pattern updates during the two-second stun.
            # Do not add another two seconds of exposure after it expires.
            self._enter_recovery(0.0)
            self.seal_cooldown = 18.0
            return False

        # 조건 2: 8초 시간 초과 -> 방어막 해제, 봉인 소멸 (스턴 보상 없음)
        if self.seal_timer <= 0.0:
            self.is_protecting = False
            if hasattr(self.boss, 'set_bone_shield'):
                self.boss.set_bone_shield(False)
            for s in self.active_seals:
                s.destroy()
            self.active_seals.clear()
            self._enter_recovery(1.0)
            self.is_skull_exposed = False
            self.seal_cooldown = 14.0
            return False

        return False
