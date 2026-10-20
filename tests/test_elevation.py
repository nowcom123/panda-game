"""Unit tests for 3D multi-level platforms, ramps, and monster pursuit navigation."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import Vec3, NodePath
from constants import PLAYER_EYE_HEIGHT, PLAYER_RADIUS, CELL_SIZE
from elevation import (
    Platform, Ramp, get_zone_elevation, get_floor_height,
    get_pursuit_goal, PLATFORM_HEIGHT
)
from collision import get_nearby_colliders
from player_controller import PlayerController


class ElevationSystemTests(unittest.TestCase):
    def test_ramp_height_interpolation(self):
        """경사로(Ramp) 진입부(0.0m)부터 정상부(3.0m)까지 정확한 선형 경사면 높이 계산 검증"""
        ramp = Ramp(
            "test_ramp",
            min_x=10.0, min_y=20.0,
            max_x=16.0, max_y=26.0,
            z_bottom=0.0, z_top=PLATFORM_HEIGHT,
            direction='+y'
        )
        # 진입부 (y = 20.0) -> z = 0.0
        z_entry = ramp.get_z(13.0, 20.0)
        self.assertAlmostEqual(z_entry, 0.0, places=3)

        # 경사로 중간 지점 (y = 23.0) -> z = 1.5
        z_mid = ramp.get_z(13.0, 23.0)
        self.assertAlmostEqual(z_mid, 1.5, places=3)

        # 정상부 (y = 26.0) -> z = 3.0
        z_exit = ramp.get_z(13.0, 26.0)
        self.assertAlmostEqual(z_exit, PLATFORM_HEIGHT, places=3)

    def test_zone_0_0_elevation_structures(self):
        """스폰 구역 (0,0)에 복층 메자닌 플랫폼 및 연결 경사로가 정상 생성되는지 검증"""
        elev = get_zone_elevation(0, 0)
        self.assertIsNotNone(elev)
        self.assertGreater(len(elev['platforms']), 0)
        self.assertGreater(len(elev['ramps']), 0)
        self.assertGreater(len(elev['pillars']), 0)
        self.assertGreater(len(elev['railings']), 0)

        # 플랫폼 높이가 3.0m인지 확인
        for plat in elev['platforms']:
            self.assertEqual(plat.z, PLATFORM_HEIGHT)

    def test_floor_height_lookup(self):
        """get_floor_height가 지면, 경사로, 복층 플랫폼 표면을 정확히 식별하는지 검증"""
        elev = get_zone_elevation(0, 0)
        plat = elev['platforms'][0]
        ramp = elev['ramps'][0]

        # 1. 일반 지면 (경사로/플랫폼 없는 곳)
        ground_z, s_type = get_floor_height(0.0, 0.0)
        self.assertAlmostEqual(ground_z, 0.0, places=3)
        self.assertEqual(s_type, 'ground')

        # 2. 복층 플랫폼 상단 (curr_z >= 1.5m)
        plat_z, s_type = get_floor_height(plat.center_x, plat.center_y, current_z=2.5)
        self.assertAlmostEqual(plat_z, PLATFORM_HEIGHT, places=3)
        self.assertEqual(s_type, 'platform')

        # 3. 복층 플랫폼 하부 통로 (curr_z < 1.5m 인 경우 지면 통과 가능)
        under_z, s_type = get_floor_height(plat.center_x, plat.center_y, current_z=0.2)
        self.assertAlmostEqual(under_z, 0.0, places=3)
        self.assertEqual(s_type, 'underpass')

        # 4. 경사로 중간 지점
        mid_rx = (ramp.min_x + ramp.max_x) * 0.5
        mid_ry = (ramp.min_y + ramp.max_y) * 0.5
        ramp_z, s_type = get_floor_height(mid_rx, mid_ry)
        self.assertAlmostEqual(ramp_z, 1.5, places=2)
        self.assertEqual(s_type, 'ramp')

    def test_monster_3d_pursuit_goal_routing(self):
        """몬스터가 고지대(2층)에 있는 플레이어를 추적할 때 경사로 진입로로 웨이포인트 우회하는지 검증"""
        elev = get_zone_elevation(0, 0)
        plat = elev['platforms'][0]
        ramp = elev['ramps'][0]

        # 플레이어는 2층 복층 플랫폼 중앙에 위치 (Z = 3.0m)
        player_pos = Vec3(plat.center_x, plat.center_y, PLATFORM_HEIGHT)

        # 몬스터는 1층 지면에 위치 (Z = 0.0m)
        monster_pos = Vec3(plat.center_x - 10.0, plat.center_y - 10.0, 0.0)

        # AI 목표점 질의
        gx, gy = get_pursuit_goal(monster_pos, player_pos)

        ent_x, ent_y = ramp.get_entrance_pos()
        dist_to_entrance = math.hypot(gx - ent_x, gy - ent_y)
        self.assertLess(dist_to_entrance, 1.5)

    def test_monster_drop_down_ambush_from_high_ground(self):
        """몬스터가 2층 가장자리에 있고 플레이어가 1층 근거리에 있을 때는 바로 낙하/기습 추적할 수 있는지 검증"""
        elev = get_zone_elevation(0, 0)
        plat = elev['platforms'][0]

        # 몬스터가 2층 플랫폼 가장자리 근처에 위치
        monster_pos = Vec3(plat.center_x, plat.min_y + 1.0, PLATFORM_HEIGHT)
        # 플레이어가 1층 지면 근거리 (3m 거리)에 위치
        player_pos = Vec3(plat.center_x, plat.min_y - 2.0, 0.0)

        gx, gy = get_pursuit_goal(monster_pos, player_pos)
        # 4.8m 이내이므로 바로 플레이어를 향해 뛰어내림
        self.assertAlmostEqual(gx, player_pos.x, places=3)
        self.assertAlmostEqual(gy, player_pos.y, places=3)

    def test_collider_elevation_filtering(self):
        """2층 안전 난간은 지면(Z=0)에서는 충돌하지 않고 2층(Z=3)에서만 충돌 방어하는지 검증"""
        elev = get_zone_elevation(0, 0)
        railings = elev['railings']
        self.assertGreater(len(railings), 0)

        r_min_x, r_min_y, r_max_x, r_max_y = railings[0]
        mid_rx = (r_min_x + r_max_x) * 0.5
        mid_ry = (r_min_y + r_max_y) * 0.5

        gx = int(math.floor(mid_rx / CELL_SIZE))
        gy = int(math.floor(mid_ry / CELL_SIZE))

        # 청크 격자 공간 분할 목(mock) 설정
        fake_chunk = SimpleNamespace(
            cell_colliders={},
            cell_colliders_elevated={(gx, gy): [(r_min_x, r_min_y, r_max_x, r_max_y)]},
            cell_colliders_ground={}
        )
        chunks = {(0, 0): fake_chunk}

        # 1. 지면 높이(curr_z = 0.5)에서 충돌체 검색 -> 2층 난간은 검색되지 않아야 함
        ground_cols = get_nearby_colliders(chunks, mid_rx, mid_ry, search_dist=2.0, curr_z=0.5)
        found_on_ground = any(abs(c[0] - r_min_x) < 0.01 and abs(c[1] - r_min_y) < 0.01 for c in ground_cols)
        self.assertFalse(found_on_ground)

        # 2. 2층 높이(curr_z = 3.0)에서 충돌체 검색 -> 2층 난간이 검색되어야 함
        elev_cols = get_nearby_colliders(chunks, mid_rx, mid_ry, search_dist=2.0, curr_z=3.0)
        found_railing = any(abs(c[0] - r_min_x) < 0.01 and abs(c[1] - r_min_y) < 0.01 for c in elev_cols)
        self.assertTrue(found_railing)

    def test_ramp_side_walls_block_lateral_entry(self):
        """경사로 측면 벽체가 1층 지면(Z=0) 및 경사로 위(Z=1.5) 모두에서 횡방향 침투를 100% 차단하는지 검증"""
        from collision import resolve_collision
        from chunk import _register_multi_cell_collider
        import collections

        elev = get_zone_elevation(0, 0)
        ramp = elev['ramps'][0]
        blockers = elev['ramp_blockers']
        self.assertGreater(len(blockers), 0)

        # 공간 인덱스 목(mock) 청크 구성
        cell_dict = collections.defaultdict(list)
        for b in blockers:
            _register_multi_cell_collider(cell_dict, b)

        fake_chunk = SimpleNamespace(
            cell_colliders=cell_dict,
            cell_colliders_ground=cell_dict,
            cell_colliders_elevated=cell_dict
        )
        chunks = {(0, 0): fake_chunk}

        # 1. 1층 지면(curr_z = 0.0)에서 경사로 서쪽 바깥(x = 0.0, y = 9.0)에서 경사로 내부(x = 2.6)로 침투 시도
        # 경사로 서측 벽은 x = 0.6 근처(두께 포함 0.42 ~ 0.78)
        start_x = 0.1
        start_y = 9.0
        delta_x = 2.0  # +X 방향 침투 시도
        res_x, res_y = resolve_collision(chunks, start_x, start_y, delta_x, 0.0, radius=PLAYER_RADIUS, curr_z=0.0)
        # 경사로 서측 벽에 가로막혀 벽 안쪽(x > 0.42 - PLAYER_RADIUS)으로 들어가지 못해야 함
        self.assertLess(res_x, 0.6)

        # 2. 경사로 위(curr_z = 1.5)에서 경사로 내부(x = 2.6, y = 9.0)에서 동쪽 바깥(x = 5.0)으로 탈출/추락 시도
        # 경사로 동측 벽은 x = 4.6 근처
        start_x2 = 2.6
        delta_x2 = 2.5 # +X 방향 벽 뚫기 시도
        res_x2, res_y2 = resolve_collision(chunks, start_x2, start_y, delta_x2, 0.0, radius=PLAYER_RADIUS, curr_z=1.5)
        # 경사로 동측 벽에 가로막혀 벽 바깥으로 통과하지 못해야 함
        self.assertLess(res_x2, 4.6)

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


class Player3DMovementTests(unittest.TestCase):
    def test_player_walks_up_ramp_and_stands_on_platform(self):
        """플레이어가 경사로를 따라 걸어 올라갈 때 고도가 0m에서 3m(플랫폼 바닥)까지 연속적으로 상승하고 안착하는지 검증"""
        elev = get_zone_elevation(0, 0)
        ramp = elev['ramps'][0]

        camera = NodePath("player-camera")
        # 경사로 진입부 시작 위치
        ent_x, ent_y = ramp.get_entrance_pos()
        camera.setPos(ent_x, ent_y, PLAYER_EYE_HEIGHT)

        player = PlayerController(SimpleNamespace(game_state="PLAYING"), None,
                                  camera, None, None, Mock())

        # 북향(+Y)으로 이동: Panda3D에서 북쪽(+Y)은 heading=0.0
        player.heading = 0.0
        player.key_map.update(w=1, shift=0)

        dt = 0.05
        prev_z = camera.getZ()
        # 경사로 중간을 거쳐 2층 플랫폼 안착까지 16 프레임 이동 (y = 6.6 -> y = 13.8)
        for _ in range(16):
            player.update(dt, {})
            cur_z = camera.getZ()
            self.assertGreaterEqual(cur_z, prev_z - 0.01)
            prev_z = cur_z

        # 2층 플랫폼 바닥(3.0m) + 눈높이(1.7m) = 4.7m에 도달했는지 확인
        self.assertAlmostEqual(camera.getZ(), PLATFORM_HEIGHT + PLAYER_EYE_HEIGHT, places=1)
        self.assertAlmostEqual(player.current_floor_z, PLATFORM_HEIGHT, places=1)

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


if __name__ == "__main__":
    unittest.main()
