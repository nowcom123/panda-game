"""End-to-end verification script for RPG foundation data models and save store.

Demonstrates:
1. Loading the item catalog
2. Creating a new profile
3. Adding items (weapons and materials) with affixes
4. Equipping two weapons into primary/secondary slots
5. Saving to an isolated temporary directory
6. Restoring and validating data integrity
7. Corrupting the primary save and recovering from .bak
8. Clean teardown
"""

import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path when script is executed directly
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rpg.items import create_item, load_catalog
from rpg.profile import new_profile
from rpg.save_store import SaveStore


def main() -> int:
    print("=== RPG Foundation E2E Verification ===")

    # 1. Load catalog
    catalog = load_catalog()
    print(f"[OK] Catalog loaded successfully with {len(catalog)} item definitions.")

    # Use TemporaryDirectory to prevent touching real user data
    with tempfile.TemporaryDirectory() as temp_dir:
        save_path = Path(temp_dir) / "profile.json"
        store = SaveStore(save_path, catalog)
        print(f"[OK] Isolated sandbox created at: {temp_dir}")

        # 2. Create new profile
        profile = new_profile(profile_id="hero-operative-42")
        print(f"[OK] New profile initialized with ID: {profile.profile_id}")

        # 3. Create items (2 weapons, 1 material)
        pistol = create_item(
            catalog,
            "weapon_pistol",
            rarity="rare",
            item_level=3,
            affixes=[{"id": "damage_mult", "value": 1.15}],
            uid="pistol-v01",
        )
        ar = create_item(
            catalog,
            "weapon_ar",
            rarity="epic",
            item_level=5,
            affixes=[
                {"id": "reload_time_mult", "value": 0.85},
                {"id": "weakpoint_mult", "value": 1.3},
            ],
            uid="ar-v01",
        )
        scrap = create_item(
            catalog,
            "scrap_metal",
            quantity=25,
            uid="scrap-v01",
        )

        profile.add_item(pistol)
        profile.add_item(ar)
        profile.add_item(scrap)
        print(f"[OK] Added 3 items to inventory: {list(profile.items.keys())}")

        # 4. Equip two weapons into primary and secondary
        profile.equip("primary", pistol.uid, catalog)
        profile.equip("secondary", ar.uid, catalog)
        profile.currencies["credits"] = 1500
        profile.unlocks.append("subway_station_keycard")
        profile.validate(catalog)
        print(f"[OK] Equipped primary={profile.equipment['primary']}, secondary={profile.equipment['secondary']}")

        # 5. First save (creates primary save file)
        store.save(profile)
        assert save_path.is_file(), "Primary save file was not created"
        print("[OK] First save succeeded.")

        # Second save (rotates initial save into .bak)
        profile.currencies["credits"] = 2000
        store.save(profile)
        assert store.backup_path.is_file(), "Backup save file was not created"
        print("[OK] Second save succeeded with backup rotation.")

        # 6. Load and verify integrity from primary
        load_result = store.load()
        assert load_result.source == "primary", f"Expected primary, got {load_result.source}"
        assert load_result.profile.currencies["credits"] == 2000
        assert load_result.profile.equipment["primary"] == "pistol-v01"
        assert load_result.profile.equipment["secondary"] == "ar-v01"
        assert load_result.profile.items["scrap-v01"].quantity == 25
        assert len(load_result.profile.items["ar-v01"].affixes) == 2
        print("[OK] Verified roundtrip save and load data integrity from primary.")

        # 7. Corrupt primary file and test recovery from .bak
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("<<<CORRUPTED_RAW_BYTES_SIMULATION>>>")
        print("[OK] Simulated corruption of primary save file.")

        recovered_result = store.load()
        assert recovered_result.source == "backup", f"Expected backup, got {recovered_result.source}"
        assert len(recovered_result.warnings) > 0, "Expected warnings on recovery"
        assert recovered_result.profile.currencies["credits"] == 1500  # The backed up version
        assert recovered_result.profile.equipment["primary"] == "pistol-v01"
        print(f"[OK] Successfully recovered profile from backup. Warning: {recovered_result.warnings[0]}")

        # Check primary file was left untouched
        with open(save_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "<<<CORRUPTED_RAW_BYTES_SIMULATION>>>", "Primary file was unexpectedly modified"
        print("[OK] Confirmed load did not overwrite corrupted primary file on disk.")

    print("=== All RPG Foundation verifications passed successfully! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
