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


ITEM_CATALOG = {
    "medkit": {
        "id": "medkit",
        "name": "군용 응급치료 키트",
        "category": "의료 소모품",
        "rarity": "RARE",
        "rarity_color": (0.35, 1.0, 0.60, 1.0),
        "icon": "assets/ui/item_medkit.png",
        "max_count": 5,
        "desc": "고농축 지혈제 및 나노 봉합 드레싱.\n사용 시 체력 +50 HP를 즉각 회복합니다.\n[단축키 1번]으로 즉시 사용 가능.",
        "quick_slot": 1
    },
    "adrenaline": {
        "id": "adrenaline",
        "name": "전술 아드레날린 주사기",
        "category": "전술 각성제",
        "rarity": "EPIC",
        "rarity_color": (0.25, 0.85, 1.0, 1.0),
        "icon": "assets/ui/item_adrenaline.png",
        "max_count": 3,
        "desc": "전투 호르몬 자동 주입기.\n사용 시 스테미나 100% 즉시 회복,\n4.5초간 불릿 타임(시간 감속) 발동 및\n오버차지 고폭탄 4발 장전.\n[단축키 2번]으로 즉시 사용 가능.",
        "quick_slot": 2
    },
    "ammo_pack": {
        "id": "ammo_pack",
        "name": "9mm 예비 탄약 상자",
        "category": "탄약 보급품",
        "rarity": "COMMON",
        "rarity_color": (1.0, 0.88, 0.35, 1.0),
        "icon": "assets/ui/item_ammo.png",
        "max_count": 8,
        "desc": "권총용 철갑 탄약 묶음 상자.\n사용 시 예비 탄약 +18발을 즉각 탄띠에 보충합니다.\n[단축키 3번]으로 즉시 사용 가능.",
        "quick_slot": 3
    },
    "frag_grenade": {
        "id": "frag_grenade",
        "name": "M67 파열 수류탄 팩",
        "category": "투척 폭발물",
        "rarity": "UNCOMMON",
        "rarity_color": (0.65, 0.95, 0.25, 1.0),
        "icon": "assets/ui/item_grenade.png",
        "max_count": 10,
        "desc": "반경 6.5m 대인 살상 파열 수류탄.\n쿨타임 없이 보유 개수만큼 [G] 키로 연속 투척 가능.\n[단축키 4번]으로도 즉시 투척.",
        "quick_slot": 4
    },
    "combat_stim": {
        "id": "combat_stim",
        "name": "생체 공격 강화제",
        "category": "특수 약물",
        "rarity": "LEGENDARY",
        "rarity_color": (0.95, 0.45, 0.95, 1.0),
        "icon": "assets/ui/item_stim.png",
        "max_count": 3,
        "desc": "근신경 반응을 극대화하는 바이오 자극제.\n사용 시 15초간 총기 공격력 +40% 증폭 버프를 부여합니다.",
        "quick_slot": None
    }
}


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
        self.perks = set()  # 보유한 로그라이크 전술 퍽 ID 집합
        self.perk_levels = {}
        self.pending_perk_picks = 0  # 레벨업 시 누적되어 카드 선택을 기다리는 퍽 포인트
        self.on_level_up = None
        self.relics = []      # 보유한 저주받은 유물 ID 목록
        self.hp_drain_accum = 0.0

        # 진흙 괴물 땅울림 이동 방해(슬로우) 및 지진 흔들림 상태
        self.slow_timer = 0.0
        self.slow_factor = 1.0
        self.shake_timer = 0.0
        self.shake_intensity = 0.0

        # 이동 및 발자국
        self.is_moving = False
        self.last_move_dir = Vec3(0, 0, 0)
        self.move_speed = 0.0  # Speed before environmental slow effects.
        self.footstep_timer = 0.0
        self.heartbeat_accum = 0.0
        self.is_aiming = False

        # 스페이스바 전술 컴뱃 슬라이드 & 긴급 회피 대시
        self.is_sliding = False
        self.slide_timer = 0.0
        self.slide_duration = 0.62
        self.slide_cooldown = 0.0
        self.slide_dir = Vec3(0, 0, 0)
        self.slide_speed = 0.0

        # 전술 인벤토리 소지품 초기화 (기본 생존 보급품)
        self.inventory = [
            dict(ITEM_CATALOG["medkit"], count=2),
            dict(ITEM_CATALOG["adrenaline"], count=1),
            dict(ITEM_CATALOG["ammo_pack"], count=2),
            dict(ITEM_CATALOG["frag_grenade"], count=3),
        ]
        self.speed_boost_timer = 0.0
        self.stim_boost_timer = 0.0

        # 키보드 입력 상태
        self.key_map = {
            "w": 0, "s": 0, "a": 0, "d": 0,
            "shift": 0
        }

    def setup_input(self, on_shoot, on_reload, on_aim_start=None, on_aim_stop=None, on_inventory=None, on_quick_use=None, on_grenade=None, on_escape=None, on_interact=None, on_weapon_next=None, on_weapon_prev=None, on_weapon_select=None):
        """키보드 및 마우스 조작 이벤트 등록 (사격, 재장전, ADS 정밀조준, 인벤토리, 퀵슬롯, 슬라이드, 수류탄, 상호작용, 무기교체)"""
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

        # 마우스 좌클릭 사격 (Shift/Ctrl 조합키 지원으로 조준 중/달리기 중 입력 누락 방지)
        for m1_evt in ["mouse1", "shift-mouse1", "control-mouse1", "alt-mouse1"]:
            self.base.accept(m1_evt, on_shoot)

        # 마우스 우클릭 정밀 조준(ADS)
        if on_aim_start:
            for m3_down in ["mouse3", "shift-mouse3", "control-mouse3"]:
                self.base.accept(m3_down, self._on_aim_down, [on_aim_start])
        if on_aim_stop:
            for m3_up in ["mouse3-up", "shift-mouse3-up", "control-mouse3-up"]:
                self.base.accept(m3_up, self._on_aim_up, [on_aim_stop])

        # R 키 재장전
        self.base.accept("r", on_reload)
        self.base.accept("shift-r", on_reload)
        self.base.accept("R", on_reload)

        # Q 및 마우스 휠 무기 교체 (다음/이전 무기 순환)
        if on_weapon_next:
            for q_evt in ["q", "Q", "shift-q", "shift-Q", "wheel_down"]:
                self.base.accept(q_evt, on_weapon_next)
        if on_weapon_prev:
            for wp_evt in ["wheel_up"]:
                self.base.accept(wp_evt, on_weapon_prev)

        # Z, X, C 직접 무기 선택 단축키 ([Z] 9mm 권총, [X] 아킴보 쌍권총, [C] 12게이지 샷건)
        if on_weapon_select:
            for z_evt in ["z", "Z", "shift-z", "shift-Z"]:
                self.base.accept(z_evt, on_weapon_select, ["PISTOL"])
            for x_evt in ["x", "X", "shift-x", "shift-X"]:
                self.base.accept(x_evt, on_weapon_select, ["DUAL_PISTOL"])
            for c_evt in ["c", "C", "shift-c", "shift-C"]:
                self.base.accept(c_evt, on_weapon_select, ["SHOTGUN"])

        # TAB / I 키 전술 인벤토리 열기/닫기 토글
        if on_inventory:
            for inv_k in ["tab", "i", "I"]:
                self.base.accept(inv_k, on_inventory)

        # 1, 2, 3, 4 인게임 전술 퀵슬롯 즉시 사용
        if on_quick_use:
            for num_k in ["1", "2", "3", "4"]:
                self.base.accept(num_k, on_quick_use, [int(num_k)])

        # ESC 마우스 커서 해제 / 인벤토리 닫기 토글
        self.on_escape = on_escape
        self.base.accept("escape", self._on_escape_pressed)

        # Space 전술 컴뱃 슬라이드 & 긴급 회피 기동
        for sp_evt in ["space", "shift-space", "control-space", "alt-space"]:
            self.base.accept(sp_evt, self.trigger_slide)

        # G 전술 파열 수류탄 투척
        if on_grenade:
            for g_evt in ["g", "G", "shift-g", "shift-G"]:
                self.base.accept(g_evt, on_grenade)

        # E 현장 오브젝트 / 전술 보급 상자 상호작용
        if on_interact:
            for e_evt in ["e", "E", "shift-e", "shift-E"]:
                self.base.accept(e_evt, on_interact)

    def _on_escape_pressed(self):
        if hasattr(self, 'on_escape') and self.on_escape:
            self.on_escape()
        else:
            self.toggle_mouse_lock()

    def reset_inventory(self):
        """새 게임 시작 시 기본 생존 보급품으로 리셋"""
        self.inventory = [
            dict(ITEM_CATALOG["medkit"], count=2),
            dict(ITEM_CATALOG["adrenaline"], count=1),
            dict(ITEM_CATALOG["ammo_pack"], count=2),
            dict(ITEM_CATALOG["frag_grenade"], count=3),
        ]
        self.speed_boost_timer = 0.0
        self.stim_boost_timer = 0.0

    def add_item(self, item_id, count=1):
        """인벤토리에 아이템 획득 및 수량 추가"""
        for item in self.inventory:
            if item["id"] == item_id:
                max_c = item.get("max_count", 99)
                if item["count"] >= max_c:
                    return False, f"[{item['name']}]의 최대 소지 수량을 초과했습니다."
                item["count"] = min(max_c, item["count"] + count)
                return True, item["name"]

        if item_id in ITEM_CATALOG:
            new_item = dict(ITEM_CATALOG[item_id], count=min(ITEM_CATALOG[item_id].get("max_count", 99), count))
            self.inventory.append(new_item)
            return True, new_item["name"]
        return False, "알 수 없는 아이템입니다."

    def get_item_count(self, item_id):
        """특정 아이템의 잔여 보유 수량 반환"""
        for item in self.inventory:
            if item["id"] == item_id:
                return item.get("count", 0)
        return 0

    def consume_item(self, item_id, count=1):
        """특정 아이템의 수량 차감 (성공 여부 및 잔여 수량 반환)"""
        for item in self.inventory:
            if item["id"] == item_id:
                cur = item.get("count", 0)
                if cur >= count:
                    item["count"] = cur - count
                    return True, item["count"]
                return False, cur
        return False, 0

    def use_item(self, item_id, combat_system=None, game_instance=None):
        """소지품 아이템 사용 및 효과 발동"""
        target_item = None
        for item in self.inventory:
            if item["id"] == item_id:
                target_item = item
                break

        if not target_item or target_item["count"] <= 0:
            return False, "사용할 수 있는 잔여 수량이 없습니다."

        iid = target_item["id"]
        if iid == "medkit":
            if self.hp >= self.max_hp:
                return False, "이미 체력이 100% 가득 차 있습니다!"
            self.heal(50.0)
            target_item["count"] -= 1
            return True, f"군용 응급키트 사용: 체력 +50 HP 회복! (현재: {int(self.hp)}/{int(self.max_hp)})"

        elif iid == "adrenaline":
            self.stamina = self.max_stamina
            self.speed_boost_timer = 10.0
            target_item["count"] -= 1
            if game_instance and hasattr(game_instance, 'trigger_bullet_time'):
                game_instance.trigger_bullet_time(4.5)
            if combat_system and hasattr(combat_system, 'activate_overcharge'):
                combat_system.activate_overcharge(4)
            return True, "전술 아드레날린 주사: 기력 100% 회복 & 불릿 타임 4.5초 및 오버차지 탄환 4발 장전!"

        elif iid == "ammo_pack":
            if combat_system:
                combat_system.reserve_ammo += 18
                combat_system.update_ammo_ui()
            target_item["count"] -= 1
            return True, "9mm 탄약 상자 개봉: 권총 예비 탄약 +18발 보급 완료!"

        elif iid == "frag_grenade":
            if game_instance and hasattr(game_instance, 'throw_grenade'):
                threw = game_instance.throw_grenade()
                if threw:
                    return True, f"파열 수류탄 투척! (잔여: {self.get_item_count('frag_grenade')}개)"
                else:
                    return False, "수류탄이 소진되었거나 던질 수 없는 상태입니다."
            return False, "수류탄을 투척할 수 없습니다."

        elif iid == "combat_stim":
            self.stim_boost_timer = 15.0
            target_item["count"] -= 1
            return True, "생체 공격 강화제 투여: 15초간 총기 공격력 +40% 증폭!"

        return False, "사용할 수 없는 아이템입니다."

    def use_quick_slot(self, slot_num, combat_system=None, game_instance=None):
        """[1~4]번 단축키 퀵슬롯 아이템 즉시 사용"""
        for item in self.inventory:
            if item.get("quick_slot") == slot_num:
                return self.use_item(item["id"], combat_system, game_instance)
        return False, f"[{slot_num}]번 퀵슬롯에 등록된 아이템이 없습니다."

    def trigger_slide(self):
        """[Space] 전술 컴뱃 슬라이드 & 긴급 회피 대시 (낮은 자세로 미끄러지며 사격 가능)"""
        # 퍽 선택 모달 활성화 중에는 Space 키로 확인/전투 재개
        if hasattr(self.base, 'game_state') and self.base.game_state == "SHOP":
            if hasattr(self.ui_mgr, 'shop_modal') and not self.ui_mgr.shop_modal.isHidden():
                self.ui_mgr._confirm_shop_and_start()
                return

        if self.slide_cooldown > 0.0 or self.is_sliding:
            return
        if self.stamina < 5.0:
            return

        # 슬라이딩 방향 결정 (이동 중이면 이동 방향, 정지 상태면 전방 시선 방향)
        if self.last_move_dir.lengthSquared() > 0.01:
            slide_vec = Vec3(self.last_move_dir)
        else:
            h_rad = math.radians(self.heading)
            slide_vec = Vec3(-math.sin(h_rad), math.cos(h_rad), 0)
        slide_vec.normalize()

        self.is_sliding = True
        self.slide_timer = self.slide_duration
        self.slide_cooldown = 0.82
        self.slide_dir = slide_vec
        # Preserve incoming movement, including perks, boosts and aiming.
        # Keep the standing dodge when there is no incoming movement.
        self.slide_speed = self.move_speed if self.move_speed > 0.0 else 15.2 * self.speed_mult
        self.stamina = max(0.0, self.stamina - 6.0)

        if self.audio_mgr and hasattr(self.audio_mgr, 'play_slide'):
            self.audio_mgr.play_slide()

    def _on_aim_down(self, cb):
        self.is_aiming = True
        cb()

    def _on_aim_up(self, cb):
        self.is_aiming = False
        cb()

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
        """경험치 획득 및 레벨업 판정 (레벨업 시 퍽 카드 선택 기회 획득)"""
        self.exp += amount
        leveled = False
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            self.exp_to_next = int(self.exp_to_next * 1.5)
            self.pending_perk_picks += 1
            leveled = True
        if leveled and self.audio_mgr:
            self.audio_mgr.play_levelup()
        self.ui_mgr.update_hp_exp(
            self.hp, self.max_hp, self.exp, self.exp_to_next, self.level,
            pending_perks=self.pending_perk_picks
        )
        if leveled and hasattr(self, 'on_level_up') and self.on_level_up:
            self.on_level_up()
        return leveled

    def add_exp(self, amount, *args, **kwargs):
        """gain_exp 별칭 메서드"""
        return self.gain_exp(amount)

    def get_attack_power(self, blackout_active=False):
        """저주받은 유물 및 전투 자극제 효과가 반영된 최종 공격력 산출"""
        dmg = self.attack_power
        if "glass_cannon" in self.relics:
            dmg *= 1.80  # 공격력 +80%
        if "abyssal_reaper" in self.relics and blackout_active:
            dmg *= 2.50  # 정전 중 공격력 2.5배
        if getattr(self, 'stim_boost_timer', 0.0) > 0.0:
            dmg *= 1.40  # 생체 공격 강화제 공격력 +40%
        return dmg

    def take_damage(self, amount, source_pos=None):
        """몬스터 공격 피격 시 체력 감소 및 시각 피격 효과 (화면 붉은 플래시, 카메라 충격 흔들림, 피격 방향 표시)"""
        if self.invincible_timer > 0.0:
            return False
        # 유리의 총열 유물: 받는 피해 +40%
        if "glass_cannon" in self.relics:
            amount *= 1.40
        # 타이탄 방탄 외골격 퍽: 받는 피해 25% 상시 감소
        if self.has_perk("titan_armor"):
            amount *= 0.75

        self.hp = max(0.0, self.hp - amount)
        self.invincible_timer = 0.55  # 0.55초 무적 쿨다운
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, pending_perks=self.pending_perk_picks)

        # 플레이어 피격 시각 효과: 화면 붉은 플래시 및 카메라 충격 흔들림
        self.ui_mgr.trigger_player_damage_flash(intensity=0.65)
        self.trigger_quake_shake(intensity=1.8, duration=0.35)
        if self.audio_mgr:
            self.audio_mgr.play_player_hurt()

        # 피격 방향 붉은 인디케이터 표시
        if source_pos is not None and hasattr(self.ui_mgr, 'show_damage_direction'):
            curr_pos = (self.camera.getX(), self.camera.getY())
            self.ui_mgr.show_damage_direction(source_pos, curr_pos, self.heading)

        return self.hp <= 0.0

    def heal(self, amount):
        self.hp = min(self.max_hp, self.hp + amount)
        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, pending_perks=self.pending_perk_picks)

    def recover_stamina(self, amount):
        """적 타격/적중 시 전술 아드레날린 활성화로 스테미나 회복"""
        self.stamina = min(self.max_stamina, self.stamina + amount)
        if self.stamina >= 15.0:
            self.stamina_exhausted = False
        self.ui_mgr.update_stamina(self.stamina, self.max_stamina, self.is_sprinting, self.stamina_exhausted)

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

        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, pending_perks=self.pending_perk_picks)
        if hasattr(self.ui_mgr, 'update_relic_badges'):
            self.ui_mgr.update_relic_badges(self.relics)

    def has_perk(self, perk_id):
        """특정 퍽 보유 여부 확인"""
        return perk_id in self.perks

    def add_perk(self, perk_id, combat_system=None):
        """로그라이크 전술 퍽 획득 및 즉각적인 스탯/패시브 적용"""
        self.perks.add(perk_id)
        self.perk_levels[perk_id] = self.perk_levels.get(perk_id, 0) + 1

        if perk_id == "speed_demon":
            self.speed_mult *= 1.20
            if combat_system:
                # 현재 재장전 진행 중인 경우 남은 장전 시간을 35% 단축
                if getattr(combat_system, "is_reloading", False):
                    combat_system.reload_timer *= 0.65
                if hasattr(combat_system, "reload_duration"):
                    try:
                        combat_system.reload_duration *= 0.65
                    except Exception:
                        pass
        elif perk_id == "titan_armor":
            self.max_hp += 25.0
            self.hp = min(self.max_hp, self.hp + 25.0)
        elif perk_id == "vampiric_leech":
            self.hp = min(self.max_hp, self.hp + 20.0)

        self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level, pending_perks=self.pending_perk_picks)
        if hasattr(self.ui_mgr, 'update_perk_badges'):
            self.ui_mgr.update_perk_badges(self.perks)

    def apply_slow(self, duration=2.8, factor=0.40):
        """진흙 괴물 땅울림으로 인한 지면 균열 이동 방해(슬로우) 부여"""
        if self.has_perk("titan_armor"):
            duration *= 0.50
            factor = min(1.0, factor + 0.30)
        self.slow_timer = duration
        self.slow_factor = factor

    def trigger_quake_shake(self, intensity=2.5, duration=0.85):
        """지면 충격 및 지진 카메라 흔들림"""
        self.shake_timer = duration
        self.shake_intensity = intensity

    def reset_position(self, x, y, z=PLAYER_EYE_HEIGHT, heading=0.0, pitch=0.0):
        """플레이어 위치 및 시선 초기화"""
        self.is_sliding = False
        self.slide_timer = 0.0
        self.slide_cooldown = 0.0
        self.slide_speed = 0.0
        self.move_speed = 0.0
        self.last_move_dir = Vec3(0, 0, 0)
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
        if self.slide_cooldown > 0.0:
            self.slide_cooldown = max(0.0, self.slide_cooldown - dt)

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
                self.ui_mgr.update_hp_exp(self.hp, self.max_hp, self.exp, self.exp_to_next, self.level)

        # 아드레날린 및 전투 자극제 버프 타이머 갱신
        if getattr(self, 'speed_boost_timer', 0.0) > 0.0:
            self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
        if getattr(self, 'stim_boost_timer', 0.0) > 0.0:
            self.stim_boost_timer = max(0.0, self.stim_boost_timer - dt)

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
            drain = 22.0 * (0.60 if self.has_perk("speed_demon") else 1.0)
            self.stamina -= drain * dt  # 스피드 데몬 퍽 보유 시 소모 40% 절감
            if self.stamina <= 0.0:
                self.stamina = 0.0
                self.stamina_exhausted = True
                self.is_sprinting = False
        else:
            recovery_rate = 14.0 if not is_moving else 8.0
            self.stamina = min(self.max_stamina, self.stamina + recovery_rate * dt)

        self.ui_mgr.update_stamina(self.stamina, self.max_stamina, self.is_sprinting, self.stamina_exhausted)

        # 4. 전술 컴뱃 슬라이딩 이동 또는 일반 지면 이동
        if self.is_sliding:
            self.slide_timer = max(0.0, self.slide_timer - dt)
            progress = 1.0 - (self.slide_timer / self.slide_duration)  # 0.0 -> 1.0

            # Maintain entry speed throughout the slide; external slows still apply.
            cur_speed = self.slide_speed * cur_slow
            disp = self.slide_dir * cur_speed * dt

            # 슬라이딩 시 시선 고도 낮추기 (1.7m -> 0.92m 크라우치 슬라이드 -> 복귀)
            crouch_height = 0.92
            if progress < 0.65:
                t_in = min(1.0, progress / 0.18)
                cur_z = PLAYER_EYE_HEIGHT + (crouch_height - PLAYER_EYE_HEIGHT) * t_in
            else:
                t_out = (progress - 0.65) / 0.35
                cur_z = crouch_height + (PLAYER_EYE_HEIGHT - crouch_height) * t_out

            curr_pos = self.camera.getPos()
            new_x, new_y = resolve_collision(chunks, curr_pos.x, curr_pos.y, disp.x, disp.y, radius=PLAYER_RADIUS)
            self.camera.setPos(new_x, new_y, cur_z)

            # 슬라이딩 시 카메라 다이내믹 뱅킹 틸트 (좌우 2.5도 기울임)
            tilt_r = math.sin(progress * math.pi) * 2.6
            self.camera.setR(tilt_r)

            view_changed = True
            is_moving = True

            if self.slide_timer <= 0.0:
                self.is_sliding = False
                self.camera.setPos(new_x, new_y, PLAYER_EYE_HEIGHT)
                self.camera.setR(0.0)
        else:
            # 일반 지면 이동 및 정밀 충돌 슬라이딩
            if is_moving:
                move_dir.normalize()
                self.last_move_dir = move_dir
                base_speed = SPRINT_SPEED if self.is_sprinting else WALK_SPEED
                aim_mult = 0.78 if self.is_aiming else 1.0
                speed_boost = 1.30 if getattr(self, 'speed_boost_timer', 0.0) > 0.0 else 1.0
                self.move_speed = base_speed * self.speed_mult * aim_mult * speed_boost
                speed = self.move_speed * cur_slow
                disp = move_dir * speed * dt

                # 발자국 소리 주기
                step_interval = (0.26 if self.is_sprinting else 0.42) / max(1.0, self.speed_mult)
                self.footstep_timer += dt
                if self.footstep_timer >= step_interval:
                    self.footstep_timer = 0.0
                    if self.audio_mgr:
                        self.audio_mgr.play_footstep(self.is_sprinting)

                curr_pos = self.camera.getPos()
                new_x, new_y = resolve_collision(chunks, curr_pos.x, curr_pos.y, disp.x, disp.y, radius=PLAYER_RADIUS)
                self.camera.setPos(new_x, new_y, PLAYER_EYE_HEIGHT)
                view_changed = True
            else:
                self.last_move_dir = Vec3(0, 0, 0)
                self.move_speed = 0.0
                self.footstep_timer = 0.35

        # 5. 빈사 상태(HP < 30) 심장박동 효과음 및 붉은 비네트 맥동
        if 0.0 < self.hp < 30.0:
            hb_interval = 0.50 + 0.50 * (self.hp / 30.0)
            self.heartbeat_accum += dt
            if self.heartbeat_accum >= hb_interval:
                self.heartbeat_accum = 0.0
                if self.audio_mgr:
                    self.audio_mgr.play_heartbeat()
                if self.ui_mgr and hasattr(self.ui_mgr, 'trigger_low_hp_pulse'):
                    self.ui_mgr.trigger_low_hp_pulse(0.38)
        else:
            self.heartbeat_accum = 0.0

        self.is_moving = is_moving
        return is_moving, self.is_sprinting, view_changed
