"""
test_range.py - 몬스터 사격/관찰 시험장(Test Range) 샌드박스 룸 관리자

테스트 모드 전용 44m x 44m 대형 룸 생성, 스튜디오 조명 배치,
5종 몬스터 정지 소환 및 실시간 탄약/체력 보충, [F5] 재소환 루프를 독립적으로 관리합니다.
"""

import math
from direct.showbase.ShowBaseGlobal import globalClock
from panda3d.core import (
    CardMaker, TextureStage, PointLight, LColor
)

from constants import FOG_COLOR
from geometry import make_cube_to
from collision import register_custom_collider, clear_custom_colliders
from monster import (
    AlluringAshWitch, TallSkeletonMonster,
    SkeletalDobermanHellhound, AbominableMudOrc, LongBlackSerpent
)


class TestRangeManager:
    """테스트 모드(사격 시험장) 전용 룸 지오메트리, 조명, 몬스터 스폰 및 정리 관리자"""

    def __init__(self, game):
        self.game = game
        self.test_room_node = None
        self.test_lights = []

    def start_test_mode(self):
        """테스트 모드: 넓은 대형 시험장 룸, 5종 전 몬스터가 정지 상태로 대기 (자유 관찰 및 사격 테스트)"""
        g = self.game
        g.is_test_mode = True
        g.game_state = "PLAYING"
        g.game_over = False
        g.game_won = False
        g.time_limit = 9999.0
        g.time_left = 9999.0
        g.door_hold_timer = 9999.0
        g.stage_banner_timer = 0.0

        # 기존 발사체, 몬스터, 시체, 청크 완전 정리
        g.clear_projectiles()
        for m in g.monsters:
            m.destroy()
        g.monsters.clear()
        for c in g.corpses:
            c.destroy()
        g.corpses.clear()

        # 청크 비동기 작업 및 기존 미로 청크 파괴
        for fut in g.active_chunk_futures.values():
            fut.cancel()
        g.active_chunk_futures.clear()
        for chunk in g.chunks.values():
            chunk.destroy()
        g.chunks.clear()

        # 기존 관문 및 커스텀 충돌체 정리
        clear_custom_colliders()
        if hasattr(g, 'beacon_light_np') and g.beacon_light_np and not g.beacon_light_np.isEmpty():
            g.render.clearLight(g.beacon_light_np)
            g.beacon_is_lit = False

        # 플레이어 스탯 및 위치 (사격선 x=0, y=-10, z=1.7)
        g.player.reset_position(0.0, -10.0, heading=0.0, pitch=0.0)
        g.player.level = 1
        g.player.exp = 0
        g.player.exp_to_next = 100
        g.player.pending_perk_picks = 0
        g.player.on_level_up = g._on_player_level_up
        g._is_level_up_modal = False
        g.player.max_hp = 100.0
        g.player.hp = 100.0
        g.player.attack_power = 35.0
        g.player.speed_mult = 1.0

        # 전투 시스템: 모든 무기 넉넉한 탄약 제공
        g.combat.stop_aim()
        g.combat._reserve_ammo = 999
        for w_id in g.combat.weapon_states:
            g.combat.weapon_states[w_id]["ammo"] = g.combat.weapon_states[w_id]["max_ammo"]
            g.combat.weapon_states[w_id]["reserve_ammo"] = 999
            g.combat.weapon_states[w_id]["slide_locked"] = False
        g.combat.ammo = g.combat.max_ammo
        g.combat.reset_state(1, keep_ammo=True)
        g.player.reset_inventory()
        for item in g.player.inventory:
            if item.get("id") == "frag_grenade":
                item['count'] = 50
            else:
                item['count'] = 10
        g._update_quickslot_hud()

        # 대형 테스트 룸 지오메트리 구축 (44m x 44m, 높이 7.5m)
        self.build_test_room()

        # 5종 몬스터 정지 대기 스폰
        self.respawn_test_monsters()

        # UI 활성화 및 테스트 모드 안내
        g.combat.vm_root.show()
        g.render.setLight(g.combat.pl_np)
        g.render.setLight(g.combat.fill_np)
        g.ui_mgr.start_game_ui()
        g.player.lock_mouse(True)
        g.audio_mgr.set_bgm_mode("PLAYING")

        # 상단 안내 배너
        g.ui_mgr.show_stage_banner(
            "[ TEST RANGE : 몬스터 사격 시험장 ]\n"
            "[Z] 권총 | [X] 쌍권총 | [C] 샷건 | [Q/휠] 무기 스왑\n"
            "[F5] 몬스터 재소환 | [F8] 원소(화염/전기) 테스트 | [ESC] 메뉴 복귀",
            color=(0.35, 0.90, 1.0, 1.0)
        )
        g.stage_banner_timer = 6.0

    def build_test_room(self):
        """테스트 모드 전용 44m x 44m 대형 룸 생성 (바닥, 천장, 4면 벽체, 커스텀 충돌체, 스튜디오 조명)"""
        g = self.game
        if self.test_room_node and not self.test_room_node.isEmpty():
            self.test_room_node.removeNode()

        self.test_room_node = g.world_root.attachNewNode("test_room_node")
        g.test_room_node = self.test_room_node
        half_w = 22.0
        room_h = 7.5

        # 1. 바닥 (Floor)
        cm_floor = CardMaker('test_floor')
        cm_floor.setFrame(-half_w, half_w, -half_w, half_w)
        floor = self.test_room_node.attachNewNode(cm_floor.generate())
        floor.setP(-90)
        floor.setPos(0, 0, 0)
        floor.setTexture(g.floor_tex)
        floor.setTexScale(TextureStage.getDefault(), 12.0, 12.0)
        floor.setColorScale(0.70, 0.68, 0.62, 1.0)

        # 2. 천장 (Ceiling)
        cm_ceil = CardMaker('test_ceil')
        cm_ceil.setFrame(-half_w, half_w, -half_w, half_w)
        ceil_np = self.test_room_node.attachNewNode(cm_ceil.generate())
        ceil_np.setP(90)
        ceil_np.setPos(0, 0, room_h)
        ceil_np.setTexture(g.floor_tex)
        ceil_np.setTexScale(TextureStage.getDefault(), 12.0, 12.0)
        ceil_np.setColorScale(0.60, 0.58, 0.54, 1.0)
        ceil_np.setTwoSided(True)

        # 3. 4면 외곽 벽체 (Perimeter Walls)
        cm_wall_x = CardMaker('test_wall_x')
        cm_wall_x.setFrame(-half_w, half_w, 0, room_h)

        # 북쪽 벽 (y = half_w)
        wall_n = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_n.setPos(0, half_w, 0)
        wall_n.setH(180)
        wall_n.setTexture(g.wall_tex)
        wall_n.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 남쪽 벽 (y = -half_w)
        wall_s = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_s.setPos(0, -half_w, 0)
        wall_s.setH(0)
        wall_s.setTexture(g.wall_tex)
        wall_s.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 서쪽 벽 (x = -half_w)
        wall_w = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_w.setPos(-half_w, 0, 0)
        wall_w.setH(-90)
        wall_w.setTexture(g.wall_tex)
        wall_w.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 동쪽 벽 (x = half_w)
        wall_e = self.test_room_node.attachNewNode(cm_wall_x.generate())
        wall_e.setPos(half_w, 0, 0)
        wall_e.setH(90)
        wall_e.setTexture(g.wall_tex)
        wall_e.setTexScale(TextureStage.getDefault(), 10.0, 2.5)

        # 4. 외곽 충돌체 등록 (플레이어가 벽 밖으로 나가지 못하도록 차단)
        register_custom_collider((-half_w - 2.0, half_w - 0.4, half_w + 2.0, half_w + 2.0))
        register_custom_collider((-half_w - 2.0, -half_w - 2.0, half_w + 2.0, -half_w + 0.4))
        register_custom_collider((-half_w - 2.0, -half_w - 2.0, -half_w + 0.4, half_w + 2.0))
        register_custom_collider((half_w - 0.4, -half_w - 2.0, half_w + 2.0, half_w + 2.0))

        # 5. 사격선 바닥 표시선 (Tactical Firing Line)
        cm_line = CardMaker('firing_line')
        cm_line.setFrame(-16.0, 16.0, -0.15, 0.15)
        f_line = self.test_room_node.attachNewNode(cm_line.generate())
        f_line.setP(-90)
        f_line.setPos(0, -9.5, 0.02)
        f_line.setColorScale(0.95, 0.75, 0.15, 0.85)

        # 6. 발밑 전시 패널 (Pedestals - 5개 스탠드)
        for x_pos in [-10.0, -5.0, 0.0, 5.0, 10.0]:
            make_cube_to(self.test_room_node, 3.2, 3.2, 0.10, LColor(0.12, 0.12, 0.14, 1.0), x_pos, 4.0, 0.05)
            make_cube_to(self.test_room_node, 3.3, 0.08, 0.12, LColor(0.92, 0.76, 0.20, 1.0), x_pos, 2.36, 0.06)

        # 7. 스튜디오 조명 배치 (몬스터 세부 디테일을 환하게 비추는 6개의 천장 라이트)
        if self.test_lights:
            for l_np in self.test_lights:
                g.render.clearLight(l_np)
                l_np.removeNode()
        self.test_lights = []

        light_positions = [
            (-10.0, 4.0, 5.5),
            (-5.0, 4.0, 5.5),
            (0.0, 4.0, 5.5),
            (5.0, 4.0, 5.5),
            (10.0, 4.0, 5.5),
            (0.0, -8.0, 5.5)
        ]
        for idx, (lx, ly, lz) in enumerate(light_positions):
            pl = PointLight(f"test_light_{idx}")
            pl.setColor((1.4, 1.35, 1.25, 1.0))
            pl.setAttenuation((1.0, 0.04, 0.005))
            pl_np = self.test_room_node.attachNewNode(pl)
            pl_np.setPos(lx, ly, lz)
            self.render_light(pl_np, g)
            self.test_lights.append(pl_np)
        g.test_lights = self.test_lights

        # 8. 안개 완화 (시험장 전체가 또렷하게 보이도록 안개 원거리 조정)
        g.liminal_fog.setColor((0.15, 0.16, 0.18, 1.0))
        g.liminal_fog.setExpDensity(0.003)
        g.setBackgroundColor((0.15, 0.16, 0.18, 1.0))
        g.amb_np.node().setColor((0.25, 0.25, 0.28, 1.0))

    def render_light(self, pl_np, g):
        g.render.setLight(pl_np)

    def respawn_test_monsters(self):
        """테스트 모드 5종 몬스터를 스탠드 위치에 정지 상태로 소환/재소환"""
        g = self.game
        for m in g.monsters:
            m.destroy()
        g.monsters.clear()
        for c in g.corpses:
            c.destroy()
        g.corpses.clear()

        # 1. 잿더미 마녀 (Alluring Ash Witch)
        witch = AlluringAshWitch(g.world_root, -10.0, 4.0)
        witch.node.setH(180)

        # 2. 장신 해골 괴물 (Tall Skeleton Monster)
        skel = TallSkeletonMonster(g.world_root, -5.0, 4.0)
        skel.node.setH(180)

        # 3. 지옥의 파수견 (Skeletal Doberman Hellhound)
        hound = SkeletalDobermanHellhound(g.world_root, 0.0, 4.0)
        hound.node.setH(180)

        # 4. 혐오스런 진흙 오크 (Abominable Mud Orc)
        orc = AbominableMudOrc(g.world_root, 5.0, 4.0)
        orc.node.setH(180)

        # 5. 검은 뱀 괴물 (Long Black Serpent)
        serp = LongBlackSerpent(g.world_root, 10.0, 4.0)
        serp.node.setH(180)

        g.monsters = [witch, skel, hound, orc, serp]

        # 몬스터별 스폰 좌표 및 리스폰 속성 설정
        for m in g.monsters:
            m._test_spawn_pos = (m.pos.x, m.pos.y)
            m._test_respawn_timer = 3.0

        if hasattr(g, 'ui_mgr') and g.ui_mgr:
            g.ui_mgr.show_hit_marker("[ 몬스터 5종 정지 소환 완료 ]")

    def cleanup_test_room(self):
        """테스트 모드 종료 시 룸 노드, 조명, 충돌체 및 안개 원복"""
        g = self.game
        g.is_test_mode = False
        if self.test_room_node and not self.test_room_node.isEmpty():
            self.test_room_node.removeNode()
            self.test_room_node = None
        g.test_room_node = None
        if self.test_lights:
            for l_np in self.test_lights:
                g.render.clearLight(l_np)
                l_np.removeNode()
            self.test_lights = []
        g.test_lights = []
        clear_custom_colliders()
        g.liminal_fog.setColor(FOG_COLOR)
        g.liminal_fog.setExpDensity(0.038)
        g.setBackgroundColor(FOG_COLOR)

    def on_f5_pressed(self):
        """[F5] 키 입력 시 테스트 모드 몬스터 즉시 재소환"""
        if getattr(self.game, 'is_test_mode', False):
            self.respawn_test_monsters()
