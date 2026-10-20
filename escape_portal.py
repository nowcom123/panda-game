import math
import random
from panda3d.core import PointLight, LColor
from direct.showbase.ShowBaseGlobal import globalClock

from constants import (
    CELL_SIZE, CHUNK_CELLS, MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import cell_has_pillar
from geometry import make_cube_to, make_sphere_to
from collision import register_custom_collider, clear_custom_colliders


class EscapePortalManager:
    """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성 및 방어전(사수) 관리 시스템"""

    def __init__(self, game):
        self.game = game
        self.door_lamps = []
        self.door_defense_spawn_timer = 0.0

    def setup_escape_portal(self):
        """4방향 완전 대칭형 비상탈출문 벙커 챔버 생성 (동서남북 4개 사분면 균등 확률 무작위 스폰)"""
        min_cell = MAP_MIN_CHUNK * CHUNK_CELLS + 1
        max_cell = (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 2
        spawn_x = 1.5 * CELL_SIZE
        spawn_y = 1.5 * CELL_SIZE

        # 4개 사분면(NE, NW, SE, SW)별 도달 가능한 복도/광장 후보지 수집
        quads = {'NE': [], 'NW': [], 'SE': [], 'SW': []}
        all_cands = []

        for gx in range(min_cell, max_cell + 1):
            for gy in range(min_cell, max_cell + 1):
                if not cell_has_pillar(gx, gy):
                    cx = (gx + 0.5) * CELL_SIZE
                    cy = (gy + 0.5) * CELL_SIZE
                    d = math.hypot(cx - spawn_x, cy - spawn_y)
                    if 60.0 <= d <= 115.0:
                        all_cands.append((cx, cy))
                        if cx >= spawn_x and cy >= spawn_y:
                            quads['NE'].append((cx, cy))
                        elif cx < spawn_x and cy >= spawn_y:
                            quads['NW'].append((cx, cy))
                        elif cx >= spawn_x and cy < spawn_y:
                            quads['SE'].append((cx, cy))
                        else:
                            quads['SW'].append((cx, cy))

        # 4개 방향(동북, 서북, 동남, 서남) 중 하나를 무작위 선택하여 전방위 균등 분산
        available_quads = [q for q, items in quads.items() if items]
        if available_quads:
            chosen_q = random.choice(available_quads)
            escape_pos = random.choice(quads[chosen_q])
        elif all_cands:
            escape_pos = random.choice(all_cands)
        else:
            rnd_ang = random.uniform(0, math.pi * 2)
            rnd_d = random.uniform(70.0, 95.0)
            escape_pos = (spawn_x + math.cos(rnd_ang) * rnd_d, spawn_y + math.sin(rnd_ang) * rnd_d)

        self.game.escape_pos = escape_pos

        if hasattr(self.game, 'escape_portal_np') and self.game.escape_portal_np:
            self.game.escape_portal_np.removeNode()

        self.game.escape_portal_np = self.game.world_root.attachNewNode("escape_portal")
        self.game.escape_portal_np.setPos(escape_pos[0], escape_pos[1], 0)

        dark_metal_frame = LColor(0.12, 0.12, 0.14, 1.0)
        steel_door_plate = LColor(0.24, 0.25, 0.28, 1.0)
        lock_reinforce_col = LColor(0.38, 0.39, 0.43, 1.0)
        hazard_dim_stripe = LColor(0.45, 0.38, 0.12, 1.0)

        half_w = 1.35
        # 벙커 바닥 밀폐 플레이트
        make_cube_to(self.game.escape_portal_np, 3.0, 3.0, 0.20, dark_metal_frame, 0, 0, 0.10)
        # 벙커 내부 완전 차폐 솔리드 코어 (내부 빈 공간 노출 100% 원천 차단)
        make_cube_to(self.game.escape_portal_np, 2.70, 2.70, 5.20, LColor(0.08, 0.08, 0.09, 1.0), 0, 0, 2.60)

        for cx_sign in (-1, 1):
            for cy_sign in (-1, 1):
                make_cube_to(self.game.escape_portal_np, 0.30, 0.30, 5.4, dark_metal_frame, cx_sign * half_w, cy_sign * half_w, 2.7)

        make_cube_to(self.game.escape_portal_np, 3.0, 3.0, 0.35, dark_metal_frame, 0, 0, 5.4)

        self.door_lamps.clear()
        for h in (0, 90, 180, 270):
            face_np = self.game.escape_portal_np.attachNewNode(f"door_face_{h}")
            face_np.setH(h)

            # 상단 인방 및 강철 도어 플레이트: 기둥과 완벽 오버랩(너비 2.70m, 높이 5.20m)으로 틈새 밀폐
            make_cube_to(face_np, 2.70, 0.28, 0.40, dark_metal_frame, 0, half_w, 5.20)
            make_cube_to(face_np, 2.70, 0.16, 5.20, steel_door_plate, 0, half_w, 2.60)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 1.2)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 2.6)
            make_cube_to(face_np, 2.1, 0.18, 0.15, lock_reinforce_col, 0, half_w + 0.04, 4.0)
            make_cube_to(face_np, 0.14, 0.22, 0.40, lock_reinforce_col, 0.85, half_w + 0.06, 2.5)
            make_cube_to(face_np, 2.3, 0.18, 0.20, hazard_dim_stripe, 0, half_w + 0.03, 0.30)

            make_cube_to(face_np, 0.40, 0.16, 0.16, dark_metal_frame, 0, half_w + 0.05, 5.5)
            lamp = make_cube_to(face_np, 0.28, 0.08, 0.10, LColor(0.35, 0.25, 0.08, 1.0), 0, half_w + 0.08, 5.5)
            lamp.setLightOff()
            self.door_lamps.append(lamp)

        self.game.door_lamps = self.door_lamps

        # 벙커 상단 비상 유도 비콘등 (Emergency Beacon Strobe Light)
        if hasattr(self.game, 'beacon_light_np') and self.game.beacon_light_np and not self.game.beacon_light_np.isEmpty():
            self.game.render.clearLight(self.game.beacon_light_np)
            self.game.beacon_light_np.removeNode()

        b_light = PointLight('escape_beacon_light')
        b_light.setColor((0.35, 1.5, 0.55, 1.0))
        b_light.setAttenuation((1.0, 0.05, 0.006))
        self.game.beacon_light_np = self.game.escape_portal_np.attachNewNode(b_light)
        self.game.beacon_light_np.setPos(0, 0, 4.3)
        self.game.beacon_is_lit = False

        # 비콘 발광 큐브
        beacon_bulb = make_sphere_to(self.game.escape_portal_np, 0.45, 0.45, 0.55, LColor(0.2, 1.0, 0.4, 1.0), 0, 0, 4.3)
        beacon_bulb.setLightOff()
        self.game.beacon_bulb = beacon_bulb

        # 관문 벙커(3.0m x 3.0m) 견고한 AABB 충돌체 등록 - 플레이어 및 몬스터 통과 완벽 차단
        clear_custom_colliders()
        ex, ey = escape_pos[0], escape_pos[1]
        register_custom_collider((ex - 1.5, ey - 1.5, ex + 1.5, ey + 1.5))

    def update_door_defense(self, dt, px, py):
        """탈출 관문 앞 3.8m 방어 판정 (관문 외벽에서 5초 사수 시 상점 모달 팝업)"""
        escape_pos = getattr(self.game, 'escape_pos', None)
        if not escape_pos:
            return False

        dist_exit = math.hypot(px - escape_pos[0], py - escape_pos[1])
        if dist_exit <= 3.8:
            # 3스테이지 이상인 경우 보스 [케이블 엔티티: 심연의 지배자] 격파 필수
            if self.game.current_stage >= 3:
                if not getattr(self.game, 'boss_spawned', False):
                    self.game.spawn_boss()
                if self.game.boss and getattr(self.game.boss, 'hp', 0) > 0 and self.game.boss in self.game.monsters:
                    self.game.ui_mgr.update_door_status(
                        f"[ 관문 비상 봉쇄: 심연의 지배자를 먼저 격파하십시오! ]\n보스 체력: {int(self.game.boss.hp)} / {int(self.game.boss.max_hp)}",
                        fg=(1.0, 0.25, 0.25, 1.0)
                    )
                    return False

            old_timer = self.game.door_hold_timer
            self.game.door_hold_timer -= dt
            progress_sec = 5.0 - max(0.0, self.game.door_hold_timer)

            # 매 1초마다 전자 보안 비프음 재생
            if int(progress_sec) != int(5.0 - max(0.0, old_timer)):
                if hasattr(self.game, 'audio_mgr') and self.game.audio_mgr:
                    self.game.audio_mgr.play_door_alarm()

            # 관문 개방 시도 중 괴물 긴급 유입 (2.0초마다 추가 괴물 증원)
            self.door_defense_spawn_timer += dt
            if self.door_defense_spawn_timer >= 2.0:
                self.door_defense_spawn_timer = 0.0
                if len(self.game.monsters) < 18:
                    self.game.spawn_reinforcement_monster(near_gate=True)

            pct = max(0.0, min(1.0, progress_sec / 5.0))
            bars = int(pct * 16)
            bar_str = "■" * bars + "□" * (16 - bars)

            blink = (int(globalClock.getFrameTime() * 8) % 2 == 0)
            blink_col = LColor(0.9, 0.15, 0.15, 1.0) if blink else LColor(0.3, 0.05, 0.05, 1.0)
            for lamp in self.door_lamps:
                lamp.setColor(blink_col)

            if self.game.door_hold_timer <= 0.0:
                for lamp in self.door_lamps:
                    lamp.setColor(LColor(0.2, 1.0, 0.4, 1.0))
                if hasattr(self.game, 'audio_mgr') and self.game.audio_mgr:
                    self.game.audio_mgr.play_door_unlock()
                self.game.door_hold_timer = 5.0
                # 던전 크롤러: 스탯 분배 및 상점 모달 팝업 & 다음 스테이지 준비
                self.game.game_state = "SHOP"
                self.game.player.lock_mouse(False)
                self.game.combat.stop_aim()
                self.game.ui_mgr.show_stage_clear_shop(
                    self.game.current_stage, self.game.player, self.game.combat,
                    self.game.on_shop_closed, on_victory_callback=self.game.trigger_victory
                )
                return True
            else:
                msg = f"[ 비상문 개방 중: {progress_sec:.1f}s / 5.0s  [{bar_str}] ]\n[ 경고: 문이 열릴 때까지 쏟아지는 괴물의 접근을 저지하세요! ]"
                self.game.ui_mgr.update_door_status(msg, fg=(1.0, 0.85, 0.2, 1.0))
        else:
            if self.game.door_hold_timer < 5.0:
                self.game.door_hold_timer = 5.0
                idle_col = LColor(0.35, 0.25, 0.08, 1.0)
                for lamp in self.door_lamps:
                    lamp.setColor(idle_col)
                self.game.ui_mgr.update_door_status("[ 비상문 개방 중단! 탈출 관문 앞을 사수하세요! ]", fg=(1.0, 0.3, 0.3, 1.0))
            else:
                self.game.ui_mgr.update_door_status("", show=False)
        return False

    def cleanup(self):
        """포털 노드 및 라이트 정리"""
        if hasattr(self.game, 'beacon_light_np') and self.game.beacon_light_np and not self.game.beacon_light_np.isEmpty():
            self.game.render.clearLight(self.game.beacon_light_np)
            self.game.beacon_light_np.removeNode()
            self.game.beacon_light_np = None
        if hasattr(self.game, 'escape_portal_np') and self.game.escape_portal_np and not self.game.escape_portal_np.isEmpty():
            self.game.escape_portal_np.removeNode()
            self.game.escape_portal_np = None
        self.door_lamps.clear()
        self.game.door_lamps = []
