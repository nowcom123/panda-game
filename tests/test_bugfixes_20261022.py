"""
tests/test_bugfixes_20261022.py
Unit tests verifying the 6 targeted bugfixes from support/antigravity/20261022-bugfixes/INSTRUCTIONS.md:
1. User FOV setting persistence across ADS, bullet time, pause menus, and stage transitions
2. Boss Ground Shockwave fatal damage immediate game over handling
3. Elite monster visual scale vs raycast hitbox & collision radius consistency across 5 monster types
4. Bullet time preservation across paused/shop/inventory/AAR menu states
5. Escape portal defense reinforcement timer reset on stage/restart/zone exit
6. Developer cheat hotkeys (F5-F8) and rankings record isolation from test mode
"""

import math
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from panda3d.core import NodePath, Vec3

from ui_manager import UIManager
from combat_system import CombatSystem
from monster_director import MonsterDirector
from monster import (
    TallSkeletonMonster, AbominableMudOrc,
    AlluringAshWitch, SkeletalDobermanHellhound, LongBlackSerpent,
    CableOverlordBoss
)
from spawner import (
    apply_elite_mutation, is_spawn_position_safe,
    get_gate_corridor_candidates, spawn_reinforcement_monster,
    get_monster_collision_radius
)
from collision import register_custom_collider, clear_custom_colliders
from escape_portal import EscapePortalManager
from game import LiminalInfiniteLoop
from player_controller import PlayerController
from perks import get_perk_level
from gate_wave import GateWaveManager, GateWaveConfig


class TestBug1FovPersistence(unittest.TestCase):
    """Bug 1: 사용자 FOV 설정 유지 및 ADS/불릿타임 정상 복귀 검증"""

    def setUp(self):
        self.root = NodePath("test_root")

    def tearDown(self):
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    def test_fov_adjust_and_combat_update_cycle(self):
        """기본 FOV를 105도로 변경 후 ADS, 불릿타임 적용/해제 시 정상 복귀 검증"""
        mock_lens = Mock()
        mock_lens.getFov.return_value = (96.0, 60.0)

        mock_base = SimpleNamespace(
            camLens=mock_lens,
            base_fov=96.0,
            bullet_time_timer=0.0
        )
        mock_base.game = mock_base

        ui = UIManager.__new__(UIManager)
        ui.base = mock_base
        ui.txt_fov_val = Mock()

        # FOV 96도에서 +9도 변경 -> 105.0도
        ui._adjust_setting("fov", +9.0)
        self.assertEqual(mock_base.base_fov, 105.0)
        mock_lens.setFov.assert_called_with(105.0)
        ui.txt_fov_val.setText.assert_called_with("105°")

        # 전투 루프에서 ADS alpha 및 불릿타임에 따른 동적 FOV 계산 검증
        cam_np = self.root.attachNewNode("cam_node")
        combat = CombatSystem(mock_base, self.root, cam_np, self.root, None, Mock())
        combat.current_weapon = "PISTOL"

        # 1) 비조준 (ads_alpha = 0.0): 설정값 105.0도 유지
        combat.is_aiming = False
        combat.ads_alpha = 0.0
        combat.update(0.016, 0.0, 0.0, False, False)
        mock_lens.setFov.assert_called_with(105.0)

        # 2) 정밀조준 (ads_alpha = 1.0): 105.0 * (80.0 / 96.0) = 87.5도
        combat.is_aiming = True
        combat.ads_alpha = 1.0
        combat.update(0.016, 0.0, 0.0, False, False)
        expected_ads = 105.0 * (80.0 / 96.0)
        mock_lens.setFov.assert_called_with(expected_ads)

        # 3) 정밀조준 + 불릿타임 (+6.5도): 87.5 + 6.5 = 94.0도
        mock_base.bullet_time_timer = 2.0
        combat.update(0.016, 0.0, 0.0, False, False)
        mock_lens.setFov.assert_called_with(expected_ads + 6.5)

        # 4) 불릿타임 및 조준 해제 (ads_alpha = 0.0, bullet_time = 0.0): 105.0도로 복귀
        mock_base.bullet_time_timer = 0.0
        combat.is_aiming = False
        combat.ads_alpha = 0.0
        combat.update(0.016, 0.0, 0.0, False, False)
        mock_lens.setFov.assert_called_with(105.0)

        # 5) 설정 범위 클램프 (70도 ~ 115도) 검증
        ui._adjust_setting("fov", +50.0)
        self.assertEqual(mock_base.base_fov, 115.0)
        ui._adjust_setting("fov", -100.0)
        self.assertEqual(mock_base.base_fov, 70.0)


class TestBug2BossShockwave(unittest.TestCase):
    """Bug 2: 보스 지진 충격파 사망 처리 및 분기 분리 검증"""

    def setUp(self):
        self.root = NodePath("test_root")

    def tearDown(self):
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    def test_boss_shockwave_fatal_damage_triggers_game_over(self):
        """치명적인 충격파 피해 시 trigger_game_over 즉시 호출 및 후속 틱 차단 검증"""
        mock_boss = CableOverlordBoss.__new__(CableOverlordBoss)
        mock_boss.hp = 1000
        mock_boss.max_hp = 2000
        mock_boss.phase = 1
        mock_boss.pos = Vec3(0, 0, 0)
        mock_boss.node = NodePath("boss_node")
        mock_boss.shockwave_cooldown = 0.0
        mock_boss.cable_lash_cooldown = 99.0
        mock_boss.is_lashing = False
        mock_boss.stun_timer = 0.0
        mock_boss.dart_cooldown = 99.0
        mock_boss.path_timer = 0.0
        mock_boss.path = []
        mock_boss.update = Mock()
        mock_boss.update_pos = Mock()

        mock_player = SimpleNamespace(
            hp=15.0,
            max_hp=100.0,
            invincible_timer=0.0,
            trigger_quake_shake=Mock(),
            apply_slow=Mock(),
            take_damage=Mock(return_value=True)  # 체력 15 < 피해량 20 -> 사망
        )

        mock_game = SimpleNamespace(
            player=mock_player,
            camera=SimpleNamespace(getX=lambda: 5.0, getY=lambda: 0.0, getZ=lambda: 1.8, getPos=lambda: Vec3(5.0, 0.0, 1.8)),
            boss=mock_boss,
            monsters=[mock_boss],
            corpses=[],
            shockwaves=[],
            render=self.root,
            audio_mgr=Mock(),
            ui_mgr=Mock(),
            trigger_game_over=Mock(),
            spawn_fireball=Mock(),
            spawn_reinforcement_monster=Mock(),
            chunks={},
            current_stage=1,
            blackout_active=False
        )

        director = MonsterDirector(mock_game)
        with patch("monster_director.get_floor_height", return_value=(0.0, "floor")):
            game_ended, closest = director.update_monsters(0.016, 5.0, 0.0)

        self.assertTrue(game_ended, "치명타 시 디렉터 업데이트가 즉시 종료(True)를 반환해야 합니다.")
        mock_game.trigger_game_over.assert_called_once_with(killer=mock_boss, reason="killed")
        mock_player.apply_slow.assert_not_called()
        mock_game.ui_mgr.show_hit_marker.assert_not_called()
        mock_game.spawn_fireball.assert_not_called()

    def test_boss_shockwave_non_fatal_damage_does_not_trigger_game_over(self):
        """비치명 피해 시 슬로우 적용 및 게임오버 미호출 검증"""
        mock_boss = CableOverlordBoss.__new__(CableOverlordBoss)
        mock_boss.hp = 1000
        mock_boss.max_hp = 2000
        mock_boss.phase = 1
        mock_boss.pos = Vec3(0, 0, 0)
        mock_boss.node = NodePath("boss_node")
        mock_boss.shockwave_cooldown = 0.0
        mock_boss.cable_lash_cooldown = 99.0
        mock_boss.is_lashing = False
        mock_boss.stun_timer = 0.0
        mock_boss.dart_cooldown = 99.0
        mock_boss.path_timer = 0.0
        mock_boss.path = []
        mock_boss.update = Mock()
        mock_boss.update_pos = Mock()

        mock_player = SimpleNamespace(
            hp=100.0,
            max_hp=100.0,
            invincible_timer=0.0,
            trigger_quake_shake=Mock(),
            apply_slow=Mock(),
            take_damage=Mock(return_value=False)  # 생존
        )

        mock_game = SimpleNamespace(
            player=mock_player,
            camera=SimpleNamespace(getX=lambda: 5.0, getY=lambda: 0.0, getZ=lambda: 1.8, getPos=lambda: Vec3(5.0, 0.0, 1.8)),
            boss=mock_boss,
            monsters=[mock_boss],
            corpses=[],
            shockwaves=[],
            render=self.root,
            audio_mgr=Mock(),
            ui_mgr=Mock(),
            trigger_game_over=Mock(),
            spawn_fireball=Mock(),
            spawn_reinforcement_monster=Mock(),
            chunks={},
            current_stage=1,
            blackout_active=False
        )

        director = MonsterDirector(mock_game)
        with patch("monster_director.get_floor_height", return_value=(0.0, "floor")):
            game_ended, closest = director.update_monsters(0.016, 5.0, 0.0)

        self.assertFalse(game_ended)
        mock_game.trigger_game_over.assert_not_called()
        mock_player.apply_slow.assert_called_once()
        mock_game.ui_mgr.show_hit_marker.assert_called_once()

    def test_boss_shockwave_with_real_player_take_damage_invincibility(self):
        """실제 PlayerController.take_damage의 무적 타이머에 따른 피해 무효화 및 사망 처리 검증"""
        mock_boss = CableOverlordBoss.__new__(CableOverlordBoss)
        mock_boss.hp = 1000
        mock_boss.max_hp = 2000
        mock_boss.phase = 1
        mock_boss.pos = Vec3(0, 0, 0)
        mock_boss.node = NodePath("boss_node")
        mock_boss.shockwave_cooldown = 0.0
        mock_boss.cable_lash_cooldown = 99.0
        mock_boss.is_lashing = False
        mock_boss.stun_timer = 0.0
        mock_boss.dart_cooldown = 99.0
        mock_boss.path_timer = 0.0
        mock_boss.path = []
        mock_boss.update = Mock()
        mock_boss.update_pos = Mock()

        cam_np = self.root.attachNewNode("cam_node")
        mock_game = SimpleNamespace()
        player = PlayerController(mock_game, None, cam_np, None, None, Mock())
        player.trigger_quake_shake = Mock()
        player.apply_slow = Mock()
        player.audio_mgr = Mock()
        player.ui_mgr = Mock()

        mock_game.player = player
        mock_game.camera = SimpleNamespace(getX=lambda: 5.0, getY=lambda: 0.0, getZ=lambda: 1.8, getPos=lambda: Vec3(5.0, 0.0, 1.8))
        mock_game.boss = mock_boss
        mock_game.monsters = [mock_boss]
        mock_game.corpses = []
        mock_game.shockwaves = []
        mock_game.render = self.root
        mock_game.audio_mgr = Mock()
        mock_game.ui_mgr = Mock()
        mock_game.trigger_game_over = Mock()
        mock_game.spawn_fireball = Mock()
        mock_game.spawn_reinforcement_monster = Mock()
        mock_game.chunks = {}
        mock_game.current_stage = 1
        mock_game.blackout_active = False

        director = MonsterDirector(mock_game)

        # 1) 무적 상태 (invincible_timer = 0.55): 피해 완전 무효화, HP 100 유지
        player.hp = 100.0
        player.invincible_timer = 0.55
        with patch("monster_director.get_floor_height", return_value=(0.0, "floor")):
            game_ended, closest = director.update_monsters(0.016, 5.0, 0.0)

        self.assertFalse(game_ended)
        self.assertEqual(player.hp, 100.0)
        mock_game.trigger_game_over.assert_not_called()

        # 2) 무적 해제 (invincible_timer = 0.0) 및 치명 피해 (hp = 15.0 < 20.0):
        # 실제 take_damage가 True 반환 및 게임오버 호출
        player.hp = 15.0
        player.invincible_timer = 0.0
        mock_boss.shockwave_cooldown = 0.0
        with patch("monster_director.get_floor_height", return_value=(0.0, "floor")):
            game_ended, closest = director.update_monsters(0.016, 5.0, 0.0)

        self.assertTrue(game_ended)
        self.assertEqual(player.hp, 0.0)
        mock_game.trigger_game_over.assert_called_once_with(killer=mock_boss, reason="killed")

        # 3) 무적 해제 및 비치명 피해 (hp = 100.0):
        # 실제 take_damage가 False 반환, 체력 80.0, invincible_timer 0.55 재설정
        player.hp = 100.0
        player.invincible_timer = 0.0
        mock_boss.shockwave_cooldown = 0.0
        mock_game.trigger_game_over.reset_mock()
        player.apply_slow.reset_mock()
        with patch("monster_director.get_floor_height", return_value=(0.0, "floor")):
            game_ended, closest = director.update_monsters(0.016, 5.0, 0.0)

        self.assertFalse(game_ended)
        self.assertEqual(player.hp, 80.0)
        self.assertEqual(player.invincible_timer, 0.55)
        mock_game.trigger_game_over.assert_not_called()
        player.apply_slow.assert_called_once()


