"""Stage growth shared by boss spawning, movement and attacks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BossScaling:
    health: float
    limb_health: float
    damage: float
    movement: float


def scaling_for_stage(stage):
    depth = max(0, int(stage) - 3)
    return BossScaling(1 + .30 * depth, 1 + .18 * depth,
                       1 + min(.60, .08 * depth),
                       1 + min(.15, .02 * depth))


def apply_boss_scaling(boss, stage):
    """Initialize a newly spawned boss once; never heal it on repeated calls."""
    if getattr(boss, '_stage_scaling_applied', False):
        return
    scale = scaling_for_stage(stage)
    boss.stage_level = max(1, int(stage))
    boss.damage_scale = scale.damage
    boss.movement_scale = scale.movement
    boss.limb_health_scale = scale.limb_health
    boss.max_hp *= scale.health
    boss.hp = boss.max_hp
    boss.leg_hp = [hp * scale.limb_health for hp in boss.leg_hp]
    boss.attack_damage *= scale.damage
    boss.speed *= scale.movement
    boss._stage_scaling_applied = True


def boss_damage(boss, base_damage):
    return base_damage * getattr(boss, 'damage_scale', 1.0)


def movement_multiplier(monster, ordinary_multiplier):
    # Spawned bosses already include their bounded stage movement growth.
    return 1.0 if getattr(monster, '_stage_scaling_applied', False) else ordinary_multiplier
