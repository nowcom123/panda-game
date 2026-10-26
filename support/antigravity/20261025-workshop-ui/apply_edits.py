"""Fix sel_defn.id -> sel_item.definition_id in equipment_ui.py."""

def fix():
    with open("rpg/equipment_ui.py", "r", encoding="utf-8") as f:
        c = f.read()

    t = (
        '            if sel_defn and sel_defn.id == "scrap_metal":\n'
        '                self.txt_comparison.setText(\n'
        '                    "【 재료 아이템 용도 안내 】\\n"\n'
        '                    "  • 용도: 무기 작업대에서 [총열 보강] 강화에 소모 (8개)\\n"\n'
        '                    "  • 효과: 무기 기본 공격력 +2%p 영구 증강 (상한: 1.30x)\\n"\n'
        '                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\\n"\n'
        '                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"\n'
        '                )\n'
        '            elif sel_defn and sel_defn.id == "bone_fragment":\n'
        '                self.txt_comparison.setText(\n'
        '                    "【 재료 아이템 용도 안내 】\\n"\n'
        '                    "  • 용도: 무기 작업대에서 [약점 각인] 강화에 소모 (6개)\\n"\n'
        '                    "  • 효과: 무기 약점 헤드샷 피해 +5%p 영구 증강 (상한: 1.50x)\\n"\n'
        '                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\\n"\n'
        '                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"\n'
        '                )'
    )
    r = (
        '            if sel_item.definition_id == "scrap_metal":\n'
        '                self.txt_comparison.setText(\n'
        '                    "【 재료 아이템 용도 안내 】\\n"\n'
        '                    "  • 용도: 무기 작업대에서 [총열 보강] 강화에 소모 (8개)\\n"\n'
        '                    "  • 효과: 무기 기본 공격력 +2%p 영구 증강 (상한: 1.30x)\\n"\n'
        '                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\\n"\n'
        '                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"\n'
        '                )\n'
        '            elif sel_item.definition_id == "bone_fragment":\n'
        '                self.txt_comparison.setText(\n'
        '                    "【 재료 아이템 용도 안내 】\\n"\n'
        '                    "  • 용도: 무기 작업대에서 [약점 각인] 강화에 소모 (6개)\\n"\n'
        '                    "  • 효과: 무기 약점 헤드샷 피해 +5%p 영구 증강 (상한: 1.50x)\\n"\n'
        '                    "  • 잠금 상태에서는 작업대 소모가 방지됩니다.\\n"\n'
        '                    "  (※ 아래 [작업대에서 사용] 버튼으로 바로 이동)"\n'
        '                )'
    )
    assert t in c, "target not found"
    c = c.replace(t, r, 1)

    with open("rpg/equipment_ui.py", "w", encoding="utf-8", newline="\r\n") as f:
        f.write(c)

    b = open("rpg/equipment_ui.py", "rb").read()
    print("equipment_ui.py CRCRLF:", b.count(b"\r\r\n"), "CRLF:", b.count(b"\r\n"))

if __name__ == "__main__":
    fix()

