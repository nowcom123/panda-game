import unittest
from panda3d.core import NodePath, Vec3
from casing_effects import CasingEffects
from combat_system import CombatSystem


class CasingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.scene = NodePath('scene')
        self.combat = CombatSystem.__new__(CombatSystem)
        self.combat.world_root = self.scene.attachNewNode('world')
        self.combat.world_root.setPos(10, -7, 0)
        self.combat.world_root.setH(37)
        camera = self.scene.attachNewNode('camera')
        camera.setPos(20, 30, 1.7)
        camera.setHpr(80, 15, 0)
        for name in ('recoil_node', 'dual_left_recoil', 'dual_right_recoil',
                     'ar_recoil_node', 'sg_recoil_node'):
            node = camera.attachNewNode(name)
            node.setPos(.18, .65, -.2)
            node.setHpr(1, 5, -.6)
            setattr(self.combat, name, node)
        self.combat.casing_effects = CasingEffects(self.combat.world_root)

    def tearDown(self):
        self.combat.casing_effects.destroy()
        self.scene.removeNode()

    def test_all_ports_use_weapon_transform_in_world_root_space(self):
        cases = (
            ('PISTOL', 'recoil_node', (.040, .040, .055)),
            ('AR', 'ar_recoil_node', (.042, .050, .038)),
            ('SHOTGUN', 'sg_recoil_node', (.045, .040, .035)),
        )
        for weapon, name, port in cases:
            with self.subTest(weapon=weapon):
                self.combat.current_weapon = weapon
                self.combat._eject_casing(is_shotgun=weapon == 'SHOTGUN')
                node = getattr(self.combat, name)
                slot = self.combat.casing_effects.pool[self.combat.casing_effects.cursor - 1]
                expected = self.combat.world_root.getRelativePoint(node, Vec3(*port))
                self.assertLess((slot['pos'] - expected).length(), 1e-5)
                local_velocity = node.getRelativeVector(self.combat.world_root, slot['vel'])
                self.assertGreater(local_velocity.x, 0)
                self.assertEqual(slot['current_weapon'], weapon)

    def test_dual_casings_eject_outward_from_the_firing_hand(self):
        self.combat.current_weapon = 'DUAL_PISTOL'
        for left in (False, True):
            self.combat._eject_casing(is_left=left)
            slot = self.combat.casing_effects.pool[self.combat.casing_effects.cursor - 1]
            node = self.combat.dual_left_recoil if left else self.combat.dual_right_recoil
            local_velocity = node.getRelativeVector(self.combat.world_root, slot['vel'])
            self.assertGreater(local_velocity.x * (-1 if left else 1), 0)
            local_position = node.getRelativePoint(self.combat.world_root, slot['pos'])
            self.assertAlmostEqual(local_position.x, -.030 if left else .030, places=4)


if __name__ == '__main__':
    unittest.main()
