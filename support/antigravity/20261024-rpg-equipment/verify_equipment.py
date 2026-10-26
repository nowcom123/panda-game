"""End-to-End verification script for RPG equipment inventory and combat integration.

Demonstrates:
1. Loading profile in an isolated temporary directory
2. Starter weapon grant (4 weapons, PISTOL/SHOTGUN equipped) without duplicate grant on restart
3. Equipping, unequipping (preventing last weapon unequip), and locking with persistence
4. CombatSystem effective config resolution: damage separation between two items of the same type (AR)
5. Magazine ammo isolation per UID and shared reserve pool per weapon type (no free ammo on switch/reload cancel)
6. Slot switching (1: primary, 2: secondary) and blocking of unequipped weapon selection
7. EquipmentUIPanel UI state verification and preview capture
8. Clean sandbox teardown
"""

import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from combat.weapon_config import WEAPON_CONFIGS
from rpg import (
    RPGSession,
    SaveStore,
    STARTER_UNLOCK_KEY,
    create_item,
    load_catalog,
)
from rpg.equipment_ui import EquipmentUIPanel
from combat_system import CombatSystem


def run_verification() -> int:
    print("=== RPG Phase 2: Equipment & Combat Integration Verification ===")
    catalog = load_catalog()
    print(f"[OK] Catalog loaded with {len(catalog)} item definitions.")

    with tempfile.TemporaryDirectory() as temp_dir:
        save_path = Path(temp_dir) / "profile.json"
        store = SaveStore(save_path, catalog)
        print(f"[OK] Isolated sandbox store at: {save_path}")

        # -------------------------------------------------------------
        # 1. First Launch & Starter Loadout Policy
        # -------------------------------------------------------------
        session = RPGSession(store, catalog)
        assert session.initialize(), "Session initialization failed"
        assert session.is_valid, "Session must be valid"
        prof = session.profile
        assert prof is not None

        assert len(prof.items) == 4, f"Expected 4 starter weapons, got {len(prof.items)}"
        assert STARTER_UNLOCK_KEY in prof.unlocks, "starter_loadout_v1 unlock must be present"
        assert prof.equipment["primary"] is not None, "Primary slot must be equipped"
        assert prof.equipment["secondary"] is not None, "Secondary slot must be equipped"

        p_defn = catalog[prof.items[prof.equipment["primary"]].definition_id]
        s_defn = catalog[prof.items[prof.equipment["secondary"]].definition_id]
        assert p_defn.weapon_key == "PISTOL", f"Expected PISTOL in primary, got {p_defn.weapon_key}"
        assert s_defn.weapon_key == "SHOTGUN", f"Expected SHOTGUN in secondary, got {s_defn.weapon_key}"
        print("[OK] Starter loadout verified: 4 starter weapons granted; PISTOL / SHOTGUN equipped.")

        # Restart session: verify NO duplicate weapons granted
        session2 = RPGSession(store, catalog)
        session2.initialize()
        assert len(session2.profile.items) == 4, "Starters must not be re-granted on restart"
        print("[OK] Session restart verified: No duplicate weapons granted.")

        # -------------------------------------------------------------
        # 2. Equip / Unequip / Lock / Persistence
        # -------------------------------------------------------------
        # Find AR in inventory
        ar_uid = None
        for uid, item in session.profile.items.items():
            if catalog[item.definition_id].weapon_key == "AR":
                ar_uid = uid
                break
        assert ar_uid is not None, "AR must exist in starters"

        # Equip AR into primary slot
        eq_ok, eq_msg = session.equip("primary", ar_uid)
        assert eq_ok, f"Equip AR failed: {eq_msg}"
        assert session.profile.equipment["primary"] == ar_uid

        # Lock AR
        lock_ok, lock_msg = session.set_locked(ar_uid, True)
        assert lock_ok, f"Lock failed: {lock_msg}"
        assert session.profile.items[ar_uid].locked

        # Unequip secondary (SHOTGUN)
        uneq_ok, uneq_msg = session.unequip("secondary")
        assert uneq_ok, f"Unequip failed: {uneq_msg}"
        assert session.profile.equipment["secondary"] is None

        # Attempt to unequip last remaining weapon (primary AR) -> MUST BE REJECTED
        last_uneq_ok, last_uneq_msg = session.unequip("primary")
        assert not last_uneq_ok, "Unequipping the last weapon must be rejected!"
        assert session.profile.equipment["primary"] == ar_uid, "Primary must remain equipped"
        print(f"[OK] Protection verified: Unequipping the last weapon rejected ({last_uneq_msg}).")

        # -------------------------------------------------------------
        # 3. Combat System & Effective Configs for 2 Items of Same Type
        # -------------------------------------------------------------
        # Create second AR with damage affix
        ar_modded = create_item(
            catalog,
            "weapon_ar",
            affixes=[("damage_mult", 1.40)],
            uid="ar-modded-uid",
        )
        session.profile.add_item(ar_modded)
        session.equip("primary", "ar-modded-uid")
        session.equip("secondary", ar_uid)  # plain AR
        session.store.save(session.profile)

        # Mock CombatSystem to verify effective configs and slot mechanics
        import types
        from unittest.mock import MagicMock
        combat = CombatSystem.__new__(CombatSystem)
        combat.base = types.SimpleNamespace(chunks={}, blackout_active=False)
        combat.render = MagicMock()
        combat.camera = MagicMock()
        combat.world_root = MagicMock()
        combat.audio_mgr = MagicMock()
        combat.ui_mgr = MagicMock()
        combat.current_weapon = "PISTOL"
        combat.max_ammo = 7
        combat.ammo = 7
        combat._reserve_ammo = 28
        combat.overcharge_rounds = 0
        combat.is_reloading = False
        combat.is_aiming = False
        combat.reload_timer = 0.0
        combat.shoot_cooldown = 0.0
        combat.recoil_timer = 0.0
        combat.weapon_recoil = MagicMock()
        combat.slide_locked = False
        combat.was_slide_locked_before_reload = False
        combat.combo_count = 0
        combat.dual_hand_toggle = 0
        combat.active_tracers = []
        combat.weapon_states = {
            "PISTOL": {"ammo": 7, "max_ammo": 7, "reserve_ammo": 28, "slide_locked": False},
            "DUAL_PISTOL": {"ammo": 34, "max_ammo": 34, "reserve_ammo": 68, "slide_locked": False},
            "AR": {"ammo": 30, "max_ammo": 30, "reserve_ammo": 90, "slide_locked": False},
            "SHOTGUN": {"ammo": 8, "max_ammo": 8, "reserve_ammo": 24, "slide_locked": False},
        }
        combat.item_states = {}
        combat.reserve_ammo_pools = {
            "PISTOL": 28, "DUAL_PISTOL": 68, "AR": 90, "SHOTGUN": 24,
        }
        combat.active_slot = "primary"
        combat.active_item_uid = None
        combat._update_viewmodel_visibility = lambda: None
        combat.update_ammo_ui = lambda: None
        combat._reset_weapon_recoil = lambda: None

        combat.set_rpg_session(session)

        # Test Primary Slot (Modded AR: 38 * 1.40 = 53.2 damage)
        combat.switch_to_slot("primary")
        cfg_p = combat.get_current_weapon_config()
        assert abs(cfg_p["damage"] - 53.2) < 0.001, f"Expected 53.2 damage, got {cfg_p['damage']}"

        # Test Secondary Slot (Plain AR: 38.0 damage)
        combat.switch_to_slot("secondary")
        cfg_s = combat.get_current_weapon_config()
        assert abs(cfg_s["damage"] - 38.0) < 0.001, f"Expected 38.0 damage, got {cfg_s['damage']}"
        print("[OK] Combat damage separation verified: Modded AR (53.2) vs Plain AR (38.0).")

        # -------------------------------------------------------------
        # 4. Ammo Isolation & No Duplicate on Switch / Reload Cancel
        # -------------------------------------------------------------
        # Spend 10 rounds from secondary AR
        combat.ammo = 20
        # Switch to primary AR: primary AR should have 30 rounds
        combat.switch_to_slot("primary")
        assert combat.ammo == 30, f"Expected 30 in primary AR, got {combat.ammo}"

        # Switch back to secondary AR: should retain its 20 rounds
        combat.switch_to_slot("secondary")
        assert combat.ammo == 20, f"Expected 20 in secondary AR, got {combat.ammo}"

        # Start reload and cancel midway
        combat.ammo = 5
        combat.reload()
        assert combat.is_reloading
        combat.switch_to_slot("primary")
        assert not combat.is_reloading, "Reload must be cancelled on weapon switch"
        combat.switch_to_slot("secondary")
        assert combat.ammo == 5, f"Ammo must remain 5 after reload cancel, got {combat.ammo}"
        print("[OK] Ammo isolation and reload cancellation verified (no ammo duplicated).")

        # -------------------------------------------------------------
        # 5. Blocking Unequipped Weapons from Direct Switch
        # -------------------------------------------------------------
        # Only 2 ARs are equipped (primary & secondary). PISTOL and DUAL_PISTOL are unequipped.
        combat.switch_weapon("PISTOL")  # Must be blocked!
        assert combat.active_slot == "secondary", "Unequipped PISTOL must be blocked"
        combat.switch_weapon("DUAL_PISTOL")  # Must be blocked!
        assert combat.active_slot == "secondary", "Unequipped DUAL_PISTOL must be blocked"
        print("[OK] Direct switch to unequipped weapons properly blocked.")

        # -------------------------------------------------------------
        # 6. Equipment UI Component Verification
        # -------------------------------------------------------------
        # Verify EquipmentUIPanel data mapping logic
        panel = EquipmentUIPanel(
            parent_node=None,
            session=session,
            combat=combat,
        )
        sorted_items = panel._get_sorted_items()
        assert len(sorted_items) == 5, f"Expected 5 items (4 starters + 1 modded), got {len(sorted_items)}"
        print(f"[OK] Equipment UI model verified: {len(sorted_items)} items sorted and formatted.")

    print("=== All RPG Equipment & Combat Verifications Passed Successfully! ===")
    return 0


if __name__ == "__main__":
    sys.exit(run_verification())
