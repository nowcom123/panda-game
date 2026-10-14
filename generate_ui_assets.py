import os
import math
from PIL import Image, ImageDraw, ImageFilter

UI_DIR = os.path.join("assets", "ui")
os.makedirs(UI_DIR, exist_ok=True)

def create_crosshairs():
    # 1. Default Crosshair (128x128)
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = 64, 64
    
    # Subtle drop shadow
    shadow_col = (0, 0, 0, 180)
    fg_col = (255, 255, 255, 230)
    accent_col = (56, 189, 248, 240) # light cyan
    
    # Center dot
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=shadow_col)
    draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=fg_col)
    
    # 4 Ticks
    gap = 7
    length = 14
    # Shadow ticks
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        x1 = cx + dx * gap
        y1 = cy + dy * gap
        x2 = cx + dx * (gap + length)
        y2 = cy + dy * (gap + length)
        draw.line([x1, y1 + 1, x2, y2 + 1], fill=shadow_col, width=3)
        draw.line([x1 + 1, y1, x2 + 1, y2], fill=shadow_col, width=3)
        draw.line([x1, y1, x2, y2], fill=fg_col, width=2)
    
    # Corner brackets (tactical HUD reticle feel)
    b_dist = 26
    b_len = 8
    # Top-Left
    draw.line([cx - b_dist, cy - b_dist, cx - b_dist + b_len, cy - b_dist], fill=accent_col, width=2)
    draw.line([cx - b_dist, cy - b_dist, cx - b_dist, cy - b_dist + b_len], fill=accent_col, width=2)
    # Top-Right
    draw.line([cx + b_dist, cy - b_dist, cx + b_dist - b_len, cy - b_dist], fill=accent_col, width=2)
    draw.line([cx + b_dist, cy - b_dist, cx + b_dist, cy - b_dist + b_len], fill=accent_col, width=2)
    # Bottom-Left
    draw.line([cx - b_dist, cy + b_dist, cx - b_dist + b_len, cy + b_dist], fill=accent_col, width=2)
    draw.line([cx - b_dist, cy + b_dist, cx - b_dist, cy + b_dist - b_len], fill=accent_col, width=2)
    # Bottom-Right
    draw.line([cx + b_dist, cy + b_dist, cx + b_dist - b_len, cy + b_dist], fill=accent_col, width=2)
    draw.line([cx + b_dist, cy + b_dist, cx + b_dist, cy + b_dist - b_len], fill=accent_col, width=2)
    
    img.save(os.path.join(UI_DIR, "crosshair_default.png"))

    # 2. Hit Marker (128x128) - Crimson X
    img_hit = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw_hit = ImageDraw.Draw(img_hit)
    hit_col = (255, 45, 65, 255)
    hit_shadow = (80, 0, 10, 200)
    h_gap = 5
    h_len = 16
    for sx, sy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        x1 = cx + sx * h_gap
        y1 = cy + sy * h_gap
        x2 = cx + sx * (h_gap + h_len)
        y2 = cy + sy * (h_gap + h_len)
        draw_hit.line([x1, y1 + 1, x2, y2 + 1], fill=hit_shadow, width=5)
        draw_hit.line([x1, y1, x2, y2], fill=hit_col, width=3)
    img_hit.save(os.path.join(UI_DIR, "crosshair_hit.png"))

    # 3. Critical Hit Marker (128x128) - Gold Starburst Reticle
    img_crit = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw_crit = ImageDraw.Draw(img_crit)
    gold_col = (255, 215, 0, 255)
    gold_glow = (255, 140, 0, 180)
    # Diamond in center
    d_size = 9
    pts = [(cx, cy - d_size), (cx + d_size, cy), (cx, cy + d_size), (cx - d_size, cy)]
    draw_crit.polygon(pts, outline=gold_glow, width=3)
    draw_crit.polygon(pts, fill=gold_col)
    
    # Radiating ticks
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        rad = math.radians(angle_deg)
        c, s = math.cos(rad), math.sin(rad)
        r1 = 12 if angle_deg % 90 == 0 else 14
        r2 = 24 if angle_deg % 90 == 0 else 22
        draw_crit.line([cx + c * r1, cy + s * r1, cx + c * r2, cy + s * r2], fill=gold_col, width=3)
    img_crit.save(os.path.join(UI_DIR, "crosshair_crit.png"))
    print("Crosshair textures generated!")

