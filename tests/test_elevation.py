"""Flat-world regressions after removing ramps and raised platforms."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from panda3d.core import NodePath, Texture, Vec3
from constants import PLAYER_EYE_HEIGHT
from chunk import Chunk
from player_controller import PlayerController
from elevation import get_floor_height, get_pursuit_goal, get_chunk_elevation, get_zone_elevation


class FlatWorldTests(unittest.TestCase):
    def test_former_ramp_and_platform_positions_are_ground(self):
        with patch('elevation.get_zone_elevation', side_effect=AssertionError('Unexpected zone scan')):
            for x, y in ((2.6, 9), (6, 14.8), (9, 12), (-18, 18), (36, 36)):
                for z in (None, 0, 1.5, 3, 8):
                    self.assertEqual(get_floor_height(x, y, z), (0.0, 'ground'))
            self.assertEqual(get_pursuit_goal(Vec3(2, 3, 0), Vec3(6, 14, 3)), (6, 14))

    def test_no_elevated_geometry_or_hidden_colliders(self):
        texture = Texture('flat-world-test')
        for cx, cy in ((0, 0), (-1, 0), (1, 1)):
            self.assertIsNone(get_zone_elevation(cx * 2, cy * 2))
            self.assertTrue(all(not values for values in get_chunk_elevation(cx, cy).values()))
            chunk = Chunk(None, cx, cy, texture, texture, texture)
            try:
                self.assertFalse(chunk.cell_colliders_ground)
                self.assertFalse(chunk.cell_colliders_elevated)
                # Untextured cubes were used for ramp walls, supports and railings.
                self.assertTrue(chunk.node.find('**/unit_cube').isEmpty())
                self.assertTrue(chunk.node.find('**/ramp_surf*').isEmpty())
                self.assertTrue(chunk.node.find('**/plat_floor*').isEmpty())
            finally:
                chunk.destroy()

    def test_player_crosses_former_ramp_on_flat_ground(self):
        camera = NodePath('player-camera')
        camera.setPos(2.6, 6.6, PLAYER_EYE_HEIGHT)
        player = PlayerController(SimpleNamespace(game_state='PLAYING'), None,
                                  camera, None, None, Mock())
        player.key_map.update(w=1, shift=0)
        for _ in range(20):
            player.update(.05, {})
            self.assertAlmostEqual(camera.getZ(), PLAYER_EYE_HEIGHT, places=5)
            self.assertEqual(player.current_floor_z, 0.0)
        self.assertGreater(camera.getY(), 12)

    def test_multi_cell_collider_spans_multiple_cells(self):
        """6m 길이의 경사로 벽체가 경계에 걸칠 때 걸쳐진 모든 그리드 셀(gx, gy)에 등록되는지 검증"""
        from chunk import _register_multi_cell_collider
        import collections

        target = collections.defaultdict(list)
        # y = 6.0 ~ 12.0 범위의 벽체 (CELL_SIZE = 6.0이므로 gy=1, gy=2 모두에 걸침)
        box = (0.42, 6.0, 0.78, 12.0)
        _register_multi_cell_collider(target, box)

        # gy=1 및 gy=2 셀 모두에 등록되어야 함
        self.assertIn((0, 1), target)
        self.assertIn((0, 2), target)
        self.assertIn(box, target[(0, 1)])
        self.assertIn(box, target[(0, 2)])


    def test_player_jump_and_gravity_landing(self):
        """Space 키를 눌렀을 때 3D 도약 후 중력에 의해 지면으로 안전하게 착지하는지 검증"""
        camera = NodePath("player-camera")
        camera.setPos(5.0, 5.0, PLAYER_EYE_HEIGHT)
        player = PlayerController(SimpleNamespace(game_state="PLAYING"), None,
                                  camera, None, None, Mock())

        # 일반 보행/정지 상태에서 Space 입력
        player.key_map.update(w=0, s=0, a=0, d=0, shift=0)
        player.trigger_slide()

        self.assertFalse(player.is_sliding)
        self.assertFalse(player.is_grounded)
        self.assertAlmostEqual(player.vertical_vel, 7.5, places=2)

        # 0.8초 동안 중력 시뮬레이션
        dt = 0.05
        max_height = 0.0
        for _ in range(25):
            player.update(dt, {})
            max_height = max(max_height, camera.getZ())

        # 점프 정점 높이가 기본 눈높이(1.7m)보다 최소 0.8m 이상 높아야 함
        self.assertGreater(max_height, PLAYER_EYE_HEIGHT + 0.8)

        # 최종적으로 지면에 착지했는지 검증
        self.assertTrue(player.is_grounded)
        self.assertAlmostEqual(camera.getZ(), PLAYER_EYE_HEIGHT, places=2)


if __name__ == '__main__':
    unittest.main()
