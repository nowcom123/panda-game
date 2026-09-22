import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
import time


class RPGTemplateEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("RPG Loot Template Architect")
        self.root.geometry("900x700")

        # 카테고리별 ID 접두사 정의
        self.prefixes = {
            "Character/Monster": "CH_",
            "Weapon": "WP_",
            "Armor/Accessory": "AR_",
        }

        self.main_categories = list(self.prefixes.keys())
        self.weapon_types = {
            "Sword": ["1H", "2H", "Dual"],
            "Axe": ["1H", "2H", "Dual"],
            "Mace": ["1H", "2H", "Dual"],
            "Knife": ["1H", "Dual"],
            "Staff": ["2H"],
            "Wand": ["1H", "Dual"],
            "Bow": ["2H"],
        }

        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        # 상단 제어바
        top_frame = tk.Frame(self.root, bg="#2c3e50", pady=10)
        top_frame.pack(fill="x")

        tk.Label(top_frame, text="Select Category:", fg="white", bg="#2c3e50").pack(
            side="left", padx=10
        )
        self.main_cat_var = tk.StringVar(value=self.main_categories[0])
        self.main_cat_combo = ttk.Combobox(
            top_frame,
            textvariable=self.main_cat_var,
            values=self.main_categories,
            state="readonly",
        )
        self.main_cat_combo.pack(side="left")
        self.main_cat_combo.bind("<<ComboboxSelected>>", self.on_category_change)

        # 메인 레이아웃
        paned = tk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # 왼쪽: 템플릿 리스트
        left_frame = tk.Frame(paned)
        self.listbox = tk.Listbox(left_frame, width=35, font=("Consolas", 10))
        self.listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.load_selected)
        paned.add(left_frame)

        # 오른쪽: 입력 영역 (Scrollable)
        right_frame = tk.Frame(paned)
        self.canvas = tk.Canvas(right_frame)
        self.scroll_frame = tk.Frame(self.canvas)
        scrollbar = tk.Scrollbar(
            right_frame, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        paned.add(right_frame)

        self.fields = {}
        self.build_fields()

    def build_fields(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.fields = {}
        cat = self.main_cat_var.get()

        # ID 및 이름 (ID는 자동 생성 버튼 제공)
        id_frame = tk.Frame(self.scroll_frame)
        id_frame.pack(fill="x", padx=10)
        tk.Label(id_frame, text="Template ID (Auto-generated)").pack(anchor="w")
        self.ent_id = tk.Entry(id_frame, state="readonly", fg="blue")
        self.ent_id.pack(side="left", fill="x", expand=True)
        tk.Button(id_frame, text="Gen ID", command=self.generate_new_id).pack(
            side="right"
        )

        self.add_single_field("Display Name", "name")

        if cat == "Character/Monster":
            self.add_section("Physical Stats (Min ~ Max)")
            for f in ["HP", "Phys_ATK", "DEF"]:
                self.add_range_field(f)
            self.add_section("Fate Stats (Fixed for Base)")
            for f in ["Quality", "Proc_Rate"]:
                self.add_single_field(f, f.lower())

        elif cat == "Weapon":
            self.add_section("Weapon Classification")
            self.w_type_var = tk.StringVar()
            ttk.Combobox(
                self.scroll_frame,
                textvariable=self.w_type_var,
                values=list(self.weapon_types.keys()),
            ).pack()
            self.add_section("Damage Ranges")
            for f in ["Phys_DMG", "Mag_DMG", "Crit_Chance"]:
                self.add_range_field(f)

        # 공통 저장 버튼
        tk.Button(
            self.scroll_frame,
            text="SAVE TEMPLATE",
            command=self.save_data,
            bg="#27ae60",
            fg="white",
            height=2,
        ).pack(fill="x", pady=20, padx=10)
        tk.Button(
            self.scroll_frame,
            text="DELETE",
            command=self.delete_item,
            bg="#c0392b",
            fg="white",
        ).pack(fill="x", padx=10)

    def add_range_field(self, label):
        frame = tk.Frame(self.scroll_frame)
        frame.pack(fill="x", padx=10, pady=2)
        tk.Label(frame, text=label).pack(anchor="w")
        min_ent = tk.Entry(frame, width=10)
        min_ent.pack(side="left")
        tk.Label(frame, text=" ~ ").pack(side="left")
        max_ent = tk.Entry(frame, width=10)
        max_ent.pack(side="left")
        self.fields[label.lower()] = (min_ent, max_ent)

    def add_single_field(self, label, key):
        tk.Label(self.scroll_frame, text=label).pack(anchor="w", padx=10)
        ent = tk.Entry(self.scroll_frame)
        ent.pack(fill="x", padx=10, pady=2)
        self.fields[key] = ent

    def add_section(self, text):
        tk.Label(
            self.scroll_frame, text=text, font=("Arial", 9, "bold"), fg="#e67e22"
        ).pack(pady=(10, 0))

    def generate_new_id(self):
        prefix = self.prefixes[self.main_cat_var.get()]
        new_id = f"{prefix}{int(time.time())}"
        self.ent_id.config(state="normal")
        self.ent_id.delete(0, tk.END)
        self.ent_id.insert(0, new_id)
        self.ent_id.config(state="readonly")

    def get_path(self):
        return f"{self.main_cat_var.get().replace('/', '_')}_Templates.json"

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        path = self.get_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
                for item in self.data:
                    self.listbox.insert(tk.END, f"{item['id']} | {item['name']}")
        else:
            self.data = []

    def save_data(self):
        item_id = self.ent_id.get()
        if not item_id:
            messagebox.showwarning("Error", "ID를 생성해주세요.")
            return

        new_item = {"id": item_id, "category": self.main_cat_var.get()}
        for k, v in self.fields.items():
            if isinstance(v, tuple):  # Range field
                new_item[f"{k}_min"] = float(v[0].get() or 0)
                new_item[f"{k}_max"] = float(v[1].get() or 0)
            else:  # Single field
                new_item[k] = v.get()

        # Update or Append
        for i, item in enumerate(self.data):
            if item["id"] == item_id:
                self.data[i] = new_item
                break
        else:
            self.data.append(new_item)

        with open(self.get_path(), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        self.refresh_list()
        messagebox.showinfo("Success", "템플릿이 저장되었습니다.")

    def on_category_change(self, e):
        self.build_fields()
        self.refresh_list()

    def load_selected(self, e):
        idx = self.listbox.curselection()
        if not idx:
            return
        item = self.data[idx[0]]

        self.ent_id.config(state="normal")
        self.ent_id.delete(0, tk.END)
        self.ent_id.insert(0, item["id"])
        self.ent_id.config(state="readonly")

        for k, v in self.fields.items():
            if isinstance(v, tuple):
                v[0].delete(0, tk.END)
                v[0].insert(0, str(item.get(f"{k}_min", "")))
                v[1].delete(0, tk.END)
                v[1].insert(0, str(item.get(f"{k}_max", "")))
            else:
                v.delete(0, tk.END)
                v.insert(0, str(item.get(k, "")))

    def delete_item(self):
        idx = self.listbox.curselection()
        if idx:
            self.data.pop(idx[0])
            with open(self.get_path(), "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            self.refresh_list()


if __name__ == "__main__":
    root = tk.Tk()
    app = RPGTemplateEditor(root)
    root.mainloop()
