"""Verify the settings toggle and its independence from bullet time on the GPU."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from panda3d.core import loadPrcFileData, Filename, PNMImage
loadPrcFileData('', 'window-type offscreen\nwin-size 1280 720\naudio-library-name null\nsync-video false')
from game import LiminalInfiniteLoop

app = LiminalInfiniteLoop()
out = Path(__file__).resolve().parent
try:
    with patch.object(app.player, 'lock_mouse'):
        app.start_test_mode()
    app.camera.setPos(0, -5, 1.7)
    app.camera.setHpr(0, -8, 0)
    app.combat.switch_weapon('AR')
    app.combat.update(.1)
    app.ui_mgr.hide_stage_banner()
    pipe = app.pbr_pipeline
    pipe._update(SimpleNamespace(DS_cont=1))

    def capture(name):
        for _ in range(3):
            app.graphicsEngine.renderFrame()
        assert not pipe._post_process_quad.getShader().getErrorFlag()
        shot = PNMImage()
        assert app.win.getScreenshot(shot)
        shot.write(Filename.fromOsSpecific(str(out / name)))
        return shot

    assert not pipe.sharpening_enabled
    normal = capture('sharpening_off.png')
    app.trigger_bullet_time(3)
    # Keep identical UI for an isolated sharpening comparison.
    app.ui_mgr.set_bullet_time_hud(False)
    pipe._update(SimpleNamespace(DS_cont=1))
    assert not pipe.sharpening_enabled
    unsharpened = capture('bullet_time_no_sharpening.png')
    assert all(normal.getXel(x, y) == unsharpened.getXel(x, y)
               for y in range(normal.getYSize()) for x in range(normal.getXSize()))
    app.ui_mgr.btn_sharpening['command']()
    assert pipe.sharpening_enabled
    active = capture('sharpening_on.png')
    changed = 0
    for y in range(normal.getYSize()):
        for x in range(normal.getXSize()):
            if (normal.getXel(x, y)-active.getXel(x, y)).length() > .01:
                changed += 1
    assert changed > 3000, changed
    app.bullet_time_timer = 0
    pipe._update(SimpleNamespace(DS_cont=1))
    assert pipe.sharpening_enabled
    app.ui_mgr.show_pause_menu(player=app.player, combat=app.combat, audio_mgr=app.audio_mgr)
    capture('sharpening_settings.png')
    app.ui_mgr.hide_pause_menu()
    app.ui_mgr.btn_sharpening['command']()
    assert not pipe.sharpening_enabled
    app.ui_mgr.set_bullet_time_hud(False)
    restored = capture('sharpening_restored.png')
    assert all(normal.getXel(x, y) == restored.getXel(x, y)
               for y in range(normal.getYSize()) for x in range(normal.getXSize()))
    # Pipeline rebuild must preserve the effect and use the augmented shader.
    pipe.set_sharpening(True)
    pipe.msaa_samples = 0
    assert pipe.sharpening_enabled
    capture('sharpening_rebuilt.png')
    pipe.set_sharpening(False)
    assert not pipe.sharpening_enabled
    print(f'PASS: GPU shaders, {changed} changed scene pixels, settings toggle, bullet-time independence, exact restoration, pipeline rebuild.')
finally:
    app.destroy()