class TestBug3EliteHitboxScaling(unittest.TestCase):
    """Bug 3: 5종 몬스터의 정예 변이 외형 배율(1.25배)과 사격/이동 판정 일치 검증"""

    def setUp(self):
        self.root = NodePath("test_root")
        self.mock_game = SimpleNamespace(render=self.root)

    def tearDown(self):
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    def test_tall_skeleton_hitbox_scaling(self):
        """장신 해골 괴물의 일반 vs 정예 판정 배율 및 헤드샷 고도 검증"""
        # 1) 일반 해골
        skel_normal = TallSkeletonMonster(self.root, 10.0, 10.0)
        self.assertAlmostEqual(skel_normal.col_radius, 0.40)
        # 일반 해골 머리 높이는 3.2m(r=0.75), z=4.05 위치의 사격은 빗나감 (3.2 + 0.75 = 3.95)
        hit, dist = skel_normal.is_hit_by_ray(Vec3(10.0, 0.0, 4.05), Vec3(0, 1, 0))
        self.assertFalse(hit, "일반 해골의 상단 외곽 사격은 빗나가야 합니다.")

        # 2) 정예 변이 해골
        skel_elite = TallSkeletonMonster(self.root, 10.0, 10.0)
        apply_elite_mutation(skel_elite, self.mock_game)
        self.assertAlmostEqual(skel_elite.col_radius, 0.40 * 1.25)
        # 1.25배 확대된 정예 해골 머리 높이는 4.0m(r=0.9375), z=4.05 위치의 사격이 명중하고 헤드샷 판정
        hit_e, dist_e = skel_elite.is_hit_by_ray(Vec3(10.0, 0.0, 4.05), Vec3(0, 1, 0))
        self.assertTrue(hit_e, "확대된 정예 해골의 상단 머리에 사격이 명중해야 합니다.")
        self.assertTrue(skel_elite.last_hit_was_head, "정예 해골 머리 피격 시 헤드샷이어야 합니다.")

        # 완전히 벗어난 외곽 사격은 miss
        hit_miss, _ = skel_elite.is_hit_by_ray(Vec3(10.0, 0.0, 6.0), Vec3(0, 1, 0))
        self.assertFalse(hit_miss)

    def test_all_five_monster_types_elite_col_radius_and_headshots(self):
        """정예 변이 가능한 5종 전체의 col_radius 및 실제 머리 조준 시 last_hit_was_head 검증"""
        monsters = [
            (TallSkeletonMonster, 0.40),
            (AbominableMudOrc, 0.45),
            (AlluringAshWitch, 0.38),
            (SkeletalDobermanHellhound, 0.35),
            (LongBlackSerpent, 0.38)
        ]

        for cls, base_col in monsters:
            m_norm = cls(self.root, 5.0, 5.0)
            self.assertAlmostEqual(m_norm.col_radius, base_col)

            m_elite = cls(self.root, 5.0, 5.0)
            apply_elite_mutation(m_elite, self.mock_game)
            self.assertAlmostEqual(m_elite.col_radius, base_col * 1.25)

            # 회전(Heading 45도) 상태에서 각 몬스터의 실제 확대 머리 좌표를 정밀 조준 사격
            h_deg = 45.0
            m_elite.node.setH(h_deg)
            h_rad = math.radians(h_deg)
            sin_h = math.sin(h_rad)
            cos_h = math.cos(h_rad)
            s = 1.25

            if cls == TallSkeletonMonster:
                head_z = m_elite.skull_pivot.getZ(m_elite.node) if hasattr(m_elite, 'skull_pivot') and not m_elite.skull_pivot.isEmpty() else 3.179
                head_y = m_elite.skull_pivot.getY(m_elite.node) if hasattr(m_elite, 'skull_pivot') and not m_elite.skull_pivot.isEmpty() else -1.607
                hx = m_elite.pos.x - sin_h * (head_y * s)
                hy = m_elite.pos.y + cos_h * (head_y * s)
                hz = m_elite.pos.z + (head_z + 0.12) * s
            elif cls == AbominableMudOrc:
                hx = m_elite.pos.x
                hy = m_elite.pos.y
                hz = m_elite.pos.z + 2.30 * s
            elif cls == AlluringAshWitch:
                hx = m_elite.pos.x
                hy = m_elite.pos.y
                hz = m_elite.pos.z + 2.00 * s
            elif cls == SkeletalDobermanHellhound:
                hx = m_elite.pos.x - sin_h * (0.52 * s)
                hy = m_elite.pos.y + cos_h * (0.52 * s)
                hz = m_elite.pos.z + 0.95 * s
            elif cls == LongBlackSerpent:
                head_z = m_elite.head.getZ() if hasattr(m_elite, 'head') and not m_elite.head.isEmpty() else 0.0
                head_y = m_elite.head.getY() if hasattr(m_elite, 'head') and not m_elite.head.isEmpty() else 0.40
                hx = m_elite.pos.x - sin_h * (head_y * s)
                hy = m_elite.pos.y + cos_h * (head_y * s)
                hz = m_elite.pos.z + (head_z + 0.35) * s

            # 머리 중심점을 향해 레이 발사
            hit, dist = m_elite.is_hit_by_ray(Vec3(hx, hy - 5.0, hz), Vec3(0, 1, 0))
            self.assertTrue(hit, f"{cls.__name__} 정예 머리 사격이 명중해야 합니다.")
            self.assertTrue(m_elite.last_hit_was_head, f"{cls.__name__} 정예 머리 명중 시 last_hit_was_head가 True여야 합니다.")

    def test_tall_skeleton_long_range_headshots_all_angles(self):
        """장신 해골 괴물의 원거리(10m~45m) 및 전 방위(0도~315도) 머리 조준 사격 적중 및 헤드샷 판정 검증"""
        for is_elite in (False, True):
            skel = TallSkeletonMonster(self.root, 0.0, 25.0)
            if is_elite:
                apply_elite_mutation(skel, self.mock_game)

            for deg in (0, 45, 90, 135, 180, 225, 270, 315):
                skel.node.setH(deg)
                skull_pos = skel.skull_pivot.getPos(self.root)

                for dist_cam in (10.0, 20.0, 35.0, 45.0):
                    cam_pos = Vec3(0.0, 25.0 - dist_cam, 1.7)
                    ray_dir = Vec3(skull_pos - cam_pos).normalized()
                    hit, dist = skel.is_hit_by_ray(cam_pos, ray_dir)

                    desc = f"{'정예' if is_elite else '일반'} 해골 H={deg}도 거리={dist_cam}m"
                    self.assertTrue(hit, f"{desc}에서 머리 조준 사격이 적중해야 합니다.")
                    self.assertTrue(skel.last_hit_was_head, f"{desc}에서 적중 시 last_hit_was_head가 True여야 합니다.")


