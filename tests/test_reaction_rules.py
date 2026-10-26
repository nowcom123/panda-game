import unittest

from combat.reactions import REACTION_PROFILES, counter_stats, reaction_chance, guarded_damage


class ReactionRulesTests(unittest.TestCase):
    def test_exclusive_roles_and_hound_baseline(self):
        self.assertEqual(REACTION_PROFILES['hound'].chance, .35)
        self.assertEqual(REACTION_PROFILES['witch'].mode, 'evade')
        self.assertEqual(REACTION_PROFILES['skeleton'].mode, 'evade')
        self.assertEqual(REACTION_PROFILES['serpent'].mode, 'guard')
        self.assertEqual(REACTION_PROFILES['golem'].mode, 'guard')

    def test_precision_counters_evade_without_reducing_guard_chance(self):
        stats = counter_stats(3, 0)
        self.assertAlmostEqual(reaction_chance(REACTION_PROFILES['witch'], stats['evasion_suppression']), .10)
        self.assertAlmostEqual(reaction_chance(REACTION_PROFILES['hound'], stats['evasion_suppression']), .20)
        self.assertEqual(reaction_chance(REACTION_PROFILES['serpent'], 1), .30)
        self.assertEqual(reaction_chance(REACTION_PROFILES['witch'], 1), 0)

    def test_penetration_changes_only_blocked_damage(self):
        self.assertAlmostEqual(guarded_damage(100, .60), 40)
        self.assertAlmostEqual(guarded_damage(100, .60, .30), 58)
        self.assertAlmostEqual(guarded_damage(100, .65, .30), 54.5)
        self.assertEqual(guarded_damage(100, 0, .30), 100)

    def test_stat_caps_and_negative_levels(self):
        self.assertEqual(counter_stats(-3, -1), counter_stats())
        self.assertEqual(counter_stats(999, 999), counter_stats(3, 3))
        self.assertEqual(guarded_damage(-10, .60), 0)
        self.assertEqual(guarded_damage(100, .60, 999), 100)
