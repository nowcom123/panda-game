"""Shared, real-time envelope for the slow-motion presentation."""
SLOW_SCALE = 0.25
ATTACK_SECONDS = 0.10
RELEASE_SECONDS = 0.30


def intensity(remaining, elapsed):
    return max(0.0, min(1.0, elapsed / ATTACK_SECONDS,
                        remaining / RELEASE_SECONDS))


def world_scale(strength):
    return 1.0 - (1.0 - SLOW_SCALE) * max(0.0, min(1.0, strength))


def effect_scale(game):
    strength = getattr(game, 'bullet_time_strength', None)
    if strength is None:
        strength = float(getattr(game, 'bullet_time_timer', 0.0) > 0.0)
    return world_scale(strength)
