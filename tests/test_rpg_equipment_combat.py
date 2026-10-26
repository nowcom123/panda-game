"""Tests for CombatSystem integration with RPG equipment and affixes."""

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from panda3d.core import LPoint3, Vec3

from combat.weapon_config import WEAPON_CONFIGS
from rpg import (
    RPGSession,
    SaveStore,
    create_item,
    load_catalog,
)
from combat_system import CombatSystem


class MockMonster:
    """Mock monster for raycast hit and damage testing."""
    def __init__(self, hp=1000.0, name="테스트더미"):
        self.hp = hp
        self.max_hp = hp
        self.name = name
        self.pos = Vec3(0.0, 5.0, 0.0)
        self.is_boss = False
        self.is_elite = False
        self.is_corpse = False
        self.last_hit_was_head = False
        self.last_action_dodged = False
        self.last_damage_taken = 0.0

    def is_hit_by_ray(self, origin, direction):
        return True, 5.0

    def take_damage(self, dmg, apply_knockback=False, hit_dir=None, **kwargs):
        self.last_damage_taken = dmg
        self.hp = max(0.0, self.hp - dmg)
        return self.hp <= 0.0


class MockPlayer:
    """Mock player with perk and stat hooks."""
    def __init__(self, attack_power=35.0):
        self.attack_power = attack_power
        self.is_sliding = False
        self.is_moving = False
        self.is_sprinting = False
        self.perks = set()
        self.stamina = 100.0

    def get_attack_power(self, blackout_active=False):
        return self.attack_power

    def has_perk(self, perk_id):
        return perk_id in self.perks

    def recover_stamina(self, amount):
        self.stamina = min(100.0, self.stamina + amount)

    def add_weapon_recoil(self, *args, **kwargs):
        pass


class TestRPGSCombatIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def _create_mock_combat(self, session: RPGSession) -> CombatSystem:
        combat = CombatSystem.__new__(CombatSystem)
        combat.base = types.SimpleNamespace(chunks={}, blackout_active=False)
        combat.render = MagicMock()
        combat.camera = MagicMock()
        combat.camera.getPos.return_value = LPoint3(0.0, 0.0, 0.0)
        combat.camera.getQuat.return_value.getForward.return_value = Vec3(0.0, 1.0, 0.0)
        combat.camera.getQuat.return_value.getRight.return_value = Vec3(1.0, 0.0, 0.0)
        combat.camera.getQuat.return_value.getUp.return_value = Vec3(0.0, 0.0, 1.0)
        combat.world_root = MagicMock()
        combat.vm_root = MagicMock()
        combat.audio_mgr = MagicMock()
        combat.ui_mgr = MagicMock()

        # Initialize core variables
        combat.current_weapon = "PISTOL"
        combat.max_ammo = 7
        combat.ammo = 7
        combat._reserve_ammo = 28
        combat.overcharge_rounds = 0
        combat.is_reloading = False
        combat.reload_timer = 0.0
        combat.shoot_cooldown = 0.0
        combat.recoil_timer = 0.0
        combat.weapon_recoil = MagicMock()
        combat.slide_locked = False
        combat.slide_timer = 0.0
        combat.slide_blowback_duration = 0.08
        combat.dual_hand_toggle = 0
        combat.combo_count = 0
        combat.stage_shots_fired = 0
        combat.stage_shots_hit = 0
        combat.ads_alpha = 0.0
        combat.is_aiming = False
        combat.bobbing_time = 0.0
        combat.active_tracers = []
        combat.hit_particles = []
        combat.ammo_drops = []
        combat.smoke_particles = []
        combat.hipfire_bloom = 0.0
        combat.muzzle_timer = 0.0
        combat.combo_timer = 0.0
        combat.muzzle_light = MagicMock()
        combat.muzzle_light_np = MagicMock()
        combat.ar_muzzle_light = MagicMock()
        combat.ar_muzzle_light_np = MagicMock()
        combat.sg_muzzle_light = MagicMock()
        combat.sg_muzzle_light_np = MagicMock()
        combat.dual_left_flash_light = MagicMock()
        combat.dual_left_flash_light_np = MagicMock()
        combat.dual_right_flash_light = MagicMock()
        combat.dual_right_flash_light_np = MagicMock()
        combat.recoil_node = MagicMock()
        combat.ar_recoil_node = MagicMock()
        combat.sg_recoil_node = MagicMock()
        combat.setup_ammo_drops = lambda *a, **k: None
        combat.sg_pump_timer = 0.0
        combat.sg_pump_cycled = False

        combat.weapon_states = {
            "PISTOL": {"ammo": 7, "max_ammo": 7, "reserve_ammo": 28, "slide_locked": False},
            "DUAL_PISTOL": {"ammo": 34, "max_ammo": 34, "reserve_ammo": 68, "slide_locked": False},
            "AR": {"ammo": 30, "max_ammo": 30, "reserve_ammo": 90, "slide_locked": False},
            "SHOTGUN": {"ammo": 8, "max_ammo": 8, "reserve_ammo": 24, "slide_locked": False},
        }
        combat.item_states = {}
        combat.reserve_ammo_pools = {
            "PISTOL": 28,
            "DUAL_PISTOL": 68,
            "AR": 90,
            "SHOTGUN": 24,
        }
        combat.active_slot = "primary"
        combat.active_item_uid = None

        combat._spawn_tracer_effect = lambda *a, **k: None
        combat.spawn_hit_particles = lambda *a, **k: None
        combat._spawn_barrel_smoke = lambda *a, **k: None
        combat._show_muzzle_flash = lambda *a, **k: None
        combat._eject_casing = lambda *a, **k: None
        combat.casing_effects = MagicMock()
        combat.hit_particle_pool = []
        combat.smoke_pool = []
        combat.casing_pool = []
        combat.casing_sg_pool = []
        combat.tracer_pool = []
        combat.pellet_rays = []
        combat.enemies = []
        combat.record_combat_hit = lambda *a, **k: None
        combat.register_kill = lambda *a, **k: None
        combat.update_ammo_ui = lambda *a, **k: None
        combat._reset_weapon_recoil = lambda *a, **k: None
        combat._update_viewmodel_visibility = lambda *a, **k: None

        combat.set_rpg_session(session)
        return combat

    def test_same_weapon_type_different_uids_separate_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            # Create 2 AR items with different damage affixes
            ar_heavy = create_item(
                self.catalog,
                "weapon_ar",
                affixes=[("damage_mult", 1.50)],
                uid="ar-heavy-uid",
            )
            ar_plain = create_item(
                self.catalog,
                "weapon_ar",
                uid="ar-plain-uid",
            )
            session.profile.add_item(ar_heavy)
            session.profile.add_item(ar_plain)

            session.equip("primary", "ar-heavy-uid")
            session.equip("secondary", "ar-plain-uid")
            session.store.save(session.profile)

            combat = self._create_mock_combat(session)
            monster = MockMonster(hp=5000.0)
            player = MockPlayer(attack_power=35.0)

            # 1. Primary slot: ar-heavy
            combat.switch_to_slot("primary")
            combat.shoot_cooldown = 0.0  # reset cooldown after switch
            self.assertEqual(combat.active_item_uid, "ar-heavy-uid")
            cfg1 = combat.get_current_weapon_config()
            self.assertAlmostEqual(cfg1["damage"], WEAPON_CONFIGS["AR"]["damage"] * 1.50)

            with patch("combat_system.raycast_walls", return_value=(65.0, None)):
                combat.shoot([monster], player=player)
            heavy_damage = monster.last_damage_taken
            self.assertAlmostEqual(heavy_damage, WEAPON_CONFIGS["AR"]["damage"] * 1.50)

            # 2. Secondary slot: ar-plain
            combat.switch_to_slot("secondary")
            combat.shoot_cooldown = 0.0
            self.assertEqual(combat.active_item_uid, "ar-plain-uid")
            cfg2 = combat.get_current_weapon_config()
            self.assertAlmostEqual(cfg2["damage"], WEAPON_CONFIGS["AR"]["damage"])

            with patch("combat_system.raycast_walls", return_value=(65.0, None)):
                combat.shoot([monster], player=player)
            plain_damage = monster.last_damage_taken
            self.assertAlmostEqual(plain_damage, WEAPON_CONFIGS["AR"]["damage"])

            # Verify damages are completely separated
            self.assertAlmostEqual(heavy_damage, plain_damage * 1.50)

    def test_weakpoint_and_reload_time_in_combat_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            custom_pistol = create_item(
                self.catalog,
                "weapon_pistol",
                affixes=[
                    ("weakpoint_mult", 1.40),
                    ("reload_time_mult", 0.80),
                ],
                uid="custom-pistol-uid",
            )
            session.profile.add_item(custom_pistol)
            session.equip("primary", "custom-pistol-uid")
            session.store.save(session.profile)

            combat = self._create_mock_combat(session)
            combat.switch_to_slot("primary")

            # 1. Reload duration check
            expected_reload_time = WEAPON_CONFIGS["PISTOL"]["reload_time"] * 0.80
            self.assertAlmostEqual(combat.reload_duration, expected_reload_time)

            # Trigger reload
            combat.ammo = 0
            combat.reload()
            self.assertTrue(combat.is_reloading)
            self.assertAlmostEqual(combat.reload_timer, expected_reload_time)

            # 2. Headshot / Weakpoint hit damage check
            monster = MockMonster(hp=5000.0)
            monster.last_hit_was_head = True
            player = MockPlayer(attack_power=35.0)

            combat.is_reloading = False
            combat.ammo = 7
            combat.shoot_cooldown = 0.0

            base_dmg = WEAPON_CONFIGS["PISTOL"]["damage"]
            expected_headshot_mult = WEAPON_CONFIGS["PISTOL"]["headshot_mult"] * 1.40
            expected_damage = base_dmg * expected_headshot_mult

            with patch("combat_system.raycast_walls", return_value=(65.0, None)):
                combat.shoot([monster], player=player)
            self.assertAlmostEqual(monster.last_damage_taken, expected_damage)

    def test_perks_and_affixes_multiply_cleanly_no_accumulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            fast_ar = create_item(
                self.catalog,
                "weapon_ar",
                affixes=[("reload_time_mult", 0.85)],
                uid="fast-ar-uid",
            )
            session.profile.add_item(fast_ar)
            session.equip("primary", "fast-ar-uid")
            session.store.save(session.profile)

            combat = self._create_mock_combat(session)
            combat.switch_to_slot("primary")

            player = MockPlayer()
            player.perks.add("speed_demon")
            combat.base.player = player

            # speed_demon grants reload_mult = 0.65
            expected_time = WEAPON_CONFIGS["AR"]["reload_time"] * 0.85 * 0.65
            self.assertAlmostEqual(combat.reload_duration, expected_time)

            # Switch back and forth multiple times
            combat.next_weapon()
            combat.next_weapon()
            combat.reset_state(keep_ammo=True)

            # Value must NOT accumulate or drift
            self.assertAlmostEqual(combat.reload_duration, expected_time)

    def test_ammo_not_duplicated_on_switch_unequip_or_reload_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            combat = self._create_mock_combat(session)
            p_uid = session.profile.equipment["primary"]
            s_uid = session.profile.equipment["secondary"]

            combat.switch_to_slot("primary")
            # Spend ammo down to 3
            combat.ammo = 3
            combat.weapon_states[combat.current_weapon]["ammo"] = 3
            combat.item_states[p_uid] = {"ammo": 3, "slide_locked": False}

            # Switch to secondary
            combat.switch_to_slot("secondary")
            self.assertEqual(combat.active_item_uid, s_uid)

            # Switch back to primary: must still be 3
            combat.switch_to_slot("primary")
            self.assertEqual(combat.active_item_uid, p_uid)
            self.assertEqual(combat.ammo, 3)

            # Start reload and cancel midway by switching slots
            combat.reload()
            self.assertTrue(combat.is_reloading)
            combat.switch_to_slot("secondary")
            self.assertFalse(combat.is_reloading)

            # Switch back to primary: ammo must remain 3 (no free ammo on reload cancel)
            combat.switch_to_slot("primary")
            self.assertEqual(combat.ammo, 3)

            # Unequip primary in session and re-equip: should NOT grant free full magazine
            session.unequip("primary")
            session.equip("primary", p_uid)
            combat.sync_with_rpg_session()
            self.assertEqual(combat.ammo, 3)

            # Stage transition with keep_ammo=True: preserves 3
            combat.reset_state(current_stage=2, keep_ammo=True)
            self.assertEqual(combat.ammo, 3)

            # Fresh run with keep_ammo=False: resets to full max_ammo
            combat.reset_state(current_stage=1, keep_ammo=False)
            self.assertEqual(combat.ammo, combat.max_ammo)

    def test_shared_reserve_ammo_pool_for_same_weapon_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            ar1 = create_item(self.catalog, "weapon_ar", uid="ar1")
            ar2 = create_item(self.catalog, "weapon_ar", uid="ar2")
            session.profile.add_item(ar1)
            session.profile.add_item(ar2)
            session.equip("primary", "ar1")
            session.equip("secondary", "ar2")
            session.store.save(session.profile)

            combat = self._create_mock_combat(session)
            combat.switch_to_slot("primary")

            initial_reserve = combat._reserve_ammo  # 90
            combat.ammo = 0
            combat.reload()
            # Fast forward reload completion
            combat.reload_timer = 0.0
            combat.update(dt=0.1)

            # Primary AR consumed 30 reserve rounds (now 60)
            self.assertEqual(combat.ammo, 30)
            self.assertEqual(combat._reserve_ammo, initial_reserve - 30)

            # Switch to secondary AR: must share the same reserve pool (60, not 90!)
            combat.switch_to_slot("secondary")
            self.assertEqual(combat._reserve_ammo, initial_reserve - 30)

    def test_two_slots_only_and_unassigned_weapon_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "profile.json"
            store = SaveStore(save_path, self.catalog)
            session = RPGSession(store, self.catalog)
            session.initialize()

            # Profile starts with PISTOL (primary) and SHOTGUN (secondary).
            # DUAL_PISTOL and AR are in inventory but not equipped.
            combat = self._create_mock_combat(session)
            combat.switch_to_slot("primary")
            self.assertEqual(combat.current_weapon, "PISTOL")

            # Q/next_weapon cycles to secondary (SHOTGUN)
            combat.next_weapon()
            self.assertEqual(combat.current_weapon, "SHOTGUN")
            self.assertEqual(combat.active_slot, "secondary")

            # Q again cycles back to primary (PISTOL)
            combat.next_weapon()
            self.assertEqual(combat.current_weapon, "PISTOL")
            self.assertEqual(combat.active_slot, "primary")

            # Attempting direct switch to unequipped weapon (AR or DUAL_PISTOL) must be BLOCKED
            combat.switch_weapon("AR")
            self.assertEqual(combat.current_weapon, "PISTOL")

            combat.switch_weapon("DUAL_PISTOL")
            self.assertEqual(combat.current_weapon, "PISTOL")

            # Direct switch to equipped weapon (SHOTGUN) switches to secondary slot
            combat.switch_weapon("SHOTGUN")
            self.assertEqual(combat.current_weapon, "SHOTGUN")
            self.assertEqual(combat.active_slot, "secondary")


if __name__ == "__main__":
    unittest.main()
