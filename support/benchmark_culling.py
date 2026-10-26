"""CPU-only culling microbenchmark; this does not measure gameplay FPS."""
import sys
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panda3d.core import NodePath, Camera, PerspectiveLens, BoundingSphere, Point3
from constants import CHUNK_SIZE
from lighting_manager import LightingManager


def main():
    root = NodePath('benchmark')
    lens = PerspectiveLens()
    lens.setFov(96, 60)
    lens.setNearFar(.15, 65)
    cam = root.attachNewNode(Camera('camera', lens))
    chunks = {}
    for x in range(-4, 5):
        for y in range(-4, 5):
            node = root.attachNewNode('chunk')
            node.node().setBounds(BoundingSphere(
                Point3((x+.5)*CHUNK_SIZE, (y+.5)*CHUNK_SIZE, 3), CHUNK_SIZE*.72))
            node.node().setFinal(True)
            chunks[x, y] = SimpleNamespace(node=node,
                set_visible=lambda visible, n=node: n.show() if visible else n.hide())
    game = SimpleNamespace(world_root=root, camera=cam, cam=cam, camLens=lens, chunks=chunks)
    manager = LightingManager(game)
    try:
        for name, force, rotate in (('stationary forced', True, False),
                                    ('stationary cached', False, False),
                                    ('rotating cached', False, True)):
            manager.reset_cull_cache()
            started = perf_counter()
            for frame in range(2000):
                if rotate:
                    cam.setH(frame*.1)
                manager.cull_chunks_to_view(force=force)
            print(f'{name}: {(perf_counter()-started)*1000:.2f} ms / 2000 calls, 81 chunks')
    finally:
        root.removeNode()


if __name__ == '__main__':
    main()