class TestBug4BulletTimePausePreservation(unittest.TestCase):
    """Bug 4: 정지/메뉴 상태에서 불릿타임 잔여시간 보존 검증"""

    def test_bullet_time_preservation_across_menu_states(self):
        """PAUSED, SHOP, INVENTORY, AAR 상태 동안 불릿타임 시간이 소비되지 않고 재개 시 정상 소모 검증"""
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.bullet_time_timer = 2.5
        game.audio_mgr = Mock()
        game.ui_mgr = Mock()

        # 1) 일시정지 (PAUSED): 10틱 후에도 2.5초 보존
        game.game_state = "PAUSED"
        for _ in range(10):
            game.update(None)
        self.assertEqual(game.bullet_time_timer, 2.5)
        game.audio_mgr.update_bullet_time.assert_not_called()

        # 2) 상점 (SHOP): 보존
        game.game_state = "SHOP"
        for _ in range(5):
            game.update(None)
        self.assertEqual(game.bullet_time_timer, 2.5)

        # 3) 인벤토리 (INVENTORY): 보존
        game.game_state = "INVENTORY"
        for _ in range(5):
            game.update(None)
        self.assertEqual(game.bullet_time_timer, 2.5)

        # 4) 전투 결과 보고서 (AAR): 보존
        game.game_state = "AAR"
        for _ in range(5):
            game.update(None)
        self.assertEqual(game.bullet_time_timer, 2.5)

        # 5) 게임플레이 재개 (PLAYING): 시간 소모 및 종료 시 1회 효과음 발생
        game.game_state = "PLAYING"
        game.game_won = False
        game.game_over = False
        game.is_test_mode = True
        game.player = SimpleNamespace(update=Mock(return_value=(False, False, False)))
        game._update_monsters = Mock(return_value=(False, 10.0))
        game.combat = SimpleNamespace(update=Mock())
        game.stage_banner_timer = 0.0
        game.time_left = 300.0
        game.chunks = {}
        game.camera = SimpleNamespace(getX=lambda: 0, getY=lambda: 0, getZ=lambda: 1.8)
        game.portal_mgr = SimpleNamespace(update_door_defense=Mock(return_value=False))
        game.monsters = []
        game.supply_crates = []
        game.hazard_barrels = []
        game.blackout_triggered_this_stage = False
        game.blackout_active = False
        game.grenade_cooldown = 0.0
        game.item_drops = []
        game.explosions = []
        game.shockwaves = []

        mock_clock = Mock()
        mock_clock.getDt.return_value = 0.1
        mock_clock.getFrameTime.return_value = 1.0

        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertAlmostEqual(game.bullet_time_timer, 2.4, places=2)
        game.audio_mgr.update_bullet_time.assert_called_once_with(0.1)

        # 잔여 시간 완전 소진 시뮬레이션
        game.bullet_time_timer = 0.05
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertEqual(game.bullet_time_timer, 0.0)
        game.audio_mgr.play_bullet_time.assert_called_once_with(is_start=False)
        game.ui_mgr.set_bullet_time_hud.assert_called_with(False)


class TestBug5PortalDefenseTimer(unittest.TestCase):
    """Bug 5: 비상탈출문 사수 생명주기 및 작업 2 단일 웨이브 전환 후 사수-증원 분리 검증
    [작업 2 규칙 교체 사유]:
    기존에는 5초 사수 중 2초마다 EscapePortalManager가 자체적으로 증원 몬스터를 스폰하였으나,
    작업 2에서 관문의 모든 증원이 GateWaveManager 단일 제어로 일원화되었다.
    따라서 5초 사수 자체는 별도의 주기 증원을 발생시키지 않으며, 재정비(REST) 구간을 활용한
    사수 탈출이 의도된 플레이로 보장된다.
    """

    def test_door_defense_does_not_spawn_reinforcements_and_preserves_hold_lifecycle(self):
        """방어 구역 사수 진행 시 자체 증원이 발생하지 않으며, 이탈 시 리셋 및 5초 완료 탈출 검증"""
        mock_game = SimpleNamespace(
            escape_pos=(50.0, 50.0),
            current_stage=1,
            door_hold_timer=5.0,
            ui_mgr=Mock(),
            audio_mgr=Mock(),
            monsters=[],
            spawn_reinforcement_monster=Mock(),
            trigger_stage_clear=Mock()
        )
        portal_mgr = EscapePortalManager(mock_game)

        # 1) 구역 내부 1.9초 사수 진행 (반경 3.8m 이내)
        portal_mgr.update_door_defense(1.9, 50.0, 50.0)
        self.assertAlmostEqual(mock_game.door_hold_timer, 3.1)
        mock_game.spawn_reinforcement_monster.assert_not_called()

        # 2) 방어 구역 이탈 (거리가 10m로 멀어짐) -> door_hold_timer 즉시 5.0초 리셋
        portal_mgr.update_door_defense(0.1, 60.0, 50.0)
        self.assertEqual(mock_game.door_hold_timer, 5.0)
        mock_game.spawn_reinforcement_monster.assert_not_called()

        # 3) 재진입 후 2.0초 사수 -> 과거에는 2초 주기 증원이 발생했으나 새 규칙에서는 자체 증원 0회
        portal_mgr.update_door_defense(2.0, 50.0, 50.0)
        self.assertAlmostEqual(mock_game.door_hold_timer, 3.0)
        mock_game.spawn_reinforcement_monster.assert_not_called()

        # 4) 나머지 3.0초 사수 완료 -> 총 5.0초 사수로 탈출 성공, 사수 중 증원 0회 확인
        cleared = portal_mgr.update_door_defense(3.0, 50.0, 50.0)
        self.assertTrue(cleared)
        mock_game.trigger_stage_clear.assert_called_once()
        mock_game.spawn_reinforcement_monster.assert_not_called()

    def test_real_restart_and_advance_stage_timer_reset(self):
        """실제 restart_game 및 advance_to_next_stage 호출 시 monster_director.gate_wave_mgr 상태 및 캐시 초기화 검증"""
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.portal_mgr = EscapePortalManager(game)
        game.monster_director = MonsterDirector(game)
        game.world_root = NodePath("world_root")
        game.render = NodePath("render")
        game.camera = NodePath("camera")
        game.win = None
        game.setBackgroundColor = Mock()
        game.ui_mgr = Mock()
        game.audio_mgr = Mock()
        game.combat = Mock()
        game.combat.reserve_ammo = 24
        game.combat.max_ammo = 12
        game.active_chunk_futures = {}
        game.explosions = []
        game.fireballs = []
        game.shockwaves = []
        game.grenades = []
        game.hazard_barrels = []
        game.supply_crates = []
        game.item_drops = []
        game.monsters = []
        game.corpses = []
        game.liminal_fog = Mock()
        game.amb_np = SimpleNamespace(node=lambda: Mock())
        game.player = PlayerController(game, None, game.camera, None, None, game.ui_mgr)

        # 무거운 외부 작업(맵/청크/3D 엔티티 스폰)만 mock 처리
        game.regenerate_map = Mock()
        game.setup_escape_portal = Mock()
        game.spawn_monsters = Mock()
        game.spawn_hazard_barrels = Mock()
        game.spawn_supply_crates = Mock()

        # 1) restart_game 실제 호출 전 임의의 웨이브 진행 상태 설정
        wave_mgr = game.monster_director.gate_wave_mgr
        wave_mgr.state = "SPAWNING"
        wave_mgr.waves_completed = 2
        wave_mgr.state_timer = 4.2
        wave_mgr._cached_candidates = [(10.0, 20.0)]
        wave_mgr._cached_escape_pos = (50.0, 50.0)

        game.restart_game()
        self.assertEqual(wave_mgr.state, "WAITING")
        self.assertEqual(wave_mgr.waves_completed, 0)
        self.assertEqual(wave_mgr.state_timer, 0.0)
        self.assertIsNone(wave_mgr._cached_candidates)
        self.assertIsNone(wave_mgr._cached_escape_pos)

        # 2) advance_to_next_stage 실제 호출 전 임의의 웨이브 진행 상태 설정
        wave_mgr.state = "REST"
        wave_mgr.waves_completed = 1
        wave_mgr.state_timer = 6.0
        wave_mgr._cached_candidates = [(30.0, 40.0)]
        wave_mgr._cached_escape_pos = (80.0, 80.0)

        game.advance_to_next_stage()
        self.assertEqual(wave_mgr.state, "WAITING")
        self.assertEqual(wave_mgr.waves_completed, 0)
        self.assertEqual(wave_mgr.state_timer, 0.0)
        self.assertIsNone(wave_mgr._cached_candidates)
        self.assertIsNone(wave_mgr._cached_escape_pos)


