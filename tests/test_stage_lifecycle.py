"""Headless integration: real assets, UI, tasks and scene nodes; isolated rankings."""

import json
import tempfile
import unittest
from collections import Counter
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from panda3d.core import LightAttrib, Vec3, loadPrcFileData

from audio_system import AudioManager
from constants import FOG_COLOR
from game import Fireball, GroundShockwave, LiminalInfiniteLoop


class StageLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loadPrcFileData('', 'window-type none\naudio-library-name null\nmodel-cache-models false\nmodel-cache-textures false\nnotify-level-text error')
        cls.app = LiminalInfiniteLoop()
        cls.temp = tempfile.TemporaryDirectory()
        cls.app.ui_mgr.rank_file = str(Path(cls.temp.name) / 'rankings.json')

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()
        cls.app.destroy()  # Repeated shutdown must be harmless.
        cls.temp.cleanup()

    def setUp(self):
        self.app.return_to_intro()
        self.base_light_count = self.light_count()
        self.app.start_game()
        self.finish_loading()

    def tearDown(self):
        self.app.return_to_intro()
        self.assertEqual(self.light_count(), self.base_light_count)

    def light_count(self):
        lights = self.app.render.getAttrib(LightAttrib)
        return lights.getNumOnLights() if lights else 0

    def finish_loading(self):
        for _ in range(100):
            self.app.taskMgr.step()
            if self.app.game_state == 'PLAYING':
                break
        self.assertEqual(self.app.game_state, 'PLAYING')
        self.assertFalse(self.app.taskMgr.hasTaskNamed('loading_process_task'))
        self.assertTrue(self.app.player.mouse_locked)
        self.assertTrue(self.app.ui_mgr.loading_modal.isHidden())

    def activate_altars_and_enter_gate(self):
        app = self.app
        for altar in app.altars:
            app.player.key_map['e'] = 1
            self.assertFalse(app._update_door_defense(1.5, *altar['pos']))
            self.assertTrue(altar['activated'])
        app.player.key_map['e'] = 0
        self.assertEqual(app.activated_altars_count, 3)
        self.assertTrue(app.escape_gate['opened'])
        self.assertTrue(app._update_door_defense(0.81, *app.escape_gate['pos']))
        self.assertEqual(app.game_state, 'SHOP')
        self.assertFalse(app.player.mouse_locked)
        self.assertFalse(app.ui_mgr.shop_modal.isHidden())

    def add_transient_effects(self):
        app = self.app
        app.combat.shoot(app.monsters, app.player)
        app.inventory.use_censer(app.player)
        app.inventory.use_fire_pot(app.player)
        app.inventory.create_ground_fire(Vec3(9, 9, 0.03))
        app.inventory.spawn_explosion_particles(Vec3(9, 9, 1))
        app.fireballs.append(Fireball(app.render, Vec3(20, 20, 1), Vec3(9, 9, 1)))
        app.shockwaves.append(GroundShockwave(app.render, 20, 20))
        app.combat.recoil_node.setP(20)
        app.ui_mgr.trigger_player_damage_flash()
        app.ui_mgr.trigger_crosshair_hit()

    def assert_no_transient_effects(self):
        app = self.app
        for items in (app.fireballs, app.shockwaves, app.combat.active_bolts,
                      app.combat.hit_particles, app.inventory.active_fire_pots,
                      app.inventory.ground_fires, app.inventory.fire_particles):
            self.assertEqual(items, [])
        self.assertEqual(app.inventory.censer_timer, 0)
        self.assertEqual(app.combat.recoil_node.getP(), 0)
        self.assertEqual(app.ui_mgr.damage_flash_alpha, 0)
        self.assertEqual(app.ui_mgr.crosshair_hit_timer, 0)

    def test_full_flow_preserves_growth_then_resets_new_game(self):
        app = self.app
        self.assertEqual(app.current_stage, 1)
        self.assertEqual(len(app.monsters), 7)
        app.player.gain_exp(100)
        self.add_transient_effects()
        self.activate_altars_and_enter_gate()
        frozen_time = app.time_left
        for _ in range(3):
            app.taskMgr.step()
        self.assertEqual(app.time_left, frozen_time)

        app.ui_mgr._allocate('SPD')
        app.ui_mgr._allocate('AMMO')
        app.ui_mgr._select_relic(0)
        growth = (app.player.level, app.player.stat_points, app.player.max_hp,
                  app.player.max_stamina, app.player.speed_mult, list(app.player.relics),
                  app.combat.reload_duration, dict(app.inventory.items))
        reserve = app.combat.reserve_ammo
        old_nodes = [m.node for m in app.monsters] + [a['node'] for a in app.altars]
        app.ui_mgr._confirm_shop_and_start()
        self.assertEqual(app.game_state, 'LOADING')
        app.taskMgr.step()
        step = app.loading_step
        app.start_game()
        app.on_shop_closed()
        self.assertEqual(app.loading_step, step, 'Repeated callbacks must not restart loading')
        self.finish_loading()
        self.assertEqual(app.current_stage, 2)
        self.assertEqual(len(app.monsters), 10)
        self.assertEqual(app.activated_altars_count, 0)
        self.assertFalse(app.escape_gate['opened'])
        self.assertTrue(all(node.isEmpty() for node in old_nodes))
        self.assertEqual(growth, (app.player.level, app.player.stat_points, app.player.max_hp,
                                 app.player.max_stamina, app.player.speed_mult, list(app.player.relics),
                                 app.combat.reload_duration, dict(app.inventory.items)))
        self.assertEqual(app.combat.reserve_ammo, reserve + 18)
        self.assert_no_transient_effects()

        app.player.hp = 1
        app.player.invincible_timer = 0
        killer = app.monsters[0]
        killer.pos.x, killer.pos.y = app.camera.getX(), app.camera.getY()
        killer.stun_timer = 0
        app.update(None)
        self.assertEqual(app.game_state, 'GAME_OVER')
        records = app.ui_mgr.load_rankings()
        app.trigger_game_over(killer=killer)
        self.assertEqual(app.ui_mgr.load_rankings(), records)
        self.assertEqual(records[-1]['stage'], 2)
        app.return_to_intro()
        self.assertEqual(app.game_state, 'INTRO')
        self.assertIsNone(app.killer_monster)
        self.assertFalse(app.game_over)
        self.assertTrue(app.ui_mgr.shop_modal.isHidden())
        app.start_game()
        self.finish_loading()
        self.assertEqual(app.current_stage, 1)
        self.assertEqual(app.player.level, 1)
        self.assertEqual(app.player.stat_points, 0)
        self.assertEqual(app.player.relics, [])
        self.assertEqual(app.player.max_stamina, 100)
        self.assertEqual(app.combat.reload_duration, 1.25)
        self.assertEqual(app.combat.reserve_ammo, 15)

    def test_menu_return_cleans_scene_and_fog(self):
        app = self.app
        app.trigger_abyssal_inversion()
        self.add_transient_effects()
        app.altars[0]['activated'] = True
        app.render.setLight(app.altars[0]['light_np'])
        app.return_to_intro()
        self.assert_no_transient_effects()
        self.assertEqual(app.monsters, [])
        self.assertEqual(app.corpses, [])
        self.assertEqual(app.altars, [])
        self.assertIsNone(app.escape_gate)
        self.assertEqual(app.combat.ammo_drops, [])
        self.assertEqual(app.inventory.relic_caches, [])
        self.assertEqual(app.liminal_fog.getColor(), FOG_COLOR)
        self.assertFalse(app.blackout_active)
        self.assertFalse(app.combat.is_blackout)
        self.assertEqual(app.audio_mgr.audio3d.sound_dict, {})

    def test_compass_rotation_rear_target_gate_and_visibility(self):
        app = self.app
        compass = app.ui_mgr.compass
        self.assertFalse(compass.root.isHidden())
        for bearing in (0, 90, 180, 270, 360, 720):
            app.camera.setH(-bearing)
            app._update_door_defense(0, app.camera.getX(), app.camera.getY())
            self.assertEqual(compass.heading, bearing % 360)
            self.assertFalse(compass.cardinals[bearing % 360].isHidden())
            self.assertAlmostEqual(compass.cardinals[bearing % 360].getX(), 0)

        altar = dict(pos=(-10, -10), activated=False, name='rear')
        app.ui_mgr.update_navigation(0, 0, 0, [altar], None)
        self.assertAlmostEqual(compass.marker.getX(), -compass.HALF_WIDTH)
        self.assertFalse(compass.left_arrow.isHidden())
        self.assertIn('뒤쪽', app.ui_mgr.altar_status_text.getText())
        app.ui_mgr.update_navigation(0, -10, -10, [altar], None)
        self.assertAlmostEqual(compass.marker.getX(), 0)
        self.assertTrue(compass.left_arrow.isHidden())

        # All three real altar interactions must switch the marker to the gate.
        for real_altar in app.altars:
            app.player.key_map['e'] = 1
            app._update_door_defense(1.5, *real_altar['pos'])
        app.player.key_map['e'] = 0
        self.assertEqual(compass.target['kind'], 'gate')
        self.assertFalse(compass.gate_icon.isHidden())
        self.assertTrue(compass.altar_icon.isHidden())
        app._update_door_defense(0.81, *app.escape_gate['pos'])
        self.assertTrue(compass.root.isHidden())
        self.assertTrue(app.ui_mgr.altar_status_text.isHidden())
        self.assertIsNone(compass.target)
        app.ui_mgr._confirm_shop_and_start()
        self.assertTrue(compass.root.isHidden())
        self.finish_loading()
        self.assertFalse(compass.root.isHidden())
        self.assertEqual(compass.target['kind'], 'altar')
        app.trigger_game_over(reason='timeout')
        self.assertTrue(compass.root.isHidden())
        app.return_to_intro()
        self.assertTrue(compass.root.isHidden())

    def test_timeout_record_is_isolated_and_written_once(self):
        app = self.app
        previous = len(app.ui_mgr.load_rankings())
        app.time_left = 0.001
        app.update(None)
        self.assertEqual(app.game_state, 'GAME_OVER')
        for _ in range(3):
            app.update(None)
        data = json.loads(Path(app.ui_mgr.rank_file).read_text(encoding='utf-8'))
        self.assertEqual(len(data), previous + 1)
        self.assertEqual(data[-1]['time_left'], 0)
        self.assertFalse(data[-1]['success'])

    def test_loading_can_be_cancelled_and_started_again(self):
        app = self.app
        app.return_to_intro()
        app.start_game()
        app.taskMgr.step()
        app.taskMgr.step()
        self.assertEqual(app.game_state, 'LOADING')
        app.return_to_intro()
        self.assertFalse(app.taskMgr.hasTaskNamed('loading_process_task'))
        for _ in range(3):
            app.taskMgr.step()
        self.assertEqual(app.game_state, 'INTRO')
        app.start_game()
        self.finish_loading()
        self.assertEqual(app.current_stage, 1)

    def test_floor_themes_match_actual_spawns_and_reset_on_new_game(self):
        app = self.app
        expected_floors = (
            (2, "미로의 심연", (2, 3, 3, 1, 1)),
            (3, "진흙의 파수대", (2, 4, 3, 1, 2)),
            (4, "잿불의 회랑", (2, 3, 5, 3, 1)),
            (5, "그림자 사냥터", (5, 3, 3, 4, 1)),
            (6, "진흙의 파수대", (2, 7, 4, 1, 4)),
        )
        names = ('ShadowStalker', 'AbominableMudOrc', 'AlluringAshWitch',
                 'LongBlackSerpent', 'TallSkeletonMonster')
        for stage, title, counts in expected_floors:
            with self.subTest(stage=stage):
                self.activate_altars_and_enter_gate()
                old_nodes = [m.node for m in app.monsters]
                app.ui_mgr._confirm_shop_and_start()
                self.assertIn(title, app.ui_mgr.loading_badge_text.getText())
                self.assertIn('TIP:', app.ui_mgr.loading_tip_text.getText())
                self.finish_loading()
                self.assertEqual(app.current_stage, stage)
                self.assertEqual(Counter(type(m).__name__ for m in app.monsters),
                                 dict(zip(names, counts)))
                self.assertIn(title, app.ui_mgr.stage_clear_banner.getText())
                self.assertFalse(app.ui_mgr.stage_clear_banner.isHidden())
                self.assertTrue(all(node.isEmpty() for node in old_nodes))
                self.assertEqual(app.activated_altars_count, 0)
                self.assertFalse(app.escape_gate['opened'])

        app.return_to_intro()
        app.start_game()
        self.assertIn('첫 번째 악몽', app.ui_mgr.loading_badge_text.getText())
        self.finish_loading()
        self.assertEqual(len(app.monsters), 7)
        self.assertIn('첫 번째 악몽', app.ui_mgr.stage_clear_banner.getText())


