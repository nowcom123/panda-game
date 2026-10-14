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
        self._build_geometry()

    def _build_geometry(self):
        # 1. 기본 전술 조준선 (정밀 센터 닷 + 4방향 십자선 + 전술 브래킷)
        ls = LineSegs("reticle_default")
        ls.setColor(0.92, 0.96, 1.0, 0.90)
        ls.setThickness(2.0)

        # 센터 닷
        ls.moveTo(0, 0, -0.0015)
        ls.drawTo(0, 0, 0.0015)

        # 4방향 틱 (중앙 여백 확보)
        gap = 0.008
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

        self.default_geom = self.root.attachNewNode(ls.create())

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
            self.root.setPos(x)
        else:
            self.root.setPos(x, y, z)

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
            scale=0.040,
            fg=(0.45, 0.85, 1.0, 0.95),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.timer_text = OnscreenText(
            text="[ 05:00 ]",
            pos=(0.45, 0.90),
            scale=0.046,
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
            scale=0.034,
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
            scale=0.034,
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
            scale=0.034,
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
            scale=0.034,
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
            scale=0.048,
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
            scale=0.048,
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
            scale=0.046,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.blackout_banner = OnscreenText(
            text="[ ! 비상 경보: 정전 프로토콜 발동 ! ]\n기지 전력 차단! 붉은 비상등 가동 (몬스터 폭주 / 처치 보상 2배)",
            pos=(0, 0.74),
            scale=0.052,
            fg=(1.0, 0.15, 0.15, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.blackout_banner.hide()
        self.blackout_pulse_timer = 0.0

        self.guide_text = OnscreenText(
            text="[WASD] 이동  |  [Shift] 달리기  |  [우클릭] 정밀조준(ADS)  |  [좌클릭] 사격  |  [R] 재장전  |  [Tab] 생체스캔",
            pos=(0, -0.93),
            scale=0.036,
            fg=(0.9, 0.9, 0.8, 0.85),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )

        self.stage_clear_banner = OnscreenText(
            text="",
            pos=(0, 0.42),
            scale=0.08,
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
            scale=0.14,
            fg=(0.95, 0.08, 0.08, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.game_over_desc = OnscreenText(
            text="기괴한 괴물에게 영혼을 잠식당했습니다...",
            pos=(0, 0.05),
            scale=0.055,
            fg=(0.88, 0.88, 0.88, 0.95),
            shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.victory_banner = OnscreenText(
            text="탈  출  성  공",
            pos=(0, 0.25),
            scale=0.14,
            fg=(0.20, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=False,
            **self.font_kw
        )
        self.victory_desc = OnscreenText(
            text="비상 탈출구를 찾아 악몽의 미궁을 탈출했습니다!",
            pos=(0, 0.05),
            scale=0.055,
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
            text_scale=0.52,
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
            text_scale=0.52,
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
            scale=0.10,
            fg=(0.95, 0.95, 0.95, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_subtitle = OnscreenText(
            text="[ 5분 던전 크롤러 RPG : 심연의 미궁 ]",
            parent=self.intro_frame,
            pos=(0, 0.35),
            scale=0.046,
            fg=(0.95, 0.45, 0.20, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_desc = OnscreenText(
            text="미궁에 도사린 몬스터들을 처치하여 경험치를 획득하고 레벨업하세요.\n5분 안에 비상탈출구를 찾아 5초간 사수하면 상점에서 특성을 강화하고 다음 층으로 내려갑니다.",
            parent=self.intro_frame,
            pos=(0, 0.20),
            scale=0.036,
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
            text_scale=0.50,
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
            text_scale=0.50,
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
            text_scale=0.50,
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
            scale=0.062,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.rank_content = OnscreenText(
            text="기록을 불러오는 중...",
            parent=self.rank_modal,
            pos=(-0.95, 0.48),
            scale=0.034,
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
            text_scale=0.55,
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

    def show_hit_marker(self, text, color=None, fg=None):
        """피격/적중/알림 표시"""
        c = fg if fg is not None else (color if color is not None else (1.0, 0.85, 0.2, 1.0))
        self.hit_marker_text.setText(text)
        self.hit_marker_text.setFg(c)
        self.hit_marker_timer = 2.2

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

    def update(self, dt):
        """HUD 실시간 애니메이션 (피격 플래시 페이드아웃, 크로스헤어 복구, 정전 경보 맥동)"""
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

        if hasattr(self, 'blackout_banner') and not self.blackout_banner.isHidden():
            self.blackout_pulse_timer += dt * 6.5
            alpha = 0.55 + 0.45 * math.sin(self.blackout_pulse_timer)
            self.blackout_banner.setFg((1.0, 0.15, 0.15, alpha))

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
            scale=0.058,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.shop_desc = OnscreenText(
            text="비상탈출구를 사수했습니다! 스탯 포인트를 분배하고 고대 미궁의 저주받은 유물을 선택하세요.",
            parent=self.shop_modal,
            pos=(0, 0.64),
            scale=0.034,
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
            scale=0.046,
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
            "text_scale": 0.55,
            "text_pos": (0, -0.14)
        }

        # --- 1단: 스탯 강화 4종 (2열 그리드 배치) ---
        # 1-1. 공격력 (좌측)
        self.stat_label_atk = OnscreenText(
            text="[공격력] 현재: 35 (+5)",
            parent=self.shop_modal,
            pos=(-1.12, 0.44),
            scale=0.038,
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
            scale=0.038,
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
            scale=0.038,
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
            scale=0.038,
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
            scale=0.044,
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
                scale=0.042,
                fg=(1.0, 0.88, 0.35, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_pro = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, 0.03),
                scale=0.033,
                fg=(0.35, 1.0, 0.55, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_con = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, -0.05),
                scale=0.033,
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
                text_scale=0.55,
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
            scale=0.039,
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
            text_scale=0.52,
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
            text_scale=0.52,
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

    def show_scanner_result(self, msg):
        """바이오 스캐너 펄스 탐지 결과 HUD 알림"""
        self.show_hit_marker(msg, color=(0.35, 0.95, 1.0, 1.0))
        self.hit_marker_timer = 3.5