class TestGateWaveReinforcementSystem(unittest.TestCase):
    """작업 2: 관문 증원 단일 웨이브 관리 시스템 종합 검증
    지시서 필수 동작 1~10번 항목의 상세 검증을 수행한다.
    """

    def setUp(self):
        self.mock_game = SimpleNamespace(
            escape_pos=(50.0, 50.0),
            current_stage=1,
            game_state="PLAYING",
            is_test_mode=False,
            blackout_active=False,
            monsters=[],
            corpses=[],
            boss=None,
            boss_spawned=False,
            boss_defeat_handled=False,
            ui_mgr=Mock(),
            audio_mgr=Mock(),
            render=NodePath("test_render"),
            world_root=NodePath("world_root"),
            item_drops=[],
            chunks={},
            camera=SimpleNamespace(getX=lambda: 50.0, getY=lambda: 20.0, getZ=lambda: 1.6, getH=lambda: 0.0, getPos=lambda: Vec3(50.0, 20.0, 1.6)),
            player=SimpleNamespace(
                heading=0.0,
                pos=SimpleNamespace(x=50.0, y=20.0, z=1.6),
                hp=100,
                max_hp=100
            ),
            combat=SimpleNamespace(ammo=12, max_ammo=12, reserve_ammo=24),
            base_fov=96.0
        )
        self.director = MonsterDirector(self.mock_game)
        self.wave_mgr = self.director.gate_wave_mgr
        self.wave_mgr.was_in_radius = True

    def _make_mock_monster(self, x=50.0, y=32.0, z=0.0, hp=100, is_corpse=False, col_radius=0.40):
        return SimpleNamespace(
            pos=SimpleNamespace(x=x, y=y, z=z),
            col_radius=col_radius,
            hp=hp,
            is_corpse=is_corpse,
            stun_timer=0.0,
            burn_timer=0.0,
            shock_timer=0.0,
            attack_damage=10,
            speed=2.0,
            height=2.0,
            path=[],
            path_timer=1.0,
            _goal_cell=None,
            _local_path=[],
            _local_path_timer=0.0,
            _local_goal=None,
            update=Mock(return_value=(False, False)),
            update_pos=Mock(),
            turn_into_corpse=Mock()
        )

    def test_01_warning_duration_and_no_multi_spawns_on_large_dt(self):
        """1. 2초 경고 전 출현 0회, 경고 후 간격 준수, 큰 dt에서도 한 프레임 다중 생성 없음"""
        spawned_monsters = []

        def mock_spawn(*args, **kwargs):
            m = self._make_mock_monster(50.0, 32.0, 0.0, hp=100)
            spawned_monsters.append(m)
            self.mock_game.monsters.append(m)
            return m

        with patch('gate_wave.GateWaveManager.get_cached_candidates', return_value=[(50.0, 32.0)]), \
             patch('spawner.spawn_reinforcement_monster', side_effect=mock_spawn):

            # 경고 상태로 시작
            self.wave_mgr.state = "WARNING"
            self.wave_mgr.state_timer = 2.0

            # 1) 경고 1.9초 진행 (2.0초 미만) -> 출현 0회
            self.director.update_monsters(1.9, 50.0, 20.0, raw_dt=1.9)
            self.assertEqual(self.wave_mgr.state, "WARNING")
            self.assertEqual(len(spawned_monsters), 0)

            # 2) 0.2초 경과 -> 총 2.1초로 경고 완료, SPAWNING 진입 및 첫 번째 적 1마리 출현
            self.director.update_monsters(0.2, 50.0, 20.0, raw_dt=0.2)
            self.assertEqual(self.wave_mgr.state, "SPAWNING")
            self.assertEqual(len(spawned_monsters), 1)

            # 3) 0.1초 경과 -> 간격(0.75초) 미달로 추가 출현 없음
            self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
            self.assertEqual(len(spawned_monsters), 1)

            # 4) 큰 dt(5.0초) 단일 프레임 주입 -> 한 프레임에 다중 생성 없이 정확히 1마리만 추가 출현
            self.director.update_monsters(5.0, 50.0, 20.0, raw_dt=5.0)
            self.assertEqual(len(spawned_monsters), 2)
            # 1스테이지 목표(2마리) 달성으로 REST 전환 확인
            self.assertEqual(self.wave_mgr.state, "REST")

    def test_02_rest_duration_no_spawns_on_kill_and_max_waves_exhaustion(self):
        """2. REST 8초 동안 출현 없음, 처치 직후 보충 없음, 세 웨이브 이후 추가 출현 없음"""
        self.wave_mgr.state = "REST"
        self.wave_mgr.state_timer = 8.0
        self.wave_mgr.waves_completed = 1

        spawn_mock = Mock()
        with patch('spawner.spawn_reinforcement_monster', spawn_mock):
            # 1) REST 4.0초 진행 -> 증원 없음
            self.director.update_monsters(4.0, 50.0, 20.0, raw_dt=4.0)
            self.assertEqual(self.wave_mgr.state, "REST")
            self.assertAlmostEqual(self.wave_mgr.state_timer, 4.0)
            spawn_mock.assert_not_called()

            # 2) 관문 근처에서 적 처치 발생 시뮬레이션 -> 기존 65% 즉시 재증원 경로가 삭제되어 추가 스폰 0회
            dead_m = self._make_mock_monster(50.0, 30.0, 0.0, hp=0, is_corpse=False)
            self.mock_game.monsters.append(dead_m)
            self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
            spawn_mock.assert_not_called()

            # 3) 3웨이브 소진 시뮬레이션 (waves_completed = 3, REST 완료)
            self.wave_mgr.waves_completed = 3
            self.wave_mgr.state_timer = 0.5
            self.director.update_monsters(1.0, 50.0, 20.0, raw_dt=1.0)
            self.assertEqual(self.wave_mgr.state, "EXHAUSTED")

            # 4) EXHAUSTED 상태에서 추가 시간 및 접근에도 스폰 0회
            self.director.update_monsters(2.0, 50.0, 20.0, raw_dt=2.0)
            self.assertEqual(self.wave_mgr.state, "EXHAUSTED")
            spawn_mock.assert_not_called()

    def test_03_nearby_enemies_threshold_and_global_alive_cap(self):
        """3. 주변 적 6마리 초과 시 다음 경고 보류, 전체 상한 16마리에서 출현 없음 (시체 제외)"""
        # 관문 45m 이내에 살아 있는 적 7마리 배치
        for i in range(7):
            m = self._make_mock_monster(50.0, 40.0 + i, 0.0, hp=100)
            self.mock_game.monsters.append(m)

        self.wave_mgr.state = "WAITING"
        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        # 6마리 초과이므로 경고 진입 보류
        self.assertEqual(self.wave_mgr.state, "WAITING")

        # 2마리를 시체로 전환 (생존 적 5마리 <= 6)
        self.mock_game.monsters[0].hp = 0
        self.mock_game.monsters[0].is_corpse = True
        self.mock_game.monsters[1].hp = 0
        self.mock_game.monsters[1].is_corpse = True

        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        # 생존 적 5마리이므로 WARNING 진입 성공
        self.assertEqual(self.wave_mgr.state, "WARNING")

        # SPAWNING 상태에서 전체 생존 적이 16마리인 경우 스폰 차단 검증
        self.wave_mgr.state = "SPAWNING"
        self.wave_mgr.spawn_cooldown = 0.0
        self.wave_mgr.wave_target = 4
        self.wave_mgr.wave_spawned = 0
        self.mock_game.monsters = [
            self._make_mock_monster(10.0, 10.0, 0.0, hp=100)
            for _ in range(16)
        ]
        # 사망한 시체 3구 추가 (상한 계산에서 제외되어야 함)
        for _ in range(3):
            self.mock_game.monsters.append(self._make_mock_monster(10.0, 10.0, 0.0, hp=0, is_corpse=True))

        spawn_mock = Mock()
        with patch('spawner.spawn_reinforcement_monster', spawn_mock):
            self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
            spawn_mock.assert_not_called()

    def test_04_spawning_phase_timeout_and_no_budget_accumulation(self):
        """4. 안전 후보 없음/상한 도달 시 0.75초 간격 재시도, 최대 6초 후 종료, 물량 누적 없음"""
        self.wave_mgr.state = "SPAWNING"
        self.wave_mgr.waves_completed = 1
        self.wave_mgr.wave_target = 2
        self.wave_mgr.wave_spawned = 0
        self.wave_mgr.spawning_time_left = 6.0
        self.wave_mgr.spawn_cooldown = 0.0
        self.wave_mgr.was_in_radius = True
        self.wave_mgr.reentry_warning_timer = 0.0

        spawn_calls = []
        def mock_failing_spawn(*args, **kwargs):
            spawn_calls.append(self.wave_mgr.spawning_time_left)
            return None

        with patch('spawner.spawn_reinforcement_monster', side_effect=mock_failing_spawn):
            # 첫 번째 틱(0.1초): spawn 시도 -> 실패 -> 0.75초 cooldown 설정
            self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
            self.assertEqual(len(spawn_calls), 1)
            self.assertAlmostEqual(self.wave_mgr.spawn_cooldown, 0.75)

            # 0.2초 경과 (cooldown 0.55s 남음) -> 추가 시도 없음
            self.director.update_monsters(0.2, 50.0, 20.0, raw_dt=0.2)
            self.assertEqual(len(spawn_calls), 1)
            self.assertAlmostEqual(self.wave_mgr.spawn_cooldown, 0.55)

            # 0.55초 경과 (총 0.75초 만료) -> 두 번째 spawn 시도 발생
            self.director.update_monsters(0.55, 50.0, 20.0, raw_dt=0.55)
            self.assertEqual(len(spawn_calls), 2)
            self.assertAlmostEqual(self.wave_mgr.spawn_cooldown, 0.75)

            # 부분 성공 검증: 1마리 성공 후 다음 시도 실패 시에도 0.75초 간격 유지
            m1 = self._make_mock_monster(50.0, 32.0, 0.0, hp=100)
            with patch('spawner.spawn_reinforcement_monster', return_value=m1):
                self.director.update_monsters(0.75, 50.0, 20.0, raw_dt=0.75)
                self.assertEqual(self.wave_mgr.wave_spawned, 1)
                self.assertAlmostEqual(self.wave_mgr.spawn_cooldown, 0.75)

            # 남은 시간 완전 소진하여 6초 타임아웃 초과 -> REST 진입
            self.director.update_monsters(5.0, 50.0, 20.0, raw_dt=5.0)
            self.assertEqual(self.wave_mgr.state, "REST")
            self.assertEqual(self.wave_mgr.state_timer, 8.0)
            # 타임아웃 틱 및 이후에는 spawn_reinforcement_monster 호출이 추가 발생하지 않음
            prev_calls = len(spawn_calls)
            self.director.update_monsters(1.0, 50.0, 20.0, raw_dt=1.0)
            self.assertEqual(len(spawn_calls), prev_calls)

        # REST 8초 완료 후 WAITING 진입 및 주변 적 검사 통과 시 WARNING 시작
        self.director.update_monsters(8.1, 50.0, 20.0, raw_dt=8.1)
        self.assertEqual(self.wave_mgr.state, "WAITING")
        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        self.assertEqual(self.wave_mgr.state, "WARNING")
        self.director.update_monsters(2.1, 50.0, 20.0, raw_dt=2.1)
        self.assertEqual(self.wave_mgr.state, "SPAWNING")
        # 1스테이지 2웨이브 목표는 기본 2마리여야 하며, 실패한 이전 웨이브 2마리가 누적(4마리)되지 않음
        self.assertEqual(self.wave_mgr.wave_target, 2)
        self.assertEqual(self.wave_mgr.waves_completed, 2)

    def test_05_radius_exit_and_reentry_policies(self):
        """5. WARNING/SPAWNING/REST 각각 45m 이탈·재진입 시 시간과 횟수 정책 준수"""
        # 1) WARNING 도중 이탈 및 재진입: 온전한 2초 경고 다시 제공
        self.wave_mgr.state = "WARNING"
        self.wave_mgr.state_timer = 0.8
        self.wave_mgr.was_in_radius = True

        # 반경 밖(60m)으로 이탈
        self.director.update_monsters(2.0, 50.0, 110.0, raw_dt=2.0)
        self.assertFalse(self.wave_mgr.was_in_radius)
        self.assertAlmostEqual(self.wave_mgr.state_timer, 0.8) # 타이머 일시 정지

        # 반경 안(30m)으로 재진입
        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        self.assertTrue(self.wave_mgr.was_in_radius)
        self.assertEqual(self.wave_mgr.state, "WARNING")
        self.assertAlmostEqual(self.wave_mgr.state_timer, 1.9) # 2.0초 리셋 후 0.1초 경과

        # 2) SPAWNING 도중 이탈 및 재진입: 잔여 수량 앞에 2초 경고 재제공, 6초 예산/웨이브 횟수 미추가
        self.wave_mgr.state = "SPAWNING"
        self.wave_mgr.waves_completed = 1
        self.wave_mgr.wave_target = 2
        self.wave_mgr.wave_spawned = 1
        self.wave_mgr.spawning_time_left = 3.5
        self.wave_mgr.was_in_radius = True

        # 이탈
        self.director.update_monsters(1.0, 50.0, 120.0, raw_dt=1.0)
        self.assertFalse(self.wave_mgr.was_in_radius)
        self.assertAlmostEqual(self.wave_mgr.spawning_time_left, 3.5)

        # 재진입
        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        self.assertTrue(self.wave_mgr.was_in_radius)
        self.assertEqual(self.wave_mgr.state, "SPAWNING")
        self.assertEqual(self.wave_mgr.waves_completed, 1) # 웨이브 추가 소모 없음
        self.assertAlmostEqual(self.wave_mgr.reentry_warning_timer, 1.9) # 2.0초 리셋 후 0.1초 경과
        self.assertAlmostEqual(self.wave_mgr.spawning_time_left, 3.5) # 6초로 리셋되지 않음

        # 3) REST 도중 이탈 및 재진입: REST 잔여시간 보존
        self.wave_mgr.state = "REST"
        self.wave_mgr.state_timer = 5.2
        self.wave_mgr.was_in_radius = True

        self.director.update_monsters(2.0, 50.0, 110.0, raw_dt=2.0)
        self.assertFalse(self.wave_mgr.was_in_radius)
        self.assertAlmostEqual(self.wave_mgr.state_timer, 5.2)

        self.director.update_monsters(0.1, 50.0, 20.0, raw_dt=0.1)
        self.assertTrue(self.wave_mgr.was_in_radius)
        self.assertEqual(self.wave_mgr.state, "REST")
        self.assertAlmostEqual(self.wave_mgr.state_timer, 5.1)

    def test_06_real_raw_dt_and_menus_test_mode_isolation(self):
        """6. 실제 LiminalInfiniteLoop 메인 루프 연동에서 조기 반환, HUD 숨김/복원, raw_dt 검증"""
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.game_state = "PLAYING"
        game.is_test_mode = False
        game.game_won = False
        game.game_over = False
        game.bullet_time_timer = 0.0
        game.chunks = {}
        game.monsters = []
        game.corpses = []
        game.item_drops = []
        game.fireball_pool = []
        game.fireballs = []
        game.shockwaves = []
        game.grenades = []
        game.hazard_barrels = []
        game.explosions = []
        game.stage_banner_timer = 0.0
        game.time_left = 300.0
        game.blackout_triggered_this_stage = False
        game.blackout_active = False
        game.grenade_cooldown = 0.0
        game.supply_crates = []
        game.nearby_crate = None
        game.nearby_item_drop = None
        game.lighting_mgr = SimpleNamespace(update_dynamic_lights=Mock())
        game.cull_chunks_to_view = Mock()
        game.active_chunk_futures = {}
        game.camera = SimpleNamespace(
            getX=lambda: 50.0, getY=lambda: 20.0, getZ=lambda: 1.6,
            getPos=lambda: Vec3(50.0, 20.0, 1.6),
            setHpr=Mock(), setPos=Mock(), lookAt=Mock()
        )
        game.player = SimpleNamespace(
            update=Mock(return_value=(False, False, False)),
            heading=0.0, lock_mouse=Mock(), mouse_locked=True
        )
        game.combat = SimpleNamespace(stop_aim=Mock(), update=Mock())
        game.audio_mgr = SimpleNamespace(
            update=Mock(), update_bullet_time=Mock(),
            play_bullet_time=Mock(), play_inventory_toggle=Mock()
        )
        game.ui_mgr = Mock()
        game.escape_pos = (50.0, 50.0)
        game.current_stage = 1
        game.portal_mgr = SimpleNamespace(update_door_defense=Mock(return_value=False))

        director = MonsterDirector(game)
        game.monster_director = director
        wave_mgr = director.gate_wave_mgr
        wave_mgr.state = "WARNING"
        wave_mgr.state_timer = 2.0
        wave_mgr.was_in_radius = True

        mock_clock = Mock()
        mock_clock.getDt.return_value = 0.1
        mock_clock.getFrameTime.return_value = 10.0

        # 1) PAUSED 상태: game.update(None) 실행 시 조기 반환으로 웨이브 시간 정지 및 HUD 숨김
        game.game_state = "PAUSED"
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertEqual(wave_mgr.state_timer, 2.0)
        game.ui_mgr.update_gate_wave_status.assert_called_with(show=False)

        # 2) PLAYING 복귀 (resume_game 호출): HUD 안내 복원
        game.resume_game()
        self.assertEqual(game.game_state, "PLAYING")
        game.ui_mgr.update_gate_wave_status.assert_called_with(
            msg="증원 경고 1/3 · 2.0초", fg=(1.0, 0.65, 0.2, 1.0), show=True
        )

        # 3) 불릿 타임 중: world_dt(0.035)와 무관하게 raw_dt(0.10)로 웨이브 타이머 진행
        game.bullet_time_timer = 2.0
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertAlmostEqual(wave_mgr.state_timer, 1.9, places=2)

        # 4) SHOP 상태 시: 조기 반환 및 HUD 숨김
        game.game_state = "SHOP"
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertAlmostEqual(wave_mgr.state_timer, 1.9, places=2)
        game.ui_mgr.update_gate_wave_status.assert_called_with(show=False)

        # 5) INVENTORY / AAR 상태 시: 조기 반환 및 HUD 숨김
        game.game_state = "INVENTORY"
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertAlmostEqual(wave_mgr.state_timer, 1.9, places=2)
        game.ui_mgr.update_gate_wave_status.assert_called_with(show=False)

        game.game_state = "AAR"
        with patch("game.globalClock", mock_clock):
            game.update(None)
        self.assertAlmostEqual(wave_mgr.state_timer, 1.9, places=2)
        game.ui_mgr.update_gate_wave_status.assert_called_with(show=False)

        # 6) 테스트 모드 진입 (start_test_mode 호출): HUD 숨김 및 웨이브 매니저 reset() 호출
        game.test_range = SimpleNamespace(start_test_mode=Mock())
        game.start_test_mode()
        self.assertEqual(wave_mgr.state, "WAITING")
        self.assertEqual(wave_mgr.waves_completed, 0)
        game.ui_mgr.update_gate_wave_status.assert_called_with(show=False)

    def test_07_boss_presence_halts_waves_and_post_boss_rest(self):
        """7. 38m 보스 출현 프레임에 보스 우선 생성 및 일반 웨이브 즉시 중단, 격파 후 8초 재정비, 보스 고유 소환 유지"""
        self.mock_game.current_stage = 3
        self.mock_game.boss = None
        self.mock_game.boss_spawned = False
        self.mock_game.escape_pos = (50.0, 50.0)

        boss_instance = self._make_mock_monster(54.0, 54.0, 0.0, hp=2000)
        def mock_spawn_boss(*args, **kwargs):
            self.mock_game.boss = boss_instance
            self.mock_game.boss_spawned = True
            self.mock_game.monsters.append(boss_instance)
            return boss_instance

        self.mock_game.spawn_boss = Mock(side_effect=mock_spawn_boss)

        self.wave_mgr.state = "SPAWNING"
        self.wave_mgr.waves_completed = 1
        self.wave_mgr.spawn_cooldown = 0.0
        self.wave_mgr.wave_target = 4
        self.wave_mgr.wave_spawned = 0
        self.wave_mgr.was_in_radius = True

        spawn_reinforce_mock = Mock()
        with patch('spawner.spawn_reinforcement_monster', spawn_reinforce_mock):
            # 플레이어가 관문 35m(<= 38m)로 접근한 프레임 실행
            px, py = 50.0, 15.0  # dist_gate = 35.0m
            self.director.update_monsters(0.1, px, py, raw_dt=0.1)

            # 1) 보스가 우선 생성되었는지 확인
            self.mock_game.spawn_boss.assert_called_once()
            self.assertTrue(self.mock_game.boss_spawned)

            # 2) 보스 출현 프레임에 일반 웨이브는 즉시 중단되고 REST 전환되었는지 확인
            self.assertEqual(self.wave_mgr.state, "REST")
            # 3) 보스 생성 프레임에 일반 웨이브 스폰이 0회인지 확인
            spawn_reinforce_mock.assert_not_called()

            # 4) 보스 생존 중에는 REST 시간이 줄어들지 않고 8.0초 유지
            self.director.update_monsters(3.0, px, py, raw_dt=3.0)
            self.assertEqual(self.wave_mgr.state_timer, 8.0)

        # 5) 보스 사망 처리 및 격파 후 8.0초 재정비 카운트다운 시작 확인
        boss_instance.hp = 0
        boss_instance.is_corpse = True
        self.mock_game.boss = None

        self.director.update_monsters(0.1, px, py, raw_dt=0.1)
        self.assertEqual(self.wave_mgr.state, "REST")
        self.assertAlmostEqual(self.wave_mgr.state_timer, 7.9)

        # 6) 기존 보스 고유 소환 패턴(2페이즈 체력 50% 진입 시 2마리 스폰) 보존 확인
        class MockCableOverlordBoss(CableOverlordBoss):
            def __init__(self, x=54.0, y=54.0, z=0.0, hp=2000):
                self.pos = SimpleNamespace(x=x, y=y, z=z)
                self.col_radius = 0.55
                self.hp = hp
                self.max_hp = hp
                self.is_corpse = False
                self.phase = 1
                self.cable_lash_cooldown = 10.0
                self.shockwave_cooldown = 10.0
                self.dart_cooldown = 10.0
                self.summon_cooldown = 15.0
                self.is_lashing = False
                self.stun_timer = 0.0
                self.burn_timer = 0.0
                self.shock_timer = 0.0
                self.attack_damage = 30
                self.speed = 1.0
                self.height = 3.0
                self.path = []
                self.path_timer = 1.0
                self._goal_cell = None
                self._local_path = []
                self._local_path_timer = 0.0
                self._local_goal = None
                self.update = Mock(return_value=(False, False))
                self.update_pos = Mock()
                self.turn_into_corpse = Mock()

        boss_m = MockCableOverlordBoss(54.0, 54.0, 0.0, hp=2000)
        self.mock_game.monsters = [boss_m]
        self.mock_game.boss = boss_m
        self.mock_game.spawn_reinforcement_monster = Mock()

        boss_m.hp = 1000  # 50% 도달
        self.director.update_monsters(0.1, px, py, raw_dt=0.1)
        self.assertEqual(boss_m.phase, 2)
        self.assertEqual(self.mock_game.spawn_reinforcement_monster.call_count, 2)

    def test_09_safety_position_checks_comprehensive(self):
        """9. 거리 12m, 벽/관문 충돌, 미로드 청크, 정면 열린 시야, 벽 뒤, 뒤쪽 후보, 실 청크/커스텀 충돌체 검증"""
        px, py, pz = 50.0, 30.0, 1.6
        cam_h = 0.0  # 정면은 +Y 방향 (y 증가)
        hfov = 96.0

        cand_x, cand_y = 50.0, 35.0

        # 1) chunks가 None이거나 빈 dict이면 무조건 False (안전 검사 우회 방지)
        game_none_chunks = SimpleNamespace(escape_pos=(50.0, 50.0), chunks=None, monsters=[])
        self.assertFalse(is_spawn_position_safe(game_none_chunks, cand_x, cand_y, 0.40, px, py, pz, cam_h, hfov))

        game_empty_chunks = SimpleNamespace(escape_pos=(50.0, 50.0), chunks={}, monsters=[])
        self.assertFalse(is_spawn_position_safe(game_empty_chunks, cand_x, cand_y, 0.40, px, py, pz, cam_h, hfov))

        # 2) 후보 좌표의 청크가 chunks에 없으면 False
        game_other_chunks = SimpleNamespace(
            escape_pos=(50.0, 50.0),
            chunks={(99, 99): SimpleNamespace(cell_colliders={})},
            monsters=[]
        )
        self.assertFalse(is_spawn_position_safe(game_other_chunks, cand_x, cand_y, 0.40, px, py, pz, cam_h, hfov))

        # 정상 로드된 청크 구성
        valid_chunks = {
            (0, 0): SimpleNamespace(cell_colliders={}),
            (1, 0): SimpleNamespace(cell_colliders={}),
            (0, 1): SimpleNamespace(cell_colliders={}),
            (1, 1): SimpleNamespace(cell_colliders={}),
        }
        game = SimpleNamespace(escape_pos=(50.0, 50.0), chunks=valid_chunks, monsters=[])

        # 3) 관문 거리 (10~30m)
        self.assertFalse(is_spawn_position_safe(game, 50.0, 42.0, 0.40, px, py, pz, cam_h, hfov)) # 8m -> False
        self.assertFalse(is_spawn_position_safe(game, 50.0, 85.0, 0.40, px, py, pz, cam_h, hfov)) # 35m -> False

        # 4) 플레이어 거리 (최소 12m)
        self.assertFalse(is_spawn_position_safe(game, 50.0, 35.0, 0.40, 50.0, 25.0, pz, cam_h, hfov)) # 10m -> False

        # 5) FOV 및 벽 차폐(Line-of-Sight) 검사 (공용 커스텀 충돌체 사용)
        px, py = 50.0, 20.0
        cand_x, cand_y = 50.0, 35.0
        try:
            clear_custom_colliders()
            # Case 5-1: 차단 충돌체가 없는 열린 공간에서 플레이어 정면 (FOV 안) -> 제외
            self.assertFalse(is_spawn_position_safe(game, cand_x, cand_y, 0.40, px, py, pz, cam_h, hfov))

            # Case 5-2: 플레이어와 후보 사이에 벽 충돌체 등록 -> 벽 뒤 차폐로 안전 허용
            register_custom_collider((45.0, 27.0, 55.0, 28.0))
            self.assertTrue(is_spawn_position_safe(game, cand_x, cand_y, 0.40, px, py, pz, cam_h, hfov))

            # Case 5-3: 플레이어 뒤쪽 위치 (angle = 180도) -> FOV 밖이므로 벽 없이도 안전 허용
            clear_custom_colliders()
            behind_x, behind_y = 50.0, 25.0
            self.assertTrue(is_spawn_position_safe(game, behind_x, behind_y, 0.40, 50.0, 40.0, pz, cam_h, hfov))

            # 6) 벽 충돌체 몸체 중첩 검사
            # 후보 (50.0, 35.0) 기준 밑단(34.5)까지의 거리 = 0.5m
            register_custom_collider((49.0, 34.0, 51.0, 34.5))
            register_custom_collider((45.0, 27.0, 55.0, 28.0)) # 차폐벽
            # 일반 반경 0.40m: 거리 0.5m이므로 벽에 겹치지 않음
            self.assertTrue(is_spawn_position_safe(game, 50.0, 35.0, 0.40, px, py, pz, cam_h, hfov))
            # 반경 0.55m: 거리 0.5m < 0.55m이므로 벽과 몸체 중첩 발생 -> 제외
            self.assertFalse(is_spawn_position_safe(game, 50.0, 35.0, 0.55, px, py, pz, cam_h, hfov))
        finally:
            clear_custom_colliders()

        # 7) 기존 생존 몬스터 및 동일 웨이브 기선정 위치 중첩
        try:
            register_custom_collider((45.0, 27.0, 55.0, 28.0)) # 차폐벽
            game.monsters = [SimpleNamespace(pos=SimpleNamespace(x=50.0, y=35.2, z=0.0), col_radius=0.40, hp=100, is_corpse=False)]
            # 기존 몬스터와 거리 0.2m < (0.4 + 0.4) -> 제외
            self.assertFalse(is_spawn_position_safe(game, 50.0, 35.0, 0.40, px, py, pz, cam_h, hfov))
        finally:
            clear_custom_colliders()

    def test_10_door_defense_hold_isolated_from_wave_system(self):
        """10. 기존 사수 5초 성공/이탈 리셋 유지 및 사수 진입으로 웨이브가 중복 시작하지 않음"""
        mock_game = SimpleNamespace(
            escape_pos=(50.0, 50.0),
            current_stage=1,
            door_hold_timer=5.0,
            ui_mgr=Mock(),
            audio_mgr=Mock(),
            monsters=[],
            spawn_reinforcement_monster=Mock(),
            trigger_stage_clear=Mock()
        )
        portal_mgr = EscapePortalManager(mock_game)
        director = MonsterDirector(mock_game)

        # 1) 사수 구역(3.8m) 진입 -> 웨이브 매니저는 WAITING 상태 유지
        portal_mgr.update_door_defense(1.0, 50.0, 50.0)
        self.assertEqual(director.gate_wave_mgr.state, "WAITING")
        self.assertEqual(director.gate_wave_mgr.waves_completed, 0)
        mock_game.spawn_reinforcement_monster.assert_not_called()

    def test_11_pre_spawn_collision_radius_matches_actual_monster_and_wall_rejection(self):
        """11. 실제 spawn_reinforcement_monster 경로에서 오크/정예 오크의 반경 일관성 및 벽 거리(0.53m) 거절 검증"""
        # 오크 기본 반경 0.45, 정예 오크 0.5625
        self.assertEqual(get_monster_collision_radius(AbominableMudOrc, is_elite=False), 0.45)
        self.assertEqual(get_monster_collision_radius(AbominableMudOrc, is_elite=True), 0.5625)

        valid_chunks = {
            (1, 1): SimpleNamespace(cell_colliders={}),
            (1, 0): SimpleNamespace(cell_colliders={}),
            (0, 1): SimpleNamespace(cell_colliders={}),
            (0, 0): SimpleNamespace(cell_colliders={}),
        }

        # 후보 중심: (50.0, 35.0), 관문: (50.0, 50.0), 플레이어: (50.0, 20.0) -> 거리 15m
        cand_x, cand_y = 50.0, 35.0
        try:
            clear_custom_colliders()
            # 벽 상자: (49.0, 34.0, 51.0, 34.47) -> 상자 윗면(34.47)과 후보(35.0) 중심 사이 거리 = 0.53m
            register_custom_collider((49.0, 34.0, 51.0, 34.47))
            register_custom_collider((45.0, 27.0, 55.0, 28.0)) # 시야 차폐벽

            game = SimpleNamespace(
                render=NodePath("test_render"),
                escape_pos=(50.0, 50.0),
                chunks=valid_chunks,
                monsters=[],
                camera=SimpleNamespace(getX=lambda: 50.0, getY=lambda: 20.0, getZ=lambda: 1.6, getH=lambda: 0.0),
                player=SimpleNamespace(heading=0.0, pos=SimpleNamespace(x=50.0, y=20.0, z=1.6)),
                base_fov=96.0,
                current_stage=1
            )

            # 1) 정예 오크(반경 0.5625m) 선택 시: 벽까지 거리 0.53m < 0.5625m이므로 거절 -> None 반환
            with patch('random.choices', return_value=[AbominableMudOrc]), \
                 patch('random.random', return_value=0.05):  # is_elite = True (0.05 < 0.20)
                spawned = spawn_reinforcement_monster(game, pos=(cand_x, cand_y))
                self.assertIsNone(spawned, "벽까지 거리 0.53m인 후보는 정예 오크(0.5625m)에 대해 반드시 거절되어야 합니다.")

            # 2) 일반 오크(반경 0.45m) 선택 시: 벽까지 거리 0.53m >= 0.45m이므로 허용 및 실제 생성 반경 0.45 일치
            with patch('random.choices', return_value=[AbominableMudOrc]), \
                 patch('random.random', return_value=0.50):  # is_elite = False
                spawned = spawn_reinforcement_monster(game, pos=(cand_x, cand_y))
                self.assertIsNotNone(spawned)
                self.assertAlmostEqual(spawned.col_radius, 0.45)
                self.assertFalse(getattr(spawned, 'is_elite', False))

            # 3) 정예 오크에 대해 충분한 여유(벽 거리 0.65m)가 있는 후보에서는 정상 생성되고 실제 생성 반경 0.5625 일치
            game.monsters.clear()
            clear_custom_colliders()
            register_custom_collider((49.0, 34.0, 51.0, 34.35)) # 거리 = 0.65m
            register_custom_collider((45.0, 27.0, 55.0, 28.0)) # 차폐벽
            with patch('random.choices', return_value=[AbominableMudOrc]), \
                 patch('random.random', return_value=0.05):  # is_elite = True
                spawned_elite = spawn_reinforcement_monster(game, pos=(cand_x, cand_y))
                self.assertIsNotNone(spawned_elite)
                self.assertAlmostEqual(spawned_elite.col_radius, 0.5625)
                self.assertTrue(getattr(spawned_elite, 'is_elite', False))
        finally:
            clear_custom_colliders()


