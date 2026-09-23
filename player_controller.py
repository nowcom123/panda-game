"""
Player Controller Module
마우스 시선 제어(FPS Heading/Pitch), 8방향 키보드 이동,
스테미나 시스템(전력질주/탈진/회복), 발자국 사운드 연동 및 벽 충돌 슬라이딩
"""

import math
from panda3d.core import WindowProperties, Vec3, KeyboardButton
from constants import (
    PLAYER_RADIUS, PLAYER_EYE_HEIGHT, WALK_SPEED, SPRINT_SPEED
)
from collision import resolve_collision


class PlayerController:
    def __init__(self, base, win, camera, mouse_watcher, audio_mgr, ui_mgr):
        self.base = base
        self.win = win
        self.camera = camera
        self.mouse_watcher = mouse_watcher
        self.audio_mgr = audio_mgr
        self.ui_mgr = ui_mgr

        # 시선 회전각
        self.heading = 0.0
        self.pitch = 0.0
        self.mouse_locked = False

        # 스테미나
        self.max_stamina = 100.0
        self.stamina = self.max_stamina
        self.is_sprinting = False
        self.stamina_exhausted = False

        # 던전 크롤러 RPG 스탯
        self.level = 1
        self.exp = 0
        self.exp_to_next = 100
        self.max_hp = 100.0
        self.hp = self.max_hp
        self.attack_power = 35.0
        self.speed_mult = 1.0
        self.invincible_timer = 0.0
        self.stat_points = 0  # 레벨업 시 획득하여 스테이지 클리어 상점에서 분배하는 포인트
        self.relics = []      # 보유한 저주받은 유물 ID 목록
        self.hp_drain_accum = 0.0

        # 진흙 괴물 땅울림 이동 방해(슬로우) 및 지진 흔들림 상태
        self.slow_timer = 0.0
        self.slow_factor = 1.0
        self.shake_timer = 0.0
        self.shake_intensity = 0.0

        # 이동 및 발자국
        self.last_move_dir = Vec3(0, 0, 0)
        self.footstep_timer = 0.0

        # 키보드 입력 상태
        self.key_map = {
            "w": 0, "s": 0, "a": 0, "d": 0,
            "shift": 0
        }

    def setup_input(self, on_shoot, on_reload):
        """키보드 및 마우스 조작 이벤트 등록"""
        self.base.disableMouse()
        self.lock_mouse(True)

        # WASD 8방향 이동 키
        for key in ["w", "a", "s", "d"]:
            self.base.accept(key, self._set_key, [key, 1])
            self.base.accept(f"{key}-up", self._set_key, [key, 0])
            self.base.accept(f"shift-{key}", self._set_key, [key, 1])
            self.base.accept(f"shift-{key}-up", self._set_key, [key, 0])
            self.base.accept(key.upper(), self._set_key, [key, 1])
            self.base.accept(f"{key.upper()}-up", self._set_key, [key, 0])

        # 화살표 키 (대체 키)
        arrow_mappings = {
            "arrow_up": "w",
            "arrow_down": "s",
            "arrow_left": "a",
            "arrow_right": "d"
        }
        for arrow, target in arrow_mappings.items():
            self.base.accept(arrow, self._set_key, [target, 1])
            self.base.accept(f"{arrow}-up", self._set_key, [target, 0])
            self.base.accept(f"shift-{arrow}", self._set_key, [target, 1])
            self.base.accept(f"shift-{arrow}-up", self._set_key, [target, 0])

        # Shift 달리기
        for s_key in ["shift", "lshift", "rshift"]:
            self.base.accept(s_key, self._set_key, ["shift", 1])
            self.base.accept(f"{s_key}-up", self._set_key, ["shift", 0])

        # 마우스 좌클릭 사격
        self.base.accept("mouse1", on_shoot)

        # R 키 재장전
        self.base.accept("r", on_reload)
        self.base.accept("shift-r", on_reload)
        self.base.accept("R", on_reload)

        # ESC 마우스 커서 해제/잠금 토글
        self.base.accept("escape", self.toggle_mouse_lock)

    def _set_key(self, key, state):
        self.key_map[key] = state

    def lock_mouse(self, lock):
        self.mouse_locked = lock
        props = WindowProperties()
        props.setCursorHidden(lock)
        props.setMouseMode(WindowProperties.M_confined if lock else WindowProperties.M_absolute)
        if hasattr(self.win, 'requestProperties'):
            self.win.requestProperties(props)

    def toggle_mouse_lock(self):
        self.lock_mouse(not self.mouse_locked)

    def gain_exp(self, amount):
        """경험치 획득 및 레벨업 판정 (레벨업 시 스탯 포인트 획득, 전투 중 즉시 스탯 증가는 하지 않음)"""
        self.exp += amount
        leveled = False
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            self.exp_to_next = int(self.exp_to_next * 1.5)
            self.stat_points += 3  # 레벨업마다 3 스탯 포인트 지급
            leveled = True
            # 레벨업 UI 텍스트 완전 제거 (조용히 EXP 바 및 스탯 포인트로만 반영)
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)
        return leveled

    def get_attack_power(self, blackout_active=False):
        """저주받은 유물 효과가 반영된 최종 공격력 산출"""
        dmg = self.attack_power
        if "glass_cannon" in self.relics:
            dmg *= 1.80  # 공격력 +80%
        if "abyssal_reaper" in self.relics and blackout_active:
            dmg *= 2.50  # 정전 중 공격력 2.5배
        return dmg

    def take_damage(self, amount):
        """몬스터 공격 피격 시 체력 감소 및 시각 피격 효과 (화면 붉은 플래시, 카메라 충격 흔들림)"""
        if self.invincible_timer > 0.0:
            return False
        # 유리의 총열 유물: 받는 피해 +40%
        if "glass_cannon" in self.relics:
            amount *= 1.40
        self.hp = max(0.0, self.hp - amount)
        self.invincible_timer = 0.55  # 0.55초 무적 쿨다운
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)

        # 플레이어 피격 시각 효과: 화면 붉은 플래시 및 카메라 충격 흔들림
        self.ui_mgr.trigger_player_damage_flash(intensity=0.65)
        self.trigger_quake_shake(intensity=1.8, duration=0.35)
        self.audio_mgr.play_skeleton_hit()

        return self.hp <= 0.0

    def heal(self, amount):
        self.hp = min(self.max_hp, self.hp + amount)
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)

    def acquire_relic(self, relic_id):
        """저주받은 유물 획득 및 지속 스탯/특수 효과 적용"""
        if relic_id in self.relics:
            return
        self.relics.append(relic_id)
        if relic_id == "iron_colossus":
            self.max_hp += 60.0
            self.hp = min(self.max_hp, self.hp + 60.0)
            self.speed_mult *= 0.85
        elif relic_id == "blood_thirst":
            self.max_hp = max(35.0, self.max_hp - 25.0)
            self.hp = min(self.hp, self.max_hp)
        elif relic_id == "frenzy_drive":
            self.speed_mult *= 1.30

        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)
        if hasattr(self.ui_mgr, 'update_relic_badges'):
            self.ui_mgr.update_relic_badges(self.relics)

    def allocate_stat(self, stat_type, combat_system=None):
        """스테이지 클리어 시 스탯 포인트 1개 소모하여 원하는 능력치 분배"""
        if self.stat_points <= 0:
            return False, "스탯 포인트가 부족합니다!"

        self.stat_points -= 1
        msg = ""
        if stat_type == "ATK":
            self.attack_power += 5.0
            msg = f"[공격력 +5] 현재 공격력: {int(self.attack_power)}"
        elif stat_type == "HP":
            self.max_hp += 25.0
            self.hp = min(self.max_hp, self.hp + 25.0)
            msg = f"[최대 체력 +25] 현재 최대 체력: {int(self.max_hp)}"
        elif stat_type == "SPD":
            self.speed_mult += 0.08
            self.max_stamina += 15.0
            self.stamina = self.max_stamina
            msg = f"[이동 속도 +8%] 현재 속도 배율: {int(self.speed_mult * 100)}%"
        elif stat_type == "AMMO":
            if combat_system:
                combat_system.max_ammo += 2
                combat_system.reserve_ammo += 12
                combat_system.ammo = min(combat_system.max_ammo, combat_system.ammo + 2)
                if hasattr(combat_system, 'ui_mgr'):
                    combat_system.ui_mgr.update_ammo(combat_system.ammo, combat_system.max_ammo, combat_system.reserve_ammo)
            msg = f"[최대 탄약 +2] 현재 탄창: {combat_system.max_ammo if combat_system else '증가'}"

        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)
        return True, msg

    def apply_slow(self, duration=2.8, factor=0.40):
        """진흙 괴물 땅울림으로 인한 지면 균열 이동 방해(슬로우) 부여"""
        self.slow_timer = duration
        self.slow_factor = factor

    def trigger_quake_shake(self, intensity=2.5, duration=0.85):
        """지면 충격 및 지진 카메라 흔들림"""
        self.shake_timer = duration
        self.shake_intensity = intensity

    def apply_upgrade(self, upgrade_type):
        """스테이지 클리어 상점 특성 적용"""
        if upgrade_type == "ATTACK":
            self.attack_power = int(self.attack_power * 1.35)
        elif upgrade_type == "HEALTH":
            self.max_hp += 40.0
            self.hp = self.max_hp
        elif upgrade_type == "SPEED":
            self.speed_mult += 0.20
            self.max_stamina += 30.0
            self.stamina = self.max_stamina
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)

    def reset_position(self, x, y, z=PLAYER_EYE_HEIGHT, heading=0.0, pitch=0.0):
        """플레이어 위치 및 시선 초기화"""
        self.heading = heading
        self.pitch = pitch
        self.camera.setPos(x, y, z)
        self.camera.setHpr(heading, pitch, 0)
        self.stamina = self.max_stamina
        self.stamina_exhausted = False
        self.is_sprinting = False
        self.footstep_timer = 0.0
        self.invincible_timer = 0.0
        self.slow_timer = 0.0
        self.slow_factor = 1.0
        self.shake_timer = 0.0
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level)

    def update(self, dt, chunks):
        """마우스 시선 제어, 8방향 이동 및 충돌 슬라이딩 처리"""
        if self.invincible_timer > 0.0:
            self.invincible_timer = max(0.0, self.invincible_timer - dt)

        view_changed = False

        # 1. 마우스 시선 제어
        if self.mouse_locked and self.mouse_watcher and self.mouse_watcher.hasMouse():
            md = self.win.getPointer(0)
            center_x, center_y = self.win.getXSize() // 2, self.win.getYSize() // 2

            delta_x = md.getX() - center_x
            delta_y = md.getY() - center_y

            if delta_x != 0 or delta_y != 0:
                mouse_sens = 0.13
                self.heading -= delta_x * mouse_sens
                self.pitch -= delta_y * mouse_sens
                self.pitch = max(-89.0, min(89.0, self.pitch))

                self.camera.setHpr(self.heading, self.pitch, 0)
                self.win.movePointer(0, center_x, center_y)
                view_changed = True

        # 땅울림 카메라 진동 처리
        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)
            shake_p = math.sin(self.shake_timer * 40.0) * self.shake_intensity
            shake_r = math.cos(self.shake_timer * 32.0) * (self.shake_intensity * 0.6)
            self.camera.setHpr(self.heading, self.pitch + shake_p, shake_r)
        elif view_changed:
            self.camera.setHpr(self.heading, self.pitch, 0)

        # 땅울림 슬로우(이동 방해) 처리 (철갑의 거인 유물 보유 시 슬로우 완전 면역)
        if "iron_colossus" in self.relics:
            cur_slow = 1.0
        elif self.slow_timer > 0.0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            cur_slow = self.slow_factor
        else:
            cur_slow = 1.0

        # 광기의 가속 유물: 초당 체력 0.40 소모 (최소 1HP 유지)
        if "frenzy_drive" in self.relics and self.hp > 1.0:
            self.hp = max(1.0, self.hp - 0.40 * dt)
            self.hp_drain_accum += dt
            if self.hp_drain_accum >= 0.25:
                self.hp_drain_accum = 0.0
                self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, self.stat_points)

        # 2. 키보드 입력 상태 감지
        base_mouse_watcher = self.mouse_watcher
        shift_held = bool(self.key_map["shift"])
        if base_mouse_watcher:
            shift_held = shift_held or (
                base_mouse_watcher.isButtonDown(KeyboardButton.shift()) or
                base_mouse_watcher.isButtonDown(KeyboardButton.lshift()) or
                base_mouse_watcher.isButtonDown(KeyboardButton.rshift())
            )

        w_held = bool(self.key_map["w"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("w")))
        s_held = bool(self.key_map["s"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("s")))
        a_held = bool(self.key_map["a"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("a")))
        d_held = bool(self.key_map["d"]) or (base_mouse_watcher and base_mouse_watcher.isButtonDown(KeyboardButton.ascii_key("d")))

        move_dir = Vec3(0, 0, 0)
        heading_rad = math.radians(self.heading)
        forward = Vec3(-math.sin(heading_rad), math.cos(heading_rad), 0)
        right = Vec3(math.cos(heading_rad), math.sin(heading_rad), 0)

        is_moving = False
        if w_held:
            move_dir += forward
            is_moving = True
        if s_held:
            move_dir -= forward
            is_moving = True
        if a_held:
            move_dir -= right
            is_moving = True
        if d_held:
            move_dir += right
            is_moving = True

        # 3. 스테미나 관리
        wants_to_sprint = shift_held and is_moving and (cur_slow >= 0.9)  # 땅울림 충격 시 달리기 불가
        if self.stamina_exhausted:
            if self.stamina >= 25.0:
                self.stamina_exhausted = False
            self.is_sprinting = False
        else:
            self.is_sprinting = wants_to_sprint and (self.stamina > 0.0)

        if self.is_sprinting:
            self.stamina -= 22.0 * dt  # 약 4.5초 전력질주 가능
            if self.stamina <= 0.0:
                self.stamina = 0.0
                self.stamina_exhausted = True
                self.is_sprinting = False
        else:
            recovery_rate = 14.0 if not is_moving else 8.0
            self.stamina = min(self.max_stamina, self.stamina + recovery_rate * dt)

        self.ui_mgr.update_stamina(self.stamina, self.max_stamina, self.is_sprinting, self.stamina_exhausted)

        # 4. 이동 및 정밀 충돌 슬라이딩 (스피드 승수 & 슬로우 감속 적용)
        if is_moving:
            move_dir.normalize()
            self.last_move_dir = move_dir
            base_speed = SPRINT_SPEED if self.is_sprinting else WALK_SPEED
            speed = base_speed * self.speed_mult * cur_slow
            disp = move_dir * speed * dt

            # 발자국 소리 주기
            step_interval = (0.26 if self.is_sprinting else 0.42) / max(1.0, self.speed_mult)
            self.footstep_timer += dt
            if self.footstep_timer >= step_interval:
                self.footstep_timer = 0.0
                self.audio_mgr.play_footstep(self.is_sprinting)

            curr_pos = self.camera.getPos()
            new_x, new_y = resolve_collision(chunks, curr_pos.x, curr_pos.y, disp.x, disp.y, radius=PLAYER_RADIUS)
            self.camera.setPos(new_x, new_y, PLAYER_EYE_HEIGHT)
            view_changed = True
        else:
            self.last_move_dir = Vec3(0, 0, 0)
            self.footstep_timer = 0.35

        return is_moving, self.is_sprinting, view_changed
