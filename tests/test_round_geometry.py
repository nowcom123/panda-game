import unittest
from panda3d.core import GeomVertexReader, NodePath
from geometry import _get_round_mesh, make_sphere_to, make_cylinder_to


class RoundGeometryTests(unittest.TestCase):
    def test_faces_are_non_degenerate_and_face_outward(self):
        for shape in ('sphere', 'cylinder'):
            for axis in ('x', 'y', 'z'):
                with self.subTest(shape=shape, axis=axis):
                    node = _get_round_mesh(shape, axis)
                    self.assertEqual(node, _get_round_mesh(shape, axis))
                    geom = node.node().getGeom(0)
                    reader = GeomVertexReader(geom.getVertexData(), 'vertex')
                    points = []
                    while not reader.isAtEnd():
                        points.append(reader.getData3())
                    primitive = geom.getPrimitive(0).decompose()
                    self.assertEqual(primitive.getNumPrimitives(), 224 if shape == 'sphere' else 64)
                    for i in range(primitive.getNumPrimitives()):
                        start = primitive.getPrimitiveStart(i)
                        a, b, c = [points[primitive.getVertex(start + j)] for j in range(3)]
                        self.assertGreater((b - a).cross(c - a).dot(a + b + c), 1e-6)

    def test_round_shapes_preserve_dimensions_and_independent_transforms(self):
        root = NodePath('test')
        for factory in (make_sphere_to, make_cylinder_to):
            node = factory(root, 2, 4, 6, (1, 1, 1, 1), 3, 5, 7)
            low, high = node.getTightBounds(root)
            self.assertTrue((high - low).almostEqual((2, 4, 6), 1e-5))
            self.assertTrue(((high + low) / 2).almostEqual((3, 5, 7), 1e-5))
            node.removeNode()
        first = make_sphere_to(root, 1, 1, 1, (1, 0, 0, 1), 0, 0, 0)
        second = make_sphere_to(root, 1, 1, 1, (0, 1, 0, 1), 2, 0, 0)
        first.setScale(2)
        self.assertEqual(second.getScale().x, 1)


if __name__ == '__main__':
    unittest.main()
