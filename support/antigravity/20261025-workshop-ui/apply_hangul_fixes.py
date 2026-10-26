import sys

with open("ui_manager.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add import
old_import = "from rpg.workshop_ui import WorkshopUIPanel\n"
new_import = (
    "from rpg.workshop_ui import WorkshopUIPanel\n"
    "from rpg.hangul_util import eng_to_hangul, get_clipboard_text\n"
)
assert old_import in content, "old_import not found"
content = content.replace(old_import, new_import, 1)

# 2. Add paste & convert buttons to char_create_frame and ctrl-v accept
old_create_block = """        self.lbl_create_err = OnscreenText(
            text="",
            parent=self.char_create_frame,
            pos=(0, -0.10),
            scale=0.024,
            fg=(1.0, 0.35, 0.35, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )"""

new_create_block = """        self.btn_create_paste = DirectButton(
            parent=self.char_create_frame,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.14, 0.18, 0.24, 0.95),
            frameSize=(-0.15, 0.15, -0.028, 0.028),
            pos=(-0.16, 0, -0.05),
            text="[ 붙여넣기 (Ctrl+V) ]",
            text_scale=0.022,
            text_pos=(0, -0.006),
            text_fg=(0.80, 0.88, 0.95, 1.0),
            command=self._on_paste_create_entry,
            **self.btn_font_kw
        )

        self.btn_create_convert = DirectButton(
            parent=self.char_create_frame,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.14, 0.20, 0.28, 0.95),
            frameSize=(-0.14, 0.14, -0.028, 0.028),
            pos=(0.16, 0, -0.05),
            text="[ 한글 변환 ]",
            text_scale=0.022,
            text_pos=(0, -0.006),
            text_fg=(0.40, 0.85, 1.0, 1.0),
            command=self._on_click_convert_create_name,
            **self.btn_font_kw
        )

        self.lbl_create_err = OnscreenText(
            text="",
            parent=self.char_create_frame,
            pos=(0, -0.13),
            scale=0.024,
            fg=(1.0, 0.35, 0.35, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )"""
assert old_create_block in content, "old_create_block not found"
content = content.replace(old_create_block, new_create_block, 1)

old_setup_del_call = "        self._setup_character_delete_modal()\n"
new_setup_del_call = """        self._setup_character_delete_modal()

        if hasattr(self, 'base') and hasattr(self.base, 'accept'):
            try:
                self.base.accept("control-v", self._on_global_ctrl_v)
            except Exception:
                pass
"""
assert old_setup_del_call in content, "old_setup_del_call not found"
content = content.replace(old_setup_del_call, new_setup_del_call, 1)

# 3. Add callbacks for creation & global ctrl-v
old_cancel_create = """    def _on_click_cancel_create(self):
        if hasattr(self, 'char_create_frame'):
            self.char_create_frame.hide()"""

new_cancel_create = """    def _on_click_cancel_create(self):
        if hasattr(self, 'char_create_frame'):
            self.char_create_frame.hide()

    def _on_paste_create_entry(self):
        text = get_clipboard_text().strip()
        if text and hasattr(self, 'char_create_entry'):
            self.char_create_entry.set(text)

    def _on_click_convert_create_name(self):
        if hasattr(self, 'char_create_entry'):
            raw = self.char_create_entry.get().strip()
            converted = eng_to_hangul(raw)
            if converted:
                self.char_create_entry.set(converted)

    def _on_global_ctrl_v(self):
        if self.is_char_delete_modal_open():
            self._on_paste_delete_entry()
        elif hasattr(self, 'char_create_frame') and not self.char_create_frame.isHidden():
            self._on_paste_create_entry()"""
assert old_cancel_create in content, "old_cancel_create not found"
content = content.replace(old_cancel_create, new_cancel_create, 1)

# 4. Update _setup_character_delete_modal widgets
old_del_widgets = """        self.lbl_del_notice = OnscreenText(
            text="목록에서 삭제하고 캐릭터 슬롯을 비웁니다.\\n"
                 "복구용 저장 파일은 남겨둡니다.\\n"
                 "삭제할 탐험가의 이름을 정확히 입력하세요.",
            parent=self.char_delete_modal,
            pos=(0, 0.11),
            scale=0.032,
            fg=(0.85, 0.88, 0.92, 0.95),
            align=TextNode.ACenter if TextNode else 0,
            **self.font_kw
        )

        self.char_delete_entry = DirectEntry(
            parent=self.char_delete_modal,
            scale=0.032,
            pos=(-0.30, 0, -0.06),
            numLines=1,
            width=19,
            frameColor=(0.12, 0.16, 0.22, 1.0),
            text_fg=(1.0, 1.0, 1.0, 1.0),
            initialText="",
            focus=0,
            command=self._on_delete_entry_enter,
            **self.btn_font_kw
        )

        self.lbl_del_err = OnscreenText(
            text="",
            parent=self.char_delete_modal,
            pos=(0, -0.15),
            scale=0.023,
            fg=(1.0, 0.35, 0.35, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw
        )

        self.btn_confirm_delete = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.14, 0.15, 0.18, 0.85),
            frameSize=(-0.20, 0.20, -0.040, 0.040),
            pos=(-0.22, 0, -0.27),
            text="[ 삭제 확정 ]",
            text_scale=0.026,
            text_pos=(0, -0.008),
            text_fg=(0.50, 0.50, 0.55, 1.0),
            command=self._on_click_confirm_delete,
            state=DGG.DISABLED if DGG else "disabled",
            **self.btn_font_kw
        )

        self.btn_cancel_delete = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.16, 0.20, 0.26, 0.95),
            frameSize=(-0.20, 0.20, -0.040, 0.040),
            pos=(0.22, 0, -0.27),
            text="[ 취소 (ESC) ]",
            text_scale=0.026,
            text_pos=(0, -0.008),
            text_fg=(0.85, 0.88, 0.92, 1.0),
            command=self.hide_character_delete_modal,
            **self.btn_font_kw
        )"""

new_del_widgets = """        self.lbl_del_notice = OnscreenText(
            text="목록에서 삭제하고 캐릭터 슬롯을 비웁니다.\\n"
                 "복구용 저장 파일은 남겨둡니다.\\n"
                 "삭제할 탐험가의 이름을 입력하거나 아래 [자동 입력]을 누르세요.",
            parent=self.char_delete_modal,
            pos=(0, 0.11),
            scale=0.030,
            fg=(0.85, 0.88, 0.92, 0.95),
            align=TextNode.ACenter if TextNode else 0,
            **self.font_kw
        )

        self.char_delete_entry = DirectEntry(
            parent=self.char_delete_modal,
            scale=0.032,
            pos=(-0.30, 0, -0.04),
            numLines=1,
            width=19,
            frameColor=(0.12, 0.16, 0.22, 1.0),
            text_fg=(1.0, 1.0, 1.0, 1.0),
            initialText="",
            focus=0,
            command=self._on_delete_entry_enter,
            **self.btn_font_kw
        )

        self.btn_del_autofill = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.14, 0.22, 0.32, 0.95),
            frameSize=(-0.16, 0.16, -0.030, 0.030),
            pos=(-0.14, 0, -0.13),
            text="[ 이름 자동 입력 ]",
            text_scale=0.024,
            text_pos=(0, -0.007),
            text_fg=(0.40, 0.85, 1.0, 1.0),
            command=self._on_click_autofill_delete_name,
            **self.btn_font_kw
        )

        self.btn_del_paste = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.003, 0.003),
            frameColor=(0.16, 0.18, 0.24, 0.95),
            frameSize=(-0.15, 0.15, -0.030, 0.030),
            pos=(0.19, 0, -0.13),
            text="[ 붙여넣기 (Ctrl+V) ]",
            text_scale=0.022,
            text_pos=(0, -0.007),
            text_fg=(0.80, 0.85, 0.95, 1.0),
            command=self._on_paste_delete_entry,
            **self.btn_font_kw
        )

        self.lbl_del_err = OnscreenText(
            text="",
            parent=self.char_delete_modal,
            pos=(0, -0.20),
            scale=0.023,
            fg=(1.0, 0.35, 0.35, 1.0),
            align=TextNode.ACenter if TextNode else 0,
            mayChange=True,
            **self.font_kw
        )

        self.btn_confirm_delete = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.14, 0.15, 0.18, 0.85),
            frameSize=(-0.20, 0.20, -0.040, 0.040),
            pos=(-0.22, 0, -0.29),
            text="[ 삭제 확정 ]",
            text_scale=0.026,
            text_pos=(0, -0.008),
            text_fg=(0.50, 0.50, 0.55, 1.0),
            command=self._on_click_confirm_delete,
            state=DGG.DISABLED if DGG else "disabled",
            **self.btn_font_kw
        )

        self.btn_cancel_delete = DirectButton(
            parent=self.char_delete_modal,
            relief=DGG.RIDGE if DGG else None,
            borderWidth=(0.004, 0.004),
            frameColor=(0.16, 0.20, 0.26, 0.95),
            frameSize=(-0.20, 0.20, -0.040, 0.040),
            pos=(0.22, 0, -0.29),
            text="[ 취소 (ESC) ]",
            text_scale=0.026,
            text_pos=(0, -0.008),
            text_fg=(0.85, 0.88, 0.92, 1.0),
            command=self.hide_character_delete_modal,
            **self.btn_font_kw
        )"""
assert old_del_widgets in content, "old_del_widgets not found"
content = content.replace(old_del_widgets, new_del_widgets, 1)

# 5. Add callbacks and update _update_delete_confirm_btn_state and _on_click_confirm_delete
old_del_methods = """    def _update_delete_confirm_btn_state(self):
        entered = self.char_delete_entry.get().strip() if hasattr(self, 'char_delete_entry') else ""
        expected = getattr(self, '_deleting_char_name', None)
        if expected and entered == expected:
            self.btn_confirm_delete["state"] = DGG.NORMAL if DGG else "normal"
            self.btn_confirm_delete["text_fg"] = (1.0, 0.35, 0.35, 1.0)
            self.btn_confirm_delete["frameColor"] = (0.35, 0.12, 0.12, 0.95)
        else:
            self.btn_confirm_delete["state"] = DGG.DISABLED if DGG else "disabled"
            self.btn_confirm_delete["text_fg"] = (0.50, 0.50, 0.55, 1.0)
            self.btn_confirm_delete["frameColor"] = (0.14, 0.15, 0.18, 0.85)

    def hide_character_delete_modal(self):
        if hasattr(self, 'char_delete_blocker'):
            self.char_delete_blocker.hide()
        if hasattr(self, 'char_delete_entry'):
            self.char_delete_entry['focus'] = 0
        if hasattr(self, 'char_delete_modal'):
            self.char_delete_modal.hide()
        self._deleting_char_id = None
        self._deleting_char_name = None
        if hasattr(self, 'base') and hasattr(self.base, 'taskMgr') and self.base.taskMgr:
            try:
                self.base.taskMgr.remove("check_delete_name_match")
            except Exception:
                pass

    def _on_click_confirm_delete(self):
        char_id = getattr(self, '_deleting_char_id', None)
        expected_name = getattr(self, '_deleting_char_name', None)
        entered_name = self.char_delete_entry.get().strip()

        if not char_id or entered_name != expected_name:
            self.lbl_del_err.setText("탐험가 이름이 일치하지 않습니다.")
            return"""

new_del_methods = """    def _on_click_autofill_delete_name(self):
        expected = getattr(self, '_deleting_char_name', None)
        if expected and hasattr(self, 'char_delete_entry'):
            self.char_delete_entry.set(expected)
            self._update_delete_confirm_btn_state()

    def _on_paste_delete_entry(self):
        text = get_clipboard_text().strip()
        if text and hasattr(self, 'char_delete_entry'):
            self.char_delete_entry.set(text)
            self._update_delete_confirm_btn_state()

    def _update_delete_confirm_btn_state(self):
        entered = self.char_delete_entry.get().strip() if hasattr(self, 'char_delete_entry') else ""
        expected = getattr(self, '_deleting_char_name', None)
        converted = eng_to_hangul(entered)
        is_match = bool(expected and (entered == expected or converted == expected))
        if is_match and entered != expected and converted == expected:
            self.char_delete_entry.set(converted)
            entered = converted

        if is_match:
            self.btn_confirm_delete["state"] = DGG.NORMAL if DGG else "normal"
            self.btn_confirm_delete["text_fg"] = (1.0, 0.35, 0.35, 1.0)
            self.btn_confirm_delete["frameColor"] = (0.35, 0.12, 0.12, 0.95)
        else:
            self.btn_confirm_delete["state"] = DGG.DISABLED if DGG else "disabled"
            self.btn_confirm_delete["text_fg"] = (0.50, 0.50, 0.55, 1.0)
            self.btn_confirm_delete["frameColor"] = (0.14, 0.15, 0.18, 0.85)

    def hide_character_delete_modal(self):
        if hasattr(self, 'char_delete_blocker'):
            self.char_delete_blocker.hide()
        if hasattr(self, 'char_delete_entry'):
            self.char_delete_entry['focus'] = 0
        if hasattr(self, 'char_delete_modal'):
            self.char_delete_modal.hide()
        self._deleting_char_id = None
        self._deleting_char_name = None
        if hasattr(self, 'base') and hasattr(self.base, 'taskMgr') and self.base.taskMgr:
            try:
                self.base.taskMgr.remove("check_delete_name_match")
            except Exception:
                pass

    def _on_click_confirm_delete(self):
        char_id = getattr(self, '_deleting_char_id', None)
        expected_name = getattr(self, '_deleting_char_name', None)
        entered_name = self.char_delete_entry.get().strip()
        if eng_to_hangul(entered_name) == expected_name:
            entered_name = expected_name

        if not char_id or entered_name != expected_name:
            self.lbl_del_err.setText("탐험가 이름이 일치하지 않습니다.")
            return"""
assert old_del_methods in content, "old_del_methods not found"
content = content.replace(old_del_methods, new_del_methods, 1)

with open("ui_manager.py", "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content)

print("ui_manager.py successfully updated with Hangul / autofill / paste support!")

