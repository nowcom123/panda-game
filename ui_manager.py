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
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.DirectGui import DirectButton, DirectFrame, DGG
from panda3d.core import TextNode, TransparencyAttrib, LineSegs
from constants import CURSED_RELICS


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

    def trigger_hit(self, is_crit=False):
        if is_crit:
            self.hit_geom.hide()
            self.crit_geom.show()
        else:
            self.crit_geom.hide()
            self.hit_geom.show()

    def reset_hit(self):
        self.hit_geom.hide()
        self.crit_geom.hide()

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
    def __init__(self, base, loader, on_start, on_return_menu, on_exit):
        self.base = base
        self.loader = loader
        self.on_start = on_start
        self.on_return_menu = on_return_menu
        self.on_exit = on_exit

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
        self._cached_door_str = ""
        self._cached_hp_str = ""
        self._cached_exp_str = ""

        # 상점 콜백 및 선택된 특성
        self.selected_upgrade = "ATTACK"
        self.on_shop_confirm = None
        self.on_escape_victory = None

        # UI 요소 빌드
        self._setup_hud()
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
        # 1. 엠비언트 다크 호러 비네트 (화면 외곽 심도감)
        self.vignette_dark = OnscreenImage(
            image="assets/ui/vignette_dark.png",
            pos=(0, 0, 0),
            scale=(1.34, 1, 1.0),
            parent=self.base.aspect2d
        )
        self.vignette_dark.setTransparency(TransparencyAttrib.MAlpha)
        self.vignette_dark.setBin("fixed", 1)

        # 2. 피격 핏자국 및 저체력 심장박동 맥동 비네트
        self.vignette_blood = OnscreenImage(
            image="assets/ui/vignette_blood.png",
            pos=(0, 0, 0),
            scale=(1.34, 1, 1.0),
            parent=self.base.aspect2d
        )
        self.vignette_blood.setTransparency(TransparencyAttrib.MAlpha)
        self.vignette_blood.setBin("fixed", 2)
        self.vignette_blood.setColorScale(1, 1, 1, 0.0)

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

        # 4. 상단 목표/나침반 패널
        self.panel_hud_top = OnscreenImage(
            image="assets/ui/panel_hud_top.png",
            pos=(0, 0, 0.91),
            scale=(0.54, 1, 0.060),
            parent=self.base.aspect2d
        )
        self.panel_hud_top.setTransparency(TransparencyAttrib.MAlpha)
        self.panel_hud_top.setBin("fixed", 4)

        self.icon_radar = OnscreenImage(
            image="assets/ui/icon_radar.png",
            pos=(-0.45, 0, 0.91),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_radar.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_radar.setBin("fixed", 5)

        self.hud_text = OnscreenText(
            text="[ 비상 탈출구 신호 탐색 중... ]",
            pos=(-0.40, 0.90),
            scale=0.028,
            fg=(0.45, 0.85, 1.0, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.timer_text = OnscreenText(
            text="[ 05:00 ]",
            pos=(0.45, 0.90),
            scale=0.032,
            fg=(0.25, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ARight,
            mayChange=True,
            **self.font_kw
        )

        # 5. 좌상단 상태바 (HP, 스테미나, EXP, 유물)
        # 5-1. 체력바
        self.icon_hp = OnscreenImage(
            image="assets/ui/icon_health.png",
            pos=(-1.28, 0, 0.88),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_hp.setBin("fixed", 5)

        self.bar_frame_hp = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-0.96, 0, 0.88),
            scale=(0.28, 1, 0.024),
            parent=self.base.aspect2d
        )
        self.bar_frame_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_hp.setBin("fixed", 5)

        self.bar_fill_hp = OnscreenImage(
            image="assets/ui/bar_hp_fill.png",
            pos=(-0.96, 0, 0.88),
            scale=(0.27, 1, 0.018),
            parent=self.base.aspect2d
        )
        self.bar_fill_hp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_hp.setBin("fixed", 6)

        self.hp_text = OnscreenText(
            text="100 / 100",
            pos=(-0.65, 0.87),
            scale=0.024,
            fg=(0.20, 0.95, 0.40, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-2. 스테미나바
        self.icon_stamina = OnscreenImage(
            image="assets/ui/icon_stamina.png",
            pos=(-1.28, 0, 0.82),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_stamina.setBin("fixed", 5)

        self.bar_frame_stamina = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-0.96, 0, 0.82),
            scale=(0.28, 1, 0.024),
            parent=self.base.aspect2d
        )
        self.bar_frame_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_stamina.setBin("fixed", 5)

        self.bar_fill_stamina = OnscreenImage(
            image="assets/ui/bar_stamina_fill.png",
            pos=(-0.96, 0, 0.82),
            scale=(0.27, 1, 0.018),
            parent=self.base.aspect2d
        )
        self.bar_fill_stamina.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_stamina.setBin("fixed", 6)

        self.stamina_text = OnscreenText(
            text="100%",
            pos=(-0.65, 0.81),
            scale=0.024,
            fg=(0.35, 0.95, 0.5, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-3. 경험치바
        self.icon_exp = OnscreenImage(
            image="assets/ui/icon_exp.png",
            pos=(-1.28, 0, 0.76),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_exp.setBin("fixed", 5)

        self.bar_frame_exp = OnscreenImage(
            image="assets/ui/bar_frame.png",
            pos=(-0.96, 0, 0.76),
            scale=(0.28, 1, 0.024),
            parent=self.base.aspect2d
        )
        self.bar_frame_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_frame_exp.setBin("fixed", 5)

        self.bar_fill_exp = OnscreenImage(
            image="assets/ui/bar_exp_fill.png",
            pos=(-0.96, 0, 0.76),
            scale=(0.27, 1, 0.018),
            parent=self.base.aspect2d
        )
        self.bar_fill_exp.setTransparency(TransparencyAttrib.MAlpha)
        self.bar_fill_exp.setBin("fixed", 6)

        self.exp_text = OnscreenText(
            text="[LV. 1] 0/100",
            pos=(-0.65, 0.75),
            scale=0.024,
            fg=(0.85, 0.70, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5-4. 유물 배지
        self.icon_relic = OnscreenImage(
            image="assets/ui/icon_relic.png",
            pos=(-1.28, 0, 0.70),
            scale=0.030,
            parent=self.base.aspect2d
        )
        self.icon_relic.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_relic.setBin("fixed", 5)

        self.relic_badge_text = OnscreenText(
            text="[보유 유물] 없음",
            pos=(-1.23, 0.69),
            scale=0.024,
            fg=(0.85, 0.70, 1.0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 6. 우하단 탄약 HUD 패널
        self.panel_hud_ammo = OnscreenImage(
            image="assets/ui/panel_hud_ammo.png",
            pos=(1.10, 0, -0.84),
            scale=(0.23, 1, 0.075),
            parent=self.base.aspect2d
        )
        self.panel_hud_ammo.setTransparency(TransparencyAttrib.MAlpha)
        self.panel_hud_ammo.setBin("fixed", 4)

        self.icon_ammo = OnscreenImage(
            image="assets/ui/icon_ammo.png",
            pos=(0.95, 0, -0.84),
            scale=0.032,
            parent=self.base.aspect2d
        )
        self.icon_ammo.setTransparency(TransparencyAttrib.MAlpha)
        self.icon_ammo.setBin("fixed", 5)

        self.ammo_text = OnscreenText(
            text="12 / 12",
            pos=(1.25, -0.85),
            scale=0.034,
            fg=(1.0, 0.90, 0.35, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ARight,
            mayChange=True,
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
            scale=0.034,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.door_status_text.hide()

        # 알림/피격 텍스트
        self.hit_marker_text = OnscreenText(
            text="",
            pos=(0, -0.16),
            scale=0.032,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.blackout_banner = OnscreenText(
            text="[ ! 비상 경보: 정전 프로토콜 발동 ! ]\n기지 전력 차단! 붉은 비상등 가동 (몬스터 폭주 / 처치 보상 2배)",
            pos=(0, 0.74),
            scale=0.036,
            fg=(1.0, 0.15, 0.15, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.blackout_banner.hide()
        self.blackout_pulse_timer = 0.0

        # 인게임 전술 퀵슬롯 HUD (소모품 수량 실시간 표시)
        self.quickslot_text = OnscreenText(
            text="[1] 응급키트: 2개  |  [2] 아드레날린: 1개  |  [3] 탄약팩: 2개  |  [4] 수류탄: 1개  |  [Tab/I] 배낭",
            pos=(0, -0.88),
            scale=0.024,
            fg=(0.35, 0.95, 1.0, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.guide_text = OnscreenText(
            text="[WASD] 이동  |  [Space] 슬라이드  |  [G] 전술수류탄  |  [우클릭] 정밀조준  |  [좌클릭] 사격  |  [R] 재장전  |  [Tab/I] 인벤토리",
            pos=(0, -0.93),
            scale=0.022,
            fg=(0.9, 0.9, 0.8, 0.85),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )

        # 스타일 킬 & 콤보 어나운서 배너 (화면 중앙 상단)
        self.style_kill_banner = OnscreenText(
            text="",
            pos=(0, 0.48),
            scale=0.046,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.style_kill_banner.hide()
        self.style_kill_timer = 0.0

        # 전술 스킬 (Space 슬라이드 / G 수류탄) 쿨다운 HUD 인디케이터
        self.skills_status_text = OnscreenText(
            text="[SPACE] 슬라이드: READY   |   [G] 수류탄: READY",
            pos=(1.28, -0.74),
            scale=0.024,
            fg=(0.35, 1.0, 0.65, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ARight,
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
        """메인 인트로 타이틀 및 메뉴 버튼 (이미지 배경 및 텍스처 버튼)"""
        self.intro_frame = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-0.90, 0.90, -0.72, 0.72),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.intro_frame.setTransparency(TransparencyAttrib.MAlpha)

        self.intro_title = OnscreenText(
            text="LIMINAL BACKROOMS",
            parent=self.intro_frame,
            pos=(0, 0.48),
            scale=0.075,
            fg=(0.95, 0.95, 0.95, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_subtitle = OnscreenText(
            text="[ 5분 던전 크롤러 RPG : 심연의 미궁 ]",
            parent=self.intro_frame,
            pos=(0, 0.35),
            scale=0.032,
            fg=(0.95, 0.45, 0.20, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_desc = OnscreenText(
            text="미궁에 도사린 몬스터들을 처치하여 경험치를 획득하고 레벨업하세요.\n5분 안에 비상탈출구를 찾아 5초간 사수하면 상점에서 특성을 강화하고 다음 층으로 내려갑니다.",
            parent=self.intro_frame,
            pos=(0, 0.20),
            scale=0.024,
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
            pos=(0, 0, 0.02),
            scale=(0.48, 1, 0.070),
            text_scale=((0.070 / 0.48) * 0.46, 0.46),
            text_pos=(0, -0.14),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self.on_start,
            **self.btn_font_kw
        )
        self.btn_start.setTransparency(TransparencyAttrib.MAlpha)

        self.btn_rank = DirectButton(
            parent=self.intro_frame,
            image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="RANKING",
            pos=(0, 0, -0.15),
            scale=(0.48, 1, 0.070),
            text_scale=((0.070 / 0.48) * 0.46, 0.46),
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
            pos=(0, 0, -0.32),
            scale=(0.48, 1, 0.070),
            text_scale=((0.070 / 0.48) * 0.46, 0.46),
            text_pos=(0, -0.14),
            text_fg=(1.0, 0.45, 0.45, 1.0),
            command=self.on_exit,
            **self.btn_font_kw
        )
        self.btn_exit.setTransparency(TransparencyAttrib.MAlpha)

    def _setup_rank_ui(self):
        """기록 랭킹 팝업 모달창"""
        self.rank_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.10, 1.10, -0.80, 0.80),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.rank_modal.setTransparency(TransparencyAttrib.MAlpha)

        self.rank_title = OnscreenText(
            text="[ 생존 & 탈출 기록 랭킹 (RANKING) ]",
            parent=self.rank_modal,
            pos=(0, 0.65),
            scale=0.044,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.rank_content = OnscreenText(
            text="기록을 불러오는 중...",
            parent=self.rank_modal,
            pos=(-0.95, 0.48),
            scale=0.024,
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
            pos=(0, 0, -0.68),
            scale=(0.40, 1, 0.058),
            text_scale=((0.058 / 0.40) * 0.48, 0.48),
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
            getattr(self, 'panel_hud_ammo', None),
            getattr(self, 'icon_ammo', None),
            getattr(self, 'ammo_text', None),
            getattr(self, 'skills_status_text', None),
            getattr(self, 'quickslot_text', None),
            getattr(self, 'guide_text', None),
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
        self.hit_marker_timer = 2.2

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
        """몬스터 타격 시 크로스헤어 적중 마커 표시 (치명타 시 골드 마커)"""
        self.crosshair_hit_timer = 0.22 if is_crit else 0.18
        if hasattr(self.crosshair, 'trigger_hit'):
            self.crosshair.trigger_hit(is_crit=is_crit)
        elif hasattr(self.crosshair, 'setImage'):
            if is_crit:
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

        if hasattr(self, 'style_kill_timer') and self.style_kill_timer > 0.0:
            self.style_kill_timer = max(0.0, self.style_kill_timer - dt)
            if self.style_kill_timer <= 0.0 and hasattr(self, 'style_kill_banner'):
                self.style_kill_banner.hide()

        if hasattr(self, 'blackout_banner') and not self.blackout_banner.isHidden():
            self.blackout_pulse_timer += dt * 6.5
            alpha = 0.55 + 0.45 * math.sin(self.blackout_pulse_timer)
            self.blackout_banner.setFg((1.0, 0.15, 0.15, alpha))

    def show_style_kill(self, title, bonus_str="", color=(1.0, 0.85, 0.2, 1.0)):
        """스타일 킬 / 콤보 어나운서 팝업 표시"""
        display_text = f"{title}   {bonus_str}" if bonus_str else title
        self.style_kill_banner.setText(display_text)
        self.style_kill_banner.setFg(color)
        self.style_kill_banner.show()
        self.style_kill_timer = 1.8

    def update_skills_hud(self, slide_ready, grenade_timer, grenade_max=9.0):
        """슬라이드 및 수류탄 쿨다운 실시간 텍스트 갱신"""
        slide_str = "READY" if slide_ready else "COOL"
        gr_str = "READY" if grenade_timer <= 0.0 else f"{grenade_timer:.1f}s"
        txt = f"[SPACE] 슬라이드: {slide_str}   |   [G] 수류탄: {gr_str}"
        self.skills_status_text.setText(txt)
        if slide_ready and grenade_timer <= 0.0:
            self.skills_status_text.setFg((0.35, 1.0, 0.65, 0.95))
        elif not slide_ready or grenade_timer > 0.0:
            self.skills_status_text.setFg((1.0, 0.85, 0.40, 0.95))

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

        if time_left <= 10.0:
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

    def update_ammo(self, ammo, max_ammo, reserve_ammo=0):
        if reserve_ammo > 0:
            msg = f"{ammo} / {max_ammo}  (+{reserve_ammo})"
        else:
            msg = f"{ammo} / {max_ammo}"
        if msg != self._cached_ammo_str:
            self.ammo_text.setText(msg)
            if ammo <= 3:
                self.ammo_text.setFg((1.0, 0.25, 0.25, 1.0))
            else:
                self.ammo_text.setFg((1.0, 0.90, 0.35, 1.0))
            self._cached_ammo_str = msg

    def update_stamina(self, stamina, max_stamina, is_sprinting=False, is_exhausted=False):
        pct = max(0.0, min(1.0, stamina / max(1.0, max_stamina)))
        self._set_bar_percentage(self.bar_fill_stamina, pct, -0.96, 0.82, 0.28, 0.024)

        stamina_pct = int(pct * 100)
        if is_exhausted:
            msg = f"{stamina_pct}% (탈진!)"
            col = (1.0, 0.25, 0.25, 1.0)
        elif is_sprinting:
            msg = f"{stamina_pct}% (달리기)"
            col = (1.0, 0.85, 0.2, 1.0)
        else:
            msg = f"{stamina_pct}%"
            col = (0.35, 0.95, 0.5, 0.95)

        if msg != self._cached_stamina_str:
            self.stamina_text.setText(msg)
            self._cached_stamina_str = msg
        if col != self._cached_stamina_col:
            self.stamina_text.setFg(col)
            self._cached_stamina_col = col

    def update_hp_exp(self, hp, max_hp, exp, exp_to_next, level=1, stat_points=0):
        pct_hp = max(0.0, min(1.0, hp / max(1.0, max_hp)))
        self._set_bar_percentage(self.bar_fill_hp, pct_hp, -0.96, 0.88, 0.28, 0.024)
        msg_hp = f"{int(hp)} / {int(max_hp)}"
        if msg_hp != self._cached_hp_str:
            self.hp_text.setText(msg_hp)
            if pct_hp <= 0.25:
                self.hp_text.setFg((1.0, 0.25, 0.25, 1.0))
            elif pct_hp <= 0.55:
                self.hp_text.setFg((1.0, 0.85, 0.2, 1.0))
            else:
                self.hp_text.setFg((0.20, 0.95, 0.40, 1.0))
            self._cached_hp_str = msg_hp

        pct_exp = max(0.0, min(1.0, exp / max(1.0, exp_to_next)))
        self._set_bar_percentage(self.bar_fill_exp, pct_exp, -0.96, 0.76, 0.28, 0.024)
        sp_tag = f" [스탯 +{stat_points}]" if stat_points > 0 else ""
        msg_exp = f"[LV.{level}] {int(exp)}/{int(exp_to_next)}{sp_tag}"
        if msg_exp != self._cached_exp_str:
            self.exp_text.setText(msg_exp)
            self._cached_exp_str = msg_exp

    def update_hud(self, px, py, escape_pos=None, heading=0.0):
        if escape_pos:
            dx = escape_pos[0] - px
            dy = escape_pos[1] - py
            dist = math.hypot(dx, dy)
            target_h = math.degrees(math.atan2(-dx, dy))
            rel_h = (target_h - heading + 180) % 360 - 180

            if abs(rel_h) <= 22.5:
                dir_str = "▲ 전방"
            elif 22.5 < rel_h <= 67.5:
                dir_str = "↗ 전방 우측"
            elif 67.5 < rel_h <= 112.5:
                dir_str = "▶ 우측"
            elif 112.5 < rel_h <= 157.5:
                dir_str = "↘ 후방 우측"
            elif abs(rel_h) > 157.5:
                dir_str = "▼ 후방"
            elif -67.5 <= rel_h < -22.5:
                dir_str = "↖ 전방 좌측"
            elif -112.5 <= rel_h < -67.5:
                dir_str = "◀ 좌측"
            else:
                dir_str = "↙ 후방 좌측"

            if dist <= 25.0:
                msg = f"[ 비상 탈출구: {dist:.0f}m ({dir_str}) ◎ 근접! ]"
                col = (0.35, 1.0, 0.45, 1.0)
            elif dist <= 60.0:
                msg = f"[ 비상 탈출구: {dist:.0f}m ({dir_str}) ]"
                col = (0.95, 0.85, 0.35, 1.0)
            else:
                msg = f"[ 비상 탈출구 신호: {dist:.0f}m ({dir_str}) ]"
                col = (0.45, 0.85, 1.0, 0.95)
        else:
            msg = f"위치: X={px:.1f}, Y={py:.1f}"
            col = (1, 1, 1, 0.9)

        if msg != self._cached_hud_str:
            self.hud_text.setText(msg)
            self._cached_hud_str = msg
            self.hud_text.setFg(col)

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

    # --- [스테이지 클리어: 스탯 분배 상점 모달 (이미지 기반 배경/카드/버튼)] ---
    def _setup_shop_ui(self):
        self.shop_player = None
        self.shop_combat = None
        self.on_shop_confirm = None
        self.on_escape_victory = None

        self.shop_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.28, 1.28, -0.88, 0.88),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.shop_modal.setTransparency(TransparencyAttrib.MAlpha)

        self.shop_title = OnscreenText(
            text="[ STAGE CLEAR! 스탯 분배 및 보급소 ]",
            parent=self.shop_modal,
            pos=(0, 0.72),
            scale=0.040,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.shop_desc = OnscreenText(
            text="비상탈출구를 사수했습니다! 스탯 포인트를 분배하고 고대 미궁의 저주받은 유물을 선택하세요.",
            parent=self.shop_modal,
            pos=(0, 0.64),
            scale=0.024,
            fg=(0.85, 0.88, 0.92, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        # 보유 스탯 포인트 표시
        self.shop_stat_points_text = OnscreenText(
            text="[ 보유 스탯 포인트: 0 P ]",
            parent=self.shop_modal,
            pos=(0, 0.55),
            scale=0.032,
            fg=(1.0, 0.88, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        btn_alloc_style = {
            "image": ('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
            "relief": None,
            "scale": (0.24, 1, 0.046),
            "text_scale": ((0.046 / 0.24) * 0.48, 0.48),
            "text_pos": (0, -0.14)
        }

        # --- 1단: 스탯 강화 4종 (2열 그리드 배치) ---
        # 1-1. 공격력 (좌측)
        self.stat_label_atk = OnscreenText(
            text="[공격력] 현재: 35 (+5)",
            parent=self.shop_modal,
            pos=(-1.12, 0.44),
            scale=0.026,
            fg=(1.0, 0.80, 0.40, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_atk = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(-0.20, 0, 0.45),
            text_fg=(1.0, 0.85, 0.4, 1.0),
            command=self._allocate,
            extraArgs=["ATK"],
            **btn_alloc_style,
            **self.btn_font_kw
        )
        self.btn_alloc_atk.setTransparency(TransparencyAttrib.MAlpha)

        # 1-2. 이동 속도 (좌측 하단)
        self.stat_label_spd = OnscreenText(
            text="[이동 속도] 현재: 100% (+8%)",
            parent=self.shop_modal,
            pos=(-1.12, 0.33),
            scale=0.026,
            fg=(0.45, 0.85, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_spd = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(-0.20, 0, 0.34),
            text_fg=(0.45, 0.85, 1.0, 1.0),
            command=self._allocate,
            extraArgs=["SPD"],
            **btn_alloc_style,
            **self.btn_font_kw
        )
        self.btn_alloc_spd.setTransparency(TransparencyAttrib.MAlpha)

        # 1-3. 최대 체력 (우측)
        self.stat_label_hp = OnscreenText(
            text="[최대 체력] 현재: 100 (+25)",
            parent=self.shop_modal,
            pos=(0.06, 0.44),
            scale=0.026,
            fg=(0.40, 1.0, 0.60, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_hp = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(0.96, 0, 0.45),
            text_fg=(0.4, 1.0, 0.6, 1.0),
            command=self._allocate,
            extraArgs=["HP"],
            **btn_alloc_style,
            **self.btn_font_kw
        )
        self.btn_alloc_hp.setTransparency(TransparencyAttrib.MAlpha)

        # 1-4. 최대 탄약 (우측 하단)
        self.stat_label_ammo = OnscreenText(
            text="[최대 탄약] 현재: 12발 (+2발)",
            parent=self.shop_modal,
            pos=(0.06, 0.33),
            scale=0.026,
            fg=(1.0, 0.92, 0.40, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_ammo = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(0.96, 0, 0.34),
            text_fg=(1.0, 0.92, 0.4, 1.0),
            command=self._allocate,
            extraArgs=["AMMO"],
            **btn_alloc_style,
            **self.btn_font_kw
        )
        self.btn_alloc_ammo.setTransparency(TransparencyAttrib.MAlpha)

        # --- 2단: 저주받은 유물 선택 (3개 이미지 카드) ---
        self.relic_section_title = OnscreenText(
            text="[ 고대 미궁의 저주받은 유물 (1개 선택 또는 다음 스테이지로 스킵) ]",
            parent=self.shop_modal,
            pos=(0, 0.22),
            scale=0.030,
            fg=(0.95, 0.72, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.relic_cards = []
        self.offered_relics = []
        card_xs = [-0.78, 0.0, 0.78]

        for i in range(3):
            card_f = DirectFrame(
                parent=self.shop_modal,
                image='assets/ui/card_relic_bg.png',
                relief=None,
                frameSize=(-0.36, 0.36, -0.21, 0.21),
                pos=(card_xs[i], 0, -0.04),
                scale=(1.0, 1, 1.0)
            )
            card_f.setTransparency(TransparencyAttrib.MAlpha)

            r_title = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, 0.12),
                scale=0.026,
                fg=(1.0, 0.88, 0.35, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_pro = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, 0.03),
                scale=0.022,
                fg=(0.35, 1.0, 0.55, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_con = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, -0.05),
                scale=0.022,
                fg=(1.0, 0.38, 0.38, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_btn = DirectButton(
                parent=card_f,
                image=('assets/ui/btn_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_hover.png', 'assets/ui/btn_disabled.png'),
                relief=None,
                text="[ 선택 획득 ]",
                pos=(0, 0, -0.14),
                scale=(0.30, 1, 0.044),
                text_scale=((0.044 / 0.30) * 0.48, 0.48),
                text_pos=(0, -0.15),
                text_fg=(0.95, 0.80, 1.0, 1.0),
                command=self._select_relic,
                extraArgs=[i],
                **self.btn_font_kw
            )
            r_btn.setTransparency(TransparencyAttrib.MAlpha)

            self.relic_cards.append({
                "frame": card_f,
                "title": r_title,
                "pro": r_pro,
                "con": r_con,
                "btn": r_btn
            })

        # 분배 안내 피드백 메시지
        self.shop_msg_text = OnscreenText(
            text="",
            parent=self.shop_modal,
            pos=(0, -0.34),
            scale=0.026,
            fg=(0.4, 1.0, 0.6, 1.0),
            shadow=(0, 0, 0, 0.9),
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
            pos=(0, 0, -0.48),
            scale=(0.54, 1, 0.058),
            text_scale=((0.058 / 0.54) * 0.46, 0.46),
            text_pos=(0, -0.15),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self._confirm_shop_and_start,
            **self.btn_font_kw
        )
        self.btn_start_next.setTransparency(TransparencyAttrib.MAlpha)

        # 미궁 완전 탈출 승리 버튼 (STAGE 3 이상 클리어 시 선택 가능)
        self.btn_escape_victory = DirectButton(
            parent=self.shop_modal,
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="★ 미궁 완전 탈출 (VICTORY ESCAPE) ★",
            pos=(0.35, 0, -0.48),
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

    def _refresh_shop_labels(self):
        """플레이어의 현재 스탯과 보유 포인트를 UI 텍스트에 실시간 반영"""
        if not self.shop_player:
            return
        sp = getattr(self.shop_player, 'stat_points', 0)
        self.shop_stat_points_text.setText(f"[ 보유 스탯 포인트: {sp} P ]")
        if sp > 0:
            self.shop_stat_points_text.setFg((1.0, 0.88, 0.25, 1.0))
        else:
            self.shop_stat_points_text.setFg((0.65, 0.65, 0.65, 0.9))

        atk = int(getattr(self.shop_player, 'attack_power', 35))
        hp = int(getattr(self.shop_player, 'max_hp', 100))
        spd_pct = int(getattr(self.shop_player, 'speed_mult', 1.0) * 100)
        ammo = self.shop_combat.max_ammo if self.shop_combat else 12

        self.stat_label_atk.setText(f"[공격력] 현재: {atk} (+5)")
        self.stat_label_hp.setText(f"[최대 체력] 현재: {hp} (+25)")
        self.stat_label_spd.setText(f"[이동 속도] 현재: {spd_pct}% (+8%)")
        self.stat_label_ammo.setText(f"[최대 탄약] 현재: {ammo}발 (+2발)")

    def _allocate(self, stat_type):
        """스탯 1개 분배 클릭 이벤트"""
        if not self.shop_player:
            return
        if self.shop_player.stat_points <= 0:
            self.shop_msg_text.setText("남은 스탯 포인트가 없습니다! 몬스터를 처치하여 레벨업하세요.")
            self.shop_msg_text.setFg((1.0, 0.35, 0.35, 1.0))
            return

        ok, msg = self.shop_player.allocate_stat(stat_type, self.shop_combat)
        if ok:
            self.shop_msg_text.setText(f"★ {msg}")
            self.shop_msg_text.setFg((0.35, 1.0, 0.55, 1.0))
        self._refresh_shop_labels()

    def _select_relic(self, card_idx):
        """저주받은 유물 선택 클릭 이벤트"""
        if card_idx >= len(self.offered_relics) or not self.shop_player:
            return
        relic = self.offered_relics[card_idx]
        self.shop_player.acquire_relic(relic["id"])

        self.shop_msg_text.setText(f"★ [{relic['name']}] 유물을 장착했습니다! ({relic['desc']})")
        self.shop_msg_text.setFg((0.95, 0.75, 1.0, 1.0))

        # 모든 유물 카드 비활성화 및 활성화 카드 하이라이트
        for idx, c in enumerate(self.relic_cards):
            c["btn"]["state"] = DGG.DISABLED
            if idx == card_idx:
                c["frame"]["image"] = 'assets/ui/card_relic_active.png'
                c["btn"]["text"] = "[ 장착 완료 ]"
            else:
                c["btn"]["text"] = "[ 미선택 ]"
        self._refresh_shop_labels()

    def _confirm_shop_and_start(self):
        self.hide_stage_clear_shop()
        if self.on_shop_confirm:
            self.on_shop_confirm()

    def _confirm_escape_victory(self):
        self.hide_stage_clear_shop()
        if hasattr(self, 'on_escape_victory') and self.on_escape_victory:
            self.on_escape_victory()

    def show_stage_clear_shop(self, stage, player, combat, on_confirm_callback, on_victory_callback=None):
        self.shop_player = player
        self.shop_combat = combat
        self.on_shop_confirm = on_confirm_callback
        self.on_escape_victory = on_victory_callback
        self.shop_title.setText(f"[ STAGE {stage} CLEAR! 스탯 분배 및 보급소 ]")
        self.shop_msg_text.setText("")
        self._refresh_shop_labels()

        # STAGE 3 이상 클리어 시 미궁 완전 탈출 버튼 활성화
        if stage >= 3 and on_victory_callback is not None:
            self.btn_start_next.setPos(-0.35, 0, -0.48)
            self.btn_start_next["text"] = "심연 더 깊이 진입 (NEXT STAGE)"
            self.btn_escape_victory.setPos(0.35, 0, -0.48)
            self.btn_escape_victory.show()
        else:
            self.btn_start_next.setPos(0, 0, -0.48)
            self.btn_start_next["text"] = "다음 스테이지 시작 (START NEXT STAGE)"
            self.btn_escape_victory.hide()

        # 미보유 유물 풀에서 무작위 3개 선별
        acquired = set(getattr(player, 'relics', []))
        available = [r for r in CURSED_RELICS.values() if r["id"] not in acquired]
        pick_count = min(3, len(available))
        self.offered_relics = random.sample(available, pick_count) if pick_count > 0 else []

        for i, card in enumerate(self.relic_cards):
            card["frame"]["image"] = 'assets/ui/card_relic_bg.png'
            if i < len(self.offered_relics):
                relic = self.offered_relics[i]
                card["frame"].show()
                card["title"].setText(f"{relic['icon']} {relic['name']}")
                card["pro"].setText(f"+ {relic['pro']}")
                card["con"].setText(f"- {relic['con']}")
                card["btn"]["state"] = DGG.NORMAL
                card["btn"]["text"] = "[ 선택 획득 ]"
            else:
                card["frame"].hide()

        self.hide_all_ingame()
        self.shop_modal.show()

    def hide_stage_clear_shop(self):
        self.shop_modal.hide()

    # --- [전술 군용 인벤토리 배낭 모달 시스템] ---
    def _setup_inventory_ui(self):
        self.inv_player = None
        self.inv_combat = None
        self.on_use_item_callback = None
        self.on_close_inventory = None
        self.selected_inv_slot = 0

        # 메인 반투명 흑요석 전술 모달 배경
        self.inv_modal = DirectFrame(
            image='assets/ui/panel_modal_bg.png',
            relief=None,
            frameSize=(-1.28, 1.28, -0.88, 0.88),
            scale=(1.0, 1, 1.0),
            pos=(0, 0, 0)
        )
        self.inv_modal.setTransparency(TransparencyAttrib.MAlpha)

        # 1. 헤더: 타이틀 & 닫기 버튼
        self.inv_title = OnscreenText(
            text="[ TACTICAL INVENTORY - 전술 군용 배낭 ]",
            parent=self.inv_modal,
            pos=(0, 0.74),
            scale=0.038,
            fg=(0.40, 0.92, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_subtitle = OnscreenText(
            text="생존 소모품 보급 현황 및 장비 관리  |  단축키 [1~4] 인게임 즉시 사용 가능",
            parent=self.inv_modal,
            pos=(0, 0.67),
            scale=0.022,
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
            pos=(0.96, 0, 0.73),
            scale=(0.26, 1, 0.046),
            text_scale=((0.046 / 0.26) * 0.44, 0.44),
            text_pos=(0, -0.14),
            text_fg=(1.0, 0.85, 0.85, 1.0),
            command=self.hide_inventory,
            **self.btn_font_kw
        )
        self.btn_close_inv.setTransparency(TransparencyAttrib.MAlpha)

        # 2. 좌측 칼럼: 생존자 RPG 종합 스탯 & 무기 제원 (x = -0.80)
        self.inv_left_title = OnscreenText(
            text="■ 생존자 상태 및 무기 제원",
            parent=self.inv_modal,
            pos=(-1.14, 0.58),
            scale=0.027,
            fg=(0.95, 0.82, 0.35, 1.0),
            align=TextNode.ALeft,
            **self.font_kw
        )

        self.inv_stats_text = OnscreenText(
            text="",
            parent=self.inv_modal,
            pos=(-1.14, 0.50),
            scale=0.021,
            fg=(0.90, 0.94, 0.98, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 3. 중앙 칼럼: 소지품 6슬롯 전술 배낭 그리드
        self.inv_grid_title = OnscreenText(
            text="■ 전술 보급품 및 소지품 (6 슬롯)",
            parent=self.inv_modal,
            pos=(-0.28, 0.58),
            scale=0.027,
            fg=(0.35, 0.95, 1.0, 1.0),
            align=TextNode.ALeft,
            **self.font_kw
        )

        self.inv_slots = []
        slot_coords = [
            (-0.16, 0.40), (0.16, 0.40),   # Row 1 (Quickslots 1, 2)
            (-0.16, 0.16), (0.16, 0.16),   # Row 2 (Quickslots 3, 4)
            (-0.16, -0.08), (0.16, -0.08)  # Row 3 (Slots 5, 6)
        ]

        for idx, (sx, sz) in enumerate(slot_coords):
            slot_btn = DirectButton(
                parent=self.inv_modal,
                image=('assets/ui/slot_bg_normal.png', 'assets/ui/slot_bg_selected.png', 'assets/ui/slot_bg_selected.png', 'assets/ui/slot_bg_normal.png'),
                relief=None,
                pos=(sx, 0, sz),
                scale=(0.14, 1, 0.11),
                command=self._select_inventory_slot,
                extraArgs=[idx]
            )
            slot_btn.setTransparency(TransparencyAttrib.MAlpha)

            slot_icon = OnscreenImage(
                image='assets/ui/item_medkit.png',
                parent=slot_btn,
                scale=(0.46, 1, 0.46),
                pos=(0, 0, 0.05)
            )
            slot_icon.setTransparency(TransparencyAttrib.MAlpha)
            slot_icon.hide()

            slot_tag = OnscreenText(
                text=f"[{idx+1}]" if idx < 4 else "",
                parent=slot_btn,
                pos=(-0.38, 0.30),
                scale=(0.18, 0.22),
                fg=(0.40, 0.95, 1.0, 1.0),
                shadow=(0, 0, 0, 0.95),
                align=TextNode.ALeft,
                mayChange=True,
                **self.font_kw
            )

            slot_count = OnscreenText(
                text="",
                parent=slot_btn,
                pos=(0.38, -0.32),
                scale=(0.18, 0.22),
                fg=(1.0, 0.90, 0.35, 1.0),
                shadow=(0, 0, 0, 0.95),
                align=TextNode.ARight,
                mayChange=True,
                **self.font_kw
            )

            slot_name = OnscreenText(
                text="[ 빈 슬롯 ]",
                parent=slot_btn,
                pos=(0, -0.44),
                scale=(0.13, 0.16),
                fg=(0.70, 0.75, 0.82, 0.90),
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

        # 4. 우측 칼럼: 선택된 아이템 상세 정보 및 사용 패널 (x = 0.78)
        self.inv_right_title = OnscreenText(
            text="■ 아이템 상세 정보 (INFO)",
            parent=self.inv_modal,
            pos=(0.44, 0.58),
            scale=0.027,
            fg=(0.40, 0.95, 0.60, 1.0),
            align=TextNode.ALeft,
            **self.font_kw
        )

        self.inv_detail_icon = OnscreenImage(
            image='assets/ui/item_medkit.png',
            parent=self.inv_modal,
            scale=(0.10, 1, 0.10),
            pos=(0.78, 0, 0.40)
        )
        self.inv_detail_icon.setTransparency(TransparencyAttrib.MAlpha)

        self.inv_detail_name = OnscreenText(
            text="[ 선택된 아이템 없음 ]",
            parent=self.inv_modal,
            pos=(0.78, 0.27),
            scale=0.028,
            fg=(1.0, 1.0, 1.0, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.inv_detail_meta = OnscreenText(
            text="분류: -  |  보유 수량: -",
            parent=self.inv_modal,
            pos=(0.78, 0.21),
            scale=0.021,
            fg=(0.75, 0.82, 0.90, 0.90),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.inv_detail_desc = OnscreenText(
            text="아이템을 선택하면 상세 정보 및 사용법이 표시됩니다.",
            parent=self.inv_modal,
            pos=(0.48, 0.13),
            scale=0.021,
            fg=(0.88, 0.92, 0.96, 0.95),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.btn_use_item = DirectButton(
            parent=self.inv_modal,
            image=('assets/ui/btn_accent_normal.png', 'assets/ui/btn_click.png', 'assets/ui/btn_accent_hover.png', 'assets/ui/btn_disabled.png'),
            relief=None,
            text="[ 사용하기 (USE ITEM) ]",
            pos=(0.78, 0, -0.06),
            scale=(0.36, 1, 0.052),
            text_scale=((0.052 / 0.36) * 0.48, 0.48),
            text_pos=(0, -0.15),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self._on_click_use_inventory_item,
            **self.btn_font_kw
        )
        self.btn_use_item.setTransparency(TransparencyAttrib.MAlpha)

        self.inv_msg_text = OnscreenText(
            text="",
            parent=self.inv_modal,
            pos=(0.78, -0.15),
            scale=0.022,
            fg=(0.40, 1.0, 0.60, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        # 5. 하단 칼럼: 장착된 고대 저주받은 유물 목록 (z = -0.32 ~ -0.58)
        self.inv_relics_title = OnscreenText(
            text="■ 장착된 고대 미궁의 저주받은 유물 (CURSED RELICS)",
            parent=self.inv_modal,
            pos=(0, -0.30),
            scale=0.026,
            fg=(0.95, 0.72, 1.0, 1.0),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.inv_relic_labels = []
        r_xs = [-0.85, -0.28, 0.28, 0.85]
        for i in range(4):
            lbl = OnscreenText(
                text="[ 빈 유물 슬롯 ]",
                parent=self.inv_modal,
                pos=(r_xs[i], -0.38),
                scale=0.020,
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
            pos=(0, -0.52),
            scale=0.021,
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
        sp = getattr(p, 'stat_points', 0)

        ammo = c.ammo if c else 12
        max_ammo = c.max_ammo if c else 12
        res_ammo = c.reserve_ammo if c else 0

        stats_str = (
            f"• 레벨: LV.{lvl}  [경험치: {exp} / {exp_next}]\n"
            f"• 체력: {hp} / {max_hp} HP\n"
            f"• 공격력: {atk} DMG  (기본: {int(getattr(p, 'attack_power', 35))})\n"
            f"• 이동 속도: {spd_pct}%\n"
            f"• 스테미나: {stamina} / {max_stamina}\n"
            f"• 미분배 스탯: {sp} P\n"
            f"-----------------------------------------\n"
            f"[주무기] 9mm Tactical Combat Pistol\n"
            f"• 장전 탄약: {ammo} / {max_ammo}발 (예비: {res_ammo}발)\n"
            f"• 조준 기구: 3점 삼중수소 야간 조준기\n"
            f"  (우클릭 시 100% 핀포인트 명중률)\n"
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
                r_info = CURSED_RELICS.get(rid, {"name": rid, "icon": "🔮", "pro": "강화", "con": "저주"})
                lbl.setText(f"{r_info.get('icon', '🔮')} {r_info.get('name', rid)}\n(+{r_info.get('pro', '')})")
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
        txt = f"[1] 응급키트: {counts[1]}개  |  [2] 아드레날린: {counts[2]}개  |  [3] 탄약팩: {counts[3]}개  |  [4] 수류탄: {counts[4]}개  |  [Tab/I] 배낭"
        if hasattr(self, 'quickslot_text'):
            self.quickslot_text.setText(txt)
