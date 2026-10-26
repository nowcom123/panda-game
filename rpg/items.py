"""Item definitions, instances, and catalog loading for RPG system."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# Validation Constants
VALID_RARITIES = frozenset({"common", "uncommon", "rare", "epic", "legendary"})
VALID_KINDS = frozenset({"weapon", "material"})
VALID_AFFIX_IDS = frozenset({"damage_mult", "reload_time_mult", "weakpoint_mult"})
VALID_WEAPON_KEYS = frozenset({"PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"})


# Exception Hierarchy
class RPGError(Exception):
    """Base exception for all RPG module errors."""
    pass


class ValidationError(RPGError):
    """Raised when data fails schema or contract validation."""
    pass


class ItemNotFoundError(ValidationError):
    """Raised when an item definition is not found in the catalog."""
    pass


class UnsupportedSaveVersion(RPGError):
    """Raised when a save file schema version is higher than supported."""
    pass


class SaveCorruptedError(RPGError):
    """Raised when save files are corrupted and cannot be recovered."""
    pass


def unique_json_object(pairs):
    """Reject duplicate JSON keys instead of silently losing inventory entries."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class ItemAffix:
    """Represents a validated stat affix on an equipment instance."""
    id: str
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or self.id not in VALID_AFFIX_IDS:
            raise ValidationError(
                f"Invalid affix id: {self.id!r}. Allowed: {sorted(VALID_AFFIX_IDS)}"
            )
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValidationError(
                f"Affix value must be a number, got {type(self.value).__name__}: {self.value!r}"
            )
        if not math.isfinite(self.value) or self.value <= 0:
            raise ValidationError(
                f"Affix value must be a positive finite number, got {self.value!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "value": self.value}

    @classmethod
    def from_dict(cls, data: Any) -> ItemAffix:
        if not isinstance(data, dict):
            raise ValidationError(f"Affix data must be a dict, got {type(data).__name__}")
        if "id" not in data or "value" not in data:
            raise ValidationError(f"Affix missing required keys ('id', 'value'): {data!r}")
        return cls(id=data["id"], value=data["value"])


@dataclass(frozen=True)
class ItemDefinition:
    """Static template definition of an item type."""
    definition_id: str
    name: str
    kind: str
    max_stack: int
    weapon_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.definition_id, str) or not self.definition_id.strip():
            raise ValidationError("definition_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("name must be a non-empty string")
        if not isinstance(self.kind, str) or self.kind not in VALID_KINDS:
            raise ValidationError(
                f"Invalid kind: {self.kind!r}. Allowed: {sorted(VALID_KINDS)}"
            )
        if (
            isinstance(self.max_stack, bool)
            or not isinstance(self.max_stack, int)
            or self.max_stack < 1
        ):
            raise ValidationError(
                f"max_stack must be a positive integer, got {self.max_stack!r}"
            )

        if self.kind == "weapon":
            if self.max_stack != 1:
                raise ValidationError(
                    f"Weapon max_stack must be 1, got {self.max_stack}"
                )
            if (
                not isinstance(self.weapon_key, str)
                or self.weapon_key not in VALID_WEAPON_KEYS
            ):
                raise ValidationError(
                    f"Weapon must have a valid weapon_key in {sorted(VALID_WEAPON_KEYS)}, "
                    f"got {self.weapon_key!r}"
                )
        elif self.kind == "material":
            if self.weapon_key is not None:
                raise ValidationError(
                    f"Material item must not have a weapon_key, got {self.weapon_key!r}"
                )


@dataclass
class ItemInstance:
    """Individual item instance in inventory or equipment."""
    uid: str
    definition_id: str
    rarity: str = "common"
    item_level: int = 1
    quantity: int = 1
    affixes: list[ItemAffix] = field(default_factory=list)
    locked: bool = False

    def validate(self, catalog: Mapping[str, ItemDefinition]) -> None:
        """Validate instance integrity against its catalog definition."""
        if not isinstance(self.uid, str) or not self.uid.strip():
            raise ValidationError(f"uid must be a non-empty string, got {self.uid!r}")

        if not isinstance(self.definition_id, str) or self.definition_id not in catalog:
            raise ItemNotFoundError(
                f"Unknown item definition_id: {self.definition_id!r}"
            )

        defn = catalog[self.definition_id]

        if not isinstance(self.rarity, str) or self.rarity not in VALID_RARITIES:
            raise ValidationError(
                f"Invalid rarity: {self.rarity!r}. Allowed: {sorted(VALID_RARITIES)}"
            )

        if (
            isinstance(self.item_level, bool)
            or not isinstance(self.item_level, int)
            or self.item_level < 1
        ):
            raise ValidationError(
                f"item_level must be a positive integer, got {self.item_level!r}"
            )

        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
            or self.quantity > defn.max_stack
        ):
            raise ValidationError(
                f"quantity must be an integer between 1 and {defn.max_stack}, got {self.quantity!r}"
            )

        if defn.kind == "weapon" and self.quantity != 1:
            raise ValidationError(
                f"Weapon quantity must be exactly 1, got {self.quantity}"
            )

        if not isinstance(self.locked, bool):
            raise ValidationError(f"locked must be a boolean, got {self.locked!r}")

        # Affixes validation
        if not isinstance(self.affixes, (list, tuple)):
            raise ValidationError(f"affixes must be a list, got {type(self.affixes).__name__}")

        if defn.kind == "material" and len(self.affixes) > 0:
            raise ValidationError(
                f"Materials cannot have affixes, found {len(self.affixes)} affixes on {self.definition_id}"
            )

        seen_affix_ids: set[str] = set()
        for affix in self.affixes:
            if not isinstance(affix, ItemAffix):
                raise ValidationError(f"Each affix must be an ItemAffix instance, got {type(affix).__name__}")
            if affix.id in seen_affix_ids:
                raise ValidationError(f"Duplicate affix id detected: {affix.id!r}")
            seen_affix_ids.add(affix.id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize item instance to JSON-compatible dictionary."""
        return {
            "uid": self.uid,
            "definition_id": self.definition_id,
            "rarity": self.rarity,
            "item_level": self.item_level,
            "quantity": self.quantity,
            "affixes": [a.to_dict() for a in self.affixes],
            "locked": self.locked,
        }

    @classmethod
    def from_dict(
        cls,
        data: Any,
        catalog: Mapping[str, ItemDefinition],
    ) -> ItemInstance:
        """Deserialize and validate item instance from a dictionary."""
        if not isinstance(data, dict):
            raise ValidationError(f"Item data must be a dict, got {type(data).__name__}")

        required_keys = {"uid", "definition_id", "rarity", "item_level", "quantity", "affixes", "locked"}
        missing = required_keys - data.keys()
        if missing:
            raise ValidationError(f"Item data missing required fields: {sorted(missing)}")

        raw_affixes = data["affixes"]
        if not isinstance(raw_affixes, (list, tuple)):
            raise ValidationError(f"affixes must be a list, got {type(raw_affixes).__name__}")

        parsed_affixes: list[ItemAffix] = []
        for aff in raw_affixes:
            parsed_affixes.append(ItemAffix.from_dict(aff))

        instance = cls(
            uid=data["uid"],
            definition_id=data["definition_id"],
            rarity=data["rarity"],
            item_level=data["item_level"],
            quantity=data["quantity"],
            affixes=parsed_affixes,
            locked=data["locked"],
        )
        instance.validate(catalog)
        return instance


def get_default_catalog_path() -> Path:
    """Return default items.json path relative to this source file."""
    return Path(__file__).resolve().parent.parent / "assets" / "data" / "items.json"


def load_catalog(path: str | Path | None = None) -> dict[str, ItemDefinition]:
    """Load and validate item definitions catalog from JSON file."""
    catalog_path = Path(path).resolve() if path is not None else get_default_catalog_path()

    if not catalog_path.is_file():
        raise FileNotFoundError(f"Catalog file not found: {catalog_path}")

    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=unique_json_object)
    except json.JSONDecodeError as err:
        raise ValidationError(f"Corrupted catalog JSON file at {catalog_path}: {err}") from err
    except (OSError, UnicodeError, ValidationError) as err:
        raise ValidationError(f"Failed to read catalog file at {catalog_path}: {err}") from err

    if not isinstance(data, dict):
        raise ValidationError(f"Catalog root must be a dict, got {type(data).__name__}")

    version = data.get("catalog_version")
    if type(version) is not int or version != 1:
        raise ValidationError(f"Unsupported catalog_version: {version!r} (expected 1)")

    raw_defs = data.get("definitions")
    if not isinstance(raw_defs, list):
        raise ValidationError("Catalog 'definitions' must be a list")

    catalog: dict[str, ItemDefinition] = {}
    for item in raw_defs:
        if not isinstance(item, dict):
            raise ValidationError(f"Item definition must be a dict, got {type(item).__name__}")

        defn = ItemDefinition(
            definition_id=item.get("definition_id", ""),
            name=item.get("name", ""),
            kind=item.get("kind", ""),
            max_stack=item.get("max_stack"),
            weapon_key=item.get("weapon_key"),
        )
        if defn.definition_id in catalog:
            raise ValidationError(f"Duplicate definition_id in catalog: {defn.definition_id!r}")
        catalog[defn.definition_id] = defn

    return catalog


def create_item(
    catalog: Mapping[str, ItemDefinition],
    definition_id: str,
    *,
    rarity: str = "common",
    item_level: int = 1,
    quantity: int = 1,
    affixes: Sequence[ItemAffix | dict[str, Any] | tuple[str, float]] | None = None,
    locked: bool = False,
    uid: str | None = None,
) -> ItemInstance:
    """Create a validated ItemInstance from catalog definition."""
    if not isinstance(definition_id, str) or definition_id not in catalog:
        raise ItemNotFoundError(f"Unknown item definition_id: {definition_id!r}")

    item_uid = str(uuid.uuid4()) if uid is None else uid

    processed_affixes: list[ItemAffix] = []
    if affixes is not None:
        for aff in affixes:
            if isinstance(aff, ItemAffix):
                processed_affixes.append(aff)
            elif isinstance(aff, dict):
                processed_affixes.append(ItemAffix.from_dict(aff))
            elif isinstance(aff, (tuple, list)) and len(aff) == 2:
                processed_affixes.append(ItemAffix(id=aff[0], value=aff[1]))
            else:
                raise ValidationError(f"Unsupported affix format: {aff!r}")

    instance = ItemInstance(
        uid=item_uid,
        definition_id=definition_id,
        rarity=rarity,
        item_level=item_level,
        quantity=quantity,
        affixes=processed_affixes,
        locked=locked,
    )
    instance.validate(catalog)
    return instance

