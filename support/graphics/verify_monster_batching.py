"""Compare rendered model appearance before/after geometry and tint batching."""
import random
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from monster import (LongBlackSerpent, TallSkeletonMonster, AbominableMudOrc,
                     AlluringAshWitch, SkeletalDobermanHellhound)
from panda3d.core import (loadPrcFileData, AmbientLight, OrthographicLens,
                         PNMImage, Filename)
loadPrcFileData('', 'window-type offscreen\nwin-size 384 384\naudio-library-name null')
from direct.showbase.ShowBase import ShowBase

app = ShowBase()
app.disableMouse()
app.setBackgroundColor(.08, .08, .08)
light = AmbientLight('comparison_light')
light.setColor((1, 1, 1, 1))
app.render.setLight(app.render.attachNewNode(light))
lens = OrthographicLens()
lens.setNearFar(.1, 200)
app.cam.node().setLens(lens)
out = Path(__file__).resolve().parent / 'performance_results'
out.mkdir(exist_ok=True)
try:
    for kind in (LongBlackSerpent, TallSkeletonMonster, AbominableMudOrc,
                 AlluringAshWitch, SkeletalDobermanHellhound):
        with patch('monster.optimize_monster_geometry'), \
                patch('monster.group_shared_tint', side_effect=lambda nodes: nodes):
            random.seed(123)
            original = kind(app.render, 0, 0)
        random.seed(123)
        optimized = kind(app.render, 0, 0)
        original.update(.016, True)
        optimized.update(.016, True)
        lo, hi = original.node.getTightBounds()
        center = (lo+hi)*.5
        span = max(hi.x-lo.x, hi.y-lo.y, hi.z-lo.z)*1.6
        lens.setFilmSize(span, span)
        app.camera.setPos(center.x+12, center.y-20, center.z+8)
        app.camera.lookAt(center)
        images = []
        for shown, hidden, suffix in ((original, optimized, 'before'),
                                       (optimized, original, 'after')):
            shown.node.show()
            hidden.node.hide()
            for _ in range(3):
                app.graphicsEngine.renderFrame()
            img = PNMImage()
            app.win.getScreenshot(img)
            img.write(Filename.fromOsSpecific(str(out / f'{kind.__name__}_{suffix}.png')))
            images.append(img)
        error = 0
        for y in range(images[0].getYSize()):
            for x in range(images[0].getXSize()):
                delta = images[0].getXel(x, y) - images[1].getXel(x, y)
                error += abs(delta.x)+abs(delta.y)+abs(delta.z)
        mean_error = error / (384*384*3)
        print(f'{kind.__name__}: mean RGB difference {mean_error:.8f}')
        assert mean_error < .002, (kind.__name__, mean_error)
        original.destroy()
        optimized.destroy()
finally:
    app.destroy()
