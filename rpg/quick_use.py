"""Quick-use selection wheel / cards for tactical consumables.

Allows selecting and using eligible inventory consumables via the backtick (`) key.
Operates within the dedicated QUICK_USE state which pauses combat while preserving
bullet time, mouse isolation, and player state.
"""
import math
from direct.showbase.DirectObject import DirectObject
from direct.gui.DirectGui import DirectFrame, DirectButton, DGG
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
from panda3d.core import TextNode, TransparencyAttrib, Point3, Point2, Vec3, WindowProperties


def get_quick_use_items(player, game=None):
    """Filter inventory items eligible for quick-use.

    In RPG mode, 1/2 are weapon shortcut keys so medkit and adrenaline are included.
    Slots 3/4 (ammo_pack, frag_grenade) are directly usable and therefore excluded.
    Unassigned consumables (quick_slot=None, e.g. combat_stim) are included.
    Items with count <= 0 are excluded. Non-consumable items are excluded.
    """
    if not player:
        return []
    inventory = getattr(player, "inventory", [])
    if game is not None:
        is_rpg = bool(getattr(game, "rpg_session", None)) and not getattr(game, "is_test_mode", False)
    else:
        is_rpg = True

    from player_controller import ITEM_CATALOG

    eligible = []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id not in ITEM_CATALOG:
            continue
        count = item.get("count", 0)
        if count <= 0:
            continue
        qs = item.get("quick_slot")
        if is_rpg:
            if qs in (3, 4):
                continue
        else:
            if qs in (1, 2, 3, 4):
                continue
        eligible.append(item)
    return eligible


ITEM_SUMMARIES = {
    "medkit": "체력 +50 HP 즉시 회복",
    "adrenaline": "불릿타임 4.5초\n오버차지 4발",
    "combat_stim": "15초간 공격력 +40%",
    "ammo_pack": "예비 탄약 +18발 즉각 보충",
    "frag_grenade": "대인 살상 파열 수류탄 투척",
}


