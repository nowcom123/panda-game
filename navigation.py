"""Radius-aware local routes layered over the existing cell maze paths."""
import heapq
import math

from constants import CELL_SIZE
from collision import get_nearby_colliders, resolve_collision
from world_gen import find_cell_path


def segment_clear(start, end, colliders, radius):
    """Test a swept circle, including rounded box corners and small blockers."""
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    length_sq = dx * dx + dy * dy
    clearance_sq = max(0.0, radius - 1e-6) ** 2
    for left, bottom, right, top in colliders:
        if (max(x, end[0]) + radius < left or min(x, end[0]) - radius > right
                or max(y, end[1]) + radius < bottom or min(y, end[1]) - radius > top):
            continue
        # Segment intersects the rectangle itself.
        lo, hi = 0.0, 1.0
        for value, delta, lower, upper in ((x, dx, left, right), (y, dy, bottom, top)):
            if abs(delta) < 1e-12:
                if not lower <= value <= upper:
                    lo, hi = 1.0, 0.0
                    break
            else:
                a, b = (lower - value) / delta, (upper - value) / delta
                lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if lo <= hi:
            return False
        # Otherwise the minimum distance is at an endpoint or a box corner.
        for ex, ey in (start, end):
            qx, qy = max(left, min(ex, right)), max(bottom, min(ey, top))
            if (ex - qx) ** 2 + (ey - qy) ** 2 < clearance_sq:
                return False
        if length_sq:
            for cx, cy in ((left, bottom), (left, top), (right, bottom), (right, top)):
                t = max(0.0, min(1.0, ((cx - x) * dx + (cy - y) * dy) / length_sq))
                if (cx - x - t * dx) ** 2 + (cy - y - t * dy) ** 2 < clearance_sq:
                    return False
    return True


def local_route(start, goal, colliders, radius):
    """Shortest visible corner route; every edge clears the full body radius."""
    if segment_clear(start, goal, colliders, radius):
        return [goal]
    padding = radius + 0.08
    bounds = (min(start[0], goal[0]) - CELL_SIZE / 2,
              min(start[1], goal[1]) - CELL_SIZE / 2,
              max(start[0], goal[0]) + CELL_SIZE / 2,
              max(start[1], goal[1]) + CELL_SIZE / 2)
    nodes = [start, goal]
    for left, bottom, right, top in colliders:
        for point in ((left - padding, bottom - padding), (left - padding, top + padding),
                      (right + padding, bottom - padding), (right + padding, top + padding)):
            if (bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]
                    and point not in nodes and segment_clear(point, point, colliders, radius)):
                nodes.append(point)
    queue = [(0.0, 0)]
    distances, parents = {0: 0.0}, {}
    visited = set()
    while queue:
        cost, current = heapq.heappop(queue)
        if current in visited:
            continue
        if current == 1:
            path = []
            while current:
                path.append(nodes[current])
                current = parents[current]
            return path[::-1]
        visited.add(current)
        for nxt, point in enumerate(nodes):
            if nxt in visited or not segment_clear(nodes[current], point, colliders, radius):
                continue
            candidate = cost + math.dist(nodes[current], point)
            if candidate < distances.get(nxt, float('inf')):
                distances[nxt], parents[nxt] = candidate, current
                heapq.heappush(queue, (candidate, nxt))
    return []


def pursuit_target(monster, chunks, goal, dt, repath_interval=0.35):
    """Return a safe waypoint without consuming doorways before cell entry."""
    start = (monster.pos.x, monster.pos.y)
    radius = getattr(monster, 'col_radius', 0.40)
    recovered = resolve_collision(chunks, *start, 0, 0, radius=radius)
    if math.dist(start, recovered) > 0.001:
        return recovered
    cell = tuple(math.floor(v / CELL_SIZE) for v in start)
    goal_cell = tuple(math.floor(v / CELL_SIZE) for v in goal)
    monster.path_timer -= dt
    if cell == goal_cell:
        monster.path = []
        target = resolve_collision(chunks, *goal, 0, 0, radius=radius)
    else:
        path = monster.path
        if cell in path:
            path = path[path.index(cell):]
        if (not path or path[0] != cell or monster.path_timer <= 0
                or getattr(monster, '_goal_cell', None) != goal_cell):
            path = find_cell_path(cell, goal_cell, max_depth=32)
            monster.path_timer = repath_interval
            monster._goal_cell = goal_cell
        monster.path = path
        if len(path) < 2:
            return start
        nxt = path[1]
        # Cross the boundary before changing to the next doorway.
        target = tuple((cell[i] + nxt[i] + 1) * CELL_SIZE / 2
                       + (nxt[i] - cell[i]) * (radius + 0.15) for i in (0, 1))
    distance = math.dist(start, target)
    colliders = list(dict.fromkeys(get_nearby_colliders(
        chunks, (start[0] + target[0]) / 2, (start[1] + target[1]) / 2,
        distance / 2 + CELL_SIZE / 2 + radius)))
    if segment_clear(start, target, colliders, radius):
        monster._local_path = []
        return target
    route = getattr(monster, '_local_path', [])
    while route and math.dist(start, route[0]) < 0.04:
        route.pop(0)
    monster._local_path_timer = getattr(monster, '_local_path_timer', 0.0) - dt
    if (not route or monster._local_path_timer <= 0
            or math.dist(target, getattr(monster, '_local_goal', start)) > 0.5
            or not segment_clear(start, route[0], colliders, radius)):
        route = local_route(start, target, colliders, radius)
        monster._local_path_timer = repath_interval
        monster._local_goal = target
    monster._local_path = route
    return route[0] if route else start
