import math
import random
from panda3d.core import Vec3, LColor, PointLight, TransparencyAttrib
from collision import get_nearby_colliders
from geometry import make_cube, make_cube_to


class Fireball:
    """매혹의 잿더미 마녀가 발사하는 타오르는 불꽃 발사체 (오브젝트 풀링 지원)"""
    def __init__(self, render):
        self.render = render
        self.node = None
        self.light_np = None
        self._build_node()

        self.damage = 22.0
        self.is_active = False
        self.pos = Vec3(0, 0, -50)
        self.vel = Vec3(0, 0, 0)
        self.lifetime = 0.0

    def _build_node(self):
        """씬그래프 노드 및 발광 조명 생성 (누락 시 즉시 자동 복구)"""
        if hasattr(self, 'node') and self.node is not None and not self.node.isEmpty():
            return
        self.node = self.render.attachNewNode("witch_fireball")
        self.node.hide()

        fire_core = make_cube("fb_core", 0.32, 0.32, 0.32, LColor(1.0, 0.28, 0.05, 1.0))
        fire_core.setLightOff()
        fire_core.reparentTo(self.node)

        fire_inner = make_cube("fb_inner", 0.18, 0.18, 0.18, LColor(1.0, 0.90, 0.30, 1.0))
        fire_inner.setLightOff()
        fire_inner.reparentTo(self.node)

        pl = PointLight('fb_glow')
        pl.setColor((1.8, 0.45, 0.10, 1.0))
        pl.setAttenuation((1.0, 0.22, 0.06))
        self.light_np = self.node.attachNewNode(pl)

    def activate(self, start_pos, target_pos):
        if not hasattr(self, 'node') or self.node is None or self.node.isEmpty():
            self._build_node()

        self.pos = Vec3(start_pos)
        self.node.setPos(self.pos)
        self.node.show()
        if hasattr(self, 'light_np') and self.light_np is not None and not self.light_np.isEmpty():
            self.render.setLight(self.light_np)

        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]
        dz = target_pos[2] - start_pos[2]
        d = math.hypot(dx, dy, dz)
        if d > 0.01:
            self.vel = Vec3(dx / d, dy / d, dz / d) * 14.5
        else:
            self.vel = Vec3(0, 1, 0) * 14.5

        self.lifetime = 3.5
        self.is_active = True

    def deactivate(self):
        self.is_active = False
        if hasattr(self, 'light_np') and self.light_np is not None and not self.light_np.isEmpty():
            self.render.clearLight(self.light_np)
        if hasattr(self, 'node') and self.node is not None and not self.node.isEmpty():
            self.node.hide()

    def update(self, dt):
        if not self.is_active:
            return False
        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self.deactivate()
            return False
        self.pos += self.vel * dt
        if hasattr(self, 'node') and self.node is not None and not self.node.isEmpty():
            self.node.setPos(self.pos)
            self.node.setH(self.node.getH() + dt * 400.0)
            self.node.setP(self.node.getP() + dt * 280.0)
        return True

    def destroy(self):
        self.deactivate()
        if hasattr(self, 'light_np') and self.light_np is not None and not self.light_np.isEmpty():
            self.light_np.removeNode()
            self.light_np = None
        if hasattr(self, 'node') and self.node is not None and not self.node.isEmpty():
            self.node.removeNode()
            self.node = None