def create_vignettes():
    size = 512
    # 1. Dark Horror Vignette (512x512)
    img_dark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels_dark = img_dark.load()
    center = size / 2.0
    max_dist = math.sqrt(2) * center
    
    for y in range(size):
        for x in range(size):
            dx = x - center
            dy = y - center
            d = math.sqrt(dx * dx + dy * dy)
            # Smooth step from 0.45 to 1.0 of max_dist
            norm_d = d / max_dist
            if norm_d < 0.35:
                alpha = 0
            else:
                t = min(1.0, (norm_d - 0.35) / 0.65)
                # Cubic ease-in
                alpha = int(220 * (t * t))
            pixels_dark[x, y] = (4, 6, 10, alpha)
    img_dark.save(os.path.join(UI_DIR, "vignette_dark.png"))

    # 2. Blood Damage Vignette (512x512)
    img_blood = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels_blood = img_blood.load()
    for y in range(size):
        for x in range(size):
            dx = x - center
            dy = y - center
            d = math.sqrt(dx * dx + dy * dy)
            norm_d = d / max_dist
            if norm_d < 0.38:
                alpha = 0
            else:
                t = min(1.0, (norm_d - 0.38) / 0.62)
                alpha = int(235 * (t * t * t))
            pixels_blood[x, y] = (180, 8, 16, alpha)
    img_blood.save(os.path.join(UI_DIR, "vignette_blood.png"))
    print("Vignette textures generated!")

def create_bars():
    w, h = 480, 36
    # 1. Bar Frame (recessed metallic frame with ticks)
    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_f = ImageDraw.Draw(frame)
    # Outer dark chassis
    draw_f.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=(14, 18, 24, 235), outline=(55, 70, 90, 255), width=2)
    # Inner track
    draw_f.rounded_rectangle([4, 4, w - 5, h - 5], radius=4, fill=(6, 8, 12, 245), outline=(28, 36, 48, 255), width=1)
    # 10% vertical tick lines
    for i in range(1, 10):
        tx = int(w * (i / 10.0))
        draw_f.line([tx, 6, tx, h - 7], fill=(35, 45, 60, 180), width=1)
    frame.save(os.path.join(UI_DIR, "bar_frame.png"))

    # Helper for glowing gradient fill
    def make_fill(c_start, c_mid, c_end, fname):
        fill_img = Image.new("RGBA", (w - 8, h - 8), (0, 0, 0, 0))
        fw, fh = fill_img.size
        draw = ImageDraw.Draw(fill_img)
        for x in range(fw):
            t = x / float(fw)
            if t < 0.5:
                sub_t = t / 0.5
                r = int(c_start[0] + (c_mid[0] - c_start[0]) * sub_t)
                g = int(c_start[1] + (c_mid[1] - c_start[1]) * sub_t)
                b = int(c_start[2] + (c_mid[2] - c_start[2]) * sub_t)
            else:
                sub_t = (t - 0.5) / 0.5
                r = int(c_mid[0] + (c_end[0] - c_mid[0]) * sub_t)
                g = int(c_mid[1] + (c_end[1] - c_mid[1]) * sub_t)
                b = int(c_mid[2] + (c_end[2] - c_mid[2]) * sub_t)
            draw.line([x, 0, x, fh - 1], fill=(r, g, b, 245))
        # Top gloss highlight
        draw.line([0, 1, fw - 1, 1], fill=(255, 255, 255, 110), width=1)
        draw.line([0, 2, fw - 1, 2], fill=(255, 255, 255, 55), width=1)
        fill_img.save(os.path.join(UI_DIR, fname))

    # Health: Vibrant Emerald -> Lime Glow
    make_fill((5, 150, 105), (16, 185, 129), (52, 211, 153), "bar_hp_fill.png")
    # Stamina: Deep Cyan -> Neon Cyan
    make_fill((8, 145, 178), (6, 182, 212), (56, 189, 248), "bar_stamina_fill.png")
    # EXP: Royal Purple -> Electric Violet
    make_fill((109, 40, 217), (139, 92, 246), (192, 132, 252), "bar_exp_fill.png")
    
    # Defense Hazard Stripe Bar (Warning Yellow/Black diagonal stripes)
    def_img = Image.new("RGBA", (w - 8, h - 8), (217, 119, 6, 255))
    draw_def = ImageDraw.Draw(def_img)
    stripe_w = 18
    for i in range(-h, w + h, stripe_w * 2):
        draw_def.polygon([(i, 0), (i + stripe_w, 0), (i + stripe_w - h, h), (i - h, h)], fill=(245, 158, 11, 255))
    draw_def.line([0, 1, w - 8, 1], fill=(255, 255, 200, 140), width=1)
    def_img.save(os.path.join(UI_DIR, "bar_defense_fill.png"))
    print("Bar textures generated!")

