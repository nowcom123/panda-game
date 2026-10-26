"""Character creation, selection, and independent storage management."""

from __future__ import annotations

import json
import os
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from rpg.items import (
    ItemDefinition,
    RPGError,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    unique_json_object,
)
from rpg.profile import CURRENT_SCHEMA_VERSION, PlayerProfile, new_profile
from rpg.save_store import SaveStore

CURRENT_CHARACTER_LIST_VERSION = 1
MAX_CHARACTERS = 3


def validate_character_name(name: str) -> str:
    """Validate character name: 2-12 characters, trimmed, no control characters."""
    if not isinstance(name, str):
        raise ValidationError("캐릭터 이름은 문자열이어야 합니다.")
    clean = name.strip()
    if not (2 <= len(clean) <= 12):
        raise ValidationError("캐릭터 이름은 2자 이상 12자 이하여야 합니다.")
    for char in clean:
        cat = unicodedata.category(char)
        if cat.startswith("C"):  # Control, format, surrogate, etc.
            raise ValidationError("캐릭터 이름에 제어 문자를 포함할 수 없습니다.")
    return clean


@dataclass
class CharacterSummary:
    """Summary information of a character stored in characters.json."""
    id: str
    name: str
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterSummary:
        if not isinstance(data, dict):
            raise ValidationError("Character data must be a dict")
        raw_id = data.get("id")
        raw_name = data.get("name")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValidationError("Character id must be a non-empty string")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValidationError("Character name must be a non-empty string")
        # Validate that id is a valid UUID
        try:
            raw_id = str(uuid.UUID(raw_id))
        except (ValueError, AttributeError):
            raise ValidationError(f"Invalid character id UUID: {raw_id}")

        clean_name = validate_character_name(raw_name)
        created_at = str(data.get("created_at", ""))
        return cls(id=raw_id, name=clean_name, created_at=created_at)


