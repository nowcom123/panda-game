"""In-run loot bag and extraction transaction management."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from rpg.items import ItemInstance, ValidationError
from rpg.session import RPGSession

MAX_RUN_LOOT_CAPACITY = 24


class RunLootBag:
    """Manages unextracted (pending) loot collected during a single campaign run."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id: str = run_id or str(uuid.uuid4())
        self.pending_items: list[ItemInstance] = []
        self.is_extracted: bool = False
        self.is_abandoned: bool = False
        self.last_save_error: str | None = None

    @property
    def count(self) -> int:
        return len(self.pending_items)

    @property
    def capacity(self) -> int:
        return MAX_RUN_LOOT_CAPACITY

    def can_add(self) -> bool:
        return (
            not self.is_extracted
            and not self.is_abandoned
            and len(self.pending_items) < MAX_RUN_LOOT_CAPACITY
        )

    def add_item(
        self,
        item: ItemInstance,
        session: RPGSession | None = None,
    ) -> tuple[bool, str]:
        """Add an item instance to the run bag."""
        if self.is_extracted:
            return False, "이미 탈출이 완료된 탐험입니다."

        if self.is_abandoned:
            return False, "이미 포기된 탐험입니다."

        if len(self.pending_items) >= MAX_RUN_LOOT_CAPACITY:
            return False, f"탐험 가방이 가득 찼습니다 ({MAX_RUN_LOOT_CAPACITY}/{MAX_RUN_LOOT_CAPACITY})."

        # Check UID duplication within pending items
        if any(p.uid == item.uid for p in self.pending_items):
            return False, "이미 가방에 존재하는 아이템입니다."

        # Check UID duplication against permanent profile items
        if session and session.profile and item.uid in session.profile.items:
            return False, "이미 영구 소유 중인 아이템입니다."

        self.pending_items.append(item)
        return True, "아이템을 획득했습니다."

    def extract(self, session: RPGSession) -> tuple[bool, str]:
        """Merge all pending loot into the permanent profile and save to disk atomically.

        Returns (success: bool, message: str).
        """
        if self.is_extracted:
            return True, "이미 탈출 보상이 확보되었습니다."

        if self.is_abandoned:
            return False, "포기된 탐험의 전리품은 확보할 수 없습니다."

        if not session or not session.is_valid or not session.profile:
            self.last_save_error = "유효한 영구 프로필 세션이 없습니다."
            return False, self.last_save_error

        # If nothing to extract, mark done and return
        if not self.pending_items:
            self.is_extracted = True
            self.last_save_error = None
            return True, "확보할 전리품이 없습니다."

        # 1. Clone candidate profile
        candidate = copy.deepcopy(session.profile)

        # 2. Merge pending items into candidate
        for item in self.pending_items:
            if item.uid in candidate.items:
                self.last_save_error = f"중복 아이템 UID 감지: {item.uid}"
                return False, self.last_save_error
            candidate.add_item(item)

        # 3. Validate candidate against catalog
        try:
            candidate.validate(session.catalog)
        except Exception as err:
            self.last_save_error = f"프로필 검증 실패: {err}"
            return False, self.last_save_error

        # 4. Atomic save to disk
        try:
            session.store.save(candidate)
        except Exception as err:
            self.last_save_error = f"탈출 저장 실패: {err}"
            # Keep pending_items intact for retry!
            return False, self.last_save_error

        # 5. Success: update session profile and clear pending
        session.profile = candidate
        session.refresh_cache()
        extracted_count = len(self.pending_items)
        self.pending_items.clear()
        self.is_extracted = True
        self.last_save_error = None

        return True, f"전리품 {extracted_count}개 영구 확보 완료!"

    def abandon(self) -> int:
        """Explicitly abandon pending loot (player confirmation required)."""
        lost_count = len(self.pending_items)
        self.pending_items.clear()
        self.is_abandoned = True
        return lost_count

    def clear_on_death(self) -> int:
        """Discard all pending loot on player death without modifying permanent save."""
        lost_count = len(self.pending_items)
        self.pending_items.clear()
        self.is_abandoned = True
        return lost_count

