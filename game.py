import os
import sys
import math
import random
import concurrent.futures
# PyInstaller 번들 리소스 경로 및 작업 디렉토리 설정
if getattr(sys, 'frozen', False):
    basedir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    os.chdir(basedir)
else:
    basedir = os.path.dirname(os.path.abspath(__file__))

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Vec3, SamplerState, Fog, AmbientLight, PointLight, LColor, WindowProperties, TransparencyAttrib,
    loadPrcFileData, getModelPath, Filename
)
import simplepbr

# Panda3D 리소스 탐색 경로에 번들 디렉토리 등록
getModelPath().prependDirectory(Filename.fromOsSpecific(basedir))
getModelPath().prependDirectory(Filename.fromOsSpecific(os.path.join(basedir, "assets")))

from constants import (
    CELL_SIZE, CHUNK_SIZE, CHUNK_CELLS, WALL_HEIGHT,
    PLAYER_EYE_HEIGHT, RENDER_RADIUS, FOG_COLOR, BLACKOUT_FOG_COLOR,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import find_cell_path, check_line_of_sight, cell_has_pillar
from chunk import Chunk
from monster import (
    LongBlackSerpent, TallSkeletonMonster,
    AbominableMudOrc, AlluringAshWitch
)
from geometry import make_cube_to, make_cube

# 분리된 모듈 임포트
from collision import (
    get_nearby_colliders, resolve_collision,
    register_custom_collider, clear_custom_colliders
)
from audio_system import AudioManager
from ui_manager import UIManager
from combat_system import CombatSystem
from player_controller import PlayerController


class Fireball:
    """매혹의 잿더미 마녀가 발사하는 타오르는 불꽃 발사체"""
    def __init__(self, render, start_pos, target_pos):
        self.render = render
        self.pos = Vec3(start_pos)
        self.node = render.attachNewNode("witch_fireball")
        self.node.setPos(self.pos)

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
        render.setLight(self.light_np)

        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]
        dz = target_pos[2] - start_pos[2]
        d = math.hypot(dx, dy, dz)
        if d > 0.01:
            self.vel = Vec3(dx / d, dy / d, dz / d) * 14.5
        else:
            self.vel = Vec3(0, 1, 0) * 14.5

        self.lifetime = 3.5
        self.damage = 22.0

    def update(self, dt):
        self.lifetime -= dt
        self.pos += self.vel * dt
        self.node.setPos(self.pos)
        self.node.setH(self.node.getH() + dt * 400.0)
        self.node.setP(self.node.getP() + dt * 280.0)
        return self.lifetime > 0.0

    def destroy(self):
        if hasattr(self, 'light_np') and not self.light_np.isEmpty():
            self.render.clearLight(self.light_np)
            self.light_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


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

        cx = int(math.floor(self.pos.x / CHUNK_SIZE))
        cy = int(math.floor(self.pos.y / CHUNK_SIZE))
        cols = get_nearby_colliders(chunks, cx, cy)
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
                if math.hypot(m.pos.x - self.pos.x, m.pos.y - self.pos.y) < 1.15:
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
        blast_dmg = 260.0
        kill_count = 0

        for m in monsters:
            if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                d = math.hypot(m.pos.x - self.pos.x, m.pos.y - self.pos.y)
                if d <= blast_radius:
                    falloff = max(0.35, 1.0 - (d / blast_radius))
                    dmg = blast_dmg * falloff
                    hit_dir = Vec3(m.pos.x - self.pos.x, m.pos.y - self.pos.y, 0)
                    if hit_dir.length() > 0.01:
                        hit_dir.normalize()
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

        if kill_count >= 2 and ui_mgr:
            ui_mgr.show_style_kill(f"💥 [ GRENADE MULTI-KILL! ×{kill_count} ] 💥", f"+{kill_count * 80} EXP", (1.0, 0.75, 0.2, 1.0))
        elif kill_count == 1 and ui_mgr:
            ui_mgr.show_style_kill("💥 [ GRENADE KILL! ] 💥", "+50 EXP", (1.0, 0.75, 0.2, 1.0))

        self.destroy()

    def destroy(self):
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class HazardBarrel:
    """던전 복도에 배치되는 붉은색 고위험 폭발성 유류 드럼통"""
    def __init__(self, render, x, y, audio_mgr):
        self.render = render
        self.pos = Vec3(x, y, 0.0)
        self.audio_mgr = audio_mgr
        self.is_ignited = False
        self.fuse_timer = 0.42
        self.is_destroyed = False

        self.node = render.attachNewNode("hazard_barrel")
        self.node.setPos(self.pos)

        make_cube_to(self.node, 0.65, 0.65, 1.15, LColor(0.85, 0.12, 0.08, 1.0), 0, 0, 0.58)
        make_cube_to(self.node, 0.70, 0.70, 0.12, LColor(0.15, 0.15, 0.15, 1.0), 0, 0, 0.95)
        make_cube_to(self.node, 0.70, 0.70, 0.12, LColor(0.15, 0.15, 0.15, 1.0), 0, 0, 0.20)
        make_cube_to(self.node, 0.67, 0.67, 0.22, LColor(0.95, 0.85, 0.10, 1.0), 0, 0, 0.58)

        self.fire_node = None

    def is_hit_by_ray(self, ray_origin, ray_dir):
        """총탄 레이캐스트 AABB 충돌 검사 (반경 0.38m, 높이 1.25m)"""
        if self.is_destroyed:
            return False, 999.0

        min_x, max_x = self.pos.x - 0.38, self.pos.x + 0.38
        min_y, max_y = self.pos.y - 0.38, self.pos.y + 0.38
        min_z, max_z = 0.0, 1.25

        dx, dy, dz = ray_dir.x, ray_dir.y, ray_dir.z
        px, py, pz = ray_origin.x, ray_origin.y, ray_origin.z

        t_min = 0.0
        t_max = 55.0

        for p_comp, d_comp, lo, hi in [(px, dx, min_x, max_x), (py, dy, min_y, max_y), (pz, dz, min_z, max_z)]:
            if abs(d_comp) < 1e-6:
                if p_comp < lo or p_comp > hi:
                    return False, 999.0
            else:
                t1 = (lo - p_comp) / d_comp
                t2 = (hi - p_comp) / d_comp
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    return False, 999.0

        if t_min > 0.2:
            return True, t_min
        return False, 999.0

    def ignite(self):
        """총격 관통 시 점화되어 화염 분출 및 폭발 대기"""
        if self.is_ignited or self.is_destroyed:
            return
        self.is_ignited = True
        if self.audio_mgr and hasattr(self.audio_mgr, 'play_barrel_ignite'):
            self.audio_mgr.play_barrel_ignite()

        self.fire_node = make_cube("barrel_fire", 0.30, 0.30, 0.40, LColor(1.0, 0.70, 0.15, 1.0))
        self.fire_node.setPos(0, 0, 1.25)
        self.fire_node.setLightOff()
        self.fire_node.reparentTo(self.node)

    def update(self, dt, monsters, player, ui_mgr, hazard_barrels=None, explosion_list=None):
        if not self.is_ignited or self.is_destroyed:
            return True

        self.fuse_timer -= dt
        if self.fire_node and not self.fire_node.isEmpty():
            sc = 1.0 + random.uniform(-0.25, 0.35)
            self.fire_node.setScale(sc, sc, sc * 1.3)

        if self.fuse_timer <= 0.0:
            self.explode(monsters, player, ui_mgr, hazard_barrels, explosion_list=explosion_list)
            return False
        return True

    def explode(self, monsters, player, ui_mgr, hazard_barrels=None, explosion_list=None):
        if self.is_destroyed:
            return
        self.is_destroyed = True

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_grenade_blast'):
            self.audio_mgr.play_grenade_blast()

        if explosion_list is not None:
            explosion_list.append(ExplosionVisualEffect(self.render, self.pos + Vec3(0, 0, 0.45), self.render))

        if player and hasattr(player, 'trigger_quake_shake'):
            player.trigger_quake_shake(intensity=4.6, duration=0.75)

        blast_radius = 8.0
        blast_dmg = 350.0
        kill_count = 0

        for m in monsters:
            if getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                d = math.hypot(m.pos.x - self.pos.x, m.pos.y - self.pos.y)
                if d <= blast_radius:
                    falloff = max(0.40, 1.0 - (d / blast_radius))
                    dmg = blast_dmg * falloff
                    hit_dir = Vec3(m.pos.x - self.pos.x, m.pos.y - self.pos.y, 0)
                    if hit_dir.length() > 0.01:
                        hit_dir.normalize()
                    is_dead = m.take_damage(dmg, apply_knockback=True, hit_dir=hit_dir)
                    if is_dead:
                        kill_count += 1
                        if hasattr(m, 'turn_into_corpse'):
                            m.turn_into_corpse(audio_mgr=self.audio_mgr)
                        if player and hasattr(player, 'gain_exp'):
                            player.gain_exp(getattr(m, 'exp_value', 35) + 50)

        if player:
            dp = math.hypot(player.camera.getX() - self.pos.x, player.camera.getY() - self.pos.y)
            if dp < 3.2:
                player.take_damage(16.0, source_pos=(self.pos.x, self.pos.y))

        if hazard_barrels:
            for b in hazard_barrels:
                if b is not self and not b.is_destroyed:
                    db = math.hypot(b.pos.x - self.pos.x, b.pos.y - self.pos.y)
                    if db <= 6.5:
                        b.ignite()

        if ui_mgr:
            if kill_count > 0:
                ui_mgr.show_style_kill("[ ! BARREL CHAIN BLAST ! ]", f"×{kill_count} 처치! +{kill_count * 100} EXP", (1.0, 0.35, 0.1, 1.0))
            else:
                ui_mgr.show_style_kill("[ ! HAZARD BARREL DETONATED ! ]", "", (1.0, 0.4, 0.1, 1.0))

        self.destroy()

    def destroy(self):
        self.is_destroyed = True
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class TacticalSupplyCrate:
    """던전 필드 곳곳에 배치되어 [E] 키로 개봉할 수 있는 전술 군용 보급 상자"""
    def __init__(self, parent, x, y, audio_mgr=None):
        self.parent = parent
        self.pos = Vec3(x, y, 0.0)
        self.audio_mgr = audio_mgr
        self.is_opened = False
        self.lid_angle = 0.0

        self.node = parent.attachNewNode("tactical_crate")
        self.node.setPos(self.pos)

        # 상자 몸통 (카키/다크 올리브 메탈)
        c_body = LColor(0.18, 0.25, 0.16, 1.0)
        c_steel = LColor(0.28, 0.30, 0.32, 1.0)
        c_latch = LColor(0.85, 0.70, 0.20, 1.0)

        # 하부 박스 베이스 (너비 0.9m, 깊이 0.6m, 높이 0.42m)
        self.body_geom = make_cube("crate_body", 0.90, 0.60, 0.42, c_body)
        self.body_geom.setPos(0, 0, 0.21)
        self.body_geom.reparentTo(self.node)

        # 강화 코너 브라켓
        corner = make_cube("crate_frame", 0.94, 0.64, 0.10, c_steel)
        corner.setPos(0, 0, 0.08)
        corner.reparentTo(self.node)

        # 래치 버클
        latch = make_cube("crate_latch", 0.14, 0.06, 0.16, c_latch)
        latch.setPos(0, -0.32, 0.26)
        latch.reparentTo(self.node)

        # 개폐식 상단 뚜껑 (Lid)
        self.lid_root = self.node.attachNewNode("crate_lid_hinge")
        self.lid_root.setPos(0, 0.28, 0.42)  # 후면 힌지 축
        self.lid_geom = make_cube("crate_lid", 0.92, 0.62, 0.08, c_body)
        self.lid_geom.setPos(0, -0.28, 0.04)
        self.lid_geom.reparentTo(self.lid_root)

        # 전술 LED 상태 표시등 (미개봉: 청록빛 네온 라이트)
        self.led_node = make_cube("crate_led", 0.12, 0.08, 0.04, LColor(0.20, 0.95, 0.45, 1.0))
        self.led_node.setPos(0, -0.28, 0.09)
        self.led_node.setLightOff()
        self.led_node.reparentTo(self.lid_root)

        # 주변을 은은하게 비추는 엠비언트 비콘 라이트
        self.beacon_light = PointLight("crate_beacon")
        self.beacon_light.setColor((0.15, 0.85, 0.40, 1.0))
        self.beacon_light.setAttenuation((1.0, 0.22, 0.08))
        self.beacon_np = self.node.attachNewNode(self.beacon_light)
        self.beacon_np.setPos(0, 0, 0.6)
        parent.setLight(self.beacon_np)

    def can_interact(self, px, py):
        """플레이어 접근 시 상호작용 가능 여부 판정 (반경 2.6m)"""
        if self.is_opened:
            return False
        return math.hypot(px - self.pos.x, py - self.pos.y) <= 2.6

    def open(self, player, combat, ui_mgr):
        """[E] 키 상호작용으로 상자 개봉 및 보급품 지급"""
        if self.is_opened:
            return
        self.is_opened = True

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_crate_open'):
            self.audio_mgr.play_crate_open()

        # 뚜껑 개방 각도 회전
        self.lid_root.setP(-75.0)

        # LED 소등 및 라이트 제거
        self.led_node.setColorScale(0.3, 0.3, 0.3, 1.0)
        if hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            self.parent.clearLight(self.beacon_np)
            self.beacon_np.removeNode()

        # 보급품 랜덤 배분 (탄약, 수류탄, 회복제, 경험치 코어)
        rewards = []
        # 1. 예비 탄약 보급 (+24발)
        ammo_gain = random.randint(18, 28)
        combat.reserve_ammo += ammo_gain
        combat.update_ammo_ui()
        rewards.append(f"권총 탄약 +{ammo_gain}발")

        # 2. 80% 확률로 전술 소모품 1개 지급
        if random.random() < 0.80 and hasattr(player, 'add_item'):
            possible_items = ["medkit", "adrenaline", "frag_grenade", "combat_stim"]
            chosen = random.choice(possible_items)
            ok, item_name = player.add_item(chosen, 1)
            if ok:
                rewards.append(f"[{item_name}] 1개")

        # 3. 추가 경험치 코어
        exp_bonus = random.randint(70, 120)
        if hasattr(player, 'gain_exp'):
            player.gain_exp(exp_bonus)
            rewards.append(f"+{exp_bonus} EXP")

        reward_str = " | ".join(rewards)
        if ui_mgr:
            ui_mgr.show_hit_marker(f"[전술 보급품 획득!] {reward_str}", (0.35, 1.0, 0.65, 1.0))
            ui_mgr.show_style_kill("[ TACTICAL CRATE OPENED ]", reward_str, (0.3, 0.95, 0.55, 1.0))

    def destroy(self):
        if hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            self.parent.clearLight(self.beacon_np)
            self.beacon_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class LiminalInfiniteLoop(ShowBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # PBR 렌더링 최적화
        if hasattr(self, 'win') and self.win is not None:
            self.pbr_pipeline = simplepbr.init(
                max_lights=8,
                use_normal_maps=False,
                use_emission_maps=False,
                use_occlusion_maps=False,
                enable_shadows=False,
                enable_fog=True
            )

        # 1. 카메라 가시거리 및 안개 설정 (FOV 88도)
        if hasattr(self, 'camLens') and self.camLens is not None:
            self.camLens.setNearFar(0.15, 85.0)
            self.camLens.setFov(88.0)
        self.rendered_chunk_count = 0
        self.total_chunk_count = 0
        self.setup_fog()

        # 2. 백룸 기본 조명 연출
        self.setup_lighting()

        # 3. 텍스처 로드
        self.load_assets()

        # 4. 무한 청크 관리자 설정
        self.chunks = {}
        self.chunk_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ChunkWorker")
        self.active_chunk_futures = {}
        self.last_cull_pos = None
        self.world_root = self.render.attachNewNode("world_root")

        # 5. 던전 크롤러 몬스터 군단 관리자 및 발사체
        self.monsters = []
        self.corpses = []
        self.killer_monster = None
        self.fireballs = []
        self.shockwaves = []
        self.grenades = []
        self.explosions = []
        self.grenade_cooldown = 0.0
        self.hazard_barrels = []
        self.supply_crates = []
        self.nearby_crate = None

        # 5-1. 정전 프로토콜 (Blackout & Crimson Protocol) 상태
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False

        # 6. 하위 서브시스템 초기화 (오디오, UI, 전투, 플레이어 제어)
        if not hasattr(self, 'camera') or self.camera is None:
            self.camera = self.render.attachNewNode("camera")
        self.audio_mgr = AudioManager(self, self.loader, self.camera, getattr(self, 'sfxManagerList', None))

        self.ui_mgr = UIManager(
            self, self.loader,
            on_start=self.start_game,
            on_return_menu=self.return_to_intro,
            on_exit=self.exit_game
        )

        self.combat = CombatSystem(
            self, self.render, self.camera, self.world_root,
            self.audio_mgr, self.ui_mgr
        )

        self.player = PlayerController(
            self, self.win, self.camera, self.mouseWatcherNode,
            self.audio_mgr, self.ui_mgr
        )
        self.player.world_root = self.world_root
        self.player.setup_input(
            on_shoot=self.shoot_pistol,
            on_reload=self.reload_pistol,
            on_aim_start=self.combat.start_aim,
            on_aim_stop=self.combat.stop_aim,
            on_grenade=self.throw_grenade,
            on_inventory=self.toggle_inventory,
            on_quick_use=self.use_quick_slot,
            on_escape=self.handle_escape,
            on_interact=self.handle_interaction
        )

        # 7. 게임 상태 및 5분(300초) 타이머 설정
        self.game_state = "INTRO"  # "INTRO", "PLAYING", "SHOP", "GAME_OVER", "VICTORY"
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 던전 크롤러 모드: 5분(300초)
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0

        # 초기 청크 및 인트로 씬 로드
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.escape_pos = (spawn_x + 75.0, spawn_y + 75.0)
        self.player.reset_position(spawn_x, spawn_y)
        self.update_chunks(force=True)

        self.show_intro_scene()
        self.taskMgr.add(self.update, "update_task")

        # 8. F11 전체화면 토글 설정 + 시작 시 창 모드 강제 적용
        self._is_fullscreen = False
        self._enforce_windowed_mode()
        self.accept("f11", self.toggle_fullscreen)

    # --- 전체화면 토글 ---
    def _enforce_windowed_mode(self):
        """시작 시 창 모드를 강제 적용하여 전체화면 자동 진입 버그 방지"""
        if not hasattr(self, 'win') or self.win is None:
            return
        try:
            props = WindowProperties()
            props.setFullscreen(False)
            props.setSize(1600, 900)
            props.setUndecorated(False)
            self.win.requestProperties(props)
        except Exception:
            pass

    def toggle_fullscreen(self):
        """F11 키로 전체화면 / 창 모드를 전환"""
        if not hasattr(self, 'win') or self.win is None:
            return
        self._is_fullscreen = not self._is_fullscreen
        try:
            props = WindowProperties()
            props.setFullscreen(self._is_fullscreen)
            if not self._is_fullscreen:
                props.setSize(1600, 900)
                props.setUndecorated(False)
            self.win.requestProperties(props)
        except Exception:
            pass

    # --- 에셋 및 렌더링 설정 ---
    def setup_fog(self):
        self.liminal_fog = Fog("LiminalDepthFog")
        self.liminal_fog.setColor(FOG_COLOR)
        # 지수 안개(Exponential Fog)로 매끄럽고 몽환적인 자연스러운 거리 감쇠 안개 형성
        self.liminal_fog.setExpDensity(0.038)
        self.render.setFog(self.liminal_fog)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)

    def setup_lighting(self):
        amb = AmbientLight('ambient_dim')
        amb.setColor((0.005, 0.005, 0.006, 1.0))
        self.amb_np = self.render.attachNewNode(amb)
        self.render.setLight(self.amb_np)

    def load_assets(self):
        try:
            self.wall_tex = self.loader.loadTexture("wall.jpg")
            self.floor_tex = self.loader.loadTexture("floor.jpg")
            self.sky_tex = self.loader.loadTexture("sky.jpg")
            for t in (self.wall_tex, self.floor_tex, self.sky_tex):
                if t:
                    t.setMagfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                    t.setAnisotropicDegree(4)
        except Exception as e:
            print(f"텍스처 로드 실패: {e}")

    # --- 사용자 액션 포워딩 ---
    def shoot_pistol(self):
        self.combat.shoot(self.monsters, self.player, self.game_state, hazard_barrels=self.hazard_barrels)

    def throw_grenade(self):
        """[G] 키 전술 파열 수류탄 투척 (1.45초 후 반경 6.5m 대폭발)"""
        if self.game_state != "PLAYING":
            return
        if self.grenade_cooldown > 0.0:
            return
        self.grenade_cooldown = 9.0
        if self.audio_mgr and hasattr(self.audio_mgr, 'play_grenade_throw'):
            self.audio_mgr.play_grenade_throw()
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        start_pos = self.camera.getPos() + cam_fwd * 0.45
        gr = FragGrenade(self.world_root, start_pos, cam_fwd, self.audio_mgr)
        self.grenades.append(gr)

    def reload_pistol(self):
        self.combat.reload(self.game_state)

    def toggle_inventory(self):
        """[Tab] 또는 [I] 키로 전술 인벤토리 배낭 창 토글"""
        if self.game_state == "PLAYING":
            self.open_inventory()
        elif self.game_state == "INVENTORY":
            self.close_inventory()

    def open_inventory(self):
        """전술 인벤토리 오픈 및 마우스 잠금 해제, 게임 루프 일시정지"""
        if self.game_state != "PLAYING":
            return
        self.game_state = "INVENTORY"
        self.player.lock_mouse(False)
        self.combat.stop_aim()
        self.audio_mgr.play_inventory_toggle(True)
        self.ui_mgr.show_inventory(
            player=self.player,
            combat=self.combat,
            on_use_item_callback=self._on_inventory_use_item,
            on_close_callback=self.close_inventory
        )

    def close_inventory(self):
        """전술 인벤토리 닫기 및 마우스 잠금 복원, 게임 루프 재개"""
        if self.game_state != "INVENTORY":
            return
        self.game_state = "PLAYING"
        self.ui_mgr.hide_inventory()
        self.player.lock_mouse(True)
        self.audio_mgr.play_inventory_toggle(False)
        self._update_quickslot_hud()

    def handle_escape(self):
        """[ESC] 키 입력 처리: 인벤토리 열려있으면 닫기, 아니면 마우스 락 토글"""
        if self.game_state == "INVENTORY":
            self.close_inventory()
        else:
            self.player.lock_mouse(not self.player.mouse_locked)

    def _on_inventory_use_item(self, item_id):
        """인벤토리 모달 내 [사용하기] 클릭 콜백"""
        success, msg = self.player.use_item(item_id, self.combat, self)
        if success:
            self.audio_mgr.play_item_use()
        self.ui_mgr.inv_msg_text.setText(msg)
        self.ui_mgr._refresh_inventory_ui()
        self._update_quickslot_hud()

    def use_quick_slot(self, slot_num):
        """[1~4] 키로 배낭을 열지 않고 전술 퀵슬롯 아이템 즉시 사용"""
        if self.game_state != "PLAYING":
            return
        success, msg = self.player.use_quick_slot(slot_num, self.combat, self)
        if success:
            self.audio_mgr.play_item_use()
            self.ui_mgr.show_hit_marker(msg)
        else:
            self.ui_mgr.show_hit_marker(f"[ 사용 불가 ] {msg}")
        self._update_quickslot_hud()

    def _update_quickslot_hud(self):
        """하단 퀵슬롯 HUD 텍스트 갱신"""
        self.ui_mgr.update_quickslots_hud(self.player.inventory)

    def exit_game(self):
        self.destroy()
        sys.exit(0)

    def clear_projectiles(self):
        """남아있는 파이어볼 및 충격파 엔티티 즉시 해제"""
        for fb in self.fireballs:
            fb.destroy()
        self.fireballs.clear()
        for sw in self.shockwaves:
            sw.destroy()
        self.shockwaves.clear()

    # --- 씬 및 게임 라이프사이클 관리 ---
    def show_intro_scene(self):
        """인트로 화면 전환"""
        self.clear_projectiles()
        for m in self.monsters:
            m.destroy()
        self.monsters = []
        for c in self.corpses:
            c.destroy()
        self.corpses = []
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()
        self.game_state = "INTRO"
        self.player.lock_mouse(False)
        self.combat.vm_root.hide()
        self.combat.set_blackout_mode(False)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.render.clearLight(self.combat.pl_np)
        self.render.clearLight(self.combat.fill_np)
        self.ui_mgr.show_intro()
        self.audio_mgr.set_bgm_mode("INTRO")

    def start_game(self):
        """START 버튼 클릭 시 1인칭 던전 크롤러 게임플레이 시작"""
        self.game_state = "PLAYING"
        self.restart_game()
        self.combat.vm_root.show()
        self.render.setLight(self.combat.pl_np)
        self.render.setLight(self.combat.fill_np)
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)
        self.audio_mgr.set_bgm_mode("PLAYING")

    def return_to_intro(self):
        self.show_intro_scene()

    def get_gate_corridor_candidates(self, min_dist=6.0, max_dist=32.0):
        """탈출 관문 주변의 복도 셀 후보 좌표 목록 반환"""
        if not hasattr(self, 'escape_pos') or not self.escape_pos:
            return []
        ex, ey = self.escape_pos
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        cands = []
        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if gx % 3 == 1 or gy % 3 == 1:
                    if cell_has_pillar(gx, gy):
                        continue
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    d = math.hypot(cx - ex, cy - ey)
                    if min_dist <= d <= max_dist:
                        cands.append((cx, cy))
        return cands

    def spawn_reinforcement_monster(self, pos=None, near_gate=True):
        """관문 인근 또는 특정 위치에 증원 몬스터 단일 스폰"""
        if len(self.monsters) >= 22:
            return None

        if pos is None:
            if near_gate:
                cands = self.get_gate_corridor_candidates(min_dist=10.0, max_dist=30.0)
                if cands:
                    pos = random.choice(cands)
                else:
                    ex, ey = getattr(self, 'escape_pos', (0, 0))
                    pos = (ex + random.choice([-16, 16]), ey + random.choice([-16, 16]))
            else:
                px, py = self.camera.getX(), self.camera.getY()
                pos = (px + random.choice([-22, 22]), py + random.choice([-22, 22]))

        types = [AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, LongBlackSerpent]
        weights = [0.35, 0.35, 0.20, 0.10]
        cls = random.choices(types, weights=weights, k=1)[0]

        monster = cls(self.render, pos[0], pos[1])
        stage_hp_mult = 1.0 + (self.current_stage - 1) * 0.25
        monster.max_hp = int(monster.max_hp * stage_hp_mult)
        monster.hp = monster.max_hp
        self.monsters.append(monster)
        return monster

    def spawn_monsters(self, stage=1):
        """스테이지별 다중 몬스터 군단 스폰 (관문 수호 호드 집중 배치 + 맵 순찰대)"""
        for m in self.monsters:
            m.destroy()
        self.monsters = []
        for c in self.corpses:
            c.destroy()
        self.corpses = []

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        ex, ey = getattr(self, 'escape_pos', (spawn_x + 75.0, spawn_y + 75.0))

        # 1. 맵 전체 복도 후보 및 관문 인근 복도 후보 분리
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        map_candidates = []
        gate_candidates = []

        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if gx % 3 == 1 or gy % 3 == 1:
                    if cell_has_pillar(gx, gy):
                        continue
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    dist_to_spawn = math.hypot(cx - spawn_x, cy - spawn_y)
                    dist_to_gate = math.hypot(cx - ex, cy - ey)

                    if dist_to_spawn >= 22.0:
                        map_candidates.append((cx, cy))
                    if 6.0 <= dist_to_gate <= 28.0:
                        gate_candidates.append((cx, cy))

        random.shuffle(map_candidates)
        random.shuffle(gate_candidates)

        stage_hp_mult = 1.0 + (stage - 1) * 0.25

        # 2. [관문 수호 몬스터 군단 (Gate Guardians)] - 탈출 관문 근처에 집중 배치
        # 기본 6마리 + 스테이지당 2마리씩 증원
        gate_monsters_count = 6 + (stage - 1) * 2
        gate_plan = [
            AbominableMudOrc, AbominableMudOrc,
            AlluringAshWitch, AlluringAshWitch,
            TallSkeletonMonster, LongBlackSerpent
        ]
        while len(gate_plan) < gate_monsters_count:
            gate_plan.append(random.choice([AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster]))

        for i, cls in enumerate(gate_plan):
            pos = gate_candidates[i % len(gate_candidates)] if gate_candidates else (ex + (i + 1) * 4, ey + 4)
            monster = cls(self.render, pos[0], pos[1])
            if stage > 1:
                monster.max_hp = int(monster.max_hp * stage_hp_mult)
                monster.hp = monster.max_hp
            self.monsters.append(monster)

        # 3. [맵 전역 순찰 몬스터] - 맵 전역의 긴장감 유지 (4마리)
        patrol_plan = [AbominableMudOrc, AlluringAshWitch, TallSkeletonMonster, LongBlackSerpent]
        for i, cls in enumerate(patrol_plan):
            pos = map_candidates[i % len(map_candidates)] if map_candidates else (spawn_x + 30.0 + i * 10, spawn_y + 30.0)
            monster = cls(self.render, pos[0], pos[1])
            if stage > 1:
                monster.max_hp = int(monster.max_hp * stage_hp_mult)
                monster.hp = monster.max_hp
            self.monsters.append(monster)

        # 오디오 관리자에 첫 번째 뱀/해골 부착
        first_serpent = next((m for m in self.monsters if isinstance(m, LongBlackSerpent)), None)
        first_skel = next((m for m in self.monsters if isinstance(m, TallSkeletonMonster)), None)
        if first_serpent and first_skel:
            self.audio_mgr.attach_monsters(first_serpent, first_skel)

        # 복도 폭발성 유류 드럼통 배치
        self.spawn_hazard_barrels()

    def spawn_hazard_barrels(self):
        """던전 복도 코너/교차로에 붉은색 고위험 유류 드럼통 6~8개 배치"""
        for b in self.hazard_barrels:
            b.destroy()
        self.hazard_barrels.clear()

        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 2
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 3
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        candidates = []
        for gx in range(min_cell, max_cell, 2):
            for gy in range(min_cell, max_cell, 2):
                if (gx % 3 == 1 or gy % 3 == 1) and not cell_has_pillar(gx, gy):
                    bx = (gx + 0.35) * CELL_SIZE
                    by = (gy + 0.35) * CELL_SIZE
                    if math.hypot(bx - spawn_x, by - spawn_y) >= 16.0:
                        candidates.append((bx, by))

        selected = random.sample(candidates, min(len(candidates), 7)) if candidates else []
        for bx, by in selected:
            barrel = HazardBarrel(self.world_root, bx, by, self.audio_mgr)
            self.hazard_barrels.append(barrel)

    def spawn_supply_crates(self):
        """던전 필드 곳곳에 전술 보급 상자 6~8개 배치"""
        for cr in self.supply_crates:
            cr.destroy()
        self.supply_crates.clear()

        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 2
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 3
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        candidates = []
        for gx in range(min_cell, max_cell, 2):
            for gy in range(min_cell, max_cell, 2):
                if not cell_has_pillar(gx, gy):
                    cx = (gx + 0.45) * CELL_SIZE
                    cy = (gy + 0.45) * CELL_SIZE
                    dist_sp = math.hypot(cx - spawn_x, cy - spawn_y)
                    if 14.0 <= dist_sp <= 110.0:
                        candidates.append((cx, cy))

        selected = random.sample(candidates, min(len(candidates), 8)) if candidates else []
        for cx, cy in selected:
            crate = TacticalSupplyCrate(self.world_root, cx, cy, self.audio_mgr)
            self.supply_crates.append(crate)

    def handle_interaction(self):
        """[E] 키 상호작용: 접근한 전술 보급 상자 개봉"""
        if self.game_state != "PLAYING" or self.game_over or self.game_won:
            return
        if self.nearby_crate and not self.nearby_crate.is_opened:
            self.nearby_crate.open(self.player, self.combat, self.ui_mgr)
            self.ui_mgr.hide_interact_prompt()
            self.nearby_crate = None

    def clear_projectiles(self):
        """스테이지 전환/리셋 시 발사체, 충격파, 수류탄, 유류 드럼통, 보급 상자 일괄 정리"""
        for fb in self.fireballs:
            fb.destroy()
        self.fireballs.clear()
        for sw in self.shockwaves:
            sw.destroy()
        self.shockwaves.clear()
        for gr in self.grenades:
            gr.destroy()
        self.grenades.clear()
        for b in self.hazard_barrels:
            b.destroy()
        self.hazard_barrels.clear()
        for cr in self.supply_crates:
            cr.destroy()
        self.supply_crates.clear()
        for exp in self.explosions:
            exp.destroy()
        self.explosions.clear()

    def restart_game(self):
        """던전 게임 초기화 (체력, 몬스터 군단, 5분 타이머, 탈출구)"""
        self.clear_projectiles()
        self.game_over = False
        self.game_won = False
        self.current_stage = 1
        self.time_limit = 300.0  # 5분 제한시간
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0
        self.stage_banner_timer = 0.0

        # 플레이어 위치 및 스탯 초기화
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.player.reset_position(spawn_x, spawn_y)
        self.player.level = 1
        self.player.exp = 0
        self.player.exp_to_next = 100
        self.player.max_hp = 100.0
        self.player.hp = self.player.max_hp
        self.player.attack_power = 35.0
        self.player.speed_mult = 1.0
        self.player.relics = []
        self.ui_mgr.update_relic_badges(self.player.relics)

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        # 전투 서브시스템 리셋
        self.combat.stop_aim()
        self.combat.reset_state(self.current_stage, keep_ammo=False)
        self.player.reset_inventory()
        self._update_quickslot_hud()

        # 비동기 작업 정리
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        self.killer_monster = None

        # 탈출구 생성 (관문 위치 확정 및 단단한 관문 충돌체 등록)
        self.setup_escape_portal()

        # 관문 접근 경보 및 증원 상태 리셋
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0

        # 다중 몬스터 군단 스폰 (관문 주변 수호 몬스터 집중 배치)
        self.spawn_monsters(self.current_stage)
        self.spawn_hazard_barrels()
        self.spawn_supply_crates()

        # 안개 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)

        self.ui_mgr.update_hp_exp(self.player.hp, self.player.max_hp, self.player.exp, self.player.exp_to_next, self.player.level)

    def advance_to_next_stage(self):
        """스탯 분배 후 다음 스테이지로 진입"""
        self.clear_projectiles()
        prev_stage = self.current_stage
        self.current_stage += 1
        self.time_left = self.time_limit
        self.door_hold_timer = 5.0

        # 정전 프로토콜 리셋
        self.blackout_active = False
        self.blackout_timer = 0.0
        self.blackout_triggered_this_stage = False
        self.ui_mgr.hide_blackout_warning()

        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE
        self.player.reset_position(spawn_x, spawn_y)

        # 비동기 작업 정리
        for fut in self.active_chunk_futures.values():
            fut.cancel()
        self.active_chunk_futures.clear()
        self.killer_monster = None

        # 새 탈출구 생성 (관문 위치 확정 및 관문 충돌체 등록)
        self.setup_escape_portal()

        # 관문 접근 경보 및 증원 상태 리셋
        self.gate_alarm_level = 0
        self.gate_reinforce_timer = 0.0
        self.door_defense_spawn_timer = 0.0

        # 다중 몬스터 군단 재배치 (관문 주변 수호 몬스터 집중 배치)
        self.spawn_monsters(self.current_stage)
        self.spawn_hazard_barrels()
        self.spawn_supply_crates()

        # 전투 서브시스템: 탄약 보급
        self.combat.stop_aim()
        self.combat.ammo = self.combat.max_ammo
        self.combat.reserve_ammo += 24
        self.combat.reset_state(self.current_stage, keep_ammo=True)
        self._update_quickslot_hud()

        # 안개 복구
        self.liminal_fog.setColor(FOG_COLOR)
        self.liminal_fog.setExpDensity(0.038)
        self.setBackgroundColor(FOG_COLOR)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(FOG_COLOR)
        self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
        self.combat.set_blackout_mode(False)

        # 배너 알림
        self.ui_mgr.show_stage_banner(f"[ STAGE {self.current_stage} START! ]\n던전 심연 진입: 몬스터 증가 & 탄약 완충!")
        self.stage_banner_timer = 3.0

    def on_shop_closed(self):
        """스탯 분배 및 상점 완료 후 다음 스테이지 진입"""
        self.advance_to_next_stage()
        self.game_state = "PLAYING"
        self.ui_mgr.start_game_ui()
        self.player.lock_mouse(True)

    def trigger_victory(self):
        """탈출구 방어 성공 시 승리"""
        if self.game_over or self.game_won:
            return
        self.game_won = True
        self.game_state = "VICTORY"

        green_fog = LColor(0.02, 0.20, 0.07, 1.0)
        self.liminal_fog.setColor(green_fog)
        self.setBackgroundColor(green_fog)
        if hasattr(self, 'win') and self.win:
            self.win.setClearColor(green_fog)

        if self.audio_mgr.bgm:
            self.audio_mgr.bgm.setVolume(0.25)

        elapsed = self.time_limit - self.time_left
        remaining = max(0.0, self.time_left)
        self.ui_mgr.show_victory(f"비상 탈출구를 열고 악몽의 미궁을 탈출했습니다!\n[소요 시간: {elapsed:.1f}초  |  남은 탄약: {self.combat.ammo}/12발]")
        self.player.lock_mouse(False)

        self.ui_mgr.save_rank_record("탈출 성공", True, elapsed, remaining, self.combat.ammo, self.current_stage, self.combat.reserve_ammo)

    def trigger_game_over(self, killer=None, reason="killed"):
        """사망 또는 시간 초과 시 게임 오버"""
        if self.game_over or self.game_won:
            return
        self.game_over = True
        self.game_state = "GAME_OVER"
        self.killer_monster = killer

        elapsed = self.time_limit - self.time_left
        remaining = max(0.0, self.time_left)

        if killer is not None:
            px, py = self.camera.getX(), self.camera.getY()
            kx, ky = killer.pos.x, killer.pos.y
            kz = getattr(killer.pos, 'z', 0.0)
            dx = kx - px
            dy = ky - py
            h = math.degrees(math.atan2(-dx, dy))
            dist = max(0.2, math.hypot(dx, dy))
            target_eye_z = kz + 1.8
            p = math.degrees(math.atan2(target_eye_z - PLAYER_EYE_HEIGHT, dist))
            self.camera.setHpr(h, p, 0)
            killer.update(0.016, is_moving=False, is_attacking=True)

            k_name = getattr(killer, 'name', '괴물')
            desc = f"{k_name}에게 무자비하게 습격당해 생명을 잃었습니다..."
            res_desc = f"사망 ({k_name})"

            blood_fog = LColor(0.025, 0.003, 0.003, 1.0)
            self.liminal_fog.setColor(blood_fog)
            self.setBackgroundColor(blood_fog)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(blood_fog)
        else:
            desc = "제한시간 5분이 모두 지나 미궁의 심연에 영원히 갇혔습니다..."
            res_desc = "탈출 실패 (시간 초과)"
            purple_fog = LColor(0.012, 0.003, 0.020, 1.0)
            self.liminal_fog.setColor(purple_fog)
            self.setBackgroundColor(purple_fog)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(purple_fog)

        if self.audio_mgr.bgm:
            self.audio_mgr.bgm.setVolume(0.20)

        self.ui_mgr.show_game_over(desc)
        self.player.lock_mouse(False)

        self.ui_mgr.save_rank_record(res_desc, False, elapsed, remaining, self.combat.ammo, self.current_stage, self.combat.reserve_ammo)

    # --- 탈출구 및 스폰 계산 ---
    def setup_escape_portal(self):
        """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성"""
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
                    if math.hypot(cx - spawn_x, cy - spawn_y) >= 70.0:
                        candidates.append((cx, cy))

        self.escape_pos = random.choice(candidates) if candidates else (spawn_x + 75.0, spawn_y + 75.0)

        if hasattr(self, 'escape_portal_np') and self.escape_portal_np:
            self.escape_portal_np.removeNode()

        self.escape_portal_np = self.world_root.attachNewNode("escape_portal")
        self.escape_portal_np.setPos(self.escape_pos[0], self.escape_pos[1], 0)

        dark_metal_frame = LColor(0.12, 0.12, 0.14, 1.0)
        steel_door_plate = LColor(0.24, 0.25, 0.28, 1.0)
        lock_reinforce_col = LColor(0.38, 0.39, 0.43, 1.0)
        hazard_dim_stripe = LColor(0.45, 0.38, 0.12, 1.0)

        half_w = 1.35
        # 벙커 바닥 밀폐 플레이트
        make_cube_to(self.escape_portal_np, 3.0, 3.0, 0.20, dark_metal_frame, 0, 0, 0.10)
        # 벙커 내부 완전 차폐 솔리드 코어 (내부 빈 공간 노출 100% 원천 차단)
        make_cube_to(self.escape_portal_np, 2.70, 2.70, 5.20, LColor(0.08, 0.08, 0.09, 1.0), 0, 0, 2.60)

        for cx_sign in (-1, 1):
            for cy_sign in (-1, 1):
                make_cube_to(self.escape_portal_np, 0.30, 0.30, 5.4, dark_metal_frame, cx_sign * half_w, cy_sign * half_w, 2.7)

        make_cube_to(self.escape_portal_np, 3.0, 3.0, 0.35, dark_metal_frame, 0, 0, 5.4)

        self.door_lamps = []
        for h in (0, 90, 180, 270):
            face_np = self.escape_portal_np.attachNewNode(f"door_face_{h}")
            face_np.setH(h)

            # 상단 인방 및 강철 도어 플레이트: 기둥과 완벽 오버랩(너비 2.70m, 높이 5.20m)으로 틈새 밀폐
            make_cube_to(face_np, 2.70, 0.28, 0.40, dark_metal_frame, 0, half_w, 5.20)
            make_cube_to(face_np, 2.70, 0.16, 5.20, steel_door_plate, 0, half_w, 2.60)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 1.2)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 2.6)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 4.0)
            make_cube_to(face_np, 0.14, 0.22, 0.40, lock_reinforce_col, 0.85, half_w + 0.06, 2.5)
            make_cube_to(face_np, 2.3, 0.18, 0.20, hazard_dim_stripe, 0, half_w + 0.03, 0.30)

            make_cube_to(face_np, 0.40, 0.16, 0.16, dark_metal_frame, 0, half_w + 0.05, 5.5)
            lamp = make_cube_to(face_np, 0.28, 0.08, 0.10, LColor(0.35, 0.25, 0.08, 1.0), 0, half_w + 0.08, 5.5)
            lamp.setLightOff()
            self.door_lamps.append(lamp)

        # 벙커 상단 비상 유도 비콘등 (Emergency Beacon Strobe Light)
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
            self.beacon_light_np.removeNode()

        b_light = PointLight('escape_beacon_light')
        b_light.setColor((0.35, 1.5, 0.55, 1.0))
        b_light.setAttenuation((1.0, 0.05, 0.006))
        self.beacon_light_np = self.escape_portal_np.attachNewNode(b_light)
        self.beacon_light_np.setPos(0, 0, 4.3)
        self.render.setLight(self.beacon_light_np)

        # 비콘 발광 큐브
        beacon_bulb = make_cube_to(self.escape_portal_np, 0.45, 0.45, 0.55, LColor(0.2, 1.0, 0.4, 1.0), 0, 0, 4.3)
        beacon_bulb.setLightOff()
        self.beacon_bulb = beacon_bulb

        # 관문 벙커(3.0m x 3.0m) 견고한 AABB 충돌체 등록 - 플레이어 및 몬스터 통과 완벽 차단
        clear_custom_colliders()
        ex, ey = self.escape_pos[0], self.escape_pos[1]
        register_custom_collider((ex - 1.5, ey - 1.5, ex + 1.5, ey + 1.5))

    # --- 청크 스트리밍 및 컬링 최적화 ---
    def update_chunks(self, force=False):
        px, py = self.camera.getX(), self.camera.getY()
        player_cx = int(math.floor(px / CHUNK_SIZE))
        player_cy = int(math.floor(py / CHUNK_SIZE))

        if not force and hasattr(self, 'last_chunk') and (player_cx, player_cy) == self.last_chunk:
            return

        self.last_chunk = (player_cx, player_cy)
        needed_chunks = set()
        for dx in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
            for dy in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
                cx, cy = player_cx + dx, player_cy + dy
                if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                    needed_chunks.add((cx, cy))

        if self.player.last_move_dir.lengthSquared() > 0.01:
            pred_x = px + self.player.last_move_dir.x * 24.0
            pred_y = py + self.player.last_move_dir.y * 24.0
            pred_cx, pred_cy = int(math.floor(pred_x / CHUNK_SIZE)), int(math.floor(pred_y / CHUNK_SIZE))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cx, cy = pred_cx + dx, pred_cy + dy
                    if MAP_MIN_CHUNK <= cx <= MAP_MAX_CHUNK and MAP_MIN_CHUNK <= cy <= MAP_MAX_CHUNK:
                        needed_chunks.add((cx, cy))

        for coord in [c for c in self.chunks if c not in needed_chunks]:
            self.chunks[coord].destroy()
            del self.chunks[coord]

        for coord in [c for c in self.active_chunk_futures if c not in needed_chunks]:
            self.active_chunk_futures.pop(coord).cancel()

        missing = [c for c in needed_chunks if c not in self.chunks and c not in self.active_chunk_futures]
        if missing:
            missing.sort(key=lambda c: (c[0] - player_cx)**2 + (c[1] - player_cy)**2)
            if force:
                futs = [self.chunk_executor.submit(Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex) for cx, cy in missing]
                for fut in futs:
                    try:
                        chunk = fut.result()
                        chunk.attach_to(self.world_root)
                        self.chunks[(chunk.cx, chunk.cy)] = chunk
                    except Exception as e:
                        print(f"초기 청크 로딩 에러: {e}")
                self.cull_chunks_to_view(force=True)
            else:
                for cx, cy in missing:
                    self.active_chunk_futures[(cx, cy)] = self.chunk_executor.submit(
                        Chunk, None, cx, cy, self.floor_tex, self.wall_tex, self.sky_tex
                    )

    def cull_chunks_to_view(self, force=False):
        """이동 거리 임계치(2.0m) 기반 청크 가시거리 컬링 최적화"""
        px, py = self.camera.getX(), self.camera.getY()
        if not force and self.last_cull_pos is not None:
            if math.hypot(px - self.last_cull_pos[0], py - self.last_cull_pos[1]) < 2.0:
                return

        self.last_cull_pos = (px, py)
        chunk_rad = (CHUNK_SIZE / 2.0) * math.sqrt(2)
        max_dist_sq = (72.0 + chunk_rad) ** 2

        visible_count = 0
        for (cx, cy), chunk in self.chunks.items():
            ccx = (cx + 0.5) * CHUNK_SIZE
            ccy = (cy + 0.5) * CHUNK_SIZE
            d_sq = (ccx - px) ** 2 + (ccy - py) ** 2
            is_visible = (d_sq <= max_dist_sq)
            chunk.set_visible(is_visible)
            if is_visible:
                visible_count += 1

        self.rendered_chunk_count = visible_count
        self.total_chunk_count = len(self.chunks)

    def _mount_async_chunks(self):
        """백그라운드 스레드에서 생성 완료된 청크 마운트"""
        chunk_created = False
        if self.active_chunk_futures:
            cur_px, cur_py = self.camera.getX(), self.camera.getY()
            cur_cx, cur_cy = int(math.floor(cur_px / CHUNK_SIZE)), int(math.floor(cur_py / CHUNK_SIZE))
            done_coords = [coord for coord, fut in self.active_chunk_futures.items() if fut.done()]
            for coord in done_coords:
                fut = self.active_chunk_futures.pop(coord)
                try:
                    chunk = fut.result()
                    if abs(coord[0] - cur_cx) <= RENDER_RADIUS + 1 and abs(coord[1] - cur_cy) <= RENDER_RADIUS + 1:
                        chunk.attach_to(self.world_root)
                        self.chunks[coord] = chunk
                        chunk_created = True
                    else:
                        chunk.destroy()
                except Exception as e:
                    print(f"청크 마운트 예외: {e}")
        return chunk_created

    # --- 몬스터 AI 제어 (다중 군단) ---
    def _update_monsters(self, dt, px, py):
        closest_dist = 999.0
        stage_mult = 1.0 + (self.current_stage - 1) * 0.15
        if self.blackout_active:
            stage_mult *= 1.25  # 정전 프로토콜: 몬스터 이동속도 25% 가속 (폭주 상태)

        # 관문 거리 계산 및 관문 접근 시 몬스터 가속 / 긴급 증원 트리거
        ex, ey = getattr(self, 'escape_pos', (px + 100, py + 100))
        dist_gate = math.hypot(px - ex, py - ey)

        # [관문 접근 가속] 관문 근처로 갈수록 몬스터들의 이동 속도 대폭 증가 (최대 +45% 가속)
        if dist_gate <= 50.0:
            prox_factor = max(0.0, min(1.0, (50.0 - dist_gate) / 50.0))
            stage_mult *= (1.0 + prox_factor * 0.45)

        # [관문 접근 1단계 경보 (45m 이내)] 몬스터 집결 및 2마리 즉시 증원
        if dist_gate <= 45.0 and getattr(self, 'gate_alarm_level', 0) < 1:
            self.gate_alarm_level = 1
            self.audio_mgr.play_door_alarm()
            self.ui_mgr.show_stage_banner("[ ⚠️ 경고: 탈출 관문 구역 접근 감지 ]\n주변 괴물들이 탈출구를 봉쇄하기 위해 몰려옵니다!", color=(1.0, 0.65, 0.1, 1.0))
            self.stage_banner_timer = 3.0
            for _ in range(2):
                self.spawn_reinforcement_monster(near_gate=True)

        # [관문 접근 2단계 경보 (25m 이내)] 대규모 긴급 증원 (3마리 추가 급습)
        if dist_gate <= 25.0 and getattr(self, 'gate_alarm_level', 0) < 2:
            self.gate_alarm_level = 2
            self.audio_mgr.play_door_alarm()
            self.ui_mgr.show_stage_banner("[ 🚨 비상: 관문 수호 방어선 진입! ]\n대규모 괴물 무리가 총공격을 시작합니다!", color=(1.0, 0.2, 0.2, 1.0))
            self.stage_banner_timer = 3.5
            for _ in range(3):
                self.spawn_reinforcement_monster(near_gate=True)

        # [관문 주변 지속 유입] 관문 32m 이내에 머무는 동안 4초마다 괴물 지속 보충
        if dist_gate <= 32.0:
            self.gate_reinforce_timer = getattr(self, 'gate_reinforce_timer', 0.0) + dt
            if self.gate_reinforce_timer >= 4.0:
                self.gate_reinforce_timer = 0.0
                if len(self.monsters) < 16:
                    self.spawn_reinforcement_monster(near_gate=True)

        for m in self.monsters[:]:
            if getattr(m, 'hp', 1) <= 0:
                # 사망한 몬스터: 시체로 전환하고 활성 몬스터 목록에서 제외하여 시체 목록으로 이전
                if not getattr(m, 'is_corpse', False) and hasattr(m, 'turn_into_corpse'):
                    m.turn_into_corpse(audio_mgr=self.audio_mgr)
                self.monsters.remove(m)
                self.corpses.append(m)
                # 관문 근처에서 처치 시 후방에서 빠르게 추가 증원
                if dist_gate <= 35.0 and len(self.monsters) < 14:
                    if random.random() < 0.65:
                        self.spawn_reinforcement_monster(near_gate=True)
                continue

            mx, my = m.pos.x, m.pos.y
            dist = math.hypot(px - mx, py - my)
            if dist < closest_dist:
                closest_dist = dist

            # 1. 근접 공격 판정
            attack_range = 1.95 if isinstance(m, (TallSkeletonMonster, AbominableMudOrc)) else 1.45
            if dist <= attack_range and m.stun_timer <= 0.0:
                is_dead = self.player.take_damage(m.attack_damage, source_pos=(mx, my))
                m.update(dt, is_moving=False, is_attacking=True)
                if is_dead:
                    self.trigger_game_over(killer=m, reason="killed")
                    return True, closest_dist
                continue

            # 2. 스턴 상태 처리
            if m.stun_timer > 0.0:
                m.update_pos(mx, my, dt, 0, 0)
                continue

            # 3. 진흙 오크: 땅을 울려서 플레이어 이동방해 (Ground Slam)
            if isinstance(m, AbominableMudOrc):
                m.slam_cooldown -= dt
                if dist <= 12.0 and m.slam_cooldown <= 0.0 and not m.is_slamming and m.stun_timer <= 0.0:
                    m.is_slamming = True
                    m.slam_timer = 0.0
                    m.slam_has_impacted = False
                    m.slam_cooldown = 5.5

                if m.is_slamming:
                    impact = m.slam_ground(dt)
                    if impact:
                        self.shockwaves.append(GroundShockwave(self.render, mx, my))
                        self.audio_mgr.play_orc_slam()
                        if dist <= 11.5:
                            self.player.apply_slow(duration=2.8, factor=0.40)
                            self.player.trigger_quake_shake(intensity=2.6, duration=0.85)
                    continue

            # 4. 시선 검사 (Line of Sight)
            has_los = False
            if dist <= 28.0:
                mid_x, mid_y = (mx + px) * 0.5, (my + py) * 0.5
                cols = get_nearby_colliders(self.chunks, mid_x, mid_y, dist * 0.5 + 1.2)
                has_los = check_line_of_sight(mx, my, px, py, cols)

            # 5. 잿더미 마녀: 파이어볼 투척 (Fireball Cast)
            if isinstance(m, AlluringAshWitch):
                m.cast_cooldown -= dt
                if has_los and dist <= 24.0 and m.cast_cooldown <= 0.0 and not m.is_casting and m.stun_timer <= 0.0:
                    m.is_casting = True
                    m.cast_timer = 0.0
                    m._fireball_fired = False
                    m.cast_cooldown = 3.2

                if m.is_casting:
                    fire = m.cast_fireball(dt)
                    if fire:
                        orb_pos = (mx, my, m.pos.z + 1.5)
                        target_pos = (px, py, PLAYER_EYE_HEIGHT)
                        self.fireballs.append(Fireball(self.render, orb_pos, target_pos))
                        self.audio_mgr.play_witch_fireball()

                    dx = px - mx
                    dy = py - my
                    target_h = math.degrees(math.atan2(-dx, dy))
                    m.node.setH(target_h)
                    continue

            # 6. 길찾기 (Pathfinding)
            m.path_timer -= dt
            if has_los:
                tx, ty = px, py
                m.path = []
            else:
                mgx = int(math.floor(mx / CELL_SIZE))
                mgy = int(math.floor(my / CELL_SIZE))
                pgx = int(math.floor(px / CELL_SIZE))
                pgy = int(math.floor(py / CELL_SIZE))

                if (mgx, mgy) == (pgx, pgy):
                    tx, ty = px, py
                else:
                    if m.path_timer <= 0.0 or not m.path:
                        interval = 0.18 + random.random() * 0.08 if dist_gate <= 35.0 else 0.35 + random.random() * 0.10
                        m.path_timer = interval
                        m.path = find_cell_path((mgx, mgy), (pgx, pgy), max_depth=28)

                    while len(m.path) > 1 and m.path[0] != (mgx, mgy):
                        if (mgx, mgy) == m.path[1]:
                            m.path.pop(0)
                        else:
                            break

                    if len(m.path) >= 2:
                        c1 = m.path[0]
                        c2 = m.path[1]
                        tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                        ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                        if math.hypot(mx - tx, my - ty) < 0.9:
                            m.path.pop(0)
                            if len(m.path) >= 2:
                                c1 = m.path[0]
                                c2 = m.path[1]
                                tx = (c1[0] + c2[0] + 1.0) * 0.5 * CELL_SIZE
                                ty = (c1[1] + c2[1] + 1.0) * 0.5 * CELL_SIZE
                            else:
                                tx, ty = px, py
                    else:
                        tx, ty = px, py

            dx = tx - mx
            dy = ty - my
            d = math.hypot(dx, dy)
            if d > 0.05:
                ndx, ndy = dx / d, dy / d
                speed = getattr(m, 'speed', 8.5) * stage_mult
                col_radius = 0.40
                new_x, new_y = resolve_collision(self.chunks, mx, my, ndx * speed * dt, ndy * speed * dt, radius=col_radius)
                m.update_pos(new_x, new_y, dt, ndx, ndy)
            else:
                m.update(dt, is_moving=False)

        # 사망한 몬스터들의 비산 파편 물리 및 폭발 섬광 조명 갱신
        for c in self.corpses:
            if hasattr(c, 'update_debris'):
                c.update_debris(dt)

        return False, closest_dist

    def _update_projectiles(self, dt, px, py, pz):
        """파이어볼 비행/벽체 및 플레이어 피격 충돌, 땅울림 분진 갱신"""
        # 1. 파이어볼 갱신
        for fb in self.fireballs[:]:
            alive = fb.update(dt)
            if not alive:
                fb.destroy()
                self.fireballs.remove(fb)
                continue

            # 벽체 충돌 검사
            cols = get_nearby_colliders(self.chunks, fb.pos.x, fb.pos.y, search_dist=0.6)
            hit_wall = False
            for min_x, min_y, max_x, max_y in cols:
                if min_x <= fb.pos.x <= max_x and min_y <= fb.pos.y <= max_y:
                    hit_wall = True
                    break
            if hit_wall:
                fb.destroy()
                self.fireballs.remove(fb)
                continue

            # 플레이어 충돌 검사
            dist_p = math.hypot(fb.pos.x - px, fb.pos.y - py)
            dz = abs(fb.pos.z - pz)
            if dist_p < 0.95 and dz < 1.6:
                is_dead = self.player.take_damage(fb.damage, source_pos=(fb.pos.x, fb.pos.y))
                fb.destroy()
                self.fireballs.remove(fb)
                if is_dead:
                    first_witch = next((m for m in self.monsters if isinstance(m, AlluringAshWitch)), None)
                    self.trigger_game_over(killer=first_witch, reason="killed")
                    return True

        # 2. 땅울림 충격파 분진 갱신
        for sw in self.shockwaves[:]:
            if not sw.update(dt):
                sw.destroy()
                self.shockwaves.remove(sw)

        # 3. 전술 파열 수류탄 갱신 및 폭발
        for gr in self.grenades[:]:
            alive = gr.update(dt, self.chunks, self.monsters)
            if not alive:
                gr.explode(self.monsters, self.player, self.ui_mgr, self.hazard_barrels, explosion_list=self.explosions)
                if gr in self.grenades:
                    self.grenades.remove(gr)

        # 4. 폭발성 유류 드럼통 점화 및 폭발 갱신
        for b in self.hazard_barrels[:]:
            alive = b.update(dt, self.monsters, self.player, self.ui_mgr, self.hazard_barrels, explosion_list=self.explosions)
            if not alive:
                if b in self.hazard_barrels:
                    self.hazard_barrels.remove(b)

        # 5. 수류탄 / 유류 드럼통 3D 폭발 비주얼 이펙트 갱신
        for exp in self.explosions[:]:
            if not exp.update(dt):
                if exp in self.explosions:
                    self.explosions.remove(exp)

        return False

    def _update_door_defense(self, dt, px, py):
        """탈출 관문 앞 3.8m 방어 판정 (관문 외벽에서 5초 사수 시 상점 모달 팝업)"""
        dist_exit = math.hypot(px - self.escape_pos[0], py - self.escape_pos[1])
        if dist_exit <= 3.8:
            old_timer = self.door_hold_timer
            self.door_hold_timer -= dt
            progress_sec = 5.0 - max(0.0, self.door_hold_timer)

            # 매 1초마다 전자 보안 비프음 재생
            if int(progress_sec) != int(5.0 - max(0.0, old_timer)):
                self.audio_mgr.play_door_alarm()

            # 관문 개방 시도 중 괴물 긴급 유입 (2.0초마다 추가 괴물 증원)
            self.door_defense_spawn_timer = getattr(self, 'door_defense_spawn_timer', 0.0) + dt
            if self.door_defense_spawn_timer >= 2.0:
                self.door_defense_spawn_timer = 0.0
                if len(self.monsters) < 18:
                    self.spawn_reinforcement_monster(near_gate=True)

            pct = max(0.0, min(1.0, progress_sec / 5.0))
            bars = int(pct * 16)
            bar_str = "■" * bars + "□" * (16 - bars)

            blink = (int(globalClock.getFrameTime() * 8) % 2 == 0)
            blink_col = LColor(0.9, 0.15, 0.15, 1.0) if blink else LColor(0.3, 0.05, 0.05, 1.0)
            for lamp in self.door_lamps:
                lamp.setColor(blink_col)

            if self.door_hold_timer <= 0.0:
                for lamp in self.door_lamps:
                    lamp.setColor(LColor(0.2, 1.0, 0.4, 1.0))
                self.audio_mgr.play_door_unlock()
                self.door_hold_timer = 5.0
                # 던전 크롤러: 스탯 분배 및 상점 모달 팝업 & 다음 스테이지 준비
                self.game_state = "SHOP"
                self.player.lock_mouse(False)
                self.combat.stop_aim()
                self.ui_mgr.show_stage_clear_shop(
                    self.current_stage, self.player, self.combat,
                    self.on_shop_closed, on_victory_callback=self.trigger_victory
                )
                return True
            else:
                msg = f"[ 비상문 개방 중: {progress_sec:.1f}s / 5.0s  [{bar_str}] ]\n[ 경고: 문이 열릴 때까지 쏟아지는 괴물의 접근을 저지하세요! ]"
                self.ui_mgr.update_door_status(msg, fg=(1.0, 0.85, 0.2, 1.0))
        else:
            if self.door_hold_timer < 5.0:
                self.door_hold_timer = 5.0
                idle_col = LColor(0.35, 0.25, 0.08, 1.0)
                for lamp in self.door_lamps:
                    lamp.setColor(idle_col)
                self.ui_mgr.update_door_status("[ 비상문 개방 중단! 탈출 관문 앞을 사수하세요! ]", fg=(1.0, 0.3, 0.3, 1.0))
            else:
                self.ui_mgr.update_door_status("", show=False)
        return False

    # --- 메인 틱 루프 (Main Update Loop) ---
    def update(self, task):
        dt = min(0.1, globalClock.getDt())
        cont = task.cont if task is not None else 1

        # 1. 인트로 시네마틱 카메라 회전
        if self.game_state == "INTRO":
            t = globalClock.getFrameTime()
            cam_x = 45.0 + math.sin(t * 0.12) * 38.0
            cam_y = 45.0 + math.cos(t * 0.12) * 38.0
            self.camera.setPos(cam_x, cam_y, 11.5)
            self.camera.lookAt(45.0, 45.0, 1.5)
            self.update_chunks()
            return cont

        # 2. 상점 및 인벤토리 모달 상태 시 업데이트 정지
        if self.game_state in ("SHOP", "INVENTORY"):
            return cont

        # 3. 승리 및 게임 오버 상태 처리
        if self.game_won or self.game_state == "VICTORY":
            return cont

        if self.game_over or self.game_state == "GAME_OVER":
            self.ui_mgr.update(dt, player_pos=(self.camera.getX(), self.camera.getY()), camera_heading=getattr(self.player, 'heading', 0.0))
            if self.killer_monster is not None:
                killer = self.killer_monster
                px, py = self.camera.getX(), self.camera.getY()
                dx, dy = killer.pos.x - px, killer.pos.y - py
                h = math.degrees(math.atan2(-dx, dy))
                p = math.degrees(math.atan2(1.8 - PLAYER_EYE_HEIGHT, max(0.2, math.hypot(dx, dy))))
                self.camera.setHpr(h, p, 0)
                killer.update(dt, is_moving=False, is_attacking=True)
            return cont

        # 4. 비동기 청크 마운트
        chunk_created = self._mount_async_chunks()

        # 5. 플레이어 시선 및 이동/충돌 처리
        is_moving, is_sprinting, view_changed = self.player.update(dt, self.chunks)
        if is_moving:
            self.update_chunks()

        # 6. 괴물 군단 AI 및 공격 판정
        px, py = self.camera.getX(), self.camera.getY()
        game_ended, closest_dist = self._update_monsters(dt, px, py)
        if game_ended:
            return cont

        # 6-1. 마녀 파이어볼 및 진흙오크 충격파 갱신
        if self._update_projectiles(dt, px, py, PLAYER_EYE_HEIGHT):
            return cont

        # 7. 오디오 3D 위치 및 감쇠
        self.audio_mgr.update(dt, closest_dist, closest_dist, False, False)

        # 8. 안개 가시거리 컬링 (임계치 2.0m 이동 또는 신규 청크 마운트 시만 실행)
        if chunk_created or is_moving:
            self.cull_chunks_to_view(force=chunk_created)

        # 9. 전투 및 뷰모델 갱신 (반동, 재장전, 탄약 습득, 밥빙)
        self.combat.update(dt, px, py, is_moving, is_sprinting)

        # 10. 배너 타이머
        if self.stage_banner_timer > 0.0:
            self.stage_banner_timer -= dt
            if self.stage_banner_timer <= 0.0:
                self.ui_mgr.hide_stage_banner()

        # 10-1. 정전 프로토콜 (Blackout & Crimson Protocol) 발동 및 타이머 갱신
        if self.time_left <= 200.0 and not self.blackout_triggered_this_stage:
            self.blackout_triggered_this_stage = True
            self.blackout_active = True
            b_duration = 18.0
            if "abyssal_reaper" in getattr(self.player, 'relics', []):
                b_duration += 10.0  # 심연의 수확자 유물: 정전 지속시간 10초 증가
            self.blackout_timer = b_duration
            self.audio_mgr.play_siren_alarm()
            self.ui_mgr.show_blackout_warning()
            self.liminal_fog.setColor(BLACKOUT_FOG_COLOR)
            self.liminal_fog.setExpDensity(0.052)  # 짙고 자욱한 핏빛 미스트 안개
            self.setBackgroundColor(BLACKOUT_FOG_COLOR)
            if hasattr(self, 'win') and self.win:
                self.win.setClearColor(BLACKOUT_FOG_COLOR)
            self.amb_np.node().setColor((0.012, 0.002, 0.002, 1.0))
            self.combat.set_blackout_mode(True)

        if self.blackout_active:
            self.blackout_timer -= dt
            if self.blackout_timer <= 0.0:
                self.blackout_active = False
                self.audio_mgr.play_power_restored()
                self.ui_mgr.hide_blackout_warning()
                self.liminal_fog.setColor(FOG_COLOR)
                self.liminal_fog.setExpDensity(0.038)
                self.setBackgroundColor(FOG_COLOR)
                if hasattr(self, 'win') and self.win:
                    self.win.setClearColor(FOG_COLOR)
                self.amb_np.node().setColor((0.005, 0.005, 0.006, 1.0))
                self.combat.set_blackout_mode(False)
                self.ui_mgr.show_stage_banner("[ 전력 복구 완료 ]\n비상 조명 해제 및 기지 전력 정상화", color=(0.4, 0.9, 1.0, 1.0))
                self.stage_banner_timer = 2.5

        # 11. 5분 탈출 제한시간 카운트다운
        self.time_left -= dt
        if self.time_left <= 0.0:
            self.time_left = 0.0
            self.trigger_game_over(killer=None, reason="timeout")
            return cont

        # 12. 비상탈출문 5초 방어 판정 (성공 시 상점 모달 오픈)
        if self._update_door_defense(dt, px, py):
            return cont

        # 12-1. 비상 비콘 유도등 실시간 맥동
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            t_now = globalClock.getFrameTime()
            pulse = 0.65 + 0.35 * math.sin(t_now * 4.5)
            self.beacon_light_np.node().setColor((0.35 * pulse, 1.5 * pulse, 0.55 * pulse, 1.0))

        # 13. HUD 텍스트 캐싱 및 실시간 피격 효과 애니메이션 갱신
        self.ui_mgr.update(dt, player_pos=(px, py), camera_heading=getattr(self.player, 'heading', 0.0), is_moving=is_moving, is_sprinting=is_sprinting)
        self.ui_mgr.update_timer(self.time_left, self.current_stage)
        self.ui_mgr.update_hud(px, py, getattr(self, 'escape_pos', None), getattr(self.player, 'heading', 0.0))

        # 전술 스킬 (슬라이드 / 수류탄) 및 필드 보급 상자 인터랙션 갱신
        if self.grenade_cooldown > 0.0:
            self.grenade_cooldown = max(0.0, self.grenade_cooldown - dt)

        # 필드 전술 보급 상자 [E] 상호작용 프롬프트 검사
        closest_crate = None
        for cr in self.supply_crates:
            if cr.can_interact(px, py):
                closest_crate = cr
                break
        self.nearby_crate = closest_crate
        if closest_crate:
            self.ui_mgr.show_interact_prompt("[ E ] 전술 보급 상자 개봉")
        else:
            self.ui_mgr.hide_interact_prompt()

        slide_ready = getattr(self.player, 'slide_cooldown', 0.0) <= 0.0
        self.ui_mgr.update_skills_hud(slide_ready, self.grenade_cooldown)

        return cont

    def destroy(self):
        if hasattr(self, 'beacon_light_np') and self.beacon_light_np and not self.beacon_light_np.isEmpty():
            self.render.clearLight(self.beacon_light_np)
        if hasattr(self, 'chunk_executor'):
            self.chunk_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()


if __name__ == "__main__":
    game = LiminalInfiniteLoop()
    game.run()