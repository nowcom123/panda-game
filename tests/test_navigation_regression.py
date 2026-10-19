"""Multi-frame regression checks against production steering and collision."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from constants import CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, MAP_MIN_CHUNK, MAP_MAX_CHUNK, WALL_THICKNESS
from collision import resolve_collision
from navigation import pursuit_target, segment_clear


def scene(boxes):
    chunks = {}
    for box in boxes:
        for gx in range(math.floor(box[0] / CELL_SIZE), math.floor(box[2] / CELL_SIZE) + 1):
            for gy in range(math.floor(box[1] / CELL_SIZE), math.floor(box[3] / CELL_SIZE) + 1):
                chunk = chunks.setdefault((gx // CHUNK_CELLS, gy // CHUNK_CELLS), SimpleNamespace(cell_colliders={}))
                chunk.cell_colliders.setdefault((gx, gy), []).append(box)
    return chunks


def open_maze(start, goal, **kwargs):
    route = [start]
    x, y = start
    while x != goal[0]:
        x += 1 if goal[0] > x else -1
        route.append((x, y))
    while y != goal[1]:
        y += 1 if goal[1] > y else -1
        route.append((x, y))
    return route


class NavigationRegressionTests(unittest.TestCase):
    def chase(self, start, goal, boxes, radius=.4, dt=1 / 60):
        chunks = scene(boxes)
        monster = SimpleNamespace(pos=SimpleNamespace(x=start[0], y=start[1]), col_radius=radius, path=[], path_timer=0.0)
        with patch('navigation.find_cell_path', side_effect=open_maze):
            for _ in range(math.ceil(8 / dt)):
                before = (monster.pos.x, monster.pos.y)
                if math.dist(before, goal) < .10:
                    return
                target = pursuit_target(monster, chunks, goal, dt)
                distance = math.dist(before, target)
                if distance > .001:
                    step = min(distance, 6.0 * dt)
                    after = resolve_collision(chunks, *before, (target[0] - before[0]) * step / distance,
                                              (target[1] - before[1]) * step / distance, radius=radius)
                    self.assertTrue(segment_clear(before, after, boxes, radius - .0001), f'Crossed: {before} -> {after}')
                    monster.pos.x, monster.pos.y = after
        self.fail(f'Chase stalled: {start} -> {goal}, ended {(monster.pos.x, monster.pos.y)}')

    def test_pillar_chases_reach_player_with_full_clearance(self):
        for start, goal in (((10.5, 9), (7.5, 9)), ((9, 7.5), (9, 10.5)),
                            ((7.4, 7.4), (10.6, 10.6)), ((10.6, 7.4), (7.4, 10.6))):
            for radius in (.35, .40, .55):
                for dt in (1 / 30, 1 / 60, 1 / 144):
                    with self.subTest(start=start, radius=radius, dt=dt):
                        self.chase(start, goal, [(8.4, 8.4, 9.6, 9.6)], radius, dt)

    def test_pillar_cell_exit_all_directions(self):
        for start, goal in (((9, 7.5), (9, 14)), ((9, 10.5), (9, 4)),
                            ((7.5, 9), (14, 9)), ((10.5, 9), (4, 9))):
            for dt in (1 / 30, 1 / 144):
                with self.subTest(start=start, dt=dt):
                    self.chase(start, goal, [(8.4, 8.4, 9.6, 9.6)], .55, dt)

    def test_doorway_near_boundary_does_not_stop_or_rebound(self):
        for start, goal in (((5.98, 3), (9, 3)), ((6.03, 3), (3, 3)),
                            ((3, 5.98), (3, 9)), ((3, 6.03), (3, 3))):
            with self.subTest(start=start):
                self.chase(start, goal, [])

    def test_custom_same_cell_blocker_and_door_frames(self):
        self.chase((1, 3), (5, 3), [(2.8, 2.4, 3.2, 3.6)])
        self.chase((4, 1), (9, 3), [(5.8, 0, 6.2, 2), (5.8, 4, 6.2, 6)], .55)

    def test_fast_movement_cannot_tunnel_through_interior_walls(self):
        for start, delta, box, axis in (
            ((1, 3), (4, 0), (2.9, 0, 3.1, 6), 0),
            ((3, 1), (0, 4), (0, 2.9, 6, 3.1), 1),
            ((1, 1), (4, 4), (2.9, 0, 3.1, 6), 0)):
            with self.subTest(delta=delta):
                end = resolve_collision(scene([box]), *start, *delta, radius=.4)
                self.assertLessEqual(end[axis], 2.5 + 1e-6)

    def test_empty_chunks_still_obey_world_bounds(self):
        low = MAP_MIN_CHUNK * CHUNK_SIZE + WALL_THICKNESS / 2 + .4
        high = (MAP_MAX_CHUNK + 1) * CHUNK_SIZE - WALL_THICKNESS / 2 - .4
        self.assertGreaterEqual(resolve_collision({}, low + .1, 0, -50, 0, .4)[0], low)
        self.assertLessEqual(resolve_collision({}, high - .1, 0, 50, 0, .4)[0], high)

    def test_penetration_recovery_and_small_obstacle_clearance(self):
        box = (2.9, 2.9, 3.1, 3.1)
        end = resolve_collision(scene([box]), 3, 3, 0, 0, .4)
        self.assertTrue(segment_clear(end, end, [box], .4 - .0001))
        self.assertFalse(segment_clear((2, 3), (4, 3), [box], .4))


if __name__ == '__main__':
    unittest.main()
