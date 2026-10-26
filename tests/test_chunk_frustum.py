import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath, Camera, PerspectiveLens, BoundingSphere, Point3
from lighting_manager import LightingManager


class ChunkFrustumTests(unittest.TestCase):
    def test_turning_and_fov_restore_hidden_chunks_without_unloading(self):
        root = NodePath('world')
        lens = PerspectiveLens()
        lens.setFov(60, 45)
        lens.setNearFar(.1, 100)
        cam = root.attachNewNode(Camera('camera', lens))
        chunks = {}
        for key, pos, radius in (((0, 0), (0, 20, 0), 2),
                                 ((0, -1), (0, -20, 0), 2),
                                 ((1, 0), (14, 20, 0), 1),
                                 ((-1, 0), (-14, 20, 0), 5)):
            node = root.attachNewNode('chunk')
            node.node().setBounds(BoundingSphere(Point3(*pos), radius))
            node.node().setFinal(True)
            chunk = SimpleNamespace(node=node, visible=True, colliders=[(1, 2, 3, 4)])
            def visible(value, c=chunk):
                c.visible = value
                c.node.show() if value else c.node.hide()
            chunk.set_visible = Mock(side_effect=visible)
            chunks[key] = chunk
        game = SimpleNamespace(world_root=root, camera=cam, cam=cam, camLens=lens, chunks=chunks)
        mgr = LightingManager(game)
        try:
            mgr.cull_chunks_to_view()
            self.assertTrue(chunks[0, 0].visible)
            self.assertFalse(chunks[0, -1].visible)
            self.assertFalse(chunks[1, 0].visible)
            self.assertTrue(chunks[-1, 0].visible)  # Edge intersects; centre outside.
            mgr.cull_chunks_to_view()
            self.assertEqual(chunks[0, 0].set_visible.call_count, 1)
            mgr.cull_chunks_to_view(force=True)
            self.assertEqual(chunks[0, 0].set_visible.call_count, 2)
            saved = chunks.pop((1, 0))
            mgr.cull_chunks_to_view()
            self.assertEqual(game.total_chunk_count, 3)
            chunks[1, 0] = saved
            mgr.cull_chunks_to_view()
            self.assertEqual(game.total_chunk_count, 4)
            lens.setFov(100, 65)
            mgr.cull_chunks_to_view()
            self.assertTrue(chunks[1, 0].visible)
            cam.setH(180)
            mgr.cull_chunks_to_view()
            self.assertTrue(chunks[0, -1].visible)
            self.assertFalse(chunks[0, 0].visible)
            self.assertEqual(len(game.chunks), 4)
            self.assertEqual(chunks[0, 0].colliders, [(1, 2, 3, 4)])
        finally:
            root.removeNode()
