"""Perk upgrades exercised through the production hit and reload paths."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from panda3d.core import NodePath, Vec3
from player_controller import PlayerController
from combat_system import CombatSystem, WEAPON_CONFIGS
from projectiles import FragGrenade


class Target:
    def __init__(self, x=0, y=5, headshot=False):
        self.pos = Vec3(x, y, 0)
        self.hp = self.max_hp = 10000
        self.is_corpse = False
        self.last_hit_was_head = headshot
        self.hits = []
        self.apply_burn = Mock()
        self.apply_shock = Mock()

    def is_hit_by_ray(self, origin, direction):
        distance = self.pos.y - origin.y
        return abs(self.pos.x - origin.x) < .3 and distance > 0, distance

    def take_damage(self, damage, **kwargs):
        self.hits.append(damage)
        self.hp -= damage
        return self.hp <= 0


class PerkRuntimeTests(unittest.TestCase):
    def setup_combat(self, perk, level):
        camera = NodePath('camera')
        player = PlayerController(SimpleNamespace(game_state='PLAYING'), None,
                                  camera, None, None, Mock())
        for _ in range(level):
            player.add_perk(perk)
        combat = CombatSystem.__new__(CombatSystem)
        combat.camera = camera
        combat.base = SimpleNamespace(chunks={}, player=player, trigger_bullet_time=Mock())
        combat.render = combat.world_root = NodePath('world')
        combat.ui_mgr = Mock()
        combat.audio_mgr = None
        combat.spawn_hit_particles = Mock()
        combat._spawn_tracer_effect = Mock()
        combat.register_kill = Mock()
        combat.update_ammo_ui = Mock()
        combat.current_weapon = 'PISTOL'
        combat.weapon_states = {'PISTOL': {'max_ammo': 12}}
        combat.ammo = 6
        combat.max_ammo = 12
        combat.combo_count = 0
        return combat, player

    def shoot(self, combat, player, targets, wall=55):
        def wall_query(chunks, origin, direction, **kwargs):
            return max(0, wall-origin.y), Vec3(0, wall, 0)
        with patch('combat_system.raycast_walls', side_effect=wall_query):
            return combat._perform_raycast(Vec3(0, 1, 0), Vec3(0, .5, 0),
                                           targets, player, None, False, WEAPON_CONFIGS['PISTOL'])

    def test_level_two_burn_uses_upgraded_dps_and_duration(self):
        combat, player = self.setup_combat('dragons_breath', 2)
        target = Target()
        self.shoot(combat, player, [target])
        target.apply_burn.assert_called_once_with(dps=35, duration=3.5)

    def test_level_two_headshot_lifesteal_heals_ten(self):
        combat, player = self.setup_combat('vampiric_leech', 2)
        player.hp = 40
        self.shoot(combat, player, [Target(headshot=True)])
        self.assertEqual(player.hp, 50)

    def test_level_two_headhunter_scales_actual_damage(self):
        combat, player = self.setup_combat('headhunter', 2)
        target = Target(headshot=True)
        self.shoot(combat, player, [target])
        expected_dmg = WEAPON_CONFIGS['PISTOL']['damage'] * WEAPON_CONFIGS['PISTOL']['headshot_mult'] * 1.9
        self.assertAlmostEqual(target.hits[0], expected_dmg)

    def test_level_two_tesla_hits_three_secondary_targets(self):
        combat, player = self.setup_combat('tesla_arc', 2)
        primary = Target(headshot=True)
        secondary = [Target(x=x) for x in (1, 2, 3, 4)]
        self.shoot(combat, player, [primary] + secondary)
        self.assertEqual(sum(t.apply_shock.call_count for t in secondary), 3)
        for target in secondary[:3]:
            self.assertEqual(target.apply_shock.call_args.kwargs['damage'], 50)

    def test_level_two_pierces_two_targets_but_not_walls(self):
        for wall, hit_count in ((55, 3), (10, 2)):
            combat, player = self.setup_combat('armor_piercing', 2)
            targets = [Target(y=y) for y in (5, 8, 11, 14)]
            self.shoot(combat, player, targets, wall=wall)
            self.assertEqual(sum(len(t.hits) for t in targets), hit_count)
            self.assertEqual(len(targets[-1].hits), 0)

    def test_level_two_reload_duration_is_used(self):
        combat, player = self.setup_combat('speed_demon', 2)
        self.assertAlmostEqual(combat.reload_duration, WEAPON_CONFIGS['PISTOL']['reload_time'] * .65**2)

    def test_level_two_adrenaline_damage_and_time(self):
        combat, player = self.setup_combat('adrenaline_slide', 2)
        player.is_sliding = True
        target = Target()
        self.shoot(combat, player, [target])
        self.assertAlmostEqual(target.hits[0], WEAPON_CONFIGS['PISTOL']['damage'] * 1.85 * 2)
        combat.base.trigger_bullet_time.assert_called_once_with(2.2)

    def test_level_two_kill_effects(self):
        for perk in ('vampiric_leech', 'bullet_storm', 'shrapnel_burst', 'headhunter'):
            with self.subTest(perk=perk):
                combat, player = self.setup_combat(perk, 2)
                player.hp = 20
                player.gain_exp = Mock()
                target = Target(headshot=perk == 'headhunter')
                target.hp = 1
                secondary = Target(x=2)
                self.shoot(combat, player, [target, secondary])
                if perk == 'vampiric_leech':
                    self.assertEqual(player.hp, 44)
                elif perk == 'bullet_storm':
                    self.assertEqual(combat.bullet_storm_timer, 4.5)
                elif perk == 'shrapnel_burst':
                    self.assertAlmostEqual(secondary.hits[0], 100 * (1 - 2/4.2*.4))
                else:
                    player.gain_exp.assert_called_once_with(35 * 3)

    def test_level_two_ricochet_damage(self):
        combat, player = self.setup_combat('ricochet', 2)
        target = Target(x=1, y=6)
        self.shoot(combat, player, [target], wall=5)
        self.assertAlmostEqual(target.hits[0], WEAPON_CONFIGS['PISTOL']['damage'] * .85)

    def test_level_two_cluster_adds_five_stronger_sub_blasts(self):
        combat, player = self.setup_combat('cluster_grenade', 2)
        target = Target()
        grenade = FragGrenade(combat.render, Vec3(0, 5, 0), Vec3(0, 1, 0), None)
        grenade.explode([target], player, Mock())
        self.assertEqual(len(target.hits), 6)  # Main blast + five sub-blasts.
        self.assertEqual(target.hits[1:], [120] * 5)


if __name__ == '__main__':
    unittest.main()