class QuickUseUIPanel:
    """Radial/card visual interface for quick-use consumables."""

    def __init__(self, base, on_select_callback=None, font_kw=None):
        self.base = base
        self.on_select_callback = on_select_callback
        self.font_kw = font_kw or {}

        self.root = self.base.aspect2d.attachNewNode("quick_use_root")
        self.root.setBin("gui-popup", 50)
        self.cards = []
        self.items = []
        self.selected_index = -1
        self._wheel_locked = False
        self._last_mouse_norm = (0.0, 0.0)

        self._build_ui()
        self.root.hide()

    def _build_ui(self):
        # 1. Dark background overlay
        self.bg_overlay = DirectFrame(
            parent=self.root,
            relief=DGG.FLAT,
            frameColor=(0.02, 0.03, 0.05, 0.65),
            frameSize=(-2.5, 2.5, -1.5, 1.5)
        )

        # 2. Top header
        self.title_text = OnscreenText(
            text="[ 전술 소모품 빠른 사용 // QUICK USE ]",
            parent=self.root,
            pos=(0, 0.76),
            scale=0.038,
            fg=(0.35, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )
        self.sub_text = OnscreenText(
            text="[마우스 호버 또는 휠 순환 · 키를 놓으면 즉시 사용 · 중앙 영역/ESC: 취소]",
            parent=self.root,
            pos=(0, 0.68),
            scale=0.030,
            fg=(0.75, 0.85, 0.92, 0.85),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        # 3. Center cancel / status hub
        self.center_frame = DirectFrame(
            parent=self.root,
            relief=DGG.FLAT,
            frameColor=(0.10, 0.12, 0.16, 0.90),
            frameSize=(-0.24, 0.24, -0.16, 0.16),
            pos=(0, 0, 0)
        )
        self.center_border = DirectFrame(
            parent=self.center_frame,
            relief=DGG.FLAT,
            frameColor=(0.30, 0.40, 0.50, 0.8),
            frameSize=(-0.24, 0.24, -0.002, 0.002),
            pos=(0, 0, 0.158)
        )
        self.center_title = OnscreenText(
            text="[ 중앙 취소 영역 ]",
            parent=self.center_frame,
            pos=(0, 0.04),
            scale=0.030,
            fg=(0.85, 0.85, 0.85, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )
        self.center_desc = OnscreenText(
            text="키를 놓으면\n사용하지 않고 닫힙니다",
            parent=self.center_frame,
            pos=(0, -0.03),
            scale=0.030,
            fg=(0.65, 0.72, 0.78, 0.9),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        # 4. Item cards container
        self.cards_root = self.root.attachNewNode("cards_root")

    def show(self, items):
        self.items = list(items)
        self.selected_index = -1
        self._wheel_locked = False
        self._last_mouse_norm = (0.0, 0.0)

        # Rebuild card widgets based on items
        self._create_cards()
        self._update_highlight()
        self.root.show()

    def hide(self):
        self.root.hide()
        self._clear_cards()

    def is_visible(self):
        return not self.root.isHidden()

    def _clear_cards(self):
        for c in self.cards:
            if c.get("frame"):
                c["frame"].destroy()
        self.cards = []

    def _create_cards(self):
        self._clear_cards()
        n = len(self.items)
        if n == 0:
            self.center_title.setText("[ 사용 가능한 소모품 없음 ]")
            self.center_desc.setText("보유 중인 퀵슬롯 미배정 소모품이 없습니다.")
            return

        radius = 0.46
        card_w, card_h = 0.72, 0.28

        # Calculate positions
        for i, item in enumerate(self.items):
            if n == 1:
                cx, cz = 0.0, 0.38
            elif n == 2:
                cx = -0.68 if i == 0 else 0.68
                cz = 0.08
            elif n == 3:
                cx, cz = [(0, .43), (-.68, -.32), (.68, -.32)][i]
            else:
                # Radial spread starting from top clockwise
                angle = math.pi / 2 - (2 * math.pi * i / n)
                cx = radius * 1.25 * math.cos(angle)
                cz = radius * 0.90 * math.sin(angle)

            frame = DirectFrame(
                parent=self.cards_root,
                relief=DGG.FLAT,
                frameColor=(0.07, 0.09, 0.13, 0.92),
                frameSize=(-card_w / 2, card_w / 2, -card_h / 2, card_h / 2),
                pos=(cx, 0, cz)
            )

            # Highlight border frame
            border = DirectFrame(
                parent=frame,
                relief=DGG.FLAT,
                frameColor=(0.25, 0.35, 0.45, 0.6),
                frameSize=(-card_w / 2, card_w / 2, card_h / 2 - .006, card_h / 2),
                pos=(0, 0, 0)
            )

            # Icon
            icon_path = item.get("icon")
            icon_img = None
            if icon_path:
                try:
                    icon_img = OnscreenImage(
                        image=icon_path,
                        parent=frame,
                        pos=(-0.27, 0, 0.02),
                        scale=(0.065, 1, 0.065)
                    )
                    icon_img.setTransparency(TransparencyAttrib.MAlpha)
                except Exception:
                    icon_img = None

            # Name
            name_text = OnscreenText(
                text=item.get("name", "소모품"),
                parent=frame,
                pos=(-0.16, 0.065),
                scale=0.032,
                fg=(0.90, 0.95, 1.0, 1.0),
                shadow=(0, 0, 0, 0.9),
                align=TextNode.ALeft,
                **self.font_kw
            )

            # Count badge
            count = item.get("count", 0)
            count_text = OnscreenText(
                text=f"x{count}",
                parent=frame,
                pos=(0.32, -0.105),
                scale=0.032,
                fg=(1.0, 0.85, 0.25, 1.0),
                shadow=(0, 0, 0, 0.9),
                align=TextNode.ARight,
                **self.font_kw
            )

            # Effect summary
            summary = ITEM_SUMMARIES.get(item.get("id"), item.get("desc", "").split("\n")[0])
            desc_text = OnscreenText(
                text=summary,
                parent=frame,
                pos=(-0.16, -0.01),
                scale=0.030,
                fg=(0.70, 0.80, 0.88, 0.9),
                shadow=(0, 0, 0, 0.9),
                align=TextNode.ALeft,
                **self.font_kw
            )

            self.cards.append({
                "item": item,
                "frame": frame,
                "border": border,
                "icon": icon_img,
                "name": name_text,
                "count": count_text,
                "desc": desc_text,
                "pos": (cx, cz),
                "w": card_w,
                "h": card_h,
            })

    def update_mouse(self):
        """Update selection from mouse coordinates unless actively locked by wheel."""
        if not self.base.mouseWatcherNode or not self.base.mouseWatcherNode.hasMouse():
            return
        mx = self.base.mouseWatcherNode.getMouseX()
        my = self.base.mouseWatcherNode.getMouseY()

        # Convert to aspect2d
        a2d = self.base.aspect2d.getRelativePoint(self.base.render2d, Point3(mx, 0, my))
        ax, az = a2d.x, a2d.z

        # Check mouse movement delta to break wheel lock
        lx, lz = self._last_mouse_norm
        if math.hypot(ax - lx, az - lz) > 0.04:
            self._wheel_locked = False
            self._last_mouse_norm = (ax, az)

        if self._wheel_locked:
            return

        # Distance from center
        dist_center = math.hypot(ax, az)
        if dist_center <= 0.22 or len(self.items) == 0:
            if self.selected_index != -1:
                self.selected_index = -1
                self._update_highlight()
            return

        # Check which card is hovered or closest
        best_idx = -1
        best_dist = 999.0
        for i, card in enumerate(self.cards):
            cx, cz = card["pos"]
            cw, ch = card["w"], card["h"]
            # Direct bounding box check
            if abs(ax - cx) <= (cw / 2 + 0.05) and abs(az - cz) <= (ch / 2 + 0.05):
                best_idx = i
                break
            d = math.hypot(ax - cx, az - cz)
            if d < best_dist:
                best_dist = d
                best_idx = i

        if best_idx != self.selected_index:
            self.selected_index = best_idx
            self._update_highlight()

    def select_next(self):
        if not self.items:
            return
        self._wheel_locked = True
        if self.selected_index == -1:
            self.selected_index = 0
        else:
            self.selected_index = (self.selected_index + 1) % len(self.items)
        self._update_highlight()

    def select_prev(self):
        if not self.items:
            return
        self._wheel_locked = True
        if self.selected_index == -1:
            self.selected_index = len(self.items) - 1
        else:
            self.selected_index = (self.selected_index - 1 + len(self.items)) % len(self.items)
        self._update_highlight()

    def _update_highlight(self):
        if self.selected_index >= 0 and self.selected_index < len(self.items):
            sel_item = self.items[self.selected_index]
            self.center_frame["frameColor"] = (0.12, 0.20, 0.28, 0.95)
            self.center_border["frameColor"] = (0.35, 0.95, 1.0, 1.0)
            self.center_title.setText(f"[ {sel_item.get('name', '')} ]")
            self.center_title.setFg((0.35, 1.0, 0.65, 1.0))
            self.center_desc.setText("키를 놓으면\n즉시 1회 사용됩니다")
            self.center_desc.setFg((0.90, 0.95, 1.0, 0.95))
        else:
            self.center_frame["frameColor"] = (0.10, 0.12, 0.16, 0.90)
            self.center_border["frameColor"] = (0.40, 0.50, 0.60, 0.7)
            if self.items:
                self.center_title.setText("[ 중앙 취소 영역 ]")
                self.center_title.setFg((0.85, 0.85, 0.85, 1.0))
                self.center_desc.setText("키를 놓으면\n사용하지 않고 닫힙니다")
                self.center_desc.setFg((0.65, 0.72, 0.78, 0.9))

        for i, card in enumerate(self.cards):
            is_sel = (i == self.selected_index)
            if is_sel:
                card["frame"]["frameColor"] = (0.14, 0.22, 0.32, 0.98)
                card["border"]["frameColor"] = (0.35, 0.95, 1.0, 1.0)
                card["name"].setFg((0.40, 1.0, 0.75, 1.0))
            else:
                card["frame"]["frameColor"] = (0.07, 0.09, 0.13, 0.92)
                card["border"]["frameColor"] = (0.22, 0.30, 0.38, 0.5)
                card["name"].setFg((0.85, 0.90, 0.95, 0.95))

    def get_selected_item(self):
        if 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def destroy(self):
        self._clear_cards()
        if hasattr(self, "root") and not self.root.isEmpty():
            self.root.removeNode()


class QuickUseManager(DirectObject):
    """Manages quick-use panel lifecycle, input handling, and pause integration."""

    def __init__(self, game):
        self.game = game
        self.ui_panel = None
        self.is_open = False
        self.is_key_down = False
        self._prev_game_state = "PLAYING"
        self._was_aiming = False
        self._selected_index = 0
        self._available_items = []
        self.accept('window-event', self.on_window_event)

    def on_window_event(self, window):
        if window is not getattr(self.game, 'win', None):
            return
        if not window.getProperties().getForeground():
            was_open = self.is_open
            self.cancel()
            if was_open and getattr(self.game, 'game_state', '') == 'PLAYING':
                self.game.pause_game()

    @property
    def selected_index(self):
        if self.ui_panel is not None:
            return self.ui_panel.selected_index
        return self._selected_index

    @selected_index.setter
    def selected_index(self, val):
        self._selected_index = val
        if self.ui_panel is not None:
            self.ui_panel.selected_index = -1 if val is None else val

    @property
    def available_items(self):
        if self.ui_panel is not None:
            return getattr(self.ui_panel, "items", [])
        return self._available_items

    def setup_ui(self):
        if self.ui_panel is None:
            font_kw = getattr(self.game.ui_mgr, "font_kw", {}) if hasattr(self.game, "ui_mgr") else {}
            try:
                self.ui_panel = QuickUseUIPanel(self.game, font_kw=font_kw)
            except Exception:
                self.ui_panel = None

    def can_open(self):
        """Verify whether quick-use can open under current game context."""
        g = self.game
        if getattr(g, "game_state", "") != "PLAYING":
            return False
        if getattr(g, "is_test_mode", False):
            return False
        if getattr(g, "_extraction_pending", False):
            return False
        if getattr(g, "game_over", False) or getattr(g, "game_won", False):
            return False
        # Do not open if character delete modal or any modal is open
        if hasattr(g, "ui_mgr") and g.ui_mgr:
            if getattr(g.ui_mgr, "is_char_delete_modal_open", lambda: False)():
                return False
            if getattr(g.ui_mgr, "is_inventory_open", lambda: False)():
                return False
        return True

    def on_key_down(self):
        """Backtick key pressed: open quick-use panel and pause combat."""
        if self.is_key_down:
            return  # Prevent OS key-repeat
        self.is_key_down = True

        if not self.can_open():
            return

        self.setup_ui()
        items = get_quick_use_items(self.game.player, self.game)
        self._available_items = items
        self._selected_index = None

        self.is_open = True
        self._prev_game_state = self.game.game_state
        self.game.game_state = "QUICK_USE"

        # Stop aiming and shooting
        p = self.game.player
        c = getattr(self.game, "combat", None)
        if c:
            c._suppress_fire_until_release = True
        if c and hasattr(c, "stop_aim"):
            c.stop_aim()
        if p:
            if isinstance(getattr(p, 'key_map', None), dict):
                p.key_map.update({key: 0 for key in p.key_map})
            self._was_aiming = getattr(p, "is_aiming", False)
            p.is_aiming = False
            if hasattr(p, "lock_mouse"):
                p.lock_mouse(False)

        if self.ui_panel:
            self.ui_panel.show(items)

    def on_key_up(self):
        """Backtick key released: consume selected item (if any) and resume."""
        if not self.is_key_down:
            return
        self.is_key_down = False

        if not self.is_open:
            return

        if self.ui_panel:
            selected_item = self.ui_panel.get_selected_item()
        else:
            if self._selected_index is not None and 0 <= self._selected_index < len(self._available_items):
                selected_item = self._available_items[self._selected_index]
            else:
                selected_item = None
        self.close(use_item=selected_item)

    def select_next(self):
        if self.is_open:
            if self.ui_panel:
                self.ui_panel.select_next()
            elif self._available_items:
                if self._selected_index is None:
                    self._selected_index = 0
                else:
                    self._selected_index = (self._selected_index + 1) % len(self._available_items)

    def select_prev(self):
        if self.is_open:
            if self.ui_panel:
                self.ui_panel.select_prev()
            elif self._available_items:
                if self._selected_index is None:
                    self._selected_index = len(self._available_items) - 1
                else:
                    self._selected_index = (self._selected_index - 1 + len(self._available_items)) % len(self._available_items)

    def update(self, dt):
        """Update UI and mouse tracking during QUICK_USE state."""
        if self.is_open and getattr(self.game, 'game_state', '') != 'QUICK_USE':
            self.cancel()
            return
        if self.is_open and self.ui_panel:
            self.ui_panel.update_mouse()

    def cancel(self):
        """Cancel quick use without consuming any item."""
        if self.is_open:
            self.close(use_item=None)
        self.is_key_down = False

    def close(self, use_item=None):
        """Close quick-use panel, apply item if requested, and restore state."""
        if not self.is_open:
            return
        can_use = getattr(self.game, 'game_state', '') == 'QUICK_USE'
        self.is_open = False
        self.is_key_down = False

        if self.ui_panel:
            self.ui_panel.hide()

        # Restore game state
        if getattr(self.game, "game_state", "") == "QUICK_USE":
            self.game.game_state = self._prev_game_state or "PLAYING"

        # Restore mouse lock and FPS controls
        p = self.game.player
        if p:
            if isinstance(getattr(p, 'key_map', None), dict):
                p.key_map.update({key: 0 for key in p.key_map})
            if hasattr(p, "lock_mouse"):
                p.lock_mouse(getattr(self.game, 'game_state', '') == 'PLAYING')
            # Re-center mouse pointer to prevent sudden view rotation jump
            if hasattr(p, "win") and hasattr(p.win, "movePointer"):
                try:
                    cx = p.win.getXSize() // 2
                    cy = p.win.getYSize() // 2
                    p.win.movePointer(0, cx, cy)
                except Exception:
                    pass

        # Execute selected item consumption
        if use_item and p and can_use and use_item.get('id') in {it['id'] for it in get_quick_use_items(p, self.game)}:
            item_id = use_item.get("id")
            combat = getattr(self.game, "combat", None)
            success, msg = p.use_item(item_id, combat_system=combat, game_instance=self.game)
            if hasattr(self.game, "ui_mgr") and self.game.ui_mgr:
                if success:
                    self.game.ui_mgr.show_hit_marker(f"[빠른 사용] {msg}", (0.35, 1.0, 0.65, 1.0))
                    if hasattr(self.game.ui_mgr, "_refresh_inventory_ui") and getattr(self.game.ui_mgr, "is_inventory_open", lambda: False)():
                        self.game.ui_mgr._refresh_inventory_ui()
                else:
                    self.game.ui_mgr.show_hit_marker(f"[사용 실패] {msg}", (1.0, 0.45, 0.45, 1.0))

    def destroy(self):
        self.cleanup()

    def cleanup(self):
        self.ignoreAll()
        self.cancel()
        if self.ui_panel:
            self.ui_panel.destroy()
            self.ui_panel = None
