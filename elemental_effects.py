"""
elemental_effects.py - 몬스터 원소 상태이상 시각 효과 (화염 피해 & 전기 피해)

몬스터가 화염 피해(드래곤 브레스, 유류 드럼통 폭발 등)를 입을 때 몬스터 몸체를
휘감는 역동적인 불길(Flame Jets), 상승하는 불씨(Embers), 열기 발광 및 짙은 연막,
전기 피해(테슬라 아크, 고전압 방전 등)를 입을 때 몬스터 전신을 타고 흐르는
고전압 지그재그 번개 아크(Lightning Arcs), 전기 스파크 및 스트로브 방전 섬광을 구현합니다.
"""

import math
import random
from panda3d.core import Vec3, LColor, TransparencyAttrib, NodePath
from geometry import make_sphere_to, make_cube_to, make_cylinder_to


def get_monster_dimensions(monster):
    """몬스터 종류별 신장(Height) 및 외형 반경(Radius) 반환"""
    cls_name = monster.__class__.__name__
    name = getattr(monster, 'name', '')

    if cls_name == 'CableOverlordBoss' or '보스' in name or 'Cable' in cls_name:
        return 4.5, 1.45
    elif cls_name == 'TallSkeletonMonster' or '해골' in name:
        return 3.2, 0.85
    elif cls_name == 'AbominableMudOrc' or '오크' in name:
        return 2.5, 1.15
    elif cls_name == 'LongBlackSerpent' or '뱀' in name:
        return 2.4, 0.95
    elif cls_name == 'AlluringAshWitch' or '마녀' in name:
        return 2.2, 0.80
    elif cls_name == 'SkeletalDobermanHellhound' or '파수견' in name or 'Hound' in cls_name:
        return 1.3, 0.65
    return 2.2, 0.85


class ElementalMonsterMixin:
    """모든 몬스터 공통 원소 상태이상(화염 DoT 및 전기 감전) 처리 믹스인"""
    burn_timer = 0.0
    burn_dps = 0.0
    shock_timer = 0.0
    _elemental_fx = None

    @property
    def elemental_fx(self):
        if getattr(self, '_elemental_fx', None) is None:
            if hasattr(self, 'node') and self.node is not None and not self.node.isEmpty():
                self._elemental_fx = MonsterElementalVisuals(self)
        return self._elemental_fx

    def apply_burn(self, dps=25.0, duration=3.0):
        """지속 화염 피해 및 타오르는 화염 시각 효과 부여"""
        self.burn_dps = max(getattr(self, 'burn_dps', 0.0), dps)
        self.burn_timer = max(getattr(self, 'burn_timer', 0.0), duration)
        fx = self.elemental_fx
        if fx:
            fx.trigger_burn(duration)

    def apply_shock(self, damage=0.0, duration=0.65, hit_pos=None):
        """전기 충격 피해, 스턴 및 생성지 중심 고전압 번개 아크 시각 효과 부여"""
        if damage > 0.0:
            self.take_damage(damage, apply_knockback=True)
        if hasattr(self, 'stun'):
            self.stun(duration)
        self.shock_timer = max(getattr(self, 'shock_timer', 0.0), duration)
        fx = self.elemental_fx
        if fx:
            fx.trigger_shock(duration, hit_pos=hit_pos)

    def update_elemental(self, dt):
        """매 프레임 화염 피해 DoT 연산 및 시각 효과 갱신"""
        # 화염 지속 피해 처리
        if getattr(self, 'burn_timer', 0.0) > 0.0:
            self.burn_timer = max(0.0, self.burn_timer - dt)
            burn_damage = getattr(self, 'burn_dps', 25.0) * dt
            if burn_damage > 0.0 and getattr(self, 'hp', 0) > 0:
                self.take_damage(burn_damage, apply_knockback=False, damage_type='dot')
            if self.burn_timer <= 0.0:
                self.burn_dps = 0.0

        # 전기 지속 타이머 처리
        if getattr(self, 'shock_timer', 0.0) > 0.0:
            self.shock_timer = max(0.0, self.shock_timer - dt)

        # 시각 효과 갱신
        if getattr(self, '_elemental_fx', None) is not None:
            self._elemental_fx.update(dt)

    def cleanup_elemental(self):
        """사망/파괴 시 원소 이펙트 정리"""
        if getattr(self, '_elemental_fx', None) is not None:
            self._elemental_fx.destroy()
            self._elemental_fx = None


