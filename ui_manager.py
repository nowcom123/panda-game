"""
UI Manager Module
Panda3D DirectGui & OnscreenText 관리, 이미지 기반 HUD (체력/스테미나/EXP 바, 아이콘, 비네트, 크로스헤어, 패널)
및 텍스트 캐싱 최적화, 랭킹 데이터 입출력
"""

import os
import sys
import json
import math
import random
import datetime
import time
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.DirectGui import DirectButton, DirectFrame, DGG
from panda3d.core import (
    TextNode, TransparencyAttrib, LineSegs, Vec3, NodePath,
    GeomVertexFormat, GeomVertexData, GeomVertexWriter, GeomTriangles, Geom, GeomNode, LColor
)
from constants import CURSED_RELICS
from perks import PERK_CATALOG, draw_random_perks, RARITY_COLORS, RARITY_NAMES, get_perk_level, describe_perk


class FloatingDamageItem:
    """3D 공간상에 투영되는 고가독성 다이내믹 플로팅 대미지 폰트 노드 (오브젝트 풀링)"""
    def __init__(self, parent, font=None):
        self.node = parent.attachNewNode("floating_dmg")
        self.node.setBillboardPointEye()
        self.node.setBin("fixed", 125)
        self.node.setDepthWrite(False)
        self.node.setDepthTest(False)
        self.node.setLightOff()

        self.text_node = TextNode("dmg_txt")
        if font:
            self.text_node.setFont(font)
        self.text_node.setAlign(TextNode.ACenter)
        self.text_node.setShadow(0.045, 0.045)
        self.text_node.setShadowColor(0.0, 0.0, 0.0, 0.95)
        self.text_np = self.node.attachNewNode(self.text_node)

        self.pos = Vec3(0, 0, 0)
        self.vel_z = 2.0
        self.timer = 0.0
        self.max_timer = 0.85
        self.base_scale = 0.40
        self.color = (1.0, 1.0, 1.0)
        self.is_active = False
        self.node.hide()

    def activate(self, damage, world_pos, is_crit=False, is_headshot=False, damage_type=None):
        self.is_active = True
        self.max_timer = 0.85
        self.timer = self.max_timer
        self.vel_z = random.uniform(2.0, 2.7)
        jx = random.uniform(-0.16, 0.16)
        jy = random.uniform(-0.16, 0.16)

        wx = getattr(world_pos, 'x', world_pos[0])
        wy = getattr(world_pos, 'y', world_pos[1])
        wz = getattr(world_pos, 'z', world_pos[2] if len(world_pos) > 2 else 1.0)
        self.pos = Vec3(wx + jx, wy + jy, wz + 0.28)

        val = max(1, int(round(damage)))
        if damage_type == 'fire':
            self.text_node.setText(f"[FIRE] {val}")
            self.color = (1.0, 0.45, 0.12)
            self.base_scale = 0.38
        elif damage_type == 'electric':
            self.text_node.setText(f"[SHOCK] {val}")
            self.color = (0.85, 0.45, 1.0)
            self.base_scale = 0.42
        elif damage_type == 'freeze':
            self.text_node.setText(f"[FROST] {val}")
            self.color = (0.35, 0.90, 1.0)
            self.base_scale = 0.38
        elif is_headshot:
            self.text_node.setText(f"HEADSHOT {val}!")
            self.color = (1.0, 0.85, 0.15)
            self.base_scale = 0.54
        elif is_crit:
            self.text_node.setText(f"CRIT {val}!")
            self.color = (1.0, 0.30, 0.18)
            self.base_scale = 0.48
        else:
            self.text_node.setText(f"{val}")
            self.color = (1.0, 0.98, 0.78)
            self.base_scale = 0.36

        self.text_node.setTextColor(self.color[0], self.color[1], self.color[2], 1.0)
        self.node.setPos(self.pos)
        self.node.setScale(self.base_scale * 1.35)
        self.node.show()

    def update(self, dt):
        if not self.is_active:
            return False
        self.timer -= dt
        if self.timer <= 0.0:
            self.is_active = False
            self.node.hide()
            return False

        self.pos.z += self.vel_z * dt
        self.vel_z = max(0.3, self.vel_z - 3.2 * dt)
        self.node.setPos(self.pos)

        progress = 1.0 - (self.timer / self.max_timer)
        if progress < 0.12:
            scale_factor = 1.35 - 0.35 * (progress / 0.12)
        else:
            scale_factor = 1.0
        self.node.setScale(self.base_scale * scale_factor)

        if self.timer < 0.28:
            alpha = max(0.0, self.timer / 0.28)
        else:
            alpha = 1.0
        self.text_node.setTextColor(self.color[0], self.color[1], self.color[2], alpha)
        return True


class FloatingDamageManager:
    """플로팅 대미지 오브젝트 풀 매니저 (GC 부하 0%)"""
    def __init__(self, render_root, pool_size=32, font=None):
        if hasattr(render_root, 'attachNewNode'):
            self.root = render_root.attachNewNode("floating_damage_root")
            self.pool = [FloatingDamageItem(self.root, font=font) for _ in range(pool_size)]
        else:
            self.root = None
            self.pool = []
        self.cursor = 0

    def spawn(self, damage, pos, is_crit=False, is_headshot=False, damage_type=None):
        if not self.pool or damage <= 0.0:
            return
        item = self.pool[self.cursor]
        self.cursor = (self.cursor + 1) % len(self.pool)
        item.activate(damage, pos, is_crit=is_crit, is_headshot=is_headshot, damage_type=damage_type)

    def update(self, dt):
        for item in self.pool:
            if item.is_active:
                item.update(dt)

    def clear(self):
        for item in self.pool:
            item.is_active = False
            if hasattr(item, 'node') and item.node:
                item.node.hide()


def create_circle_fan_geom(radius, segments=36, color=(0.02, 0.05, 0.08, 0.78)):
    """원형 다크 글래스모피즘 메쉬 폴리곤 팬 생성"""
    format = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData('circle_fan', format, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, 'vertex')
    col = GeomVertexWriter(vdata, 'color')
    vertex.addData3(0, 0, 0)
    col.addData4(*color)
    for i in range(segments + 1):
        ang = 2.0 * math.pi * (i / segments)
        vertex.addData3(math.cos(ang) * radius, 0, math.sin(ang) * radius)
        col.addData4(*color)
    triangles = GeomTriangles(Geom.UHStatic)
    for i in range(1, segments + 1):
        triangles.addVertex(0)
        triangles.addVertex(i)
        triangles.addVertex(i + 1)
    geom = Geom(vdata)
    geom.addPrimitive(triangles)
    gnode = GeomNode('circle_fan_node')
    gnode.addGeom(geom)
    return gnode


def create_radar_rings_geom(radius):
    """전술 레이더 동심원 외곽 링 및 십자선 벡터 라인 생성"""
    ls = LineSegs("radar_rings")
    ls.setThickness(2.2)
    # Outer ring
    ls.setColor(0.18, 0.88, 0.98, 0.85)
    segments = 48
    for i in range(segments + 1):
        ang = 2.0 * math.pi * (i / segments)
        x = math.cos(ang) * radius
        z = math.sin(ang) * radius
        if i == 0:
            ls.moveTo(x, 0, z)
        else:
            ls.drawTo(x, 0, z)

    # 15m middle ring
    mid_r = radius * 0.45
    ls.setColor(0.18, 0.88, 0.98, 0.35)
    ls.setThickness(1.5)
    for i in range(segments + 1):
        ang = 2.0 * math.pi * (i / segments)
        x = math.cos(ang) * mid_r
        z = math.sin(ang) * mid_r
        if i == 0:
            ls.moveTo(x, 0, z)
        else:
            ls.drawTo(x, 0, z)

    # Crosshair axes
    ls.setColor(0.18, 0.88, 0.98, 0.30)
    ls.moveTo(-radius * 0.95, 0, 0)
    ls.drawTo(radius * 0.95, 0, 0)
    ls.moveTo(0, 0, -radius * 0.95)
    ls.drawTo(0, 0, radius * 0.95)
    return ls.create()


class TacticalCrosshair:
    """
    LineSegs 기반 전술 레티클 시스템.
    텍스처 카드(OnscreenImage)의 투명도 렌더링 결함으로 인한 검은 사각형 현상을 원천 방지하며,
    모든 해상도(FHD, QHD, 4K)에서 왜곡 없이 날카로운 벡터 조준선을 투영합니다.
    """
    def __init__(self, parent, **kwargs):
        self.root = parent.attachNewNode("tactical_crosshair")
        self.root.setBin("fixed", 25)
        self.root.setDepthTest(False)
        self.root.setDepthWrite(False)
        self.scale = 1.0
        self.base_pos = (0.0, 0.0, 0.0)

        # 다이내믹 탄퍼짐(블룸) 및 흔들림(셰이크) 상태 변수
        self.current_bloom = 1.0
        self.target_bloom = 1.0
        self.shake_timer = 0.0
        self.shake_duration = 0.18
        self.shake_magnitude = 0.0

        self._build_geometry()

    def _build_geometry(self):
        # 1-A. 고정 센터 닷 (중앙 초정밀 조준점 - 스케일 불변)
        ls_dot = LineSegs("reticle_center_dot")
        ls_dot.setColor(0.92, 0.96, 1.0, 0.95)
        ls_dot.setThickness(2.5)
        ls_dot.moveTo(0, 0, -0.0015)
        ls_dot.drawTo(0, 0, 0.0015)
        self.dot_geom = self.root.attachNewNode(ls_dot.create())

        # 1-B. 다이내믹 십자선 & 전술 브래킷 (탄퍼짐/이동/격발 시 외곽으로 팽창)
        ls = LineSegs("reticle_default")
        ls.setColor(0.92, 0.96, 1.0, 0.90)
        ls.setThickness(2.0)

        # 4방향 틱 (중앙 여백 확보)
        gap = 0.009
        t_len = 0.022
        # 상
        ls.moveTo(0, 0, gap)
        ls.drawTo(0, 0, gap + t_len)
        # 하
        ls.moveTo(0, 0, -gap)
        ls.drawTo(0, 0, -(gap + t_len))
        # 좌
        ls.moveTo(-gap, 0, 0)
        ls.drawTo(-(gap + t_len), 0, 0)
        # 우
        ls.moveTo(gap, 0, 0)
        ls.drawTo(gap + t_len, 0, 0)

        # 전술 코너 브래킷 [ ]
        b_pos = 0.040
        b_len = 0.010
        # 우상
        ls.moveTo(b_pos - b_len, 0, b_pos)
        ls.drawTo(b_pos, 0, b_pos)
        ls.drawTo(b_pos, 0, b_pos - b_len)
        # 좌상
        ls.moveTo(-b_pos + b_len, 0, b_pos)
        ls.drawTo(-b_pos, 0, b_pos)
        ls.drawTo(-b_pos, 0, b_pos - b_len)
        # 우하
        ls.moveTo(b_pos - b_len, 0, -b_pos)
        ls.drawTo(b_pos, 0, -b_pos)
        ls.drawTo(b_pos, 0, -b_pos + b_len)
        # 좌하
        ls.moveTo(-b_pos + b_len, 0, -b_pos)
        ls.drawTo(-b_pos, 0, -b_pos)
        ls.drawTo(-b_pos, 0, -b_pos + b_len)

        self.reticle_geom = self.root.attachNewNode(ls.create())
        self.default_geom = self.reticle_geom  # 하위 호환성 유지

        # 2. 적중(Hit) 피격 마커 (선홍색 X자 틱)
        ls_hit = LineSegs("reticle_hit")
        ls_hit.setColor(1.0, 0.22, 0.22, 0.95)
        ls_hit.setThickness(2.6)
        hs = 0.006
        he = 0.022
        ls_hit.moveTo(hs, 0, hs)
        ls_hit.drawTo(he, 0, he)
        ls_hit.moveTo(-hs, 0, hs)
        ls_hit.drawTo(-he, 0, he)
        ls_hit.moveTo(hs, 0, -hs)
        ls_hit.drawTo(he, 0, -he)
        ls_hit.moveTo(-hs, 0, -hs)
        ls_hit.drawTo(-he, 0, -he)
        self.hit_geom = self.root.attachNewNode(ls_hit.create())
        self.hit_geom.hide()

        # 3. 치명타(Crit) 피격 마커 (황금빛 스타버스트 및 다이아몬드)
        ls_crit = LineSegs("reticle_crit")
        ls_crit.setColor(1.0, 0.88, 0.15, 1.0)
        ls_crit.setThickness(3.0)
        cs = 0.008
        ce = 0.030
        ls_crit.moveTo(cs, 0, cs)
        ls_crit.drawTo(ce, 0, ce)
        ls_crit.moveTo(-cs, 0, cs)
        ls_crit.drawTo(-ce, 0, ce)
        ls_crit.moveTo(cs, 0, -cs)
        ls_crit.drawTo(ce, 0, -ce)
        ls_crit.moveTo(-cs, 0, -cs)
        ls_crit.drawTo(-ce, 0, -ce)
        d_len = 0.018
        ls_crit.moveTo(0, 0, d_len)
        ls_crit.drawTo(d_len * 0.45, 0, 0)
        ls_crit.drawTo(0, 0, -d_len)
        ls_crit.drawTo(-d_len * 0.45, 0, 0)
        ls_crit.drawTo(0, 0, d_len)
        self.crit_geom = self.root.attachNewNode(ls_crit.create())
        self.crit_geom.hide()

        # 4. 처치(Kill) 피격 마커 (강렬한 선홍색 대형 X자 킬 마커)
        ls_kill = LineSegs("reticle_kill")
        ls_kill.setColor(1.0, 0.15, 0.15, 1.0)
        ls_kill.setThickness(3.2)
        ks = 0.007
        ke = 0.026
        ls_kill.moveTo(ks, 0, ks)
        ls_kill.drawTo(ke, 0, ke)
        ls_kill.moveTo(-ks, 0, ks)
        ls_kill.drawTo(-ke, 0, ke)
        ls_kill.moveTo(ks, 0, -ks)
        ls_kill.drawTo(ke, 0, -ke)
        ls_kill.moveTo(-ks, 0, -ks)
        ls_kill.drawTo(-ke, 0, -ke)
        self.kill_geom = self.root.attachNewNode(ls_kill.create())
        self.kill_geom.hide()

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def isHidden(self):
        return self.root.isHidden()

    def setScale(self, s, *args):
        if isinstance(s, (int, float)):
            self.root.setScale(s, s, s)
        else:
            self.root.setScale(s)

    def getScale(self):
        return self.root.getScale()

    def setPos(self, x, y=None, z=None):
        if y is None and z is None:
            if hasattr(x, '__getitem__'):
                self.base_pos = (float(x[0]), float(x[1]), float(x[2]) if len(x) > 2 else 0.0)
            else:
                self.base_pos = (float(x), 0.0, 0.0)
        else:
            self.base_pos = (float(x), float(y if y is not None else 0.0), float(z if z is not None else 0.0))
        self.root.setPos(*self.base_pos)

    def getPos(self):
        return self.root.getPos()

    def setTransparency(self, mode):
        pass

    def setBin(self, bin_name, sort_order):
        self.root.setBin(bin_name, sort_order)

    def setText(self, text):
        pass

    def setFg(self, fg):
        pass

    def setImage(self, img_path):
        if 'crit' in str(img_path):
            self.trigger_hit(is_crit=True)
        elif 'hit' in str(img_path):
            self.trigger_hit(is_crit=False)
        else:
            self.reset_hit()

    def trigger_hit(self, is_crit=False, is_kill=False):
        if is_kill:
            self.hit_geom.hide()
            self.crit_geom.hide()
            if hasattr(self, 'kill_geom'):
                self.kill_geom.show()
        elif is_crit:
            if hasattr(self, 'kill_geom'):
                self.kill_geom.hide()
            self.hit_geom.hide()
            self.crit_geom.show()
        else:
            if hasattr(self, 'kill_geom'):
                self.kill_geom.hide()
            self.crit_geom.hide()
            self.hit_geom.show()

    def reset_hit(self):
        self.hit_geom.hide()
        self.crit_geom.hide()
        if hasattr(self, 'kill_geom'):
            self.kill_geom.hide()

    def trigger_hipfire_kick(self, kick_bloom=0.72, shake_mag=0.024, shake_dur=0.18):
        """지향사격(Hip-fire) 시 크로스헤어 격발 팽창 및 급격한 고주파 흔들림(Jitter Shake) 연출"""
        self.current_bloom = min(2.5, self.current_bloom + kick_bloom)
        self.shake_timer = shake_dur
        self.shake_duration = max(0.01, shake_dur)
        self.shake_magnitude = shake_mag

    def update(self, dt, is_moving=False, is_sprinting=False):
        """매 프레임 이동 상태에 따른 블룸 크기 조절 및 사격 후 반동 복구, 흔들림 감쇠"""
        if is_sprinting:
            move_bloom = 1.65
        elif is_moving:
            move_bloom = 1.25
        else:
            move_bloom = 1.0

        # 사격 반동으로 팽창된 블룸이 이동 목표치로 부드럽게 복구
        if self.current_bloom > move_bloom:
            self.current_bloom = max(move_bloom, self.current_bloom - 4.5 * dt)
        else:
            self.current_bloom = min(move_bloom, self.current_bloom + 3.0 * dt)

        # 조준선 외곽선에 블룸 스케일 적용 (센터 닷은 정밀 유지)
        if hasattr(self, 'reticle_geom') and not self.reticle_geom.isEmpty():
            self.reticle_geom.setScale(self.current_bloom, 1.0, self.current_bloom)
        elif hasattr(self, 'default_geom') and not self.default_geom.isEmpty():
            self.default_geom.setScale(self.current_bloom, 1.0, self.current_bloom)

        # 지향사격 반동 흔들림(Jitter Shake) 고주파 연출
        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - dt)
            progress = self.shake_timer / self.shake_duration
            cur_mag = self.shake_magnitude * (progress ** 1.1)
            jitter_x = random.uniform(-1.0, 1.0) * cur_mag
            jitter_z = random.uniform(-1.0, 1.0) * cur_mag
            bx, by, bz = self.base_pos
            self.root.setPos(bx + jitter_x, by, bz + jitter_z)
        else:
            self.root.setPos(*self.base_pos)


