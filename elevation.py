"""Flat-world surface queries shared by movement, props and monster AI.

Elevated platforms, ramps, supports and railings are no longer generated.
Queries intentionally do no zone scans or procedural geometry work.
"""


def get_floor_height(x, y, current_z=None):
    """Return the ground plane, including beneath jumping/falling actors."""
    return 0.0, 'ground'


def get_pursuit_goal(monster_pos, player_pos):
    """Pursue the player directly in XY; navigation handles maze walls."""
    return player_pos.x, player_pos.y


def get_zone_elevation(mx, my):
    """No raised architecture remains in any zone."""
    return None


def get_ramp_for_pos(x, y):
    return None


def get_chunk_elevation(cx, cy):
    """Empty compatibility result for map inspection tools."""
    return {key: [] for key in ('platforms', 'ramps', 'pillars',
                               'railings', 'ramp_blockers')}
