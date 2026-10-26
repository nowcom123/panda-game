"""Exercise real game objects and combat paths with isolated persistence."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from game import LiminalInfiniteLoop
from panda3d.core import loadPrcFileData, Vec3, PNMImage, Filename
from monster import (LongBlackSerpent, TallSkeletonMonster, AlluringAshWitch,
                     AbominableMudOrc, SkeletalDobermanHellhound, CableOverlordBoss)

loadPrcFileData('', 'window-type offscreen\nwin-size 1280 720\naudio-library-name null\nsync-video false')

with tempfile.TemporaryDirectory() as tmp:
    app = LiminalInfiniteLoop(save_path=Path(tmp) / 'profile.json')
    spawned = []
    try:
        app.ui_mgr.save_rank_record = lambda *a, **k: None
        app.start_game()
        app.taskMgr.remove('update_task')
        p, c, q = app.player, app.combat, app.quick_use_mgr
        p.camera.setPos(0, 0, 1.7)
        p.camera.setHpr(0, 0, 0)
        p.hp = 50
        app.bullet_time_timer = 2.5
        count = p.get_item_count('medkit')
        q.on_key_down()
        assert q.is_open and q.selected_index == -1
        q.on_key_up()
        assert p.get_item_count('medkit') == count
        q.on_key_down()
        q.on_key_down()
        q.select_next()
        q.on_key_up()
        q.on_key_up()
        assert p.get_item_count('medkit') == count - 1
        assert app.bullet_time_timer == 2.5
        q.on_key_down()
        q.select_next()
        app.game_state = 'GAME_OVER'
        q.on_key_up()
        assert p.get_item_count('medkit') == count - 1
        assert not p.mouse_locked
        app.game_state = 'PLAYING'
        q.on_key_down()
        q.on_window_event(SimpleNamespace())  # unrelated window ignored
        q.cancel()
        p.hp = 100
        p.invincible_timer = .5
        p.take_damage(4, damage_type='dot')
        assert p.hp == 96 and p.invincible_timer == .5
        p.apply_poison(duration=.001, dps=4)
        hp = p.hp
        with patch.object(app, '_update_monsters', return_value=(False, 100)), patch.object(app, '_update_projectiles', return_value=False):
            app.update(SimpleNamespace(cont='cont'))
        assert 0 <= hp - p.hp <= .00401, 'poison exceeded remaining duration'
        print('PASS real quick-use consumption, cancellation, state changes, DOT API')

        for cls in (LongBlackSerpent, TallSkeletonMonster, AlluringAshWitch,
                    AbominableMudOrc, SkeletalDobermanHellhound, CableOverlordBoss):
            m = cls(app.render, 0, 5)
            spawned.append(m)
            m.hp = m.max_hp = 10000
            m.is_hit_by_ray = lambda *args: (True, 5.0)
            c._discharge_reactions = {}
            c._shotgun_close_hits = {}
            before = m.hp
            with patch('combat_system.raycast_walls', return_value=(100, None)), patch('combat_system.random.random', return_value=1):
                c._perform_raycast(Vec3(0, 1, 0), Vec3(0, 0, 1.7), [m], p, [], False, c.get_current_weapon_config())
            assert m.hp < before, cls.__name__
            print('PASS actual raycast damage', cls.__name__)

        for m in spawned[:5]:
            m.stun_timer = 0
            m.node.setH(180)
            m.reaction_cooldown = 0
            if m.reaction_role in ('serpent', 'golem'):
                with patch('combat_system.random.random', return_value=0):
                    first = c._resolve_monster_reaction(m, Vec3(0, 1, 0), p)
                assert first['blocked']
                again = c._resolve_monster_reaction(m, Vec3(0, 1, 0), p)
                assert again['blocked'], 'guard lost while counter pending'
                assert not c._resolve_monster_reaction(m, Vec3(0, -1, 0), p)['blocked']
                p.invincible_timer = 0
                p.hp = 100
                with patch('monster.raycast_walls', return_value=(100, None)):
                    m.update_reactions(2, app, 0, 0, 1.7)
                assert p.hp < 100, m.reaction_role
                hp = p.hp
                m.update_reactions(2, app, 0, 0, 1.7)
                assert p.hp == hp, 'duplicate counter'
            else:
                with patch('combat_system.random.random', return_value=0), patch('monster.resolve_collision', side_effect=lambda ch,x,y,*a,**k:(x,y)), patch('monster.raycast_walls', return_value=(100, None)):
                    result = c._resolve_monster_reaction(m, Vec3(0, 1, 0), p)
                assert result['dodged'], m.reaction_role
                app.monsters = [m]
                with patch.object(app.monster_director.gate_wave_mgr, 'update'):
                    app.monster_director.update_monsters(.1, 0, 0, raw_dt=.1)
                assert m.is_dodging
                m.update_reactions(.6, app, 0, 0, 1.7)
                if m.reaction_role != 'hound':
                    assert not m.is_dodging
            print('PASS active reaction', m.reaction_role)
        from combat.weapon_config import WEAPON_CONFIGS
        guard = spawned[0]
        guard.is_guarding = guard.counter_pending = False
        guard.reaction_cooldown = guard.stun_timer = 0
        c.shoot_cooldown = 0
        c.is_reloading = False
        c._suppress_fire_until_release = False
        c.ammo = 8
        with patch.object(c, 'get_current_weapon_config', return_value=WEAPON_CONFIGS['SHOTGUN']), patch('combat_system.raycast_walls', return_value=(100, None)), patch('combat_system.random.random', return_value=0), patch.object(c, '_resolve_monster_reaction', wraps=c._resolve_monster_reaction) as resolver, patch.object(guard, 'trigger_guard', wraps=guard.trigger_guard) as reaction:
            c.shoot([guard], player=p)
            assert resolver.call_count == 1, resolver.call_count
            assert reaction.call_count == 1, reaction.call_count
        print('PASS actual shotgun discharge: one reaction for all pellets')
        print('REVIEW INTEGRATION PASS')
    finally:
        app.monsters = []
        for m in spawned:
            m.destroy()
        app.destroy()
