"""Player profile schema and lifecycle management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from rpg.items import (
    ItemDefinition,
    ItemInstance,
    UnsupportedSaveVersion,
    ValidationError,
    load_catalog,
)

CURRENT_SCHEMA_VERSION = 1
EQUIPMENT_SLOTS = frozenset({"primary", "secondary"})


@dataclass
class PlayerProfile:
    """Persistent player profile containing items, equipment, currencies and unlocks."""
    profile_id: str
    schema_version: int = CURRENT_SCHEMA_VERSION
    items: dict[str, ItemInstance] = field(default_factory=dict)
    equipment: dict[str, str | None] = field(
        default_factory=lambda: {"primary": None, "secondary": None}
    )
    currencies: dict[str, int] = field(
        default_factory=lambda: {"credits": 0}
    )
    unlocks: list[str] = field(default_factory=list)

    def validate(self, catalog: Mapping[str, ItemDefinition] | None = None) -> None:
        """Thoroughly validate profile integrity and references."""
        # Schema version check
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise ValidationError(
                f"schema_version must be an integer, got {type(self.schema_version).__name__}"
            )
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            if self.schema_version > CURRENT_SCHEMA_VERSION:
                raise UnsupportedSaveVersion(
                    f"Unsupported schema version: {self.schema_version} (supported: {CURRENT_SCHEMA_VERSION})"
                )
            raise ValidationError(
                f"Invalid schema version: {self.schema_version} (expected: {CURRENT_SCHEMA_VERSION})"
            )

        # Profile ID
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValidationError("profile_id must be a non-empty string")

        # Items mapping
        if not isinstance(self.items, dict):
            raise ValidationError(f"items must be a dict, got {type(self.items).__name__}")

        for uid_key, item in self.items.items():
            if not isinstance(uid_key, str) or not uid_key.strip():
                raise ValidationError(f"Item key must be a non-empty string, got {uid_key!r}")
            if not isinstance(item, ItemInstance):
                raise ValidationError(f"Item values must be ItemInstance, got {type(item).__name__}")
            if uid_key != item.uid:
                raise ValidationError(
                    f"Dictionary key {uid_key!r} does not match ItemInstance.uid {item.uid!r}"
                )
            if catalog is not None:
                item.validate(catalog)

        # Equipment validation
        if not isinstance(self.equipment, dict):
            raise ValidationError(f"equipment must be a dict, got {type(self.equipment).__name__}")

        if set(self.equipment.keys()) != EQUIPMENT_SLOTS:
            raise ValidationError(
                f"equipment keys must be exactly {sorted(EQUIPMENT_SLOTS)}, got {sorted(self.equipment.keys())}"
            )

        equipped_uids: list[str] = []
        for slot, uid in self.equipment.items():
            if uid is None:
                continue
            if not isinstance(uid, str) or not uid.strip():
                raise ValidationError(f"equipment[{slot!r}] UID must be non-empty string or None, got {uid!r}")
            if uid not in self.items:
                raise ValidationError(
                    f"equipment[{slot!r}] references unowned item UID: {uid!r}"
                )
            if catalog is not None:
                item_inst = self.items[uid]
                defn = catalog[item_inst.definition_id]
                if defn.kind != "weapon":
                    raise ValidationError(
                        f"Cannot equip non-weapon item ({defn.definition_id!r}, kind={defn.kind!r}) in slot {slot!r}"
                    )
            equipped_uids.append(uid)

        # Check for same UID equipped in both primary and secondary
        if len(equipped_uids) == 2 and equipped_uids[0] == equipped_uids[1]:
            raise ValidationError(
                f"Cannot equip the same item UID in both primary and secondary: {equipped_uids[0]!r}"
            )

        # Currencies validation
        if not isinstance(self.currencies, dict):
            raise ValidationError(f"currencies must be a dict, got {type(self.currencies).__name__}")

        if "credits" not in self.currencies:
            raise ValidationError("currencies must contain 'credits'")

        for curr_name, val in self.currencies.items():
            if not isinstance(curr_name, str) or not curr_name.strip():
                raise ValidationError("currency key must be a non-empty string")
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValidationError(
                    f"currency {curr_name!r} value must be an integer, got {type(val).__name__}: {val!r}"
                )
            if val < 0:
                raise ValidationError(
                    f"currency {curr_name!r} cannot be negative: {val}"
                )

        # Unlocks validation
        if not isinstance(self.unlocks, list):
            raise ValidationError(f"unlocks must be a list, got {type(self.unlocks).__name__}")

        seen_unlocks: set[str] = set()
        for entry in self.unlocks:
            if not isinstance(entry, str) or not entry.strip():
                raise ValidationError(f"Unlock item must be a non-empty string, got {entry!r}")
            if entry in seen_unlocks:
                raise ValidationError(f"Duplicate unlock key detected: {entry!r}")
            seen_unlocks.add(entry)

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile to isolated JSON-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "items": {uid: item.to_dict() for uid, item in self.items.items()},
            "equipment": dict(self.equipment),
            "currencies": dict(self.currencies),
            "unlocks": list(self.unlocks),
        }

    @classmethod
    def from_dict(
        cls,
        data: Any,
        catalog: Mapping[str, ItemDefinition],
    ) -> PlayerProfile:
        """Deserialize and validate PlayerProfile from dictionary."""
        if not isinstance(data, dict):
            raise ValidationError(f"Profile root must be a dict, got {type(data).__name__}")

        # Check schema version first for backward/forward compatibility
        raw_version = data.get("schema_version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise ValidationError(f"schema_version must be an integer, got {type(raw_version).__name__}")

        if raw_version > CURRENT_SCHEMA_VERSION:
            raise UnsupportedSaveVersion(
                f"Unsupported save schema version: {raw_version} (supported up to {CURRENT_SCHEMA_VERSION})"
            )
        if raw_version != CURRENT_SCHEMA_VERSION:
            raise ValidationError(f"Invalid schema version: {raw_version}")

        profile_id = data.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValidationError("profile_id must be a non-empty string")

        raw_items = data.get("items")
        if not isinstance(raw_items, dict):
            raise ValidationError("items must be a dict")

        restored_items: dict[str, ItemInstance] = {}
        for uid_key, raw_item in raw_items.items():
            if not isinstance(uid_key, str):
                raise ValidationError(f"Item key must be a string, got {type(uid_key).__name__}")
            item_instance = ItemInstance.from_dict(raw_item, catalog)
            if uid_key != item_instance.uid:
                raise ValidationError(
                    f"Item dictionary key {uid_key!r} does not match instance uid {item_instance.uid!r}"
                )
            restored_items[uid_key] = item_instance

        raw_equipment = data.get("equipment")
        if not isinstance(raw_equipment, dict):
            raise ValidationError("equipment must be a dict")
        equipment = dict(raw_equipment)

        raw_currencies = data.get("currencies")
        if not isinstance(raw_currencies, dict):
            raise ValidationError("currencies must be a dict")
        currencies = dict(raw_currencies)

        raw_unlocks = data.get("unlocks")
        if not isinstance(raw_unlocks, list):
            raise ValidationError("unlocks must be a list")
        unlocks = list(raw_unlocks)

        profile = cls(
            profile_id=profile_id,
            schema_version=raw_version,
            items=restored_items,
            equipment=equipment,
            currencies=currencies,
            unlocks=unlocks,
        )
        profile.validate(catalog)
        return profile

    def add_item(self, item: ItemInstance) -> None:
        """Add an item instance to the inventory."""
        if not isinstance(item, ItemInstance):
            raise ValidationError(f"Expected ItemInstance, got {type(item).__name__}")
        if not isinstance(item.uid, str) or not item.uid.strip():
            raise ValidationError("Item UID must be a non-empty string")
        if item.uid in self.items:
            raise ValidationError(f"Duplicate item UID: {item.uid!r}")
        self.items[item.uid] = item

    def remove_item(self, uid: str) -> ItemInstance | None:
        """Remove item from inventory and unequip if equipped."""
        item = self.items.pop(uid, None)
        if item is not None:
            for slot, eq_uid in list(self.equipment.items()):
                if eq_uid == uid:
                    self.equipment[slot] = None
        return item

    def equip(self, slot: str, uid: str | None, catalog: Mapping[str, ItemDefinition] | None = None) -> None:
        """Equip an item UID into slot ('primary' or 'secondary')."""
        if not isinstance(slot, str) or slot not in EQUIPMENT_SLOTS:
            raise ValidationError(f"Invalid equipment slot: {slot!r}. Allowed: {sorted(EQUIPMENT_SLOTS)}")

        if uid is not None:
            if not isinstance(uid, str) or not uid.strip():
                raise ValidationError("Equipment UID must be a non-empty string")
            if uid not in self.items:
                raise ValidationError(f"Cannot equip unowned item UID: {uid!r}")
            if catalog is None:
                catalog = load_catalog()
            self.items[uid].validate(catalog)
            if catalog is not None:
                defn = catalog[self.items[uid].definition_id]
                if defn.kind != "weapon":
                    raise ValidationError(
                        f"Cannot equip non-weapon ({defn.definition_id!r}) in slot {slot!r}"
                    )
            other_slot = "secondary" if slot == "primary" else "primary"
            if self.equipment.get(other_slot) == uid:
                raise ValidationError(f"Item UID {uid!r} is already equipped in slot {other_slot!r}")

        self.equipment[slot] = uid

    def unequip(self, slot: str) -> None:
        """Unequip item from slot."""
        if slot not in EQUIPMENT_SLOTS:
            raise ValidationError(f"Invalid equipment slot: {slot!r}. Allowed: {sorted(EQUIPMENT_SLOTS)}")
        self.equipment[slot] = None


def new_profile(profile_id: str | None = None) -> PlayerProfile:
    """Create a new empty profile without test equipment."""
    pid = str(uuid.uuid4()) if profile_id is None else profile_id
    if not isinstance(pid, str) or not pid.strip():
        raise ValidationError("profile_id must be a non-empty string")
    return PlayerProfile(
        profile_id=pid,
        schema_version=CURRENT_SCHEMA_VERSION,
        items={},
        equipment={"primary": None, "secondary": None},
        currencies={"credits": 0},
        unlocks=[],
    )