class TestBug6DevHotkeysAndRankingIsolation(unittest.TestCase):
    """Bug 6: 개발 단축키(F5-F8)와 랭킹 기록의 테스트 모드 격리 검증"""

    def test_dev_hotkeys_blocked_in_normal_playing(self):
        """일반 PLAYING 모드에서는 F5~F8 단축키가 작동하지 않음 검증"""
        cam_np = NodePath("cam_node")
        ui_mgr = Mock()
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.is_test_mode = False
        game.game_state = "PLAYING"
        game.test_range = Mock()
        game.spawn_boss = Mock()
        game.player = PlayerController(game, None, cam_np, None, None, ui_mgr)
        game.ui_mgr = ui_mgr
        game.combat = Mock()

        # F5
        game._on_f5_pressed()
        game.test_range.on_f5_pressed.assert_not_called()

        # F6
        game._on_f6_spawn_boss()
        game.spawn_boss.assert_not_called()

        # F7
        with patch.object(game.player, 'gain_exp') as mock_gain_exp:
            game._on_f7_grant_exp()
            mock_gain_exp.assert_not_called()

        # F8
        game._on_f8_test_elemental()
        self.assertFalse(game.player.has_perk("dragons_breath"))
        self.assertFalse(game.player.has_perk("tesla_arc"))
        self.assertEqual(get_perk_level(game.player, "dragons_breath"), 0)
        self.assertEqual(get_perk_level(game.player, "tesla_arc"), 0)

    def test_dev_hotkeys_functional_in_test_mode(self):
        """테스트 모드(is_test_mode=True)에서는 F5~F8 단축키가 정상 작동함 검증"""
        cam_np = NodePath("cam_node")
        ui_mgr = Mock()
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.is_test_mode = True
        game.game_state = "PLAYING"
        game.test_range = Mock()
        game.spawn_boss = Mock()
        game.player = PlayerController(game, None, cam_np, None, None, ui_mgr)
        game.camera = SimpleNamespace(getX=lambda: 0, getY=lambda: 0)
        game.ui_mgr = ui_mgr
        game.combat = Mock()
        game.monsters = []

        game._on_f5_pressed()
        game.test_range.on_f5_pressed.assert_called_once()

        game._on_f6_spawn_boss()
        game.spawn_boss.assert_called_once()

        with patch.object(game.player, 'gain_exp') as mock_gain_exp:
            game._on_f7_grant_exp()
            mock_gain_exp.assert_called_once_with(100)

        game._on_f8_test_elemental()
        self.assertTrue(game.player.has_perk("dragons_breath"))
        self.assertTrue(game.player.has_perk("tesla_arc"))
        self.assertEqual(get_perk_level(game.player, "dragons_breath"), 1)
        self.assertEqual(get_perk_level(game.player, "tesla_arc"), 1)

    def test_f8_repeated_press_does_not_increment_perk_levels(self):
        """반복 F8 입력 시 add_perk 경로를 통해 레벨 1만 유지되고 특성 레벨이 계속 증가하지 않음 검증"""
        cam_np = NodePath("cam_node")
        ui_mgr = Mock()
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.is_test_mode = True
        game.camera = SimpleNamespace(getX=lambda: 0, getY=lambda: 0)
        game.ui_mgr = ui_mgr
        game.combat = Mock()
        game.monsters = []
        game.player = PlayerController(game, None, cam_np, None, None, ui_mgr)

        # 1회 입력: Lv.1 획득
        game._on_f8_test_elemental()
        self.assertTrue(game.player.has_perk("dragons_breath"))
        self.assertTrue(game.player.has_perk("tesla_arc"))
        self.assertEqual(get_perk_level(game.player, "dragons_breath"), 1)
        self.assertEqual(get_perk_level(game.player, "tesla_arc"), 1)

        # 2회 입력: 여전히 Lv.1 유지
        game._on_f8_test_elemental()
        self.assertEqual(get_perk_level(game.player, "dragons_breath"), 1)
        self.assertEqual(get_perk_level(game.player, "tesla_arc"), 1)

        # 3회 입력: 여전히 Lv.1 유지
        game._on_f8_test_elemental()
        self.assertEqual(get_perk_level(game.player, "dragons_breath"), 1)
        self.assertEqual(get_perk_level(game.player, "tesla_arc"), 1)

    def test_ranking_record_isolation_in_test_mode(self):
        """테스트 모드 플레이 결과는 rankings.json에 저장되지 않음 검증"""
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.is_test_mode = True
        game.time_limit = 300.0
        game.time_left = 250.0
        game.current_stage = 1
        game.combat = SimpleNamespace(ammo=10, reserve_ammo=20)
        game.player = SimpleNamespace(lock_mouse=Mock())
        game.audio_mgr = SimpleNamespace(bgm=Mock())
        game.ui_mgr = Mock()
        game.game_won = False
        game.game_over = False
        game.liminal_fog = Mock()
        game.setBackgroundColor = Mock()
        game.amb_np = SimpleNamespace(node=lambda: Mock())

        # 1) 테스트 모드 승리 호출 -> save_rank_record 미호출
        game.trigger_victory()
        game.ui_mgr.save_rank_record.assert_not_called()

        # 2) 테스트 모드 게임 오버 호출 -> save_rank_record 미호출
        game.trigger_game_over(killer=None, reason="timeout")
        game.ui_mgr.save_rank_record.assert_not_called()

        # 3) UIManager.save_rank_record 자체 가드 검증
        ui = UIManager.__new__(UIManager)
        ui.base = SimpleNamespace(is_test_mode=True)
        with patch("builtins.open") as mock_open:
            ui.save_rank_record("탈출 성공", True, 50.0, 250.0, 10)
            mock_open.assert_not_called()

    def test_test_mode_resets_on_normal_restart(self):
        """테스트 모드 상태에서 restart_game 호출 시 is_test_mode가 False로 초기화됨 검증"""
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.is_test_mode = True
        game.test_range = Mock()
        game.clear_projectiles = Mock()
        game.player = Mock()
        game.audio_mgr = Mock()
        game.ui_mgr = Mock()
        game.combat = Mock()
        game.active_chunk_futures = {}
        game.regenerate_map = Mock()
        game.setup_escape_portal = Mock()
        game.spawn_monsters = Mock()
        game.spawn_hazard_barrels = Mock()
        game.spawn_supply_crates = Mock()
        game.liminal_fog = Mock()
        game.setBackgroundColor = Mock()
        game.amb_np = SimpleNamespace(node=lambda: Mock())

        game.restart_game()
        self.assertFalse(game.is_test_mode)
        game.test_range.cleanup_test_room.assert_called_once()


