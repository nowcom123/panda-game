"""Render actual frames with streaming, moving tracers and repeated shutdown."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from panda3d.core import loadPrcFileData, Vec3
loadPrcFileData('', 'window-type offscreen\naudio-library-name null')
from game import LiminalInfiniteLoop

app = LiminalInfiniteLoop()
try:
    app.game_state = 'SHOP'  # Avoid match progression and ranking writes.
    for frame in range(600):
        app.camera.setH(frame * 1.2)
        if frame % 100 == 0:
            app.camera.setX((frame // 100 % 3) * 24)
            app.update_chunks()
        app._mount_async_chunks()
        app.cull_chunks_to_view()
        origin = app.camera.getPos(app.world_root)
        app.render.setShaderInput('camera_world_position', app.camera.getPos(app.render))
        if frame % 4 == 0:
            app.combat._spawn_tracer_effect(origin, origin + Vec3(0, 20, 0),
                                            Vec3(0, 1, 0), 20, False)
        app.combat.update(1 / 60)
        app.taskMgr.step()
    print('PASS: 600 rendered frames, streaming, culling and dynamic tracers')
finally:
    app.destroy()
    app.destroy()
print('PASS: worker completion and repeated shutdown')