def create_icons():
    # 64x64 Icons
    def make_badge(fg_draw_fn, fname, glow_col):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Octagonal / rounded badge background
        draw.rounded_rectangle([2, 2, 61, 61], radius=10, fill=(12, 16, 22, 240), outline=(glow_col[0]//2, glow_col[1]//2, glow_col[2]//2, 200), width=2)
        fg_draw_fn(draw)
        img.save(os.path.join(UI_DIR, fname))

    # 1. Health Icon (Medical Cross)
    def draw_hp(d):
        d.rectangle([27, 16, 36, 47], fill=(16, 185, 129, 255))
        d.rectangle([16, 27, 47, 36], fill=(16, 185, 129, 255))
        # Inner white cross core
        d.rectangle([29, 18, 34, 45], fill=(255, 255, 255, 230))
        d.rectangle([18, 29, 45, 34], fill=(255, 255, 255, 230))
    make_badge(draw_hp, "icon_health.png", (16, 185, 129))

    # 2. Stamina Icon (Lightning bolt)
    def draw_stamina(d):
        pts = [(34, 12), (20, 32), (30, 32), (26, 52), (44, 28), (34, 28)]
        d.polygon(pts, fill=(6, 182, 212, 255))
        pts_core = [(33, 16), (23, 31), (31, 31), (28, 46), (40, 29), (33, 29)]
        d.polygon(pts_core, fill=(230, 255, 255, 240))
    make_badge(draw_stamina, "icon_stamina.png", (6, 182, 212))

    # 3. EXP Icon (Rank Chevron Star)
    def draw_exp(d):
        pts_star = [(32, 14), (36, 26), (49, 26), (38, 34), (42, 47), (32, 39), (22, 47), (26, 34), (15, 26), (28, 26)]
        d.polygon(pts_star, fill=(168, 85, 247, 255))
        d.polygon([(32, 20), (35, 28), (43, 28), (36, 33), (39, 41), (32, 36), (25, 41), (28, 33), (21, 28), (29, 28)], fill=(245, 230, 255, 250))
    make_badge(draw_exp, "icon_exp.png", (168, 85, 247))

    # 4. Ammo Icon (Tactical Bullets)
    def draw_ammo(d):
        # 3 bullets
        for offset_x in [19, 31, 43]:
            # Bullet body
            d.rectangle([offset_x - 3, 22, offset_x + 3, 48], fill=(245, 158, 11, 255))
            # Primer rim
            d.rectangle([offset_x - 4, 46, offset_x + 4, 50], fill=(180, 83, 9, 255))
            # Bullet cone head
            d.polygon([(offset_x - 3, 22), (offset_x + 3, 22), (offset_x, 14)], fill=(217, 119, 6, 255))
            # Specular highlight
            d.line([offset_x - 1, 16, offset_x - 1, 46], fill=(255, 230, 160, 200), width=1)
    make_badge(draw_ammo, "icon_ammo.png", (245, 158, 11))

    # 5. Radar / Beacon Icon
    def draw_radar(d):
        cx, cy = 32, 32
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline=(56, 189, 248, 180), width=2)
        d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=(56, 189, 248, 150), width=1)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(56, 189, 248, 255))
        d.line([cx, cy - 21, cx, cy + 21], fill=(56, 189, 248, 120), width=1)
        d.line([cx - 21, cy, cx + 21, cy], fill=(56, 189, 248, 120), width=1)
        # Radar sweep fan
        d.pieslice([cx - 18, cy - 18, cx + 18, cy + 18], -45, 0, fill=(56, 189, 248, 90))
    make_badge(draw_radar, "icon_radar.png", (56, 189, 248))

    # 6. Relic Cursed Skull
    def draw_relic(d):
        cx, cy = 32, 32
        # Skull head
        d.ellipse([cx - 14, cy - 17, cx + 14, cy + 7], fill=(147, 51, 234, 255))
        # Jaw
        d.rectangle([cx - 8, cy + 5, cx + 8, cy + 17], fill=(147, 51, 234, 255))
        # Eye sockets
        d.ellipse([cx - 9, cy - 6, cx - 3, cy + 2], fill=(15, 10, 25, 255))
        d.ellipse([cx + 3, cy - 6, cx + 9, cy + 2], fill=(15, 10, 25, 255))
        # Teeth lines
        d.line([cx - 4, cy + 8, cx - 4, cy + 15], fill=(20, 10, 30, 255), width=2)
        d.line([cx, cy + 8, cx, cy + 15], fill=(20, 10, 30, 255), width=2)
        d.line([cx + 4, cy + 8, cx + 4, cy + 15], fill=(20, 10, 30, 255), width=2)
    make_badge(draw_relic, "icon_relic.png", (147, 51, 234))
    print("Icon textures generated!")

