"""Gameplay regressions using real Panda3D nodes, without a window or audio device."""

import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from panda3d.core import AmbientLight, Fog, NodePath, Vec3

from audio_system import AudioManager
from combat_system import CombatSystem, CrossbowBolt
from collision import first_world_hit, ray_spheres_hit
from constants import CURSED_RELICS, WALL_HEIGHT
from game import LiminalInfiniteLoop
from inventory_system import InventorySystem, ThrowingFirePot
from monster import ShadowStalker, TallSkeletonMonster
from player_controller import PlayerController


class GameplayRegressions(unittest.TestCase):
    def setUp(self):
        self.root = NodePath("test_world")
        self.camera = self.root.attachNewNode("camera")
        self.camera.setZ(1.7)
        self.ui = Mock()
        self.audio = Mock()
        self.game = SimpleNamespace(
            render=self.root, camera=self.camera, ui_mgr=self.ui,
            audio_mgr=self.audio, win=None, game_state="PLAYING",
            current_stage=1, time_limit=300.0, time_left=250.0,
            blackout_active=False, blackout_timer=0.0,
            blackout_triggered_this_stage=False, monsters=[], corpses=[],
            chunks={}, active_chunk_futures={}, fireballs=[], shockwaves=[],
            liminal_fog=Fog("test_fog"),
            amb_np=self.root.attachNewNode(AmbientLight("test_ambient")),
            setBackgroundColor=Mock(), spawn_monsters=Mock(),
            setup_escape_portal=Mock(),
        )
        for name in (
            "on_use_item", "trigger_abyssal_inversion", "end_abyssal_inversion",
            "_update_monsters", "restart_game", "advance_to_next_stage",
            "clear_projectiles", "melee_bash", "_discard_pending_chunks",
        ):
            setattr(self.game, name, MethodType(getattr(LiminalInfiniteLoop, name), self.game))
        self.player = PlayerController(
            self.game, None, self.camera, None, self.audio, self.ui
        )
        self.combat = CombatSystem(
            self.game, self.root, self.camera, self.root, self.audio, self.ui
        )
        self.inventory = InventorySystem(
            self.game, self.root, self.camera, self.root, self.audio, self.ui
        )
        self.game.player = self.player
        self.game.combat = self.combat
        self.game.inventory = self.inventory

    def tearDown(self):
        self.root.removeNode()

    def test_bolt_applies_stalker_weakness_once(self):
        for exposed, expected_hp in ((False, 110.5), (True, 47.5)):
            with self.subTest(exposed=exposed):
                stalker = ShadowStalker(self.root, 0, 5)
                if exposed:
                    stalker.stun(1.35)
                bolt = CrossbowBolt(
                    self.root, Vec3(0, 0, 1.25), Vec3(0, 1, 0), player=self.player
                )
                bolt.update(0.1, None, [stalker], self.combat)
                self.assertTrue(bolt.is_dead, "The bolt must actually hit the target")
                self.assertAlmostEqual(stalker.hp, expected_hp)
                stalker.destroy()

    def test_stalker_loot_is_complete_and_only_collected_once(self):
        self.player.relics = [r for r in CURSED_RELICS if r != "glass_cannon"]
        stalker = ShadowStalker(self.root, 0, 5)
        stalker.take_damage(1000)
        stalker.turn_into_corpse()
        self.game.monsters = [stalker]
        self.game._update_monsters(0.016, 0, 0)
        self.assertEqual(self.game.monsters, [])
        self.assertEqual(self.combat.reserve_ammo, 15)

        self.game._update_monsters(0.016, 0, 5)
        self.assertEqual(self.combat.reserve_ammo, 20)
        self.assertEqual(set(self.player.relics), set(CURSED_RELICS))
        self.assertTrue(stalker.relic_drop_np.isEmpty())
        # A duplicate corpse transition must not replenish already collected loot.
        stalker.turn_into_corpse()
        self.game._update_monsters(0.016, 0, 5)
        self.assertEqual(self.combat.reserve_ammo, 20)
        self.assertEqual(len(self.player.relics), len(CURSED_RELICS))

    def test_stalker_loot_with_all_relics_owned(self):
        self.player.relics = list(CURSED_RELICS)
        stalker = ShadowStalker(self.root, 0, 0)
        stalker.take_damage(1000)
        stalker.turn_into_corpse()
        self.game.corpses = [stalker]
        self.game._update_monsters(0.016, 0, 0)
        self.assertEqual(self.combat.reserve_ammo, 20)
        self.assertEqual(len(self.player.relics), len(CURSED_RELICS))
        self.assertFalse(stalker.recoverable_relic)

    def test_rewards_are_immediate_and_once_for_each_attack_source(self):
        self.player.acquire_relic("blood_thirst")
        cases = [(attack, blackout) for attack in
                 ("bolt", "melee", "explosion", "censer", "ground_fire")
                 for blackout in (False, True)]
        for attack, blackout in cases:
            with self.subTest(attack=attack, blackout=blackout):
                self.player.hp = 30.0
                self.player.exp = 0
                self.game.blackout_active = blackout
                self.inventory.reset_state(keep_items=False)
                self.combat.reset_state()
                monster = TallSkeletonMonster(self.root, 0, 1)
                monster.hp = 1
                self.game.monsters = [monster]
                if attack == "bolt":
                    bolt = CrossbowBolt(
                        self.root, Vec3(0, 0, 1.25), Vec3(0, 1, 0), player=self.player
                    )
                    bolt.update(0.1, None, [monster], self.combat)
                elif attack == "melee":
                    self.combat.melee_bash([monster], self.player)
                elif attack == "explosion":
                    pot = ThrowingFirePot(
                        self.root, Vec3(0, 1, 0.5), Vec3(0, 1, 0), player=self.player
                    )
                    pot.explode(self.inventory, [monster])
                else:
                    if attack == "censer":
                        self.inventory.use_censer(self.player)
                    else:
                        self.inventory.create_ground_fire(Vec3(0, 1, 0))
                    self.inventory.update(0.016, self.player, [monster], {})
                self.assertEqual(monster.hp, 0, "The attack must kill the target")
                expected_exp = monster.exp_value * (2 if blackout else 1)
                self.assertEqual(self.player.hp, 42.0)
                self.assertEqual(self.player.exp, expected_exp)
                # Even a late overlapping hit or a blackout ending cannot change rewards.
                self.game.blackout_active = not blackout
                self.assertFalse(self.combat.apply_damage(monster, 100, self.player))
                self.game._update_monsters(0.016, 100, 100)
                self.assertEqual(self.player.hp, 42.0)
                self.game._update_monsters(0.016, 100, 100)
                self.assertEqual(self.player.hp, 42.0)
                self.assertEqual(self.player.exp, expected_exp)

    def test_rejected_melee_does_not_spend_stamina_or_deal_damage(self):
        monster = TallSkeletonMonster(self.root, 0, 1)
        self.game.monsters = [monster]
        cases = (
            ("SHOP", False, 0.0, 100.0, False),
            ("PLAYING", True, 0.0, 100.0, False),
            ("PLAYING", False, 0.2, 100.0, False),
            ("PLAYING", False, 0.0, 17.0, False),
            ("PLAYING", False, 0.0, 25.0, True),
        )
        for state, reloading, timer, stamina, exhausted in cases:
            with self.subTest(state=state, reloading=reloading, timer=timer,
                              stamina=stamina, exhausted=exhausted):
                self.game.game_state = state
                self.combat.is_reloading = reloading
                self.combat.melee_timer = timer
                self.player.stamina = stamina
                self.player.stamina_exhausted = exhausted
                self.assertFalse(self.game.melee_bash())
                self.assertEqual(self.player.stamina, stamina)
                self.assertEqual(self.combat.melee_timer, timer)
                self.assertEqual(monster.hp, monster.max_hp)

    def test_melee_spends_stamina_once_for_multiple_targets_or_a_miss(self):
        self.game.monsters = [TallSkeletonMonster(self.root, x, 1) for x in (-0.2, 0.2)]
        self.assertTrue(self.game.melee_bash())
        self.assertEqual(self.player.stamina, 82)
        for monster in self.game.monsters:
            self.assertLess(monster.hp, monster.max_hp)
        self.assertFalse(self.game.melee_bash())
        self.assertEqual(self.player.stamina, 82)
        self.game.monsters = []
        self.combat.melee_timer = 0
        self.player.stamina = 18
        self.assertTrue(self.game.melee_bash())
        self.assertEqual(self.player.stamina, 0)
        self.assertTrue(self.player.stamina_exhausted)

    def test_nonlethal_hit_has_no_reward_and_lethal_hit_levels_up_once(self):
        monster = TallSkeletonMonster(self.root, 0, 1)
        self.player.acquire_relic("blood_thirst")
        self.player.hp = 70
        self.player.exp = 90
        self.assertFalse(self.combat.apply_damage(monster, 1, self.player))
        self.assertEqual(self.player.hp, 70)
        self.assertEqual(self.player.exp, 90)
        self.assertTrue(self.combat.apply_damage(monster, 100, self.player))
        self.assertEqual(self.player.hp, 75)
        self.assertEqual(self.player.level, 2)
        self.assertEqual(self.player.stat_points, 3)
        self.assertEqual(self.player.exp, 20)
        self.assertFalse(self.combat.apply_damage(monster, 100, self.player))
        self.assertEqual(self.player.stat_points, 3)

    def test_bolt_hits_first_surface_without_tunneling_through_thin_wall(self):
        wall = (8.0, 12.0, 10.0, 12.2)
        chunks = {(0, 0): SimpleNamespace(cell_colliders={(1, 1): [wall], (1, 2): [wall]})}
        # The third target's surface is in front of the wall, despite its center being behind it.
        for monster_y, blocked in ((14.0, True), (11.0, False), (12.5, False), (None, True)):
            with self.subTest(monster_y=monster_y):
                monster = ShadowStalker(self.root, 9, monster_y) if monster_y is not None else None
                bolt = CrossbowBolt(self.root, Vec3(9, 9, 1.25), Vec3(0, 1, 0), player=self.player)
                bolt.update(0.1, chunks, [monster] if monster else [], self.combat)
                if blocked:
                    self.assertTrue(bolt.is_embedded)
                    self.assertAlmostEqual(bolt.pos.y, 12.0)
                    if monster:
                        self.assertEqual(monster.hp, monster.max_hp)
                    self.camera.setPos(9, 12, 1.7)
                    ammo = self.combat.reserve_ammo
                    bolt.update(0.016, chunks, [], self.combat)
                    bolt.update(0.016, chunks, [], self.combat)
                    self.assertEqual(self.combat.reserve_ammo, ammo + 1)
                else:
                    self.assertTrue(bolt.is_dead)
                    self.assertLess(monster.hp, monster.max_hp)
                if monster:
                    monster.destroy()

    def test_bolt_does_not_hit_beyond_this_frames_travel(self):
        monster = ShadowStalker(self.root, 9, 11.0)
        bolt = CrossbowBolt(self.root, Vec3(9, 9, 1.25), Vec3(0, 1, 0), player=self.player)
        bolt.update(0.01, None, [monster], self.combat)
        self.assertEqual(monster.hp, monster.max_hp)
        self.assertFalse(bolt.is_dead)
        bolt.update(0.01, None, [monster], self.combat)
        self.assertTrue(bolt.is_dead)

    def test_bolt_floor_and_ceiling_stop_it_before_a_monster(self):
        for z, velocity_z, expected_z in ((0.3, -20, 0.06), (12.5, 20, WALL_HEIGHT - 0.25)):
            with self.subTest(z=z):
                monster = ShadowStalker(self.root, 9, 14)
                monster.pos.z = 13.3 if velocity_z > 0 else -3
                bolt = CrossbowBolt(self.root, Vec3(9, 9, z), Vec3(0, 1, 0), player=self.player)
                bolt.vel.z = velocity_z
                bolt.update(0.1, None, [monster], self.combat)
                self.assertTrue(bolt.is_embedded)
                self.assertAlmostEqual(bolt.pos.z, expected_z, places=5)
                self.assertEqual(monster.hp, monster.max_hp)

    def test_nearest_monster_is_hit_regardless_of_list_order(self):
        far = ShadowStalker(self.root, 9, 14)
        near = ShadowStalker(self.root, 9, 12)
        bolt = CrossbowBolt(self.root, Vec3(9, 9, 1.25), Vec3(0, 1, 0), player=self.player)
        bolt.update(0.1, None, [far, near], self.combat)
        self.assertEqual(far.hp, far.max_hp)
        self.assertLess(near.hp, near.max_hp)

    def test_censer_clears_blackout_and_blocks_new_triggers_while_burning(self):
        stalker = ShadowStalker(self.root, 0, 10)
        self.game.monsters = [stalker]
        self.game.trigger_abyssal_inversion()
        self.assertTrue(stalker.hunt_mode)
        self.assertTrue(self.combat.is_blackout)

        self.game.on_use_item(2)
        self.assertEqual(self.inventory.items["censer"], 0)
        self.assertFalse(self.game.blackout_active)
        self.assertEqual(self.game.blackout_timer, 0)
        self.assertFalse(self.combat.is_blackout)
        self.assertFalse(stalker.hunt_mode)
        for reason in ("altar", "stage"):
            self.game.trigger_abyssal_inversion(reason=reason)
            self.assertFalse(self.game.blackout_active)

        self.inventory.update(12.0, self.player, [], {})
        self.game.trigger_abyssal_inversion()
        self.assertTrue(self.game.blackout_active)
        self.assertTrue(stalker.hunt_mode)
        # Trying an empty quickslot must not purify an active blackout.
        self.game.on_use_item(2)
        self.assertTrue(self.game.blackout_active)

    def test_blackout_cleanup_is_idempotent(self):
        self.game.trigger_abyssal_inversion()
        self.game.end_abyssal_inversion()
        self.game.end_abyssal_inversion()
        self.audio.play_eclipse_purify.assert_called_once()
        self.assertFalse(self.game.blackout_active)
        self.assertEqual(self.game.blackout_timer, 0)

    def test_new_game_resets_growth_but_next_stage_preserves_it(self):
        self.player.gain_exp(100)
        self.player.allocate_stat("SPD", self.combat)
        self.player.allocate_stat("AMMO", self.combat)
        self.player.acquire_relic("iron_colossus")
        self.player.hp_drain_accum = 0.2
        self.player.key_map["e"] = 1
        self.player.last_move_dir = Vec3(1, 0, 0)
        self.inventory.items["flask"] = 3
        self.inventory.censer_burn_tick = 0.4
        reload_duration = self.combat.reload_duration
        self.game.advance_to_next_stage()
        self.assertEqual(self.game.current_stage, 2)
        self.assertEqual(self.player.stat_points, 1)
        self.assertEqual(self.player.max_stamina, 115)
        self.assertEqual(self.player.max_hp, 160)
        self.assertEqual(self.player.relics, ["iron_colossus"])
        self.assertEqual(self.inventory.items["flask"], 3)
        self.assertEqual(self.combat.reload_duration, reload_duration)
        self.assertEqual(self.combat.reserve_ammo, 43)
        self.assertEqual(self.inventory.censer_burn_tick, 0)
        self.assertFalse(any(self.player.key_map.values()))

        self.game.restart_game()
        self.assertEqual(self.player.level, 1)
        self.assertEqual(self.player.exp, 0)
        self.assertEqual(self.player.stat_points, 0)
        self.assertEqual(self.player.hp, 100)
        self.assertEqual(self.player.max_hp, 100)
        self.assertEqual(self.player.max_stamina, 100)
        self.assertEqual(self.player.stamina, 100)
        self.assertEqual(self.player.speed_mult, 1)
        self.assertEqual(self.player.hp_drain_accum, 0)
        self.assertEqual(self.player.relics, [])
        self.assertEqual(self.player.last_move_dir.lengthSquared(), 0)
        self.assertEqual(self.combat.reload_duration, 1.25)
        self.assertEqual(self.combat.reserve_ammo, 15)
        self.assertEqual(self.inventory.items, {"flask": 1, "censer": 1, "fire_pot": 1})


