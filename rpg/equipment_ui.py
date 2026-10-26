"""Equipment UI panel for managing weapons, affixes, comparison, and slot assignments."""

from __future__ import annotations

from typing import Any, Callable

try:
    from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
    from direct.gui.OnscreenText import OnscreenText
    from panda3d.core import LColor, TextNode, TransparencyAttrib, TextProperties, TextPropertiesManager
    HAS_PANDA3D = True
except ImportError:
    HAS_PANDA3D = False
    DirectFrame = object  # type: ignore
    DirectButton = object  # type: ignore
    OnscreenText = object  # type: ignore
    TextNode = None  # type: ignore
    TransparencyAttrib = None  # type: ignore
    LColor = None  # type: ignore
    DGG = None  # type: ignore

from rpg.session import RPGSession
from rpg.weapon_stats import resolve_weapon_config
from combat.weapon_config import WEAPON_CONFIGS

RARITY_NAMES = {
    "common": "일반",
    "uncommon": "고급",
    "rare": "희귀",
    "epic": "영웅",
    "legendary": "전설",
}

RARITY_ORDER = {
    "legendary": 0,
    "epic": 1,
    "rare": 2,
    "uncommon": 3,
    "common": 4,
}

RARITY_COLORS = {
    "common": (0.85, 0.85, 0.85, 1.0),
    "uncommon": (0.35, 0.95, 0.45, 1.0),
    "rare": (0.30, 0.70, 1.0, 1.0),
    "epic": (0.80, 0.40, 1.0, 1.0),
    "legendary": (1.0, 0.75, 0.20, 1.0),
}

AFFIX_NAMES = {
    "damage_mult": "기본 공격력",
    "reload_time_mult": "재장전 시간",
    "weakpoint_mult": "약점 헤드샷 피해",
}


