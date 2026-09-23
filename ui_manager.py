"""
UI Manager Module
Panda3D DirectGui & OnscreenText 관리, HUD 실시간 갱신 최적화(텍스트 캐싱) 및 랭킹 데이터 입출력
"""

import os
import sys
import json
import math
import random
import datetime
from direct.gui.OnscreenText import OnscreenText
from direct.gui.DirectGui import DirectButton, DirectFrame, DGG
from panda3d.core import TextNode
from constants import CURSED_RELICS


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

        # UI 요소 빌드
        self._setup_hud()
        self._setup_end_game_ui()
        self._setup_intro_ui()
        self._setup_rank_ui()
        self._setup_shop_ui()

    def _setup_hud(self):
        """인게임 조준점 및 HUD 요소 초기화"""
        self.crosshair = OnscreenText(
            text="+",
            pos=(0, -0.015),
            scale=0.065,
            fg=(1.0, 1.0, 1.0, 0.85),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True
        )

        # 화면 피격 붉은 플래시 오버레이
        self.damage_flash = DirectFrame(
            frameColor=(0.85, 0.05, 0.05, 0.0),
            frameSize=(-2.0, 2.0, -2.0, 2.0),
            pos=(0, 0, 0)
        )
        self.damage_flash.setBin("fixed", 5)
        self.damage_flash_alpha = 0.0
        self.crosshair_hit_timer = 0.0

        self.timer_text = OnscreenText(
            text="[ 탈출 제한시간: 01:00 ]",
            pos=(0, 0.91),
            scale=0.052,
            fg=(0.25, 0.95, 0.45, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        self.ammo_text = OnscreenText(
            text="[ 탄약: 12 / 12 ]",
            pos=(1.28, -0.85),
            scale=0.048,
            fg=(1.0, 0.90, 0.35, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ARight,
            mayChange=True,
            **self.font_kw
        )

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

        self.hud_text = OnscreenText(
            text="위치: X=0.0, Y=0.0",
            pos=(-1.3, 0.92),
            scale=0.045,
            fg=(1, 1, 1, 0.9),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.stamina_text = OnscreenText(
            text="스테미나: [|||||||||||||||] 100%",
            pos=(-1.3, 0.86),
            scale=0.04,
            fg=(0.35, 0.95, 0.5, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        # 5.5. 플레이어 체력(HP) & 경험치(EXP) HUD
        self.hp_text = OnscreenText(
            text="체  력: [|||||||||||||||] 100/100",
            pos=(-1.3, 0.80),
            scale=0.04,
            fg=(0.20, 0.95, 0.40, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.exp_text = OnscreenText(
            text="[LV. 1] EXP: [...............] 0/100",
            pos=(-1.3, 0.74),
            scale=0.038,
            fg=(0.35, 0.85, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )

        self.relic_badge_text = OnscreenText(
            text="[보유 유물] 없음",
            pos=(-1.3, 0.68),
            scale=0.034,
            fg=(0.85, 0.70, 1.0, 0.95),
            align=TextNode.ALeft,
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
            text="[WASD] 8방향 이동  |  [Shift] 달리기  |  [좌클릭] 사격  |  [R] 재장전",
            pos=(0, -0.93),
            scale=0.038,
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

        self.door_status_text = OnscreenText(
            text="",
            pos=(0, 0.65),
            scale=0.048,
            fg=(1.0, 0.85, 0.2, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )
        self.door_status_text.hide()

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
            text="메인 메뉴 (MENU)",
            pos=(-0.28, 0, -0.22),
            scale=0.055,
            relief=DGG.RAISED,
            frameColor=(0.15, 0.16, 0.22, 0.95),
            text_fg=(1.0, 1.0, 1.0, 1.0),
            borderWidth=(0.005, 0.005),
            pad=(0.35, 0.15),
            command=self.on_return_menu,
            **self.btn_font_kw
        )
        self.btn_game_rank = DirectButton(
            text="기록 랭킹 (RANK)",
            pos=(0.28, 0, -0.22),
            scale=0.055,
            relief=DGG.RAISED,
            frameColor=(0.18, 0.15, 0.12, 0.95),
            text_fg=(1.0, 0.9, 0.3, 1.0),
            borderWidth=(0.005, 0.005),
            pad=(0.35, 0.15),
            command=self.show_rank_modal,
            **self.btn_font_kw
        )

        self.game_over_banner.hide()
        self.game_over_desc.hide()
        self.victory_banner.hide()
        self.victory_desc.hide()
        self.btn_game_menu.hide()
        self.btn_game_rank.hide()

    def _setup_intro_ui(self):
        """메인 인트로 타이틀 및 메뉴 버튼"""
        self.intro_frame = DirectFrame(
            frameColor=(0, 0, 0, 0),
            frameSize=(-1.5, 1.5, -1.0, 1.0),
            pos=(0, 0, 0)
        )

        self.intro_title = OnscreenText(
            text="LIMINAL BACKROOMS",
            parent=self.intro_frame,
            pos=(0, 0.52),
            scale=0.11,
            fg=(0.95, 0.95, 0.95, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_subtitle = OnscreenText(
            text="[ 5분 던전 크롤러 RPG : 심연의 미궁 ]",
            parent=self.intro_frame,
            pos=(0, 0.38),
            scale=0.048,
            fg=(0.95, 0.45, 0.20, 1.0),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.intro_desc = OnscreenText(
            text="미궁에 도사린 몬스터들을 처치하여 경험치를 획득하고 레벨업하세요.\n5분 안에 비상탈출구를 찾아 5초간 사수하면 상점에서 특성을 강화하고 다음 층으로 내려갑니다.",
            parent=self.intro_frame,
            pos=(0, 0.22),
            scale=0.038,
            fg=(0.85, 0.88, 0.92, 0.92),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter,
            **self.font_kw
        )

        btn_style = {
            "relief": DGG.RAISED,
            "borderWidth": (0.005, 0.005),
            "pad": (0.45, 0.16),
            "scale": 0.065
        }

        self.btn_start = DirectButton(
            parent=self.intro_frame,
            text="START",
            pos=(0, 0, 0.02),
            frameColor=(0.14, 0.24, 0.16, 0.95),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            command=self.on_start,
            **btn_style,
            **self.btn_font_kw
        )

        self.btn_rank = DirectButton(
            parent=self.intro_frame,
            text="RANK",
            pos=(0, 0, -0.15),
            frameColor=(0.20, 0.18, 0.12, 0.95),
            text_fg=(1.0, 0.85, 0.25, 1.0),
            command=self.show_rank_modal,
            **btn_style,
            **self.btn_font_kw
        )

        self.btn_exit = DirectButton(
            parent=self.intro_frame,
            text="EXIT",
            pos=(0, 0, -0.32),
            frameColor=(0.22, 0.12, 0.12, 0.95),
            text_fg=(1.0, 0.4, 0.4, 1.0),
            command=self.on_exit,
            **btn_style,
            **self.btn_font_kw
        )

    def _setup_rank_ui(self):
        """기록 랭킹 팝업 모달창"""
        self.rank_modal = DirectFrame(
            frameColor=(0.06, 0.07, 0.09, 0.96),
            frameSize=(-1.10, 1.10, -0.80, 0.80),
            pos=(0, 0, 0)
        )

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
            text="닫기 (CLOSE)",
            pos=(0, 0, -0.68),
            scale=0.052,
            relief=DGG.RAISED,
            frameColor=(0.18, 0.18, 0.22, 0.95),
            text_fg=(0.95, 0.95, 0.95, 1.0),
            borderWidth=(0.005, 0.005),
            pad=(0.35, 0.14),
            command=self.hide_rank_modal,
            **self.btn_font_kw
        )
        self.rank_modal.hide()

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

        self.crosshair.show()
        self.timer_text.show()
        self.ammo_text.show()
        self.hud_text.show()
        self.stamina_text.show()
        self.hp_text.show()
        self.exp_text.show()
        self.guide_text.show()

    def hide_all_ingame(self):
        """인게임 HUD 전체 숨김"""
        self.crosshair.hide()
        self.timer_text.hide()
        self.ammo_text.hide()
        self.hud_text.hide()
        self.stamina_text.hide()
        self.hp_text.hide()
        self.exp_text.hide()
        self.guide_text.hide()
        self.door_status_text.hide()
        self.hit_marker_text.setText("")
        self.stage_clear_banner.hide()

    def show_hit_marker(self, text, color=(1.0, 0.85, 0.2, 1.0)):
        """피격/적중/알림 표시"""
        self.hit_marker_text.setText(text)
        self.hit_marker_text.setFg(color)

    def trigger_player_damage_flash(self, intensity=0.60):
        """플레이어 피격 시 화면 붉은 플래시 효과"""
        self.damage_flash_alpha = intensity
        self.damage_flash['frameColor'] = (0.85, 0.05, 0.05, self.damage_flash_alpha)

    def trigger_crosshair_hit(self, is_kill=False):
        """몬스터 타격 시 크로스헤어 적중 마커 표시"""
        self.crosshair_hit_timer = 0.18
        if is_kill:
            self.crosshair.setText("X")
            self.crosshair.setScale(0.088)
            self.crosshair.setFg((1.0, 0.20, 0.20, 1.0))
        else:
            self.crosshair.setText("x")
            self.crosshair.setScale(0.078)
            self.crosshair.setFg((1.0, 0.40, 0.40, 1.0))

    def update(self, dt):
        """HUD 실시간 애니메이션 (피격 플래시 페이드아웃, 크로스헤어 복구, 정전 경보 맥동)"""
        if self.damage_flash_alpha > 0.0:
            self.damage_flash_alpha = max(0.0, self.damage_flash_alpha - dt * 2.5)
            self.damage_flash['frameColor'] = (0.85, 0.05, 0.05, self.damage_flash_alpha)

        if self.crosshair_hit_timer > 0.0:
            self.crosshair_hit_timer -= dt
            if self.crosshair_hit_timer <= 0.0:
                self.crosshair.setText("+")
                self.crosshair.setScale(0.065)
                self.crosshair.setFg((1.0, 1.0, 1.0, 0.85))

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

    # --- 텍스트 캐싱 기반 HUD 고속 업데이트 (프레임 페이싱 최적화) ---
    def update_timer(self, time_left, stage=1):
        mins = int(time_left) // 60
        secs = int(time_left) % 60
        t_str = f"{mins:02d}:{secs:02d}"
        stg_str = f"[ STAGE {stage} ]  "

        if time_left <= 10.0:
            flash = (int(time_left * 4) % 2 == 0)
            col = (1.0, 0.2, 0.2, 1.0) if flash else (1.0, 0.8, 0.8, 1.0)
            msg = f"{stg_str}[ ! 탈출 제한시간: {t_str} (서두르세요!) ]"
        elif time_left <= 25.0:
            col = (1.0, 0.85, 0.2, 1.0)
            msg = f"{stg_str}[ 탈출 제한시간: {t_str} ]"
        else:
            col = (0.25, 0.95, 0.45, 1.0)
            msg = f"{stg_str}[ 탈출 제한시간: {t_str} ]"

        if msg != self._cached_timer_str:
            self.timer_text.setText(msg)
            self._cached_timer_str = msg
        if col != self._cached_timer_col:
            self.timer_text.setFg(col)
            self._cached_timer_col = col

    def update_ammo(self, ammo, max_ammo, reserve_ammo=0):
        if reserve_ammo > 0:
            msg = f"[ 탄약: {ammo} / {max_ammo} (예비: {reserve_ammo}) ]"
        else:
            msg = f"[ 탄약: {ammo} / {max_ammo} ]"
        if msg != self._cached_ammo_str:
            self.ammo_text.setText(msg)
            self._cached_ammo_str = msg

    def update_stamina(self, stamina, max_stamina, is_sprinting=False, is_exhausted=False):
        bars = int((stamina / max_stamina) * 15)
        bar_str = "|" * bars + "." * (15 - bars)
        stamina_pct = int(stamina)

        if is_exhausted:
            msg = f"스테미나: [{bar_str}] {stamina_pct}% (탈진! 회복 대기...)"
            col = (1.0, 0.25, 0.25, 1.0)
        elif is_sprinting:
            msg = f"스테미나: [{bar_str}] {stamina_pct}% (전력질주 중!)"
            col = (1.0, 0.85, 0.2, 1.0)
        else:
            msg = f"스테미나: [{bar_str}] {stamina_pct}%"
            col = (0.35, 0.95, 0.5, 0.95)

        if msg != self._cached_stamina_str:
            self.stamina_text.setText(msg)
            self._cached_stamina_str = msg
        if col != self._cached_stamina_col:
            self.stamina_text.setFg(col)
            self._cached_stamina_col = col

    def update_hud(self, px, py, rendered_count, total_count):
        msg = f"위치: X={px:.1f}, Y={py:.1f} | 활성: {rendered_count}/{total_count} 청크"
        if msg != self._cached_hud_str:
            self.hud_text.setText(msg)
            self._cached_hud_str = msg

    def update_door_status(self, msg, fg=None, show=True):
        if show:
            if not self.door_status_text.isHidden() and msg == self._cached_door_str:
                return
            self.door_status_text.setText(msg)
            self._cached_door_str = msg
            if fg is not None:
                self.door_status_text.setFg(fg)
            self.door_status_text.show()
        else:
            if not self.door_status_text.isHidden():
                self.door_status_text.hide()
                self._cached_door_str = ""

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

    # --- 플레이어 체력 및 경험치 HUD 업데이트 ---
    def update_hp_exp(self, hp, max_hp, exp, exp_to_next, level=1, stat_points=0):
        pct_hp = max(0.0, min(1.0, hp / max(1.0, max_hp)))
        bars_hp = int(pct_hp * 15)
        bar_hp_str = "|" * bars_hp + "." * (15 - bars_hp)
        msg_hp = f"체  력: [{bar_hp_str}] {int(hp)}/{int(max_hp)}"

        if msg_hp != self._cached_hp_str:
            self.hp_text.setText(msg_hp)
            if pct_hp <= 0.25:
                self.hp_text.setFg((1.0, 0.2, 0.2, 1.0))
            elif pct_hp <= 0.55:
                self.hp_text.setFg((1.0, 0.85, 0.2, 1.0))
            else:
                self.hp_text.setFg((0.20, 0.95, 0.40, 1.0))
            self._cached_hp_str = msg_hp

        pct_exp = max(0.0, min(1.0, exp / max(1.0, exp_to_next)))
        bars_exp = int(pct_exp * 15)
        bar_exp_str = "|" * bars_exp + "." * (15 - bars_exp)
        sp_tag = f" [스탯P +{stat_points}]" if stat_points > 0 else ""
        msg_exp = f"[LV. {level}{sp_tag}] EXP: [{bar_exp_str}] {int(exp)}/{int(exp_to_next)}"

        if msg_exp != self._cached_exp_str:
            self.exp_text.setText(msg_exp)
            self._cached_exp_str = msg_exp

    # --- [스테이지 클리어: 스탯 분배 상점 모달] ---
    def _setup_shop_ui(self):
        self.shop_player = None
        self.shop_combat = None
        self.on_shop_confirm = None

        self.shop_modal = DirectFrame(
            frameColor=(0.06, 0.07, 0.09, 0.98),
            frameSize=(-1.28, 1.28, -0.88, 0.88),
            pos=(0, 0, 0)
        )

        self.shop_title = OnscreenText(
            text="[ STAGE CLEAR! 스탯 분배 및 보급소 ]",
            parent=self.shop_modal,
            pos=(0, 0.75),
            scale=0.058,
            fg=(1.0, 0.85, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            **self.font_kw
        )

        self.shop_desc = OnscreenText(
            text="비상탈출구를 사수했습니다! 스탯 포인트를 분배하고 고대 미궁의 저주받은 유물을 선택하세요.",
            parent=self.shop_modal,
            pos=(0, 0.67),
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
            pos=(0, 0.58),
            scale=0.046,
            fg=(1.0, 0.88, 0.25, 1.0),
            shadow=(0, 0, 0, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
            **self.font_kw
        )

        btn_alloc_style = {
            "relief": DGG.RAISED,
            "borderWidth": (0.005, 0.005),
            "scale": 0.042,
            "pad": (0.32, 0.14)
        }

        # --- 1단: 스탯 강화 4종 (2열 그리드 배치) ---
        # 1-1. 공격력 (좌측)
        self.stat_label_atk = OnscreenText(
            text="[공격력] 현재: 35 (+5)",
            parent=self.shop_modal,
            pos=(-1.12, 0.47),
            scale=0.038,
            fg=(1.0, 0.80, 0.40, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_atk = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(-0.22, 0, 0.48),
            frameColor=(0.28, 0.16, 0.16, 0.95),
            text_fg=(1.0, 0.85, 0.4, 1.0),
            command=self._allocate,
            extraArgs=["ATK"],
            **btn_alloc_style,
            **self.btn_font_kw
        )

        # 1-2. 이동 속도 (좌측 하단)
        self.stat_label_spd = OnscreenText(
            text="[이동 속도] 현재: 100% (+8%)",
            parent=self.shop_modal,
            pos=(-1.12, 0.36),
            scale=0.038,
            fg=(0.45, 0.85, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_spd = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(-0.22, 0, 0.37),
            frameColor=(0.14, 0.20, 0.30, 0.95),
            text_fg=(0.45, 0.85, 1.0, 1.0),
            command=self._allocate,
            extraArgs=["SPD"],
            **btn_alloc_style,
            **self.btn_font_kw
        )

        # 1-3. 최대 체력 (우측)
        self.stat_label_hp = OnscreenText(
            text="[최대 체력] 현재: 100 (+25)",
            parent=self.shop_modal,
            pos=(0.04, 0.47),
            scale=0.038,
            fg=(0.40, 1.0, 0.60, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_hp = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(0.94, 0, 0.48),
            frameColor=(0.14, 0.26, 0.16, 0.95),
            text_fg=(0.4, 1.0, 0.6, 1.0),
            command=self._allocate,
            extraArgs=["HP"],
            **btn_alloc_style,
            **self.btn_font_kw
        )

        # 1-4. 최대 탄약 (우측 하단)
        self.stat_label_ammo = OnscreenText(
            text="[최대 탄약] 현재: 12발 (+2발)",
            parent=self.shop_modal,
            pos=(0.04, 0.36),
            scale=0.038,
            fg=(1.0, 0.92, 0.40, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
            **self.font_kw
        )
        self.btn_alloc_ammo = DirectButton(
            parent=self.shop_modal,
            text="[ +1 강화 ]",
            pos=(0.94, 0, 0.37),
            frameColor=(0.26, 0.24, 0.14, 0.95),
            text_fg=(1.0, 0.92, 0.4, 1.0),
            command=self._allocate,
            extraArgs=["AMMO"],
            **btn_alloc_style,
            **self.btn_font_kw
        )

        # --- 2단: 저주받은 유물 선택 (3개 카드) ---
        self.relic_section_title = OnscreenText(
            text="[ 고대 미궁의 저주받은 유물 (1개 선택 또는 다음 스테이지로 스킵) ]",
            parent=self.shop_modal,
            pos=(0, 0.23),
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
                frameColor=(0.10, 0.11, 0.16, 0.97),
                frameSize=(-0.36, 0.36, -0.21, 0.21),
                pos=(card_xs[i], 0, -0.04),
                relief=DGG.RIDGE,
                borderWidth=(0.005, 0.005)
            )
            r_title = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, 0.13),
                scale=0.042,
                fg=(1.0, 0.88, 0.35, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_pro = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, 0.04),
                scale=0.033,
                fg=(0.35, 1.0, 0.55, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_con = OnscreenText(
                text="",
                parent=card_f,
                pos=(0, -0.04),
                scale=0.033,
                fg=(1.0, 0.38, 0.38, 1.0),
                align=TextNode.ACenter,
                mayChange=True,
                **self.font_kw
            )
            r_btn = DirectButton(
                parent=card_f,
                text="[ 선택 획득 ]",
                pos=(0, 0, -0.14),
                scale=0.042,
                relief=DGG.RAISED,
                frameColor=(0.20, 0.15, 0.30, 0.95),
                text_fg=(0.95, 0.80, 1.0, 1.0),
                borderWidth=(0.005, 0.005),
                pad=(0.35, 0.12),
                command=self._select_relic,
                extraArgs=[i],
                **self.btn_font_kw
            )
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
            text="다음 스테이지 시작 (START NEXT STAGE)",
            pos=(0, 0, -0.48),
            scale=0.058,
            relief=DGG.RAISED,
            frameColor=(0.18, 0.32, 0.20, 0.98),
            text_fg=(0.35, 1.0, 0.55, 1.0),
            borderWidth=(0.006, 0.006),
            pad=(0.50, 0.18),
            command=self._confirm_shop_and_start,
            **self.btn_font_kw
        )

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

        # 모든 유물 카드 비활성화
        for c in self.relic_cards:
            c["btn"]["state"] = DGG.DISABLED
            c["btn"]["frameColor"] = (0.15, 0.15, 0.15, 0.8)
            c["btn"]["text_fg"] = (0.5, 0.5, 0.5, 0.8)
        self.relic_cards[card_idx]["btn"]["text"] = "[ 장착 완료 ]"
        self._refresh_shop_labels()

    def _confirm_shop_and_start(self):
        self.hide_stage_clear_shop()
        if self.on_shop_confirm:
            self.on_shop_confirm()

    def show_stage_clear_shop(self, stage, player, combat, on_confirm_callback):
        self.shop_player = player
        self.shop_combat = combat
        self.on_shop_confirm = on_confirm_callback
        self.shop_title.setText(f"[ STAGE {stage} CLEAR! 스탯 분배 및 보급소 ]")
        self.shop_msg_text.setText("")
        self._refresh_shop_labels()

        # 미보유 유물 풀에서 무작위 3개 선별
        acquired = set(getattr(player, 'relics', []))
        available = [r for r in CURSED_RELICS.values() if r["id"] not in acquired]
        pick_count = min(3, len(available))
        self.offered_relics = random.sample(available, pick_count) if pick_count > 0 else []

        for i, card in enumerate(self.relic_cards):
            if i < len(self.offered_relics):
                relic = self.offered_relics[i]
                card["frame"].show()
                card["title"].setText(f"{relic['icon']} {relic['name']}")
                card["pro"].setText(f"+ {relic['pro']}")
                card["con"].setText(f"- {relic['con']}")
                card["btn"]["state"] = DGG.NORMAL
                card["btn"]["text"] = "[ 선택 획득 ]"
                card["btn"]["frameColor"] = (0.20, 0.15, 0.30, 0.95)
                card["btn"]["text_fg"] = (0.95, 0.80, 1.0, 1.0)
            else:
                card["frame"].hide()

        self.hide_all_ingame()
        self.shop_modal.show()

    def hide_stage_clear_shop(self):
        self.shop_modal.hide()
