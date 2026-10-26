"""RPG Foundation package: item data, player profile, and atomic save store."""

from rpg.items import (
    ItemAffix,
    ItemDefinition,
    ItemInstance,
    ItemNotFoundError,
    RPGError,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    create_item,
    get_default_catalog_path,
    load_catalog,
)
from rpg.profile import (
    CURRENT_SCHEMA_VERSION,
    PlayerProfile,
    new_profile,
)
from rpg.save_store import (
    LoadResult,
    SaveStore,
    get_default_save_path,
)
from rpg.session import (
    RPGSession,
    STARTER_UNLOCK_KEY,
)
from rpg.weapon_stats import (
    resolve_weapon_config,
)
from rpg.loot import (
    roll_loot,
    roll_affixes,
)
from rpg.run_loot import (
    RunLootBag,
    MAX_RUN_LOOT_CAPACITY,
)
from rpg.characters import (
    CharacterSummary,
    CharacterList,
    CharacterManager,
    validate_character_name,
)
from rpg.hangul_util import (
    eng_to_hangul,
    get_clipboard_text,
    set_clipboard_text,
)
def __getattr__(name):
    # Keep data/save imports independent of the rendering engine.
    if name in ('LootWorldItem', 'LootWorldManager'):
        from rpg import loot_world
        return getattr(loot_world, name)
    if name == 'WorkshopUIPanel':
        from rpg import workshop_ui
        return getattr(workshop_ui, name)
    if name == 'EquipmentUIPanel':
        from rpg import equipment_ui
        return getattr(equipment_ui, name)
    if name == 'RunLootUIPanel':
        from rpg import run_loot_ui
        return getattr(run_loot_ui, name)
    raise AttributeError(name)

__all__ = [
    "ItemAffix",
    "ItemDefinition",
    "ItemInstance",
    "ItemNotFoundError",
    "RPGError",
    "SaveCorruptedError",
    "UnsupportedSaveVersion",
    "ValidationError",
    "create_item",
    "get_default_catalog_path",
    "load_catalog",
    "CURRENT_SCHEMA_VERSION",
    "PlayerProfile",
    "new_profile",
    "LoadResult",
    "SaveStore",
    "get_default_save_path",
    "RPGSession",
    "STARTER_UNLOCK_KEY",
    "resolve_weapon_config",
    "roll_loot",
    "roll_affixes",
    "RunLootBag",
    "MAX_RUN_LOOT_CAPACITY",
    "LootWorldItem",
    "LootWorldManager",
    "CharacterSummary",
    "CharacterList",
    "CharacterManager",
    "validate_character_name",
    "EquipmentUIPanel",
    "RunLootUIPanel",
    "WorkshopUIPanel",
    "eng_to_hangul",
    "get_clipboard_text",
    "set_clipboard_text",
]

