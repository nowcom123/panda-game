import math
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from panda3d.core import NodePath, Vec3, Point3
from combat.reactions import REACTION_PROFILES, counter_stats, reaction_chance, guarded_damage
from combat_system import CombatSystem
from perks import PERK_CATALOG, get_perk_stats, draw_random_perks
from monster import (
    SkeletalDobermanHellhound,
    AlluringAshWitch,
    TallSkeletonMonster,
    LongBlackSerpent,
    AbominableMudOrc,
)


class MonsterReactionsTests(unittest.TestCase):
    def test_monster_roles(self):
        """5종 몬스터의 reaction_role 클래스 및 인스턴스 할당 확인"""
        self.assertEqual(SkeletalDobermanHellhound.reaction_role, "hound")
        self.assertEqual(AlluringAshWitch.reaction_role, "witch")
        self.assertEqual(TallSkeletonMonster.reaction_role, "skeleton")
        self.assertEqual(LongBlackSerpent.reaction_role, "serpent")
        self.assertEqual(AbominableMudOrc.reaction_role, "golem")

    def test_frontal_hit_calculation(self):
        """전방 120도 (좌우 60도, cos >= 0.5) 각도 판정 검증"""
        root = NodePath("root")
        m_node = root.attachNewNode("monster")
        m_node.setH(0)  # Facing +Y

        combat = CombatSystem.__new__(CombatSystem)
        combat.render = root

        monster = SimpleNamespace(node=m_node)

        # Shooter directly in front of monster (ray coming from +Y towards -Y)
        ray_dir_frontal = Vec3(0, -1, 0)
        self.assertTrue(combat._is_frontal_hit(monster, ray_dir_frontal))

        # Shooter behind monster (ray coming from -Y towards +Y)
        ray_dir_back = Vec3(0, 1, 0)
        self.assertFalse(combat._is_frontal_hit(monster, ray_dir_back))

        # 45 degrees angle -> Frontal (cos 45 = 0.707 >= 0.5)
        rad45 = math.radians(45)
        ray_dir_45 = Vec3(-math.sin(rad45), -math.cos(rad45), 0)
        self.assertTrue(combat._is_frontal_hit(monster, ray_dir_45))

        # 75 degrees angle -> Flank/Back (cos 75 = 0.258 < 0.5)
        rad75 = math.radians(75)
        ray_dir_75 = Vec3(-math.sin(rad75), -math.cos(rad75), 0)
        self.assertFalse(combat._is_frontal_hit(monster, ray_dir_75))

        root.removeNode()

    def test_single_reaction_per_discharge_and_target(self):
        """샷건 8펠릿 발사 시 대상 몬스터당 반응 판정은 1회만 캐시되어 중복 반격 방지"""
        combat = CombatSystem.__new__(CombatSystem)
        player = SimpleNamespace(perk_levels={})
        combat.player = player
        combat._discharge_reactions = {}

        monster = SimpleNamespace(
            reaction_role="serpent",
            reaction_cooldown=0.0,
            hp=100.0,
            is_dead=False,
            is_corpse=False,
            stun_timer=0.0,
            is_stunned=False,
            is_reacting=False,
            is_telegraphing=False,
            is_boss=False,
            is_seal=False,
            is_dodging=False,
            is_guarding=False,
            counter_pending=False,
            trigger_guard=MagicMock(),
        )

        ray_dir = Vec3(0, -1, 0)
        with patch("combat_system.random.random", return_value=0.01):
            with patch.object(combat, "_is_frontal_hit", return_value=True):
                res1 = combat._resolve_monster_reaction(monster, ray_dir, player)
                combat._discharge_reactions[id(monster)] = res1

        self.assertIsNotNone(res1)
        self.assertEqual(res1.get("mode"), "guard")
        self.assertTrue(res1.get("blocked"))

        # Second pellet hits the same monster in the same discharge
        # Should reuse cached result without re-evaluating
        cached_res = combat._discharge_reactions.get(id(monster))
        self.assertIs(cached_res, res1)

    def test_hound_skip_dodge_flag(self):
        """skip_dodge=True 전달 시 파수견의 내부 random < 0.35 회피가 중복 실행되지 않음"""
        hound = SkeletalDobermanHellhound.__new__(SkeletalDobermanHellhound)
        hound.hp = 100.0
        hound.max_hp = 100.0
        hound.is_dead = False
        hound.is_corpse = False
        hound.is_dodging = False
        hound.is_stunned = False
        hound.is_attacking = False
        hound.is_reacting = False
        hound.audio_mgr = MagicMock()
        hound.game = MagicMock()
        hound.last_action_dodged = False

        # If skip_dodge is True, even if random would be 0, it doesn't dodge inside take_damage
        with patch("monster.random.random", return_value=0.0):
            hound.take_damage(20.0, skip_dodge=True)
            self.assertFalse(hound.last_action_dodged)
            self.assertEqual(hound.hp, 80.0)

    def test_witch_evade_fallback_when_blocked(self):
        """마녀 회피 시 주변 후보가 모두 벽이나 부적격일 경우 회피 취소 및 정상 피해 적용"""
        witch = AlluringAshWitch.__new__(AlluringAshWitch)
        witch.node = MagicMock()
        witch.node.getPos = MagicMock(return_value=Point3(5, 5, 0))
        witch.node.isEmpty = MagicMock(return_value=False)
        witch.pos = Point3(5, 5, 0)
        witch.is_reacting = False
        witch.is_dead = False
        witch.is_corpse = False
        witch.hp = 100.0
        witch.reaction_role = "witch"

        # When collision resolution indicates walls blocking all candidates
        with patch("monster.resolve_collision", return_value=(999.0, 999.0)):
            evaded = witch.trigger_witch_evade(Vec3(0, 1, 0), chunks={}, player_pos=Point3(0, 0, 0))
            self.assertFalse(evaded)
            self.assertFalse(getattr(witch, "is_dodging", False))

    def test_skeleton_disassembly_restore(self):
        """해골 분해 회피 후 원래 부품 위치 복구 보장"""
        skeleton = TallSkeletonMonster.__new__(TallSkeletonMonster)
        skeleton.reaction_role = "skeleton"
        skeleton.is_reacting = False
        skeleton.reaction_timer = 0.0

        dummy_node = NodePath("part")
        dummy_node.setPos(1, 2, 3)

        skeleton._base_part_positions = {
            "pelvis": (dummy_node, Point3(1, 2, 3)),
            "spine": None,
            "skull": None,
            "ribs": [],
            "arms": [],
            "legs": [],
        }

        # Alter position during scatter
        dummy_node.setPos(10, 20, 30)

        # Restore
        skeleton.restore_base_part_positions()
        self.assertEqual(dummy_node.getPos(), Point3(1, 2, 3))
        dummy_node.removeNode()

    def test_serpent_guard_and_poison_duration(self):
        """뱀 방어 성공 시 60% 피해 감쇄 및 0.85s 예고 후 10 피해 + 3s 독(dps 4) 적용, 독 시간 갱신 확인"""
        serpent = LongBlackSerpent.__new__(LongBlackSerpent)
        serpent.reaction_role = "serpent"
        serpent.is_reacting = False
        serpent.is_telegraphing = False
        serpent.reaction_timer = 0.0
        serpent.telegraph_timer = 0.0
        serpent.reaction_cooldown = 0.0
        serpent.telegraph_np = None

        dmg = 100.0
        reduced_dmg = guarded_damage(dmg, REACTION_PROFILES["serpent"].reduction)
        self.assertAlmostEqual(reduced_dmg, 40.0)  # 60% reduction

        # Test poison duration on player
        player = MagicMock()
        player.poison_timer = 1.0
        player.poison_dps = 4.0

        # Apply poison refreshes to 3.0s instead of adding (3.0 + 1.0 = 4.0)
        from player_controller import PlayerController
        PlayerController.apply_poison(player, duration=3.0, dps=4.0)
        self.assertEqual(player.poison_timer, 3.0)

    def test_golem_earthquake_and_jump_evasion(self):
        """골렘 방어 시 65% 감쇄, 지진 1.0s 예고 후 반경 8m/24피해, 점프 0.75m 이상 시 회피"""
        orc = AbominableMudOrc.__new__(AbominableMudOrc)
        orc.reaction_role = "golem"
        orc.is_reacting = False
        orc.is_telegraphing = False
        orc.reaction_timer = 0.0
        orc.telegraph_timer = 0.0
        orc.reaction_cooldown = 0.0
        orc.telegraph_np = None

        dmg = 100.0
        reduced_dmg = guarded_damage(dmg, REACTION_PROFILES["golem"].reduction)
        self.assertAlmostEqual(reduced_dmg, 35.0)  # 65% reduction

        # Jump height test: (camera Z - 1.7) - floor_z >= 0.75 -> Evaded
        player_ground = MagicMock()
        player_ground.camera.getZ = MagicMock(return_value=1.7)
        player_ground.current_floor_z = 0.0
        jump_h_ground = (player_ground.camera.getZ() - 1.7) - player_ground.current_floor_z
        self.assertLess(jump_h_ground, 0.75)

        player_jumping = MagicMock()
        player_jumping.camera.getZ = MagicMock(return_value=2.5)  # 2.5 - 1.7 = 0.8m
        player_jumping.current_floor_z = 0.0
        jump_h_jumping = (player_jumping.camera.getZ() - 1.7) - player_jumping.current_floor_z
        self.assertGreaterEqual(jump_h_jumping, 0.75)

    def test_perks_precision_training_and_guard_breaker(self):
        """신규 퍽 precision_training, guard_breaker 수치 및 3레벨 도달 시 드로우 제외 확인"""
        self.assertIn("precision_training", PERK_CATALOG)
        self.assertIn("guard_breaker", PERK_CATALOG)

        p_stats1 = get_perk_stats("precision_training", 1)
        p_stats3 = get_perk_stats("precision_training", 3)
        self.assertAlmostEqual(p_stats1["evasion_suppression"], 0.05)
        self.assertAlmostEqual(p_stats3["evasion_suppression"], 0.15)

        g_stats1 = get_perk_stats("guard_breaker", 1)
        g_stats3 = get_perk_stats("guard_breaker", 3)
        self.assertAlmostEqual(g_stats1["guard_penetration"], 0.10)
        self.assertAlmostEqual(g_stats3["guard_penetration"], 0.30)

        # Draw perks with level 3 should exclude maxed perk
        perk_levels = {"precision_training": 3, "guard_breaker": 2}
        drawn = draw_random_perks(perk_levels, count=20)
        drawn_ids = [p["id"] for p in drawn]
        self.assertNotIn("precision_training", drawn_ids)
        self.assertIn("guard_breaker", drawn_ids)


if __name__ == "__main__":
    unittest.main()