class GroundShockwave:
    """혐오스런 진흙 오크의 땅울림(Ground Slam) 지면 충격파 분진 효과"""
    def __init__(self, render, x, y):
        self.render = render
        self.pos = Vec3(x, y, 0.06)
        self.node = render.attachNewNode("orc_shockwave")
        self.node.setPos(self.pos)
        self.radius = 0.6
        self.max_radius = 11.5
        self.timer = 0.0
        self.duration = 0.70

        self.fragments = []
        dust_col = LColor(0.28, 0.22, 0.14, 0.9)
        for i in range(8):
            ang = i * (math.pi / 4.0)
            p = make_cube(f"sw_{i}", 0.40, 0.40, 0.16, dust_col)
            p.reparentTo(self.node)
            self.fragments.append((p, math.cos(ang), math.sin(ang)))

    def update(self, dt):
        self.timer += dt
        pct = min(1.0, self.timer / self.duration)
        r = self.radius + pct * (self.max_radius - self.radius)
        z = math.sin(pct * math.pi) * 0.42
        for part, dx, dy in self.fragments:
            part.setPos(dx * r, dy * r, z)
            part.setScale(max(0.1, 1.0 - pct * 0.5))
        return pct < 1.0

    def destroy(self):
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class ExplosionVisualEffect:
    """수류탄 및 유류 드럼통 폭발 시 발생하는 3D 고광도 화구, 충격파 링, 고속 파편 및 연막 이펙트"""
    def __init__(self, parent, pos, render):
        self.parent = parent
        self.render = render
        self.pos = Vec3(pos)
        self.timer = 0.65
        self.max_timer = 0.65
        self.is_destroyed = False

        self.root = parent.attachNewNode("explosion_fx")
        self.root.setPos(self.pos)

        # 1. 순간 폭발 섬광 고휘도 조명 (PointLight)
        self.light = PointLight("exp_blast_light")
        self.light.setColor((4.8, 2.6, 0.6, 1.0))
        self.light.setAttenuation((1.0, 0.035, 0.008))
        self.light_np = self.root.attachNewNode(self.light)
        self.light_np.setPos(0, 0, 0.8)
        self.render.setLight(self.light_np)

        # 2. 중심 팽창 화구 (Expanding Core Fireball)
        self.core_np = self.root.attachNewNode("core_fireball")
        self.core_cube1 = make_cube_to(self.core_np, 1.0, 1.0, 1.0, LColor(1.0, 0.90, 0.25, 0.95), 0, 0, 0, rot_h=0)
        self.core_cube2 = make_cube_to(self.core_np, 0.85, 0.85, 0.85, LColor(1.0, 0.55, 0.10, 0.85), 0, 0, 0, rot_h=45)
        self.core_cube1.setLightOff()
        self.core_cube2.setLightOff()
        self.core_np.setTransparency(TransparencyAttrib.MAlpha)
        self.core_np.setScale(0.6)

        # 3. 바닥 충격파 링 (Shockwave Disc)
        self.ring_np = self.root.attachNewNode("shockwave_ring")
        self.ring_geom = make_cube_to(self.ring_np, 1.0, 1.0, 0.04, LColor(1.0, 0.80, 0.30, 0.80), 0, 0, 0.08)
        self.ring_geom.setLightOff()
        self.ring_np.setTransparency(TransparencyAttrib.MAlpha)
        self.ring_np.setScale(0.8)

        # 4. 방사형 고속 비산 파편 & 불꽃 (Shrapnel & Sparks, 28개)
        self.particles = []
        for _ in range(28):
            p_node = self.root.attachNewNode("shrapnel")
            sz = random.uniform(0.06, 0.16)
            is_spark = random.random() < 0.65
            col = LColor(1.0, 0.85, 0.25, 1.0) if is_spark else LColor(0.28, 0.25, 0.22, 1.0)
            geom = make_cube_to(p_node, sz, sz, sz, col, 0, 0, 0)
            geom.setLightOff()
            p_node.setTransparency(TransparencyAttrib.MAlpha)

            angle = random.uniform(0, math.pi * 2)
            spd = random.uniform(5.5, 16.0)
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd
            vz = random.uniform(2.5, 11.0)
            self.particles.append({
                "node": p_node,
                "pos": Vec3(0, 0, 0.3),
                "vel": Vec3(vx, vy, vz),
                "is_spark": is_spark
            })

        # 5. 피어오르는 검붉은 연막 구름 (Smoke Puffs, 10개)
        self.smoke_clouds = []
        for _ in range(10):
            s_node = self.root.attachNewNode("smoke_puff")
            s_sz = random.uniform(0.35, 0.65)
            s_col = LColor(0.18, 0.16, 0.15, 0.70)
            s_geom = make_cube_to(s_node, s_sz, s_sz, s_sz, s_col, 0, 0, 0, rot_h=random.uniform(0, 360))
            s_geom.setLightOff()
            s_node.setTransparency(TransparencyAttrib.MAlpha)
            sx = random.uniform(-0.6, 0.6)
            sy = random.uniform(-0.6, 0.6)
            sz_pos = random.uniform(0.2, 0.8)
            s_node.setPos(sx, sy, sz_pos)
            self.smoke_clouds.append({
                "node": s_node,
                "pos": Vec3(sx, sy, sz_pos),
                "vel": Vec3(random.uniform(-1.2, 1.2), random.uniform(-1.2, 1.2), random.uniform(1.6, 3.8)),
                "scale": 1.0
            })

    def update(self, dt):
        if self.is_destroyed:
            return False

        self.timer -= dt
        progress = 1.0 - max(0.0, self.timer / self.max_timer)

        # 조명 감쇠
        if hasattr(self, 'light') and hasattr(self, 'light_np') and not self.light_np.isEmpty():
            light_alpha = max(0.0, 1.0 - progress * 2.8)
            self.light.setColor((4.8 * light_alpha, 2.6 * light_alpha, 0.6 * light_alpha, 1.0))
            if light_alpha <= 0.0 and self.render:
                self.render.clearLight(self.light_np)

        # 화구 급격한 팽창 후 소멸
        if hasattr(self, 'core_np') and not self.core_np.isEmpty():
            if progress < 0.22:
                c_scale = 0.6 + (progress / 0.22) * 2.8
                self.core_np.setScale(c_scale)
            else:
                fade = max(0.0, 1.0 - (progress - 0.22) / 0.78)
                self.core_np.setScale(3.4 * (1.0 + (1.0 - fade) * 0.4))
                self.core_cube1.setColor(1.0, 0.45 * fade, 0.1 * fade, 0.95 * fade)
                self.core_cube2.setColor(0.8 * fade, 0.2 * fade, 0.05 * fade, 0.85 * fade)

        # 충격파 링 팽창
        if hasattr(self, 'ring_np') and not self.ring_np.isEmpty():
            ring_scale = 0.8 + progress * 6.5
            ring_alpha = max(0.0, 0.80 * (1.0 - progress * 1.5))
            self.ring_np.setScale(ring_scale, ring_scale, 1.0)
            self.ring_geom.setColor(1.0, 0.80, 0.30, ring_alpha)

        # 파편 물리
        for p in self.particles:
            p["vel"].z -= 14.5 * dt
            p["pos"] += p["vel"] * dt
            if p["pos"].z <= 0.04:
                p["pos"].z = 0.04
                p["vel"].z = -p["vel"].z * 0.32
                p["vel"].x *= 0.65
                p["vel"].y *= 0.65
            p["node"].setPos(p["pos"])
            fade = max(0.0, self.timer / self.max_timer)
            p["node"].setScale(max(0.1, fade))

        # 연막 구름 상승 & 확장
        for s in self.smoke_clouds:
            s["pos"] += s["vel"] * dt
            s["node"].setPos(s["pos"])
            s["scale"] += dt * 2.2
            s["node"].setScale(s["scale"])
            fade = max(0.0, self.timer / self.max_timer)
            s["node"].setColorScale(1.0, 1.0, 1.0, fade * 0.8)

        if self.timer <= 0.0:
            self.destroy()
            return False
        return True

    def destroy(self):
        if self.is_destroyed:
            return
        self.is_destroyed = True
        if hasattr(self, 'light_np') and not self.light_np.isEmpty():
            self.render.clearLight(self.light_np)
            self.light_np.removeNode()
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()


