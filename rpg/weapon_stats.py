"""Resolve rolled equipment stats without modifying shared weapon balance."""
from copy import deepcopy

from rpg.items import ValidationError


def resolve_weapon_config(base_configs, catalog, item):
    """Return an independent effective config; perks are applied by combat later.

    Rarity and item level are descriptive in phase 2, not hidden damage bonuses.
    reload_time_mult below one makes reloading faster.
    """
    item.validate(catalog)
    definition = catalog[item.definition_id]
    if definition.kind != 'weapon':
        raise ValidationError('Only weapons have combat stats')
    if definition.weapon_key not in base_configs:
        raise ValidationError(f'No base weapon config for {definition.weapon_key!r}')
    config = deepcopy(base_configs[definition.weapon_key])
    fields = {'damage_mult': 'damage', 'reload_time_mult': 'reload_time',
              'weakpoint_mult': 'headshot_mult'}
    for affix in item.affixes:
        config[fields[affix.id]] *= affix.value
    return config