@dataclass
class CharacterList:
    """List of all characters and active character selection."""
    version: int = CURRENT_CHARACTER_LIST_VERSION
    active_character_id: str | None = None
    characters: list[CharacterSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "active_character_id": self.active_character_id,
            "characters": [c.to_dict() for c in self.characters],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterList:
        if not isinstance(data, dict):
            raise ValidationError("Character list data must be a dict")
        ver = data.get("version")
        if isinstance(ver, bool) or not isinstance(ver, int):
            raise ValidationError("version must be an integer")
        if ver > CURRENT_CHARACTER_LIST_VERSION:
            raise UnsupportedSaveVersion(
                f"Unsupported character list version: {ver} (supported: {CURRENT_CHARACTER_LIST_VERSION})"
            )
        if ver < CURRENT_CHARACTER_LIST_VERSION:
            raise ValidationError(f"Invalid character list version: {ver}")

        active_id = data.get("active_character_id")
        if active_id is not None:
            if not isinstance(active_id, str):
                raise ValidationError("active_character_id must be a string or null")
            try:
                active_id = str(uuid.UUID(active_id))
            except (ValueError, AttributeError):
                raise ValidationError(f"Invalid active_character_id UUID: {active_id}")

        raw_chars = data.get("characters", [])
        if not isinstance(raw_chars, list):
            raise ValidationError("characters must be a list")

        characters = [CharacterSummary.from_dict(c) for c in raw_chars]
        ids = [c.id for c in characters]
        if len(set(ids)) != len(ids):
            raise ValidationError("Duplicate character IDs")
        if active_id is not None and active_id not in ids:
            raise ValidationError("Active character is not in the character list")
        if len(characters) > MAX_CHARACTERS:
            raise ValidationError(f"Characters exceed maximum limit of {MAX_CHARACTERS}")

        return cls(version=ver, active_character_id=active_id, characters=characters)


class CharacterManager:
    """Manages character lifecycle, list persistence, and per-character SaveStores."""

    def __init__(self, root_dir: str | Path, catalog: Mapping[str, ItemDefinition]) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.catalog = catalog
        self.list_path = self.root_dir / "characters.json"
        self.list_backup_path = self.root_dir / "characters.json.bak"
        self.characters_dir = self.root_dir / "characters"
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.character_list: CharacterList | None = None

    def _inspect_existing_list_file(self, target_path: Path) -> dict[str, Any] | None:
        if not target_path.exists():
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f, object_pairs_hook=unique_json_object)
        except (json.JSONDecodeError, UnicodeError, ValidationError):
            return None

        if isinstance(data, dict):
            raw_ver = data.get("version")
            if (
                not isinstance(raw_ver, bool)
                and isinstance(raw_ver, int)
                and raw_ver > CURRENT_CHARACTER_LIST_VERSION
            ):
                raise UnsupportedSaveVersion(
                    f"File {target_path} has unsupported higher version: {raw_ver} "
                    f"(supported up to {CURRENT_CHARACTER_LIST_VERSION})"
                )
        return data if isinstance(data, dict) else None

    def _atomic_write(self, target: Path, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target.with_name(f"{target.name}.tmp.{uuid.uuid4().hex}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    def load_character_list(self) -> CharacterList:
        """Load character list from characters.json or backup; migrate legacy profile if needed."""
        # 1. If characters.json exists
        if self.list_path.exists():
            try:
                data = self._inspect_existing_list_file(self.list_path)
                if data is None:
                    raise SaveCorruptedError(f"Failed to parse JSON from {self.list_path}")
                self.character_list = CharacterList.from_dict(data)
                return self.character_list
            except UnsupportedSaveVersion:
                raise
            except (ValidationError, SaveCorruptedError) as primary_err:
                # Try backup
                if self.list_backup_path.exists():
                    try:
                        b_data = self._inspect_existing_list_file(self.list_backup_path)
                        if b_data is None:
                            raise SaveCorruptedError(f"Backup {self.list_backup_path} is invalid")
                        self.character_list = CharacterList.from_dict(b_data)
                        return self.character_list
                    except UnsupportedSaveVersion:
                        raise
                    except Exception as b_err:
                        raise SaveCorruptedError(
                            f"Both primary {self.list_path} and backup {self.list_backup_path} corrupted: {primary_err}; {b_err}"
                        ) from b_err
                raise SaveCorruptedError(f"Character list {self.list_path} corrupted: {primary_err}") from primary_err

        # 2. If primary missing but backup exists
        if self.list_backup_path.exists():
            try:
                b_data = self._inspect_existing_list_file(self.list_backup_path)
                if b_data is None:
                    raise SaveCorruptedError(f"Backup {self.list_backup_path} is invalid")
                self.character_list = CharacterList.from_dict(b_data)
                return self.character_list
            except UnsupportedSaveVersion:
                raise
            except Exception as b_err:
                raise SaveCorruptedError(f"Backup {self.list_backup_path} corrupted: {b_err}") from b_err

        # 3. Neither exists: check for legacy single profile.json
        legacy_path = self.root_dir / "profile.json"
        if legacy_path.exists() or (self.root_dir / "profile.json.bak").exists():
            self.character_list = self._migrate_legacy_profile(legacy_path)
            return self.character_list

        # 4. Fresh empty list
        self.character_list = CharacterList(version=CURRENT_CHARACTER_LIST_VERSION, active_character_id=None, characters=[])
        return self.character_list

    def save_character_list(self) -> None:
        """Atomically save character list and rotate backup."""
        if self.character_list is None:
            return
        payload = self.character_list.to_dict()
        # Verify before saving
        CharacterList.from_dict(payload)
        self._inspect_existing_list_file(self.list_backup_path)

        # Rotate existing valid list to backup
        if self.list_path.exists():
            existing = self._inspect_existing_list_file(self.list_path)
            if existing is not None:
                try:
                    CharacterList.from_dict(existing)
                    self._atomic_write(self.list_backup_path, existing)
                except ValidationError:
                    pass

        self._atomic_write(self.list_path, payload)

    def _migrate_legacy_profile(self, legacy_path: Path) -> CharacterList:
        """Migrate existing profile.json to characters/<uuid>/profile.json preserving original."""
        legacy_store = SaveStore(legacy_path, self.catalog)
        load_result = legacy_store.load()
        legacy_profile = load_result.profile

        # Deterministic UUID based on profile_id ensures idempotence and no duplicate migration
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"legacy_{legacy_profile.profile_id}"))

        target_store = self.get_character_save_store(deterministic_id)
        # Save to target without deleting legacy file or backup
        if not target_store.path.exists() and not target_store.backup_path.exists():
            target_store.save(legacy_profile)

        # Verify target file loads
        verify_result = target_store.load()
        if not verify_result.profile or verify_result.profile.profile_id != legacy_profile.profile_id:
            raise SaveCorruptedError("Migration verification failed: target profile did not match")

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        char_summary = CharacterSummary(
            id=deterministic_id,
            name="기존 탐험가",
            created_at=getattr(legacy_profile, "created_at", now_str),
        )
        char_list = CharacterList(
            version=CURRENT_CHARACTER_LIST_VERSION,
            active_character_id=deterministic_id,
            characters=[char_summary],
        )
        self.character_list = char_list
        self.save_character_list()
        return char_list

    def get_character_save_store(self, char_id: str) -> SaveStore:
        """Get SaveStore for a specific character ID, enforcing strict UUID validation."""
        try:
            parsed = uuid.UUID(char_id)
            canonical_id = str(parsed)
        except (ValueError, AttributeError):
            raise ValidationError(f"Invalid character id UUID: {char_id}")

        char_dir = self.characters_dir / canonical_id
        char_dir.mkdir(parents=True, exist_ok=True)
        return SaveStore(char_dir / "profile.json", self.catalog)

    def get_active_save_store(self) -> SaveStore | None:
        """Get SaveStore for currently active character."""
        if not self.character_list:
            self.load_character_list()
        if not self.character_list or not self.character_list.active_character_id:
            return None
        return self.get_existing_character_store(self.character_list.active_character_id)

    def get_existing_character_store(self, char_id: str) -> SaveStore:
        if not self.character_list or not any(c.id == char_id for c in self.character_list.characters):
            raise ValidationError("Unknown character ID")
        store = self.get_character_save_store(char_id)
        if not store.path.exists() and not store.backup_path.exists():
            raise SaveCorruptedError("캐릭터 저장 파일이 없습니다. 빈 데이터로 대체하지 않습니다.")
        return store

    def create_character(self, name: str) -> CharacterSummary:
        """Create a new character with starter profile."""
        if not self.character_list:
            self.load_character_list()

        if len(self.character_list.characters) >= MAX_CHARACTERS:
            raise RPGError(f"캐릭터는 최대 {MAX_CHARACTERS}명까지 생성할 수 있습니다.")

        clean_name = validate_character_name(name)
        new_id = str(uuid.uuid4())

        # Initialize fresh profile for this character
        store = self.get_character_save_store(new_id)
        prof = new_profile()
        store.save(prof)

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        summary = CharacterSummary(id=new_id, name=clean_name, created_at=now_str)
        previous_active = self.character_list.active_character_id
        self.character_list.characters.append(summary)
        self.character_list.active_character_id = new_id
        try:
            self.save_character_list()
        except Exception:
            self.character_list.characters.remove(summary)
            self.character_list.active_character_id = previous_active
            raise
        return summary

    def select_character(self, char_id: str) -> None:
        """Select active character by UUID."""
        if not self.character_list:
            self.load_character_list()

        match = next((c for c in self.character_list.characters if c.id == char_id), None)
        if not match:
            raise RPGError(f"존재하지 않는 캐릭터 ID입니다: {char_id}")

        self.get_existing_character_store(char_id).load()
        previous_active = self.character_list.active_character_id
        self.character_list.active_character_id = char_id
        try:
            self.save_character_list()
        except Exception:
            self.character_list.active_character_id = previous_active
            raise

    def delete_character(self, char_id: str, *, confirmation_name: str) -> bool:
        """Remove a roster entry atomically, retaining profile files for recovery.

        Returns whether the active character was removed. Caller must discard
        its runtime session in that case. No filesystem deletion is performed.
        """
        if self.character_list is None:
            self.load_character_list()
        match = next((c for c in self.character_list.characters if c.id == char_id), None)
        if match is None:
            raise ValidationError('존재하지 않는 캐릭터입니다.')
        if not isinstance(confirmation_name, str) or confirmation_name != match.name:
            raise ValidationError('삭제할 캐릭터 이름을 정확히 입력하세요.')
        previous = self.character_list
        was_active = previous.active_character_id == char_id
        self.character_list = CharacterList(
            version=previous.version,
            active_character_id=None if was_active else previous.active_character_id,
            characters=[c for c in previous.characters if c.id != char_id],
        )
        try:
            self.save_character_list()
        except Exception:
            self.character_list = previous
            raise
        return was_active

    def get_character_card_data(self, char_id: str) -> dict[str, Any]:
        """Fetch summary display info for character cards."""
        char_info = next((c for c in self.character_list.characters if c.id == char_id), None) if self.character_list else None
        name = char_info.name if char_info else "알 수 없음"

        try:
            store = self.get_existing_character_store(char_id)
            res = store.load()
            prof = res.profile
            item_count = len(prof.items)
            pri_uid = prof.equipment.get("primary")
            sec_uid = prof.equipment.get("secondary")
            pri_item = prof.items.get(pri_uid) if pri_uid else None
            sec_item = prof.items.get(sec_uid) if sec_uid else None

            pri_name = self.catalog[pri_item.definition_id].name if pri_item and pri_item.definition_id in self.catalog else (pri_item.definition_id if pri_item else "없음")
            sec_name = self.catalog[sec_item.definition_id].name if sec_item and sec_item.definition_id in self.catalog else (sec_item.definition_id if sec_item else "없음")
            credits_val = prof.currencies.get("credits", 0)
        except Exception:
            item_count = 0
            pri_name = "오류"
            sec_name = "오류"
            credits_val = 0

        return {
            "id": char_id,
            "name": name,
            "item_count": item_count,
            "primary_name": pri_name,
            "secondary_name": sec_name,
            "credits": credits_val,
            "is_active": (self.character_list and self.character_list.active_character_id == char_id),
        }
