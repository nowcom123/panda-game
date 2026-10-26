"""Save store implementation with atomic write, backup rotation, and integrity recovery."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from rpg.items import (
    ItemDefinition,
    SaveCorruptedError,
    UnsupportedSaveVersion,
    ValidationError,
    unique_json_object,
)
from rpg.profile import CURRENT_SCHEMA_VERSION, PlayerProfile, new_profile

# Extension hook for future schema migrations (e.g. 1 -> 2)
# Signature: Callable[[dict[str, Any]], dict[str, Any]]
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


@dataclass(frozen=True)
class LoadResult:
    """Outcome of loading a save file."""
    profile: PlayerProfile
    source: str  # "primary" | "backup" | "new"
    warnings: list[str]


def get_default_save_path() -> Path:
    """Calculate the platform-appropriate default save file path."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data and local_app_data.strip():
        return Path(local_app_data) / "LiminalBackrooms" / "profile.json"
    return Path.home() / ".liminal_backrooms" / "profile.json"


class SaveStore:
    """Manages persistent player profile saving, loading, atomic swap, and backup."""

    def __init__(self, path: str | Path, catalog: Mapping[str, ItemDefinition]) -> None:
        self.path = Path(path).resolve()
        self.backup_path = self.path.with_name(self.path.name + ".bak")
        self.catalog = catalog

    def _inspect_existing_file(self, target_path: Path) -> dict[str, Any] | None:
        """Inspect and parse an existing save file.

        Returns parsed dict if JSON is valid; returns None if file does not exist or JSON is invalid.
        Raises UnsupportedSaveVersion if schema_version is higher than supported.
        """
        if not target_path.exists():
            return None

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f, object_pairs_hook=unique_json_object)
        except (json.JSONDecodeError, UnicodeError, ValidationError):
            return None

        if isinstance(data, dict):
            raw_ver = data.get("schema_version")
            if (
                not isinstance(raw_ver, bool)
                and isinstance(raw_ver, int)
                and raw_ver > CURRENT_SCHEMA_VERSION
            ):
                raise UnsupportedSaveVersion(
                    f"File {target_path} has unsupported higher schema version: {raw_ver} "
                    f"(supported up to {CURRENT_SCHEMA_VERSION})"
                )
        return data if isinstance(data, dict) else None

    def save(self, profile: PlayerProfile) -> None:
        """Atomically save the profile, updating backup only if existing save is valid."""
        profile.validate(self.catalog)
        # Protect future-version backups too, including a missing primary.
        self._inspect_existing_file(self.backup_path)

        # Disallow overwriting higher schema version files
        if self.path.exists():
            existing_data = self._inspect_existing_file(self.path)
            if existing_data is not None:
                try:
                    # Verify existing save is valid before rotating to backup
                    PlayerProfile.from_dict(existing_data, self.catalog)
                except ValidationError:
                    # Existing primary is corrupted; do not overwrite good backup with it!
                    pass
                else:
                    self._atomic_write(self.backup_path, existing_data)

        payload = profile.to_dict()
        self._atomic_write(self.path, payload)

    @staticmethod
    def _atomic_write(target, payload):
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

    def load(self) -> LoadResult:
        """Load profile from primary save or fall back to backup if corrupted.

        Returns LoadResult. If neither exists, returns new in-memory profile without writing to disk.
        """
        if not self.path.exists():
            if not self.backup_path.exists():
                # No files exist: return fresh in-memory profile
                return LoadResult(profile=new_profile(), source="new", warnings=[])

            # Primary missing but backup exists
            try:
                backup_data = self._inspect_existing_file(self.backup_path)
                if backup_data is None:
                    raise SaveCorruptedError(f"Backup file at {self.backup_path} is invalid JSON")
                backup_profile = PlayerProfile.from_dict(backup_data, self.catalog)
                return LoadResult(
                    profile=backup_profile,
                    source="backup",
                    warnings=[f"Primary save {self.path} missing; loaded from backup {self.backup_path}"],
                )
            except UnsupportedSaveVersion:
                raise
            except (ValidationError, SaveCorruptedError) as backup_err:
                raise SaveCorruptedError(
                    f"Primary save missing at {self.path} and backup corrupted at {self.backup_path}: {backup_err}"
                ) from backup_err

        # Primary exists
        primary_err: Exception | None = None
        try:
            primary_data = self._inspect_existing_file(self.path)
            if primary_data is None:
                raise SaveCorruptedError(f"Failed to parse JSON from primary save {self.path}")
            profile = PlayerProfile.from_dict(primary_data, self.catalog)
            return LoadResult(profile=profile, source="primary", warnings=[])
        except UnsupportedSaveVersion:
            # Do not fall back to backup on higher schema version
            raise
        except (ValidationError, SaveCorruptedError) as err:
            primary_err = err

        # Primary is corrupted; try backup
        if not self.backup_path.exists():
            raise SaveCorruptedError(
                f"Primary save file {self.path} is corrupted ({primary_err}) and no backup file exists."
            ) from primary_err

        try:
            backup_data = self._inspect_existing_file(self.backup_path)
            if backup_data is None:
                raise SaveCorruptedError(f"Backup file {self.backup_path} is also corrupted")
            backup_profile = PlayerProfile.from_dict(backup_data, self.catalog)
            return LoadResult(
                profile=backup_profile,
                source="backup",
                warnings=[
                    f"Primary save {self.path} is corrupted ({primary_err}); recovered from backup {self.backup_path}"
                ],
            )
        except UnsupportedSaveVersion:
            raise
        except (ValidationError, SaveCorruptedError) as backup_err:
            raise SaveCorruptedError(
                f"Both primary save {self.path} and backup {self.backup_path} are corrupted. "
                f"Primary error: {primary_err}; Backup error: {backup_err}"
            ) from backup_err