class EquipmentUIPanel:
    """3-column Equipment and stash inspection panel embedded in the tactical inventory modal.
    - Left Column: Primary & Secondary equipped weapon slots, credits
    - Center Column: Stash storage with [Rarity/Kind/Name] sorting and pagination
    - Right Column: Detailed item stats, affixes, and comparison vs target slot
    """

    ITEMS_PER_PAGE = 7

    def __init__(
        self,
        parent_node: Any,
        session: RPGSession,
        combat: Any = None,
        on_change_callback: Callable[[], None] | None = None,
        font_kw: dict[str, Any] | None = None,
        btn_font_kw: dict[str, Any] | None = None,
        on_open_workshop: Callable[[], None] | None = None,
    ) -> None:
        self.parent_node = parent_node
        self.session = session
        self.combat = combat
        self.on_change_callback = on_change_callback
        self.on_open_workshop = on_open_workshop
        self.font_kw = font_kw or {}
        self.btn_font_kw = btn_font_kw or {}

        self.current_page = 0
        self.selected_uid: str | None = None
        self.target_slot: str = "primary"  # slot used for stat comparison
        self.sort_mode: str = "rarity"      # "rarity" | "kind" | "name"

        self.frame: Any = None
        self.item_rows: list[Any] = []
        self._build_ui()

    def _build_ui(self) -> None:
        if not HAS_PANDA3D or self.parent_node is None:
            return
        for name, color in (('rpg_better', (.35, 1, .5, 1)), ('rpg_worse', (1, .4, .35, 1))):
            prop = TextProperties()
            prop.setTextColor(*color)
            TextPropertiesManager.getGlobalPtr().setProperties(name, prop)

        # Main panel container
        self.frame = DirectFrame(
            parent=self.parent_node,
            relief=None,
            frameSize=(-1.65, 1.65, -0.85, 0.72),
            pos=(0, 0, 0),
        )
        # 3 Distinct Column Background Cards & Dividers
        self.frame_col1 = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.42, 0.42, -0.56, 0.56),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(-1.14, 0, -0.06),
        )
        DirectFrame(
            parent=self.frame_col1,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.38, 0.38, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.48),
        )
        self.frame_col2 = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.44, 0.44, -0.56, 0.56),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(-0.05, 0, -0.06),
        )
        DirectFrame(
            parent=self.frame_col2,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.40, 0.40, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.48),
        )
        self.frame_col3 = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.46, 0.46, -0.56, 0.56),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(1.05, 0, -0.06),
        )
        DirectFrame(
            parent=self.frame_col3,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.42, 0.42, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.48),
        )

        # =============================================================
        # 1. Left Column: Equipped Weapon Slots (x = -1.14)
        # =============================================================
        self.lbl_slots_title = OnscreenText(
            text="■ 슬롯 장착 무기",
            parent=self.frame,
            pos=(-1.48, 0.54),
            scale=0.034,
            fg=(0.35, 0.90, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # Primary Slot Card
        self.btn_slot_primary = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.34, 0.34, -0.11, 0.11),
            pos=(-1.14, 0, 0.34),
            text="[ 1 : 주 무기 ]\n장착 정보 로딩 중...",
            text_scale=0.032,
            text_pos=(0, 0.04),
            text_fg=(0.95, 0.95, 1.0, 1.0),
            command=self._select_slot,
            extraArgs=["primary"],
            **self.btn_font_kw,
        )

        # Secondary Slot Card
        self.btn_slot_secondary = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.34, 0.34, -0.11, 0.11),
            pos=(-1.14, 0, 0.06),
            text="[ 2 : 보조 무기 ]\n장착 정보 로딩 중...",
            text_scale=0.032,
            text_pos=(0, 0.04),
            text_fg=(0.95, 0.95, 1.0, 1.0),
            command=self._select_slot,
            extraArgs=["secondary"],
            **self.btn_font_kw,
        )

        self.lbl_slot_hint = OnscreenText(
            text="* 슬롯을 클릭하여 비교 기준을 전환하세요.",
            parent=self.frame,
            pos=(-1.48, -0.10),
            scale=0.032,
            fg=(0.70, 0.80, 0.90, 0.90),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.txt_currencies = OnscreenText(
            text="보유 크레딧: 0 C",
            parent=self.frame,
            pos=(-1.48, -0.22),
            scale=0.032,
            fg=(1.0, 0.85, 0.30, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # =============================================================
        # 2. Middle Column: Stash Storage with Sorting (x = -0.05)
        # =============================================================
        self.lbl_inv_title = OnscreenText(
            text="■ 영구 보관함 (0개)",
            parent=self.frame,
            pos=(-0.45, 0.54),
            scale=0.034,
            fg=(0.40, 0.92, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # Sort Buttons
        self.btn_sort_rarity = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.11, 0.11, -0.028, 0.028),
            pos=(-0.30, 0, 0.48),
            text="[ 등급순 ]",
            text_scale=0.032,
            text_pos=(0, -0.007),
            text_fg=(0.35, 0.95, 1.0, 1.0),
            command=self._set_sort_mode,
            extraArgs=["rarity"],
            **self.btn_font_kw,
        )
        self.btn_sort_kind = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.11, 0.11, -0.028, 0.028),
            pos=(-0.05, 0, 0.48),
            text="[ 종류순 ]",
            text_scale=0.032,
            text_pos=(0, -0.007),
            text_fg=(0.75, 0.80, 0.85, 1.0),
            command=self._set_sort_mode,
            extraArgs=["kind"],
            **self.btn_font_kw,
        )
        self.btn_sort_name = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.11, 0.11, -0.028, 0.028),
            pos=(0.20, 0, 0.48),
            text="[ 이름순 ]",
            text_scale=0.032,
            text_pos=(0, -0.007),
            text_fg=(0.75, 0.80, 0.85, 1.0),
            command=self._set_sort_mode,
            extraArgs=["name"],
            **self.btn_font_kw,
        )

        # Item Rows (7 items per page)
        self.item_rows = []
        for i in range(self.ITEMS_PER_PAGE):
            y_pos = 0.38 - (i * 0.09)
            btn = DirectButton(
                parent=self.frame,
                relief=None,
                frameSize=(-0.38, 0.38, -0.038, 0.038),
                pos=(-0.05, 0, y_pos),
                text=f"아이템 슬롯 {i+1}",
                text_scale=0.032,
                text_pos=(-0.36, -0.008),
                text_align=TextNode.ALeft if TextNode else 0,
                text_fg=(0.85, 0.85, 0.90, 1.0),
                command=self._select_item_by_index,
                extraArgs=[i],
                **self.btn_font_kw,
            )
            self.item_rows.append(btn)

        # Pagination controls
        self.btn_prev_page = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.12, 0.12, -0.032, 0.032),
            pos=(-0.25, 0, -0.32),
            text="[ ◀ 이전 ]",
            text_scale=0.032,
            text_pos=(0, -0.007),
            text_fg=(0.8, 0.9, 1.0, 1.0),
            command=self._prev_page,
            **self.btn_font_kw,
        )
        self.lbl_page = OnscreenText(
            text="1 / 1",
            parent=self.frame,
            pos=(-0.05, -0.33),
            scale=0.032,
            fg=(0.9, 0.9, 0.9, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            **self.font_kw,
        )
        self.btn_next_page = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.12, 0.12, -0.032, 0.032),
            pos=(0.15, 0, -0.32),
            text="[ 다음 ▶ ]",
            text_scale=0.032,
            text_pos=(0, -0.007),
            text_fg=(0.8, 0.9, 1.0, 1.0),
            command=self._next_page,
            **self.btn_font_kw,
        )

        # =============================================================
        # 3. Right Column: Detailed View & Comparison (x = 1.00)
        # =============================================================
        self.lbl_detail_title = OnscreenText(
            text="■ 상세 제원 및 슬롯 비교",
            parent=self.frame,
            pos=(0.55, 0.54),
            scale=0.034,
            fg=(0.40, 0.90, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.txt_detail_header = OnscreenText(
            text="아이템을 선택하세요",
            parent=self.frame,
            pos=(0.55, 0.48),
            scale=0.032,
            fg=(1.0, 1.0, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            wordwrap=32,
            **self.font_kw,
        )

        self.txt_comparison = OnscreenText(
            text="",
            parent=self.frame,
            pos=(0.55, 0.34),
            scale=0.032,
            fg=(0.95, 0.95, 0.95, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            wordwrap=32,
            **self.font_kw,
        )

        self.txt_detail_affixes = OnscreenText(
            text="",
            parent=self.frame,
            pos=(0.55, -0.02),
            scale=0.032,
            fg=(0.85, 0.95, 0.85, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            wordwrap=32,
            **self.font_kw,
        )

        self.lbl_status_msg = OnscreenText(
            text="",
            parent=self.frame,
            pos=(1.05, -0.20),
            scale=0.032,
            fg=(0.4, 1.0, 0.5, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            wordwrap=32,
            **self.font_kw,
        )

        # Action Buttons
        self.btn_go_workshop = DirectButton(
            parent=self.frame,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.14, 0.28, 0.20, 0.95),
            frameSize=(-0.49, 0.49, -0.040, 0.040),
            pos=(1.05, 0, -0.25),
            text="[ 무기 작업대에서 재료 사용하기 ▶ ]",
            text_scale=0.030,
            text_pos=(0, -0.008),
            text_fg=(1.0, 0.85, 0.35, 1.0),
            command=self._on_click_go_workshop,
            **self.btn_font_kw,
        )
        self.btn_go_workshop.hide()

        self.btn_equip_primary = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.24, 0.24, -0.040, 0.040),
            pos=(0.80, 0, -0.25),
            text="[ 주 무기 장착 ]",
            text_scale=0.032,
            text_pos=(0, -0.008),
            text_fg=(0.4, 0.9, 1.0, 1.0),
            command=self._on_click_equip,
            extraArgs=["primary"],
            **self.btn_font_kw,
        )

        self.btn_equip_secondary = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.24, 0.24, -0.040, 0.040),
            pos=(1.30, 0, -0.25),
            text="[ 보조 무기 장착 ]",
            text_scale=0.032,
            text_pos=(0, -0.008),
            text_fg=(0.4, 0.9, 1.0, 1.0),
            command=self._on_click_equip,
            extraArgs=["secondary"],
            **self.btn_font_kw,
        )

        self.btn_unequip = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.24, 0.24, -0.040, 0.040),
            pos=(0.80, 0, -0.35),
            text="[ 슬롯 해제 ]",
            text_scale=0.032,
            text_pos=(0, -0.008),
            text_fg=(1.0, 0.5, 0.5, 1.0),
            command=self._on_click_unequip,
            **self.btn_font_kw,
        )

        self.btn_lock_toggle = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.24, 0.24, -0.040, 0.040),
            pos=(1.30, 0, -0.35),
            text="[ 잠금 / 해제 ]",
            text_scale=0.032,
            text_pos=(0, -0.008),
            text_fg=(1.0, 0.85, 0.4, 1.0),
            command=self._on_click_lock_toggle,
            **self.btn_font_kw,
        )

    def show(self) -> None:
        """Show equipment UI panel and refresh all components."""
        if self.frame:
            self.frame.show()
        self.refresh()

    def hide(self) -> None:
        """Hide equipment UI panel."""
        if self.frame:
            self.frame.hide()

    def _select_slot(self, slot: str) -> None:
        """Select slot to compare against."""
        self.target_slot = slot
        self.refresh()

    def _set_sort_mode(self, mode: str) -> None:
        """Set active sort mode and refresh list."""
        self.sort_mode = mode
        if hasattr(self, "btn_sort_rarity"):
            self.btn_sort_rarity["text_fg"] = (0.35, 0.95, 1.0, 1.0) if mode == "rarity" else (0.75, 0.80, 0.85, 1.0)
        if hasattr(self, "btn_sort_kind"):
            self.btn_sort_kind["text_fg"] = (0.35, 0.95, 1.0, 1.0) if mode == "kind" else (0.75, 0.80, 0.85, 1.0)
        if hasattr(self, "btn_sort_name"):
            self.btn_sort_name["text_fg"] = (0.35, 0.95, 1.0, 1.0) if mode == "name" else (0.75, 0.80, 0.85, 1.0)
        self.refresh()

    def _get_sorted_items(self) -> list[Any]:
        if not self.session or not self.session.profile:
            return []
        items = list(self.session.profile.items.values())
        cat = self.session.catalog

        if self.sort_mode == "rarity":
            def sort_key(it: Any):
                defn = cat.get(it.definition_id)
                r_order = RARITY_ORDER.get(it.rarity, 99)
                is_wpn = 0 if (defn and defn.kind == "weapon") else 1
                return (r_order, is_wpn, -it.item_level, defn.name if defn else "")
            items.sort(key=sort_key)
        elif self.sort_mode == "kind":
            def sort_key(it: Any):
                defn = cat.get(it.definition_id)
                kind_order = 0 if (defn and defn.kind == "weapon") else 1
                return (kind_order, -it.item_level, defn.name if defn else "")
            items.sort(key=sort_key)
        else:  # "name"
            def sort_key(it: Any):
                defn = cat.get(it.definition_id)
                return (defn.name if defn else it.definition_id, -it.item_level)
            items.sort(key=sort_key)

        return items

    def _select_item_by_index(self, index_in_page: int) -> None:
        items = self._get_sorted_items()
        idx = self.current_page * self.ITEMS_PER_PAGE + index_in_page
        if idx < len(items):
            self.selected_uid = items[idx].uid
        self.refresh()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh()

    def _next_page(self) -> None:
        items = self._get_sorted_items()
        max_pages = max(1, (len(items) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        if self.current_page < max_pages - 1:
            self.current_page += 1
            self.refresh()

    def refresh(self) -> None:
        """Synchronize UI with current profile, catalog, and combat state."""
        if not HAS_PANDA3D or not self.frame:
            return

        if not self.session or not self.session.profile:
            return

        prof = self.session.profile
        cat = self.session.catalog

        # 1. Update Slot Buttons & Currencies
        p_uid = prof.equipment.get("primary")
        s_uid = prof.equipment.get("secondary")

        p_item = prof.items.get(p_uid) if p_uid else None
        s_item = prof.items.get(s_uid) if s_uid else None

        p_name = cat[p_item.definition_id].name if (p_item and p_item.definition_id in cat) else "비어있음"
        s_name = cat[s_item.definition_id].name if (s_item and s_item.definition_id in cat) else "비어있음"

        p_tag = "★ [ 1 : 주 무기 (선택됨) ]" if self.target_slot == "primary" else "[ 1 : 주 무기 ]"
        s_tag = "★ [ 2 : 보조 무기 (선택됨) ]" if self.target_slot == "secondary" else "[ 2 : 보조 무기 ]"

        p_sub = f"Lv.{p_item.item_level} | {RARITY_NAMES.get(p_item.rarity, '')}" if p_item else "(장착 해제 상태)"
        s_sub = f"Lv.{s_item.item_level} | {RARITY_NAMES.get(s_item.rarity, '')}" if s_item else "(장착 해제 상태)"

        self.btn_slot_primary["text"] = f"{p_tag}\n{p_name}\n{p_sub}"
        self.btn_slot_secondary["text"] = f"{s_tag}\n{s_name}\n{s_sub}"
        if self.target_slot == "primary":
            self.btn_slot_primary["frameColor"] = (0.15, 0.24, 0.35, 0.98)
            self.btn_slot_primary["borderWidth"] = (0.006, 0.006)
            self.btn_slot_secondary["frameColor"] = (0.09, 0.12, 0.16, 0.90)
            self.btn_slot_secondary["borderWidth"] = (0.003, 0.003)
        else:
            self.btn_slot_primary["frameColor"] = (0.09, 0.12, 0.16, 0.90)
            self.btn_slot_primary["borderWidth"] = (0.003, 0.003)
            self.btn_slot_secondary["frameColor"] = (0.15, 0.24, 0.35, 0.98)
            self.btn_slot_secondary["borderWidth"] = (0.006, 0.006)

        credits_val = prof.currencies.get("credits", 0)
        self.txt_currencies.setText(f"보유 크레딧: {credits_val:,} C")

        # 2. Update Item List and Pagination
        items = self._get_sorted_items()
        self.lbl_inv_title.setText(f"■ 영구 보관함 ({len(items)}개)")

        # Ensure selected_uid remains valid; if missing, default to first item
        all_uids = {it.uid for it in items}
        if not self.selected_uid or self.selected_uid not in all_uids:
            self.selected_uid = items[0].uid if items else None

        max_pages = max(1, (len(items) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        self.current_page = max(0, min(self.current_page, max_pages - 1))
        self.lbl_page.setText(f"{self.current_page + 1} / {max_pages}")

        start_idx = self.current_page * self.ITEMS_PER_PAGE
        for i in range(self.ITEMS_PER_PAGE):
            row_btn = self.item_rows[i]
            item_idx = start_idx + i
            if item_idx < len(items):
                it = items[item_idx]
                defn = cat.get(it.definition_id)
                d_name = defn.name if defn else "알 수 없음"
                if len(d_name) > 13:
                    d_name = d_name[:12] + ".."
                r_name = RARITY_NAMES.get(it.rarity, it.rarity)

                equip_tag = ""
                if it.uid == p_uid:
                    equip_tag = " [주]"
                elif it.uid == s_uid:
                    equip_tag = " [보조]"

                lock_tag = " 🔒" if it.locked else ""
                sel_tag = "▶ " if it.uid == self.selected_uid else "   "

                qty_str = f" x{it.quantity}" if it.quantity > 1 else ""
                row_text = f"{sel_tag}[{r_name}] {d_name} Lv.{it.item_level}{qty_str}{equip_tag}{lock_tag}"
                row_btn["text"] = row_text
                row_btn["text_fg"] = (1.0, 1.0, 0.4, 1.0) if it.uid == self.selected_uid else RARITY_COLORS.get(it.rarity, (0.8, 0.8, 0.8, 1.0))
                if it.uid == self.selected_uid:
                    row_btn["frameColor"] = (0.16, 0.25, 0.35, 0.98)
                    row_btn["borderWidth"] = (0.004, 0.004)
                else:
                    row_btn["frameColor"] = (0.09, 0.11, 0.16, 0.90) if (i % 2 == 0) else (0.11, 0.14, 0.20, 0.90)
                    row_btn["borderWidth"] = (0.002, 0.002)
                row_btn.show()
            else:
                row_btn.hide()

        # 3. Update Detail & Comparison Panel
        sel_item = prof.items.get(self.selected_uid) if self.selected_uid else None
        if not sel_item:
            self.txt_detail_header.setText("아이템을 선택하세요.")
            self.txt_detail_affixes.setText("")
            self.txt_comparison.setText("")
            self._update_action_buttons(None, p_uid, s_uid)
            return

        sel_defn = cat.get(sel_item.definition_id)
        sel_name = sel_defn.name if sel_defn else "알 수 없음"
        sel_rarity = RARITY_NAMES.get(sel_item.rarity, sel_item.rarity)
        sel_kind = "무기" if (sel_defn and sel_defn.kind == "weapon") else "재료"
        locked_desc = "잠김 🔒" if sel_item.locked else "잠금 해제"

        self.txt_detail_header.setText(
            f"{sel_name} [{sel_rarity}]  |  Lv.{sel_item.item_level}  |  {sel_kind}  |  {locked_desc}"
        )
        self.txt_detail_header.setFg(RARITY_COLORS.get(sel_item.rarity, (1, 1, 1, 1)))

        # Comparison with target slot weapon
        target_uid = prof.equipment.get(self.target_slot)
        target_item = prof.items.get(target_uid) if target_uid else None
        slot_title = "주 무기 [1]" if self.target_slot == "primary" else "보조 무기 [2]"

        if sel_defn and sel_defn.kind == "weapon":
            try:
                sel_cfg = resolve_weapon_config(WEAPON_CONFIGS, cat, sel_item)
            except Exception:
                sel_cfg = None

            comp_lines = [f"【 {slot_title} 슬롯 장비 대비 제원 비교 】"]
            if sel_cfg:
                if target_item:
                    try:
                        target_cfg = resolve_weapon_config(WEAPON_CONFIGS, cat, target_item)
                    except Exception:
                        target_cfg = None

                    if target_cfg:
                        # Damage comparison
                        d_dmg = sel_cfg["damage"] - target_cfg["damage"]
                        if d_dmg > 0.001:
                            dmg_str = f"현재 {target_cfg['damage']:.1f}  →  선택 {sel_cfg['damage']:.1f}  (▲ +{d_dmg:.1f})"
                        elif d_dmg < -0.001:
                            dmg_str = f"현재 {target_cfg['damage']:.1f}  →  선택 {sel_cfg['damage']:.1f}  (▼ {d_dmg:.1f})"
                        else:
                            dmg_str = f"현재 {target_cfg['damage']:.1f}  →  선택 {sel_cfg['damage']:.1f}  (동일)"
                        comp_lines.append(f"  • 기본 공격력 : {dmg_str}")

                        # Reload time comparison (lower is faster/better)
                        d_rel = sel_cfg["reload_time"] - target_cfg["reload_time"]
                        if d_rel < -0.001:
                            rel_str = f"현재 {target_cfg['reload_time']:.2f}s  →  선택 {sel_cfg['reload_time']:.2f}s  (▲ {d_rel:.2f}s 가속)"
                        elif d_rel > 0.001:
                            rel_str = f"현재 {target_cfg['reload_time']:.2f}s  →  선택 {sel_cfg['reload_time']:.2f}s  (▼ +{d_rel:.2f}s 지연)"
                        else:
                            rel_str = f"현재 {target_cfg['reload_time']:.2f}s  →  선택 {sel_cfg['reload_time']:.2f}s  (동일)"
                        comp_lines.append(f"  • 재장전 시간 : {rel_str}")

                        # Weakpoint multiplier comparison
                        d_hs = sel_cfg["headshot_mult"] - target_cfg["headshot_mult"]
                        if d_hs > 0.001:
                            hs_str = f"현재 {target_cfg['headshot_mult']:.2f}x  →  선택 {sel_cfg['headshot_mult']:.2f}x  (▲ +{d_hs:.2f}x)"
                        elif d_hs < -0.001:
                            hs_str = f"현재 {target_cfg['headshot_mult']:.2f}x  →  선택 {sel_cfg['headshot_mult']:.2f}x  (▼ {d_hs:.2f}x)"
                        else:
                            hs_str = f"현재 {target_cfg['headshot_mult']:.2f}x  →  선택 {sel_cfg['headshot_mult']:.2f}x  (동일)"
                        comp_lines.append(f"  • 약점 배율   : {hs_str}")
                    else:
                        comp_lines.append("  (대상 슬롯 장비 설정 오류)")
                else:
                    comp_lines.append("  (현재 슬롯이 비어있음)")
                    comp_lines.append(f"  • 기본 공격력 : {sel_cfg['damage']:.1f}")
                    comp_lines.append(f"  • 재장전 시간 : {sel_cfg['reload_time']:.2f}s")
                    comp_lines.append(f"  • 약점 배율   : {sel_cfg['headshot_mult']:.2f}x")
            for index, line in enumerate(comp_lines):
                style = 'rpg_better' if '▲' in line else 'rpg_worse' if '▼' in line else None
                if style:
                    comp_lines[index] = f"\1{style}\1{line}\2"
            self.txt_comparison.setText("\n".join(comp_lines))
        else:
            if sel_item.definition_id == "scrap_metal":
                self.txt_comparison.setText(
                    "【 재료 아이템 용도 안내 】\n"
                    "  • 용도: 무기 작업대에서 [총열 보강] 강화에 소모 (8개)\n"
                    "  • 효과: 무기 기본 공격력 +2%p 영구 증강 (상한: 1.30x)\n"
                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\n"
                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"
                )
            elif sel_item.definition_id == "bone_fragment":
                self.txt_comparison.setText(
                    "【 재료 아이템 용도 안내 】\n"
                    "  • 용도: 무기 작업대에서 [약점 각인] 강화에 소모 (6개)\n"
                    "  • 효과: 무기 약점 헤드샷 피해 +5%p 영구 증강 (상한: 1.50x)\n"
                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\n"
                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"
                )
            else:
                self.txt_comparison.setText(
                    "【 재료 아이템 용도 안내 】\n"
                    "  • 영구 보관 재료 아이템입니다.\n"
                    "  • 무기 작업대 공정에 활용할 수 있습니다."
                )

        # Affixes list
        if sel_item.affixes:
            lines = ["【 부여된 옵션 효과 】"]
            for aff in sel_item.affixes:
                name_ko = AFFIX_NAMES.get(aff.id, aff.id)
                if aff.id == "reload_time_mult":
                    delta = (1.0 - aff.value) * 100.0
                    val_str = f"-{delta:.1f}% (가속)" if delta > 0 else f"+{-delta:.1f}% (지연)"
                else:
                    delta = (aff.value - 1.0) * 100.0
                    val_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
                lines.append(f"  • {name_ko}: {val_str}")
            self.txt_detail_affixes.setText("\n".join(lines))
        else:
            if sel_defn and sel_defn.kind == "weapon":
                self.txt_detail_affixes.setText("【 부여된 옵션 효과 】\n  (옵션 없음 - 기본 사양)")
            else:
                self.txt_detail_affixes.setText(f"【 재료 수량: {sel_item.quantity}개 】")

        # 4. Action Buttons State and Reason
        self._update_action_buttons(sel_item, p_uid, s_uid)

    def _update_action_buttons(self, sel_item: Any | None, p_uid: str | None, s_uid: str | None) -> None:
        if not sel_item:
            self._set_btn_state(self.btn_equip_primary, False, "[ 주 무기 장착 ]")
            self._set_btn_state(self.btn_equip_secondary, False, "[ 보조 무기 장착 ]")
            self._set_btn_state(self.btn_unequip, False, "[ 슬롯 해제 ]")
            self._set_btn_state(self.btn_lock_toggle, False, "[ 잠금 / 해제 ]")
            return

        cat = self.session.catalog
        defn = cat.get(sel_item.definition_id)
        is_weapon = bool(defn and defn.kind == "weapon")

        if not is_weapon:
            if hasattr(self, "btn_go_workshop") and self.btn_go_workshop:
                self.btn_go_workshop.show()
            if hasattr(self, "btn_equip_primary") and self.btn_equip_primary:
                self.btn_equip_primary.hide()
            if hasattr(self, "btn_equip_secondary") and self.btn_equip_secondary:
                self.btn_equip_secondary.hide()
        else:
            if hasattr(self, "btn_go_workshop") and self.btn_go_workshop:
                self.btn_go_workshop.hide()
            if hasattr(self, "btn_equip_primary") and self.btn_equip_primary:
                self.btn_equip_primary.show()
            if hasattr(self, "btn_equip_secondary") and self.btn_equip_secondary:
                self.btn_equip_secondary.show()
            if sel_item.uid == p_uid:
                self._set_btn_state(self.btn_equip_primary, False, "[이미 주 무기]")
            else:
                self._set_btn_state(self.btn_equip_primary, True, "[ 주 무기 장착 ]")
            if sel_item.uid == s_uid:
                self._set_btn_state(self.btn_equip_secondary, False, "[이미 보조 무기]")
            else:
                self._set_btn_state(self.btn_equip_secondary, True, "[ 보조 무기 장착 ]")

        # Unequip button acts on target slot
        target_uid = p_uid if self.target_slot == "primary" else s_uid
        other_uid = s_uid if self.target_slot == "primary" else p_uid
        if not target_uid:
            self._set_btn_state(self.btn_unequip, False, "[이미 비어있음]")
        elif not other_uid:
            self._set_btn_state(self.btn_unequip, False, "[마지막 무기 해제 불가]")
        else:
            slot_name = "주" if self.target_slot == "primary" else "보조"
            self._set_btn_state(self.btn_unequip, True, f"[ {slot_name} 무기 해제 ]")

        # Lock toggle
        lock_label = "[ 잠금 해제 ]" if sel_item.locked else "[ 아이템 잠금 ]"
        self._set_btn_state(self.btn_lock_toggle, True, lock_label)

    def _on_click_go_workshop(self) -> None:
        if hasattr(self, "on_open_workshop") and self.on_open_workshop:
            self.on_open_workshop()

    def _set_btn_state(self, btn: Any, enabled: bool, text: str) -> None:
        if not btn:
            return
        btn["text"] = text
        if enabled:
            btn["state"] = DGG.NORMAL if DGG else "normal"
            btn["text_fg"] = (0.35, 0.95, 1.0, 1.0)
            btn["frameColor"] = (0.14, 0.22, 0.30, 0.95)
        else:
            btn["state"] = DGG.DISABLED if DGG else "disabled"
            btn["text_fg"] = (0.50, 0.55, 0.60, 1.0)
            btn["frameColor"] = (0.10, 0.12, 0.15, 0.85)

    def _on_click_equip(self, slot: str) -> None:
        if self._read_only():
            return
        if not self.selected_uid:
            self._show_status("아이템을 먼저 선택하세요.", is_error=True)
            return

        success, msg = self.session.equip(slot, self.selected_uid)
        self._show_status(msg, is_error=not success)
        if success:
            if self.combat and hasattr(self.combat, "sync_with_rpg_session"):
                self.combat.sync_with_rpg_session()
            if self.on_change_callback:
                self.on_change_callback()
        self.refresh()

    def _on_click_unequip(self) -> None:
        if self._read_only():
            return
        success, msg = self.session.unequip(self.target_slot)
        self._show_status(msg, is_error=not success)
        if success:
            if self.combat and hasattr(self.combat, "sync_with_rpg_session"):
                self.combat.sync_with_rpg_session()
            if self.on_change_callback:
                self.on_change_callback()
        self.refresh()

    def _on_click_lock_toggle(self) -> None:
        if self._read_only():
            return
        if not self.selected_uid or not self.session.profile:
            return
        item = self.session.profile.items.get(self.selected_uid)
        if not item:
            return
        new_lock = not item.locked
        success, msg = self.session.set_locked(self.selected_uid, new_lock)
        self._show_status(msg, is_error=not success)
        self.refresh()

    def _show_status(self, msg: str, is_error: bool = False) -> None:
        if hasattr(self, "lbl_status_msg") and self.lbl_status_msg:
            self.lbl_status_msg.setText(msg)
            col = (1.0, 0.4, 0.4, 1.0) if is_error else (0.4, 1.0, 0.5, 1.0)
            self.lbl_status_msg.setFg(col)

    def _read_only(self) -> bool:
        if getattr(getattr(self.combat, 'base', None), 'is_test_mode', False):
            self._show_status('사격장에서는 영구 장비를 변경할 수 없습니다.', is_error=True)
            return True
        return False
