"""GPU regression: bullet time must not crush readable shadows to black."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from panda3d.core import CardMaker, Filename, OrthographicLens, PNMImage, loadPrcFileData
loadPrcFileData('', 'window-type offscreen\nwin-size 1280 720\naudio-library-name null\nsync-video false')
from game import LiminalInfiniteLoop

app = LiminalInfiniteLoop()
out = Path(__file__).resolve().parent
try:
    app.world_root.hide()
    app.combat.vm_root.hide()
    for child in app.aspect2d.getChildren():
        child.hide()
    lens = OrthographicLens()
    lens.setFilmSize(5, 3)
    app.cam.node().setLens(lens)
    app.camera.setPos(0, -5, 0)
    app.camera.setHpr(0, 0, 0)
    scene = app.render.attachNewNode('shadow_visibility_chart')
    scene.setShaderOff(100)
    scene.setLightOff(100)
    for i, gray in enumerate((.02, .04, .08, .18, .45)):
        card = CardMaker(f'shadow_{gray}')
        card.setFrame(-2.5+i, -1.5+i, -1, 1)
        tile = scene.attachNewNode(card.generate())
        tile.setColor(gray, gray, gray, 1)
    pipe = app.pbr_pipeline
    pipe._update(SimpleNamespace(DS_cont=1))

    def capture(name):
        for _ in range(3):
            app.graphicsEngine.renderFrame()
        assert not pipe._post_process_quad.getShader().getErrorFlag()
        image = PNMImage()
        assert app.win.getScreenshot(image)
        image.write(Filename.fromOsSpecific(str(out / name)))
        return image

    normal = capture('bullet_time_visibility_normal.png')
    for strength, elapsed in ((.1, .01), (1., .1), (1., 1.0), (.1, 2.9)):
        pipe.set_bullet_time(strength)
        app.ui_mgr.set_bullet_time_hud(True, 3-elapsed, strength, elapsed)
        assert app.ui_mgr.vignette_bullet_time.isHidden()
        active = capture('bullet_time_visibility_active.png')
        for i in range(5):
            x, y = int(normal.getXSize()*(i+.5)/5), normal.getYSize()//2
            before = normal.getXel(x, y)
            after = active.getXel(x, y)
            luma = lambda c: c.x*.2126+c.y*.7152+c.z*.0722
            assert luma(before) > .01
            assert luma(after) >= luma(before)*.97, (strength, i, before, after)
    pipe.set_bullet_time(0)
    app.ui_mgr.set_bullet_time_hud(False)
    restored = capture('bullet_time_visibility_restored.png')
    for i in range(5):
        x, y = int(normal.getXSize()*(i+.5)/5), normal.getYSize()//2
        assert restored.getXel(x, y) == normal.getXel(x, y)
    print('PASS: five shadow/brightness levels preserved through entry, active, exit; dark overlay hidden; original pixels restored.')
finally:
    app.destroy()
