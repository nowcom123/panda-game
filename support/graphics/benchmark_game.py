"""Repeatable offscreen frame benchmark; render time includes CPU submission/GPU waits.

Run each case in a separate process. No FPS cap, no audio device, fixed simulation
dt, seeded mixed enemies, stationary player and rotating view. Not live-match FPS.
"""
import argparse
import cProfile
import json
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter, process_time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
parser = argparse.ArgumentParser()
parser.add_argument('--width', type=int, default=1600)
parser.add_argument('--enemies', type=int, default=20)
parser.add_argument('--frames', type=int, default=600)
parser.add_argument('--profile', action='store_true')
parser.add_argument('--hide-enemies', action='store_true')
parser.add_argument('--label', default='')
args = parser.parse_args()
from panda3d.core import loadPrcFileData, ClockObject, Filename
from game import LiminalInfiniteLoop
from monster import (TallSkeletonMonster, SkeletalDobermanHellhound,
                     AbominableMudOrc, AlluringAshWitch, LongBlackSerpent)
from world_gen import cell_has_pillar
from constants import CELL_SIZE

loadPrcFileData('', f'window-type offscreen\nwin-size {args.width} {args.width*9//16}\n'
                   'audio-library-name null\nsync-video false\nclock-mode non-real-time')
random.seed(20261024)
app = LiminalInfiniteLoop()
out = Path(__file__).resolve().parent / 'performance_results'
out.mkdir(exist_ok=True)
tag = f'{args.width}_{args.enemies}'
if args.hide_enemies:
    tag += '_hidden'
if args.label:
    tag += '_' + args.label
try:
    app.start_game()
    app.player.mouse_locked = False
    app.player.hp = app.player.max_hp = 1000000
    app.time_left = 100000
    app.escape_pos = (1000, 1000)
    app.monster_director.gate_wave_mgr.update = lambda *a, **kw: None
    app.spawn_reinforcement_monster = lambda *a, **kw: None
    for monster in app.monsters:
        monster.destroy()
    app.monsters.clear()
    app.player.reset_position(0, 0)
    kinds = (TallSkeletonMonster, SkeletalDobermanHellhound, AbominableMudOrc,
             AlluringAshWitch, LongBlackSerpent)
    cells = [(x, y) for x in range(-4, 5) for y in range(-4, 5)
             if x*x+y*y >= 4 and not cell_has_pillar(x, y)]
    for i in range(args.enemies):
        x, y = cells[i % len(cells)]
        app.monsters.append(kinds[i % len(kinds)](
            app.world_root, (x+.5)*CELL_SIZE, (y+.5)*CELL_SIZE))
        if args.hide_enemies:
            app.monsters[-1].node.hide()
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setDt(1/60)
    current = {}
    samples = {}

    def wrap(obj, name, label):
        original = getattr(obj, name)
        def measured(*a, **kw):
            start = perf_counter()
            try:
                return original(*a, **kw)
            finally:
                current[label] = current.get(label, 0) + (perf_counter()-start)*1000
        setattr(obj, name, measured)

    for obj, name, label in (
        (app, 'update', 'game_update'),
        (app, '_update_monsters', 'enemy_ai_animation'),
        (app, '_update_projectiles', 'projectiles'),
        (app, 'cull_chunks_to_view', 'chunk_culling'),
        (app, '_update_dynamic_lights', 'lights'),
        (app.player, 'update', 'player'),
        (app.combat, 'update', 'weapon_effects'),
        (app.ui_mgr, 'update', 'ui_update'),
    ):
        wrap(obj, name, label)
    app.taskMgr.remove('update_task')
    app.taskMgr.add(app.update, 'update_task')
    profiler = cProfile.Profile()
    for frame in range(args.frames + 120):
        app.player.heading = frame * .6
        app.camera.setH(frame * .6)
        current.clear()
        if args.profile and frame == 120:
            profiler.enable()
        start = perf_counter()
        cpu_start = process_time()
        app.taskMgr.step()
        elapsed = (perf_counter()-start)*1000
        assert app.game_state == 'PLAYING', app.game_state
        if frame >= 120:
            current['frame'] = elapsed
            current['process_cpu'] = (process_time()-cpu_start)*1000
            current['other_tasks_render_wait'] = elapsed-current.get('game_update', 0)
            for key, value in current.items():
                samples.setdefault(key, []).append(value)
    if args.profile:
        profiler.disable()
        profiler.dump_stats(str(out / f'{tag}.prof'))
    def stats(values):
        ordered = sorted(values)
        return dict(mean_ms=round(statistics.mean(values), 3),
                    p95_ms=round(ordered[int(.95*(len(ordered)-1))], 3),
                    p99_ms=round(ordered[int(.99*(len(ordered)-1))], 3),
                    max_ms=round(max(values), 3))
    result = dict(renderer=app.win.getGsg().getDriverRenderer(),
                  size=[app.win.getXSize(), app.win.getYSize()], enemies=len(app.monsters),
                  chunks=len(app.chunks), frames=args.frames, profiled=args.profile,
                  enemies_hidden=args.hide_enemies,
                  enemy_geom_nodes=sum(m.node.findAllMatches('**/+GeomNode').getNumPaths()
                                       for m in app.monsters),
                  timings={key: stats(values) for key, values in samples.items()})
    (out / f'{tag}{"_profiled" if args.profile else ""}.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')
    if args.enemies == 80 and args.width == 1600:
        app.win.saveScreenshot(Filename.fromOsSpecific(str(out / f'{tag}_scene.png')))
    print(json.dumps(result))
finally:
    app.destroy()
