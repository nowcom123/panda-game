import unittest
from panda3d.core import NodePath, Vec3, GeomVertexReader
from combat_system import CombatSystem
from combat.tracer_effects import update_tracers


class TracerReuseTests(unittest.TestCase):
    def test_flight_impact_fade_cleanup_and_list_identity(self):
        root = NodePath('lifecycle')
        tracers = [dict(life=1, phase='fly', speed=100, traveled=0, total_dist=1,
                        start=Vec3(0), end=Vec3(0, 1, 0), dir=Vec3(0, 1, 0))
                   for _ in range(3)]
        original_list = tracers
        try:
            update_tracers(tracers, root, .02)
            self.assertTrue(all(tr['phase'] == 'fade' for tr in tracers))
            self.assertEqual(root.getNumChildren(), 12)
            tracers[1]['fade_timer'] = .08
            tracers[0]['fade_timer'] = tracers[2]['fade_timer'] = .01
            survivor = tracers[1]
            update_tracers(tracers, root, .02)
            self.assertIs(tracers, original_list)
            self.assertEqual(tracers, [survivor])
            update_tracers(tracers, root, .1)
            self.assertFalse(tracers)
            self.assertEqual(root.getNumChildren(), 0)
        finally:
            root.removeNode()

    def test_nodes_reused_and_rendered_endpoints_updated(self):
        combat = CombatSystem.__new__(CombatSystem)
        combat.world_root = NodePath('tracer_test')
        tr = {}
        try:
            combat._update_tracer_lines(tr, Vec3(0), Vec3(0, 1, 0))
            nodes = [tr[k].node() for k in ('core', 'glow', 'halo')]
            for i in range(120):
                combat._update_tracer_lines(tr, Vec3(1, 2, 3), Vec3(4, 8, 6))
            self.assertEqual(combat.world_root.getNumChildren(), 3)
            for index, key in enumerate(('core', 'glow', 'halo')):
                self.assertEqual(tr[key].node(), nodes[index])
                reader = GeomVertexReader(tr[key].node().getGeom(0).getVertexData(), 'vertex')
                start = reader.getData3f()
                end = reader.getData3f()
                inset = (0, .15, .35)[index]
                self.assertLess((start-(Vec3(1, 2, 3)+Vec3(3, 6, 3)*inset)).length(), 1e-5)
                self.assertLess((end-Vec3(4, 8, 6)).length(), 1e-5)
        finally:
            combat.world_root.removeNode()