class FragGrenade:
    """[G] 키로 투척하는 3D 물리 바운싱 전술 파열 수류탄"""
    def __init__(self, render, start_pos, throw_dir, audio_mgr):
        self.render = render
        self.audio_mgr = audio_mgr
        self.pos = Vec3(start_pos)
        self.vel = Vec3(throw_dir.x, throw_dir.y, throw_dir.z + 0.18) * 17.5
        self.timer = 1.45  # 1.45초 지연 신관
        self.is_exploded = False

        self.node = render.attachNewNode("frag_grenade")
        self.node.setPos(self.pos)

        body = make_cube("gr_body", 0.16, 0.16, 0.22, LColor(0.24, 0.35, 0.18, 1.0))
        body.reparentTo(self.node)
        cap = make_cube("gr_cap", 0.09, 0.09, 0.08, LColor(0.70, 0.60, 0.22, 1.0))
        cap.setPos(0, 0, 0.13)
        cap.reparentTo(self.node)
        pin = make_cube("gr_pin", 0.04, 0.04, 0.05, LColor(0.9, 0.9, 0.9, 1.0))
        pin.setPos(0.06, 0, 0.15)
        pin.reparentTo(self.node)

        self.rot_speed = Vec3(random.uniform(-400, 400), random.uniform(-400, 400), random.uniform(-400, 400))

    def update(self, dt, chunks, monsters):
        if self.is_exploded:
            return False

        self.vel.z -= 13.5 * dt
        next_pos = self.pos + self.vel * dt

        if next_pos.z <= 0.12:
            next_pos.z = 0.12
            self.vel.z = -self.vel.z * 0.40
            self.vel.x *= 0.70
            self.vel.y *= 0.70

        cols = get_nearby_colliders(chunks, self.pos.x, self.pos.y, search_dist=2.0)
        for min_x, min_y, max_x, max_y in cols:
            if min_x - 0.12 <= next_pos.x <= max_x + 0.12 and min_y - 0.12 <= next_pos.y <= max_y + 0.12:
                self.vel.x = -self.vel.x * 0.45
                self.vel.y = -self.vel.y * 0.45
                break

        self.pos = next_pos
        self.node.setPos(self.pos)
        self.node.setHpr(
            self.node.getH() + self.rot_speed.x * dt,
            self.node.getP() + self.rot_speed.y * dt,
            self.node.getR() + self.rot_speed.z * dt
        )

        for m in monsters:
            if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                dx = m.pos.x - self.pos.x
                dy = m.pos.y - self.pos.y
                if (dx * dx + dy * dy) < 1.3225:  # 1.15m 반경 직접 접촉 신관
                    return False

        self.timer -= dt
        return self.timer > 0.0

    def explode(self, monsters, player, ui_mgr, hazard_barrels=None, explosion_list=None):
        if self.is_exploded:
            return
        self.is_exploded = True

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_grenade_blast'):
            self.audio_mgr.play_grenade_blast()

        # 3D 고광도 화구, 충격파 링, 파편 및 연막 이펙트 발동
        if explosion_list is not None:
            explosion_list.append(ExplosionVisualEffect(self.render, self.pos, self.render))

        if player and hasattr(player, 'trigger_quake_shake'):
            player.trigger_quake_shake(intensity=4.2, duration=0.65)

        blast_radius = 6.5
        blast_r_sq = blast_radius * blast_radius
        blast_dmg = 260.0
        kill_count = 0

        for m in monsters:
            if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                dx = m.pos.x - self.pos.x
                dy = m.pos.y - self.pos.y
                d_sq = dx * dx + dy * dy
                if d_sq <= blast_r_sq:
                    d = math.sqrt(d_sq)
                    falloff = max(0.35, 1.0 - (d / blast_radius))
                    dmg = blast_dmg * falloff
                    hit_dir = Vec3(dx, dy, 0)
                    if d > 0.01:
                        hit_dir /= d
                    is_dead = m.take_damage(dmg, apply_knockback=True, hit_dir=hit_dir)
                    if player and hasattr(player, 'recover_stamina'):
                        player.recover_stamina(18.0)
                    if is_dead:
                        kill_count += 1
                        if hasattr(m, 'turn_into_corpse'):
                            m.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player and hasattr(player, 'gain_exp'):
                            player.gain_exp(getattr(m, 'exp_value', 35) + 30)

        if hazard_barrels:
            for b in hazard_barrels:
                if not b.is_destroyed:
                    db = math.hypot(b.pos.x - self.pos.x, b.pos.y - self.pos.y)
                    if db <= blast_radius:
                        b.ignite()

        # 집속 수류탄 퍽: 4개의 자탄이 사방으로 비산하여 2차 연쇄 폭발
        if player and hasattr(player, 'has_perk') and player.has_perk("cluster_grenade"):
            angles = [0.0, math.pi * 0.5, math.pi, math.pi * 1.5]
            for ang in angles:
                sub_pos = Vec3(self.pos.x + math.cos(ang) * 2.2, self.pos.y + math.sin(ang) * 2.2, self.pos.z)
                if explosion_list is not None:
                    explosion_list.append(ExplosionVisualEffect(self.render, sub_pos, self.render))
                for m in monsters:
                    if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                        if (m.pos - sub_pos).length() <= 3.5:
                            s_dead = m.take_damage(90.0, apply_knockback=True, hit_dir=(m.pos - sub_pos).normalized())
                            if s_dead:
                                kill_count += 1
                                if hasattr(m, 'turn_into_corpse'):
                                    m.turn_into_corpse(audio_mgr=self.audio_mgr)
                                if player and hasattr(player, 'gain_exp'):
                                    player.gain_exp(getattr(m, 'exp_value', 35))
            if ui_mgr:
                ui_mgr.show_hit_marker("💣 [집속 수류탄!] 4방향 2차 연쇄 폭발!", (1.0, 0.6, 0.2, 1.0))

        if kill_count >= 2 and ui_mgr:
            ui_mgr.show_style_kill(f"[ GRENADE MULTI-KILL! ×{kill_count} ]", f"+{kill_count * 80} EXP", (1.0, 0.75, 0.2, 1.0))
        elif kill_count == 1 and ui_mgr:
            ui_mgr.show_style_kill("[ GRENADE KILL! ]", "+50 EXP", (1.0, 0.75, 0.2, 1.0))

        self.destroy()

    def destroy(self):
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()
