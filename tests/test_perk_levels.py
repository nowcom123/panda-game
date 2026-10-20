"""Repeated picks must improve effects, not just an owned flag."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from panda3d.core import NodePath
from perks import (PERK_CATALOG, get_perk_level, get_perk_stats,
                   get_player_perk_stats, draw_random_perks, describe_perk)
from player_controller import PlayerController


class PerkLevelTests(unittest.TestCase):
    def make_player(self):
        return PlayerController(SimpleNamespace(game_state='PLAYING'), None,
                                NodePath('camera'), None, None, Mock())

    def test_every_duplicate_increases_level_and_effects(self):
        for perk_id in PERK_CATALOG:
            with self.subTest(perk_id=perk_id):
                player = self.make_player()
                player.add_perk(perk_id)
                first = get_player_perk_stats(player, perk_id)
                player.add_perk(perk_id)
                self.assertEqual(get_perk_level(player, perk_id), 2)
                self.assertEqual(len(player.perks), 1)
                self.assertNotEqual(first, get_player_perk_stats(player, perk_id))
                self.assertNotEqual(describe_perk(perk_id, 1), describe_perk(perk_id, 2))

    def test_speed_stacks_without_reapplying_relic_or_double_scaling_reload(self):
        player = self.make_player()
        player.speed_mult = 1.30
        combat = SimpleNamespace(is_reloading=True, reload_timer=2.0)
        player.add_perk('speed_demon', combat)
        player.add_perk('speed_demon', combat)
        self.assertAlmostEqual(player.speed_mult, 1.30 * 1.40)
        self.assertAlmostEqual(combat.reload_timer, 2 * .65**2)
        self.assertAlmostEqual(get_player_perk_stats(player, 'speed_demon')['stamina_mult'], .36)

    def test_armor_damage_and_slow_improve_on_second_pick(self):
        player = self.make_player()
        player.add_perk('titan_armor')
        player.add_perk('titan_armor')
        self.assertEqual(player.max_hp, 150)
        player.take_damage(40)
        self.assertAlmostEqual(player.hp, 150 - 40*.75**2)
        player.apply_slow(duration=4, factor=.4)
        self.assertAlmostEqual(player.slow_timer, 1)
        self.assertAlmostEqual(player.slow_factor, .85)

    def test_owned_perk_is_eligible_before_all_perks_are_owned(self):
        owned = next(iter(PERK_CATALOG))
        with patch('perks.random.choices', side_effect=lambda population, **kw: [population[0]]):
            choices = draw_random_perks({owned}, count=3)
        self.assertIn(owned, [c['id'] for c in choices])
        self.assertEqual(len({c['id'] for c in choices}), 3)

    def test_legacy_owned_perk_upgrades_from_one_to_two(self):
        player = self.make_player()
        player.perks.add('ricochet')
        self.assertEqual(get_perk_level(player, 'ricochet'), 1)
        player.add_perk('ricochet')
        self.assertEqual(get_perk_level(player, 'ricochet'), 2)

    def test_effect_counts_and_reload_times_remain_bounded(self):
        self.assertEqual(get_perk_stats('cluster_grenade', 100)['count'], 12)
        self.assertEqual(get_perk_stats('tesla_arc', 100)['targets'], 8)
        self.assertGreaterEqual(get_perk_stats('speed_demon', 100)['reload_mult'], .1)
        self.assertGreater(get_perk_stats('cluster_grenade', 100)['damage'],
                           get_perk_stats('cluster_grenade', 99)['damage'])

    def test_unknown_perk_is_not_granted(self):
        player = self.make_player()
        with self.assertRaises(ValueError):
            player.add_perk('not_a_perk')
        self.assertFalse(player.perks)
        self.assertFalse(player.perk_levels)


if __name__ == '__main__':
    unittest.main()
