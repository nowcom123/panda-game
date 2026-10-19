import math
import random
from panda3d.core import Vec3, LColor, PointLight, LineSegs
from geometry import make_cube, make_cube_to
from projectiles import ExplosionVisualEffect


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

        self.parent = parent
        self.beacon_is_lit = False

        # 주변을 은은하게 비추는 엠비언트 비콘 라이트
        self.beacon_light = PointLight("crate_beacon")
        self.beacon_light.setColor((0.15, 0.85, 0.40, 1.0))
        self.beacon_light.setAttenuation((1.0, 0.22, 0.08))
        self.beacon_np = self.node.attachNewNode(self.beacon_light)
        self.beacon_np.setPos(0, 0, 0.6)

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
        if getattr(self, 'beacon_is_lit', False) and hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            if hasattr(self, 'parent') and self.parent and not self.parent.isEmpty():
                self.parent.clearLight(self.beacon_np)
            self.beacon_is_lit = False
        if hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
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
        if getattr(self, 'beacon_is_lit', False) and hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            if hasattr(self, 'parent') and self.parent and not self.parent.isEmpty():
                self.parent.clearLight(self.beacon_np)
            self.beacon_is_lit = False
        if hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            self.beacon_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class TacticalItemDrop:
    """
    몬스터 처치 시 바닥에 확률적으로 드랍되는 3D 필드 전리품 (Loot Drop)
    - 5종 전술 아이템(응급키트, 탄약상자, 아드레날린, 수류탄, 생체자극제) 고유 3D 모델
    - 상하 부유(Floating) 및 360도 회전(Spin) 애니메이션
    - 등급별 고유 네온 발광 포인트라이트 & 수직 라이트 빔 (어두운 복도 시인성 극대화)
    - 플레이어 1.8m 이내 접근 시 자동 습득 (Auto-pickup) 또는 [E] 상호작용
    """
    ITEM_CONFIGS = {
        "ammo_pack": {
            "name": "9mm 예비 탄약 상자",
            "rarity": "COMMON",
            "color": LColor(1.0, 0.85, 0.22, 1.0),
            "light_color": (1.0, 0.85, 0.20, 1.0),
            "weight": 38,
        },
        "medkit": {
            "name": "군용 응급치료 키트",
            "rarity": "RARE",
            "color": LColor(0.25, 0.95, 0.50, 1.0),
            "light_color": (0.20, 0.95, 0.45, 1.0),
            "weight": 26,
        },
        "adrenaline": {
            "name": "전술 아드레날린 주사기",
            "rarity": "EPIC",
            "color": LColor(0.20, 0.85, 1.0, 1.0),
            "light_color": (0.15, 0.80, 1.0, 1.0),
            "weight": 16,
        },
        "frag_grenade": {
            "name": "M67 파열 수류탄 팩",
            "rarity": "UNCOMMON",
            "color": LColor(1.0, 0.45, 0.15, 1.0),
            "light_color": (1.0, 0.40, 0.12, 1.0),
            "weight": 12,
        },
        "combat_stim": {
            "name": "생체 공격 강화제",
            "rarity": "LEGENDARY",
            "color": LColor(0.95, 0.35, 0.95, 1.0),
            "light_color": (0.90, 0.30, 0.95, 1.0),
            "weight": 8,
        }
    }

    def __init__(self, parent, x, y, item_id="ammo_pack", audio_mgr=None):
        self.parent = parent
        self.pos = Vec3(x, y, 0.0)
        self.item_id = item_id
        self.audio_mgr = audio_mgr
        self.cfg = self.ITEM_CONFIGS.get(item_id, self.ITEM_CONFIGS["ammo_pack"])
        self.name = self.cfg["name"]
        self.is_collected = False
        self.is_lit = False
        self.anim_time = random.uniform(0.0, 6.28)

        self.node = parent.attachNewNode(f"drop_{item_id}")
        self.node.setPos(self.pos)

        self.model_root = self.node.attachNewNode("model_root")
        self.model_root.setPos(0, 0, 0.28)

        self._build_geometry()

        # 등급별 네온 발광 포인트라이트
        self.beacon_light = PointLight(f"drop_light_{item_id}")
        self.beacon_light.setColor(self.cfg["light_color"])
        self.beacon_light.setAttenuation((1.0, 0.22, 0.06))
        self.beacon_np = self.node.attachNewNode(self.beacon_light)
        self.beacon_np.setPos(0, 0, 0.35)

    def _build_geometry(self):
        col = self.cfg["color"]
        iid = self.item_id

        if iid == "medkit":
            # 흰색 구급상자 + 붉은 십자가
            make_cube_to(self.model_root, 0.38, 0.26, 0.24, LColor(0.94, 0.94, 0.96, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.20, 0.27, 0.07, LColor(0.95, 0.12, 0.12, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.07, 0.27, 0.20, LColor(0.95, 0.12, 0.12, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.20, 0.07, 0.25, LColor(0.95, 0.12, 0.12, 1.0), 0, 0, 0)
        elif iid == "ammo_pack":
            # 올리브색 탄약통 + 황동 총알
            make_cube_to(self.model_root, 0.38, 0.25, 0.22, LColor(0.20, 0.30, 0.18, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.40, 0.27, 0.05, LColor(0.28, 0.28, 0.32, 1.0), 0, 0, 0.11)
            b1 = make_cube_to(self.model_root, 0.06, 0.06, 0.12, LColor(0.95, 0.85, 0.20, 1.0), -0.09, 0, 0.15)
            b2 = make_cube_to(self.model_root, 0.06, 0.06, 0.12, LColor(0.95, 0.85, 0.20, 1.0), 0.09, 0, 0.15)
            b1.setLightOff()
            b2.setLightOff()
        elif iid == "adrenaline":
            # 시린지 주사기 + 청록색 발광 액체 코어
            make_cube_to(self.model_root, 0.11, 0.11, 0.36, LColor(0.85, 0.90, 0.95, 0.8), 0, 0, 0)
            core = make_cube_to(self.model_root, 0.07, 0.07, 0.26, LColor(0.15, 0.90, 1.0, 1.0), 0, 0, 0)
            core.setLightOff()
            make_cube_to(self.model_root, 0.02, 0.02, 0.14, LColor(0.85, 0.85, 0.88, 1.0), 0, 0, -0.24)
            make_cube_to(self.model_root, 0.14, 0.14, 0.04, LColor(0.3, 0.3, 0.3, 1.0), 0, 0, 0.20)
        elif iid == "frag_grenade":
            # 파열 수류탄 몸통 + 안전핀 레버
            make_cube_to(self.model_root, 0.20, 0.20, 0.26, LColor(0.22, 0.26, 0.18, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.22, 0.10, 0.22, LColor(0.18, 0.22, 0.15, 1.0), 0, 0, 0)
            make_cube_to(self.model_root, 0.08, 0.08, 0.08, LColor(0.7, 0.7, 0.75, 1.0), 0, 0, 0.17)
            make_cube_to(self.model_root, 0.04, 0.10, 0.18, LColor(0.7, 0.7, 0.75, 1.0), 0.07, 0, 0.08)
        else: # combat_stim
            # 자극제 바이알 + 골드 링
            vial = make_cube_to(self.model_root, 0.14, 0.14, 0.36, LColor(0.95, 0.30, 0.95, 1.0), 0, 0, 0)
            vial.setLightOff()
            make_cube_to(self.model_root, 0.16, 0.16, 0.06, LColor(0.90, 0.80, 0.25, 1.0), 0, 0, 0.18)
            make_cube_to(self.model_root, 0.16, 0.16, 0.06, LColor(0.90, 0.80, 0.25, 1.0), 0, 0, -0.18)

        # 수직 발광 비콘 빔 (원거리 시인성 향상)
        ls = LineSegs("item_beacon_beam")
        ls.setColor(col[0], col[1], col[2], 0.95)
        ls.setThickness(2.8)
        ls.moveTo(0, 0, 0.18)
        ls.drawTo(0, 0, 0.75)
        beam = self.model_root.attachNewNode(ls.create())
        beam.setLightOff()

    def update(self, dt, px, py):
        """부유 및 회전 애니메이션, 플레이어 거리 판정"""
        if self.is_collected:
            return "DESTROYED"

        self.anim_time += dt
        self.node.setH((self.anim_time * 65.0) % 360.0)
        self.model_root.setZ(0.28 + math.sin(self.anim_time * 3.2) * 0.07)

        dx = px - self.pos.x
        dy = py - self.pos.y
        dist_sq = dx * dx + dy * dy
        if dist_sq <= 3.24:  # 1.8m ^ 2
            return "COLLECT"
        elif dist_sq <= 6.76:  # 2.6m ^ 2
            return "CAN_INTERACT"
        return "NONE"

    def collect(self, player, combat, ui_mgr):
        """플레이어 아이템 수거 처리"""
        if self.is_collected:
            return
        self.is_collected = True

        # 탄약 상자 수거 시 예비 탄약 +18발 즉시 추가
        if self.item_id == "ammo_pack" and combat:
            combat.reserve_ammo += 18
            combat.update_ammo_ui()

        # 인벤토리 추가
        if player and hasattr(player, 'add_item'):
            player.add_item(self.item_id, 1)

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_ammo_pickup'):
            self.audio_mgr.play_ammo_pickup()

        cfg = self.cfg
        if ui_mgr:
            ui_mgr.show_hit_marker(f"[ ★ {cfg['name']} 획득! ★ ]", (cfg['color'][0], cfg['color'][1], cfg['color'][2], 1.0))
            ui_mgr.show_style_kill(f"[ LOOT: {cfg['name']} ]", "+1 획득", (cfg['color'][0], cfg['color'][1], cfg['color'][2], 1.0))

        self.destroy()

    def destroy(self):
        self.is_collected = True
        if getattr(self, 'is_lit', False) and hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            if hasattr(self, 'parent') and self.parent and not self.parent.isEmpty():
                self.parent.clearLight(self.beacon_np)
            self.is_lit = False
        if hasattr(self, 'beacon_np') and not self.beacon_np.isEmpty():
            self.beacon_np.removeNode()
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


def maybe_drop_monster_loot(parent, mx, my, monster, audio_mgr):
    """몬스터 처치 시 확률에 따라 전술 아이템 드랍 생성 (정예 몬스터는 100% 확정 고급 전리품 드랍)"""
    is_elite = getattr(monster, 'is_elite', False)
    m_name = getattr(monster, '__class__', type(monster)).__name__

    # 몬스터 등급별 드랍 확률
    if is_elite:
        drop_chance = 1.0
    elif "Witch" in m_name:
        drop_chance = 0.75
    elif "MudOrc" in m_name:
        drop_chance = 0.70
    elif "Skeleton" in m_name:
        drop_chance = 0.50
    elif "Serpent" in m_name:
        drop_chance = 0.45
    else:
        drop_chance = 0.50

    if not is_elite and random.random() > drop_chance:
        return None

    # 아이템 가중치 추첨
    configs = TacticalItemDrop.ITEM_CONFIGS
    item_ids = list(configs.keys())
    if is_elite:
        # 정예 변이 괴물은 아드레날린 각성제, 생체 자극제, 응급키트 우선 추첨
        weights = [25, 35, 10, 15, 35]  # medkit, adrenaline, ammo_pack, frag_grenade, combat_stim
    else:
        weights = [configs[iid]["weight"] for iid in item_ids]

    chosen_id = random.choices(item_ids, weights=weights, k=1)[0]
    return TacticalItemDrop(parent, mx, my, item_id=chosen_id, audio_mgr=audio_mgr)

