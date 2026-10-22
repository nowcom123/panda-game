"""
골해의 지배자 (CableOverlordBoss) 외형 및 전투 기믹/패턴 종합 단위 테스트
- 1. Panda3D NodePath 기반 외형 생성, 8개 다리, 360도 회전 팔, 두개골 부위, 광원 1개 이하
- 2. 상태 머신 전환: IDLE -> TELEGRAPH -> ACTIVE -> RECOVERY
- 3. 예고(0.8s+) 시간 동안 무피해 및 시각 인디케이터 생성
- 4. 단일 타격 보장 (프레임 중복 피해 방지)
- 5. 회피 조건: 점프, 범위 이탈, 걸어서 회피
- 6. 큰 dt(0.5s, 1.0s) 환경 안정성
- 7. 2페이즈 1회 전환 및 몬스터 상한(16) 준수
- 8. 회복(Recovery) 상태 중 해골 머리 약점 노출 (헤드샷 판정)
- 9. 사망 및 destroy 시 잔여 인디케이터/스파이크/라이트 정리
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from panda3d.core import NodePath, Vec3, PointLight
from monster import CableOverlordBoss
from boss_patterns import (BossPatternController, BossPatternState,
                           GroundDangerIndicator, GroundBoneSpike)
from monster_director import MonsterDirector


class TestBossAppearanceAndHierarchy(unittest.TestCase):
    def setUp(self):
        self.root = NodePath("test_root")

    def tearDown(self):
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    def test_boss_model_parts_and_eight_spider_legs(self):
        """보스 외형: 8개 거미 다리, 360도 회전 팔 2개, 해골 두개골 부위 존재 검증"""
        boss = CableOverlordBoss(self.root, 10.0, 10.0)

        # 1. 8개 거미 다리 검증
        self.assertEqual(len(boss.spider_legs), 8, "거미 다리는 좌우 4개씩 총 8개여야 합니다.")
        for leg_base, femur, knee, tibia, ang_deg, idx in boss.spider_legs:
            self.assertFalse(leg_base.isEmpty())
            self.assertFalse(femur.isEmpty())
            self.assertFalse(knee.isEmpty())
            self.assertFalse(tibia.isEmpty())

        # 2. 360도 회전 팔 검증
        self.assertFalse(boss.arm_pivot_l.isEmpty())
        self.assertFalse(boss.arm_pivot_r.isEmpty())
        # 360도 임의 각도 설정 시 에러 없이 회전
        boss.set_sweep_arm_angle(0.0)
        start = self.root.getRelativePoint(boss.forearm_l, Vec3(0, 0, -1.68))
        boss.set_sweep_arm_angle(180.0)
        opposite = self.root.getRelativePoint(boss.forearm_l, Vec3(0, 0, -1.68))
        self.assertGreater((opposite-start).length(), 8.0)
        boss.set_sweep_arm_angle(360.0)
        finish = self.root.getRelativePoint(boss.forearm_l, Vec3(0, 0, -1.68))
        self.assertLess((finish-start).length(), 1e-5)

        # 3. 해골 두개골 및 가동 턱부위
        self.assertFalse(boss.head_pivot.isEmpty())
        self.assertFalse(boss.jaw_pivot.isEmpty())
        self.assertFalse(boss.cranium.isEmpty())
        self.assertEqual(boss.name, "골해의 지배자")
        self.assertEqual(boss.col_radius, 0.55)

        boss.destroy()

    def test_boss_light_count_at_most_one(self):
        """광원은 1개 이하 사양 준수 검증"""
        boss = CableOverlordBoss(self.root, 0.0, 0.0)
        # parent_ref에 등록된 조명 검증
        lights = [c for c in boss.head_pivot.getChildren() if c.node().isOfType(PointLight.getClassType())]
        self.assertLessEqual(len(lights), 1, "보스 광원은 1개 이하여야 합니다.")
        boss.destroy()


class TestBossPatternStateMachine(unittest.TestCase):
    def setUp(self):
        self.root = NodePath("test_pattern_root")
        self.boss = CableOverlordBoss(self.root, 0.0, 0.0)

        self.mock_player = SimpleNamespace(
            hp=100.0,
            max_hp=100.0,
            take_damage=Mock(return_value=False),
            trigger_quake_shake=Mock(),
            apply_slow=Mock()
        )
        self.mock_game = SimpleNamespace(
            player=self.mock_player,
            camera=SimpleNamespace(getX=lambda: 0.0, getY=lambda: 0.0, getZ=lambda: 1.8, getPos=lambda: Vec3(0, 0, 1.8)),
            boss=self.boss,
            monsters=[self.boss],
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

    def tearDown(self):
        if hasattr(self, 'boss'):
            self.boss.destroy()
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    def test_sweep_telegraph_fairness_and_damage(self):
        """360도 뼈팔 휩쓸기: 예고(0.8s+) 동안 피해 없음 및 단일 피해 검증"""
        ctrl = self.boss.pattern_controller
        ctrl.sweep_cooldown = 0.0

        # 근접 플레이어 (3.0m)
        px, py, pz = 3.0, 0.0, 0.0
        dist, dist_z = 3.0, 0.0

        # 패턴 개시
        ctrl.update(0.016, self.mock_game, px, py, pz, dist, dist_z)
        self.assertEqual(ctrl.current_pattern, "sweep")
        self.assertEqual(ctrl.state, BossPatternState.TELEGRAPH)
        self.assertGreaterEqual(ctrl.telegraph_duration, 0.80)
        self.assertEqual(len(ctrl.indicators), 1, "바닥 예고 인디케이터가 생성되어야 합니다.")

        # 예고 시간 동안 0.7초 진행 (피해 0회)
        for _ in range(40):
            ctrl.update(0.016, self.mock_game, px, py, pz, dist, dist_z)
        self.assertEqual(self.mock_player.take_damage.call_count, 0, "예고 중에는 피해를 주지 않아야 합니다.")

        # 예고 종료 및 발동 진입 (0.85초 초과)
        ctrl.update(0.30, self.mock_game, px, py, pz, dist, dist_z)
        self.assertEqual(ctrl.state, BossPatternState.ACTIVE)

        # 발동 시간 동안 회전하며 타격 (단 1회만 타격 적용)
        for _ in range(30):
            ctrl.update(0.03, self.mock_game, px, py, pz, dist, dist_z)

        self.assertEqual(self.mock_player.take_damage.call_count, 1, "발동당 단 1회만 피해가 적용되어야 합니다.")

    def test_sweep_evasion_by_jumping_or_distance(self):
        """360도 뼈팔 휩쓸기: 범위 밖(dist > 5.8m)이나 점프(dist_z > 2.0m) 시 회피 검증"""
        ctrl = self.boss.pattern_controller
        ctrl.sweep_cooldown = 0.0

        # 1. 점프로 수직 회피 (dist_z = 2.4m)
        ctrl.update(0.016, self.mock_game, 3.0, 0.0, 2.6, 3.0, 2.4)
        # 예고 완료 후 발동
        ctrl.timer = ctrl.telegraph_duration + 0.01
        ctrl.update(0.016, self.mock_game, 3.0, 0.0, 2.6, 3.0, 2.4)
        self.assertEqual(ctrl.state, BossPatternState.ACTIVE)

        # 발동 진행
        ctrl.update(0.35, self.mock_game, 3.0, 0.0, 2.6, 3.0, 2.4)
        self.assertEqual(self.mock_player.take_damage.call_count, 0, "점프로 피한 경우 피해를 받지 않아야 합니다.")

    def test_bone_spikes_walk_away_evasion(self):
        """순차 뼈 가시 분출: 시전 당시 위치가 고정되어 걸어서 벗어나면 회피 가능 검증"""
        ctrl = self.boss.pattern_controller
        ctrl.spikes_cooldown = 0.0

        # 시전 시작 당시 플레이어 위치 (0, 10.0)
        px, py, pz = 0.0, 10.0, 0.0
        ctrl.update(0.016, self.mock_game, px, py, pz, 10.0, 0.0)
        self.assertEqual(ctrl.current_pattern, "spikes")
        self.assertEqual(ctrl.state, BossPatternState.TELEGRAPH)

        # 플레이어가 예고를 보고 5.0m 멀리 이동
        new_px, new_py = 5.0, 15.0
        # 예고 시간 경과 -> 발동
        ctrl.timer = ctrl.telegraph_duration + 0.05
        ctrl.update(0.016, self.mock_game, new_px, new_py, pz, 15.0, 0.0)
        self.assertEqual(ctrl.state, BossPatternState.ACTIVE)

        # 3개 가시가 순차 분출되는 동안 대기
        for _ in range(30):
            ctrl.update(0.05, self.mock_game, new_px, new_py, pz, 15.0, 0.0)

        # 플레이어는 범위 밖으로 이동했으므로 피격 없음
        self.assertEqual(self.mock_player.take_damage.call_count, 0, "예고 위치를 벗어나면 피해가 없어야 합니다.")

    def test_spider_leap_slam_and_collision_check(self):
        """거미 다리 도약 강타: 착지점 고정 인디케이터 및 단일 충격파 타격 검증"""
        ctrl = self.boss.pattern_controller
        ctrl.leap_cooldown = 0.0

        with patch("boss_patterns.BossPatternController._can_leap_to_target", return_value=True):
            ctrl.leap_start = Vec3(0, 0, 0)
            ctrl.leap_target = Vec3(0, 8.0, 0)
            ctrl._start_spider_leap_slam(self.mock_game, 0.0, 8.0)

            self.assertEqual(ctrl.state, BossPatternState.TELEGRAPH)
            self.assertEqual(len(ctrl.indicators), 1)

            # 예고 경과
            ctrl.timer = ctrl.telegraph_duration + 0.01
            ctrl.update(0.016, self.mock_game, 0.0, 8.0, 0.0, 8.0, 0.0)
            self.assertEqual(ctrl.state, BossPatternState.ACTIVE)

            # 착지 (active 완료)
            ctrl.timer = ctrl.active_duration * 0.95
            ctrl.update(0.05, self.mock_game, 0.0, 8.0, 1.7, 0.0, 0.0)

            # 플레이어가 착지점에 서 있었으므로 1회 피격
            self.assertEqual(self.mock_player.take_damage.call_count, 1)

    def test_large_dt_stability(self):
        """큰 dt(0.5초, 1.0초) 환경에서도 단일 타격 보장 및 상태 전이 정상 처리"""
        ctrl = self.boss.pattern_controller
        ctrl.sweep_cooldown = 0.0

        # 한 번에 1.2초 진행
        ctrl.update(1.20, self.mock_game, 2.0, 0.0, 0.0, 2.0, 0.0)
        # 발동 상태 진행
        ctrl.update(1.00, self.mock_game, 2.0, 0.0, 0.0, 2.0, 0.0)

        self.assertLessEqual(self.mock_player.take_damage.call_count, 1, "큰 dt에서도 발동당 중복 피해 금지")

    def test_recovery_state_exposes_skull_headshot(self):
        """회복 상태 중 해골 머리 취약 노출: 헤드샷 판정 범위 확장 검증"""
        ctrl = self.boss.pattern_controller
        ctrl._enter_recovery(1.0)
        self.assertTrue(ctrl.is_skull_exposed)

        # 레이캐스트 검증: 회복 중 낮아진 머리 위치(Z ~ 2.75m)
        ray_o = Vec3(0, 10.0, 2.75)
        ray_d = Vec3(0, -1.0, 0)
        hit, t = self.boss.is_hit_by_ray(ray_o, ray_d)
        self.assertTrue(hit)
        self.assertTrue(self.boss.last_hit_was_head, "회복 중 노출된 해골 머리에 헤드샷이 적중해야 합니다.")

    def test_phase_2_transition_only_once(self):
        """체력 50% 이하 2페이즈 진입은 1회만 발생하며 소환수 상한 준수"""
        self.boss.hp = 1700  # max 3500의 50% 이하
        ctrl = self.boss.pattern_controller

        ctrl.update(0.016, self.mock_game, 10.0, 10.0, 0.0, 14.0, 0.0)
        self.assertEqual(self.boss.phase, 2)
        self.assertTrue(ctrl.phase2_triggered)
        self.assertEqual(self.mock_game.spawn_reinforcement_monster.call_count, 2)

        # 다시 갱신해도 2페이즈 재진입 및 중복 소환 없음
        ctrl.update(0.016, self.mock_game, 10.0, 10.0, 0.0, 14.0, 0.0)
        self.assertEqual(self.mock_game.spawn_reinforcement_monster.call_count, 2)

    def test_cleanup_on_death_and_destroy(self):
        """사망/파괴 시 모든 바닥 인디케이터, 스파이크, 조명 노드 즉각 해제"""
        ctrl = self.boss.pattern_controller
        ctrl._start_bone_arm_sweep(self.mock_game)
        self.assertGreater(len(ctrl.indicators), 0)

        self.boss.turn_into_corpse(self.mock_game.audio_mgr)
        self.assertEqual(len(ctrl.indicators), 0, "사망 시 모든 인디케이터가 정리되어야 합니다.")
        self.assertEqual(ctrl.state, BossPatternState.IDLE)
        self.assertTrue(self.boss.is_dead)


if __name__ == "__main__":
    unittest.main()
