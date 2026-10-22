"""Exercise the production game, director, boss and HUD without a live match."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type offscreen\naudio-library-name null\nsync-video false')
from game import LiminalInfiniteLoop

app = LiminalInfiniteLoop()
try:
    app.game_state = 'PLAYING'
    app.current_stage = 1
    app.camera.setPos(0, 0, 1.7)
    app.player.hp = app.player.max_hp = 100000
    boss = app.spawn_boss(0, 8)
    states = set()
    patterns = set()
    with patch.object(app.monster_director.gate_wave_mgr, 'update'), \
            patch.object(app, 'spawn_reinforcement_monster'):
        for frame in range(1800):
            if frame == 900:
                boss.take_damage(2000)
            app.monster_director.update_monsters(1/60, 0, 0)
            app.ui_mgr._animate_boss_hp(1/60)
            states.add(boss.pattern_controller.state)
            if boss.pattern_controller.current_pattern:
                patterns.add(boss.pattern_controller.current_pattern)
        assert {'IDLE', 'TELEGRAPH', 'ACTIVE', 'RECOVERY'} <= states, states
        assert len(patterns) >= 2, patterns
        assert boss.phase == 2
        assert abs(app.ui_mgr.boss_bar_fill.getSx()-boss.hp/boss.max_hp) < 1e-4
        boss.hp = 0
        app.monster_director.update_monsters(1/60, 0, 0)
        assert app.boss_defeat_handled
        assert boss not in app.monsters
        assert not boss.pattern_controller.indicators
        assert not boss.pattern_controller.bone_spikes
        print('PASS: production director ran 30 seconds, repeated patterns:', sorted(patterns))
        print('PASS: phase 2, animated HUD, death and cleanup.')
finally:
    if app.boss:
        app.boss.destroy()
    app.destroy()
