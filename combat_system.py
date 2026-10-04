"""
Combat System Module - Dark Fantasy Medieval Arbalest & Melee System
기계식 강철 아발레스트(Crossbow), 볼트 장전 및 사격, 우클릭 근접 밀치기(Melee Bash),
시체 볼트 회수, 가죽 화살통 파밍, 절차적 파티클 및 3D 뷰모델
"""

import math
import random
from panda3d.core import (
    PointLight, Spotlight, PerspectiveLens, LineSegs, LColor, Vec3,
    GeomVertexFormat, GeomVertexData, Geom, GeomNode, GeomTriangles, GeomVertexWriter,
    TransparencyAttrib, PNMImage, Texture, CardMaker
)
from constants import (
    CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import cell_has_pillar
from geometry import make_cube_to
from collision import first_world_hit



class CrossbowBolt:
    """
    중세 강철 아발레스트 물리 비행 볼트 (Physical Projectile Bolt)
    - 즉발 레이캐스트가 아닌 68.0 m/s 비행 속도와 중력 낙차를 가진 실체 투사체
    - 포물선 탄도학(Ballistics): 거리에 따라 포물선을 그리며 낙하 (원거리 사격 시 상향 조준 필요)
    - 3D 볼트 모델: 0.40m 오크 샤프트, 흑철 보드킨 촉, 붉은 가죽 깃
    - 몬스터 관통 타격: 둔탁한 관통음 + 치명적 피해 + 몸체에 꽂힘
    - 벽/바닥/천장 착탄: 묵직한 석재 타격음 + 벽에 박힘(Embedded) + 플레이어 접근 시 회수 가능!
    """
    def __init__(self, world_root, spawn_pos, shoot_dir, damage=65.0, player=None):
        self.world_root = world_root
        self.pos = Vec3(spawn_pos)
        self.speed = 68.0
        self.vel = Vec3(shoot_dir * self.speed)
        self.damage = damage
        self.player = player
        self.gravity = -12.5  # 포물선 중력 낙차
        self.is_embedded = False
        self.embedded_timer = 30.0
        self.life = 0.0
        self.max_life = 3.5
        self.is_dead = False
        self.is_recoverable = False

        self.node = world_root.attachNewNode("flying_crossbow_bolt")
        self.node.setPos(self.pos)
        self.node.lookAt(self.pos + self.vel)

        c_wood = LColor(0.38, 0.24, 0.14, 1.0)
        c_steel = LColor(0.85, 0.88, 0.92, 1.0)
        c_fletch = LColor(0.85, 0.12, 0.10, 1.0)

        make_cube_to(self.node, 0.024, 0.40, 0.024, c_wood, 0, 0, 0)
        tip = make_cube_to(self.node, 0.038, 0.10, 0.038, c_steel, 0, 0.22, 0)
        tip.setLightOff()
        f1 = make_cube_to(self.node, 0.055, 0.10, 0.008, c_fletch, 0, -0.16, 0)
        f2 = make_cube_to(self.node, 0.008, 0.10, 0.055, c_fletch, 0, -0.16, 0)
        f1.setLightOff()
        f2.setLightOff()

    def update(self, dt, chunks, monsters, combat_sys):
        if self.is_dead:
            return

        # 1. 벽/바닥에 박힌 상태인 경우
        if self.is_embedded:
            self.embedded_timer -= dt
            if self.embedded_timer <= 0.0:
                self.destroy()
                return

            px, py = combat_sys.camera.getX(), combat_sys.camera.getY()
            if math.hypot(px - self.pos.x, py - self.pos.y) <= 1.85:
                combat_sys.reserve_ammo += 1
                combat_sys.update_ammo_ui()
                combat_sys.audio_mgr.play_bolt_retrieve()
                combat_sys.ui_mgr.show_hit_marker("벽에 박힌 볼트 회수! (+1)", (0.4, 0.9, 1.0, 1.0))
                self.destroy()
            return

        # 2. 비행 중인 상태
        self.life += dt
        if self.life >= self.max_life:
            self.destroy()
            return

        old_pos = Vec3(self.pos)
        self.vel.z += self.gravity * dt
        new_pos = self.pos + self.vel * dt
        flight_vec = new_pos - old_pos
        flight_dist = flight_vec.length()
        if flight_dist < 1e-4:
            return
        flight_dir = flight_vec / flight_dist
        wall_fraction = first_world_hit(chunks, old_pos, new_pos)
        wall_dist = wall_fraction * flight_dist if wall_fraction is not None else math.inf

        # (1) 몬스터 피격 검사 (선분 레이캐스트)
        closest_m = None
        closest_hit_t = 999.0
        if monsters:
            for m in monsters:
                if getattr(m, 'hp', 0) <= 0:
                    continue
                if hasattr(m, 'is_hit_by_ray'):
                    hit, hit_t = m.is_hit_by_ray(old_pos, flight_dir, max_dist=flight_dist)
                    if hit and hit_t < closest_hit_t:
                        closest_hit_t = hit_t
                        closest_m = m

        # 벽과 몬스터가 같은 거리에 있으면 벽이 볼트를 차단합니다.
        if closest_m is not None and closest_hit_t < wall_dist:
            impact_point = old_pos + flight_dir * closest_hit_t
            blackout_active = getattr(combat_sys.base, 'blackout_active', False)
            if self.player and hasattr(self.player, 'get_attack_power'):
                dmg = self.player.get_attack_power(blackout_active=blackout_active)
            else:
                dmg = getattr(self.player, 'attack_power', 65.0) if self.player else 65.0

            # 약점 배율은 몬스터의 take_damage()에서 한 번만 적용합니다.
            is_dead = combat_sys.apply_damage(closest_m, dmg, self.player)
            m_name = getattr(closest_m, 'name', '괴물')
            closest_m.stun(0.45)

            combat_sys.ui_mgr.trigger_crosshair_hit(is_kill=is_dead)
            if self.player and hasattr(self.player, 'trigger_quake_shake'):
                self.player.trigger_quake_shake(intensity=0.65 if is_dead else 0.38, duration=0.09)

            combat_sys.spawn_hit_particles(impact_point, is_blood=True, is_kill=is_dead)

            if hasattr(closest_m, 'pos'):
                push = 0.65 if is_dead else 0.35
                closest_m.pos.x += flight_dir.x * push
                closest_m.pos.y += flight_dir.y * push
                if hasattr(closest_m, 'node') and not closest_m.node.isEmpty():
                    closest_m.node.setX(closest_m.pos.x)
                    closest_m.node.setY(closest_m.pos.y)

            if is_dead:
                if "스토커" in m_name:
                    combat_sys.audio_mgr.play_stalker_shriek()
                combat_sys.audio_mgr.play_kill_hit()
                if random.random() < 0.80:
                    closest_m.recoverable_bolts = getattr(closest_m, 'recoverable_bolts', 0) + 1
                if hasattr(closest_m, 'turn_into_corpse'):
                    closest_m.turn_into_corpse()
            else:
                combat_sys.audio_mgr.play_flesh_hit()
                if hasattr(closest_m, 'node') and not closest_m.node.isEmpty():
                    b_stick = make_cube_to(closest_m.node, 0.024, 0.35, 0.024, LColor(0.85, 0.88, 0.92, 1.0), 0, 0, 0.8)
                    b_stick.setP(random.uniform(25, 60))
                    b_stick.setLightOff()
                    closest_m.embedded_bolt_np = b_stick

            self.destroy()
            return

        # (2) 이번 프레임 이동 구간에서 처음 만난 벽 / 기둥 / 바닥 / 천장
        if wall_fraction is not None:
            hit_wall_pos = old_pos + flight_vec * wall_fraction
            self.pos = hit_wall_pos
            self.node.setPos(self.pos)
            self.node.lookAt(self.pos + flight_dir)
            self.is_embedded = True
            self.is_recoverable = True
            combat_sys.audio_mgr.play_wall_hit()
            combat_sys.spawn_hit_particles(hit_wall_pos, is_blood=False)
            return

        self.pos = new_pos
        self.node.setPos(self.pos)
        self.node.lookAt(self.pos + self.vel)

    def destroy(self):
        self.is_dead = True
        if hasattr(self, 'node') and not self.node.isEmpty():
            self.node.removeNode()


class CombatSystem:
    def apply_damage(self, monster, damage, player=None):
        """피해와 처치 보상을 공통 처리합니다. 새 처치일 때만 True를 반환합니다."""
        if monster.hp <= 0 or getattr(monster, 'is_corpse', False):
            return False
        is_dead = monster.take_damage(damage)
        if is_dead and player is not None and not getattr(monster, '_kill_rewarded', False):
            monster._kill_rewarded = True
            exp_gain = getattr(monster, 'exp_value', 40)
            if getattr(self.base, 'blackout_active', False):
                exp_gain *= 2
            player.gain_exp(exp_gain)
            if "blood_thirst" in player.relics:
                player.heal(12.0)
        return is_dead

    def __init__(self, base, render, camera, world_root, audio_mgr, ui_mgr):
        self.base = base
        self.render = render
        self.camera = camera
        self.world_root = world_root
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 탄약 (볼트) 시스템
        self.max_ammo = 1
        self.ammo = 1
        self.reserve_ammo = 15
        self.reload_duration = 1.25
        self.active_bolts = []
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0

        # 근접 공격 (Melee Bash) 상태
        self.melee_timer = 0.0
        self.is_meleeing = False

        self.active_tracers = []
        self.ammo_drops = []
        self.hit_particles = []

        # 백룸 암전(Blackout) 모드
        self.is_blackout = False
        self.beam_flicker_time = 0.0
        self.mist_particles = []
        self._setup_mist_particles()

        # 뷰모델 생성
        self._setup_viewmodel()

    def _setup_viewmodel(self):
        """1인칭 뷰모델: 정밀 3D 기계식 강철 아발레스트 (Heavy Arbalest)"""
        if hasattr(self, 'vm_root') and self.vm_root:
            self.vm_root.removeNode()

        self.vm_root = self.camera.attachNewNode("viewmodel_root")

        # 손전등 더미 노드 (빛 비활성화)
        self.vm_flashlight = self.vm_root.attachNewNode("vm_flashlight_dummy")
        dummy_spot = Spotlight('player_flashlight_dummy')
        dummy_spot.setColor((0, 0, 0, 0))
        self.pl_np = self.vm_flashlight.attachNewNode(dummy_spot)

        dummy_fill = PointLight('player_fill_dummy')
        dummy_fill.setColor((0, 0, 0, 0))
        self.fill_np = self.vm_flashlight.attachNewNode(dummy_fill)
        self.beam_np = None

        # --- 1인칭 중세 강철 아발레스트 (Crossbow) ---
        self.vm_crossbow = self.vm_root.attachNewNode("vm_crossbow")
        self.vm_crossbow.setPos(0.24, 0.54, -0.25)
        self.vm_crossbow.setHpr(4.0, 13.0, -8.0)

        self.recoil_node = self.vm_crossbow.attachNewNode("recoil_node")

        # 다크 판타지 컬러 팔레트
        oak_wood = LColor(0.28, 0.17, 0.10, 1.0)
        oak_dark = LColor(0.18, 0.11, 0.07, 1.0)
        iron_dark = LColor(0.16, 0.16, 0.18, 1.0)
        iron_metal = LColor(0.35, 0.35, 0.40, 1.0)
        iron_bright = LColor(0.72, 0.74, 0.78, 1.0)
        brass_gold = LColor(0.85, 0.70, 0.25, 1.0)
        feather_red = LColor(0.70, 0.14, 0.12, 1.0)
        bolt_wood = LColor(0.38, 0.26, 0.16, 1.0)

        # 1. 오크 목재 몸체 (Tiller / Stock)
        make_cube_to(self.recoil_node, 0.075, 0.58, 0.08, oak_wood, 0, 0.16, 0)
        grip = make_cube_to(self.recoil_node, 0.068, 0.22, 0.09, oak_dark, 0, -0.16, -0.05)
        grip.setP(20)

        # 2. 전면 강철 하우징 & 철제 보강 밴드 (Iron Reinforcements)
        make_cube_to(self.recoil_node, 0.11, 0.08, 0.095, iron_dark, 0, 0.42, 0.01)
        make_cube_to(self.recoil_node, 0.082, 0.035, 0.088, iron_metal, 0, 0.18, 0.005)
        make_cube_to(self.recoil_node, 0.082, 0.035, 0.088, iron_metal, 0, -0.04, 0.005)
        make_cube_to(self.recoil_node, 0.088, 0.02, 0.03, brass_gold, 0, 0.18, 0.025)
        make_cube_to(self.recoil_node, 0.088, 0.02, 0.03, brass_gold, 0, -0.04, 0.025)

        # 3. 방아쇠 가드 및 강철 레버 (Trigger Assembly)
        make_cube_to(self.recoil_node, 0.025, 0.14, 0.015, iron_dark, 0, -0.08, -0.07)
        make_cube_to(self.recoil_node, 0.018, 0.02, 0.055, iron_bright, 0, -0.06, -0.05)

        # 4. 강철 곡면 활대 (Curved Forged Prods / Limbs)
        l1 = make_cube_to(self.recoil_node, 0.18, 0.042, 0.048, iron_dark, -0.12, 0.42, 0.02)
        l1.setH(16); l1.setR(-6)
        l2 = make_cube_to(self.recoil_node, 0.18, 0.035, 0.042, iron_metal, -0.27, 0.46, 0.035)
        l2.setH(32); l2.setR(-12)
        tip_l = make_cube_to(self.recoil_node, 0.045, 0.055, 0.05, brass_gold, -0.38, 0.50, 0.05)

        r1 = make_cube_to(self.recoil_node, 0.18, 0.042, 0.048, iron_dark, 0.12, 0.42, 0.02)
        r1.setH(-16); r1.setR(6)
        r2 = make_cube_to(self.recoil_node, 0.18, 0.035, 0.042, iron_metal, 0.27, 0.46, 0.035)
        r2.setH(-32); r2.setR(12)
        tip_r = make_cube_to(self.recoil_node, 0.045, 0.055, 0.05, brass_gold, 0.38, 0.50, 0.05)

        # 5. 전면 강철 발걸쇠 / 타격 램 (Stirrup - Melee Spikes)
        make_cube_to(self.recoil_node, 0.024, 0.13, 0.024, iron_dark, -0.06, 0.49, 0.01).setH(22)
        make_cube_to(self.recoil_node, 0.024, 0.13, 0.024, iron_dark, 0.06, 0.49, 0.01).setH(-22)
        make_cube_to(self.recoil_node, 0.15, 0.028, 0.032, iron_bright, 0, 0.57, 0.01)
        make_cube_to(self.recoil_node, 0.035, 0.05, 0.035, iron_bright, 0, 0.60, 0.01, rot_h=45)

        # 6. 화살 안착 레일 (Flight Track) & 황동 래칫 너트
        make_cube_to(self.recoil_node, 0.038, 0.44, 0.018, iron_metal, 0, 0.22, 0.046)
        make_cube_to(self.recoil_node, 0.046, 0.045, 0.042, brass_gold, 0, 0.02, 0.052)
        make_cube_to(self.recoil_node, 0.042, 0.018, 0.035, iron_bright, 0, -0.03, 0.074) # 가늠자
        make_cube_to(self.recoil_node, 0.016, 0.018, 0.030, iron_bright, 0, 0.42, 0.072)  # 가늠쇠

        # 7. 강철 현 (Bowstrings - 당겨진 상태 & 발사 후 전진 상태)
        ls_cocked = LineSegs('bowstring_cocked')
        ls_cocked.setThickness(2.8)
        ls_cocked.setColor(0.85, 0.88, 0.92, 1.0)
        ls_cocked.moveTo(-0.38, 0.50, 0.05)
        ls_cocked.drawTo(0.0, 0.02, 0.052)
        ls_cocked.drawTo(0.38, 0.50, 0.05)
        self.str_cocked = self.recoil_node.attachNewNode(ls_cocked.create())
        self.str_cocked.setLightOff()

        ls_uncocked = LineSegs('bowstring_uncocked')
        ls_uncocked.setThickness(2.8)
        ls_uncocked.setColor(0.85, 0.88, 0.92, 1.0)
        ls_uncocked.moveTo(-0.38, 0.50, 0.05)
        ls_uncocked.drawTo(0.0, 0.44, 0.05)
        ls_uncocked.drawTo(0.38, 0.50, 0.05)
        self.str_uncocked = self.recoil_node.attachNewNode(ls_uncocked.create())
        self.str_uncocked.setLightOff()
        self.str_uncocked.hide()

        # 8. 장전된 강철 볼트 (Loaded Quarrel)
        self.bolt_node = self.recoil_node.attachNewNode('loaded_bolt')
        make_cube_to(self.bolt_node, 0.020, 0.35, 0.020, bolt_wood, 0, 0.23, 0.058)
        head = make_cube_to(self.bolt_node, 0.040, 0.08, 0.026, iron_bright, 0, 0.42, 0.058)
        head.setLightOff()
        make_cube_to(self.bolt_node, 0.045, 0.075, 0.009, feather_red, 0, 0.08, 0.062)
        make_cube_to(self.bolt_node, 0.009, 0.075, 0.045, feather_red, 0, 0.08, 0.062)

        # 사격 시 미세 운동 마찰 스파크 노드
                # 머즐 플래시 완전 삭제 (더미 노드만 유지하여 호환성 보장)
        self.muzzle_flash_geom = self.recoil_node.attachNewNode("dummy_flash")
        self.muzzle_light = PointLight('dummy_light')
        self.muzzle_light_np = self.recoil_node.attachNewNode(self.muzzle_light)

    def shoot(self, monsters, player=None, game_state="PLAYING"):
        """중세 강철 아발레스트 단발 물리 볼트 발사 (탄도학 & 물리 투사체)"""
        if game_state != "PLAYING" or self.is_reloading or self.shoot_cooldown > 0.0 or self.melee_timer > 0.0:
            return

        if self.ammo <= 0:
            if self.reserve_ammo > 0:
                self.reload(game_state)
            else:
                self.ui_mgr.show_hit_marker("화살이 다 떨어졌습니다! (시체 또는 벽의 볼트를 회수하세요)", (1.0, 0.3, 0.3, 1.0))
                self.hit_marker_timer = 1.8
                self.shoot_cooldown = 0.35
            return

        # 1발 발사
        self.ammo = 0
        self.shoot_cooldown = 0.55
        self.recoil_timer = 0.22

        # 강철 활줄 탄성 해제 및 장전된 볼트 감춤
        if hasattr(self, 'bolt_node') and self.bolt_node:
            self.bolt_node.hide()
        if hasattr(self, 'str_cocked') and self.str_cocked:
            self.str_cocked.hide()
        if hasattr(self, 'str_uncocked') and self.str_uncocked:
            self.str_uncocked.show()

        # 중세 강철 활줄 튕김 사운드
        self.audio_mgr.play_crossbow_shoot()
        self.update_ammo_ui()

        # 발사 시 묵직한 반동
        if player and hasattr(player, 'trigger_quake_shake'):
            player.trigger_quake_shake(intensity=0.35, duration=0.08)

        # 물리 볼트 생성 (포탄 궤적 및 탄도학)
        cam_pos = self.camera.getPos()
        cam_quat = self.camera.getQuat()
        cam_fwd = cam_quat.getForward()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()

        muzzle_world = cam_pos + cam_fwd * 0.72 + cam_right * 0.22 - cam_up * 0.16
        bolt = CrossbowBolt(self.world_root, muzzle_world, cam_fwd, damage=65.0, player=player)
        self.active_bolts.append(bolt)

    def melee_bash(self, monsters, player=None, game_state="PLAYING"):
        """마우스 우클릭: 강철 쇠뇌 발걸쇠로 전방 강타 및 밀치기 (Melee Bash)"""
        if game_state != "PLAYING" or self.melee_timer > 0.0 or self.is_reloading:
            return False
        if player is not None and not player.consume_stamina(18.0):
            self.ui_mgr.show_hit_marker("스태미나 부족! (근접 밀치기 불가)", (1.0, 0.4, 0.4, 1.0))
            return False

        self.melee_timer = 0.38
        self.is_meleeing = True

        cam_pos = self.camera.getPos()
        cam_fwd = self.camera.getQuat().getForward()

        hit_any = False
        monster_list = monsters if isinstance(monsters, (list, tuple)) else [monsters]

        for m in monster_list:
            if getattr(m, 'hp', 1) <= 0:
                continue
            mx, my = m.pos.x, m.pos.y
            dx = mx - cam_pos.x
            dy = my - cam_pos.y
            dist = math.hypot(dx, dy)

            if dist <= 2.3:
                # 전방 65도 원추각 판정
                dir_x = dx / (dist + 1e-5)
                dir_y = dy / (dist + 1e-5)
                dot = dir_x * cam_fwd.x + dir_y * cam_fwd.y

                if dot > 0.45:
                    hit_any = True
                    dmg = 28.0
                    if player and hasattr(player, 'get_attack_power'):
                        dmg = max(24.0, player.get_attack_power() * 0.75)

                    is_dead = self.apply_damage(m, dmg, player)
                    is_stalker = hasattr(m, 'heart_exposed') or ("스토커" in getattr(m, 'name', ''))
                    stun_dur = 1.35 if is_stalker else 0.85
                    push_dist = 2.20 if is_stalker else 1.30
                    m.stun(stun_dur)
                    m.pos.x += cam_fwd.x * push_dist
                    m.pos.y += cam_fwd.y * push_dist
                    if hasattr(m, 'node') and not m.node.isEmpty():
                        m.node.setX(m.pos.x)
                        m.node.setY(m.pos.y)

                    hit_pos = Vec3(mx, my, 1.0)
                    self.spawn_hit_particles(hit_pos, is_blood=True, is_kill=is_dead)
                    self.ui_mgr.trigger_crosshair_hit(is_kill=is_dead)
                    if is_stalker:
                        self.ui_mgr.show_hit_marker("스토커 강타! 공허의 심장이 노출되었습니다! (2.5배 치명타)", (1.0, 0.35, 1.0, 1.0))
                    else:
                        self.ui_mgr.show_hit_marker("강타! 괴물이 비틀거립니다!", (1.0, 0.7, 0.25, 1.0))
                    self.hit_marker_timer = 1.4

                    if is_dead:
                        self.audio_mgr.play_kill_hit()
                        if hasattr(m, 'turn_into_corpse'):
                            m.turn_into_corpse()
                    else:
                        self.audio_mgr.play_melee_hit()

        if hit_any:
            if player and hasattr(player, 'trigger_quake_shake'):
                player.trigger_quake_shake(intensity=0.60, duration=0.12)
        else:
            self.audio_mgr.play_melee_swing()
            if player and hasattr(player, 'trigger_quake_shake'):
                player.trigger_quake_shake(intensity=0.30, duration=0.06)
        return True

    def spawn_hit_particles(self, hit_pos, is_blood=True, is_kill=False):
        """선혈 및 화살 파편 파티클"""
        count = 28 if (is_blood and is_kill) else (20 if is_blood else 14)
        for _ in range(count):
            p_node = self.world_root.attachNewNode("hit_particle")
            p_node.setPos(hit_pos)
            if is_blood:
                r = random.uniform(0.18, 0.36)
                g = random.uniform(0.015, 0.035)
                b = random.uniform(0.015, 0.040)
                col = LColor(r, g, b, 0.95)
                size = random.uniform(0.06, 0.12) if is_kill else random.uniform(0.05, 0.09)
                cube = make_cube_to(p_node, size, size, size, col, 0, 0, 0)
                cube.setLightOff()

                vx = random.uniform(-4.5, 4.5)
                vy = random.uniform(-4.5, 4.5)
                vz = random.uniform(1.8, 5.5)
                timer = random.uniform(0.35, 0.55)
            else:
                c = random.uniform(0.70, 0.90)
                col = LColor(c, c * 0.92, c * 0.80, 1.0)
                size = random.uniform(0.04, 0.08)
                cube = make_cube_to(p_node, size, size, size, col, 0, 0, 0)
                cube.setLightOff()

                vx = random.uniform(-3.5, 3.5)
                vy = random.uniform(-3.5, 3.5)
                vz = random.uniform(1.5, 4.2)
                timer = random.uniform(0.25, 0.40)

            self.hit_particles.append({
                "node": p_node,
                "pos": Vec3(hit_pos),
                "vel": Vec3(vx, vy, vz),
                "timer": timer
            })

    def apply_upgrade(self, upgrade_type):
        """볼트 가방 강화"""
        if upgrade_type == "AMMO":
            self.max_ammo += 4
            self.ammo = self.max_ammo
            self.reserve_ammo += 24
            self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)
            self.ui_mgr.show_hit_marker("[특성 강화] 최대 볼트 +4발 및 예비 볼트 +24발 획득!", (1.0, 0.85, 0.2, 1.0))

    def reload(self, game_state="PLAYING"):
        """[R] 키 중세 아발레스트 장전 (윈들래스/지렛대 활줄 당김 및 볼트 거치)"""
        if game_state != "PLAYING" or self.is_reloading or self.ammo >= self.max_ammo or self.melee_timer > 0.0:
            return
        if self.reserve_ammo <= 0:
            self.ui_mgr.show_hit_marker("화살통이 비었습니다! (시체 또는 벽에서 볼트를 회수하세요)", (1.0, 0.3, 0.3, 1.0))
            self.hit_marker_timer = 1.8
            return

        self.is_reloading = True
        self.reload_timer = getattr(self, 'reload_duration', 1.25)
        self.audio_mgr.play_crossbow_reload()
        self.ui_mgr.show_hit_marker("볼트 장전 중...", (0.9, 0.9, 0.9, 1.0))
        self.hit_marker_timer = self.reload_timer

    def clear_ammo_drops(self):
        """보급품과 등록된 광원을 해제합니다."""
        for d in self.ammo_drops:
            if d.get("light_np") and not d["light_np"].isEmpty():
                self.render.clearLight(d["light_np"])
            if d.get("node") and not d["node"].isEmpty():
                d["node"].removeNode()
        self.ammo_drops = []

    def setup_ammo_drops(self, current_stage=1):
        """던전 가죽 화살통 & 무기 궤짝 배치"""
        self.clear_ammo_drops()
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
                    if d >= 18.0:
                        candidates.append((cx, cy))

        if not candidates:
            return

        drop_count = min(6, len(candidates))
        chosen_positions = random.sample(candidates, drop_count)

        chest_wood = LColor(0.24, 0.15, 0.09, 1.0)
        iron_metal = LColor(0.32, 0.32, 0.36, 1.0)
        quiver_leather = LColor(0.42, 0.26, 0.15, 1.0)
        arrow_fletch = LColor(0.70, 0.15, 0.12, 1.0)

        for x, y in chosen_positions:
            drop_np = self.world_root.attachNewNode("quiver_chest")
            drop_np.setPos(x, y, 0.18)

            # 오크 궤짝 본체 및 철제 보강 띠
            make_cube_to(drop_np, 0.48, 0.32, 0.26, chest_wood, 0, 0, 0)
            make_cube_to(drop_np, 0.50, 0.06, 0.28, iron_metal, 0, -0.09, 0)
            make_cube_to(drop_np, 0.50, 0.06, 0.28, iron_metal, 0, 0.09, 0)
            # 가죽 화살통 및 볼트 깃
            make_cube_to(drop_np, 0.16, 0.16, 0.32, quiver_leather, 0.12, 0, 0.12).setP(15)
            f1 = make_cube_to(drop_np, 0.04, 0.04, 0.18, arrow_fletch, 0.12, 0, 0.28)
            f1.setP(15); f1.setLightOff()

            drop_light = PointLight('quiver_glow')
            drop_light.setColor((0.85, 0.65, 0.20, 1.0))
            drop_light.setAttenuation((1.0, 0.15, 0.04))
            drop_light_np = drop_np.attachNewNode(drop_light)
            drop_light_np.setPos(0, 0, 0.35)
            self.render.setLight(drop_light_np)

            self.ammo_drops.append({
                "node": drop_np,
                "light_np": drop_light_np,
                "pos": (x, y)
            })

    def reset_state(self, current_stage=1, keep_ammo=False, spawn_drops=True):
        """상태 초기화"""
        if not keep_ammo:
            self.max_ammo = 1
            self.ammo = 1
            self.reserve_ammo = 15
            self.reload_duration = 1.25
        if hasattr(self, 'active_bolts'):
            for b in self.active_bolts:
                b.destroy()
            self.active_bolts.clear()
        self.is_reloading = False
        self.reload_timer = 0.0
        self.shoot_cooldown = 0.0
        self.recoil_timer = 0.0
        self.muzzle_timer = 0.0
        self.melee_timer = 0.0
        self.is_meleeing = False
        self.hit_marker_timer = 0.0
        self.bobbing_time = 0.0
        self.recoil_node.setPosHpr(0, 0, 0, 0, 0, 0)
        self.vm_root.setPos(0, 0, 0)
        self.muzzle_flash_geom.hide()
        self.render.clearLight(self.muzzle_light_np)

        for tr in self.active_tracers:
            if tr.get("np") and not tr["np"].isEmpty():
                tr["np"].removeNode()
        self.active_tracers = []

        for p in self.hit_particles:
            if not p["node"].isEmpty():
                p["node"].removeNode()
        self.hit_particles.clear()

        # 볼트 및 현 기본 상태 복원
        if hasattr(self, 'bolt_node') and self.bolt_node:
            self.bolt_node.show()
        if hasattr(self, 'str_cocked') and self.str_cocked:
            self.str_cocked.show()
        if hasattr(self, 'str_uncocked') and self.str_uncocked:
            self.str_uncocked.hide()

        if spawn_drops:
            self.setup_ammo_drops(current_stage)
        else:
            self.clear_ammo_drops()
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

    def update_ammo_ui(self):
        """UI 실시간 갱신"""
        self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

    _update_ammo_ui = update_ammo_ui

    def update(self, dt, px, py, is_moving, is_sprinting, chunks=None, monsters=None, player=None):
        """전투 시스템 애니메이션 및 물리 탄도 업데이트"""
        # 물리 볼트 업데이트 (탄도학 궤적, 벽 박힘/회수, 몬스터 관통 타격)
        if hasattr(self, 'active_bolts'):
            for b in self.active_bolts[:]:
                b.update(dt, chunks, monsters, self)
                if b.is_dead:
                    self.active_bolts.remove(b)

        """매 프레임 애니메이션 및 루팅 처리"""
        # 볼트 비행 궤적 수명 관리
        for tr in self.active_tracers[:]:
            tr["life"] -= dt
            if tr["life"] <= 0.0:
                tr["np"].removeNode()
                self.active_tracers.remove(tr)

        # 타격 파티클 수명 및 물리 연산
        for p in self.hit_particles[:]:
            p["timer"] -= dt
            p["vel"].z -= 13.0 * dt
            p["pos"] += p["vel"] * dt
            if p["pos"].z <= 0.025:
                p["pos"].z = 0.025
                p["vel"].x *= 0.35
                p["vel"].y *= 0.35
                p["vel"].z = 0.0
            p["node"].setPos(p["pos"])
            scale = max(0.1, p["timer"] / 0.38)
            p["node"].setScale(scale)
            if p["timer"] <= 0.0:
                if not p["node"].isEmpty():
                    p["node"].removeNode()
                self.hit_particles.remove(p)

        # 사격 쿨다운
        if self.shoot_cooldown > 0.0:
            self.shoot_cooldown = max(0.0, self.shoot_cooldown - dt)

        if self.muzzle_timer > 0.0:
            self.muzzle_timer -= dt
            if self.muzzle_timer <= 0.0:
                self.muzzle_flash_geom.hide()
                self.render.clearLight(self.muzzle_light_np)

        # 근접 공격 (우클릭 밀치기) 애니메이션
        if self.melee_timer > 0.0:
            self.melee_timer -= dt
            t_norm = max(0.0, self.melee_timer / 0.38)
            thrust = math.sin(t_norm * math.pi)
            self.recoil_node.setPos(0, 0.28 * thrust, -0.05 * thrust)
            self.recoil_node.setP(14.0 * thrust)
            self.recoil_node.setR(16.0 * thrust)
            if self.melee_timer <= 0.0:
                self.is_meleeing = False
                self.recoil_node.setPos(0, 0, 0)
                self.recoil_node.setP(0)
                self.recoil_node.setR(0)

        # 재장전 애니메이션 (권선 및 볼트 삽입 단계별 연출)
        elif self.is_reloading:
            self.reload_timer -= dt
            t_rel = max(0.0, self.reload_timer / 1.30)
            tilt = math.sin(t_rel * math.pi)
            self.recoil_node.setPos(0, -0.06 * tilt, -0.10 * tilt)
            self.recoil_node.setP(-24.0 * tilt)

            # 장전 중간 시점: 현 당김
            if self.reload_timer <= 0.70 and self.str_cocked.isHidden():
                self.str_uncocked.hide()
                self.str_cocked.show()

            # 장전 후반 시점: 볼트 거치
            if self.reload_timer <= 0.35 and self.bolt_node.isHidden():
                self.bolt_node.show()

            if self.reload_timer <= 0.0:
                self.is_reloading = False
                self.recoil_node.setPos(0, 0, 0)
                self.recoil_node.setP(0)
                if self.reserve_ammo > 0:
                    self.ammo = 1
                    self.reserve_ammo -= 1
                    self.update_ammo_ui()
                    self.ui_mgr.show_hit_marker("장전 완료! (1/1)", (0.35, 1.0, 0.5, 1.0))
                self.hit_marker_timer = 1.2

        # 사격 반동 애니메이션
        elif self.recoil_timer > 0.0:
            self.recoil_timer -= dt
            t_norm = max(0.0, self.recoil_timer / 0.16)
            snap = math.sin(t_norm * math.pi * 0.5) ** 0.8
            self.recoil_node.setPos(0, -0.07 * snap, 0.025 * snap)
            self.recoil_node.setP(10.0 * snap)
            self.recoil_node.setR(-2.0 * snap)
        else:
            self.recoil_node.setPos(0, 0, 0)
            self.recoil_node.setP(0)
            self.recoil_node.setR(0)

        # 히트마커 타이머
        if self.hit_marker_timer > 0.0:
            self.hit_marker_timer -= dt
            if self.hit_marker_timer <= 0.0:
                self.ui_mgr.show_hit_marker("")

        # 화살통 파밍 루팅 (반경 1.8m 이내)
        if self.ammo_drops:
            for drop in self.ammo_drops[:]:
                dx = px - drop["pos"][0]
                dy = py - drop["pos"][1]
                if math.hypot(dx, dy) <= 1.8:
                    self.reserve_ammo += 10
                    self.ui_mgr.show_hit_marker("화살통 획득! (+10 강철 볼트)", (0.35, 1.0, 0.5, 1.0))
                    self.hit_marker_timer = 2.0
                    self.audio_mgr.play_bolt_retrieve()
                    if "light_np" in drop and drop["light_np"] and not drop["light_np"].isEmpty():
                        self.render.clearLight(drop["light_np"])
                    if "node" in drop and drop["node"] and not drop["node"].isEmpty():
                        drop["node"].removeNode()
                    self.ammo_drops.remove(drop)
                    self.ui_mgr.update_ammo(self.ammo, self.max_ammo, self.reserve_ammo)

        # 걷기/질주 밥빙(Bobbing)
        if is_moving:
            self.bobbing_time += dt * (14.0 if is_sprinting else 8.5)
            bob_x = math.sin(self.bobbing_time * 0.5) * 0.012
            bob_y = abs(math.cos(self.bobbing_time)) * 0.014
            self.vm_root.setPos(bob_x, 0, -bob_y)
        else:
            self.bobbing_time += dt * 2.0
            sway_z = math.sin(self.bobbing_time) * 0.003
            self.vm_root.setPos(0, 0, sway_z)

        self._update_flashlight_beam(dt)
        self._update_mist_particles(dt, px, py)

    def _setup_flashlight_beam(self):
        self.beam_np = None

    def _setup_mist_particles(self):
        self.mist_particles = []
        self.mist_root = None

    def _update_flashlight_beam(self, dt):
        pass

    def _update_mist_particles(self, dt, px, py):
        pass

    def set_blackout_mode(self, is_active: bool):
        self.is_blackout = is_active
