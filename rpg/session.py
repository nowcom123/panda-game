"""RPG Session management connecting profile, save store, and runtime equipment policies."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from rpg.items import (
    ItemDefinition,
    ItemInstance,
    RPGError,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    create_item,
)
from rpg.profile import PlayerProfile
from rpg.save_store import SaveStore
from rpg.weapon_stats import resolve_weapon_config
from combat.weapon_config import WEAPON_CONFIGS

STARTER_UNLOCK_KEY = "starter_loadout_v1"


class RPGSession:
    """Manages the lifecycle of a player profile during a game session."""

    def __init__(self, store: SaveStore, catalog: Mapping[str, ItemDefinition]) -> None:
        self.store = store
        self.catalog = catalog
        self.profile: PlayerProfile | None = None
        self.is_valid: bool = False
        self.load_error: str | None = None
        self.load_warnings: list[str] = []
        self.active_slot: str = "primary"
        self._effective_config_cache: dict[str, dict[str, Any]] = {}

    def initialize(self, grant_starters=True) -> bool:
        """Load profile from store, enforcing data preservation and starter loadout policy."""
        self._effective_config_cache.clear()
        try:
            load_result = self.store.load()
            self.profile = load_result.profile
            self.load_warnings = list(load_result.warnings)
            self.is_valid = True
            self.load_error = None
        except (UnsupportedSaveVersion, SaveCorruptedError, ValidationError, Exception) as err:
            self.profile = None
            self.is_valid = False
            self.load_error = f"저장 파일 오류 ({type(err).__name__}): {err}"
            return False

        # Apply starter loadout policy if applicable
        try:
            if grant_starters and self._should_grant_starter_loadout():
                self._grant_starter_loadout()
        except (OSError, RPGError) as err:
            self.profile = None
            self.is_valid = False
            self.load_error = f"초기 장비 저장 실패: {err}"
            return False

        # Invalidate/warm cache
        self.refresh_cache()
        return True

    def _should_grant_starter_loadout(self) -> bool:
        if self.profile is None:
            return False
        return (
            STARTER_UNLOCK_KEY not in self.profile.unlocks
            and len(self.profile.items) == 0
        )

    def _grant_starter_loadout(self) -> None:
        """Grant the 4 basic starter weapons and equip PISTOL / SHOTGUN."""
        if self.profile is None:
            return

        w_pistol = create_item(self.catalog, "weapon_pistol", rarity="common", item_level=1)
        w_dual = create_item(self.catalog, "weapon_dual_pistol", rarity="common", item_level=1)
        w_ar = create_item(self.catalog, "weapon_ar", rarity="common", item_level=1)
        w_shotgun = create_item(self.catalog, "weapon_shotgun", rarity="common", item_level=1)

        self.profile.add_item(w_pistol)
        self.profile.add_item(w_dual)
        self.profile.add_item(w_ar)
        self.profile.add_item(w_shotgun)

        self.profile.equip("primary", w_pistol.uid, self.catalog)
        self.profile.equip("secondary", w_shotgun.uid, self.catalog)

        self.profile.unlocks.append(STARTER_UNLOCK_KEY)
        self.profile.validate(self.catalog)

        # Save immediately so starters are persisted
        self.store.save(self.profile)

    def refresh_cache(self) -> None:
        """Recompute and cache effective weapon configs for all owned weapons."""
        self._effective_config_cache.clear()
        if not self.profile:
            return
        for uid, item in self.profile.items.items():
            defn = self.catalog.get(item.definition_id)
            if defn and defn.kind == "weapon":
                try:
                    cfg = resolve_weapon_config(WEAPON_CONFIGS, self.catalog, item)
                    self._effective_config_cache[uid] = cfg
                except Exception:
                    pass

    def get_effective_config_for_item(self, item: ItemInstance) -> dict[str, Any] | None:
        """Get cached effective config for a given item instance."""
        if item.uid not in self._effective_config_cache:
            defn = self.catalog.get(item.definition_id)
            if defn and defn.kind == "weapon":
                try:
                    self._effective_config_cache[item.uid] = resolve_weapon_config(
                        WEAPON_CONFIGS, self.catalog, item
                    )
                except Exception:
                    return None
        return self._effective_config_cache.get(item.uid)

    def get_effective_config_for_slot(self, slot: str) -> dict[str, Any] | None:
        """Get cached effective config for weapon equipped in slot."""
        if not self.profile:
            return None
        uid = self.profile.equipment.get(slot)
        if not uid:
            return None
        item = self.profile.items.get(uid)
        if not item:
            return None
        return self.get_effective_config_for_item(item)

    def get_item(self, uid: str) -> ItemInstance | None:
        if not self.profile:
            return None
        return self.profile.items.get(uid)

    def quote_upgrade(self, uid, recipe_id):
        from rpg.workshop import quote_upgrade
        if not self.is_valid or self.profile is None:
            raise ValidationError('유효한 프로필이 없습니다.')
        return quote_upgrade(self.profile, self.catalog, uid, recipe_id)

    def upgrade_weapon(self, quote) -> tuple[bool, str]:
        """Commit material spending and the weapon upgrade in a single save."""
        from rpg.workshop import upgrade_candidate
        if not self.is_valid or self.profile is None:
            return False, '유효한 프로필이 없습니다.'
        try:
            candidate = upgrade_candidate(self.profile, self.catalog, quote)
            self.store.save(candidate)
        except Exception as err:
            return False, f'강화 실패: {err}'
        self.profile = candidate
        self.refresh_cache()
        return True, '강화 완료. 재료와 장비가 저장되었습니다.'

    def get_equipped_item(self, slot: str) -> ItemInstance | None:
        if not self.profile:
            return None
        uid = self.profile.equipment.get(slot)
        if not uid:
            return None
        return self.profile.items.get(uid)

    def equip(self, slot: str, uid: str) -> tuple[bool, str]:
        """Equip an item into slot ('primary' or 'secondary'), saving atomically.

        Returns (success: bool, message: str).
        """
        if not self.is_valid or self.profile is None:
            return False, "유효한 프로필이 없습니다."

        if slot not in ("primary", "secondary"):
            return False, f"잘못된 장착 슬롯입니다: {slot}"

        if uid not in self.profile.items:
            return False, "소유하지 않은 아이템입니다."

        item = self.profile.items[uid]
        defn = self.catalog.get(item.definition_id)
        if not defn or defn.kind != "weapon":
            return False, "재료 아이템은 장착할 수 없습니다."

        other_slot = "secondary" if slot == "primary" else "primary"
        if self.profile.equipment.get(other_slot) == uid:
            return False, "이미 다른 슬롯에 장착되어 있는 장비입니다."

        # Clone and validate candidate
        candidate = copy.deepcopy(self.profile)
        try:
            candidate.equip(slot, uid, self.catalog)
            candidate.validate(self.catalog)
            self.store.save(candidate)
        except Exception as err:
            return False, f"장착 저장 실패: {err}"

        # Reflect changes
        self.profile = candidate
        self.refresh_cache()
        return True, "장착되었습니다."

    def unequip(self, slot: str) -> tuple[bool, str]:
        """Unequip item from slot, ensuring at least one weapon remains equipped."""
        if not self.is_valid or self.profile is None:
            return False, "유효한 프로필이 없습니다."

        if slot not in ("primary", "secondary"):
            return False, f"잘못된 슬롯입니다: {slot}"

        if self.profile.equipment.get(slot) is None:
            return False, "이미 비어있는 슬롯입니다."

        other_slot = "secondary" if slot == "primary" else "primary"
        if self.profile.equipment.get(other_slot) is None:
            return False, "최소 1개의 무기는 장착되어 있어야 합니다."

        candidate = copy.deepcopy(self.profile)
        try:
            candidate.unequip(slot)
            candidate.validate(self.catalog)
            self.store.save(candidate)
        except Exception as err:
            return False, f"해제 저장 실패: {err}"

        self.profile = candidate
        self.refresh_cache()
        return True, "장착 해제되었습니다."

    def set_locked(self, uid: str, locked: bool) -> tuple[bool, str]:
        """Toggle or set item locked flag, persisting atomically."""
        if not self.is_valid or self.profile is None:
            return False, "유효한 프로필이 없습니다."

        if uid not in self.profile.items:
            return False, "아이템을 찾을 수 없습니다."

        candidate = copy.deepcopy(self.profile)
        candidate.items[uid].locked = bool(locked)
        try:
            candidate.validate(self.catalog)
            self.store.save(candidate)
        except Exception as err:
            return False, f"잠금 설정 저장 실패: {err}"

        self.profile = candidate
        msg = "아이템이 잠겼습니다." if locked else "아이템 잠금이 해제되었습니다."
        return True, msg

