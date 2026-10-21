"""
Combat and HUD Features Unit Tests
Verifies:
1. Floating Damage Numbers (spawning, pooling, lifecycle, and formatting)
2. Flesh Impact SFX trigger on body and pierce hits
3. Tactical Circular Radar (geometry, blip projection, heading rotation, and distance clamping)
4. [ESC] Pause & Settings Modal (sensitivity, SFX, BGM, FOV adjustments, toggle)
5. After-Action Report (stats tracking, score ranking, report modal)
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace
from panda3d.core import NodePath, Vec3, TextNode
from ui_manager import FloatingDamageItem, FloatingDamageManager, UIManager
from combat_system import CombatSystem, WEAPON_CONFIGS
from player_controller import PlayerController
from audio_system import AudioManager


class CombatHUDFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.root = NodePath("test_root")

    def tearDown(self):
        if hasattr(self, 'root') and not self.root.isEmpty():
            self.root.removeNode()

    # =========================================================================
    # 1. Floating Damage Numbers
    # =========================================================================
    def test_floating_damage_item_formatting(self):
        """플로팅 대미지 폰트 텍스트 및 컬러 포맷 검증"""
        item = FloatingDamageItem(self.root)
        
        # 일반 타격
        item.activate(42.4, Vec3(0, 0, 1), is_crit=False, is_headshot=False)
        self.assertTrue(item.is_active)
        self.assertEqual(item.text_node.getText(), "42")
        self.assertEqual(item.color, (1.0, 0.98, 0.78))

        # 치명타
        item.activate(99.0, Vec3(0, 0, 1), is_crit=True, is_headshot=False)
        self.assertEqual(item.text_node.getText(), "CRIT 99!")
        self.assertEqual(item.color, (1.0, 0.30, 0.18))

        # 헤드샷
        item.activate(150.0, Vec3(0, 0, 1), is_crit=True, is_headshot=True)
        self.assertEqual(item.text_node.getText(), "HEADSHOT 150!")
        self.assertEqual(item.color, (1.0, 0.85, 0.15))

        # 원소 화염
        item.activate(25.0, Vec3(0, 0, 1), damage_type="fire")
        self.assertIn("FIRE", item.text_node.getText())

        # 원소 전기
        item.activate(60.0, Vec3(0, 0, 1), damage_type="electric")
        self.assertIn("SHOCK", item.text_node.getText())

    def test_floating_damage_manager_lifecycle_and_pooling(self):
        """플로팅 대미지 매니저의 풀링 및 페이드아웃 라이프사이클 검증"""
        mgr = FloatingDamageManager(self.root, pool_size=4)
        self.assertEqual(len(mgr.pool), 4)

        mgr.spawn(30, Vec3(1, 2, 3))
        self.assertTrue(mgr.pool[0].is_active)
        self.assertEqual(mgr.cursor, 1)

        # 0.5초 경과 (상승 중)
        mgr.update(0.5)
        self.assertTrue(mgr.pool[0].is_active)
        self.assertGreater(mgr.pool[0].pos.z, 3.0)

        # 0.4초 추가 경과 (총 0.9초 > max_timer 0.85초) -> 비활성화
        mgr.update(0.4)
        self.assertFalse(mgr.pool[0].is_active)

    # =========================================================================
    # 2. Flesh Impact SFX
    # =========================================================================
    def test_flesh_impact_sfx_on_body_hit(self):
        """몸통 적중 시 play_flesh_hit이 호출되고 헤드샷 크런치는 호출되지 않는지 검증"""
        combat = CombatSystem.__new__(CombatSystem)
        combat.camera = NodePath("cam")
        combat.world_root = self.root
        combat.ui_mgr = Mock()
        combat.audio_mgr = Mock()
        combat.base = SimpleNamespace(chunks={})
        combat.spawn_hit_particles = Mock()
        combat._spawn_tracer_effect = Mock()
        combat.register_kill = Mock()
        combat.record_combat_hit = Mock()
        combat.current_weapon = "PISTOL"
        combat.weapon_states = {"PISTOL": {"max_ammo": 12}}
        combat.ammo = 6
        combat.max_ammo = 12
        combat.combo_count = 0

        monster = Mock()
        monster.hp = 100
        monster.max_hp = 100
        monster.last_hit_was_head = False
        monster.last_action_dodged = False
        monster.take_damage = Mock(return_value=False)
        monster.is_hit_by_ray = Mock(return_value=(True, 5.0))
        monster.name = "괴물"

        with patch("combat_system.raycast_walls", return_value=(55.0, Vec3(0, 55, 0))):
            combat._perform_raycast(Vec3(0, 1, 0), Vec3(0, 0, 0), [monster], None, None, False, WEAPON_CONFIGS["PISTOL"])

        combat.audio_mgr.play_flesh_hit.assert_called_once()
        combat.audio_mgr.play_headshot_crunch.assert_not_called()

    def test_headshot_sfx_does_not_play_flesh_hit(self):
        """헤드샷 적중 시 play_headshot_crunch가 호출되고 play_flesh_hit은 호출되지 않는지 검증"""
        combat = CombatSystem.__new__(CombatSystem)
        combat.camera = NodePath("cam")
        combat.world_root = self.root
        combat.ui_mgr = Mock()
        combat.audio_mgr = Mock()
        combat.base = SimpleNamespace(chunks={})
        combat.spawn_hit_particles = Mock()
        combat._spawn_tracer_effect = Mock()
        combat.register_kill = Mock()
        combat.record_combat_hit = Mock()
        combat.current_weapon = "PISTOL"
        combat.weapon_states = {"PISTOL": {"max_ammo": 12}}
        combat.ammo = 6
        combat.max_ammo = 12
        combat.combo_count = 0

        monster = Mock()
        monster.hp = 100
        monster.max_hp = 100
        monster.last_hit_was_head = True
        monster.last_action_dodged = False
        monster.stun_timer = 0.0
        monster.take_damage = Mock(return_value=False)
        monster.is_hit_by_ray = Mock(return_value=(True, 5.0))
        monster.name = "괴물"

        with patch("combat_system.raycast_walls", return_value=(55.0, Vec3(0, 55, 0))):
            combat._perform_raycast(Vec3(0, 1, 0), Vec3(0, 0, 0), [monster], None, None, False, WEAPON_CONFIGS["PISTOL"])

        combat.audio_mgr.play_headshot_crunch.assert_called_once()
        combat.audio_mgr.play_flesh_hit.assert_not_called()

    # =========================================================================
    # 3. Tactical Circular Radar Coordinate Projection
    # =========================================================================
    def test_tactical_radar_projection_and_heading(self):
        """원형 전술 레이더의 상대 좌표 투영 및 시선 각도 회전 검증"""
        ui = UIManager.__new__(UIManager)
        ui.radar_root = Mock(isHidden=Mock(return_value=False))
        ui.radar_radius = 0.20
        ui.radar_max_dist = 35.0

        pos_tracker = {}
        blip = Mock()
        blip.fg = (1.0, 0.24, 0.24, 1.0)
        def set_pos(x, z):
            pos_tracker['x'] = x
            pos_tracker['z'] = z
        blip.setPos = set_pos

        ui.monster_blips = [blip]
        ui.portal_blip = Mock()
        ui.crate_blips = []

        # Case A: 플레이어가 북쪽(heading=0)을 보고 있고 적이 10m 정면 북쪽에 위치
        monster = SimpleNamespace(hp=100, is_corpse=False, pos=Vec3(0, 10, 0))
        ui.update_tactical_radar(player_pos=(0, 0), heading=0.0, monsters=[monster])

        self.assertAlmostEqual(pos_tracker['x'], 0.0, places=3)
        self.assertGreater(pos_tracker['z'], 0.0)

        # Case B: 플레이어가 90도 우회전(heading=-90, 동쪽 지향)하면 정북의 적은 좌측(X < 0)에 위치해야 함
        ui.update_tactical_radar(player_pos=(0, 0), heading=-90.0, monsters=[monster])
        self.assertLess(pos_tracker['x'], 0.0)

        # Case C: 35m 초과 거리는 원형 외곽(radius=0.20)으로 클램핑
        far_monster = SimpleNamespace(hp=100, is_corpse=False, pos=Vec3(0, 100, 0))
        ui.update_tactical_radar(player_pos=(0, 0), heading=0.0, monsters=[far_monster])
        self.assertAlmostEqual(pos_tracker['z'], ui.radar_radius, delta=0.02)

    # =========================================================================
    # 4. [ESC] Pause & Settings Modal
    # =========================================================================
    def test_pause_settings_adjustments(self):
        """일시정지 설정 메뉴 내 감도 및 볼륨 조정 검증"""
        ui = UIManager.__new__(UIManager)
        ui.pause_player = SimpleNamespace(mouse_sensitivity=0.15)
        ui.pause_audio_mgr = Mock(master_sfx_volume=1.0, master_bgm_volume=1.0)
        ui.txt_sens_val = Mock()
        ui.txt_sfx_val = Mock()
        ui.txt_bgm_val = Mock()
        ui.txt_fov_val = Mock()
        ui.base = SimpleNamespace(camLens=Mock(getFov=Mock(return_value=(96.0, 60.0))))

        # 감도 증가
        ui._adjust_setting("sens", +0.02)
        self.assertAlmostEqual(ui.pause_player.mouse_sensitivity, 0.17, places=2)
        ui.txt_sens_val.setText.assert_called_with("0.17")

        # SFX 볼륨 감소
        ui._adjust_setting("sfx", -0.10)
        ui.pause_audio_mgr.set_sfx_volume.assert_called_with(0.9)

        # BGM 볼륨 감소
        ui._adjust_setting("bgm", -0.10)
        ui.pause_audio_mgr.set_bgm_volume.assert_called_with(0.9)

    # =========================================================================
    # 5. After-Action Report (AAR)
    # =========================================================================
    def test_after_action_report_stats_and_grading(self):
        """전투 결과 보고서 통계 누적 및 S+ 등급 판정 검증"""
        combat = CombatSystem.__new__(CombatSystem)
        combat.stage_kills = 25
        combat.stage_headshots = 30
        combat.stage_shots_fired = 100
        combat.stage_shots_hit = 80
        combat.stage_damage_dealt = 12500.0
        combat.stage_damage_taken = 20.0
        combat.stage_max_combo = 15
        combat.stage_start_time = 0.0

        stats = combat.get_stage_stats()
        self.assertEqual(stats["kills"], 25)
        self.assertEqual(stats["headshots"], 30)
        self.assertAlmostEqual(stats["accuracy"], 80.0)
        self.assertAlmostEqual(stats["headshot_ratio"], 37.5)

        # UI 결과 보고서 등급 판정 테스트
        ui = UIManager.__new__(UIManager)
        ui.aar_modal = Mock()
        ui.aar_title = Mock()
        ui.aar_sub = Mock()
        ui.aar_stats_values = Mock()
        ui.aar_rank_badge = Mock()
        ui.aar_rank_title = Mock()
        ui.aar_rank_comment = Mock()

        ui.show_after_action_report(stage=1, stats=stats)
        ui.aar_rank_badge.setText.assert_called_with("RANK  S+")

    # =========================================================================
    # 6. Monster & Elite Monster Names
    # =========================================================================
    def test_monster_and_elite_names(self):
        """일반 몬스터 및 엘리트 몬스터 고유 명칭 변경 검증"""
        from spawner import apply_elite_mutation
        from monster import (
            AbominableMudOrc, TallSkeletonMonster,
            AlluringAshWitch, LongBlackSerpent,
            SkeletalDobermanHellhound
        )

        mock_game = SimpleNamespace(render=Mock())

        # 1. 일반 오크 이름 검증
        orc = AbominableMudOrc.__new__(AbominableMudOrc)
        orc.max_hp = 280
        orc.hp = 280
        orc.attack_damage = 35
        orc.exp_value = 65
        orc.node = Mock()
        orc.name = "뼈박살 오크"
        self.assertEqual(orc.name, "뼈박살 오크")

        # 2. 엘리트 변이 시 명칭 검증
        apply_elite_mutation(orc, mock_game)
        self.assertEqual(orc.name, "되살아난 거산 스룬달")

        skeleton = TallSkeletonMonster.__new__(TallSkeletonMonster)
        skeleton.max_hp = 200
        skeleton.hp = 200
        skeleton.attack_damage = 30
        skeleton.exp_value = 50
        skeleton.node = Mock()
        skeleton.name = "장신 해골 괴물"
        apply_elite_mutation(skeleton, mock_game)
        self.assertEqual(skeleton.name, "휩쓰는 공포 스컬")

        witch = AlluringAshWitch.__new__(AlluringAshWitch)
        witch.max_hp = 160
        witch.hp = 160
        witch.attack_damage = 25
        witch.exp_value = 55
        witch.node = Mock()
        witch.name = "매혹의 잿더미 마녀"
        apply_elite_mutation(witch, mock_game)
        self.assertEqual(witch.name, "염마 스칼렛")

        serpent = LongBlackSerpent.__new__(LongBlackSerpent)
        serpent.max_hp = 350
        serpent.hp = 350
        serpent.attack_damage = 40
        serpent.exp_value = 80
        serpent.node = Mock()
        serpent.name = "검은 뱀 괴물"
        apply_elite_mutation(serpent, mock_game)
        self.assertEqual(serpent.name, "백골룡 우르보로스")

        hound = SkeletalDobermanHellhound.__new__(SkeletalDobermanHellhound)
        hound.max_hp = 120
        hound.hp = 120
        hound.attack_damage = 20
        hound.exp_value = 40
        hound.node = Mock()
        hound.name = "지옥의 파수견"
        apply_elite_mutation(hound, mock_game)
        self.assertEqual(hound.name, "끝없는 고통의 켈베스")

    # =========================================================================
    # 7. Weapon Arsenal & HUD Top Guide Removal
    # =========================================================================
    def test_weapon_configurations_and_arsenal(self):
        """4종 무기(데저트 이글, 듀얼 글록, 돌격소총 AR, 펌프 샷건) 사양 및 명칭 검증"""
        from combat_system import WEAPON_ORDER
        self.assertEqual(WEAPON_ORDER, ["PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"])

        # 1. .50 매그넘 데저트 이글
        deagle = WEAPON_CONFIGS["PISTOL"]
        self.assertIn("데저트 이글", deagle["name"])
        self.assertEqual(deagle["max_ammo"], 7)
        self.assertEqual(deagle["initial_reserve"], 28)
        self.assertEqual(deagle["damage"], 120.0)
        self.assertEqual(deagle["headshot_mult"], 3.2)

        # 2. 9mm 듀얼 글록 (아킴보)
        glock = WEAPON_CONFIGS["DUAL_PISTOL"]
        self.assertIn("글록", glock["name"])
        self.assertEqual(glock["max_ammo"], 34)
        self.assertEqual(glock["initial_reserve"], 68)
        self.assertEqual(glock["damage"], 26.0)
        self.assertEqual(glock["cooldown"], 0.065)

        # 3. 5.56mm 전술 돌격소총 (AR)
        ar = WEAPON_CONFIGS["AR"]
        self.assertIn("AR", ar["name"])
        self.assertEqual(ar["max_ammo"], 30)
        self.assertEqual(ar["initial_reserve"], 90)
        self.assertEqual(ar["damage"], 38.0)
        self.assertEqual(ar["cooldown"], 0.082)

        # 4. 12게이지 펌프 샷건
        shotgun = WEAPON_CONFIGS["SHOTGUN"]
        self.assertIn("펌프 샷건", shotgun["name"])
        self.assertEqual(shotgun["max_ammo"], 8)
        self.assertEqual(shotgun["initial_reserve"], 24)
        self.assertEqual(shotgun["damage"], 25.0)
        self.assertEqual(shotgun["pellets"], 8)
        self.assertEqual(shotgun["pump_time"], 0.44)

    def test_weapon_cycling_and_switching(self):
        """무기 순환(Q / 휠) 및 직접 스왑 검증"""
        combat = CombatSystem.__new__(CombatSystem)
        combat.current_weapon = "PISTOL"
        combat.max_ammo = 7
        combat.ammo = 7
        combat._reserve_ammo = 28
        combat.slide_locked = False
        combat.is_reloading = False
        combat.shoot_cooldown = 0.0
        combat.audio_mgr = Mock()
        combat.ui_mgr = Mock()
        combat._update_viewmodel_visibility = Mock()
        combat.update_ammo_ui = Mock()
        combat.weapon_states = {
            "PISTOL": {"ammo": 7, "reserve_ammo": 28, "slide_locked": False, "max_ammo": 7},
            "DUAL_PISTOL": {"ammo": 34, "reserve_ammo": 68, "slide_locked": False, "max_ammo": 34},
            "AR": {"ammo": 30, "reserve_ammo": 90, "slide_locked": False, "max_ammo": 30},
            "SHOTGUN": {"ammo": 8, "reserve_ammo": 24, "slide_locked": False, "max_ammo": 8},
        }

        # next_weapon: PISTOL -> DUAL_PISTOL -> AR -> SHOTGUN -> PISTOL
        combat.next_weapon()
        self.assertEqual(combat.current_weapon, "DUAL_PISTOL")
        self.assertEqual(combat.max_ammo, 34)

        combat.next_weapon()
        self.assertEqual(combat.current_weapon, "AR")
        self.assertEqual(combat.max_ammo, 30)

        combat.next_weapon()
        self.assertEqual(combat.current_weapon, "SHOTGUN")
        self.assertEqual(combat.max_ammo, 8)

        combat.next_weapon()
        self.assertEqual(combat.current_weapon, "PISTOL")

        # prev_weapon: PISTOL -> SHOTGUN
        combat.prev_weapon()
        self.assertEqual(combat.current_weapon, "SHOTGUN")

        # Direct switch
        combat.switch_weapon("AR")
        self.assertEqual(combat.current_weapon, "AR")

    def test_top_center_guide_removed_from_ui(self):
        """중앙 상단 길잡이(panel_hud_top) 제거 및 update_hud 안전 no-op 검증"""
        ui = UIManager.__new__(UIManager)
        # update_hud should execute cleanly without raising an error
        ui.update_hud(10.0, 5.0, escape_pos=(3, 5), heading=45.0)
        # Verify panel_hud_top is not an active attribute
        self.assertFalse(hasattr(ui, "panel_hud_top"))

    def test_player_status_ui_in_bottom_right(self):
        """플레이어 상태 UI (HP, 스테미나, EXP, 유물, 퍽 배지)가 좌상단에서 우하단(x > 0, z < 0)으로 이동되었는지 검증"""
        ui = UIManager.__new__(UIManager)
        ui.base = SimpleNamespace(aspect2d=NodePath("dummy_aspect2d"))
        ui.font_kw = {}
        ui._cached_ammo_str = ""
        ui._cached_stamina_str = ""
        ui._cached_stamina_col = None
        ui._cached_hp_str = ""
        ui._cached_exp_str = ""
        ui._cached_door_str = ""

        # Test _set_bar_percentage anchor tracking in bottom right
        bar_calls = []
        def track_set_bar(fill_img, pct, cx, cz, hw, hh):
            bar_calls.append((cx, cz))
        ui._set_bar_percentage = track_set_bar

        ui.bar_fill_stamina = Mock()
        ui.stamina_text = Mock()
        ui.update_stamina(80, 100)
        self.assertEqual(len(bar_calls), 1)
        self.assertGreater(bar_calls[0][0], 1.0)  # x in right quadrant (cx > 1.0)
        self.assertLess(bar_calls[0][1], 0.0)     # z in bottom quadrant (cz < 0.0)

        ui.bar_fill_hp = Mock()
        ui.hp_text = Mock()
        ui.bar_fill_exp = Mock()
        ui.exp_text = Mock()
        ui.update_hp_exp(100, 100, 50, 100)
        self.assertEqual(len(bar_calls), 3)
        # HP anchor in bottom-right
        self.assertGreater(bar_calls[1][0], 1.0)
        self.assertLess(bar_calls[1][1], 0.0)
        # EXP anchor in bottom-right
        self.assertGreater(bar_calls[2][0], 1.0)
        self.assertLess(bar_calls[2][1], 0.0)

    def test_ar_hk416_configuration(self):
        """AR이 H&K HK416으로 정밀 정의되었는지 검증"""
        ar = WEAPON_CONFIGS["AR"]
        self.assertIn("HK416", ar["name"])
        self.assertIn("AR", ar["name"])
        self.assertIn("HK416", ar["description"])
        self.assertEqual(ar["max_ammo"], 30)
        self.assertEqual(ar["initial_reserve"], 90)
        self.assertEqual(ar["damage"], 38.0)
        self.assertEqual(ar["cooldown"], 0.082)


if __name__ == "__main__":
    unittest.main()

