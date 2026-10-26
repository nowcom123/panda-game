"""Tactical weapon workshop UI panel for deterministic weapon upgrades."""

from __future__ import annotations

import copy
from typing import Any, Callable

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

from rpg.equipment_ui import AFFIX_NAMES, RARITY_COLORS, RARITY_NAMES, RARITY_ORDER
from rpg.items import ItemAffix, ValidationError
from rpg.session import RPGSession
from rpg.weapon_stats import resolve_weapon_config
from rpg.workshop import RECIPES, material_count
from combat.weapon_config import WEAPON_CONFIGS


class WorkshopUIPanel:
    """3-column Tactical Weapon Workshop panel embedded in the tactical inventory modal.
    - Top Banner: Scrap metal and bone fragment total and usable stock badges
    - Left Column: Owned permanent weapons list with slot/lock indicators and pagination
    - Center Column: 2 Deterministic Upgrade Recipe Cards (reinforce & weakpoint)
    - Right Column: Clear preview card (before -> after stats, cost, execution button)
    """

    ITEMS_PER_PAGE = 7

    def __init__(
        self,
        parent_node: Any,
        session: RPGSession | None = None,
        game: Any = None,
        on_change_callback: Callable[[], None] | None = None,
        font_kw: dict[str, Any] | None = None,
        btn_font_kw: dict[str, Any] | None = None,
    ) -> None:
        self.parent_node = parent_node
        self.session = session
        self.game = game
        self.on_change_callback = on_change_callback
        self.font_kw = font_kw or {}
        self.btn_font_kw = btn_font_kw or {}

        self.current_page = 0
        self.selected_uid: str | None = None
        self.selected_recipe: str = "reinforce"
        self.status_msg: str = ""
        self.status_is_error: bool = False

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

        # -------------------------------------------------------------
        # Top Banner: Material Stock Badges Bar
        # -------------------------------------------------------------
        self.frame_mat_bar = DirectFrame(
            parent=self.frame,
            frameColor=(0.05, 0.07, 0.10, 0.95),
            frameSize=(-1.46, 1.46, -0.038, 0.038),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, 0.54),
        )

        self.lbl_mat_scrap = OnscreenText(
            parent=self.frame_mat_bar,
            text="[ 고철 ]  총 0개 (사용 가능 0개 / 잠김 0개)",
            pos=(-0.72, -0.010),
            scale=0.030,
            fg=(0.95, 0.85, 0.35, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_mat_bone = OnscreenText(
            parent=self.frame_mat_bar,
            text="[ 뼈 파편 ]  총 0개 (사용 가능 0개 / 잠김 0개)",
            pos=(0.72, -0.010),
            scale=0.030,
            fg=(0.80, 0.90, 1.0, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        # -------------------------------------------------------------
        # Left Column: Permanent Weapon List
        # -------------------------------------------------------------
        self.frame_left = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.45, 0.45, -0.58, 0.58),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(-0.98, 0, -0.16),
        )

        self.lbl_left_title = OnscreenText(
            parent=self.frame_left,
            text="■ 영구 보관 무기 목록",
            pos=(-0.40, 0.50),
            scale=0.030,
            fg=(0.35, 0.95, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_left_sub = OnscreenText(
            parent=self.frame_left,
            text="* 강화할 무기를 선택하세요 (잠금 해제 필수)",
            pos=(-0.40, 0.44),
            scale=0.030,
            fg=(0.70, 0.75, 0.82, 0.90),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # Divider line
        DirectFrame(
            parent=self.frame_left,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.41, 0.41, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.41),
        )

        self.lbl_empty_weapons = OnscreenText(
            parent=self.frame_left,
            text="강화 가능한 영구 무기가 없습니다.\n탈출 성공 시 획득한 무기가 보관됩니다.",
            pos=(0, 0.10),
            scale=0.030,
            fg=(0.7, 0.7, 0.7, 0.8),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.item_rows = []
        for i in range(self.ITEMS_PER_PAGE):
            y_pos = 0.33 - (i * 0.102)
            btn = DirectButton(
                parent=self.frame_left,
                relief=DGG.RIDGE if DGG else None,
                borderWidth=(0.003, 0.003),
                frameColor=(0.10, 0.13, 0.18, 0.90),
                frameSize=(-0.41, 0.41, -0.040, 0.040),
                pos=(0, 0, y_pos),
                text="",
                text_scale=0.030,
                text_pos=(-0.38, -0.008),
                text_align=TextNode.ALeft if TextNode else 0,
                text_fg=(0.9, 0.9, 0.9, 1.0),
                command=self._select_weapon_row,
                extraArgs=[i],
                **self.btn_font_kw,
            )
            btn.hide()
            self.item_rows.append(btn)

        # Pagination controls
        self.btn_prev_page = DirectButton(
            parent=self.frame_left,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.12, 0.16, 0.22, 0.90),
            frameSize=(-0.10, 0.10, -0.030, 0.030),
            pos=(-0.25, 0, -0.49),
            text="◀ 이전",
            text_scale=0.030,
            text_pos=(0, -0.007),
            text_fg=(0.85, 0.90, 0.95, 1.0),
            command=self._prev_page,
            **self.btn_font_kw,
        )

        self.lbl_page_info = OnscreenText(
            parent=self.frame_left,
            text="1 / 1",
            pos=(0.0, -0.498),
            scale=0.030,
            fg=(0.85, 0.90, 0.95, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.btn_next_page = DirectButton(
            parent=self.frame_left,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.12, 0.16, 0.22, 0.90),
            frameSize=(-0.10, 0.10, -0.030, 0.030),
            pos=(0.25, 0, -0.49),
            text="다음 ▶",
            text_scale=0.030,
            text_pos=(0, -0.007),
            text_fg=(0.85, 0.90, 0.95, 1.0),
            command=self._next_page,
            **self.btn_font_kw,
        )

        # -------------------------------------------------------------
        # Center Column: 2 Deterministic Upgrade Recipe Cards
        # -------------------------------------------------------------
        self.frame_center = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.45, 0.45, -0.58, 0.58),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(0.0, 0, -0.16),
        )

        self.lbl_center_title = OnscreenText(
            parent=self.frame_center,
            text="■ 강화 방식 선택 (2종)",
            pos=(-0.40, 0.50),
            scale=0.030,
            fg=(1.0, 0.85, 0.35, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_center_sub = OnscreenText(
            parent=self.frame_center,
            text="확보한 재료로 강화 · 실패 확률 없음",
            pos=(-0.40, 0.44),
            scale=0.030,
            fg=(0.70, 0.75, 0.82, 0.90),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # Divider line
        DirectFrame(
            parent=self.frame_center,
            frameColor=(0.20, 0.30, 0.42, 0.8),
            frameSize=(-0.41, 0.41, -0.002, 0.002),
            relief=DGG.FLAT if DGG else None,
            pos=(0, 0, 0.41),
        )

        # Recipe Card 1: reinforce
        self.card_reinforce = DirectFrame(
            parent=self.frame_center,
            frameColor=(0.10, 0.13, 0.19, 0.95),
            frameSize=(-0.41, 0.41, -0.19, 0.19),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(0, 0, 0.18),
        )

        self.lbl_rf_icon = OnscreenText(
            parent=self.card_reinforce,
            text="[ 1. 총열 보강 ]",
            pos=(-0.37, 0.12),
            scale=0.030,
            fg=(0.95, 0.85, 0.35, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_rf_desc = OnscreenText(
            parent=self.card_reinforce,
            text=f"공격력 보너스 +{RECIPES['reinforce'].increment*100:g}%p\n최대 +{(RECIPES['reinforce'].cap-1)*100:g}%\n비용: 고철 {RECIPES['reinforce'].cost}개",
            pos=(-0.37, 0.05),
            scale=0.030,
            fg=(0.85, 0.88, 0.92, 0.95),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_rf_status = OnscreenText(
            parent=self.card_reinforce,
            text="",
            pos=(-0.37, -0.08),
            scale=0.030,
            fg=(0.4, 0.9, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.btn_select_rf = DirectButton(
            parent=self.card_reinforce,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.15, 0.28, 0.38, 0.95),
            frameSize=(-0.37, 0.37, -0.032, 0.032),
            pos=(0, 0, -0.14),
            text="[ ★ 총열 보강 선택됨 ]",
            text_scale=0.030,
            text_pos=(0, -0.007),
            text_fg=(0.35, 0.95, 1.0, 1.0),
            command=self._select_recipe,
            extraArgs=["reinforce"],
            **self.btn_font_kw,
        )

        # Recipe Card 2: weakpoint
        self.card_weakpoint = DirectFrame(
            parent=self.frame_center,
            frameColor=(0.10, 0.13, 0.19, 0.95),
            frameSize=(-0.41, 0.41, -0.19, 0.19),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(0, 0, -0.24),
        )

        self.lbl_wp_icon = OnscreenText(
            parent=self.card_weakpoint,
            text="[ 2. 약점 각인 ]",
            pos=(-0.37, 0.12),
            scale=0.030,
            fg=(0.80, 0.90, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_wp_desc = OnscreenText(
            parent=self.card_weakpoint,
            text=f"약점 피해 보너스 +{RECIPES['weakpoint'].increment*100:g}%p\n최대 +{(RECIPES['weakpoint'].cap-1)*100:g}%\n비용: 뼈 파편 {RECIPES['weakpoint'].cost}개",
            pos=(-0.37, 0.05),
            scale=0.030,
            fg=(0.85, 0.88, 0.92, 0.95),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        self.lbl_wp_status = OnscreenText(
            parent=self.card_weakpoint,
            text="",
            pos=(-0.37, -0.08),
            scale=0.030,
            fg=(0.4, 0.9, 1.0, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.btn_select_wp = DirectButton(
            parent=self.card_weakpoint,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.15, 0.20, 0.28, 0.95),
            frameSize=(-0.37, 0.37, -0.032, 0.032),
            pos=(0, 0, -0.14),
            text="[ 약점 각인 선택 ]",
            text_scale=0.030,
            text_pos=(0, -0.007),
            text_fg=(0.75, 0.80, 0.85, 1.0),
            command=self._select_recipe,
            extraArgs=["weakpoint"],
            **self.btn_font_kw,
        )

        # -------------------------------------------------------------
        # Right Column: Detailed Preview & Upgrade Execution Card
        # -------------------------------------------------------------
        self.frame_right = DirectFrame(
            parent=self.frame,
            frameColor=(0.06, 0.08, 0.12, 0.95),
            frameSize=(-0.45, 0.45, -0.58, 0.58),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            pos=(0.98, 0, -0.16),
        )

        self.lbl_right_title = OnscreenText(
            parent=self.frame_right,
            text="■ 강화 결과 미리보기 및 실행",
            pos=(-0.40, 0.50),
            scale=0.030,
            fg=(0.35, 1.0, 0.65, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            **self.font_kw,
        )

        # Selected weapon header box
        self.box_sel_hdr = DirectFrame(
            parent=self.frame_right,
            frameColor=(0.10, 0.14, 0.20, 0.95),
            frameSize=(-0.41, 0.41, -0.065, 0.065),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, 0.42),
        )

        self.lbl_target_weapon_name = OnscreenText(
            parent=self.box_sel_hdr,
            text="선택된 무기 없음",
            pos=(0, 0.016),
            scale=0.030,
            fg=(1.0, 1.0, 1.0, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            wordwrap=26,
            **self.font_kw,
        )

        # Stats preview text block
        self.lbl_preview_stats = OnscreenText(
            parent=self.frame_right,
            text="",
            pos=(-0.40, 0.29),
            scale=0.030,
            fg=(0.88, 0.92, 0.96, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            wordwrap=26,
            **self.font_kw,
        )

        # Material cost info box
        self.box_cost = DirectFrame(
            parent=self.frame_right,
            frameColor=(0.10, 0.13, 0.18, 0.95),
            frameSize=(-0.41, 0.41, -0.048, 0.048),
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, -0.16),
        )

        self.lbl_cost_info = OnscreenText(
            parent=self.box_cost,
            text="소모 재료 정보",
            pos=(-0.37, 0.015),
            scale=0.030,
            fg=(1.0, 0.88, 0.35, 1.0),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        self.lbl_cost_detail = OnscreenText(
            parent=self.box_cost,
            text="사용 가능: 0개 / 소모 후 잔여: 0개",
            pos=(-0.37, -0.025),
            scale=0.030,
            fg=(0.80, 0.85, 0.90, 0.90),
            align=TextNode.ALeft if TextNode else 0,
            mayChange=True,
            **self.font_kw,
        )

        # Execution Button
        self.btn_upgrade_execute = DirectButton(
            parent=self.frame_right,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.12, 0.28, 0.20, 0.95),
            frameSize=(-0.41, 0.41, -0.045, 0.045),
            pos=(0, 0, -0.28),
            text="[ 선택 무기 강화 실행 ]",
            text_scale=0.030,
            text_pos=(0, -0.009),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self._on_click_upgrade,
            **self.btn_font_kw,
        )

        # Disabled reason / Status message
        self.lbl_fail_reason = OnscreenText(
            parent=self.frame_right,
            text="",
            pos=(0, -0.36),
            scale=0.030,
            fg=(1.0, 0.40, 0.40, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            wordwrap=26,
            **self.font_kw,
        )

        self.lbl_feedback = OnscreenText(
            parent=self.frame_right,
            text="",
            pos=(0, -0.44),
            scale=0.030,
            fg=(0.35, 1.0, 0.55, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            wordwrap=26,
            **self.font_kw,
        )

    def show(self) -> None:
        if self.frame:
            self.frame.show()
            self.refresh()

    def hide(self) -> None:
        if self.frame:
            self.frame.hide()

    def is_hidden(self) -> bool:
        return self.frame is None or self.frame.isHidden()

    def _select_weapon_row(self, row_idx: int) -> None:
        weapons = self._get_weapons()
        start_idx = self.current_page * self.ITEMS_PER_PAGE
        idx = start_idx + row_idx
        if 0 <= idx < len(weapons):
            self.selected_uid = weapons[idx].uid
            self.status_msg = ""
            self.refresh()

    def _select_recipe(self, recipe_id: str) -> None:
        if recipe_id in RECIPES:
            self.selected_recipe = recipe_id
            self.status_msg = ""
            self.refresh()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh()

    def _next_page(self) -> None:
        weapons = self._get_weapons()
        max_pages = max(1, (len(weapons) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        if self.current_page < max_pages - 1:
            self.current_page += 1
            self.refresh()

    def _get_weapons(self) -> list[Any]:
        if not self.session or not self.session.profile:
            return []
        cat = self.session.catalog
        items = [
            it for it in self.session.profile.items.values()
            if cat.get(it.definition_id) and cat[it.definition_id].kind == "weapon"
        ]
        # Sort by rarity (legendary first), then item level desc, then UID
        items.sort(key=lambda it: (RARITY_ORDER.get(it.rarity, 99), -it.item_level, it.uid))
        return items

    def refresh(self) -> None:
        self._displayed_quote = None
        if not HAS_PANDA3D or self.frame is None:
            return

        prof = self.session.profile if (self.session and self.session.is_valid) else None
        cat = self.session.catalog if self.session else {}

        # -------------------------------------------------------------
        # 1. Update Material Stock Badges Bar
        # -------------------------------------------------------------
        if prof:
            total_scrap = sum(it.quantity for it in prof.items.values() if it.definition_id == "scrap_metal")
            usable_scrap = material_count(prof, "scrap_metal")
            locked_scrap = total_scrap - usable_scrap

            total_bone = sum(it.quantity for it in prof.items.values() if it.definition_id == "bone_fragment")
            usable_bone = material_count(prof, "bone_fragment")
            locked_bone = total_bone - usable_bone
        else:
            total_scrap = usable_scrap = locked_scrap = 0
            total_bone = usable_bone = locked_bone = 0

        self.lbl_mat_scrap.setText(
            f"[ 고철 ]  총 {total_scrap}개 (사용 가능 {usable_scrap}개 / 잠김 {locked_scrap}개)"
        )
        self.lbl_mat_bone.setText(
            f"[ 뼈 파편 ]  총 {total_bone}개 (사용 가능 {usable_bone}개 / 잠김 {locked_bone}개)"
        )

        # -------------------------------------------------------------
        # 2. Update Weapons List
        # -------------------------------------------------------------
        weapons = self._get_weapons()
        p_uid = prof.equipment.get("primary") if prof else None
        s_uid = prof.equipment.get("secondary") if prof else None

        if not weapons:
            self.lbl_empty_weapons.show()
            for btn in self.item_rows:
                btn.hide()
            self.btn_prev_page.hide()
            self.btn_next_page.hide()
            self.lbl_page_info.hide()
            self.selected_uid = None
        else:
            self.lbl_empty_weapons.hide()
            self.btn_prev_page.show()
            self.btn_next_page.show()
            self.lbl_page_info.show()

            if not self.selected_uid or not any(w.uid == self.selected_uid for w in weapons):
                self.selected_uid = weapons[0].uid

            max_pages = max(1, (len(weapons) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
            self.current_page = max(0, min(self.current_page, max_pages - 1))
            self.lbl_page_info.setText(f"{self.current_page + 1} / {max_pages}")

            start_idx = self.current_page * self.ITEMS_PER_PAGE
            for i in range(self.ITEMS_PER_PAGE):
                btn = self.item_rows[i]
                idx = start_idx + i
                if idx < len(weapons):
                    w = weapons[idx]
                    defn = cat.get(w.definition_id)
                    d_name = defn.name if defn else "알 수 없음"
                    if len(d_name) > 11:
                        d_name = d_name[:10] + ".."
                    r_name = RARITY_NAMES.get(w.rarity, w.rarity)

                    equip_tag = ""
                    if w.uid == p_uid:
                        equip_tag = " [주]"
                    elif w.uid == s_uid:
                        equip_tag = " [보조]"

                    lock_tag = " 🔒" if w.locked else ""
                    is_sel = (w.uid == self.selected_uid)
                    sel_tag = "▶ " if is_sel else "   "

                    btn["text"] = f"{sel_tag}[{r_name}] {d_name} Lv.{w.item_level}{equip_tag}{lock_tag}"
                    btn["text_fg"] = (1.0, 1.0, 0.4, 1.0) if is_sel else RARITY_COLORS.get(w.rarity, (0.85, 0.85, 0.85, 1.0))
                    if is_sel:
                        btn["frameColor"] = (0.16, 0.24, 0.32, 0.95)
                    else:
                        btn["frameColor"] = (0.10, 0.13, 0.18, 0.90)
                    btn.show()
                else:
                    btn.hide()

        # -------------------------------------------------------------
        # 3. Update Recipe Cards Selection State
        # -------------------------------------------------------------
        rf_recipe = RECIPES.get("reinforce")
        wp_recipe = RECIPES.get("weakpoint")

        sel_item = prof.items.get(self.selected_uid) if (prof and self.selected_uid) else None

        if self.selected_recipe == "reinforce":
            self.card_reinforce["frameColor"] = (0.12, 0.18, 0.26, 0.98)
            self.btn_select_rf["text"] = "[ ★ 총열 보강 선택됨 ]"
            self.btn_select_rf["text_fg"] = (0.35, 0.95, 1.0, 1.0)
            self.btn_select_rf["frameColor"] = (0.18, 0.32, 0.44, 0.95)

            self.card_weakpoint["frameColor"] = (0.09, 0.11, 0.16, 0.90)
            self.btn_select_wp["text"] = "[ 약점 각인 선택 ]"
            self.btn_select_wp["text_fg"] = (0.70, 0.75, 0.80, 1.0)
            self.btn_select_wp["frameColor"] = (0.12, 0.16, 0.22, 0.90)
        else:
            self.card_reinforce["frameColor"] = (0.09, 0.11, 0.16, 0.90)
            self.btn_select_rf["text"] = "[ 총열 보강 선택 ]"
            self.btn_select_rf["text_fg"] = (0.70, 0.75, 0.80, 1.0)
            self.btn_select_rf["frameColor"] = (0.12, 0.16, 0.22, 0.90)

            self.card_weakpoint["frameColor"] = (0.12, 0.18, 0.26, 0.98)
            self.btn_select_wp["text"] = "[ ★ 약점 각인 선택됨 ]"
            self.btn_select_wp["text_fg"] = (0.35, 0.95, 1.0, 1.0)
            self.btn_select_wp["frameColor"] = (0.18, 0.32, 0.44, 0.95)

        # Show current weapon cap/status under each recipe card
        if sel_item and rf_recipe and wp_recipe:
            rf_val = next((a.value for a in sel_item.affixes if a.id == rf_recipe.affix_id), 1.0)
            wp_val = next((a.value for a in sel_item.affixes if a.id == wp_recipe.affix_id), 1.0)

            rf_cap_tag = " [상한 도달]" if rf_val >= rf_recipe.cap - 1e-9 else f" (+{(rf_val - 1.0)*100:.0f}%p / 최대 +30%p)"
            self.lbl_rf_status.setText(f"현재 +{(rf_val-1)*100:.0f}% / 상한 +{(rf_recipe.cap-1)*100:.0f}%")

            wp_cap_tag = " [상한 도달]" if wp_val >= wp_recipe.cap - 1e-9 else f" (+{(wp_val - 1.0)*100:.0f}%p / 최대 +50%p)"
            self.lbl_wp_status.setText(f"현재 +{(wp_val-1)*100:.0f}% / 상한 +{(wp_recipe.cap-1)*100:.0f}%")
        else:
            self.lbl_rf_status.setText(f"가용 고철: {usable_scrap}개 (8개 소모)")
            self.lbl_wp_status.setText(f"가용 뼈 파편: {usable_bone}개 (6개 소모)")

        # -------------------------------------------------------------
        # 4. Update Right Column: Preview & Action
        # -------------------------------------------------------------
        if not sel_item:
            self.lbl_target_weapon_name.setText("무기를 선택하세요.")
            self.lbl_target_weapon_name.setFg((0.7, 0.7, 0.7, 1.0))
            self.lbl_preview_stats.setText("왼쪽 목록에서 강화할 무기를 선택하세요.")
            self.lbl_cost_info.setText("소모 재료 정보 없음")
            self.lbl_cost_detail.setText("")
            self.btn_upgrade_execute["state"] = DGG.DISABLED if DGG else "disabled"
            self.btn_upgrade_execute["text_fg"] = (0.50, 0.55, 0.60, 1.0)
            self.lbl_fail_reason.setText("")
            self.lbl_feedback.setText("")
            return

        recipe = RECIPES.get(self.selected_recipe)
        if not recipe:
            return

        defn = cat.get(sel_item.definition_id)
        w_name = defn.name if defn else "알 수 없음"
        r_name = RARITY_NAMES.get(sel_item.rarity, sel_item.rarity)
        r_col = RARITY_COLORS.get(sel_item.rarity, (1, 1, 1, 1))

        slot_tag = "보관함"
        if sel_item.uid == p_uid:
            slot_tag = "주 무기 장착 중"
        elif sel_item.uid == s_uid:
            slot_tag = "보조 무기 장착 중"

        lock_tag = "잠김" if sel_item.locked else "잠금 해제"
        self.lbl_target_weapon_name.setText(
            f"{w_name}\n[{r_name}] Lv.{sel_item.item_level} | {slot_tag} | {lock_tag}"
        )
        self.lbl_target_weapon_name.setFg(r_col)

        # Before stats
        try:
            cur_cfg = resolve_weapon_config(WEAPON_CONFIGS, cat, sel_item)
        except Exception:
            cur_cfg = None

        cur_affix_val = next((a.value for a in sel_item.affixes if a.id == recipe.affix_id), 1.0)
        next_affix_val = round(max(cur_affix_val, min(recipe.cap, cur_affix_val + recipe.increment)), 6)

        # Simulated after item
        sim_item = copy.deepcopy(sel_item)
        sim_item.affixes = [a for a in sim_item.affixes if a.id != recipe.affix_id]
        sim_item.affixes.append(ItemAffix(id=recipe.affix_id, value=next_affix_val))

        try:
            next_cfg = resolve_weapon_config(WEAPON_CONFIGS, cat, sim_item)
        except Exception:
            next_cfg = None

        # Build stats text
        pellets = cur_cfg.get("pellets", 1) if cur_cfg else 1
        lines = [f"【 강화 공정 적용 제원 비교 : {recipe.name} 】"]

        if cur_cfg and next_cfg:
            diff_dmg = next_cfg["damage"] - cur_cfg["damage"]
            if diff_dmg > 0.001:
                if pellets > 1:
                    lines.append(
                        f"  • 기본 공격력 : 현재 {cur_cfg['damage']:.1f} → 변경 {next_cfg['damage']:.1f} (▲ +{diff_dmg:.1f})\n"
                        f"    ※ 샷건 펠릿당 피해량 (1회 발사 시 총 {pellets}발 발사)"
                    )
                else:
                    lines.append(f"  • 기본 공격력 : 현재 {cur_cfg['damage']:.1f} → 변경 {next_cfg['damage']:.1f} (▲ +{diff_dmg:.1f})")
            else:
                if pellets > 1:
                    lines.append(f"  • 기본 공격력 : 현재 {cur_cfg['damage']:.1f} (동일, 총 {pellets}발 발사)")
                else:
                    lines.append(f"  • 기본 공격력 : 현재 {cur_cfg['damage']:.1f} (동일)")

            lines.append(f"  • 재장전 시간 : 현재 {cur_cfg['reload_time']:.2f}s (동일)")

            diff_hs = next_cfg["headshot_mult"] - cur_cfg["headshot_mult"]
            if diff_hs > 0.001:
                lines.append(f"  • 약점 헤드샷 : 현재 {cur_cfg['headshot_mult']:.2f}x → 변경 {next_cfg['headshot_mult']:.2f}x (▲ +{diff_hs:.2f}x)")
            else:
                lines.append(f"  • 약점 헤드샷 : 현재 {cur_cfg['headshot_mult']:.2f}x (동일)")

            affix_title = AFFIX_NAMES.get(recipe.affix_id, recipe.name)
            delta_p = (next_affix_val - cur_affix_val) * 100.0
            lines.append(
                f"  • {affix_title} 배율 : {cur_affix_val:.2f}x → {next_affix_val:.2f}x (+{delta_p:.0f}%p / 상한 {recipe.cap:.2f}x)"
            )
        else:
            lines.append("  (무기 제원 계산 중 오류가 발생했습니다)")

        self.lbl_preview_stats.setText("\n".join(lines))

        # Material requirement & availability
        mat_defn = cat.get(recipe.material_id)
        mat_name = mat_defn.name if mat_defn else recipe.material_id
        avail_count = material_count(prof, recipe.material_id)
        tot_count = sum(it.quantity for it in prof.items.values() if it.definition_id == recipe.material_id)
        rem_after = max(0, avail_count - recipe.cost)

        self.lbl_cost_info.setText(
            f"필요 소모: {mat_name} {recipe.cost}개 / 사용 가능 {avail_count}개"
        )
        self.lbl_cost_detail.setText(
            f"강화 후 잔여 {rem_after}개 · 잠금 재료 보존"
        )

        # Check upgrade eligibility
        can_upgrade = True
        fail_reason = ""
        quote = None

        try:
            quote = self.session.quote_upgrade(sel_item.uid, self.selected_recipe)
        except ValidationError as err:
            can_upgrade = False
            fail_reason = str(err)
        except Exception as err:
            can_upgrade = False
            fail_reason = f"강화 불가: {err}"

        # Additional environment guards
        if getattr(self.game, "is_test_mode", False):
            can_upgrade = False
            fail_reason = "사격장 모드에서는 무기를 강화할 수 없습니다 (읽기 전용)"
        elif getattr(self.game, "game_state", "INVENTORY") != "INVENTORY":
            can_upgrade = False
            fail_reason = "인벤토리 상태에서만 강화할 수 있습니다"
        elif getattr(self.game, "_extraction_pending", False):
            can_upgrade = False
            fail_reason = "탈출 대기 상태에서는 강화할 수 없습니다"

        # Apply state to button and messages
        if can_upgrade and quote is not None:
            self._displayed_quote = quote
            self.btn_upgrade_execute["state"] = DGG.NORMAL if DGG else "normal"
            self.btn_upgrade_execute["text"] = f"[ {recipe.name} 실행 ]"
            self.btn_upgrade_execute["text_fg"] = (0.35, 1.0, 0.55, 1.0)
            self.btn_upgrade_execute["frameColor"] = (0.15, 0.35, 0.22, 0.95)
            self.lbl_fail_reason.setText("")
        else:
            self.btn_upgrade_execute["state"] = DGG.DISABLED if DGG else "disabled"
            self.btn_upgrade_execute["text"] = "[ 강화 조건 미충족 ]"
            self.btn_upgrade_execute["text_fg"] = (0.55, 0.60, 0.65, 1.0)
            self.btn_upgrade_execute["frameColor"] = (0.16, 0.18, 0.22, 0.90)
            self.lbl_fail_reason.setText(f"※ {fail_reason}" if fail_reason else "")

        if self.status_msg:
            self.lbl_feedback.setText(self.status_msg)
            self.lbl_feedback.setFg((1.0, 0.40, 0.40, 1.0) if self.status_is_error else (0.35, 1.0, 0.55, 1.0))
        else:
            self.lbl_feedback.setText("")

    def _on_click_upgrade(self) -> None:
        """Execute weapon upgrade through game.upgrade_weapon."""
        if not self.session or not self.session.profile or not self.selected_uid:
            self.status_msg = "선택된 무기가 없습니다."
            self.status_is_error = True
            self.refresh()
            return

        if not self.game:
            self.status_msg = "게임 인스턴스를 찾을 수 없습니다."
            self.status_is_error = True
            self.refresh()
            return

        quote = getattr(self, '_displayed_quote', None)
        if quote is None:
            self.status_msg = "강화 미리보기를 다시 확인하세요."
            self.status_is_error = True
            self.refresh()
            return
        self._displayed_quote = None

        # Execute upgrade through game.upgrade_weapon (enforces all game state guards)
        ok, msg = self.game.upgrade_weapon(quote)
        self.status_msg = msg
        self.status_is_error = not ok

        if ok:
            # Sync with equipment panel and combat
            if self.on_change_callback:
                self.on_change_callback()
            eq_ui = getattr(getattr(self.game, "ui_mgr", None), "equipment_ui", None)
            if eq_ui and hasattr(eq_ui, "refresh"):
                eq_ui.refresh()

        self.refresh()