class ResourceLifecycle(unittest.TestCase):
    def test_running_chunk_is_disposed_after_cancellation_request(self):
        queued, running, completed = Future(), Future(), Future()
        running.set_running_or_notify_cancel()
        old_chunk, late_chunk = Mock(), Mock()
        completed.set_result(old_chunk)
        app = SimpleNamespace(active_chunk_futures={(0, 0): queued, (1, 0): running, (2, 0): completed})
        LiminalInfiniteLoop._discard_pending_chunks(app)
        self.assertTrue(queued.cancelled())
        self.assertEqual(app.active_chunk_futures, {})
        old_chunk.destroy.assert_called_once()
        running.set_result(late_chunk)
        late_chunk.destroy.assert_called_once()

    def test_monster_audio_is_stopped_and_detached(self):
        audio = AudioManager.__new__(AudioManager)
        audio.audio3d = Mock()
        sounds = [Mock() for _ in range(4)]
        names = ('serpent_slither_sfx', 'serpent_hiss_sfx', 'skeleton_rattle_sfx', 'skeleton_groan_sfx')
        for name, sound in zip(names, sounds):
            setattr(audio, name, sound)
        audio.detach_monsters()
        audio.detach_monsters()
        self.assertEqual(audio.audio3d.detachSound.call_count, 4)
        for name, sound in zip(names, sounds):
            sound.stop.assert_called_once()
            self.assertIsNone(getattr(audio, name))


if __name__ == '__main__':
    unittest.main()
