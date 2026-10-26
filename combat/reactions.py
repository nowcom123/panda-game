"""Engine-independent tuning for enemy reactions and their player counters.

These helpers do not roll RNG, apply damage or start animations. The combat
integration owns one reaction decision per target per weapon discharge.
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ReactionProfile:
    mode: str
    chance: float
    cooldown: float
    duration: float
    reduction: float = 0.0


REACTION_PROFILES = MappingProxyType({
    'hound': ReactionProfile('evade', .35, 0.0, .35),
    'witch': ReactionProfile('evade', .25, 4.5, .25),
    'skeleton': ReactionProfile('evade', .20, 5.0, .45),
    'serpent': ReactionProfile('guard', .30, 6.0, .40, .60),
    'golem': ReactionProfile('guard', .35, 8.0, .60, .65),
})


def counter_stats(precision_level=0, guard_break_level=0):
    """Perk levels 1/2/3 give 5/10/15 pp evade suppression and 10/20/30% penetration."""
    return {
        'evasion_suppression': min(3, max(0, int(precision_level))) * .05,
        'guard_penetration': min(3, max(0, int(guard_break_level))) * .10,
    }


def reaction_chance(profile, evasion_suppression=0.0):
    """Precision counters evasion only; it never turns an aimed shot into a miss."""
    suppression = max(0.0, min(1.0, evasion_suppression)) if profile.mode == 'evade' else 0.0
    return max(0.0, min(1.0, profile.chance - suppression))


def guarded_damage(damage, reduction, guard_penetration=0.0):
    """Penetration weakens a successful guard, without changing its activation chance."""
    reduction = max(0.0, min(1.0, reduction))
    penetration = max(0.0, min(1.0, guard_penetration))
    return max(0.0, damage) * (1.0 - reduction * (1.0 - penetration))
