"""Role goals only; the director retains pathfinding, collision and attacks."""
import math
from collision import get_nearby_colliders
from navigation import segment_clear


def approach_goal(monster, role, chunks, player, dt, has_los):
    mx, my = monster.pos.x, monster.pos.y
    px, py = player
    dx, dy = px-mx, py-my
    distance = math.hypot(dx, dy)
    if distance < .01 or not has_los:
        return player, False
    nx, ny = dx/distance, dy/distance
    radius = getattr(monster, 'col_radius', .4)

    def clear(goal):
        cols = get_nearby_colliders(chunks, mx, my,
            search_dist=math.dist((mx, my), goal)+radius+1, curr_z=monster.pos.z)
        return segment_clear((mx, my), goal, cols, radius)

    if role == 'ranged':
        # Hysteresis prevents alternating approach/retreat at one boundary.
        retreating = getattr(monster, '_role_retreating', False)
        retreating = distance < (12 if retreating else 9)
        monster._role_retreating = retreating
        if retreating:
            for angle in (0, .7, -.7):
                c, s = math.cos(angle), math.sin(angle)
                goal = (mx-(nx*c-ny*s)*3, my-(nx*s+ny*c)*3)
                if clear(goal):
                    return goal, False
            return (mx, my), True
        if distance <= 17:
            return (mx, my), True
        return player, False

    if role == 'flanker' and distance > 2.5:
        phase = getattr(monster, '_approach_phase', 'flank')
        timer = getattr(monster, '_approach_timer', 0.0)+dt
        side = getattr(monster, '_approach_side', 1)
        if phase == 'flank':
            goal = (px-nx*4-ny*side*4, py-ny*4+nx*side*4)
            if timer >= 1.4 or math.dist((mx, my), goal) < 1:
                phase, timer = 'warn', 0.0
                monster._approach_warning = True
            elif clear(goal):
                monster._approach_timer = timer
                return goal, False
            else:
                # Tight corridors use the existing route instead of circling a wall.
                monster._approach_timer = timer
                return player, False
        if phase == 'warn' and timer >= .45:
            phase, timer = 'chase', 0.0
        elif phase == 'chase' and timer >= 2.2:
            phase, timer = 'flank', 0.0
        monster._approach_phase, monster._approach_timer = phase, timer
        return ((mx, my), True) if phase == 'warn' else (player, False)
    return player, False