def create_damage_indicator_geom():
    """피격 방향을 가리키는 고해상도 붉은색 벡터 아크 및 전술 쉐브론 화살표"""
    ls = LineSegs("damage_direction_indicator")
    ls.setColor(1.0, 0.08, 0.08, 1.0)
    ls.setThickness(4.8)

    # 1. 외곽 곡선 아크 (-28도 ~ +28도, 반경 0.44)
    r_outer = 0.44
    steps = 14
    for i in range(steps):
        a1 = math.radians(-28.0 + (56.0 * i / steps))
        a2 = math.radians(-28.0 + (56.0 * (i + 1) / steps))
        ls.moveTo(math.sin(a1) * r_outer, 0, math.cos(a1) * r_outer)
        ls.drawTo(math.sin(a2) * r_outer, 0, math.cos(a2) * r_outer)

    # 2. 내곽 보조 아크 (-18도 ~ +18도, 반경 0.40)
    r_inner = 0.40
    steps_in = 10
    for i in range(steps_in):
        a1 = math.radians(-18.0 + (36.0 * i / steps_in))
        a2 = math.radians(-18.0 + (36.0 * (i + 1) / steps_in))
        ls.moveTo(math.sin(a1) * r_inner, 0, math.cos(a1) * r_inner)
        ls.drawTo(math.sin(a2) * r_inner, 0, math.cos(a2) * r_inner)

    # 3. 중앙 정점 전술 화살표 팁 (외부를 향해 뾰족하게 돌출)
    tip_r = 0.51
    ls.moveTo(-0.045, 0, 0.43)
    ls.drawTo(0.0, 0, tip_r)
    ls.drawTo(0.045, 0, 0.43)

    return ls.create()



ImageCrosshair = TacticalCrosshair


