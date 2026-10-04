import math
import random
from panda3d.core import (
    PointLight, Vec3, LColor, NodePath, TransparencyAttrib
)
from constants import CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK, WALL_HEIGHT
from world_gen import cell_has_pillar
from geometry import make_cube_to, make_cube
from collision import get_nearby_colliders


class ThrowingFirePot:
    """
    투척용 비산 화약병 (Greek Fire / Explosive Fire Pot Projectile)
    - 플레이어가 포물선 궤적으로 투척하는 물리 화약 단지
    - 바닥/벽/몬스터 착탄 시 굉음과 함께 광역 화염 폭발 (반경 3.8m, 85 피해)
    - 착탄 지점에 4.5초간 성스러운 화염 지대(Ground Fire)를 남겨 지속 피해
    """
    def __init__(self, world_root, spawn_pos, throw_dir, player=None):
        self.world_root = world_root
        self.pos = Vec3(spawn_pos)
        self.speed = 22.0
        # 전방 속도 + 살짝 위쪽 곡사각
        self.vel = Vec3(throw_dir.x * self.speed, throw_dir.y * self.speed, throw_dir.z * self.speed + 3.8)
        self.gravity = -15.5
        self.player = player
        self.is_dead = False
        self.life = 0.0
        self.max_life = 4.0

        self.node = world_root.attachNewNode("thrown_fire_pot")
        self.node.setPos(self.pos)

        # 점토 항아리 + 도화선 불씨 3D 모델
        clay_col = LColor(0.48, 0.28, 0.16, 1.0)
        iron_col = LColor(0.22, 0.22, 0.25, 1.0)
        flame_col = LColor(1.0, 0.65, 0.15, 1.0)

        make_cube_to(self.node, 0.22, 0.22, 0.28, clay_col, 0, 0, 0)
        make_cube_to(self.node, 0.14, 0.14, 0.09, iron_col, 0, 0, 0.16)
        fuse = make_cube_to(self.node, 0.05, 0.05, 0.07, flame_col, 0, 0, 0.22)
        fuse.setLightOff()

        self.light = PointLight('pot_fuse_light')
        self.light.setColor((1.0, 0.55, 0.15, 1.0))
        self.light.setAttenuation((1.0, 0.4, 0.1))
        self.light_np = self.node.attachNewNode(self.light)
        self.world_root.setLight(self.light_np)

    def update(self, dt, chunks, monsters, inventory_sys):
        if self.is_dead:
            return

        self.life += dt
        if self.life >= self.max_life:
            self.explode(inventory_sys, monsters)
            return

        self.vel.z += self.gravity * dt
        new_pos = self.pos + self.vel * dt

        # 항아리 회전
        self.node.setP(self.node.getP() + 380 * dt)
        self.node.setH(self.node.getH() + 220 * dt)

        # 1. 몬스터 직격 충돌
        hit_monster = False
        if monsters:
            for m in monsters:
                if getattr(m, 'hp', 0) <= 0:
                    continue
                mx, my, mz = m.pos.x, m.pos.y, getattr(m.pos, 'z', 1.0)
                if math.hypot(new_pos.x - mx, new_pos.y - my) <= 0.95 and abs(new_pos.z - mz) <= 1.5:
                    hit_monster = True
                    break

        # 2. 바닥/천장 충돌
        hit_ground = (new_pos.z <= 0.06)
        hit_ceiling = (new_pos.z >= WALL_HEIGHT - 0.25)

        # 3. 벽 충돌
        hit_wall = False
        if chunks:
            cols = get_nearby_colliders(chunks, new_pos.x, new_pos.y, search_dist=1.2)
            for c_min_x, c_min_y, c_max_x, c_max_y in cols:
                if c_min_x <= new_pos.x <= c_max_x and c_min_y <= new_pos.y <= c_max_y:
                    hit_wall = True
                    break

        if hit_monster or hit_ground or hit_ceiling or hit_wall:
            self.pos = new_pos
            if hit_ground:
                self.pos.z = 0.05
            self.explode(inventory_sys, monsters)
            return

        self.pos = new_pos
        self.node.setPos(self.pos)

    def explode(self, inventory_sys, monsters):
        """착탄 폭발: 광역 피해, 넉백, 기절 및 바닥 화염 지대 생성"""
        if self.is_dead:
            return
        self.is_dead = True

        inventory_sys.audio_mgr.play_firepot_explode()

        if self.player and hasattr(self.player, 'trigger_quake_shake'):
            self.player.trigger_quake_shake(intensity=0.55, duration=0.12)

        inventory_sys.spawn_explosion_particles(self.pos)

        hit_count = 0
        if monsters:
            for m in monsters:
                if getattr(m, 'hp', 0) <= 0:
                    continue
                dist = math.hypot(m.pos.x - self.pos.x, m.pos.y - self.pos.y)
                if dist <= 3.8:
                    hit_count += 1
                    dmg = 85.0 * max(0.4, 1.0 - (dist / 4.2))
                    is_dead = inventory_sys.base.combat.apply_damage(m, dmg, self.player)
                    m.stun(1.25)
                    dx = m.pos.x - self.pos.x
                    dy = m.pos.y - self.pos.y
                    norm = math.hypot(dx, dy)
                    if norm > 0.01:
                        push = 0.95 if is_dead else 0.55
                        m.pos.x += (dx / norm) * push
                        m.pos.y += (dy / norm) * push
                        if hasattr(m, 'node') and not m.node.isEmpty():
                            m.node.setX(m.pos.x)
                            m.node.setY(m.pos.y)

                    if is_dead and hasattr(m, 'turn_into_corpse'):
                        m.turn_into_corpse()

        if hit_count > 0:
            inventory_sys.ui_mgr.show_hit_marker(f"[화약 폭발] {hit_count}체 타격! (85 피해)", (1.0, 0.65, 0.2, 1.0))

        inventory_sys.create_ground_fire(Vec3(self.pos.x, self.pos.y, 0.03), radius=2.2, duration=4.5)
        self.destroy()

    def destroy(self):
        self.is_dead = True
        if hasattr(self, 'light_np') and not self.light_np.isEmpty():
            self.world_root.clearLight(self.light_np)
            self.light_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class InventorySystem:
    """
    다크 판타지 생존 소비 아이템 및 퀵슬롯 파밍 시스템
    - [1] 생명의 성수병 (Holy Water): 체력 +45 즉각 치유 & 슬로우 해제
    - [2] 정화의 향로 (Sanctifying Censer): 12초간 신성 오라, 피해 반경 5.5m, 괴수 지속 퇴치/피해, 암전 무력화
    - [3] 비산 화약병 (Throwing Fire Pot): 곡사 투척 폭발탄, 85 광역 피해 & 4.5초 잔류 화염 지대
    - 던전 전역 유골함/철제 보급 궤짝 파밍 및 근접 자동 획득
    """
    def __init__(self, base, render, camera, world_root, audio_mgr, ui_mgr):
        self.base = base
        self.render = render
        self.camera = camera
        self.world_root = world_root
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 아이템 수량 및 상한선 (시작 시 각 1개씩 지급)
        self.items = {
            "flask": 1,
            "censer": 1,
            "fire_pot": 1
        }
        self.max_items = {
            "flask": 3,
            "censer": 2,
            "fire_pot": 3
        }

        self.censer_timer = 0.0
        self.censer_burn_tick = 0.0
        self.censer_light = PointLight('censer_holy_light')
        self.censer_light.setColor((1.0, 0.88, 0.50, 1.0))
        self.censer_light.setAttenuation((1.0, 0.06, 0.015))
        self.censer_light_np = self.world_root.attachNewNode(self.censer_light)

        self.active_fire_pots = []
        self.ground_fires = []
        self.fire_particles = []
        self.relic_caches = []

    def use_flask(self, player):
        """[1] 생명의 성수병 사용: 체력 45 회복 및 상태이상 정화"""
        if self.items["flask"] <= 0:
            self.ui_mgr.show_hit_marker("성수병이 없습니다! (던전 유골함을 수색하세요)", (1.0, 0.35, 0.35, 1.0))
            return False

        if player.hp >= player.max_hp and getattr(player, 'slow_timer', 0.0) <= 0.0:
            self.ui_mgr.show_hit_marker("체력이 이미 가득 차 있습니다!", (0.9, 0.9, 0.9, 1.0))
            return False

        self.items["flask"] -= 1
        heal_amount = 45.0
        player.hp = min(player.max_hp, player.hp + heal_amount)
        player.slow_timer = 0.0

        self.audio_mgr.play_flask_drink()
        self.ui_mgr.update_hp_exp(player.hp, player.max_hp, player.exp, player.exp_to_next, player.level, player.stat_points)
        self.ui_mgr.show_hit_marker(f"[생명의 성수] 체력 +{int(heal_amount)} 회복 및 상태이상 정화!", (0.4, 1.0, 0.6, 1.0))
        self.update_quickslot_ui()
        return True

    def use_censer(self, player):
        """[2] 정화의 향로 사용: 12초간 거룩한 오라 발동, 암전 무력화 & 괴수 퇴치"""
        if self.items["censer"] <= 0:
            self.ui_mgr.show_hit_marker("정화의 향로가 없습니다! (던전 유골함을 수색하세요)", (1.0, 0.35, 0.35, 1.0))
            return False

        if self.censer_timer > 0.0:
            self.censer_timer = min(20.0, self.censer_timer + 10.0)
            self.items["censer"] -= 1
            self.ui_mgr.show_hit_marker("[정화의 향로] 향로 연소 시간 연장! (+10초)", (1.0, 0.9, 0.3, 1.0))
        else:
            self.items["censer"] -= 1
            self.censer_timer = 12.0
            self.censer_burn_tick = 0.0
            self.audio_mgr.play_censer_ignite()
            self.render.setLight(self.censer_light_np)
            self.ui_mgr.show_hit_marker("[정화의 향로] 거룩한 향로 점화! (12초간 신성 오라 & 괴수 퇴치)", (1.0, 0.92, 0.45, 1.0))

        self.update_quickslot_ui()
        return True

    def use_fire_pot(self, player):
        """[3] 비산 화약병 투척: 포물선 곡사 투척 화약탄"""
        if self.items["fire_pot"] <= 0:
            self.ui_mgr.show_hit_marker("화약병이 없습니다! (던전 보급함을 수색하세요)", (1.0, 0.35, 0.35, 1.0))
            return False

        self.items["fire_pot"] -= 1

        cam_pos = self.camera.getPos()
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()

        spawn_world = cam_pos + cam_fwd * 0.65 + cam_right * 0.18 - Vec3(0, 0, 0.12)
        pot = ThrowingFirePot(self.world_root, spawn_world, cam_fwd, player=player)
        self.active_fire_pots.append(pot)

        self.ui_mgr.show_hit_marker("[비산 화약병] 화약병 투척!", (1.0, 0.65, 0.25, 1.0))
        self.update_quickslot_ui()
        return True

    def create_ground_fire(self, pos, radius=2.2, duration=4.5):
        """착탄 지점에 성스러운 화염 지대 생성"""
        fire_root = self.world_root.attachNewNode("holy_ground_fire")
        fire_root.setPos(pos)

        fire_color = LColor(0.95, 0.35, 0.08, 0.88)
        inner_color = LColor(1.0, 0.85, 0.25, 0.95)

        for i in range(5):
            r = radius * (0.35 + i * 0.15)
            ang = i * 45
            card = make_cube_to(fire_root, r, r, 0.02, fire_color if i % 2 == 0 else inner_color, 0, 0, 0.002 * i, rot_h=ang)
            card.setLightOff()

        fire_light = PointLight('ground_fire_light')
        fire_light.setColor((1.0, 0.55, 0.12, 1.0))
        fire_light.setAttenuation((1.0, 0.15, 0.05))
        fire_light_np = fire_root.attachNewNode(fire_light)
        fire_light_np.setPos(0, 0, 0.4)
        self.render.setLight(fire_light_np)

        self.ground_fires.append({
            "root": fire_root,
            "light_np": fire_light_np,
            "pos": Vec3(pos),
            "radius": radius,
            "timer": duration,
            "max_timer": duration,
            "tick": 0.0
        })

    def spawn_explosion_particles(self, hit_pos):
        """폭발 화염 파티클 30개 분사"""
        for _ in range(32):
            p_node = self.world_root.attachNewNode("fire_particle")
            p_node.setPos(hit_pos)
            size = random.uniform(0.08, 0.18)
            col = LColor(random.uniform(0.85, 1.0), random.uniform(0.25, 0.65), 0.05, 1.0)
            cube = make_cube_to(p_node, size, size, size, col, 0, 0, 0)
            cube.setLightOff()

            vx = random.uniform(-6.0, 6.0)
            vy = random.uniform(-6.0, 6.0)
            vz = random.uniform(2.5, 7.5)
            self.fire_particles.append({
                "node": p_node,
                "pos": Vec3(hit_pos),
                "vel": Vec3(vx, vy, vz),
                "timer": random.uniform(0.38, 0.65)
            })

    def update(self, dt, player, monsters, chunks, blackout_active=False):
        """매 프레임 소비 아이템 및 화염 상태 업데이트"""
        px, py, pz = player.camera.getX(), player.camera.getY(), player.camera.getZ()

        # 1. 정화의 향로 업데이트
        if self.censer_timer > 0.0:
            self.censer_timer -= dt
            self.censer_light_np.setPos(px, py, pz + 0.2)

            self.censer_burn_tick -= dt
            if self.censer_burn_tick <= 0.0:
                self.censer_burn_tick = 0.45
                if monsters:
                    for m in monsters:
                        if getattr(m, 'hp', 0) <= 0:
                            continue
                        dist = math.hypot(m.pos.x - px, m.pos.y - py)
                        if dist <= 5.5:
                            is_dead = self.base.combat.apply_damage(m, 14.0, player)
                            m.stun(0.4)
                            dx = m.pos.x - px
                            dy = m.pos.y - py
                            norm = math.hypot(dx, dy)
                            if norm > 0.01:
                                m.pos.x += (dx / norm) * 0.45
                                m.pos.y += (dy / norm) * 0.45
                                if hasattr(m, 'node') and not m.node.isEmpty():
                                    m.node.setX(m.pos.x)
                                    m.node.setY(m.pos.y)
                            if is_dead and hasattr(m, 'turn_into_corpse'):
                                m.turn_into_corpse()

            if self.censer_timer <= 0.0:
                self.censer_timer = 0.0
                self.render.clearLight(self.censer_light_np)
                self.ui_mgr.show_hit_marker("향로의 불꽃이 모두 소진되었습니다.", (0.8, 0.8, 0.8, 1.0))
            self.update_quickslot_ui()

        # 2. 투척 화약병 업데이트
        for pot in self.active_fire_pots[:]:
            pot.update(dt, chunks, monsters, self)
            if pot.is_dead:
                self.active_fire_pots.remove(pot)

        # 3. 지면 잔류 화염 지대 업데이트
        for fire in self.ground_fires[:]:
            fire["timer"] -= dt
            fire["tick"] -= dt
            if fire["tick"] <= 0.0:
                fire["tick"] = 0.40
                fx, fy = fire["pos"].x, fire["pos"].y
                r = fire["radius"]
                if monsters:
                    for m in monsters:
                        if getattr(m, 'hp', 0) <= 0:
                            continue
                        if math.hypot(m.pos.x - fx, m.pos.y - fy) <= r:
                            is_dead = self.base.combat.apply_damage(m, 16.0, player)
                            m.stun(0.3)
                            if is_dead and hasattr(m, 'turn_into_corpse'):
                                m.turn_into_corpse()

            scale = max(0.1, fire["timer"] / fire["max_timer"])
            fire["root"].setScale(scale, scale, 1.0)

            if fire["timer"] <= 0.0:
                self.render.clearLight(fire["light_np"])
                fire["root"].removeNode()
                self.ground_fires.remove(fire)

        # 4. 폭발 파티클 업데이트
        for p in self.fire_particles[:]:
            p["timer"] -= dt
            p["vel"].z -= 14.0 * dt
            p["pos"] += p["vel"] * dt
            if p["pos"].z <= 0.025:
                p["pos"].z = 0.025
                p["vel"].set(0, 0, 0)
            p["node"].setPos(p["pos"])
            scale = max(0.1, p["timer"] / 0.5)
            p["node"].setScale(scale)
            if p["timer"] <= 0.0:
                p["node"].removeNode()
                self.fire_particles.remove(p)

        # 5. 던전 파밍 상자 근접 수색 및 획득 (반경 1.85m)
        if self.relic_caches:
            for cache in self.relic_caches[:]:
                cx, cy = cache["pos"]
                if math.hypot(px - cx, py - cy) <= 1.85:
                    self.loot_cache(cache, player)

    def loot_cache(self, cache, player):
        """상자 파밍 성공: 생존 아이템 획득"""
        self.audio_mgr.play_item_pickup()
        c_type = cache.get("type", "urn")

        candidates = []
        if self.items["flask"] < self.max_items["flask"]:
            candidates.extend(["flask", "flask"])
        if self.items["censer"] < self.max_items["censer"]:
            candidates.append("censer")
        if self.items["fire_pot"] < self.max_items["fire_pot"]:
            candidates.extend(["fire_pot", "fire_pot"])

        chosen = random.choice(candidates) if candidates else "flask"

        if chosen == "flask":
            self.items["flask"] = min(self.max_items["flask"], self.items["flask"] + 1)
            item_name = "생명의 성수병 (+1)"
            col = (0.4, 1.0, 0.6, 1.0)
        elif chosen == "censer":
            self.items["censer"] = min(self.max_items["censer"], self.items["censer"] + 1)
            item_name = "정화의 향로 (+1)"
            col = (1.0, 0.9, 0.35, 1.0)
        else:
            self.items["fire_pot"] = min(self.max_items["fire_pot"], self.items["fire_pot"] + 1)
            item_name = "비산 화약병 (+1)"
            col = (1.0, 0.65, 0.25, 1.0)

        title = "성스러운 유골함 발굴!" if c_type == "urn" else "철제 보급 상자 수색!"
        self.ui_mgr.show_hit_marker(f"[{title}] {item_name} 획득!", col)

        if "light_np" in cache and cache["light_np"] and not cache["light_np"].isEmpty():
            self.render.clearLight(cache["light_np"])
            cache["light_np"].removeNode()
        if "node" in cache and cache["node"] and not cache["node"].isEmpty():
            cache["node"].removeNode()
        self.relic_caches.remove(cache)
        self.update_quickslot_ui()

    def clear_stage_loot(self):
        """보급함과 등록된 광원을 해제합니다."""
        for cache in self.relic_caches:
            if cache.get("light_np") and not cache["light_np"].isEmpty():
                self.render.clearLight(cache["light_np"])
                cache["light_np"].removeNode()
            if cache.get("node") and not cache["node"].isEmpty():
                cache["node"].removeNode()
        self.relic_caches = []

    def setup_stage_loot(self, current_stage=1):
        """각 스테이지 던전 복도에 7~9개의 유골함 및 보급 상자 배치"""
        self.clear_stage_loot()
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
                    d = math.hypot(cx - spawn_x, cy - spawn_y)
                    if d >= 16.0:
                        candidates.append((cx, cy))

        if not candidates:
            return

        cache_count = min(9, max(6, len(candidates) // 15))
        chosen_positions = random.sample(candidates, cache_count)

        urn_clay = LColor(0.55, 0.35, 0.20, 1.0)
        urn_gold = LColor(0.85, 0.70, 0.25, 1.0)
        iron_box = LColor(0.25, 0.28, 0.32, 1.0)
        steel_band = LColor(0.45, 0.45, 0.50, 1.0)

        for i, (x, y) in enumerate(chosen_positions):
            is_urn = (i % 2 == 0)
            c_type = "urn" if is_urn else "chest"
            cache_np = self.world_root.attachNewNode(f"loot_{c_type}_{i}")
            cache_np.setPos(x, y, 0.18)

            if is_urn:
                make_cube_to(cache_np, 0.34, 0.34, 0.45, urn_clay, 0, 0, 0)
                make_cube_to(cache_np, 0.36, 0.36, 0.08, urn_gold, 0, 0, 0.08).setLightOff()
                make_cube_to(cache_np, 0.24, 0.24, 0.12, urn_clay, 0, 0, 0.24)

                c_light = PointLight('urn_glow')
                c_light.setColor((0.95, 0.80, 0.35, 1.0))
                c_light.setAttenuation((1.0, 0.25, 0.08))
                c_light_np = cache_np.attachNewNode(c_light)
                c_light_np.setPos(0, 0, 0.42)
                self.render.setLight(c_light_np)
            else:
                make_cube_to(cache_np, 0.52, 0.36, 0.30, iron_box, 0, 0, 0)
                make_cube_to(cache_np, 0.54, 0.08, 0.32, steel_band, 0, -0.09, 0)
                make_cube_to(cache_np, 0.54, 0.08, 0.32, steel_band, 0, 0.09, 0)

                c_light = PointLight('chest_glow')
                c_light.setColor((0.45, 0.90, 0.65, 1.0))
                c_light.setAttenuation((1.0, 0.25, 0.08))
                c_light_np = cache_np.attachNewNode(c_light)
                c_light_np.setPos(0, 0, 0.40)
                self.render.setLight(c_light_np)

            self.relic_caches.append({
                "node": cache_np,
                "light_np": c_light_np,
                "pos": (x, y),
                "type": c_type
            })

    def update_quickslot_ui(self):
        """UI에 소비 아이템 퀵슬롯 상태 반영"""
        f_count = self.items["flask"]
        f_max = self.max_items["flask"]
        c_count = self.items["censer"]
        c_max = self.max_items["censer"]
        p_count = self.items["fire_pot"]
        p_max = self.max_items["fire_pot"]

        if self.censer_timer > 0.0:
            censer_str = f"[2] 향로 연소 중 ({self.censer_timer:.1f}s)"
        else:
            censer_str = f"[2] 향로: {c_count}/{c_max}"

        msg = f"[1] 성수: {f_count}/{f_max}  |  {censer_str}  |  [3] 화약병: {p_count}/{p_max}"
        if hasattr(self.ui_mgr, 'update_quickslot'):
            self.ui_mgr.update_quickslot(msg, is_censer_burning=(self.censer_timer > 0.0))

    def reset_state(self, current_stage=1, keep_items=True, spawn_loot=True):
        """스테이지 전환 시 상태 리셋"""
        if not keep_items:
            self.items = {"flask": 1, "censer": 1, "fire_pot": 1}

        self.censer_timer = 0.0
        self.censer_burn_tick = 0.0
        self.render.clearLight(self.censer_light_np)

        for pot in self.active_fire_pots:
            pot.destroy()
        self.active_fire_pots.clear()

        for fire in self.ground_fires:
            if fire.get("light_np") and not fire["light_np"].isEmpty():
                self.render.clearLight(fire["light_np"])
            if fire.get("root") and not fire["root"].isEmpty():
                fire["root"].removeNode()
        self.ground_fires.clear()

        for p in self.fire_particles:
            if not p["node"].isEmpty():
                p["node"].removeNode()
        self.fire_particles.clear()

        if spawn_loot:
            self.setup_stage_loot(current_stage)
        else:
            self.clear_stage_loot()
        self.update_quickslot_ui()