def create_panels_and_buttons():
    # 1. Top HUD Banner Panel (640x72)
    p_top = Image.new("RGBA", (640, 72), (0, 0, 0, 0))
    draw_p = ImageDraw.Draw(p_top)
    # Chamfered angular header shape
    pts = [(18, 0), (621, 0), (639, 44), (610, 71), (29, 71), (0, 44)]
    draw_p.polygon(pts, fill=(10, 14, 20, 230), outline=(56, 189, 248, 220))
    # Accent sub-lines
    draw_p.line([34, 66, 605, 66], fill=(56, 189, 248, 100), width=1)
    p_top.save(os.path.join(UI_DIR, "panel_hud_top.png"))

    # 2. Bottom-Right Ammo Panel (280x96)
    p_ammo = Image.new("RGBA", (280, 96), (0, 0, 0, 0))
    draw_a = ImageDraw.Draw(p_ammo)
    pts_a = [(24, 0), (279, 0), (279, 95), (0, 95), (0, 28)]
    draw_a.polygon(pts_a, fill=(12, 16, 22, 235), outline=(245, 158, 11, 220))
    draw_a.line([8, 88, 271, 88], fill=(245, 158, 11, 100), width=1)
    p_ammo.save(os.path.join(UI_DIR, "panel_hud_ammo.png"))

    # 3. Main Modal Window Background (840x620)
    p_modal = Image.new("RGBA", (840, 620), (0, 0, 0, 0))
    draw_m = ImageDraw.Draw(p_modal)
    # Outer dark chassis with glowing border
    draw_m.rounded_rectangle([0, 0, 839, 619], radius=16, fill=(10, 13, 18, 246), outline=(45, 60, 80, 255), width=3)
    # Inner decorative glow rim
    draw_m.rounded_rectangle([6, 6, 833, 613], radius=12, outline=(56, 189, 248, 80), width=1)
    # Header bar
    draw_m.rounded_rectangle([10, 10, 829, 76], radius=8, fill=(16, 22, 32, 240), outline=(56, 189, 248, 160), width=2)
    # Corner tactical brackets
    c_len = 24
    for cx, cy, sx, sy in [(12, 12, 1, 1), (827, 12, -1, 1), (12, 607, 1, -1), (827, 607, -1, -1)]:
        draw_m.line([cx, cy, cx + sx * c_len, cy], fill=(56, 189, 248, 240), width=3)
        draw_m.line([cx, cy, cx, cy + sy * c_len], fill=(56, 189, 248, 240), width=3)
    p_modal.save(os.path.join(UI_DIR, "panel_modal_bg.png"))

    # 4. Relic Card Backgrounds (240x320)
    def make_card(border_col, glow_col, fname):
        card = Image.new("RGBA", (240, 320), (0, 0, 0, 0))
        d_c = ImageDraw.Draw(card)
        d_c.rounded_rectangle([0, 0, 239, 319], radius=12, fill=(12, 14, 20, 245), outline=border_col, width=2)
        d_c.rounded_rectangle([6, 6, 233, 313], radius=8, outline=glow_col, width=1)
        # Card inner illustration header frame
        d_c.rounded_rectangle([14, 14, 225, 120], radius=6, fill=(8, 10, 14, 240), outline=border_col, width=1)
        card.save(os.path.join(UI_DIR, fname))
    
    make_card((120, 70, 180, 255), (168, 85, 247, 90), "card_relic_bg.png")
    make_card((217, 119, 6, 255), (245, 158, 11, 120), "card_relic_active.png")

    # 5. Buttons (320x64)
    # 5-1. Normal Button
    def make_btn(fill_col, outline_col, highlight_col, fname):
        btn = Image.new("RGBA", (320, 64), (0, 0, 0, 0))
        d_b = ImageDraw.Draw(btn)
        d_b.rounded_rectangle([0, 0, 319, 63], radius=8, fill=fill_col, outline=outline_col, width=2)
        # Top highlight sheen
        d_b.line([10, 2, 309, 2], fill=highlight_col, width=1)
        d_b.line([10, 3, 309, 3], fill=(highlight_col[0], highlight_col[1], highlight_col[2], highlight_col[3]//2), width=1)
        btn.save(os.path.join(UI_DIR, fname))

    # Standard Button states
    make_btn((18, 26, 38, 245), (45, 68, 98, 255), (255, 255, 255, 100), "btn_normal.png")
    make_btn((28, 42, 62, 255), (56, 189, 248, 255), (100, 220, 255, 200), "btn_hover.png")
    make_btn((12, 18, 28, 255), (30, 48, 72, 255), (150, 150, 150, 50), "btn_click.png")
    make_btn((16, 20, 26, 200), (30, 36, 45, 200), (80, 90, 100, 40), "btn_disabled.png")

    # Accent Gold/Amber Button states (e.g. for Victory Escape or Play)
    make_btn((58, 36, 12, 250), (217, 119, 6, 255), (255, 240, 180, 160), "btn_accent_normal.png")
    make_btn((92, 54, 16, 255), (245, 158, 11, 255), (255, 255, 210, 230), "btn_accent_hover.png")
    
    # Critical Red Button states (e.g. for Exit / Danger)
    make_btn((48, 16, 20, 250), (220, 38, 38, 255), (255, 200, 200, 140), "btn_danger_normal.png")
    make_btn((72, 22, 28, 255), (248, 113, 113, 255), (255, 230, 230, 220), "btn_danger_hover.png")
    
    print("Panels and buttons generated!")

if __name__ == "__main__":
    create_crosshairs()
    create_vignettes()
    create_bars()
    create_icons()
    create_panels_and_buttons()
    print("=== ALL UI IMAGE ASSETS GENERATED SUCCESSFULLY ===")