class ProjectileIntersections(unittest.TestCase):
    def test_wall_intersections_in_both_directions_and_parallel_paths(self):
        wall = (8.0, 12.0, 10.0, 12.2)
        chunks = {(0, 0): SimpleNamespace(cell_colliders={(1, 1): [wall], (1, 2): [wall]})}
        self.assertAlmostEqual(first_world_hit(chunks, Vec3(9, 9, 1), Vec3(9, 15, 1)), 0.5)
        self.assertAlmostEqual(first_world_hit(chunks, Vec3(9, 15, 1), Vec3(9, 9, 1)), 2.8 / 6)
        self.assertIsNone(first_world_hit(chunks, Vec3(11, 9, 1), Vec3(11, 15, 1)))
        self.assertEqual(first_world_hit(chunks, Vec3(9, 12.1, 1), Vec3(9, 15, 1)), 0)
        self.assertEqual(first_world_hit({}, Vec3(9, 9, 1), Vec3(9, 15, 1)), 0)

    def test_ray_selects_nearest_sphere_surface_and_handles_start_inside(self):
        targets = [(0, 8, 0, 1), (0, 4, 0, 1)]
        hit, distance = ray_spheres_hit(Vec3(0), Vec3(0, 1, 0), targets, 10)
        self.assertTrue(hit)
        self.assertAlmostEqual(distance, 3)
        self.assertEqual(ray_spheres_hit(Vec3(0, 4, 0), Vec3(0, 1, 0), targets, 1), (True, 0))
        self.assertFalse(ray_spheres_hit(Vec3(0), Vec3(0, -1, 0), targets, 10)[0])
        self.assertFalse(ray_spheres_hit(Vec3(0), Vec3(0, 1, 0), targets, 2.9)[0])


class AudioPaths(unittest.TestCase):
    def test_root_consumables_and_assets_audio_resolve(self):
        manager = AudioManager.__new__(AudioManager)
        root = Path(__file__).resolve().parents[1]
        manager.audio_dir = str(root / "assets" / "audio")
        for name in ("flask_drink.wav", "censer_ignite.wav", "firepot_explode.wav", "item_pickup.wav"):
            with self.subTest(name=name):
                path = manager._get_path(name)
                self.assertIsNotNone(path)
                self.assertEqual(Path(path.toOsSpecific()).resolve(), root / name)
        self.assertIsNotNone(manager._get_path("crossbow_shoot.wav"))
        self.assertIsNone(manager._get_path("missing_test_sound.wav"))

    def test_assets_directory_has_priority_over_root(self):
        manager = AudioManager.__new__(AudioManager)
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "flask_drink.wav"
            override.touch()
            manager.audio_dir = directory
            self.assertEqual(Path(manager._get_path(override.name).toOsSpecific()).resolve(), override.resolve())


if __name__ == "__main__":
    unittest.main()
