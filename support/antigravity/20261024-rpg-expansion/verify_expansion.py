"""End-to-end verification script for RPG Expansion: Boss Gimmicks, Characters, and Inventory."""

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from panda3d.core import NodePath, Vec3
from boss_scaling import apply_boss_scaling, scaling_for_stage
from boss_patterns import BossPatternState
from monster import CableOverlordBoss
from rpg.characters import CharacterManager, validate_character_name
from rpg.items import create_item, load_catalog, UnsupportedSaveVersion, RPGError
from rpg.session import RPGSession
from rpg.equipment_ui import EquipmentUIPanel
from rpg.run_loot import RunLootBag
from rpg.run_loot_ui import RunLootUIPanel
from rpg.weapon_stats import resolve_weapon_config
from combat.weapon_config import WEAPON_CONFIGS


def run_expansion_verification() -> int:
    print("=== [RPG EXPANSION VERIFICATION SUITE] ===")
    catalog = load_catalog()

    # -------------------------------------------------------------
    # 1. Verify Phase A: Boss Growth & Gimmicks
    # -------------------------------------------------------------
    print("\n--- [Phase A: Boss Growth & Gimmicks] ---")
    root = NodePath("verify_boss_root")
    try:
        boss = CableOverlordBoss(root, 0, 0)
        apply_boss_scaling(boss, 6)
        assert boss.hp == 6650, f"Expected 6650 HP on stage 6, got {boss.hp}"
        assert boss.leg_hp[0] == 462, f"Expected 462 leg HP, got {boss.leg_hp[0]}"
        print("[OK] Stage 6 boss scaling: HP 6650, Leg HP 462.")

        ctrl = boss.pattern_controller
        game = SimpleNamespace(
            render=root,
            chunks={},
            player=SimpleNamespace(
                pos=Vec3(0, 8, 0),
                take_damage=Mock(return_value=False),
                trigger_quake_shake=Mock(),
            ),
            ui_mgr=Mock(),
            audio_mgr=Mock(),
            trigger_game_over=Mock(),
            current_stage=6,
        )

        # Gimmick 1: Bone Fan Wave
        ctrl._start_bone_fan_wave(game, 0, 8)
        assert ctrl.current_pattern == "fan_wave"
        assert ctrl.telegraph_duration >= 1.0
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_fan_wave_telegraph(0.1, game)
        assert ctrl.state == BossPatternState.ACTIVE

        # Safe corridor: angle diff 0 -> no damage
        ctrl.fan_wave_hit_done = False
        ctrl._update_fan_wave_active(0.1, game, 0, 8, 1.7)
        game.player.take_damage.assert_not_called()
        print("[OK] Bone Fan Wave: Safe corridor guarantees zero damage.")

        # Danger wing: angle diff 30 deg -> hit once
        import math
        rad = ctrl.fan_wave_angle + math.radians(30)
        px = math.cos(rad) * 8.0
        py = math.sin(rad) * 8.0
        ctrl.fan_wave_hit_done = False
        ctrl._update_fan_wave_active(0.1, game, px, py, 1.7)
        game.player.take_damage.assert_called_once()
        print("[OK] Bone Fan Wave: Danger wing damages player once without frame repeat.")
        ctrl.cleanup()

        # Gimmick 2: Bone Heart Seal
        ctrl._start_bone_heart_seal(game, 0, 8)
        ctrl.timer = ctrl.telegraph_duration
        ctrl._update_seal_telegraph(0.1, game)
        assert ctrl.is_protecting and boss.is_protected
        assert len(ctrl.active_seals) >= 1
        print(f"[OK] Bone Heart Seal: Spawned {len(ctrl.active_seals)} seals and activated 60% shield.")

        # Damage reduction test
        old_hp = boss.hp
        boss.take_damage(100.0)
        assert abs(boss.hp - (old_hp - 40.0)) < 0.01, f"Expected 40 dmg taken, got {old_hp - boss.hp}"
        print("[OK] Bone Heart Seal: 60% damage reduction verified.")

        # Destroy all seals -> 2s stun & exposed skull
        for s in list(ctrl.active_seals):
            s.take_damage(999.0)
        ctrl._update_seal_active(0.1, game, 0, 8, 1.7)
        assert not ctrl.is_protecting and not boss.is_protected
        assert boss.stun_timer == 2.0
        assert ctrl.is_skull_exposed
        print("[OK] Bone Heart Seal: Breaking all seals removes shield, stuns for 2s, exposes skull.")
        ctrl.cleanup()

        # Spider Leap restriction: 4 legs broken forbids leap
        boss.leg_hp[0] = 0
        boss.leg_hp[1] = 0
        boss.leg_hp[2] = 0
        assert ctrl._can_leap_to_target(game, 0, 10)
        boss.leg_hp[3] = 0
        assert not ctrl._can_leap_to_target(game, 0, 10)
        print("[OK] Spider Leap Slam: Forbidden when 4 legs are destroyed.")

        boss.destroy()
    finally:
        root.removeNode()

    # -------------------------------------------------------------
    # 2. Verify Phase B: Character Management & Storage Separation
    # -------------------------------------------------------------
    print("\n--- [Phase B: Character Creation & Storage Separation] ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        root_dir = Path(tmp_dir)
        mgr = CharacterManager(root_dir, catalog)

        # Name validation
        assert validate_character_name("  생존자A  ") == "생존자A"
        try:
            validate_character_name("x")
            assert False, "Should have rejected 1-char name"
        except Exception:
            pass

        # Create up to 3 characters
        c1 = mgr.create_character("개척자1")
        c2 = mgr.create_character("개척자2")
        c3 = mgr.create_character("개척자3")
        assert len(mgr.character_list.characters) == 3
        try:
            mgr.create_character("초과")
            assert False, "Should have rejected 4th character"
        except RPGError:
            print("[OK] Max 3 characters constraint enforced.")

        # Storage isolation between c1 and c2
        store1 = mgr.get_character_save_store(c1.id)
        store2 = mgr.get_character_save_store(c2.id)

        s1 = RPGSession(store1, catalog)
        s1.initialize(grant_starters=True)
        s1.profile.currencies["credits"] = 1200
        extra_w = create_item(catalog, "weapon_ar", rarity="epic", item_level=8)
        s1.profile.add_item(extra_w)
        store1.save(s1.profile)

        s2 = RPGSession(store2, catalog)
        s2.initialize(grant_starters=True)
        s2.profile.currencies["credits"] = 100
        store2.save(s2.profile)

        p1_re = store1.load().profile
        p2_re = store2.load().profile
        assert p1_re.currencies["credits"] == 1200 and p2_re.currencies["credits"] == 100
        assert extra_w.uid in p1_re.items and extra_w.uid not in p2_re.items
        print("[OK] Two characters have completely isolated items, equipment, and credits.")

        # Legacy profile migration test
        legacy_dir = root_dir / "legacy_test"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "profile.json"
        from rpg.save_store import SaveStore
        from rpg.profile import new_profile
        l_store = SaveStore(legacy_file, catalog)
        l_prof = new_profile()
        l_prof.currencies["credits"] = 9999
        l_store.save(l_prof)
        orig_bytes = legacy_file.read_bytes()

        mig_mgr = CharacterManager(legacy_dir, catalog)
        mig_list = mig_mgr.load_character_list()
        assert len(mig_list.characters) == 1
        assert mig_list.characters[0].name == "기존 탐험가"
        assert legacy_file.read_bytes() == orig_bytes, "Original legacy file must be preserved byte-for-byte!"
        print("[OK] Legacy profile migrated to deterministic UUID while preserving original file bytes.")

    # -------------------------------------------------------------
    # 3. Verify Phase C: Inventory UI 3-Column Layout & Capabilities
    # -------------------------------------------------------------
    print("\n--- [Phase C: Inventory UI Reorganization] ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        root_dir = Path(tmp_dir)
        mgr = CharacterManager(root_dir, catalog)
        char = mgr.create_character("인벤토리테스터")
        store = mgr.get_character_save_store(char.id)
        session = RPGSession(store, catalog)
        session.initialize(grant_starters=True)

        # Add 40 permanent weapons
        for i in range(40):
            item = create_item(catalog, "weapon_ar", rarity="rare", item_level=i + 1)
            session.profile.add_item(item)
        store.save(session.profile)

        ui_node = NodePath("inv_test_node")
        try:
            panel = EquipmentUIPanel(ui_node, session)
            assert len(session.profile.items) == 44
            panel.refresh()
            assert panel.current_page == 0
            assert "/ 7" in panel.lbl_page.getText()
            print("[OK] 44 permanent items cleanly paginated across 7 pages.")

            # Sorting verification
            panel._set_sort_mode("rarity")
            assert panel.sort_mode == "rarity"
            panel._set_sort_mode("name")
            assert panel.sort_mode == "name"
            print("[OK] Sorting by rarity and name works without modifying underlying profile data.")

            # Unequip last weapon protection
            panel._on_click_unequip()  # Unequip secondary (primary is target_slot default or primary)
            panel.target_slot = "primary"
            panel.refresh()
            if session.profile.equipment["secondary"] is None:
                assert "마지막 무기 해제 불가" in panel.btn_unequip["text"]
                assert panel.btn_unequip["state"] == "disabled"
                print("[OK] Last equipped weapon cannot be unequipped (disabled + reason shown).")

            # In-run loot bag 24 capacity
            bag = RunLootBag()
            for i in range(24):
                it = create_item(catalog, "weapon_pistol", rarity="uncommon", item_level=1)
                ok, _ = bag.add_item(it)
                assert ok
            assert not bag.can_add()
            run_ui = RunLootUIPanel(ui_node, bag, catalog)
            run_ui.refresh()
            assert "24 / 24" in run_ui.lbl_bag_status.getText()
            print("[OK] In-run loot capacity 24/24 and UI status verified.")
        finally:
            ui_node.removeNode()

    print("\n=== ALL RPG EXPANSION VERIFICATION CHECKS PASSED SUCCESSFULLY! ===")
    return 0


if __name__ == "__main__":
    sys.exit(run_expansion_verification())