class MonsterElementalVisuals:
    """몬스터 노드에 종속되어 화염 및 전기 원소 시각 효과를 렌더링하는 시각 컴포넌트"""

    def __init__(self, monster):
        self.monster = monster
        self.height, self.radius = get_monster_dimensions(monster)
        self.anim_time = random.uniform(0.0, 10.0)
        self.is_destroyed = False

        # 생성지(Shock Origin): 기본값은 몬스터 흉부/체심
        self.shock_origin = Vec3(0, 0, self.height * 0.55)

        parent_node = monster.node if hasattr(monster, 'node') and not monster.node.isEmpty() else None
        if parent_node is None:
            self.fx_root = NodePath("elemental_fx_orphan")
        else:
            self.fx_root = parent_node.attachNewNode("elemental_fx")

        # 1. 화염 시각 효과 루트
        self.fire_root = self.fx_root.attachNewNode("fire_fx")
        self.fire_particles = []
        self.ember_particles = []
        self.smoke_particles = []
        self._build_fire_fx()
        self.fire_root.hide()

        # 2. 전기 시각 효과 루트 (생성지 중심 방사형 번개 아크)
        self.shock_root = self.fx_root.attachNewNode("shock_fx")
        self.shock_arcs = []
        self.shock_sparks = []
        self._build_shock_fx()
        self.shock_root.hide()

    def _build_fire_fx(self):
        """화염 피해 효과: 타오르는 불길 12개, 상승하는 불씨 8개, 열기 발광체 및 연막 생성"""
        # 중심 화염 발광 구체
        self.fire_glow = make_sphere_to(
            self.fire_root,
            self.radius * 1.35, self.radius * 1.35, self.height * 0.55,
            LColor(1.0, 0.45, 0.08, 0.26),
            0, 0, self.height * 0.48
        )
        self.fire_glow.setLightOff()
        self.fire_glow.setTransparency(TransparencyAttrib.MAlpha)

        # 12개의 불길 제트 파티클
        for i in range(12):
            p_node = self.fire_root.attachNewNode(f"flame_{i}")
            sz = random.uniform(0.14, 0.26)
            geom = make_sphere_to(
                p_node, sz, sz, sz * 1.4,
                LColor(1.0, 0.85, 0.25, 0.92),
                0, 0, 0
            )
            geom.setLightOff()
            p_node.setTransparency(TransparencyAttrib.MAlpha)

            ang = (i / 12.0) * math.pi * 2 + random.uniform(-0.25, 0.25)
            rad = random.uniform(0.35, 0.95) * self.radius
            base_z = random.uniform(0.15, 0.75) * self.height
            spd = random.uniform(2.2, 4.0)

            self.fire_particles.append({
                "node": p_node,
                "geom": geom,
                "ang": ang,
                "rad": rad,
                "curr_z": base_z,
                "max_z": self.height * random.uniform(0.95, 1.25),
                "spd": spd,
                "sz": sz,
                "phase": random.uniform(0.0, 6.28)
            })

        # 8개의 고속 상승 불씨 (Embers)
        for i in range(8):
            e_node = self.fire_root.attachNewNode(f"ember_{i}")
            e_sz = random.uniform(0.045, 0.08)
            geom = make_cube_to(
                e_node, e_sz, e_sz, e_sz,
                LColor(1.0, 0.92, 0.35, 1.0),
                0, 0, 0
            )
            geom.setLightOff()
            e_node.setTransparency(TransparencyAttrib.MAlpha)

            ang = random.uniform(0, math.pi * 2)
            rad = random.uniform(0.4, 1.1) * self.radius
            curr_z = random.uniform(0.2, 0.9) * self.height

            self.ember_particles.append({
                "node": e_node,
                "geom": geom,
                "ang": ang,
                "rad": rad,
                "curr_z": curr_z,
                "max_z": self.height * random.uniform(1.2, 1.6),
                "spd": random.uniform(3.5, 6.2),
                "phase": random.uniform(0, 6.28)
            })

        # 4개의 상단 검붉은 그을림 연막
        for i in range(4):
            s_node = self.fire_root.attachNewNode(f"smoke_{i}")
            s_sz = random.uniform(0.25, 0.45)
            geom = make_sphere_to(
                s_node, s_sz, s_sz, s_sz,
                LColor(0.18, 0.15, 0.14, 0.45),
                0, 0, 0
            )
            geom.setLightOff()
            s_node.setTransparency(TransparencyAttrib.MAlpha)

            self.smoke_particles.append({
                "node": s_node,
                "geom": geom,
                "ang": random.uniform(0, math.pi * 2),
                "curr_z": self.height * random.uniform(0.85, 1.3),
                "spd": random.uniform(1.2, 2.4),
                "sz": s_sz
            })

    def _build_shock_fx(self):
        """전기 피해 효과: 생성지를 중심으로 360도 방사형으로 뻗어나가는 8개 번개 줄기, 스파크 및 중심 코어 방전체 생성"""
        # 1. 생성지(Origin) 고전압 방전 중심 코어 (Origin Core)
        self.origin_core = self.shock_root.attachNewNode("shock_origin_core")
        self.origin_core_inner = make_sphere_to(
            self.origin_core, 0.16, 0.16, 0.16,
            LColor(1.0, 1.0, 1.0, 1.0), 0, 0, 0
        )
        self.origin_core_inner.setLightOff()
        self.origin_core_halo = make_sphere_to(
            self.origin_core, 0.40, 0.40, 0.40,
            LColor(0.25, 0.90, 1.0, 0.60), 0, 0, 0
        )
        self.origin_core_halo.setLightOff()
        self.origin_core.setTransparency(TransparencyAttrib.MAlpha)

        # 2. 중심 전기 방전 구체 (생성지 주변 고전압 오라)
        self.shock_glow = make_sphere_to(
            self.shock_root,
            self.radius * 1.30, self.radius * 1.30, self.height * 0.45,
            LColor(0.25, 0.85, 1.0, 0.35),
            0, 0, 0
        )
        self.shock_glow.setLightOff()
        self.shock_glow.setTransparency(TransparencyAttrib.MAlpha)

        # 3. 8개의 방사형 지그재그 번개 아크 체인 (생성지에서 외곽 및 옆 몬스터로 뻗어나감)
        # 뿌리(두꺼움/백색) -> 내측(청록색) -> 외측(청자색) -> 끝 가지(가늘음/청색)
        thicknesses = [0.052, 0.040, 0.030, 0.020]
        self.shock_arcs = []
        pitches = [-0.55, 0.55, -0.25, 0.25, -0.65, 0.65, 0.0, 0.0]

        for arc_i in range(8):
            arc_node = self.shock_root.attachNewNode(f"arc_{arc_i}")
            segments = []
            for seg_i in range(4):
                seg_node = arc_node.attachNewNode(f"seg_{seg_i}")
                thick = thicknesses[seg_i]
                geom = make_cylinder_to(
                    seg_node, thick, 0.35, thick,
                    LColor(0.40, 0.90, 1.0, 0.95),
                    0, 0, 0,
                    axis='y'
                )
                geom.setLightOff()
                seg_node.setTransparency(TransparencyAttrib.MAlpha)
                segments.append(seg_node)

            base_angle = (arc_i / 8.0) * math.pi * 2 + random.uniform(-0.15, 0.15)
            self.shock_arcs.append({
                "root": arc_node,
                "segments": segments,
                "base_angle": base_angle,
                "pitch": pitches[arc_i % len(pitches)],
                "recalc_timer": random.uniform(0.01, 0.04)
            })

        # 4. 12개의 생성지 방출 고전압 스파크 파티클
        self.shock_sparks = []
        for sp_i in range(12):
            sp_node = self.shock_root.attachNewNode(f"spark_{sp_i}")
            sp_sz = random.uniform(0.045, 0.075)
            col = LColor(0.95, 0.98, 1.0, 1.0) if sp_i % 2 == 0 else LColor(0.35, 0.88, 1.0, 0.95)
            geom = make_cube_to(
                sp_node, sp_sz, sp_sz, sp_sz,
                col, 0, 0, 0
            )
            geom.setLightOff()
            sp_node.setTransparency(TransparencyAttrib.MAlpha)

            sp_ang = random.uniform(0, math.pi * 2)
            sp_pitch = random.uniform(-0.85, 0.85)
            cos_p = math.cos(sp_pitch)
            sp_dir = Vec3(
                math.cos(sp_ang) * cos_p,
                math.sin(sp_ang) * cos_p,
                math.sin(sp_pitch)
            )
            if sp_dir.length() > 0.01:
                sp_dir.normalize()
            else:
                sp_dir = Vec3(0, 1, 0)

            self.shock_sparks.append({
                "node": sp_node,
                "geom": geom,
                "dir": sp_dir,
                "spd": random.uniform(2.5, 4.5) * self.radius,
                "age": random.uniform(0.0, 0.18),
                "max_age": random.uniform(0.12, 0.22)
            })

    def trigger_burn(self, duration=3.0):
        """화염 효과 활성화"""
        if self.is_destroyed:
            return
        if self.fire_root and not self.fire_root.isEmpty():
            self.fire_root.show()

    def set_shock_origin(self, hit_pos=None):
        """번개 줄기의 생성지(Shock Origin)를 설정 (피격 위치 또는 몬스터 흉부/체심)"""
        if hit_pos is not None:
            try:
                if hasattr(self, 'shock_root') and self.shock_root and not self.shock_root.isEmpty():
                    parent = self.monster.node.getParent() if (hasattr(self.monster, 'node') and not self.monster.node.isEmpty() and not self.monster.node.getParent().isEmpty()) else self.shock_root
                    local_p = self.shock_root.getRelativePoint(parent, hit_pos)
                else:
                    m_pos = getattr(self.monster, 'pos', Vec3(0, 0, 0))
                    local_p = Vec3(hit_pos) - m_pos

                lx = max(-self.radius * 1.15, min(self.radius * 1.15, local_p.x))
                ly = max(-self.radius * 1.15, min(self.radius * 1.15, local_p.y))
                lz = max(0.15 * self.height, min(0.90 * self.height, local_p.z))
                self.shock_origin = Vec3(lx, ly, lz)
                return
            except Exception:
                pass
        self.shock_origin = Vec3(0, 0, self.height * 0.55)

    def trigger_shock(self, duration=0.65, hit_pos=None):
        """전기 효과 활성화 및 생성지 중심 번개 아크 방출 시작"""
        if self.is_destroyed:
            return
        self.set_shock_origin(hit_pos)
        if self.shock_root and not self.shock_root.isEmpty():
            self.shock_root.show()
            self._recalc_all_lightning_arcs()

    def _find_nearby_monsters(self, max_dist=7.5):
        """현재 몬스터 기준 주변에 생존해 있는 다른 몬스터 목록 탐색 (거리순 정렬)"""
        nearby = []
        try:
            import builtins
            base_obj = getattr(builtins, 'base', None)
            if base_obj is None:
                from direct.showbase import ShowBaseGlobal
                base_obj = getattr(ShowBaseGlobal, 'base', None)
            monsters = getattr(base_obj, 'monsters', None)
            if not monsters:
                return nearby
            my_pos = getattr(self.monster, 'pos', None)
            if my_pos is None:
                return nearby

            for m in monsters:
                if m is self.monster:
                    continue
                if getattr(m, 'hp', 0) <= 0 or getattr(m, 'is_corpse', False):
                    continue
                m_pos = getattr(m, 'pos', None)
                if m_pos is None:
                    continue
                dist = math.hypot(m_pos.x - my_pos.x, m_pos.y - my_pos.y)
                if dist <= max_dist:
                    nearby.append((dist, m))

            nearby.sort(key=lambda item: item[0])
            return [item[1] for item in nearby]
        except Exception:
            return nearby

    def _get_target_for_arc(self, arc_i, nearby):
        """아크 인덱스별 연쇄 대상 옆 몬스터 매핑"""
        if not nearby:
            return None
        if len(nearby) == 1:
            if arc_i in (0, 1):
                return nearby[0]
        elif len(nearby) >= 2:
            if arc_i in (0, 1):
                return nearby[0]
            elif arc_i in (2, 3):
                return nearby[1]
            elif len(nearby) >= 3 and arc_i == 4:
                return nearby[2]
        return None

    def _recalc_all_lightning_arcs(self):
        """모든 번개 아크를 생성지 기준으로 방사형 또는 옆 몬스터 연쇄 유도로 재배치"""
        nearby = self._find_nearby_monsters(max_dist=7.5)
        for arc_i, arc in enumerate(self.shock_arcs):
            target_monster = self._get_target_for_arc(arc_i, nearby)
            self._recalc_arc(arc, target_monster=target_monster)

    def _recalc_arc(self, arc, target_monster=None):
        """생성지(shock_origin)를 중심으로 외곽 또는 옆 몬스터를 향해 뻗어나가는 4마디 번개 줄기 계산"""
        # 1) 시작점 P0: 생성지 중심 (약간의 고전압 지터 ±0.035m)
        origin = Vec3(self.shock_origin)
        p0 = origin + Vec3(
            random.uniform(-0.035, 0.035),
            random.uniform(-0.035, 0.035),
            random.uniform(-0.025, 0.025)
        )

        # -------------------------------------------------------------
        # 1. 옆 몬스터가 타깃으로 지정된 경우: 옆 몬스터의 가슴/코어까지 직접 연결되는 연쇄 번개 줄기
        # -------------------------------------------------------------
        if target_monster is not None:
            try:
                import builtins
                base_obj = getattr(builtins, 'base', None)
                if base_obj is None:
                    from direct.showbase import ShowBaseGlobal
                    base_obj = getattr(ShowBaseGlobal, 'base', None)

                h_target, _ = get_monster_dimensions(target_monster)
                t_pos = getattr(target_monster, 'pos', None)
                if t_pos is not None:
                    # 타깃 몬스터의 월드 피격점 (가슴 중심부)
                    target_world = Vec3(t_pos.x, t_pos.y, t_pos.z + h_target * 0.55)
                    render_node = getattr(base_obj, 'render', None) if base_obj else None
                    if render_node is not None and hasattr(self.shock_root, 'getRelativePoint'):
                        p_target = self.shock_root.getRelativePoint(render_node, target_world)
                    elif hasattr(self.shock_root, 'getRelativePoint'):
                        try:
                            p_target = self.shock_root.getRelativePoint(render_node, target_world)
                        except Exception:
                            my_pos = getattr(self.monster, 'pos', Vec3(0, 0, 0))
                            p_target = target_world - my_pos
                    else:
                        my_pos = getattr(self.monster, 'pos', Vec3(0, 0, 0))
                        p_target = target_world - my_pos

                    diff = p_target - p0
                    total_dist = diff.length()
                    if total_dist > 0.05:
                        fwd = diff / total_dist
                        # 진행 방향에 수직인 횡방향 지그재그 기저 벡터
                        arb = Vec3(0, 0, 1) if abs(fwd.z) < 0.8 else Vec3(1, 0, 0)
                        perp1 = fwd.cross(arb).normalized()
                        perp2 = fwd.cross(perp1).normalized()

                        # 4마디로 뻗어나가며 옆 몬스터에 도달 (P0 -> P1 -> P2 -> P3 -> P4)
                        amp = min(0.45, total_dist * 0.10)
                        p1 = p0 + fwd * (total_dist * 0.25) + perp1 * random.uniform(-amp, amp) + perp2 * random.uniform(-amp, amp)
                        p2 = p0 + fwd * (total_dist * 0.52) + perp1 * random.uniform(-amp * 1.3, amp * 1.3) + perp2 * random.uniform(-amp * 1.3, amp * 1.3)
                        p3 = p0 + fwd * (total_dist * 0.78) + perp1 * random.uniform(-amp, amp) + perp2 * random.uniform(-amp, amp)
                        p4 = p_target

                        points = [p0, p1, p2, p3, p4]
                        self._apply_points_to_arc(arc, points, fwd)

                        # 옆 몬스터에게 연쇄 감전 유도 (아직 감전되지 않은 경우)
                        if getattr(target_monster, 'shock_timer', 0.0) <= 0.0:
                            if hasattr(target_monster, 'apply_shock'):
                                target_monster.apply_shock(damage=20.0, duration=0.75, hit_pos=target_world)
                        return
            except Exception:
                pass

        # -------------------------------------------------------------
        # 2. 일반 방사형 번개 줄기: 생성지에서 360도 외곽으로 3.2m ~ 5.4m까지 대폭 확장
        # -------------------------------------------------------------
        base_ang = arc.get("base_angle", random.uniform(0, math.pi * 2))
        ang = base_ang + random.uniform(-0.25, 0.25)
        pitch = arc.get("pitch", 0.0) + random.uniform(-0.22, 0.22)

        cos_p = math.cos(pitch)
        u = Vec3(
            math.cos(ang) * cos_p,
            math.sin(ang) * cos_p,
            math.sin(pitch)
        )
        if u.length() < 0.01:
            u = Vec3(0, 1, 0)
        else:
            u.normalize()

        # u에 수직인 지그재그 기저 벡터
        arb = Vec3(0, 0, 1) if abs(u.z) < 0.8 else Vec3(1, 0, 0)
        perp1 = u.cross(arb)
        if perp1.length() < 0.01:
            perp1 = Vec3(1, 0, 0)
        else:
            perp1.normalize()
        perp2 = u.cross(perp1).normalized()

        # 확장된 4개 마디 길이 (마디당 0.8 ~ 1.35m -> 총 3.2m ~ 5.4m까지 뻗어나감)
        step_base = max(0.85, self.radius * 1.1)
        len1 = random.uniform(0.75, 1.20) * step_base
        jit1 = perp1 * random.uniform(-0.16, 0.16) + perp2 * random.uniform(-0.16, 0.16)
        p1 = p0 + u * len1 + jit1

        len2 = random.uniform(0.80, 1.30) * step_base
        u2 = (u + perp1 * random.uniform(-0.18, 0.18) + perp2 * random.uniform(-0.18, 0.18)).normalized()
        jit2 = perp1 * random.uniform(-0.22, 0.22) + perp2 * random.uniform(-0.22, 0.22)
        p2 = p1 + u2 * len2 + jit2

        len3 = random.uniform(0.85, 1.40) * step_base
        u3 = (u2 + perp1 * random.uniform(-0.20, 0.20) + perp2 * random.uniform(-0.20, 0.20)).normalized()
        jit3 = perp1 * random.uniform(-0.25, 0.25) + perp2 * random.uniform(-0.25, 0.25)
        p3 = p2 + u3 * len3 + jit3

        len4 = random.uniform(0.90, 1.45) * step_base
        u4 = (u3 + perp1 * random.uniform(-0.22, 0.22) + perp2 * random.uniform(-0.22, 0.22)).normalized()
        jit4 = perp1 * random.uniform(-0.28, 0.28) + perp2 * random.uniform(-0.28, 0.28)
        p4 = p3 + u4 * len4 + jit4

        points = [p0, p1, p2, p3, p4]
        self._apply_points_to_arc(arc, points, u)

    def _apply_points_to_arc(self, arc, points, default_dir):
        """계산된 좌표 배열을 아크 세그먼트 노드에 적용"""
        for i, seg in enumerate(arc["segments"]):
            if i + 1 >= len(points):
                break
            start = points[i]
            end = points[i + 1]
            diff = end - start
            dist = diff.length()
            if dist < 0.05:
                dist = 0.05
                end = start + default_dir * 0.05

            mid = (start + end) * 0.5
            seg.setPos(mid)
            scale_y = max(0.08, dist / 0.35)
            seg.setScale(1.0, scale_y, 1.0)
            try:
                seg.lookAt(self.shock_root, end)
            except Exception:
                pass

    def update(self, dt):
        """매 프레임 몬스터의 원소 상태이상 타이머 검사 및 애니메이션 갱신"""
        if self.is_destroyed or self.fx_root.isEmpty():
            return

        self.anim_time += dt
        t = self.anim_time

        burn_timer = getattr(self.monster, 'burn_timer', 0.0)
        shock_timer = getattr(self.monster, 'shock_timer', 0.0)

        # -----------------------------------------------------------------
        # 1. 화염 피해 효과 갱신
        # -----------------------------------------------------------------
        if burn_timer > 0.0:
            if self.fire_root.isHidden():
                self.fire_root.show()

            # 화염 중심 발광체 맥동 (Heat Flicker)
            heat_pulse = 0.5 + 0.5 * math.sin(t * 22.0)
            self.fire_glow.setColorScale(
                1.0,
                0.55 + heat_pulse * 0.35,
                0.25 + heat_pulse * 0.35,
                0.24 + heat_pulse * 0.16
            )

            # 불길 제트 파티클 상승 및 역동적 형태 변화
            for p in self.fire_particles:
                p["curr_z"] += p["spd"] * dt
                progress = min(1.0, p["curr_z"] / p["max_z"])

                # 난류 요동
                wobble_x = math.sin(t * 8.5 + p["phase"]) * 0.09
                wobble_y = math.cos(t * 8.5 + p["phase"]) * 0.09
                cur_rad = p["rad"] * (1.0 - progress * 0.45)
                px = math.cos(p["ang"] + wobble_x) * cur_rad + wobble_x
                py = math.sin(p["ang"] + wobble_y) * cur_rad + wobble_y
                p["node"].setPos(px, py, p["curr_z"])

                # 하단 밝은 황금색 -> 중단 타오르는 주황색 -> 상단 붉은 그을림
                if progress < 0.35:
                    col = LColor(1.0, 0.90, 0.25, 0.95)
                    scale_mult = 0.8 + (progress / 0.35) * 0.5
                elif progress < 0.75:
                    col = LColor(1.0, 0.45, 0.08, 0.85)
                    scale_mult = 1.3 - ((progress - 0.35) / 0.40) * 0.4
                else:
                    fade = max(0.0, 1.0 - (progress - 0.75) / 0.25)
                    col = LColor(0.65, 0.18, 0.05, 0.70 * fade)
                    scale_mult = max(0.08, 0.9 * fade)

                p["geom"].setColor(col)
                p["node"].setScale(max(0.08, scale_mult))

                # 상단 도달 시 바닥에서 재순환
                if p["curr_z"] >= p["max_z"]:
                    p["curr_z"] = random.uniform(0.08, 0.32) * self.height
                    p["ang"] = random.uniform(0, math.pi * 2)
                    p["rad"] = random.uniform(0.35, 0.95) * self.radius

            # 불씨(Embers) 상승
            for e in self.ember_particles:
                e["curr_z"] += e["spd"] * dt
                swirl_x = math.sin(t * 11.0 + e["phase"]) * 0.12
                swirl_y = math.cos(t * 11.0 + e["phase"]) * 0.12
                ex = math.cos(e["ang"]) * e["rad"] + swirl_x
                ey = math.sin(e["ang"]) * e["rad"] + swirl_y
                e["node"].setPos(ex, ey, e["curr_z"])

                fade = max(0.0, 1.0 - (e["curr_z"] / e["max_z"]))
                e["geom"].setColor(LColor(1.0, 0.88, 0.25, fade))

                if e["curr_z"] >= e["max_z"]:
                    e["curr_z"] = random.uniform(0.1, 0.4) * self.height
                    e["ang"] = random.uniform(0, math.pi * 2)

            # 연막 구름(Smoke) 확산
            for s in self.smoke_particles:
                s["curr_z"] += s["spd"] * dt
                sx = math.cos(s["ang"]) * (self.radius * 0.6) + math.sin(t * 3.0) * 0.15
                sy = math.sin(s["ang"]) * (self.radius * 0.6) + math.cos(t * 3.0) * 0.15
                s["node"].setPos(sx, sy, s["curr_z"])
                if s["curr_z"] >= self.height * 1.55:
                    s["curr_z"] = self.height * random.uniform(0.75, 0.95)
        else:
            if not self.fire_root.isHidden():
                self.fire_root.hide()

        # -----------------------------------------------------------------
        # 2. 전기 피해 효과 갱신
        # -----------------------------------------------------------------
        if shock_timer > 0.0:
            if self.shock_root.isHidden():
                self.shock_root.show()

            # 1. 생성지(Origin) 고전압 방전 코어 및 발광체 갱신
            self.shock_glow.setPos(self.shock_origin)
            self.origin_core.setPos(self.shock_origin)

            # 생성지 코어 맥동 및 고주파 스트로브
            strobe = random.uniform(0.65, 1.35) if random.random() < 0.85 else 0.2
            self.shock_glow.setColorScale(0.75, 0.95, 1.3, strobe * 0.42)
            core_pulse = 0.85 + 0.35 * math.sin(t * 32.0) + random.uniform(-0.15, 0.15)
            self.origin_core.setScale(max(0.1, core_pulse))
            self.origin_core_inner.setColor(LColor(1.0, 1.0, 1.0, 0.98))
            self.origin_core_halo.setColor(LColor(0.35, 0.92, 1.0, 0.55 * max(0.2, core_pulse)))

            # 2. 각 방사형 번개 줄기별 타이머 갱신 (0.035~0.055초마다 지그재그 궤적 재점프)
            nearby = self._find_nearby_monsters(max_dist=7.5)
            for arc_i, arc in enumerate(self.shock_arcs):
                arc["recalc_timer"] -= dt
                if arc["recalc_timer"] <= 0.0:
                    arc["recalc_timer"] = random.uniform(0.035, 0.055)
                    target_monster = self._get_target_for_arc(arc_i, nearby)
                    self._recalc_arc(arc, target_monster=target_monster)
                    # 뿌리 -> 내측 -> 외측 -> 끝 가지 마디별 계층 색상/밝기 섬광
                    is_bright = (random.random() < 0.45)
                    cols = [
                        LColor(0.98, 1.0, 1.0, 1.0) if is_bright else LColor(0.85, 0.96, 1.0, 0.95),
                        LColor(0.55, 0.94, 1.0, 0.95) if is_bright else LColor(0.35, 0.86, 1.0, 0.90),
                        LColor(0.30, 0.82, 1.0, 0.90) if is_bright else LColor(0.18, 0.70, 1.0, 0.85),
                        LColor(0.18, 0.65, 1.0, 0.85) if is_bright else LColor(0.10, 0.50, 0.95, 0.70),
                    ]
                    for s_idx, seg in enumerate(arc["segments"]):
                        seg.setColorScale(cols[min(s_idx, len(cols) - 1)])

            # 3. 생성지에서 사방으로 뿜어져 나가는 전기 스파크 물리 갱신
            for sp in self.shock_sparks:
                sp["age"] += dt
                prog = sp["age"] / sp["max_age"]
                if prog >= 1.0:
                    sp["age"] = 0.0
                    sp["max_age"] = random.uniform(0.10, 0.22)
                    sp_ang = random.uniform(0, math.pi * 2)
                    sp_pitch = random.uniform(-0.85, 0.85)
                    cos_sp = math.cos(sp_pitch)
                    sp["dir"] = Vec3(
                        math.cos(sp_ang) * cos_sp,
                        math.sin(sp_ang) * cos_sp,
                        math.sin(sp_pitch)
                    )
                    if sp["dir"].length() > 0.01:
                        sp["dir"].normalize()
                    sp["spd"] = random.uniform(2.5, 4.5) * self.radius
                    prog = 0.0

                dist_travel = sp["spd"] * sp["age"]
                sp_pos = self.shock_origin + sp["dir"] * dist_travel
                sp["node"].setPos(sp_pos)
                fade = max(0.1, 1.0 - prog)
                sp["node"].setScale(max(0.1, 1.0 - prog * 0.5))
                sp["geom"].setColor(LColor(0.88, 0.98, 1.0, fade))

            # 4. 감전 시 몬스터 몸체 미세 경련(Spasm Jitter) 연출
            jitter_x = random.uniform(-0.035, 0.035)
            jitter_y = random.uniform(-0.035, 0.035)
            jitter_z = random.uniform(-0.025, 0.025)
            self.fx_root.setPos(jitter_x, jitter_y, jitter_z)
        else:
            if not self.shock_root.isHidden():
                self.shock_root.hide()
            self.fx_root.setPos(0, 0, 0)

    def destroy(self):
        """원소 이펙트 노드 완전 제거"""
        if self.is_destroyed:
            return
        self.is_destroyed = True
        if hasattr(self, 'fx_root') and not self.fx_root.isEmpty():
            self.fx_root.removeNode()
