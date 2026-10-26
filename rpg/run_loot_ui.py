"""In-run loot inspection UI panel embedded within the tactical inventory modal."""

from __future__ import annotations

from typing import Any, Callable, Mapping

try:
    from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
    from direct.gui.OnscreenText import OnscreenText
    from panda3d.core import LColor, TextNode, TransparencyAttrib
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

from rpg.equipment_ui import AFFIX_NAMES, RARITY_COLORS, RARITY_NAMES
from rpg.items import ItemInstance
from rpg.loot_world import get_item_name
from rpg.run_loot import RunLootBag


class RunLootUIPanel:
    """Read-only inspection panel for unextracted in-run loot in the inventory modal."""

    ITEMS_PER_PAGE = 7

    def __init__(
        self,
        parent_node: Any,
        run_loot_bag: RunLootBag | None = None,
        catalog: Mapping[str, Any] | None = None,
        font_kw: dict[str, Any] | None = None,
        btn_font_kw: dict[str, Any] | None = None,
    ) -> None:
        self.parent_node = parent_node
        self.run_loot_bag = run_loot_bag
        self.catalog = catalog
        self.font_kw = font_kw or {}
        self.btn_font_kw = btn_font_kw or {}

        self.current_page = 0
        self.selected_uid: str | None = None

        self.frame: Any = None
        self.item_rows: list[Any] = []
        self._build_ui()

    def _build_ui(self) -> None:
        if not HAS_PANDA3D or self.parent_node is None:
            return

        self.frame = DirectFrame(
            parent=self.parent_node,
            relief=None,
            frameSize=(-1.60, 1.60, -0.80, 0.72),
            pos=(0, 0, 0),
        )

        # Top notice banner
        self.lbl_bag_status = OnscreenText(
            parent=self.frame,
            text="[ 이번 탐험 미확보 전리품 가방 : 0 / 24 ]",
            pos=(-1.40, 0.54),
            scale=0.038,
            fg=(1.0, 0.90, 0.35, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_rule_notice = OnscreenText(
            parent=self.frame,
            text="* 미확보 전리품은 탈출 성공 시 영구 확보됩니다. 탐험 중 사망 또는 중도 포기 시 모두 소실됩니다.",
            pos=(-1.40, 0.48),
            scale=0.024,
            fg=(1.0, 0.45, 0.45, 0.95),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.capacity_track = DirectFrame(
            parent=self.frame, relief=DGG.FLAT, frameColor=(.15, .19, .24, 1),
            frameSize=(0, .55, -.012, .012), pos=(.85, 0, .55))
        self.capacity_fill = DirectFrame(
            parent=self.capacity_track, relief=DGG.FLAT, frameColor=(.35, .85, 1, 1),
            frameSize=(0, .55, -.012, .012))

        # Distinct Card Backgrounds for Left and Right Columns
        self.frame_loot_left = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.60, 0.60, -0.56, 0.52),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(-0.84, 0, -0.06),
        )
        DirectFrame(
            parent=self.frame_loot_left,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.56, 0.56, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.48),
        )
        self.frame_loot_right = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.60, 0.60, -0.56, 0.52),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(0.84, 0, -0.06),
        )
        DirectFrame(
            parent=self.frame_loot_right,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.56, 0.56, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.48),
        )

        # -------------------------------------------------------------
        # Left Side: In-run Items List
        # -------------------------------------------------------------
        self.lbl_inv_title = OnscreenText(
            text="■ 획득 전리품 목록 (읽기 전용)",
            parent=self.frame,
            pos=(-1.40, 0.44),
            scale=0.034,
            fg=(0.40, 0.90, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_empty_msg = OnscreenText(
            parent=self.frame,
            text="이번 탐험에서 획득한 전리품이 없습니다.\n적을 처치하고 바닥의 전리품을 [E] 키로 수집하세요.",
            pos=(-0.84, 0.0),
            scale=0.030,
            fg=(0.7, 0.7, 0.7, 0.8),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        # Pre-instantiate item row buttons
        self.item_rows = []
        for i in range(self.ITEMS_PER_PAGE):
            y_pos = 0.36 - (i * 0.10)
            btn = DirectButton(
                parent=self.frame,
                relief=None,
                frameSize=(-0.56, 0.56, -0.042, 0.042),
                pos=(-0.84, 0, y_pos),
                text="",
                text_scale=0.028,
                text_pos=(-0.52, -0.01),
                text_align=TextNode.ALeft if TextNode else 0,
                text_fg=(0.9, 0.9, 0.9, 1.0),
                command=self._select_item_row,
                extraArgs=[i],
                **self.btn_font_kw,
            )
            btn.hide()
            self.item_rows.append(btn)

        # Pagination controls
        self.btn_prev_page = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.16, 0.16, -0.04, 0.04),
            pos=(-1.12, 0, -0.42),
            text="[ ◀ 이전 ]",
            text_scale=0.028,
            text_pos=(0, -0.01),
            text_fg=(0.8, 0.9, 1.0, 1.0),
            command=self._prev_page,
            **self.btn_font_kw,
        )
        self.lbl_page_info = OnscreenText(
            parent=self.frame,
            text="1 / 1",
            pos=(-0.84, -0.43),
            scale=0.028,
            fg=(0.9, 0.9, 0.9, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )
        self.btn_next_page = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.16, 0.16, -0.04, 0.04),
            pos=(-0.56, 0, -0.42),
            text="[ 다음 ▶ ]",
            text_scale=0.028,
            text_pos=(0, -0.01),
            text_fg=(0.8, 0.9, 1.0, 1.0),
            command=self._next_page,
            **self.btn_font_kw,
        )

        # -------------------------------------------------------------
        # Right Side: Detailed Item Card (Read-Only)
        # -------------------------------------------------------------
        self.lbl_detail_title = OnscreenText(
            text="■ 전리품 상세 정보 (미확보)",
            parent=self.frame,
            pos=(0.04, 0.44),
            scale=0.034,
            fg=(0.40, 0.90, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_detail_rarity = OnscreenText(
            parent=self.frame,
            text="[ 전리품 상세 정보 ]",
            pos=(0.04, 0.36),
            scale=0.030,
            fg=(0.4, 0.9, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_detail_name = OnscreenText(
            parent=self.frame,
            text="아이템을 선택하세요",
            pos=(0.04, 0.28),
            scale=0.040,
            fg=(1.0, 1.0, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_detail_meta = OnscreenText(
            parent=self.frame,
            text="",
            pos=(0.04, 0.20),
            scale=0.028,
            fg=(0.7, 0.8, 0.9, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_detail_affixes = OnscreenText(
            parent=self.frame,
            text="",
            pos=(0.04, 0.12),
            scale=0.027,
            fg=(0.35, 0.95, 0.55, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_detail_guide = OnscreenText(
            parent=self.frame,
            text="",
            pos=(0.04, -0.16),
            scale=0.024,
            fg=(0.80, 0.85, 0.90, 0.9),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        # Disabled Action Button
        self.btn_equip_disabled = DirectButton(
            parent=self.frame,
            relief=None,
            frameSize=(-0.45, 0.45, -0.052, 0.052),
            pos=(0.48, 0, -0.42),
            text="[ 탈출 후 영구 소유 및 장착 가능 ]",
            text_scale=0.028,
            text_pos=(0, -0.009),
            text_fg=(0.60, 0.65, 0.70, 0.8),
            state=DGG.DISABLED,
            **self.btn_font_kw,
        )

        self.hide()

    def show(self) -> None:
        if self.frame:
            self.frame.show()
            self.refresh()

    def hide(self) -> None:
        if self.frame:
            self.frame.hide()

    def set_run_loot_bag(self, bag: RunLootBag | None) -> None:
        self.run_loot_bag = bag
        self.refresh()

    def refresh(self) -> None:
        if not HAS_PANDA3D or self.frame is None:
            return

        bag = self.run_loot_bag
        items = bag.pending_items if bag else []
        count = len(items)
        capacity = bag.capacity if bag else 24

        # Update header with visual capacity progress bar
        self.capacity_fill.setSx(max(0, min(1, count / capacity)) if capacity else 0)
        self.capacity_fill['frameColor'] = (1, .35, .35, 1) if count >= capacity else (.35, .85, 1, 1)
        if count >= capacity:
            self.lbl_bag_status.setText(f"[ 가방 가득참 : {count} / {capacity} ]")
            self.lbl_bag_status.setFg((1.0, 0.35, 0.35, 1.0))
            self.lbl_rule_notice.setText("* 가방이 가득 찼습니다! 탈출 관문을 가동하여 전리품을 안전하게 확보하세요.")
        elif count > 0:
            self.lbl_bag_status.setText(f"[ 이번 탐험 미확보 전리품 가방 : {count} / {capacity} ]")
            self.lbl_bag_status.setFg((1.0, 0.90, 0.35, 1.0))
            self.lbl_rule_notice.setText("* 미확보 전리품은 탈출 성공 시 영구 확보됩니다. 탐험 중 사망 또는 중도 포기 시 모두 소실됩니다.")
        else:
            self.lbl_bag_status.setText(f"[ 이번 탐험 미확보 전리품 가방 : 0 / {capacity} ]")
            self.lbl_bag_status.setFg((0.75, 0.75, 0.80, 1.0))
            self.lbl_rule_notice.setText("* 미확보 전리품은 탈출 성공 시 영구 확보됩니다. 탐험 중 사망 또는 중도 포기 시 모두 소실됩니다.")

        if not items:
            self.lbl_empty_msg.show()
            for btn in self.item_rows:
                btn.hide()
            self.btn_prev_page.hide()
            self.btn_next_page.hide()
            self.lbl_page_info.hide()
            self._clear_detail()
            return

        self.lbl_empty_msg.hide()
        self.btn_prev_page.show()
        self.btn_next_page.show()
        self.lbl_page_info.show()

        total_pages = max(1, (count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
        if self.current_page < 0:
            self.current_page = 0

        self.lbl_page_info.setText(f"{self.current_page + 1} / {total_pages}")

        start_idx = self.current_page * self.ITEMS_PER_PAGE
        page_items = items[start_idx : start_idx + self.ITEMS_PER_PAGE]

        # Check if selected UID is still valid
        if self.selected_uid and not any(it.uid == self.selected_uid for it in items):
            self.selected_uid = None

        if not self.selected_uid and page_items:
            self.selected_uid = page_items[0].uid

        for i in range(self.ITEMS_PER_PAGE):
            btn = self.item_rows[i]
            if i < len(page_items):
                it = page_items[i]
                rarity_ko = RARITY_NAMES.get(it.rarity, "일반")
                rarity_col = RARITY_COLORS.get(it.rarity, (0.85, 0.85, 0.85, 1.0))
                is_selected = it.uid == self.selected_uid

                prefix = "▶ " if is_selected else "  "
                qty_str = f" x{it.quantity}" if it.quantity > 1 else ""
                aff_tag = f" ({len(it.affixes)}옵션)" if it.affixes else ""
                name = get_item_name(it, self.catalog)
                btn["text"] = f"{prefix}[{rarity_ko}] {name}{qty_str}{aff_tag}"
                btn["text_fg"] = (1.0, 1.0, 0.3, 1.0) if is_selected else rarity_col
                if is_selected:
                    btn["frameColor"] = (0.18, 0.25, 0.35, 0.98)
                    btn["borderWidth"] = (0.004, 0.004)
                else:
                    btn["frameColor"] = (0.09, 0.11, 0.16, 0.90) if (i % 2 == 0) else (0.11, 0.14, 0.20, 0.90)
                    btn["borderWidth"] = (0.002, 0.002)
                btn.show()
            else:
                btn.hide()

        self._update_detail()

    def _select_item_row(self, row_idx: int) -> None:
        if not self.run_loot_bag:
            return
        items = self.run_loot_bag.pending_items
        start_idx = self.current_page * self.ITEMS_PER_PAGE
        target_idx = start_idx + row_idx
        if 0 <= target_idx < len(items):
            self.selected_uid = items[target_idx].uid
            self.refresh()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh()

    def _next_page(self) -> None:
        if not self.run_loot_bag:
            return
        total_pages = max(1, (len(self.run_loot_bag.pending_items) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.refresh()

    def _clear_detail(self) -> None:
        self.lbl_detail_rarity.setText("[ 전리품 상세 정보 ]")
        self.lbl_detail_name.setText("선택된 아이템 없음")
        self.lbl_detail_name.setFg((0.6, 0.6, 0.6, 1.0))
        self.lbl_detail_meta.setText("")
        self.lbl_detail_affixes.setText("")
        self.lbl_detail_guide.setText("")

    def _update_detail(self) -> None:
        if not self.run_loot_bag or not self.selected_uid:
            self._clear_detail()
            return

        selected_item = next(
            (it for it in self.run_loot_bag.pending_items if it.uid == self.selected_uid), None
        )
        if not selected_item:
            self._clear_detail()
            return

        it = selected_item
        rarity_ko = RARITY_NAMES.get(it.rarity, "일반")
        rarity_col = RARITY_COLORS.get(it.rarity, (0.85, 0.85, 0.85, 1.0))
        name = get_item_name(it, self.catalog)

        self.lbl_detail_rarity.setText(f"[ {rarity_ko} 등급 전리품 ]")
        self.lbl_detail_rarity.setFg(rarity_col)

        qty_str = f" x{it.quantity}개" if it.quantity > 1 else ""
        self.lbl_detail_name.setText(f"{name}{qty_str}")
        self.lbl_detail_name.setFg(rarity_col)

        is_weapon = it.definition_id.startswith("weapon_")
        cat_str = "무기 장비" if is_weapon else "제작/강화 재료"
        self.lbl_detail_meta.setText(f"분류: {cat_str}  |  아이템 레벨: Lv.{it.item_level}  |  상태: [미확보]")

        if it.affixes:
            lines = ["◆ 부여된 추가 무작위 옵션:"]
            for aff in it.affixes:
                name_ko = AFFIX_NAMES.get(aff.id, aff.id)
                diff = aff.value - 1.0
                sign = "+" if diff >= 0 else ""
                lines.append(f"  • {name_ko}: {sign}{diff * 100:.1f}% (계수: x{aff.value:.3f})")
            self.lbl_detail_affixes.setText("\n".join(lines))
        else:
            self.lbl_detail_affixes.setText("◆ 추가 옵션 없음 (기본 사양)")

        if is_weapon:
            self.lbl_detail_guide.setText(
                "이번 탐험에서 획득한 미확보 상태의 무기 장비입니다.\n"
                "탈출 관문을 활성화하여 작전을 성공적으로 완료하면\n"
                "영구 무기/장비 보관함으로 이관되어 장착할 수 있습니다."
            )
        else:
            self.lbl_detail_guide.setText(
                "이번 탐험에서 획득한 미확보 상태의 제작/강화 재료입니다.\n"
                "★ 탈출로 확보 후 작업대에서 사용 가능합니다.\n"
                "(작업대 강화 시 무기 기본 공격력 또는 약점 배율 강화에 소모됩니다)"
            )

