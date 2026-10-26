"""Loot generation module: drop rates, affix rolls, and tier-based tables."""

from __future__ import annotations

import random
import uuid
from typing import Any, Mapping, Sequence

from rpg.items import ItemAffix, ItemDefinition, ItemInstance, create_item

# Balance Constants & Tables
DROP_CHANCE_NORMAL = 0.20
TYPE_WEIGHTS = {"weapon": 0.60, "material": 0.40}

RARITY_WEIGHTS = {
    "normal": [("common", 50), ("uncommon", 40), ("rare", 10)],
    "elite": [("uncommon", 35), ("rare", 55), ("epic", 10)],
    "boss": [("rare", 70), ("epic", 30)],
}

AFFIX_COUNTS = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
}

AFFIX_RANGES = {
    "damage_mult": (1.050, 1.200),
    "reload_time_mult": (0.850, 0.950),
    "weakpoint_mult": (1.050, 1.250),
}

WEAPON_DEF_IDS = [
    "weapon_pistol",
    "weapon_dual_pistol",
    "weapon_ar",
    "weapon_shotgun",
]

MATERIAL_DEF_IDS = [
    "scrap_metal",
    "bone_fragment",
]


def _weighted_choice(rng: random.Random, choices: Sequence[tuple[str, int | float]]) -> str:
    total = sum(weight for _, weight in choices)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, weight in choices:
        if upto + weight >= r:
            return item
        upto += weight
    return choices[-1][0]


def roll_affixes(rng: random.Random, rarity: str) -> list[ItemAffix]:
    """Roll non-duplicate affixes with rounded 3-decimal multipliers."""
    count = AFFIX_COUNTS.get(rarity, 0)
    if count <= 0:
        return []

    available_ids = list(AFFIX_RANGES.keys())
    chosen_ids = rng.sample(available_ids, min(count, len(available_ids)))

    affixes: list[ItemAffix] = []
    for aff_id in chosen_ids:
        low, high = AFFIX_RANGES[aff_id]
        val = round(rng.uniform(low, high), 3)
        affixes.append(ItemAffix(id=aff_id, value=val))
    return affixes


def roll_loot(
    catalog: Mapping[str, ItemDefinition],
    rng: random.Random | None = None,
    *,
    enemy_tier: str = "normal",
    stage: int = 1,
) -> list[ItemInstance]:
    """Roll dropped items for enemy defeat.

    Args:
        catalog: Loaded ItemDefinition catalog.
        rng: Injectable random.Random instance. If None, a new random.Random() is used.
        enemy_tier: 'normal', 'elite', or 'boss'.
        stage: Current campaign stage (determines item_level).

    Returns:
        List of generated ItemInstance objects.
    """
    if rng is None:
        rng = random.Random()

    tier = enemy_tier.lower()
    item_level = max(1, int(stage))
    generated: list[ItemInstance] = []

    if tier == "boss":
        # Boss guarantees: 1 Weapon + 1 Material bundle
        # 1) Weapon
        rarity = _weighted_choice(rng, RARITY_WEIGHTS["boss"])
        w_def_id = rng.choice(WEAPON_DEF_IDS)
        affixes = roll_affixes(rng, rarity)
        w_item = create_item(
            catalog,
            w_def_id,
            rarity=rarity,
            item_level=item_level,
            quantity=1,
            affixes=affixes,
            uid=str(uuid.uuid4()),
        )
        generated.append(w_item)

        # 2) Material bundle (qty: 3~6)
        m_def_id = rng.choice(MATERIAL_DEF_IDS)
        m_qty = rng.randint(3, 6)
        m_item = create_item(
            catalog,
            m_def_id,
            rarity="common",
            item_level=item_level,
            quantity=m_qty,
            affixes=[],
            uid=str(uuid.uuid4()),
        )
        generated.append(m_item)
        return generated

    # Normal or Elite
    if tier == "normal":
        if rng.random() > DROP_CHANCE_NORMAL:
            return []  # 80% no drop
        rarity_weights = RARITY_WEIGHTS["normal"]
    elif tier == "elite":
        rarity_weights = RARITY_WEIGHTS["elite"]
    else:
        rarity_weights = RARITY_WEIGHTS["normal"]

    # 60% weapon, 40% material
    is_weapon = rng.random() < TYPE_WEIGHTS["weapon"]

    if is_weapon:
        rarity = _weighted_choice(rng, rarity_weights)
        w_def_id = rng.choice(WEAPON_DEF_IDS)
        affixes = roll_affixes(rng, rarity)
        item = create_item(
            catalog,
            w_def_id,
            rarity=rarity,
            item_level=item_level,
            quantity=1,
            affixes=affixes,
            uid=str(uuid.uuid4()),
        )
    else:
        m_def_id = rng.choice(MATERIAL_DEF_IDS)
        m_qty = rng.randint(1, 3)
        item = create_item(
            catalog,
            m_def_id,
            rarity="common",
            item_level=item_level,
            quantity=m_qty,
            affixes=[],
            uid=str(uuid.uuid4()),
        )

    generated.append(item)
    return generated

