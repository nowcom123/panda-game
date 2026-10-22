import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from monster import CableOverlordBoss
from world_gen import cell_has_pillar


@dataclass
class GateWaveConfig:
    activation_radius: float = 45.0
    max_waves_per_stage: int = 3
    warning_duration: float = 2.0
    spawn_interval: float = 0.75
    rest_duration: float = 8.0
    max_nearby_enemies_for_warning: int = 6
    global_alive_enemies_cap: int = 16
    spawning_phase_timeout: float = 6.0


class GateWaveManager:
    """단일 관문 증원 웨이브 관리자 (Gate Wave Manager)
    
    기존의 분산된 5개 관문 증원 경로를 단일 유한 웨이브 생명주기로 통합:
    - 상태 전이: WAITING -> WARNING -> SPAWNING -> REST -> WAITING (3회 소진 시 EXHAUSTED)
    - 관문 45m 이내 및 주변 생존 적 6마리 이하 시 경고(2초) 개시
    - 경고 진입 시 경보음 1회 재생 및 예고 라벨 표시
    - 웨이브당 목표: 2 + min(max(stage - 1, 0), 2)마리 (1스테이지 2, 2스테이지 3, 3스테이지+ 4)
    - 출현 간격 0.75초 이상, 프레임당 최대 1마리 생성 시도
    - 출현 단계 최대 6초 초과 또는 목표 달성 시 즉시 REST(8초) 진입, 실패 수량 이월 없음
    - 45m 반경 이탈 시 모든 타이머 정지, 재진입 시 WARNING/SPAWNING 2초 경고 재제공 (웨이브 횟수/예산 추가 없음)
    - 살아 있는 보스 활성화 시 일반 증원 중지 및 진행 중 웨이브 취소/소비, 보스 사망 후 잔여 웨이브는 8초 재정비 후 재개
    """

    def __init__(self, game: Any, config: Optional[GateWaveConfig] = None):
        self.game = game
        self.config = config or GateWaveConfig()

        self.state: str = "WAITING"
        self.waves_completed: int = 0
        self.state_timer: float = 0.0
        self.spawn_cooldown: float = 0.0
        self.wave_target: int = 0
        self.wave_spawned: int = 0
        self.spawning_time_left: float = 0.0
        self.spawned_positions_this_wave: List[Tuple[float, float, float]] = []
        self.reentry_warning_timer: float = 0.0

        self.was_in_radius: bool = False
        self.boss_was_alive: bool = False

        self._cached_candidates: Optional[List[Tuple[float, float]]] = None
        self._cached_escape_pos: Optional[Tuple[float, float]] = None

    def reset(self):
        """스테이지 전환, 게임 재시작 시 상태 및 캐시 완전 초기화"""
        self.state = "WAITING"
        self.waves_completed = 0
        self.state_timer = 0.0
        self.spawn_cooldown = 0.0
        self.wave_target = 0
        self.wave_spawned = 0
        self.spawning_time_left = 0.0
        self.spawned_positions_this_wave.clear()
        self.reentry_warning_timer = 0.0
        self.was_in_radius = False
        self.boss_was_alive = False
        self.invalidate_candidates()
        self._update_hud("", show=False)

    def on_gate_changed(self):
        """관문 위치 변경 시 후보 캐시 무효화"""
        self.invalidate_candidates()

    def invalidate_candidates(self):
        self._cached_candidates = None
        self._cached_escape_pos = None

    def get_cached_candidates(self) -> List[Tuple[float, float]]:
        """관문 10~30m 후보 좌표 반환 (캐시 유지)"""
        escape_pos = getattr(self.game, 'escape_pos', None)
        if not escape_pos:
            return []
        ex = getattr(escape_pos, 'x', escape_pos[0])
        ey = getattr(escape_pos, 'y', escape_pos[1])
        cur_pos = (round(ex, 2), round(ey, 2))

        if self._cached_candidates is None or self._cached_escape_pos != cur_pos:
            from spawner import get_gate_corridor_candidates
            self._cached_escape_pos = cur_pos
            self._cached_candidates = get_gate_corridor_candidates(escape_pos, min_dist=10.0, max_dist=30.0)
        return self._cached_candidates

    def _play_alarm(self):
        if hasattr(self.game, 'audio_mgr') and self.game.audio_mgr:
            if hasattr(self.game.audio_mgr, 'play_door_alarm'):
                try:
                    self.game.audio_mgr.play_door_alarm()
                except Exception:
                    pass

    def get_status_hud_text(self) -> Tuple[str, Optional[Tuple[float, float, float, float]]]:
        """현재 상태에 해당하는 HUD 텍스트와 색상 반환"""
        if self.state == "WARNING":
            wave_num = min(self.config.max_waves_per_stage, self.waves_completed + 1)
            t = max(0.0, self.state_timer)
            return f"증원 경고 {wave_num}/{self.config.max_waves_per_stage} · {t:.1f}초", (1.0, 0.65, 0.2, 1.0)
        elif self.state == "SPAWNING":
            if self.reentry_warning_timer > 0.0:
                return f"증원 경고 {self.waves_completed}/{self.config.max_waves_per_stage} · {max(0.0, self.reentry_warning_timer):.1f}초", (1.0, 0.65, 0.2, 1.0)
            return f"증원 접근 {self.waves_completed}/{self.config.max_waves_per_stage}", (1.0, 0.3, 0.3, 1.0)
        elif self.state == "REST":
            return f"재정비 · {max(0.0, self.state_timer):.1f}초", (0.4, 0.95, 0.5, 1.0)
        elif self.state == "EXHAUSTED":
            return "추가 증원 종료", (0.70, 0.78, 0.88, 0.85)
        return "", None

    def refresh_hud(self):
        """플레이 복귀 또는 HUD 갱신 필요 시 현재 웨이브 상태 안내 복원"""
        if getattr(self.game, 'game_state', None) != "PLAYING" or getattr(self.game, 'is_test_mode', False):
            self.hide_hud()
            return
        if not self.was_in_radius:
            self.hide_hud()
            return
        msg, fg = self.get_status_hud_text()
        self._update_hud(msg=msg, fg=fg, show=bool(msg))

    def hide_hud(self):
        """메뉴/테스트 모드/종료 시 HUD 숨김"""
        self._update_hud("", show=False)

    def _update_hud(self, msg: str = "", fg: Optional[Tuple[float, float, float, float]] = None, show: bool = True):
        if hasattr(self.game, 'ui_mgr') and self.game.ui_mgr:
            if hasattr(self.game.ui_mgr, 'update_gate_wave_status'):
                try:
                    self.game.ui_mgr.update_gate_wave_status(msg=msg, fg=fg, show=show)
                except Exception:
                    pass

    def _is_boss_alive(self) -> bool:
        boss = getattr(self.game, 'boss', None)
        if boss and getattr(boss, 'hp', 0) > 0 and not getattr(boss, 'is_corpse', False):
            return True
        for m in getattr(self.game, 'monsters', []):
            if isinstance(m, CableOverlordBoss) and getattr(m, 'hp', 0) > 0 and not getattr(m, 'is_corpse', False):
                return True
        return False

    def count_nearby_alive_enemies(self, ex: float, ey: float, radius: float = 45.0) -> int:
        count = 0
        for m in getattr(self.game, 'monsters', []):
            if getattr(m, 'hp', 1) <= 0 or getattr(m, 'is_corpse', False):
                continue
            mx = getattr(m.pos, 'x', m.pos[0] if hasattr(m.pos, '__getitem__') else 0.0)
            my = getattr(m.pos, 'y', m.pos[1] if hasattr(m.pos, '__getitem__') else 0.0)
            if math.hypot(mx - ex, my - ey) <= radius:
                count += 1
        return count

    def count_global_alive_enemies(self) -> int:
        count = 0
        for m in getattr(self.game, 'monsters', []):
            if getattr(m, 'hp', 1) > 0 and not getattr(m, 'is_corpse', False):
                count += 1
        return count

    def update(self, raw_dt: float, px: float, py: float):
        """메인 틱 루프에서 1회 호출되는 raw_dt 기반 웨이브 업데이트"""
        # 1. 메뉴 / 정지 / 테스트 모드 검사
        game_state = getattr(self.game, 'game_state', 'PLAYING')
        if game_state in ("SHOP", "INVENTORY", "PAUSED", "AAR", "INTRO", "GAME_OVER", "VICTORY") or getattr(self.game, 'is_test_mode', False):
            self.hide_hud()
            return

        escape_pos = getattr(self.game, 'escape_pos', None)
        if not escape_pos:
            self._update_hud("", show=False)
            return

        ex = getattr(escape_pos, 'x', escape_pos[0])
        ey = getattr(escape_pos, 'y', escape_pos[1])
        dist_gate = math.hypot(px - ex, py - ey)
        in_radius = (dist_gate <= self.config.activation_radius)

        # 2. 보스 생존 처리
        boss_alive = self._is_boss_alive()
        if boss_alive:
            if self.state in ("WARNING", "SPAWNING"):
                # 진행 중인 웨이브 취소 및 1회 소비
                if self.state == "WARNING":
                    self.waves_completed += 1
                self.state = "REST"
                self.state_timer = self.config.rest_duration
                self.reentry_warning_timer = 0.0
            self.boss_was_alive = True
            # 보스 생존 중에는 일반 증원 및 REST 시간 소진 중지
            self._update_hud("", show=False)
            return
        elif self.boss_was_alive:
            # 보스 격파 후 복귀: 잔여 웨이브가 있다면 최소 8초 재정비
            self.boss_was_alive = False
            if self.waves_completed < self.config.max_waves_per_stage:
                self.state = "REST"
                self.state_timer = max(self.state_timer, self.config.rest_duration)
            else:
                self.state = "EXHAUSTED"

        # 3. 45m 반경 이탈 / 재진입 처리
        if not in_radius:
            if self.was_in_radius:
                self.was_in_radius = False
                self._update_hud("", show=False)
            return

        if not self.was_in_radius:
            # 반경 밖에서 안으로 재진입
            self.was_in_radius = True
            if self.state == "WARNING":
                # 온전한 2초 경고 다시 제공
                self.state_timer = self.config.warning_duration
                self._play_alarm()
            elif self.state == "SPAWNING":
                # 남은 수량 앞에 2초 경고 다시 제공 (웨이브 횟수/6초 출현 예산은 추가 지급하지 않음)
                self.reentry_warning_timer = self.config.warning_duration
                self._play_alarm()
            # REST 잔여시간은 보존된 채로 유지

        # 4. 상태 머신 실행
        if self.waves_completed >= self.config.max_waves_per_stage and self.state not in ("WARNING", "SPAWNING"):
            self.state = "EXHAUSTED"
            self._update_hud("추가 증원 종료", fg=(0.70, 0.78, 0.88, 0.85), show=True)
            return

        if self.state == "WAITING":
            # 관문 45m 내 생존 적 6마리 이하일 때 경고 시작
            nearby_count = self.count_nearby_alive_enemies(ex, ey, self.config.activation_radius)
            if nearby_count <= self.config.max_nearby_enemies_for_warning:
                self.state = "WARNING"
                self.state_timer = self.config.warning_duration
                self._play_alarm()
                wave_display_num = self.waves_completed + 1
                self._update_hud(
                    f"증원 경고 {wave_display_num}/{self.config.max_waves_per_stage} · {self.state_timer:.1f}초",
                    fg=(1.0, 0.65, 0.2, 1.0),
                    show=True
                )
            else:
                self._update_hud("", show=False)

        elif self.state == "WARNING":
            self.state_timer -= raw_dt
            if self.state_timer <= 0.0:
                # 경고 완료 -> 출현 단계 시작
                self.state = "SPAWNING"
                self.waves_completed += 1
                stage = getattr(self.game, 'current_stage', 1)
                self.wave_target = 2 + min(max(stage - 1, 0), 2)
                self.wave_spawned = 0
                self.spawning_time_left = self.config.spawning_phase_timeout
                self.spawn_cooldown = 0.0
                self.spawned_positions_this_wave.clear()
                self.reentry_warning_timer = 0.0
                self._update_hud(
                    f"증원 접근 {self.waves_completed}/{self.config.max_waves_per_stage}",
                    fg=(1.0, 0.3, 0.3, 1.0),
                    show=True
                )
            else:
                wave_display_num = self.waves_completed + 1
                self._update_hud(
                    f"증원 경고 {wave_display_num}/{self.config.max_waves_per_stage} · {max(0.0, self.state_timer):.1f}초",
                    fg=(1.0, 0.65, 0.2, 1.0),
                    show=True
                )

        if self.state == "SPAWNING":
            # 이탈 후 재진입 경고 중일 때
            if self.reentry_warning_timer > 0.0:
                self.reentry_warning_timer -= raw_dt
                self._update_hud(
                    f"증원 경고 {self.waves_completed}/{self.config.max_waves_per_stage} · {max(0.0, self.reentry_warning_timer):.1f}초",
                    fg=(1.0, 0.65, 0.2, 1.0),
                    show=True
                )
                return

            # 타임아웃 또는 출현 목표 달성 우선 검사 (시간이 소진된 틱에서는 새 생성 시도 차단)
            self.spawning_time_left -= raw_dt
            if self.spawning_time_left <= 0.0 or self.wave_spawned >= self.wave_target:
                self.state = "REST"
                self.state_timer = self.config.rest_duration
                self.spawned_positions_this_wave.clear()
                self._update_hud(
                    f"재정비 · {self.state_timer:.1f}초",
                    fg=(0.4, 0.95, 0.5, 1.0),
                    show=True
                )
                return

            self.spawn_cooldown = max(0.0, self.spawn_cooldown - raw_dt)

            # 출현 시도 (0.75초 간격 준수, 한 프레임에 최대 1마리만 시도)
            if self.spawn_cooldown <= 0.0 and self.wave_spawned < self.wave_target:
                global_alive = self.count_global_alive_enemies()
                if global_alive < self.config.global_alive_enemies_cap:
                    from spawner import spawn_reinforcement_monster
                    monster = spawn_reinforcement_monster(
                        self.game,
                        near_gate=True,
                        wave_spawned_positions=self.spawned_positions_this_wave,
                        candidate_cache=self.get_cached_candidates()
                    )
                    # 성공 여부와 관계없이 출현 시도 후 0.75초 재시도 간격 적용
                    self.spawn_cooldown = self.config.spawn_interval
                    if monster is not None:
                        self.wave_spawned += 1
                        col_r = getattr(monster, 'col_radius', 0.40)
                        self.spawned_positions_this_wave.append((monster.pos.x, monster.pos.y, col_r))
                        if self.wave_spawned >= self.wave_target:
                            self.state = "REST"
                            self.state_timer = self.config.rest_duration
                            self.spawned_positions_this_wave.clear()
                            self._update_hud(
                                f"재정비 · {self.state_timer:.1f}초",
                                fg=(0.4, 0.95, 0.5, 1.0),
                                show=True
                            )
                            return

            self._update_hud(
                f"증원 접근 {self.waves_completed}/{self.config.max_waves_per_stage}",
                fg=(1.0, 0.3, 0.3, 1.0),
                show=True
            )

        elif self.state == "REST":
            self.state_timer -= raw_dt
            if self.state_timer <= 0.0:
                if self.waves_completed >= self.config.max_waves_per_stage:
                    self.state = "EXHAUSTED"
                    self._update_hud("추가 증원 종료", fg=(0.70, 0.78, 0.88, 0.85), show=True)
                else:
                    self.state = "WAITING"
                    self._update_hud("", show=False)
            else:
                self._update_hud(
                    f"재정비 · {max(0.0, self.state_timer):.1f}초",
                    fg=(0.4, 0.95, 0.5, 1.0),
                    show=True
                )
