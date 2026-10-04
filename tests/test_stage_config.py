"""Stage composition contracts without loading the renderer."""

import unittest
from collections import Counter

from stage_config import build_monster_roster, get_stage_profile


class StageComposition(unittest.TestCase):
    def test_first_two_floors_keep_original_composition(self):
        for stage, expected in (
            (1, dict(stalker=1, orc=2, witch=2, serpent=1, skeleton=1)),
            (2, dict(stalker=2, orc=3, witch=3, serpent=1, skeleton=1)),
        ):
            with self.subTest(stage=stage):
                self.assertEqual(Counter(build_monster_roster(stage)), expected)

    def test_deep_floors_cycle_without_extra_monsters_or_unbounded_stalkers(self):
        for stage in range(3, 101):
            with self.subTest(stage=stage):
                roster = Counter(build_monster_roster(stage))
                self.assertEqual(sum(roster.values()), 8 + (stage - 1) * 2)
                self.assertEqual(set(roster), {'stalker', 'orc', 'witch', 'serpent', 'skeleton'})
                self.assertLessEqual(roster['stalker'], 5)
                self.assertEqual(get_stage_profile(stage), get_stage_profile(stage + 3))

    def test_invalid_floor_is_rejected(self):
        for stage in (0, -1):
            with self.subTest(stage=stage):
                with self.assertRaises(ValueError):
                    get_stage_profile(stage)
                with self.assertRaises(ValueError):
                    build_monster_roster(stage)