class UIManager:
    def __init__(self, base, loader, on_start, on_return_menu, on_exit, on_test_mode=None):
        self.base = base
        self.loader = loader
        self.on_start = on_start
        self.on_return_menu = on_return_menu
        self.on_exit = on_exit
        self.on_test_mode = on_test_mode

        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            self.rank_file = os.path.join(exe_dir, "rankings.json")
        else:
            self.rank_file = os.path.join(os.path.dirname(__file__), "rankings.json")

        # 폰트 로드
        try:
            self.korean_font = self.loader.loadFont('/c/Windows/Fonts/malgun.ttf')
        except Exception:
            self.korean_font = None

        self.font_kw = {"font": self.korean_font} if self.korean_font else {}
        self.btn_font_kw = {"text_font": self.korean_font} if self.korean_font else {}

        # 텍스트 변경 캐시 (Panda3D TextNode 불필요한 재빌드 방지)
        self._cached_timer_str = ""
        self._cached_timer_col = None
        self._cached_stamina_str = ""
        self._cached_stamina_col = None
        self._cached_hud_str = ""
        self._cached_ammo_str = ""
        self._cached_weapon_name = ""
        self._cached_door_str = ""
        self._cached_hp_str = ""
        self._cached_exp_str = ""

        # 상점 콜백 및 선택된 특성
        self.selected_upgrade = "ATTACK"
        self.on_shop_confirm = None
        self.on_escape_victory = None

        # 플로팅 대미지 오브젝트 풀 매니저 초기화
        render_root = getattr(self.base, 'render', None)
        self.floating_damage_mgr = FloatingDamageManager(render_root, font=self.korean_font) if render_root else None

        # UI 요소 빌드
        self._setup_hud()
        self._setup_tactical_radar()
        self._setup_pause_ui()
        self._setup_after_action_report_ui()
        self._setup_end_game_ui()
        self._setup_intro_ui()
        self._setup_rank_ui()
        self._setup_shop_ui()
        self._setup_inventory_ui()

    def _set_bar_percentage(self, fill_img, pct, cx, cz, hw, hh):
        """이미지 기반 프로그레스바의 가로 스케일 및 왼쪽 정렬 앵커 오프셋 계산"""
        pct = max(0.0, min(1.0, pct))
        if pct <= 0.005:
            fill_img.hide()
        else:
            fill_img.show()
            track_w = 2.0 * hw * 0.96
            x_left = cx - hw * 0.96
            cur_w = track_w * pct
            fill_img.setPos(x_left + cur_w / 2.0, 0, cz)
            fill_img.setScale(cur_w / 2.0, 1.0, hh * 0.76)

    def _setup_hud(self):
        """인게임 조준점 및 이미지 기반 HUD 요소 초기화"""
        # 1. 엠비언트 다크 호러 비네트 (화면 외곽 심도감, 16:9 1920x1080 와이드 풀스크린)
        self.vignette_dark = OnscreenImage(
            image="assets/ui/vignette_dark.png",
            pos=(0, 0, 0),
            scale=(1.80, 1, 1.0),
            parent=self.base.aspect2d
        )
        self.vignette_dark.setTransparency(TransparencyAttrib.MAlpha)
        self.vignette_dark.setBin("fixed", 1)

        # 2. 피격 핏자국 및 저체력 심장박동 맥동 비네트
        self.vignette_blood = OnscreenImage(
            image="assets/ui/vignette_blood.png",
            pos=(0, 0, 0),
            scale=(1.80, 1, 1.0),
            parent=self.base.aspect2d
        )
        self.vignette_blood.setTransparency(TransparencyAttrib.MAlpha)
        self.vignette_blood.setBin("fixed", 2)
        self.vignette_blood.setColorScale(1, 1, 1, 0.0)

        # 2-B. 불릿타임 시간 감속 일렉트릭 사이안 비네트 (전체 화면 시공간 왜곡 효과)
        self.vignette_bullet_time = OnscreenImage(
            image="assets/ui/vignette_dark.png",
            pos=(0, 0, 0),
            scale=(1.80, 1, 1.0),
            parent=self.base.aspect2d
        )
        self.vignette_bullet_time.setTransparency(TransparencyAttrib.MAlpha)
        self.vignette_bullet_time.setBin("fixed", 2)
        self.vignette_bullet_time.setColorScale(0.18, 0.85, 1.0, 0.0)
        self.vignette_bullet_time.hide()

        # 하위 호환용 damage_flash 프레임
        self.damage_flash = DirectFrame(
            frameColor=(0.85, 0.05, 0.05, 0.0),
            frameSize=(-2.0, 2.0, -2.0, 2.0),
            pos=(0, 0, 0)
        )
        self.damage_flash.setBin("fixed", 3)
        self.damage_flash_alpha = 0.0

        # 3. LineSegs 기반 무결점 전술 크로스헤어 (검은 배경 박스 원천 제거)
        self.crosshair = TacticalCrosshair(
            parent=self.base.aspect2d
        )
        self.crosshair.setBin("fixed", 25)
        self.crosshair_hit_timer = 0.0
        self.hit_marker_timer = 0.0

        # 3-2. 플레이어 피격 방향 전술 인디케이터 루트 및 활성 목록
        self.damage_dir_root = self.base.aspect2d.attachNewNode("damage_dir_root")
        self.damage_dir_root.setBin("fixed", 24)
        self.damage_indicators = []

        # 4. 상단 미션 생존 타이머 위젯 (중앙 상단 길잡이 삭제 및 타이머 중앙 정렬)
        self.panel_hud_top = None
        self.icon_radar = None
        self.hud_text = None

        self.timer_text = OnscreenText(
            text="[ 05:00 ]",
            pos=(0, 0.925),
            scale=0.042,
            fg=(0.25, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 5. 좌하단 플레이어 상태 HUD (HP, 스테미나, EXP, 유물, 퍽 배지) - 고가독성 스케일 & 통일 정렬
        # 5-1. 체력바
        self.icon_hp = OnscreenImage(
            image="assets/ui/icon_health.png",
            pos=(-1.65, 0, -0.340),
            scale=0.034,
            parent=self.base.aspect2d
        )
        self.icon_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_hp.setBin("fixed", 5)

        self.bar_frame_hp = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-1.32, 0, -0.340),
            scale=(0.28, 1, 0.025),
            parent=self.base.aspect2d
        )
        self.bar_frame_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_hp.setBin("fixed", 5)

        self.bar_fill_hp = OnscreenImage(
            image="assets/ui/bar_hp_fill.png",
            pos=(-1.32, 0, -0.340),
            scale=(0.27, 1, 0.019),
            parent=self.base.aspect2d
        )
        self.bar_fill_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_hp.setBin("fixed", 6)

        self.hp_text = OnscreenText(
            text="HP  100 / 100",
            pos=(-1.60, -0.310),
            scale=0.030,
            fg=(0.25, 1.0, 0.45, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-2. 스테미나바
        self.icon_stamina = OnscreenImage(
            image="assets/ui/icon_stamina.png",
            pos=(-1.65, 0, -0.415),
            scale=0.034,
            parent=self.base.aspect2d
        )
        self.icon_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_stamina.setBin("fixed", 5)

        self.bar_frame_stamina = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-1.32, 0, -0.415),
            scale=(0.28, 1, 0.025),
            parent=self.base.aspect2d
        )
        self.bar_frame_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_stamina.setBin("fixed", 5)

        self.bar_fill_stamina = OnscreenImage(
            image="assets/ui/bar_stamina_fill.png",
            pos=(-1.32, 0, -0.415),
            scale=(0.27, 1, 0.019),
            parent=self.base.aspect2d
        )
        self.bar_fill_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_stamina.setBin("fixed", 6)

        self.stamina_text = OnscreenText(
            text="STM  100%",
            pos=(-1.60, -0.385),
            scale=0.030,
            fg=(0.35, 0.95, 0.5, 0.95),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-3. 경험치바
        self.icon_exp = OnscreenImage(
            image="assets/ui/icon_exp.png",
            pos=(-1.65, 0, -0.490),
            scale=0.034,
            parent=self.base.aspect2d
        )
        self.icon_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_exp.setBin("fixed", 5)

        self.bar_frame_exp = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-1.32, 0, -0.490),
            scale=(0.28, 1, 0.025),
            parent=self.base.aspect2d
        )
        self.bar_frame_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_exp.setBin("fixed", 5)

        self.bar_fill_exp = OnscreenImage(
            image="assets/ui/bar_exp_fill.png",
            pos=(-1.32, 0, -0.490),
            scale=(0.27, 1, 0.019),
            parent=self.base.aspect2d
        )
        self.bar_fill_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_exp.setBin("fixed", 6)

        self.exp_text = OnscreenText(
            text="[LV. 1] EXP  0 / 100",
            pos=(-1.60, -0.460),
            scale=0.030,
            fg=(0.85, 0.70, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-4. 유물 배지
        self.icon_relic = OnscreenImage(
            image="assets/ui/icon_relic.png",
            pos=(-1.65, 0, -0.550),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_relic.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_relic.setBin("fixed", 5)

        self.relic_badge_text = OnscreenText(
            text="[보유 유물] 없음",
            pos=(-1.60, -0.560),
            scale=0.028,
            fg=(0.95, 0.75, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-5. 로그라이크 전술 퍽 배지 목록
        self.perk_badge_text = OnscreenText(
            text="[장착 퍽] 없음",
            pos=(-1.60, -0.610),
            scale=0.026,
            fg=(0.35, 0.90, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 6. 우하단 탄약 HUD 패널 (고대비 및 크기 확장)
        self.panel_hud_ammo = OnscreenImage(
            image="assets/ui/panel_hud_ammo.png",
            pos=(1.38, 0, -0.825),
            scale=(0.32, 1, 0.105),
            parent=self.base.aspect2d
        )
        self.panel_hud_ammo.setTransparency(TransparencyAttrib.MAlpha)
        self.panel_hud_ammo.setBin("fixed", 4)

        self.icon_ammo = OnscreenImage(
            image="assets/ui/icon_ammo.png",
            pos=(1.10, 0, -0.825),
            scale=0.038,
            parent=self.base.aspect2d
        )
        self.icon_ammo.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_ammo.setBin("fixed", 5)

        self.weapon_name_text = OnscreenText(
            text="[ .50 매그넘 데저트 이글 ]",
            pos=(1.66, -0.780),
            scale=0.035,
            fg=(0.40, 0.92, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ARight,
            mayChange=True,
            **self.font_kw
        )

        self.ammo_text = OnscreenText(
            text="탄약  7 / 7  [+28]",
            pos=(1.66, -0.828),
            scale=0.040,
            fg=(1.0, 0.90, 0.35, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ARight,
            mayChange=True,
            **self.font_kw
        )

        self.weapon_guide_text = OnscreenText(
            text="[Q / 휠] 무기교체  [Z,X,C,V] 선택",
            pos=(1.66, -0.875),
            scale=0.025,
            fg=(0.70, 0.78, 0.88, 0.85),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ARight,
            mayChange=False,
            **self.font_kw
        )

        # 7. 중앙 비상문 방어 프로그레스바 (하저드 스트라이프)
        self.bar_frame_defense = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(0, 0, 0.60),
            scale=(0.42, 1, 0.032),
            parent=self.base.aspect2d
        )
        self.bar_frame_defense.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_defense.setBin("fixed", 8)
        self.bar_frame_defense.hide()

        self.bar_fill_defense = OnscreenImage(
            image="assets/ui/bar_defense_fill.png",
            pos=(0, 0, 0.60),
            scale=(0.40, 1, 0.024),
            parent=self.base.aspect2d
        )
        self.bar_fill_defense.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_defense.setBin("fixed", 9)
        self.bar_fill_defense.hide()

        self.door_status_text = OnscreenText(
            text="",
            pos=(0, 0.66),
            scale=0.038,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.door_status_text.hide()

        # --- [ 거대 보스 전용 HP바 HUD (화면 최상단) ] ---
        self.boss_hud_frame = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.04, 0.05, 0.08, 0.92),
            frameSize=(-0.78, 0.78, -0.075, 0.075),
            relief=DGG.RIDGE,
            borderWidth=(0.004, 0.004),
            pos=(0, 0, 0.86)
        )
        self.boss_hud_frame.setBin("fixed", 20)
        self.boss_hud_frame.hide()

        self.boss_name_text = OnscreenText(
            text="[ ★ BOSS: 케이블 엔티티 - 심연의 지배자 ★ ]",
            parent=self.boss_hud_frame,
            pos=(0, 0.030),
            scale=0.035,
            fg=(1.0, 0.30, 0.30, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.boss_bar_bg = DirectFrame(
            parent=self.boss_hud_frame,
            frameColor=(0.10, 0.12, 0.15, 0.95),
            frameSize=(-0.70, 0.70, -0.016, 0.016),
            relief=DGG.FLAT,
            pos=(0, 0, -0.015)
        )

        self.boss_bar_fill = DirectFrame(
            parent=self.boss_hud_frame,
            frameColor=(0.25, 0.85, 1.0, 1.0),
            frameSize=(-0.70, 0.70, -0.014, 0.014),
            relief=DGG.FLAT,
            pos=(0, 0, -0.015)
        )

        self.boss_hp_text = OnscreenText(
            text="3500 / 3500 (100.0%)",
            parent=self.boss_hud_frame,
            pos=(0, -0.054),
            scale=0.024,
            fg=(1.0, 0.90, 0.90, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 알림/피격/획득 텍스트 백플레이트 및 고가독성 텍스트
        self.panel_hit_marker = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.03, 0.05, 0.08, 0.85),
            frameSize=(-0.58, 0.58, -0.045, 0.045),
            relief=DGG.RIDGE,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, -0.66)
        )
        self.panel_hit_marker.setBin("fixed", 7)
        self.panel_hit_marker.hide()

        self.hit_marker_text = OnscreenText(
            text="",
            pos=(0, -0.672),
            scale=0.036,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.blackout_banner = OnscreenText(
            text="[ ! 비상 경보: 정전 프로토콜 발동 ! ]\n기지 전력 차단! 붉은 비상등 가동 (몬스터 폭주 / 처치 보상 2배)",
            pos=(0, 0.74),
            scale=0.040,
            fg=(1.0, 0.15, 0.15, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.blackout_banner.hide()
        self.blackout_pulse_timer = 0.0

        # 인게임 전술 퀵슬롯 HUD 백플레이트 패널 (1920x1080 하단 중앙)
        self.panel_quickslot = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.04, 0.06, 0.09, 0.82),
            frameSize=(-0.84, 0.84, -0.044, 0.044),
            relief=DGG.RIDGE,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, -0.86)
        )
        self.panel_quickslot.setBin("fixed", 6)

        self.quickslot_text = OnscreenText(
            text="[1] 응급키트: 2개  |  [2] 아드레날린: 1개  |  [3] 탄약팩: 2개  |  [4] 수류탄: 1개  |  [Tab] 배낭",
            pos=(0, -0.872),
            scale=0.034,
            fg=(0.35, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.guide_text = OnscreenText(
            text="",
            pos=(0, -0.92),
            scale=0.024,
            fg=(0.9, 0.9, 0.8, 0.0),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )
        self.guide_text.hide()

        # 상호작용 프롬프트 백플레이트 패널 ([E] 전술 보급 상자 개봉 등)
        self.panel_interact = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.03, 0.05, 0.08, 0.88),
            frameSize=(-0.52, 0.52, -0.048, 0.048),
            relief=DGG.RIDGE,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, -0.42)
        )
        self.panel_interact.setBin("fixed", 8)
        self.panel_interact.hide()

        self.interact_prompt_text = OnscreenText(
            text="",
            pos=(0, -0.435),
            scale=0.040,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.interact_prompt_text.hide()

        # 스타일 킬 & 콤보 어나운서 배너 (화면 중앙 상단)
        self.style_kill_banner = OnscreenText(
            text="",
            pos=(0, 0.48),
            scale=0.048,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.style_kill_banner.hide()
        self.style_kill_timer = 0.0

        # 전술 스킬 쿨다운 HUD 백플레이트 패널 및 인디케이터
        self.panel_skills = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.04, 0.06, 0.09, 0.80),
            frameSize=(-0.34, 0.34, -0.030, 0.030),
            relief=DGG.RIDGE,
            borderWidth=(0.003, 0.003),
            pos=(1.38, 0, -0.665)
        )
        self.panel_skills.setBin("fixed", 6)

        self.skills_status_text = OnscreenText(
            text="[SPACE] 슬라이드: READY   |   [G] 수류탄: READY",
            pos=(1.38, -0.676),
            scale=0.028,
            fg=(0.35, 1.0, 0.65, 0.95),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.stage_clear_banner = OnscreenText(
            text="",
            pos=(0, 0.42),
            scale=0.055,
            fg=(0.3, 1.0, 0.5, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.stage_clear_banner.hide()

        # 불릿 타임 (시간 감속) HUD 배너 (화면 중앙 상단 네온 사이안)
        self.panel_bullet_time = DirectFrame(
            parent=self.base.aspect2d,
            frameColor=(0.02, 0.08, 0.14, 0.88),
            frameSize=(-0.45, 0.45, -0.040, 0.040),
            relief=DGG.RIDGE,
            borderWidth=(0.003, 0.003),
            pos=(0, 0, 0.78)
        )
        self.panel_bullet_time.setBin("fixed", 8)
        self.panel_bullet_time.hide()

        self.bullet_time_text = OnscreenText(
            text="[ BULLET TIME  0.35x ]",
            pos=(0, 0.768),
            scale=0.038,
            fg=(0.25, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.bullet_time_text.hide()

    def _setup_end_game_ui(self):
        """사망 및 승리 화면 UI"""
        self.game_over_banner = OnscreenText(
            text="사  망",
            pos=(0, 0.25),
            scale=0.085,
            fg=(0.95, 0.08, 0.08, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.game_over_desc = OnscreenText(
            text="기괴한 괴물에게 영혼을 잠식당했습니다...",
            pos=(0, 0.05),
            scale=0.032,
            fg=(0.88, 0.88, 0.88, 0.95),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.victory_banner = OnscreenText(
            text="탈  출  성  공",
            pos=(0, 0.25),
            scale=0.085,
            fg=(0.20, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )
        self.victory_desc = OnscreenText(
            text="비상 탈출구를 찾아 악몽의 미궁을 탈출했습니다!",
            pos=(0, 0.05),
            scale=0.032,
            fg=(0.92, 0.98, 0.92, 0.95),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.btn_game_menu = DirectButton(
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="메인 메뉴 (MENU)",
            pos=(-0.35, 0, -0.22),
            scale=(0.42, 1, 0.060),
            text_scale=((0.060 / 0.42) * 0.46, 0.46),
            text_pos=(0, -0.15),
            text_fg=(1.0, 1.0, 1.0, 1.0),
            command=self.on_return_menu,
            **self.btn_font_kw
        )
        self.btn_game_menu.setTransparency(TransparencyAttrib.MAlpha)

        self.btn_game_rank = DirectButton(
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="기록 랭킹 (RANK)",
            pos=(0.35, 0, -0.22),
            scale=(0.42, 1, 0.060),
            text_scale=((0.060 / 0.42) * 0.46, 0.46),
            text_pos=(0, -0.15),
            text_fg=(1.0, 0.9, 0.3, 1.0),
            command=self.show_rank_modal,
            **self.btn_font_kw
        )
        self.btn_game_rank.setTransparency(TransparencyAttrib.MAlpha)

        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()
        self.btn_game_menu.hide()
        self.btn_game_rank.hide()

    def _setup_intro_ui(self):
        """메인 인트로 타이틀 및 메뉴 버튼 (1920x1080 와이드 화면 비율 최적화)"""
        self.intro_frame = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.15, 1.15, -0.78, 0.78),
            image_scale=(1.15, 1.0, 0.78),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.intro_frame.setTransparency(TransparencyAttrib.MAlpha)

        self.intro_title = OnscreenText(
            text="LIMINAL BACKROOMS",
            parent=self.intro_frame,
            pos=(0, 0.52),
            scale=0.082,
            fg=(0.95, 0.95, 0.95, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_subtitle = OnscreenText(
            text="[ 5분 던전 크롤러 RPG : 심연의 미궁 ]",
            parent=self.intro_frame,
            pos=(0, 0.38),
            scale=0.034,
            fg=(0.95, 0.45, 0.20, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_desc = OnscreenText(
            text="미궁에 도사린 몬스터들을 처치하여 경험치를 획득하고 레벨업하세요.\n5분 안에 비상탈출구를 찾아 5초간 사수하면 상점에서 특성을 강화하고 다음 층으로 내려갑니다.",
            parent=self.intro_frame,
            pos=(0, 0.22),
            scale=0.026,
            fg=(0.85, 0.88, 0.92, 0.92),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.btn_start = DirectButton(
            parent=self.intro_frame,
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="START GAME",
            pos=(0, 0, 0.08),
            scale=(0.54, 1, 0.075),
            text_scale=((0.075 / 0.54) * 0.46, 0.46),
            text_pos=(0, -0.14),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self.on_start,
            **self.btn_font_kw
        )
        self.btn_start.setTransparency(TransparencyAttrib.MAlpha)

        self.btn_test = DirectButton(
            parent=self.intro_frame,
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="TEST MODE (사격 시험장)",
            pos=(0, 0, -0.06),
            scale=(0.54, 1, 0.075),
            text_scale=((0.075 / 0.54) * 0.44, 0.44),
            text_pos=(0, -0.14),
            text_fg=(0.35, 0.88, 1.0, 1.0),
            command=self.on_test_mode if self.on_test_mode else self.on_start,
            **self.btn_font_kw
        )
        self.btn_test.setTransparency(TransparencyAttrib.MAlpha)

        self.btn_rank = DirectButton(
            parent=self.intro_frame,
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="RANKING",
            pos=(0, 0, -0.20),
            scale=(0.54, 1, 0.075),
            text_scale=((0.075 / 0.54) * 0.46, 0.46),
            text_pos=(0, -0.14),
            text_fg=(1.0, 0.85, 0.25, 1.0),
            command=self.show_rank_modal,
            **self.btn_font_kw
        )
        self.btn_rank.setTransparency(TransparencyAttrib.MAlpha)

        self.btn_exit = DirectButton(
            parent=self.intro_frame,
            image=('assets/ui/btn_danger_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_danger_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="EXIT",
            pos=(0, 0, -0.34),
            scale=(0.54, 1, 0.075),
            text_scale=((0.075 / 0.54) * 0.46, 0.46),
            text_pos=(0, -0.14),
            text_fg=(1.0, 0.45, 0.45, 1.0),
            command=self.on_exit,
            **self.btn_font_kw
        )
        self.btn_exit.setTransparency(TransparencyAttrib.MAlpha)

    def _setup_rank_ui(self):
        """기록 랭킹 팝업 모달창 (1920x1080 와이드 최적화)"""
        self.rank_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.42, 1.42, -0.85, 0.85),
            image_scale=(1.42, 1.0, 0.85),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.rank_modal.setTransparency(TransparencyAttrib.MAlpha)

        self.rank_title = OnscreenText(
            text="[ 생존 & 탈출 기록 랭킹 (RANKING) ]",
            parent=self.rank_modal,
            pos=(0, 0.70),
            scale=0.048,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.rank_content = OnscreenText(
            text="기록을 불러오는 중...",
            parent=self.rank_modal,
            pos=(-1.20, 0.52),
            scale=0.028,
            fg=(0.92, 0.92, 0.92, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.btn_close_rank = DirectButton(
            parent=self.rank_modal,
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="닫기 (CLOSE)",
            pos=(0, 0, -0.70),
            scale=(0.44, 1, 0.060),
            text_scale=((0.060 / 0.44) * 0.48, 0.48),
            text_pos=(0, -0.15),
            text_fg=(0.95, 0.95, 0.95, 1.0),
            command=self.hide_rank_modal,
            **self.btn_font_kw
        )
        self.btn_close_rank.setTransparency(TransparencyAttrib.MAlpha)
        self.rank_modal.hide()

    def _set_hud_cluster_visible(self, visible: bool):
        """인게임 HUD 요소 일괄 표시/숨김 제어"""
        nodes = [
            getattr(self, 'vignette_dark', None),
            getattr(self, 'vignette_blood', None),
            getattr(self, 'vignette_bullet_time', None),
            getattr(self, 'crosshair', None),
            getattr(self, 'panel_hud_top', None),
            getattr(self, 'icon_radar', None),
            getattr(self, 'hud_text', None),
            getattr(self, 'timer_text', None),
            getattr(self, 'icon_hp', None),
            getattr(self, 'bar_frame_hp', None),
            getattr(self, 'bar_fill_hp', None),
            getattr(self, 'hp_text', None),
            getattr(self, 'icon_stamina', None),
            getattr(self, 'bar_frame_stamina', None),
            getattr(self, 'bar_fill_stamina', None),
            getattr(self, 'stamina_text', None),
            getattr(self, 'icon_exp', None),
            getattr(self, 'bar_frame_exp', None),
            getattr(self, 'bar_fill_exp', None),
            getattr(self, 'exp_text', None),
            getattr(self, 'icon_relic', None),
            getattr(self, 'relic_badge_text', None),
            getattr(self, 'perk_badge_text', None),
            getattr(self, 'panel_hud_ammo', None),
            getattr(self, 'icon_ammo', None),
            getattr(self, 'weapon_name_text', None),
            getattr(self, 'ammo_text', None),
            getattr(self, 'weapon_guide_text', None),
            getattr(self, 'panel_skills', None),
            getattr(self, 'skills_status_text', None),
            getattr(self, 'panel_quickslot', None),
            getattr(self, 'quickslot_text', None),
            getattr(self, 'radar_root', None),
        ]
        for n in nodes:
            if n is not None:
                if visible:
                    n.show()
                else:
                    n.hide()
        if not visible:
            if hasattr(self, 'bar_frame_defense') and self.bar_frame_defense:
                self.bar_frame_defense.hide()
            if hasattr(self, 'bar_fill_defense') and self.bar_fill_defense:
                self.bar_fill_defense.hide()
            if hasattr(self, 'door_status_text') and self.door_status_text:
                self.door_status_text.hide()
            if hasattr(self, 'panel_interact') and self.panel_interact:
                self.panel_interact.hide()
            if hasattr(self, 'interact_prompt_text') and self.interact_prompt_text:
                self.interact_prompt_text.hide()
            if hasattr(self, 'panel_hit_marker') and self.panel_hit_marker:
                self.panel_hit_marker.hide()
            if hasattr(self, 'hit_marker_text') and self.hit_marker_text:
                self.hit_marker_text.setText("")
            if hasattr(self, 'style_kill_banner') and self.style_kill_banner:
                self.style_kill_banner.hide()
            if hasattr(self, 'bullet_time_text') and self.bullet_time_text:
                self.bullet_time_text.hide()
            if hasattr(self, 'panel_bullet_time') and self.panel_bullet_time:
                self.panel_bullet_time.hide()
            if hasattr(self, 'inv_modal') and self.inv_modal:
                self.inv_modal.hide()

    def show_intro(self):
        """인트로 화면 표시"""
        self.hide_all_ingame()
        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()
        self.btn_game_menu.hide()
        self.btn_game_rank.hide()
        self.rank_modal.hide()
        self.intro_frame.show()

    def start_game_ui(self):
        """게임 시작 시 인게임 HUD 표시"""
        self.intro_frame.hide()
        self.rank_modal.hide()
        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()
        self.btn_game_menu.hide()
        self.btn_game_rank.hide()
        self._set_hud_cluster_visible(True)

    def hide_all_ingame(self):
        """인게임 HUD 전체 숨김"""
        self._set_hud_cluster_visible(False)
        self.hit_marker_text.setText("")
        self.stage_clear_banner.hide()
        for ind in self.damage_indicators:
            if ind.get("node") and not ind["node"].isEmpty():
                ind["node"].removeNode()
        self.damage_indicators = []

    def show_hit_marker(self, text, color=None, fg=None):
        """피격/적중/알림 표시"""
        c = fg if fg is not None else (color if color is not None else (1.0, 0.85, 0.2, 1.0))
        self.hit_marker_text.setText(text)
        self.hit_marker_text.setFg(c)
        if text:
            if hasattr(self, 'panel_hit_marker') and self.panel_hit_marker:
                self.panel_hit_marker.show()
            self.hit_marker_timer = 1.6
        else:
            if hasattr(self, 'panel_hit_marker') and self.panel_hit_marker:
                self.panel_hit_marker.hide()
            self.hit_marker_timer = 0.0

    def show_damage_direction(self, source_pos, player_pos, camera_heading):
        """플레이어 피격 시 공격자가 위치한 3D 월드 방향을 실시간 추적하는 붉은색 전술 인디케이터 표시"""
        if source_pos is None or player_pos is None:
            return

        sx = getattr(source_pos, 'x', source_pos[0])
        sy = getattr(source_pos, 'y', source_pos[1])
        px = player_pos[0]
        py = player_pos[1]

        dx = sx - px
        dy = sy - py
        if math.hypot(dx, dy) < 1e-4:
            return

        node = self.damage_dir_root.attachNewNode(create_damage_indicator_geom())
        node.setLightOff()

        world_bearing = math.degrees(math.atan2(dx, dy))
        rel_angle = (world_bearing + camera_heading) % 360.0
        node.setR(rel_angle)

        if len(self.damage_indicators) >= 4:
            oldest = self.damage_indicators.pop(0)
            if oldest.get("node") and not oldest["node"].isEmpty():
                oldest["node"].removeNode()

        self.damage_indicators.append({
            "node": node,
            "source": (sx, sy),
            "timer": 1.4,
            "max_timer": 1.4
        })

    def trigger_player_damage_flash(self, intensity=0.60):
        """플레이어 피격 시 화면 붉은 핏빛 비네트 효과"""
        self.damage_flash_alpha = intensity
        self.damage_flash['frameColor'] = (0.85, 0.05, 0.05, self.damage_flash_alpha)
        if hasattr(self, 'vignette_blood') and self.vignette_blood:
            self.vignette_blood.setColorScale(1, 1, 1, self.damage_flash_alpha)

    def trigger_crosshair_hit(self, is_kill=False, is_crit=False):
        """몬스터 타격 시 크로스헤어 적중 마커 표시 (화면을 가리지 않는 최소한의 모던 FPS 직관적 피드백)"""
        self.crosshair_hit_timer = 0.18 if is_kill else (0.15 if is_crit else 0.11)
        if hasattr(self.crosshair, 'trigger_hit'):
            self.crosshair.trigger_hit(is_crit=is_crit, is_kill=is_kill)
        elif hasattr(self.crosshair, 'setImage'):
            if is_kill or is_crit:
                self.crosshair.setImage("assets/ui/crosshair_crit.png")
                self.crosshair.setScale(0.054)
            else:
                self.crosshair.setImage("assets/ui/crosshair_hit.png")
                self.crosshair.setScale(0.046)

    def set_crosshair_visible(self, visible: bool):
        """정밀 조준(ADS) 시 크로스헤어 표시/숨김 제어"""
        if hasattr(self, 'crosshair') and self.crosshair:
            if visible:
                self.crosshair.show()
            else:
                self.crosshair.hide()

    def trigger_low_hp_pulse(self, intensity=0.40):
        """체력 30 미만 빈사 상태 시 심장박동 화면 붉은 비네트 펄스"""
        self.damage_flash_alpha = max(self.damage_flash_alpha, intensity)
        self.damage_flash['frameColor'] = (0.75, 0.04, 0.04, self.damage_flash_alpha)
        if hasattr(self, 'vignette_blood') and self.vignette_blood:
            self.vignette_blood.setColorScale(1, 1, 1, self.damage_flash_alpha)

    def trigger_hipfire_kick(self, kick_bloom=0.72, shake_mag=0.024, shake_dur=0.18):
        """지향사격(Hip-fire) 시 크로스헤어 격발 팽창 및 고주파 흔들림(Jitter Shake) 발동"""
        if hasattr(self, 'crosshair') and hasattr(self.crosshair, 'trigger_hipfire_kick'):
            self.crosshair.trigger_hipfire_kick(kick_bloom=kick_bloom, shake_mag=shake_mag, shake_dur=shake_dur)

    def update(self, dt, player_pos=None, camera_heading=None, is_moving=False, is_sprinting=False):
        """HUD 실시간 애니메이션 (피격 플래시/방향 인디케이터 페이드아웃, 크로스헤어 블룸/흔들림 복구, 정전 경보 맥동)"""
        # 크로스헤어 다이내믹 블룸 및 반동 흔들림 갱신
        if hasattr(self, 'crosshair') and hasattr(self.crosshair, 'update'):
            self.crosshair.update(dt, is_moving=is_moving, is_sprinting=is_sprinting)
        # 피격 방향 인디케이터 갱신 (실시간 카메라 회전 연동 및 페이드아웃)
        for ind in self.damage_indicators[:]:
            ind["timer"] -= dt
            if ind["timer"] <= 0.0:
                if ind.get("node") and not ind["node"].isEmpty():
                    ind["node"].removeNode()
                self.damage_indicators.remove(ind)
                continue

            alpha = max(0.0, ind["timer"] / ind["max_timer"])
            if ind.get("node") and not ind["node"].isEmpty():
                ind["node"].setColorScale(1.0, 1.0, 1.0, alpha)
                if player_pos is not None and camera_heading is not None:
                    dx = ind["source"][0] - player_pos[0]
                    dy = ind["source"][1] - player_pos[1]
                    world_bearing = math.degrees(math.atan2(dx, dy))
                    rel_angle = (world_bearing + camera_heading) % 360.0
                    ind["node"].setR(rel_angle)

        if self.damage_flash_alpha > 0.0:
            self.damage_flash_alpha = max(0.0, self.damage_flash_alpha - dt * 2.5)
            self.damage_flash['frameColor'] = (0.85, 0.05, 0.05, self.damage_flash_alpha)
            if hasattr(self, 'vignette_blood') and self.vignette_blood:
                self.vignette_blood.setColorScale(1, 1, 1, self.damage_flash_alpha)

        if self.crosshair_hit_timer > 0.0:
            self.crosshair_hit_timer = max(0.0, self.crosshair_hit_timer - dt)
            if self.crosshair_hit_timer <= 0.0:
                if hasattr(self.crosshair, 'reset_hit'):
                    self.crosshair.reset_hit()
                elif hasattr(self.crosshair, 'setImage'):
                    self.crosshair.setImage("assets/ui/crosshair_default.png")
                    self.crosshair.setScale(0.038)

        if self.hit_marker_timer > 0.0:
            self.hit_marker_timer -= dt
            if self.hit_marker_timer <= 0.0:
                self.hit_marker_text.setText("")
                if hasattr(self, 'panel_hit_marker') and self.panel_hit_marker:
                    self.panel_hit_marker.hide()

        if hasattr(self, 'style_kill_timer') and self.style_kill_timer > 0.0:
            self.style_kill_timer = max(0.0, self.style_kill_timer - dt)
            if self.style_kill_timer <= 0.0 and hasattr(self, 'style_kill_banner'):
                self.style_kill_banner.hide()

        if hasattr(self, 'blackout_banner') and not self.blackout_banner.isHidden():
            self.blackout_pulse_timer += dt * 6.5
            alpha = 0.55 + 0.45 * math.sin(self.blackout_pulse_timer)
            self.blackout_banner.setFg((1.0, 0.15, 0.15, alpha))

        # 플로팅 대미지 폰트 애니메이션 갱신
        if hasattr(self, 'floating_damage_mgr') and self.floating_damage_mgr:
            self.floating_damage_mgr.update(dt)

        # 전술 레이더 스위프 빔 회전 애니메이션
        if hasattr(self, 'radar_sweep_node') and self.radar_sweep_node and not self.radar_sweep_node.isEmpty():
            self.radar_sweep_angle = (getattr(self, 'radar_sweep_angle', 0.0) - dt * 200.0) % 360.0
            self.radar_sweep_node.setR(self.radar_sweep_angle)

    def show_style_kill(self, title, bonus_str="", color=(1.0, 0.85, 0.2, 1.0)):
        """스타일 킬 / 콤보 어나운서 팝업 표시"""
        display_text = f"{title}   {bonus_str}" if bonus_str else title
        self.style_kill_banner.setText(display_text)
        self.style_kill_banner.setFg(color)
        self.style_kill_banner.show()
        self.style_kill_timer = 1.8

    def update_skills_hud(self, slide_ready, grenade_param=0.0, grenade_max=9.0, grenade_count=None):
        """슬라이드 및 수류탄 잔여 수량/상태 실시간 텍스트 갱신"""
        slide_str = "READY" if slide_ready else "COOL"

        if grenade_count is not None:
            g_cnt = grenade_count
        elif isinstance(grenade_param, int):
            g_cnt = grenade_param
        else:
            g_cnt = None

        if g_cnt is not None:
            if g_cnt > 0:
                gr_str = f"x{g_cnt} (투척 가능)"
                is_ready = True
            else:
                gr_str = "0개 (소진)"
                is_ready = False
        else:
            if grenade_param <= 0.0:
                gr_str = "READY"
                is_ready = True
            else:
                gr_str = f"{grenade_param:.1f}s"
                is_ready = False

        txt = f"[SPACE] 슬라이드: {slide_str}   |   [G] 수류탄: {gr_str}"
        if txt != getattr(self, '_cached_skills_txt', ''):
            self.skills_status_text.setText(txt)
            self._cached_skills_txt = txt
            if slide_ready and is_ready:
                self.skills_status_text.setFg((0.35, 1.0, 0.65, 1.0))
            elif not is_ready:
                self.skills_status_text.setFg((1.0, 0.45, 0.35, 1.0))
            else:
                self.skills_status_text.setFg((1.0, 0.85, 0.35, 1.0))

    def show_interact_prompt(self, text="[ E ] 전술 보급 상자 개봉"):
        """현장 상호작용 가능한 물체 접근 시 프롬프트 표시"""
        self.interact_prompt_text.setText(text)
        self.interact_prompt_text.show()
        if hasattr(self, 'panel_interact') and self.panel_interact:
            self.panel_interact.show()

    def hide_interact_prompt(self):
        """상호작용 범위 벗어남 시 프롬프트 숨김"""
        self.interact_prompt_text.hide()
        if hasattr(self, 'panel_interact') and self.panel_interact:
            self.panel_interact.hide()

    def show_blackout_warning(self):
        """정전 프로토콜 발동 경고 배너 표시"""
        self.blackout_pulse_timer = 0.0
        self.blackout_banner.show()

    def hide_blackout_warning(self):
        """정전 프로토콜 종료 후 배너 숨김"""
        self.blackout_banner.hide()

    def update_relic_badges(self, relic_ids):
        """플레이어가 획득한 저주받은 유물 목록 HUD 텍스트 갱신"""
        if not relic_ids:
            self.relic_badge_text.setText("[보유 유물] 없음")
            self.relic_badge_text.setFg((0.6, 0.6, 0.6, 0.8))
        else:
            names = [f"{CURSED_RELICS[rid]['icon']} {CURSED_RELICS[rid]['name']}" for rid in relic_ids if rid in CURSED_RELICS]
            self.relic_badge_text.setText(f"[유물]  {'  '.join(names)}")
            self.relic_badge_text.setFg((0.95, 0.75, 1.0, 1.0))

    def update_perk_badges(self, perk_ids, perk_levels=None):
        """플레이어가 획득한 로그라이크 전술 퍽 HUD 텍스트 갱신"""
        if not hasattr(self, 'perk_badge_text') or not self.perk_badge_text:
            return
        if not perk_ids:
            self.perk_badge_text.setText("[장착 퍽] 없음")
            self.perk_badge_text.setFg((0.6, 0.6, 0.6, 0.8))
            return

        if perk_levels is None:
            player = getattr(self, 'shop_player', None)
            if not player and hasattr(self, 'base'):
                player = getattr(self.base, 'player', None)
            perk_levels = getattr(player, 'perk_levels', None) if player else None

        names = []
        for pid in perk_ids:
            if pid in PERK_CATALOG:
                lvl = perk_levels.get(pid, 1) if isinstance(perk_levels, dict) else 1
                names.append(f"{PERK_CATALOG[pid]['icon']} {PERK_CATALOG[pid]['name']} Lv.{lvl}")
        self.perk_badge_text.setText(f"[퍽]  {'  '.join(names)}")
        self.perk_badge_text.setFg((0.35, 0.90, 1.0, 1.0))

    def show_boss_hp_bar(self, boss_name="[ ★ BOSS: 케이블 엔티티 - 심연의 지배자 ★ ]", hp=None, max_hp=None):
        """보스 출현 시 상단 전용 체력바 표시"""
        if hasattr(self, 'boss_hud_frame') and self.boss_hud_frame:
            self.boss_name_text.setText(boss_name)
            self.boss_hud_frame.show()
            if hp is not None and max_hp is not None:
                self.update_boss_hp(hp, max_hp)

    def update_boss_hp(self, hp, max_hp, phase=1):
        """보스 체력 및 페이즈 실시간 갱신"""
        if not hasattr(self, 'boss_hud_frame') or not self.boss_hud_frame:
            return
        if self.boss_hud_frame.isHidden():
            self.boss_hud_frame.show()

        pct = max(0.0, min(1.0, hp / max(1.0, max_hp)))
        fill_width = 1.40 * pct
        self.boss_bar_fill["frameSize"] = (-0.70, -0.70 + fill_width, -0.014, 0.014)

        if phase == 2:
            self.boss_bar_fill["frameColor"] = (1.0, 0.15, 0.15, 1.0)
            self.boss_name_text.setText("[ ★ BOSS: 케이블 엔티티 - BERSERK 폭주 ★ ]")
            self.boss_name_text.setFg((1.0, 0.20, 0.20, 1.0))
        else:
            self.boss_bar_fill["frameColor"] = (0.25, 0.85, 1.0, 1.0)
            self.boss_name_text.setText("[ ★ BOSS: 케이블 엔티티 - 심연의 지배자 ★ ]")
            self.boss_name_text.setFg((0.40, 0.90, 1.0, 1.0))

        self.boss_hp_text.setText(f"{int(hp)} / {int(max_hp)} ({pct*100:.1f}%)")

    def hide_boss_hp_bar(self):
        """보스 사망 시 상단 체력바 숨김"""
        if hasattr(self, 'boss_hud_frame') and self.boss_hud_frame:
            self.boss_hud_frame.hide()

    def show_stage_banner(self, text, color=(0.3, 1.0, 0.5, 1.0)):
        """스테이지 클리어/시작 배너 표시"""
        self.stage_clear_banner.setText(text)
        self.stage_clear_banner.setFg(color)
        self.stage_clear_banner.show()

    def hide_stage_banner(self):
        self.stage_clear_banner.hide()

    def show_game_over(self, reason_text="기괴한 괴물에게 영혼을 잠식당했습니다..."):
        """게임 오버 화면 표시"""
        self.hide_all_ingame()
        self.game_over_desc.setText(reason_text)
        self.game_over_banner.show()
        self.game_over_desc.show()
        self.btn_game_menu.show()
        self.btn_game_rank.show()

    def show_victory(self, desc_text="비상 탈출구를 찾아 악몽의 미궁을 탈출했습니다!"):
        """탈출 성공 화면 표시"""
        self.hide_all_ingame()
        self.victory_desc.setText(desc_text)
        self.victory_banner.show()
        self.victory_desc.show()
        self.btn_game_menu.show()
        self.btn_game_rank.show()

    # --- 텍스트 및 이미지 기반 HUD 고속 업데이트 ---
    def update_timer(self, time_left, stage=1):
        mins = int(time_left) // 60
        secs = int(time_left) % 60
        t_str = f"{mins:02d}:{secs:02d}"

        if time_left >= 9000.0:
            col = (0.35, 0.90, 1.0, 1.0)
            msg = "TEST MODE"
        elif time_left <= 10.0:
            flash = (int(time_left * 4) % 2 == 0)
            col = (1.0, 0.2, 0.2, 1.0) if flash else (1.0, 0.8, 0.8, 1.0)
            msg = f"! {t_str} !"
        elif time_left <= 25.0:
            col = (1.0, 0.85, 0.2, 1.0)
            msg = t_str
        else:
            col = (0.25, 0.95, 0.45, 1.0)
            msg = t_str

        if msg != self._cached_timer_str:
            self.timer_text.setText(msg)
            self._cached_timer_str = msg
        if col != self._cached_timer_col:
            self.timer_text.setFg(col)
            self._cached_timer_col = col

    def set_bullet_time_hud(self, is_active, time_left=0.0):
        """불릿 타임 (시간 감속) HUD 배너 및 일렉트릭 사이안 시공간 비네트 실시간 갱신"""
        if is_active and time_left > 0.0:
            pulse = 0.52 + 0.18 * math.sin(time.time() * 9.0)
            if hasattr(self, 'vignette_bullet_time') and self.vignette_bullet_time:
                self.vignette_bullet_time.setColorScale(0.18, 0.85, 1.0, pulse)
                self.vignette_bullet_time.show()
            self.bullet_time_text.setText(f">> [ BULLET TIME : {time_left:.1f}s (0.35x) ] <<")
            self.bullet_time_text.show()
            self.panel_bullet_time.show()
        else:
            if hasattr(self, 'vignette_bullet_time') and self.vignette_bullet_time:
                self.vignette_bullet_time.setColorScale(0.18, 0.85, 1.0, 0.0)
                self.vignette_bullet_time.hide()
            self.bullet_time_text.hide()
            self.panel_bullet_time.hide()

    def update_ammo(self, ammo, max_ammo, reserve_ammo=0, overcharge_rounds=0, weapon_name=None):
        if weapon_name and hasattr(self, 'weapon_name_text') and self.weapon_name_text:
            if weapon_name != getattr(self, '_cached_weapon_name', ''):
                self.weapon_name_text.setText(f"[ {weapon_name} ]")
                self._cached_weapon_name = weapon_name

        if overcharge_rounds > 0:
            msg = f"★오버차지: {overcharge_rounds}발★  {ammo}/{max_ammo} [+{reserve_ammo}]"
            col = (0.25, 0.95, 1.0, 1.0)
        elif ammo == 0:
            msg = f"탄약  0 / {max_ammo}  [ R 장전 필요! ]"
            col = (1.0, 0.20, 0.20, 1.0)
        elif ammo <= 3:
            msg = f"탄약  {ammo} / {max_ammo}  [+{reserve_ammo}] (R)"
            col = (1.0, 0.45, 0.25, 1.0)
        elif reserve_ammo > 0:
            msg = f"탄약  {ammo} / {max_ammo}  [+{reserve_ammo}]"
            col = (1.0, 0.90, 0.35, 1.0)
        else:
            msg = f"탄약  {ammo} / {max_ammo}"
            col = (1.0, 0.90, 0.35, 1.0)

        if msg != self._cached_ammo_str:
            self.ammo_text.setText(msg)
            self._cached_ammo_str = msg
        self.ammo_text.setFg(col)

    def update_stamina(self, stamina, max_stamina, is_sprinting=False, is_exhausted=False):
        pct = max(0.0, min(1.0, stamina / max(1.0, max_stamina)))
        self._set_bar_percentage(self.bar_fill_stamina, pct, -1.32, -0.415, 0.28, 0.025)

        stamina_pct = int(pct * 100)
        if is_exhausted:
            msg = f"STM  {stamina_pct}% (탈진!)"
            col = (1.0, 0.25, 0.25, 1.0)
        elif is_sprinting:
            msg = f"STM  {stamina_pct}% (질주)"
            col = (1.0, 0.85, 0.2, 1.0)
        else:
            msg = f"STM  {stamina_pct}%"
            col = (0.35, 0.95, 0.5, 0.95)

        if msg != self._cached_stamina_str:
            self.stamina_text.setText(msg)
            self._cached_stamina_str = msg
        if col != self._cached_stamina_col:
            self.stamina_text.setFg(col)
            self._cached_stamina_col = col

    def update_hp_exp(self, hp, max_hp, exp, exp_to_next, level=1, stat_points=0, pending_perks=0):
        pct_hp = max(0.0, min(1.0, hp / max(1.0, max_hp)))
        self._set_bar_percentage(self.bar_fill_hp, pct_hp, -1.32, -0.340, 0.28, 0.025)
        msg_hp = f"HP  {int(hp)} / {int(max_hp)}"
        if msg_hp != self._cached_hp_str:
            self.hp_text.setText(msg_hp)
            if pct_hp <= 0.25:
                self.hp_text.setFg((1.0, 0.25, 0.25, 1.0))
            elif pct_hp <= 0.55:
                self.hp_text.setFg((1.0, 0.85, 0.2, 1.0))
            else:
                self.hp_text.setFg((0.25, 1.0, 0.45, 1.0))
            self._cached_hp_str = msg_hp

        pct_exp = max(0.0, min(1.0, exp / max(1.0, exp_to_next)))
        self._set_bar_percentage(self.bar_fill_exp, pct_exp, -1.32, -0.490, 0.28, 0.025)
        perk_tag = f"  ★ [퍽 선택 가능({pending_perks})] ★" if pending_perks > 0 else ""
        msg_exp = f"[LV.{level}] EXP  {int(exp)} / {int(exp_to_next)}{perk_tag}"
        if msg_exp != self._cached_exp_str:
            self.exp_text.setText(msg_exp)
            if pending_perks > 0:
                self.exp_text.setFg((1.0, 0.90, 0.30, 1.0))
            else:
                self.exp_text.setFg((0.85, 0.70, 1.0, 1.0))
            self._cached_exp_str = msg_exp

    def update_hud(self, px, py, escape_pos=None, heading=0.0):
        """중앙 상단 길잡이 삭제 완료 (우측 상단 원형 전술 레이더 위젯으로 통합 대체)"""
        pass

    def update_door_status(self, msg, fg=None, show=True):
        if show:
            if not self.door_status_text.isHidden() and msg == self._cached_door_str:
                return
            self.door_status_text.setText(msg)
            self._cached_door_str = msg
            if fg is not None:
                self.door_status_text.setFg(fg)
            self.door_status_text.show()
            self.bar_frame_defense.show()

            # "비상문 개방 중: 3.5s / 5.0s" 추출하여 하저드바 비율 갱신
            if "개방 중:" in msg and "/ 5.0s" in msg:
                try:
                    sec_str = msg.split("개방 중:")[1].split("s")[0].strip()
                    sec = float(sec_str)
                    pct = max(0.0, min(1.0, sec / 5.0))
                    self._set_bar_percentage(self.bar_fill_defense, pct, 0, 0.60, 0.42, 0.032)
                except Exception:
                    pass
            elif "중단" in msg:
                self._set_bar_percentage(self.bar_fill_defense, 0.0, 0, 0.60, 0.42, 0.032)
        else:
            if not self.door_status_text.isHidden():
                self.door_status_text.hide()
                self._cached_door_str = ""
            self.bar_frame_defense.hide()
            self.bar_fill_defense.hide()

    # --- 랭킹 입출력 관리 ---
    def load_rankings(self):
        if os.path.exists(self.rank_file):
            try:
                with open(self.rank_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"랭킹 로드 오류: {e}")
        return []

    def save_rank_record(self, result_type, success, time_elapsed, time_left, ammo_left, stage=1, reserve_ammo=0, max_ammo=12):
        rec = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stage": stage,
            "result": result_type,
            "success": success,
            "time_elapsed": round(time_elapsed, 1),
            "time_left": round(time_left, 1),
            "ammo_left": ammo_left,
            "reserve_ammo": reserve_ammo,
            "ammo_used": max_ammo - ammo_left
        }
        records = self.load_rankings()
        records.append(rec)
        try:
            with open(self.rank_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"랭킹 저장 실패: {e}")

    def show_rank_modal(self):
        records = self.load_rankings()
        escapes = [r for r in records if r.get("success", False)]
        escapes.sort(key=lambda r: r.get("time_elapsed", 9999))
        recent = list(reversed(records))[:6]

        lines = ["=== [ 탈출 성공 명예의 전당 (최단 시간 TOP 5) ] ==="]
        if escapes:
            for i, r in enumerate(escapes[:5], 1):
                stg = r.get('stage', 1)
                t_el = r.get('time_elapsed', 0)
                ammo = r.get('ammo_left', 0)
                res = r.get('reserve_ammo', 0)
                ts = r.get('timestamp', '')
                lines.append(f"  #{i}위 | STAGE {stg} | 탈출 시간: {t_el:.1f}초 | 탄약: {ammo}/12 (예비: {res}) | {ts}")
        else:
            lines.append("  아직 탈출 성공 기록이 없습니다. 최초로 탈출에 성공해보세요!")

        lines.append("\n=== [ 최근 플레이 도전 기록 (최근 6회) ] ===")
        if recent:
            for r in recent:
                stg = r.get('stage', 1)
                res_desc = r.get('result', '기록 없음')
                t_el = r.get('time_elapsed', 0)
                ammo = r.get('ammo_left', 0)
                res_am = r.get('reserve_ammo', 0)
                ts = r.get('timestamp', '')
                lines.append(f"  • [STAGE {stg} | {res_desc}]  진행: {t_el:.1f}초 | 탄약: {ammo}/12 (예비: {res_am}) | {ts}")
        else:
            lines.append("  플레이 기록이 없습니다.")

        self.rank_content.setText("\n".join(lines))
        self.rank_modal.show()
        self.intro_frame.hide()

    def hide_rank_modal(self):
        self.rank_modal.hide()
        if not self.btn_game_menu.isHidden():
            pass  # 게임 오버/승리 화면 상태 유지
        else:
            self.intro_frame.show()

    # --- [로그라이크 전술 퍽(Perk) 3-Card 선택 모달 시스템 (1920x1080 FHD 최적화)] ---
    def _setup_shop_ui(self):
        self.shop_player = None
        self.shop_combat = None
        self.on_shop_confirm = None
        self.on_escape_victory = None
        self.offered_perks = []
        self.selected_perk_idx = -1

        self.shop_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.62, 1.62, -0.92, 0.92),
            image_scale=(1.62, 1.0, 0.92),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.shop_modal.setTransparency(TransparencyAttrib.MAlpha)

        self.shop_title = OnscreenText(
            text="[ ★ ROGUELIKE PERK PROTOCOL : 전술 퍽 선택 ★ ]",
            parent=self.shop_modal,
            pos=(0, 0.74),
            scale=0.042,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.shop_desc = OnscreenText(
            text="심연의 미궁을 돌파하기 위한 전술 강화 퍽을 1장 선택하세요 (키보드 [1], [2], [3] 번호키 또는 마우스 클릭)",
            parent=self.shop_modal,
            pos=(0, 0.65),
            scale=0.026,
            fg=(0.85, 0.88, 0.92, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 3장의 대형 퍽 카드 (1920x1080 화면에 최적화된 3열 와이드 배치)
        self.perk_cards = []
        card_xs = [-1.02, 0.0, 1.02]

        btn_perk_style = {
            "image": ('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.36, 1, 0.052),
            "text_scale": ((0.052 / 0.36) * 0.46, 0.46),
            "text_pos": (0, -0.15)
        }

        for i in range(3):
            card_f = DirectFrame(
                parent=self.shop_modal,
                image='assets/ui/card_relic_bg.png',
                relief=None,
                frameSize=(-0.46, 0.46, -0.44, 0.44),
                image_scale=(0.46, 1.0, 0.44),
                pos=(card_xs[i], 0, 0.08),
                scale=(1.0, 1, 1.0)
            )
            card_f.setTransparency(TransparencyAttrib.MAlpha)

            # 희귀도 라벨 배지 (일반 / 희귀 / 영웅 / 전설)
            r_rarity = OnscreenText(
                text="[ 희귀 퍽 ]",
                parent=card_f,
                pos=(0, 0.34),
                scale=0.026,
                fg=(0.75, 0.40, 1.0, 1.0),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )

            # 퍽 아이콘 & 이름
            r_title = OnscreenText(
                text="◆ 도탄 사격",
                parent=card_f,
                pos=(0, 0.23),
                scale=0.038,
                fg=(1.0, 0.95, 0.85, 1.0),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )

            # 카테고리 & 태그
            r_category = OnscreenText(
                text="[전술 사격] #도탄 #추적",
                parent=card_f,
                pos=(0, 0.14),
                scale=0.023,
                fg=(0.70, 0.80, 0.90, 0.95),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )

            # 퍽 효과 상세 설명
            r_desc = OnscreenText(
                text="벽면에 착탄한 탄환이 튕겨 반경 14m 이내의 가장 가까운 적을 자동 추적 타격합니다.",
                parent=card_f,
                pos=(0, 0.02),
                scale=0.026,
                fg=(0.92, 0.94, 0.96, 1.0),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ACenter,
                wordwrap=14.5,
                mayChange=True,
                **self.font_kw
            )

            # 선택 버튼
            r_btn = DirectButton(
                parent=card_f,
                text=f"[ {i+1}번 퍽 선택 (KEY {i+1}) ]",
                pos=(0, 0, -0.32),
                text_fg=(0.35, 1.0, 0.65, 1.0),
                command=self._select_perk_card,
                extraArgs=[i],
                **btn_perk_style,
                **self.btn_font_kw
            )
            r_btn.setTransparency(TransparencyAttrib.MAlpha)

            self.perk_cards.append({
                "frame": card_f,
                "rarity": r_rarity,
                "title": r_title,
                "category": r_category,
                "desc": r_desc,
                "btn": r_btn
            })

        # 하단 1: 현재 보유 퍽 배지 목록
        self.shop_owned_perks_text = OnscreenText(
            text="[ 현재 장착 퍽: 없음 ]",
            parent=self.shop_modal,
            pos=(0, -0.42),
            scale=0.028,
            fg=(0.40, 0.88, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 하단 2: 선택 피드백 안내 메시지
        self.shop_msg_text = OnscreenText(
            text="",
            parent=self.shop_modal,
            pos=(0, -0.49),
            scale=0.028,
            fg=(0.35, 1.0, 0.55, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 다음 스테이지 시작 버튼
        self.btn_start_next = DirectButton(
            parent=self.shop_modal,
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="다음 스테이지 시작 (START NEXT STAGE)",
            pos=(0, 0, -0.62),
            scale=(0.54, 1, 0.058),
            text_scale=((0.058 / 0.54) * 0.46, 0.46),
            text_pos=(0, -0.15),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self._confirm_shop_and_start,
            **self.btn_font_kw
        )
        self.btn_start_next.setTransparency(TransparencyAttrib.MAlpha)

        # 미궁 완전 탈출 승리 버튼 (STAGE 3 이상 클리어 시)
        self.btn_escape_victory = DirectButton(
            parent=self.shop_modal,
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="★ 미궁 완전 탈출 (VICTORY ESCAPE) ★",
            pos=(0.35, 0, -0.62),
            scale=(0.52, 1, 0.054),
            text_scale=((0.054 / 0.52) * 0.46, 0.46),
            text_pos=(0, -0.15),
            text_fg=(0.40, 0.95, 1.0, 1.0),
            command=self._confirm_escape_victory,
            **self.btn_font_kw
        )
        self.btn_escape_victory.setTransparency(TransparencyAttrib.MAlpha)
        self.btn_escape_victory.hide()

        self.shop_modal.hide()

    def _refresh_owned_perks_label(self):
        """보유 퍽 텍스트 실시간 갱신"""
        if not self.shop_player:
            return
        perks = getattr(self.shop_player, 'perks', set())
        perk_levels = getattr(self.shop_player, 'perk_levels', {})
        if not perks:
            self.shop_owned_perks_text.setText("[ 현재 장착 퍽: 없음 ]")
            self.shop_owned_perks_text.setFg((0.6, 0.6, 0.6, 0.9))
        else:
            names = []
            for pid in perks:
                if pid in PERK_CATALOG:
                    lvl = perk_levels.get(pid, 1) if isinstance(perk_levels, dict) else 1
                    names.append(f"{PERK_CATALOG[pid]['icon']} {PERK_CATALOG[pid]['name']} Lv.{lvl}")
            self.shop_owned_perks_text.setText(f"[ 현재 장착 퍽 ({len(perks)}개) ]  {'  •  '.join(names)}")
            self.shop_owned_perks_text.setFg((0.35, 0.90, 1.0, 1.0))

    def _select_perk_card(self, card_idx):
        """퍽 카드 선택 클릭 또는 키보드 [1, 2, 3] 이벤트"""
        if getattr(self.shop_modal, 'isHidden', lambda: False)():
            return
        if self.selected_perk_idx != -1:
            return
        if card_idx < 0 or card_idx >= len(self.offered_perks) or not self.shop_player:
            return

        self.selected_perk_idx = card_idx
        perk = self.offered_perks[card_idx]
        new_lvl = self.shop_player.add_perk(perk["id"], self.shop_combat)
        if new_lvl is None:
            new_lvl = get_perk_level(self.shop_player, perk["id"])

        # 카드 하이라이트 및 비활성화
        for idx, card in enumerate(self.perk_cards):
            card["btn"]["state"] = DGG.DISABLED
            if idx == card_idx:
                card["frame"]["image"] = 'assets/ui/card_relic_active.png'
                card["btn"]["text"] = f"[ Lv.{new_lvl} 장착 완료 ★ ]"
                card["btn"]["text_fg"] = (1.0, 0.90, 0.25, 1.0)
            else:
                card["btn"]["text"] = "[ 미선택 ]"
                card["btn"]["text_fg"] = (0.5, 0.5, 0.5, 0.8)

        self.shop_msg_text.setText(f"★ [{perk['name']} Lv.{new_lvl}] 퍽 장착 완료! 하단 버튼 또는 [Enter]/[Space]를 눌러 계속하세요.")
        self.shop_msg_text.setFg((0.35, 1.0, 0.55, 1.0))
        self._refresh_owned_perks_label()

        if hasattr(self, 'update_perk_badges'):
            self.update_perk_badges(self.shop_player.perks, getattr(self.shop_player, 'perk_levels', None))

    def select_perk_by_key(self, key_num):
        """키보드 [1], [2], [3] 입력 시 퍽 카드 즉시 선택"""
        if self.shop_modal.isHidden():
            return False
        idx = key_num - 1
        if 0 <= idx < len(self.offered_perks):
            self._select_perk_card(idx)
            return True
        return False

    def _confirm_shop_and_start(self):
        if self.selected_perk_idx == -1 and len(self.offered_perks) > 0:
            self.shop_msg_text.setText("★ 먼저 장착할 퍽 카드 1장을 선택해 주세요! (키보드 1, 2, 3 또는 클릭) ★")
            self.shop_msg_text.setFg((1.0, 0.35, 0.35, 1.0))
            return
        self.hide_stage_clear_shop()
        if self.on_shop_confirm:
            self.on_shop_confirm()

    def _confirm_escape_victory(self):
        self.hide_stage_clear_shop()
        if hasattr(self, 'on_escape_victory') and self.on_escape_victory:
            self.on_escape_victory()

    def show_stage_clear_shop(self, stage, player, combat, on_confirm_callback, on_victory_callback=None):
        """스테이지 클리어 시 3장의 무작위 퍽 카드 제시"""
        self.shop_player = player
        self.shop_combat = combat
        self.on_shop_confirm = on_confirm_callback
        self.on_escape_victory = on_victory_callback
        self.selected_perk_idx = -1

        self.shop_title.setText(f"[ ★ STAGE {stage} CLEAR : 전술 퍽 프로토콜 ★ ]")
        self.shop_desc.setText("심연의 미궁을 돌파하기 위한 전술 강화 퍽을 1장 선택하세요 (키보드 [1], [2], [3] 번호키 또는 마우스 클릭)")
        self.shop_msg_text.setText("원하는 퍽 카드를 1장 선택하세요 (키보드 [1], [2], [3] 또는 클릭)")
        self.shop_msg_text.setFg((1.0, 0.85, 0.25, 1.0))
        self._refresh_owned_perks_label()

        # STAGE 3 이상 클리어 시 미궁 완전 탈출 버튼 활성화
        if stage >= 3 and on_victory_callback is not None:
            self.btn_start_next.setPos(-0.35, 0, -0.62)
            self.btn_start_next["text"] = "심연 더 깊이 진입 (NEXT STAGE)"
            self.btn_escape_victory.setPos(0.35, 0, -0.62)
            self.btn_escape_victory.show()
        else:
            self.btn_start_next.setPos(0, 0, -0.62)
            self.btn_start_next["text"] = "다음 스테이지 시작 (START NEXT STAGE)"
            self.btn_escape_victory.hide()

        # 퍽 풀에서 3장 무작위 추첨
        p_perks = getattr(player, 'perks', set())
        self.offered_perks = draw_random_perks(p_perks, count=3)

        for i, card in enumerate(self.perk_cards):
            card["frame"]["image"] = 'assets/ui/card_relic_bg.png'
            if i < len(self.offered_perks):
                perk = self.offered_perks[i]
                card["frame"].show()
                rarity = perk.get("rarity", "COMMON")
                rarity_name = RARITY_NAMES.get(rarity, "일반 퍽")
                rarity_col = RARITY_COLORS.get(rarity, (0.35, 0.85, 1.0, 1.0))

                card["rarity"].setText(f"[ {rarity_name} ]")
                card["rarity"].setFg(rarity_col)

                cur_lvl = get_perk_level(player, perk["id"])
                next_lvl = cur_lvl + 1
                card["title"].setText(f"{perk['icon']} {perk['name']} (Lv.{cur_lvl} → Lv.{next_lvl})")
                tags_str = " ".join([f"#{t}" for t in perk.get("tags", [])])
                card["category"].setText(f"[{perk.get('category', '전술')}]  {tags_str}")
                desc_text = describe_perk(perk["id"], next_lvl)
                card["desc"].setText(desc_text)

                card["btn"]["state"] = DGG.NORMAL
                card["btn"]["text"] = f"[ {i+1}번 퍽 선택 (KEY {i+1}) ]"
                card["btn"]["text_fg"] = (0.35, 1.0, 0.65, 1.0)
            else:
                card["frame"].hide()

        self.hide_all_ingame()
        self.shop_modal.show()

    def show_levelup_perk_modal(self, level, player, combat, on_confirm_callback, pending_count=1):
        """레벨업 달성 시 3장의 무작위 전술 퍽 카드 제시 및 선택 모달 오픈"""
        self.shop_player = player
        self.shop_combat = combat
        self.on_shop_confirm = on_confirm_callback
        self.on_escape_victory = None
        self.selected_perk_idx = -1

        pending_str = f"  (남은 선택 기회: {pending_count}회)" if pending_count > 1 else ""
        self.shop_title.setText(f"[ ★ LEVEL UP : LV.{level} 전술 퍽 획득{pending_str} ★ ]")
        self.shop_desc.setText("레벨업 달성! 전장에 적용할 전술 강화 퍽을 1장 선택하세요 (키보드 [1], [2], [3] 번호키 또는 마우스 클릭)")
        self.shop_msg_text.setText("원하는 퍽 카드를 1장 선택하세요 (선택 후 [전투 재개] 클릭 또는 [Enter]/[Space])")
        self.shop_msg_text.setFg((1.0, 0.85, 0.25, 1.0))
        self._refresh_owned_perks_label()

        self.btn_start_next.setPos(0, 0, -0.62)
        self.btn_start_next["text"] = "전투 재개 (RESUME COMBAT)"
        self.btn_escape_victory.hide()

        # 퍽 풀에서 3장 무작위 추첨
        p_perks = getattr(player, 'perks', set())
        self.offered_perks = draw_random_perks(p_perks, count=3)

        for i, card in enumerate(self.perk_cards):
            card["frame"]["image"] = 'assets/ui/card_relic_bg.png'
            if i < len(self.offered_perks):
                perk = self.offered_perks[i]
                card["frame"].show()
                rarity = perk.get("rarity", "COMMON")
                rarity_name = RARITY_NAMES.get(rarity, "일반 퍽")
                rarity_col = RARITY_COLORS.get(rarity, (0.35, 0.85, 1.0, 1.0))

                card["rarity"].setText(f"[ {rarity_name} ]")
                card["rarity"].setFg(rarity_col)

                cur_lvl = get_perk_level(player, perk["id"])
                next_lvl = cur_lvl + 1
                card["title"].setText(f"{perk['icon']} {perk['name']} (Lv.{cur_lvl} → Lv.{next_lvl})")
                tags_str = " ".join([f"#{t}" for t in perk.get("tags", [])])
                card["category"].setText(f"[{perk.get('category', '전술')}]  {tags_str}")
                desc_text = describe_perk(perk["id"], next_lvl)
                card["desc"].setText(desc_text)

                card["btn"]["state"] = DGG.NORMAL
                card["btn"]["text"] = f"[ {i+1}번 퍽 선택 (KEY {i+1}) ]"
                card["btn"]["text_fg"] = (0.35, 1.0, 0.65, 1.0)
            else:
                card["frame"].hide()

        self.hide_all_ingame()
        self.shop_modal.show()

    def hide_stage_clear_shop(self):
        self.shop_modal.hide()

    # --- [전술 군용 인벤토리 배낭 모달 시스템 (1920x1080 FHD 최적화)] ---
    def _setup_inventory_ui(self):
        self.inv_player = None
        self.inv_combat = None
        self.on_use_item_callback = None
        self.on_close_inventory = None
        self.selected_inv_slot = 0

        # 메인 반투명 흑요석 전술 모달 배경 (1920x1080 화면에 최적화된 확대 비율)
        self.inv_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.68, 1.68, -0.92, 0.92),
            image_scale=(1.68, 1.0, 0.92),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.inv_modal.setTransparency(TransparencyAttrib.MAlpha)

        # 1. 헤더: 타이틀 & 서브타이틀 & 닫기 버튼
        self.inv_title = OnscreenText(
            text="[ TACTICAL INVENTORY - 전술 군용 배낭 ]",
            parent=self.inv_modal,
            pos=(0, 0.81),
            scale=0.052,
            fg=(0.40, 0.92, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_subtitle = OnscreenText(
            text="생존 소모품 보급 현황 및 무기 제원 관리  |  단축키 [1~4] 인게임 즉시 사용 가능",
            parent=self.inv_modal,
            pos=(0, 0.74),
            scale=0.028,
            fg=(0.78, 0.85, 0.92, 0.90),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.btn_close_inv = DirectButton(
            parent=self.inv_modal,
            image=('assets/ui/btn_danger_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_danger_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="[ X 닫기 (TAB / ESC) ]",
            pos=(1.38, 0, 0.81),
            scale=(0.26, 1, 0.056),
            text_scale=((0.056 / 0.26) * 0.48, 0.48),
            text_pos=(0, -0.14),
            text_fg=(1.0, 0.85, 0.85, 1.0),
            command=self.hide_inventory,
            **self.btn_font_kw
        )
        self.btn_close_inv.setTransparency(TransparencyAttrib.MAlpha)

        # 2. 좌측 칼럼: 생존자 RPG 종합 스탯 & 무기 제원 (x = -1.48 ~ -0.45)
        self.inv_left_title = OnscreenText(
            text="■ 생존자 상태 및 무기 제원",
            parent=self.inv_modal,
            pos=(-1.48, 0.63),
            scale=0.038,
            fg=(0.95, 0.82, 0.35, 1.0),
            align=TextNode.ALeft,
            **self.font_kw
        )

        self.inv_stats_text = OnscreenText(
            text="",
            parent=self.inv_modal,
            pos=(-1.48, 0.54),
            scale=0.030,
            fg=(0.90, 0.94, 0.98, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 3. 중앙 칼럼: 소지품 6슬롯 전술 배낭 그리드 (x = -0.35 ~ 0.35)
        self.inv_grid_title = OnscreenText(
            text="■ 전술 보급품 및 소지품 (6 슬롯)",
            parent=self.inv_modal,
            pos=(0, 0.63),
            scale=0.038,
            fg=(0.35, 0.95, 1.0, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_slots = []
        slot_coords = [
            (-0.25, 0.42), (0.25, 0.42),   # Row 1 (Quickslots 1, 2)
            (-0.25, 0.10), (0.25, 0.10),   # Row 2 (Quickslots 3, 4)
            (-0.25, -0.22), (0.25, -0.22)  # Row 3 (Slots 5, 6)
        ]

        for idx, (sx, sz) in enumerate(slot_coords):
            # 대폭 확대한 1:1 정방형 슬롯 (1920x1080 기준 약 120px 큼직한 슬롯)
            slot_btn = DirectButton(
                parent=self.inv_modal,
                image=('assets/ui/slot_bg_normal.png', 'assets/ui/slot_bg_selected.png', 'assets/ui/slot_bg_selected.png', 'assets/ui/slot_bg_normal.png'),
                relief=None,
                pos=(sx, 0, sz),
                scale=(0.22, 1.0, 0.22),
                command=self._select_inventory_slot,
                extraArgs=[idx]
            )
            slot_btn.setTransparency(TransparencyAttrib.MAlpha)

            slot_icon = OnscreenImage(
                image='assets/ui/item_medkit.png',
                parent=slot_btn,
                scale=(0.66, 1.0, 0.66),
                pos=(0, 0, 0.04)
            )
            slot_icon.setTransparency(TransparencyAttrib.MAlpha)
            slot_icon.hide()

            slot_tag = OnscreenText(
                text=f"[{idx+1}]" if idx < 4 else "",
                parent=slot_btn,
                pos=(-0.38, 0.36),
                scale=0.22,
                fg=(0.40, 0.95, 1.0, 1.0),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ALeft,
                mayChange=True,
                **self.font_kw
            )

            slot_count = OnscreenText(
                text="",
                parent=slot_btn,
                pos=(0.38, -0.36),
                scale=0.22,
                fg=(1.0, 0.90, 0.35, 1.0),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ARight,
                mayChange=True,
                **self.font_kw
            )

            slot_name = OnscreenText(
                text="[ 빈 슬롯 ]",
                parent=slot_btn,
                pos=(0, -0.56),
                scale=0.18,
                fg=(0.70, 0.75, 0.82, 0.90),
                shadow=(0, 0, 0, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )

            self.inv_slots.append({
                "btn": slot_btn,
                "icon": slot_icon,
                "tag": slot_tag,
                "count": slot_count,
                "name": slot_name
            })

        # 4. 우측 칼럼: 선택된 아이템 상세 정보 및 사용 패널 (x = 0.55 ~ 1.55)
        self.inv_right_title = OnscreenText(
            text="■ 아이템 상세 정보 (INFO)",
            parent=self.inv_modal,
            pos=(1.08, 0.63),
            scale=0.038,
            fg=(0.40, 0.95, 0.60, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_detail_icon = OnscreenImage(
            image='assets/ui/item_medkit.png',
            parent=self.inv_modal,
            scale=(0.22, 1.0, 0.22),
            pos=(1.08, 0, 0.40)
        )
        self.inv_detail_icon.setTransparency(TransparencyAttrib.MAlpha)

        self.inv_detail_name = OnscreenText(
            text="[ 선택된 아이템 없음 ]",
            parent=self.inv_modal,
            pos=(1.08, 0.18),
            scale=0.044,
            fg=(1.0, 1.0, 1.0, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.inv_detail_meta = OnscreenText(
            text="분류: -  |  보유 수량: -",
            parent=self.inv_modal,
            pos=(1.08, 0.10),
            scale=0.032,
            fg=(0.75, 0.85, 0.95, 0.95),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.inv_detail_desc = OnscreenText(
            text="아이템을 선택하면 상세 정보 및 사용법이 표시됩니다.",
            parent=self.inv_modal,
            pos=(0.58, 0.02),
            scale=0.030,
            fg=(0.88, 0.92, 0.96, 0.95),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ALeft,
            wordwrap=24,
            mayChange=True,
            **self.font_kw
        )

        self.btn_use_item = DirectButton(
            parent=self.inv_modal,
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="[ 사용하기 (USE ITEM) ]",
            pos=(1.08, 0, -0.20),
            scale=(0.46, 1.0, 0.072),
            text_scale=((0.072 / 0.46) * 0.48, 0.48),
            text_pos=(0, -0.15),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self._on_click_use_inventory_item,
            **self.btn_font_kw
        )
        self.btn_use_item.setTransparency(TransparencyAttrib.MAlpha)

        self.inv_msg_text = OnscreenText(
            text="",
            parent=self.inv_modal,
            pos=(1.08, -0.30),
            scale=0.027,
            fg=(0.40, 1.0, 0.60, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 5. 하단 칼럼: 장착된 고대 저주받은 유물 목록 (z = -0.46 ~ -0.66)
        self.inv_relics_title = OnscreenText(
            text="■ 장착된 고대 미궁의 저주받은 유물 (CURSED RELICS)",
            parent=self.inv_modal,
            pos=(0, -0.46),
            scale=0.032,
            fg=(0.95, 0.72, 1.0, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_relic_labels = []
        r_xs = [-1.15, -0.38, 0.38, 1.15]
        for i in range(4):
            lbl = OnscreenText(
                text="[ 빈 유물 슬롯 ]",
                parent=self.inv_modal,
                pos=(r_xs[i], -0.56),
                scale=0.026,
                fg=(0.60, 0.60, 0.65, 0.85),
                shadow=(0, 0, 0, 0.95),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            self.inv_relic_labels.append(lbl)

        # 6. 하단 안내 텍스트
        self.inv_footer_text = OnscreenText(
            text="[1~4] 키로 인게임에서 배낭을 열지 않고 즉시 사용 가능  |  [TAB] / [I] / [ESC] 키로 배낭 닫기",
            parent=self.inv_modal,
            pos=(0, -0.76),
            scale=0.026,
            fg=(0.65, 0.75, 0.85, 0.80),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_modal.hide()

    def is_inventory_open(self):
        """인벤토리 모달이 열려 있는지 확인"""
        return hasattr(self, 'inv_modal') and not self.inv_modal.isHidden()

    def show_inventory(self, player, combat, on_use_item_callback=None, on_close_callback=None):
        """전술 인벤토리 배낭 모달 오픈"""
        self.inv_player = player
        self.inv_combat = combat
        self.on_use_item_callback = on_use_item_callback
        self.on_close_inventory = on_close_callback
        self.inv_msg_text.setText("")
        self._refresh_inventory_ui()
        self.inv_modal.show()

    def hide_inventory(self):
        """전술 인벤토리 배낭 모달 닫기"""
        if hasattr(self, 'inv_modal'):
            self.inv_modal.hide()
        if hasattr(self, 'on_close_inventory') and self.on_close_inventory:
            cb = self.on_close_inventory
            self.on_close_inventory = None
            cb()

    def _select_inventory_slot(self, slot_idx):
        """인벤토리 슬롯 클릭 시 아이템 선택 및 상세 패널 갱신"""
        self.selected_inv_slot = slot_idx
        self.inv_msg_text.setText("")
        self._refresh_inventory_ui()

    def _on_click_use_inventory_item(self):
        """선택된 아이템 [사용하기] 클릭 이벤트"""
        if not self.inv_player:
            return
        inv = getattr(self.inv_player, 'inventory', [])
        if self.selected_inv_slot < len(inv):
            item = inv[self.selected_inv_slot]
            if self.on_use_item_callback:
                self.on_use_item_callback(item["id"])
            self._refresh_inventory_ui()

    def _refresh_inventory_ui(self):
        """인벤토리 스탯, 슬롯 그리드, 상세 정보 패널 실시간 갱신"""
        if not self.inv_player:
            return

        p = self.inv_player
        c = self.inv_combat
        inv = getattr(p, 'inventory', [])

        # 1. 좌측 스탯 텍스트 갱신
        lvl = getattr(p, 'level', 1)
        exp = int(getattr(p, 'exp', 0))
        exp_next = int(getattr(p, 'exp_to_next', 100))
        hp = int(getattr(p, 'hp', 100))
        max_hp = int(getattr(p, 'max_hp', 100))
        atk = int(p.get_attack_power()) if hasattr(p, 'get_attack_power') else int(getattr(p, 'attack_power', 35))
        spd_pct = int(getattr(p, 'speed_mult', 1.0) * (1.30 if getattr(p, 'speed_boost_timer', 0.0) > 0.0 else 1.0) * 100)
        stamina = int(getattr(p, 'stamina', 100))
        max_stamina = int(getattr(p, 'max_stamina', 100))
        perks_count = len(getattr(p, 'perks', set()))

        ammo = c.ammo if c else 12
        max_ammo = c.max_ammo if c else 12
        res_ammo = c.reserve_ammo if c else 0

        stats_str = (
            f"• 레벨: LV.{lvl}  [경험치: {exp} / {exp_next}]\n"
            f"• 체력: {hp} / {max_hp} HP\n"
            f"• 공격력: {atk} DMG  (기본: {int(getattr(p, 'attack_power', 35))})\n"
            f"• 이동 속도: {spd_pct}%\n"
            f"• 스테미나: {stamina} / {max_stamina}\n"
            f"• 장착 퍽: {perks_count}개 보유\n"
            f"-----------------------------------------\n"
            f"[장착 무기] {getattr(c, 'get_weapon_display_name', lambda: '9mm 택티컬 권총')() if c else '9mm 택티컬 권총'}\n"
            f"• 탄약 상태: {ammo} / {max_ammo}발 (예비: {res_ammo}발)\n"
            f"• 무기 스왑: [Q / 휠] 또는 [Z]권총 [X]쌍권총 [C]샷건\n"
            f"• 1. 9mm 택티컬 권총 (12발 / 핀포인트 정밀 헤드샷)\n"
            f"• 2. 아킴보 쌍권총 (24발 / 초고속 0.11s 교차 난사)\n"
            f"• 3. 12G 전술 샷건 (8발 / 8발 산탄 224 극딜 펌프액션)\n"
            f"-----------------------------------------\n"
            f"[보조장비] M67 전술 파열 수류탄 [G]\n"
            f"[전술기동] 컴뱃 슬라이드 & 회피 [Space]"
        )
        self.inv_stats_text.setText(stats_str)

        # 2. 중앙 소지품 슬롯 그리드 갱신
        for idx, slot_ui in enumerate(self.inv_slots):
            if idx < len(inv):
                item = inv[idx]
                cnt = item.get("count", 0)
                qs = item.get("quick_slot")
                slot_ui["icon"].setImage(item["icon"])
                slot_ui["icon"].show()
                slot_ui["tag"].setText(f"[{qs}]" if qs else "")
                slot_ui["count"].setText(f"x{cnt}")
                slot_ui["name"].setText(item["name"])
                slot_ui["name"].setFg(item.get("rarity_color", (0.9, 0.9, 0.9, 1.0)))

                if idx == self.selected_inv_slot:
                    slot_ui["btn"]["image"] = 'assets/ui/slot_bg_selected.png'
                else:
                    slot_ui["btn"]["image"] = 'assets/ui/slot_bg_normal.png'
            else:
                slot_ui["icon"].hide()
                slot_ui["tag"].setText("")
                slot_ui["count"].setText("")
                slot_ui["name"].setText("[ 빈 슬롯 ]")
                slot_ui["name"].setFg((0.45, 0.50, 0.58, 0.70))
                slot_ui["btn"]["image"] = 'assets/ui/slot_bg_normal.png'

        # 3. 우측 상세 정보 패널 갱신
        if self.selected_inv_slot < len(inv):
            sel_item = inv[self.selected_inv_slot]
            self.inv_detail_icon.setImage(sel_item["icon"])
            self.inv_detail_icon.show()
            self.inv_detail_name.setText(f"[ {sel_item['name']} ]")
            self.inv_detail_name.setFg(sel_item.get("rarity_color", (1, 1, 1, 1)))

            qs_str = f" | [단축키 {sel_item['quick_slot']}번]" if sel_item.get("quick_slot") else ""
            self.inv_detail_meta.setText(f"분류: {sel_item['category']}  |  보유: {sel_item['count']}/{sel_item.get('max_count', 99)}개{qs_str}")
            self.inv_detail_desc.setText(sel_item["desc"])

            if sel_item["count"] > 0:
                self.btn_use_item["state"] = DGG.NORMAL
                self.btn_use_item["text"] = "[ 사용하기 (USE ITEM) ]"
            else:
                self.btn_use_item["state"] = DGG.DISABLED
                self.btn_use_item["text"] = "[ 수량 소진 (EMPTY) ]"
        else:
            self.inv_detail_icon.hide()
            self.inv_detail_name.setText("[ 빈 슬롯 ]")
            self.inv_detail_name.setFg((0.6, 0.6, 0.6, 1.0))
            self.inv_detail_meta.setText("아이템이 없습니다.")
            self.inv_detail_desc.setText("소지품 슬롯을 선택하면 상세 정보 및 사용법이 표시됩니다.")
            self.btn_use_item["state"] = DGG.DISABLED
            self.btn_use_item["text"] = "[ 사용 불가 ]"

        # 4. 하단 유물 슬롯 갱신
        relics = getattr(p, 'relics', [])
        for i, lbl in enumerate(self.inv_relic_labels):
            if i < len(relics):
                rid = relics[i]
                r_info = CURSED_RELICS.get(rid, {"name": rid, "icon": "[유물]", "pro": "강화", "con": "저주"})
                lbl.setText(f"{r_info.get('icon', '[유물]')} {r_info.get('name', rid)}\n(+{r_info.get('pro', '')})")
                lbl.setFg((0.95, 0.80, 1.0, 1.0))
            else:
                lbl.setText("[ 빈 유물 슬롯 ]\n(스테이지 클리어 시 획득)")
                lbl.setFg((0.50, 0.52, 0.58, 0.70))

    def update_quickslots_hud(self, inventory):
        """인게임 HUD 전술 퀵슬롯 실시간 수량 텍스트 갱신"""
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for item in inventory:
            qs = item.get("quick_slot")
            if qs in counts:
                counts[qs] = item.get("count", 0)
        txt = f"[1] 응급키트: {counts[1]}개   |   [2] 아드레날린: {counts[2]}개   |   [3] 탄약팩: {counts[3]}개   |   [4] 수류탄: {counts[4]}개   |   [Tab] 배낭"
        if hasattr(self, 'quickslot_text'):
            self.quickslot_text.setText(txt)

    def spawn_floating_damage(self, damage, pos, is_crit=False, is_headshot=False, damage_type=None):
        """3D 공간상에 고가독성 플로팅 대미지 숫자 생성"""
        if hasattr(self, 'floating_damage_mgr') and self.floating_damage_mgr:
            self.floating_damage_mgr.spawn(damage, pos, is_crit=is_crit, is_headshot=is_headshot, damage_type=damage_type)

    # =========================================================================
    # 1. 원형 전술 레이더 / 미니맵 HUD 위젯
    # =========================================================================
    def _setup_tactical_radar(self):
        """우상단 원형 전술 레이더 / 미니맵 HUD 위젯 지오메트리 및 블립 초기화"""
        self.radar_root = self.base.aspect2d.attachNewNode("tactical_radar_root")
        self.radar_root.setPos(1.38, 0, 0.65)
        self.radar_root.setBin("fixed", 20)
        self.radar_root.setDepthTest(False)
        self.radar_root.setDepthWrite(False)
        self.radar_radius = 0.20
        self.radar_max_dist = 35.0  # 35미터 전술 감지 반경

        # 1. 다크 글래스모피즘 원형 배경
        bg_geom = create_circle_fan_geom(self.radar_radius, color=(0.02, 0.05, 0.08, 0.78))
        self.radar_bg = self.radar_root.attachNewNode(bg_geom)
        self.radar_bg.setTransparency(TransparencyAttrib.MAlpha)

        # 2. 전술 동심원 링 및 십자선 지오메트리
        rings_geom = create_radar_rings_geom(self.radar_radius)
        self.radar_rings = self.radar_root.attachNewNode(rings_geom)

        # 3. 회전하는 전술 스위프 빔 (Sweep Beam)
        ls_sweep = LineSegs("radar_sweep_beam")
        ls_sweep.setColor(0.25, 0.95, 1.0, 0.85)
        ls_sweep.setThickness(2.0)
        ls_sweep.moveTo(0, 0, 0)
        ls_sweep.drawTo(0, 0, self.radar_radius * 0.98)
        self.radar_sweep_node = self.radar_root.attachNewNode(ls_sweep.create())
        self.radar_sweep_angle = 0.0

        # 4. 레이더 중앙 플레이어 마커 (상단 지향 녹색 화살표)
        self.player_blip = OnscreenText(
            text="▲",
            parent=self.radar_root,
            pos=(0, -0.012),
            scale=0.038,
            fg=(0.25, 1.0, 0.55, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )

        # 5. 레이더 하단 거리 라벨
        self.radar_label = OnscreenText(
            text="RADAR 35M",
            parent=self.radar_root,
            pos=(0, -self.radar_radius - 0.032),
            scale=0.024,
            fg=(0.35, 0.85, 0.95, 0.85),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 6. 블립 풀링 (괴물 32체, 탈출 관문 1개, 보급 상자 8개)
        self.monster_blips = []
        for _ in range(32):
            b = OnscreenText(
                text="●",
                parent=self.radar_root,
                pos=(0, 0),
                scale=0.030,
                fg=(1.0, 0.22, 0.22, 1.0),
                shadow=(0, 0, 0, 0.9),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            b.hide()
            self.monster_blips.append(b)

        # 탈출구 블립 (녹색 스타)
        self.portal_blip = OnscreenText(
            text="★",
            parent=self.radar_root,
            pos=(0, 0),
            scale=0.046,
            fg=(0.20, 1.0, 0.40, 1.0),
            shadow=(0, 0, 0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.portal_blip.hide()

        # 보급 상자 블립 (청록색 사각형)
        self.crate_blips = []
        for _ in range(8):
            cb = OnscreenText(
                text="■",
                parent=self.radar_root,
                pos=(0, 0),
                scale=0.028,
                fg=(0.25, 0.85, 1.0, 1.0),
                shadow=(0, 0, 0, 0.9),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            cb.hide()
            self.crate_blips.append(cb)

    def update_tactical_radar(self, player_pos, heading, monsters=None, escape_pos=None, supply_crates=None):
        """플레이어 위치 및 시선 기준 원형 전술 레이더 실시간 갱신"""
        if not hasattr(self, 'radar_root') or self.radar_root.isHidden():
            return
        if player_pos is None:
            return

        px, py = player_pos[0], player_pos[1]
        h_rad = math.radians(heading)
        fwd_x = -math.sin(h_rad)
        fwd_y = math.cos(h_rad)
        rgt_x = math.cos(h_rad)
        rgt_y = math.sin(h_rad)

        scale = self.radar_radius / self.radar_max_dist

        # 1. 몬스터 블립 갱신
        for b in self.monster_blips:
            b.hide()

        b_idx = 0
        if monsters:
            for m in monsters:
                if b_idx >= len(self.monster_blips):
                    break
                if getattr(m, 'hp', 0) <= 0 or getattr(m, 'is_corpse', False):
                    continue
                m_pos = getattr(m, 'pos', None)
                if m_pos is None:
                    continue
                mx = getattr(m_pos, 'x', m_pos[0])
                my = getattr(m_pos, 'y', m_pos[1])

                dx = mx - px
                dy = my - py
                fwd_d = dx * fwd_x + dy * fwd_y
                rgt_d = dx * rgt_x + dy * rgt_y
                dist = math.hypot(fwd_d, rgt_d)

                blip = self.monster_blips[b_idx]
                is_elite = getattr(m, 'is_elite', False)
                is_boss = getattr(m, 'is_boss', False)

                if is_boss:
                    base_color = (1.0, 0.20, 0.35)
                    blip.setText("X")
                    blip.setScale(0.046)
                elif is_elite:
                    base_color = (1.0, 0.85, 0.20)
                    blip.setText("◆")
                    blip.setScale(0.038)
                else:
                    base_color = (1.0, 0.24, 0.24)
                    blip.setText("●")
                    blip.setScale(0.030)

                alpha = 0.45 if dist > self.radar_max_dist else 1.0
                if dist > self.radar_max_dist:
                    factor = self.radar_max_dist / dist
                    rgt_d *= factor
                    fwd_d *= factor

                blip.setFg((base_color[0], base_color[1], base_color[2], alpha))

                blip.setPos(rgt_d * scale, fwd_d * scale - 0.01)
                blip.show()
                b_idx += 1

        # 2. 탈출 관문 블립 갱신
        if escape_pos:
            ex = getattr(escape_pos, 'x', escape_pos[0])
            ey = getattr(escape_pos, 'y', escape_pos[1])
            dx = ex - px
            dy = ey - py
            fwd_d = dx * fwd_x + dy * fwd_y
            rgt_d = dx * rgt_x + dy * rgt_y
            dist = math.hypot(fwd_d, rgt_d)
            if dist > self.radar_max_dist:
                factor = self.radar_max_dist / dist
                rgt_d *= factor
                fwd_d *= factor
                self.portal_blip.setFg((0.2, 1.0, 0.4, 0.65))
            else:
                self.portal_blip.setFg((0.2, 1.0, 0.4, 1.0))
            self.portal_blip.setPos(rgt_d * scale, fwd_d * scale - 0.01)
            self.portal_blip.show()
        else:
            self.portal_blip.hide()

        # 3. 보급 상자 블립 갱신
        for cb in self.crate_blips:
            cb.hide()

        cb_idx = 0
        if supply_crates:
            for c in supply_crates:
                if cb_idx >= len(self.crate_blips):
                    break
                if getattr(c, 'is_opened', False):
                    continue
                cx = getattr(c, 'x', 0)
                cy = getattr(c, 'y', 0)
                dx = cx - px
                dy = cy - py
                fwd_d = dx * fwd_x + dy * fwd_y
                rgt_d = dx * rgt_x + dy * rgt_y
                dist = math.hypot(fwd_d, rgt_d)
                c_blip = self.crate_blips[cb_idx]
                if dist > self.radar_max_dist:
                    factor = self.radar_max_dist / dist
                    rgt_d *= factor
                    fwd_d *= factor
                    c_blip.setFg((0.25, 0.85, 1.0, 0.50))
                else:
                    c_blip.setFg((0.25, 0.85, 1.0, 0.95))
                c_blip.setPos(rgt_d * scale, fwd_d * scale - 0.008)
                c_blip.show()
                cb_idx += 1

    # =========================================================================
    # 2. [ESC] 전용 일시정지 & 시스템 설정 메뉴 (Pause / Settings Modal)
    # =========================================================================
    def _setup_pause_ui(self):
        """[ESC] 전용 일시정지 & 시스템 설정 모달 초기화"""
        self.pause_player = None
        self.pause_combat = None
        self.pause_audio_mgr = None
        self.on_resume_callback = None
        self.on_restart_callback = None
        self.on_title_callback = None
        self.on_exit_callback = None

        self.pause_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.10, 1.10, -0.85, 0.85),
            image_scale=(1.10, 1.0, 0.85),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.pause_modal.setTransparency(TransparencyAttrib.MAlpha)
        self.pause_modal.setBin("fixed", 60)
        self.pause_modal.hide()

        # 모달 타이틀
        self.pause_title = OnscreenText(
            text="[ TACTICAL PAUSE & SYSTEM SETTINGS ]",
            parent=self.pause_modal,
            pos=(0, 0.68),
            scale=0.042,
            fg=(0.30, 0.92, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )

        self.pause_sub = OnscreenText(
            text="작전 현장 통제 및 사용자 환경 설정",
            parent=self.pause_modal,
            pos=(0, 0.60),
            scale=0.026,
            fg=(0.75, 0.85, 0.92, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )

        btn_step_style = {
            "image": ('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.055, 1, 0.040),
            "text_scale": ((0.040 / 0.055) * 0.55, 0.55),
            "text_pos": (0, -0.15),
            "text_fg": (1, 1, 1, 1),
            **self.btn_font_kw
        }

        # 1. 마우스 감도
        self.lbl_sens = OnscreenText(
            text="마우스 감도 (Mouse Sensitivity)",
            parent=self.pause_modal,
            pos=(-0.55, 0.42),
            scale=0.030,
            fg=(0.92, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            **self.font_kw
        )
        self.btn_sens_minus = DirectButton(
            parent=self.pause_modal,
            text="-",
            pos=(0.18, 0, 0.43),
            command=self._adjust_setting,
            extraArgs=["sens", -0.02],
            **btn_step_style
        )
        self.txt_sens_val = OnscreenText(
            text="0.15",
            parent=self.pause_modal,
            pos=(0.34, 0.42),
            scale=0.030,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.btn_sens_plus = DirectButton(
            parent=self.pause_modal,
            text="+",
            pos=(0.50, 0, 0.43),
            command=self._adjust_setting,
            extraArgs=["sens", +0.02],
            **btn_step_style
        )

        # 2. 효과음 볼륨
        self.lbl_sfx = OnscreenText(
            text="효과음 음량 (SFX Volume)",
            parent=self.pause_modal,
            pos=(-0.55, 0.28),
            scale=0.030,
            fg=(0.92, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            **self.font_kw
        )
        self.btn_sfx_minus = DirectButton(
            parent=self.pause_modal,
            text="-",
            pos=(0.18, 0, 0.29),
            command=self._adjust_setting,
            extraArgs=["sfx", -0.10],
            **btn_step_style
        )
        self.txt_sfx_val = OnscreenText(
            text="100%",
            parent=self.pause_modal,
            pos=(0.34, 0.28),
            scale=0.030,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.btn_sfx_plus = DirectButton(
            parent=self.pause_modal,
            text="+",
            pos=(0.50, 0, 0.29),
            command=self._adjust_setting,
            extraArgs=["sfx", +0.10],
            **btn_step_style
        )

        # 3. 배경음 볼륨
        self.lbl_bgm = OnscreenText(
            text="배경음 음량 (BGM Volume)",
            parent=self.pause_modal,
            pos=(-0.55, 0.14),
            scale=0.030,
            fg=(0.92, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            **self.font_kw
        )
        self.btn_bgm_minus = DirectButton(
            parent=self.pause_modal,
            text="-",
            pos=(0.18, 0, 0.15),
            command=self._adjust_setting,
            extraArgs=["bgm", -0.10],
            **btn_step_style
        )
        self.txt_bgm_val = OnscreenText(
            text="100%",
            parent=self.pause_modal,
            pos=(0.34, 0.14),
            scale=0.030,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.btn_bgm_plus = DirectButton(
            parent=self.pause_modal,
            text="+",
            pos=(0.50, 0, 0.15),
            command=self._adjust_setting,
            extraArgs=["bgm", +0.10],
            **btn_step_style
        )

        # 4. 시야각 FOV
        self.lbl_fov = OnscreenText(
            text="시야각 (Field of View - FOV)",
            parent=self.pause_modal,
            pos=(-0.55, 0.00),
            scale=0.030,
            fg=(0.92, 0.95, 1.0, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            **self.font_kw
        )
        self.btn_fov_minus = DirectButton(
            parent=self.pause_modal,
            text="-",
            pos=(0.18, 0, 0.01),
            command=self._adjust_setting,
            extraArgs=["fov", -5.0],
            **btn_step_style
        )
        self.txt_fov_val = OnscreenText(
            text="96°",
            parent=self.pause_modal,
            pos=(0.34, 0.00),
            scale=0.030,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.btn_fov_plus = DirectButton(
            parent=self.pause_modal,
            text="+",
            pos=(0.50, 0, 0.01),
            command=self._adjust_setting,
            extraArgs=["fov", +5.0],
            **btn_step_style
        )

        # 하단 조작 버튼들 (계속하기, 재시작, 타이틀, 종료)
        btn_action_style = {
            "image": ('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.22, 1, 0.050),
            "text_scale": ((0.050 / 0.22) * 0.44, 0.44),
            "text_pos": (0, -0.15),
            "text_fg": (1, 1, 1, 1),
            **self.btn_font_kw
        }
        btn_normal_style = {
            "image": ('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.22, 1, 0.050),
            "text_scale": ((0.050 / 0.22) * 0.44, 0.44),
            "text_pos": (0, -0.15),
            "text_fg": (1, 1, 1, 1),
            **self.btn_font_kw
        }
        btn_danger_style = {
            "image": ('assets/ui/btn_danger_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_danger_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.22, 1, 0.050),
            "text_scale": ((0.050 / 0.22) * 0.44, 0.44),
            "text_pos": (0, -0.15),
            "text_fg": (1, 1, 1, 1),
            **self.btn_font_kw
        }

        self.btn_pause_resume = DirectButton(
            parent=self.pause_modal,
            text="계속하기 (RESUME)",
            pos=(-0.72, 0, -0.38),
            command=self._on_pause_resume_clicked,
            **btn_action_style
        )

        self.btn_pause_restart = DirectButton(
            parent=self.pause_modal,
            text="스테이지 재시작 (RETRY)",
            pos=(-0.24, 0, -0.38),
            command=self._on_pause_restart_clicked,
            **btn_normal_style
        )

        self.btn_pause_title = DirectButton(
            parent=self.pause_modal,
            text="타이틀 메뉴 (TITLE)",
            pos=(0.24, 0, -0.38),
            command=self._on_pause_title_clicked,
            **btn_normal_style
        )

        self.btn_pause_exit = DirectButton(
            parent=self.pause_modal,
            text="게임 종료 (EXIT)",
            pos=(0.72, 0, -0.38),
            command=self._on_pause_exit_clicked,
            **btn_danger_style
        )

        self.pause_esc_hint = OnscreenText(
            text="[ESC] 키를 다시 눌러 게임 현장으로 즉시 복귀할 수 있습니다.",
            parent=self.pause_modal,
            pos=(0, -0.56),
            scale=0.024,
            fg=(0.60, 0.85, 1.0, 0.85),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

    def show_pause_menu(self, player=None, combat=None, audio_mgr=None, on_resume_callback=None, on_restart_callback=None, on_title_callback=None, on_exit_callback=None):
        """일시정지 및 설정 모달 표시"""
        self.pause_player = player
        self.pause_combat = combat
        self.pause_audio_mgr = audio_mgr
        self.on_resume_callback = on_resume_callback
        self.on_restart_callback = on_restart_callback
        self.on_title_callback = on_title_callback
        self.on_exit_callback = on_exit_callback

        if player:
            sens = getattr(player, 'mouse_sensitivity', 0.15)
            self.txt_sens_val.setText(f"{sens:.2f}")

        if audio_mgr:
            sfx_v = getattr(audio_mgr, 'master_sfx_volume', 1.0)
            bgm_v = getattr(audio_mgr, 'master_bgm_volume', 1.0)
            self.txt_sfx_val.setText(f"{int(round(sfx_v * 100))}%")
            self.txt_bgm_val.setText(f"{int(round(bgm_v * 100))}%")

        lens = getattr(self.base, 'camLens', None)
        if lens and hasattr(lens, 'getFov'):
            fov = lens.getFov()[0]
            self.txt_fov_val.setText(f"{int(fov)}°")

        self.pause_modal.show()

    def hide_pause_menu(self):
        """일시정지 모달 숨김"""
        if hasattr(self, 'pause_modal') and self.pause_modal:
            self.pause_modal.hide()

    def is_pause_menu_open(self):
        """일시정지 모달 오픈 상태 반환"""
        return hasattr(self, 'pause_modal') and self.pause_modal and not self.pause_modal.isHidden()

    def _adjust_setting(self, setting_type, delta):
        """마우스 감도, SFX/BGM 볼륨, FOV 실시간 조정"""
        if setting_type == "sens":
            cur = getattr(self.pause_player, 'mouse_sensitivity', 0.15) if self.pause_player else 0.15
            new_val = round(max(0.04, min(0.40, cur + delta)), 2)
            if self.pause_player:
                self.pause_player.mouse_sensitivity = new_val
            self.txt_sens_val.setText(f"{new_val:.2f}")
        elif setting_type == "sfx":
            cur = getattr(self.pause_audio_mgr, 'master_sfx_volume', 1.0) if self.pause_audio_mgr else 1.0
            new_val = round(max(0.0, min(1.0, cur + delta)), 2)
            if self.pause_audio_mgr and hasattr(self.pause_audio_mgr, 'set_sfx_volume'):
                self.pause_audio_mgr.set_sfx_volume(new_val)
            self.txt_sfx_val.setText(f"{int(round(new_val * 100))}%")
        elif setting_type == "bgm":
            cur = getattr(self.pause_audio_mgr, 'master_bgm_volume', 1.0) if self.pause_audio_mgr else 1.0
            new_val = round(max(0.0, min(1.0, cur + delta)), 2)
            if self.pause_audio_mgr and hasattr(self.pause_audio_mgr, 'set_bgm_volume'):
                self.pause_audio_mgr.set_bgm_volume(new_val)
            self.txt_bgm_val.setText(f"{int(round(new_val * 100))}%")
        elif setting_type == "fov":
            lens = getattr(self.base, 'camLens', None)
            cur = lens.getFov()[0] if lens and hasattr(lens, 'getFov') else 96.0
            new_val = round(max(70.0, min(115.0, cur + delta)), 1)
            if lens and hasattr(lens, 'setFov'):
                lens.setFov(new_val)
            self.txt_fov_val.setText(f"{int(new_val)}°")

    def _on_pause_resume_clicked(self):
        if self.on_resume_callback:
            self.on_resume_callback()

    def _on_pause_restart_clicked(self):
        self.hide_pause_menu()
        if self.on_restart_callback:
            self.on_restart_callback()

    def _on_pause_title_clicked(self):
        self.hide_pause_menu()
        if self.on_title_callback:
            self.on_title_callback()

    def _on_pause_exit_clicked(self):
        self.hide_pause_menu()
        if self.on_exit_callback:
            self.on_exit_callback()

    # =========================================================================
    # 3. 스테이지 클리어 전투 결과 보고서 (After-Action Report)
    # =========================================================================
    def _setup_after_action_report_ui(self):
        """스테이지 클리어 전투 결과 보고서 (After-Action Report) 모달 초기화"""
        self.on_aar_continue = None

        self.aar_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.35, 1.35, -0.88, 0.88),
            image_scale=(1.35, 1.0, 0.88),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.aar_modal.setTransparency(TransparencyAttrib.MAlpha)
        self.aar_modal.setBin("fixed", 65)
        self.aar_modal.hide()

        # 헤더
        self.aar_title = OnscreenText(
            text="[ ★ AFTER-ACTION REPORT // 작전 전투 결과 보고서 ★ ]",
            parent=self.aar_modal,
            pos=(0, 0.72),
            scale=0.044,
            fg=(0.20, 1.0, 0.50, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.aar_sub = OnscreenText(
            text="구역 방어 성공 및 탈출 관문 확보 완료",
            parent=self.aar_modal,
            pos=(0, 0.63),
            scale=0.026,
            fg=(0.85, 0.90, 0.96, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 좌측 전투 분석 지표 (7개 핵심 항목)
        self.aar_stats_labels = OnscreenText(
            text=(
                "▷  클리어 소요 시간\n\n"
                "▷  처치한 변이 괴물\n\n"
                "▷  탄환 사격 명중률\n\n"
                "▷  헤드샷 치명타율\n\n"
                "▷  누적 가한 총 피해\n\n"
                "▷  작전 중 피격 피해\n\n"
                "▷  최대 콤보 스트릭"
            ),
            parent=self.aar_modal,
            pos=(-0.88, 0.45),
            scale=0.028,
            fg=(0.75, 0.85, 0.95, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            **self.font_kw
        )

        self.aar_stats_values = OnscreenText(
            text="-\n\n-\n\n-\n\n-\n\n-\n\n-\n\n-",
            parent=self.aar_modal,
            pos=(-0.10, 0.45),
            scale=0.028,
            fg=(0.35, 1.0, 0.65, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ARight,
            mayChange=True,
            **self.font_kw
        )

        # 우측 전술 평가 및 등급 패널
        self.aar_rank_frame = DirectFrame(
            parent=self.aar_modal,
            image='assets/ui/card_relic_bg.png',
            relief=None,
            frameSize=(-0.52, 0.52, -0.44, 0.44),
            image_scale=(0.52, 1.0, 0.44),
            pos=(0.52, 0, 0.12)
        )
        self.aar_rank_frame.setTransparency(TransparencyAttrib.MAlpha)

        self.aar_rank_title_hdr = OnscreenText(
            text="[ 작전 종합 평가 등급 ]",
            parent=self.aar_rank_frame,
            pos=(0, 0.32),
            scale=0.026,
            fg=(0.85, 0.90, 1.0, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.aar_rank_badge = OnscreenText(
            text="RANK  S+",
            parent=self.aar_rank_frame,
            pos=(0, 0.14),
            scale=0.068,
            fg=(1.0, 0.85, 0.20, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.aar_rank_title = OnscreenText(
            text="[ 천재적인 생존자 (APEX SURVIVOR) ]",
            parent=self.aar_rank_frame,
            pos=(0, 0.02),
            scale=0.026,
            fg=(0.35, 1.0, 0.85, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.aar_rank_comment = OnscreenText(
            text="완벽한 기동과 치명적인 명중률로\n구역 내 위협을 완전히 소탕했습니다.",
            parent=self.aar_rank_frame,
            pos=(0, -0.12),
            scale=0.022,
            fg=(0.80, 0.85, 0.90, 0.9),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.aar_reward_text = OnscreenText(
            text="[ 보급 보너스 ] EXP +500 & 전술 탄약 보충",
            parent=self.aar_rank_frame,
            pos=(0, -0.32),
            scale=0.024,
            fg=(1.0, 0.85, 0.30, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 하단 계속하기 버튼
        btn_aar_style = {
            "image": ('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.42, 1, 0.062),
            "text_scale": ((0.062 / 0.42) * 0.46, 0.46),
            "text_pos": (0, -0.15),
            "text_fg": (1, 1, 1, 1),
            **self.btn_font_kw
        }
        self.btn_aar_continue = DirectButton(
            parent=self.aar_modal,
            text="특성 강화 및 다음 구역 진입 (PROCEED)",
            pos=(0, 0, -0.66),
            command=self._on_aar_continue_clicked,
            **btn_aar_style
        )

    def show_after_action_report(self, stage, stats, on_continue_callback=None):
        """스테이지 클리어 전투 결과 보고서 표시 및 평가 등급 판정"""
        self.on_aar_continue = on_continue_callback

        self.aar_title.setText(f"[ ★ AFTER-ACTION REPORT // STAGE {stage} 작전 결과 보고서 ★ ]")
        self.aar_sub.setText(f"구역 방어 성공 및 탈출 관문 확보 - STAGE {stage} CLEAR")

        kills = int(stats.get("kills", 0))
        headshots = int(stats.get("headshots", 0))
        shots_fired = int(stats.get("shots_fired", 0))
        shots_hit = int(stats.get("shots_hit", 0))
        accuracy = float(stats.get("accuracy", 0.0))
        headshot_ratio = float(stats.get("headshot_ratio", 0.0))
        damage_dealt = float(stats.get("damage_dealt", 0.0))
        damage_taken = float(stats.get("damage_taken", 0.0))
        max_combo = int(stats.get("max_combo", 0))
        clear_time = float(stats.get("clear_time", 0.0))

        mins = int(clear_time) // 60
        secs = int(clear_time) % 60

        val_str = (
            f"{mins:02d}:{secs:02d}\n\n"
            f"{kills} 마리\n\n"
            f"{accuracy:.1f}% ({shots_hit} / {shots_fired})\n\n"
            f"{headshot_ratio:.1f}% ({headshots} hits)\n\n"
            f"{int(round(damage_dealt)):,} DMG\n\n"
            f"{int(round(damage_taken))} HP\n\n"
            f"{max_combo} COMBO"
        )
        self.aar_stats_values.setText(val_str)

        # 전투 점수 및 종합 등급 판정
        score = 0
        if accuracy >= 65.0: score += 250
        elif accuracy >= 45.0: score += 150
        if headshot_ratio >= 35.0: score += 200
        elif headshot_ratio >= 20.0: score += 100
        if damage_taken <= 40.0: score += 250
        elif damage_taken <= 80.0: score += 120
        if clear_time <= 150.0: score += 200
        elif clear_time <= 240.0: score += 100
        score += min(300, kills * 15)
        score += min(200, max_combo * 20)

        if score >= 880:
            rank_str = "RANK  S+"
            rank_col = (1.0, 0.85, 0.20, 1.0)
            title_str = "[ 천재적인 생존자 (APEX SURVIVOR) ]"
            title_col = (0.35, 1.0, 0.85, 1.0)
            desc_str = "완벽한 전술 기동과 치명적인 화력 집중으로\n구역 내 모든 위협을 압도적으로 섬멸했습니다."
        elif score >= 640:
            rank_str = "RANK  S"
            rank_col = (1.0, 0.75, 0.25, 1.0)
            title_str = "[ 특수부대 정예 (ELITE OPERATOR) ]"
            title_col = (1.0, 0.85, 0.35, 1.0)
            desc_str = "신속한 판단과 날카로운 사격 솜씨로\n탈출 관문을 완벽히 사수하고 돌파했습니다."
        elif score >= 400:
            rank_str = "RANK  A"
            rank_col = (0.35, 0.90, 1.0, 1.0)
            title_str = "[ 베테랑 요원 (VETERAN AGENT) ]"
            title_col = (0.45, 0.85, 1.0, 1.0)
            desc_str = "치열한 교전 속에서도 침착함을 유지하며\n임무 목표를 성공적으로 완수했습니다."
        else:
            rank_str = "RANK  B"
            rank_col = (0.85, 0.88, 0.92, 1.0)
            title_str = "[ 생존 임무 완수 (SURVIVOR) ]"
            title_col = (0.80, 0.85, 0.90, 1.0)
            desc_str = "위기 상황을 극복하고 탈출에 성공했습니다.\n다음 구역에서는 추가 전술 보강이 권장됩니다."

        self.aar_rank_badge.setText(rank_str)
        self.aar_rank_badge.setFg(rank_col)
        self.aar_rank_title.setText(title_str)
        self.aar_rank_title.setFg(title_col)
        self.aar_rank_comment.setText(desc_str)

        self.aar_modal.show()

    def hide_after_action_report(self):
        """결과 보고서 모달 숨김"""
        if hasattr(self, 'aar_modal') and self.aar_modal:
            self.aar_modal.hide()

    def is_after_action_report_open(self):
        """결과 보고서 모달 오픈 상태 반환"""
        return hasattr(self, 'aar_modal') and self.aar_modal and not self.aar_modal.isHidden()

    def _on_aar_continue_clicked(self):
        self.hide_after_action_report()
        if self.on_aar_continue:
            self.on_aar_continue()