class TestLevelUpPerkDecoupling(unittest.TestCase):
    """사격/처치 시 즉시 퍽 모달 팝업 방지 및 퍽 포인트 누적/수동 오픈 검증"""

    def setUp(self):
        self.game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        self.game.game_state = "PLAYING"
        self.game.game_over = False
        self.game.game_won = False
        self.game._is_level_up_modal = False
        self.game.ui_mgr = Mock()
        self.game.audio_mgr = Mock()
        self.game.combat = Mock()

        # 플레이어 모의 객체
        self.player = Mock()
        self.player.level = 1
        self.player.exp = 0
        self.player.exp_to_next = 100
        self.player.pending_perk_picks = 0
        self.player.hp = 100.0
        self.player.max_hp = 100.0
        self.player.mouse_locked = True
        self.game.player = self.player

        # 실제 PlayerController.gain_exp 및 game 핸들러 바인딩
        self.player.on_level_up = self.game._on_player_level_up
        self.player.audio_mgr = self.game.audio_mgr
        self.player.ui_mgr = self.game.ui_mgr

    def test_gain_exp_does_not_freeze_combat(self):
        """적 처치로 레벨업 시 게임이 멈추지 않고(PLAYING 유지) 퍽 포인트만 누적되는지 검증"""
        # PlayerController.gain_exp 실제 로직 호출
        PlayerController.gain_exp(self.player, 120)

        self.assertEqual(self.player.level, 2)
        self.assertEqual(self.player.exp, 20)
        self.assertEqual(self.player.pending_perk_picks, 1)

        # 게임 상태는 SHOP으로 강제 전환되지 않고 계속 PLAYING 상태 유지
        self.assertEqual(self.game.game_state, "PLAYING")
        self.assertFalse(self.game._is_level_up_modal)

        # 즉각적인 모달 팝업 없이 알림 메시지만 표시
        self.game.ui_mgr.show_levelup_perk_modal.assert_not_called()
        self.game.ui_mgr.show_hit_marker.assert_called()

    def test_tab_key_routes_to_perk_modal_when_pending(self):
        """대기 퍽이 있을 때 Tab 키는 퍽 모달을 열고, 없을 때는 인벤토리를 여는지 검증"""
        self.game.open_inventory = Mock()

        # 1) 대기 퍽이 1개 있는 경우 -> 퍽 모달 오픈
        self.player.pending_perk_picks = 1
        self.game.on_tab_pressed()
        self.assertEqual(self.game.game_state, "SHOP")
        self.assertTrue(self.game._is_level_up_modal)
        self.game.ui_mgr.show_levelup_perk_modal.assert_called_once()
        self.game.open_inventory.assert_not_called()

        # 2) 대기 퍽이 0개인 경우 -> 인벤토리 오픈
        self.game.game_state = "PLAYING"
        self.game._is_level_up_modal = False
        self.player.pending_perk_picks = 0
        self.game.on_tab_pressed()
        self.game.open_inventory.assert_called_once()

    def test_close_level_up_modal_preserves_perk_points(self):
        """퍽 모달을 ESC나 Tab으로 닫았을 때 퍽 포인트가 보존되고 전투로 복귀하는지 검증"""
        self.player.pending_perk_picks = 2
        self.game.open_perk_modal()
        self.assertEqual(self.game.game_state, "SHOP")

        # 닫기 실행 (handle_escape)
        self.game.handle_escape()
        self.assertEqual(self.game.game_state, "PLAYING")
        self.assertFalse(self.game._is_level_up_modal)
        self.assertEqual(self.player.pending_perk_picks, 2)  # 포인트 유지됨

    def test_stage_clear_shop_presents_unspent_perks(self):
        """스테이지 상점 완료 시 잔여 퍽 선택 포인트가 남아있으면 퍽 모달이 호출되는지 검증"""
        self.game.advance_to_next_stage = Mock()
        self.player.pending_perk_picks = 1

        self.game.on_shop_closed()
        self.game.advance_to_next_stage.assert_called_once()
        self.game.ui_mgr.show_levelup_perk_modal.assert_called_once()


if __name__ == "__main__":
    unittest.main()

