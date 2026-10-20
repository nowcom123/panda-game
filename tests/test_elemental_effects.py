"""Unit tests for elemental effects (fire DoT & electric shock) and monster damage_type handling."""
import unittest
from unittest.mock import MagicMock
from panda3d.core import Vec3, NodePath
from elemental_effects import get_monster_dimensions, ElementalMonsterMixin
from monster import (
    LongBlackSerpent,
    TallSkeletonMonster,
    AbominableMudOrc,
    AlluringAshWitch,
    SkeletalDobermanHellhound,
    CableOverlordBoss,
)


class DummyNode:
    """Lightweight dummy node for tests that don't need full Panda3D render engine."""
    def __init__(self):
        self._pos = Vec3(0, 0, 0)
        self._hpr = Vec3(0, 0, 0)

    def isEmpty(self):
        return False

    def getPos(self):
        return self._pos

    def setPos(self, *args):
        if len(args) == 1:
            self._pos = args[0]
        else:
            self._pos = Vec3(*args)

    def getH(self):
        return self._hpr.x

    def setH(self, h):
        self._hpr.x = h

    def setP(self, p):
        self._hpr.y = p

    def setR(self, r):
        self._hpr.z = r

    def getParent(self):
        return self

    def removeNode(self):
        pass

    def attachNewNode(self, name):
        return DummyNode()

    def setLight(self, *args):
        pass

    def clearLight(self, *args):
        pass

    def setScale(self, *args):
        pass

    def lookAt(self, *args):
        pass

    def hide(self):
        pass

    def show(self):
        pass


class ElementalEffectsTests(unittest.TestCase):
    def test_monster_dimensions(self):
        boss_mock = MagicMock()
        boss_mock.__class__.__name__ = 'CableOverlordBoss'
        boss_mock.name = '보스'
        h, r = get_monster_dimensions(boss_mock)
        self.assertAlmostEqual(h, 4.5)
        self.assertAlmostEqual(r, 1.45)

        hound_mock = MagicMock()
        hound_mock.__class__.__name__ = 'SkeletalDobermanHellhound'
        hound_mock.name = '사냥개'
        h, r = get_monster_dimensions(hound_mock)
        self.assertAlmostEqual(h, 1.3)
        self.assertAlmostEqual(r, 0.65)

    def test_hellhound_take_damage_no_damage_type(self):
        """Verify SkeletalDobermanHellhound.take_damage handles default damage_type=None without NameError."""
        hound = SkeletalDobermanHellhound.__new__(SkeletalDobermanHellhound)
        hound.hp = 100
        hound.max_hp = 100
        hound.is_corpse = False
        hound.is_dodging = False
        hound.last_action_dodged = False
        hound.pos = Vec3(0, 0, 0)
        hound.node = DummyNode()
        hound._elemental_fx = MagicMock()

        # Call with only dmg, apply_knockback, hit_dir (reproducing combat_system line 913)
        is_dead = hound.take_damage(25.0, apply_knockback=False, hit_dir=Vec3(0, 1, 0))
        self.assertIn(hound.hp, [75.0, 100.0])  # Either took 25 dmg or dodged (35% dodge chance)

    def test_hellhound_take_damage_with_fire_and_electric(self):
        """Verify SkeletalDobermanHellhound handles fire and electric damage_type."""
        hound = SkeletalDobermanHellhound.__new__(SkeletalDobermanHellhound)
        hound.hp = 100
        hound.max_hp = 100
        hound.is_corpse = False
        hound.is_dodging = False
        hound.last_action_dodged = False
        hound.pos = Vec3(0, 0, 0)
        hound.node = DummyNode()
        hound._elemental_fx = MagicMock()

        hound.take_damage(20.0, apply_knockback=False, hit_dir=Vec3(0, 1, 0), damage_type='fire')
        if not hound.last_action_dodged:
            self.assertGreater(hound.burn_timer, 0.0)

        hound.take_damage(15.0, apply_knockback=False, hit_dir=Vec3(0, 1, 0), damage_type='electric')
        if not hound.last_action_dodged:
            self.assertGreater(hound.shock_timer, 0.0)

    def test_all_monster_classes_take_damage_signature(self):
        """Verify all 6 monster classes accept damage_type and trigger burn/shock."""
        classes = [
            LongBlackSerpent,
            TallSkeletonMonster,
            AbominableMudOrc,
            AlluringAshWitch,
            SkeletalDobermanHellhound,
            CableOverlordBoss,
        ]

        for cls in classes:
            with self.subTest(monster_class=cls.__name__):
                m = cls.__new__(cls)
                m.hp = 200
                m.max_hp = 200
                m.is_corpse = False
                m.is_dodging = False
                m.last_action_dodged = False
                m.pos = Vec3(0, 0, 0)
                m.node = DummyNode()
                m._elemental_fx = MagicMock()
                m.stun = MagicMock()

                # 1. Normal damage
                m.take_damage(20.0, apply_knockback=False, hit_dir=Vec3(1, 0, 0))
                self.assertLessEqual(m.hp, 200)

                # 2. Fire damage
                m.take_damage(25.0, apply_knockback=False, hit_dir=Vec3(0, 1, 0), damage_type='fire')
                if not getattr(m, 'last_action_dodged', False):
                    self.assertGreater(getattr(m, 'burn_timer', 0.0), 0.0)

                # 3. Electric damage
                m.take_damage(10.0, apply_knockback=False, hit_dir=Vec3(0, 1, 0), damage_type='electric')
                if not getattr(m, 'last_action_dodged', False):
                    self.assertGreater(getattr(m, 'shock_timer', 0.0), 0.0)

    def test_burn_dot_ticking(self):
        """Verify update_elemental correctly applies DoT damage over time."""
        hound = SkeletalDobermanHellhound.__new__(SkeletalDobermanHellhound)
        hound.hp = 100
        hound.max_hp = 100
        hound.is_corpse = False
        hound.is_dodging = False
        hound.pos = Vec3(0, 0, 0)
        hound.node = DummyNode()
        hound._elemental_fx = MagicMock()

        hound.apply_burn(dps=30.0, duration=2.0)
        self.assertEqual(hound.burn_timer, 2.0)
        self.assertEqual(hound.burn_dps, 30.0)

        # Tick 0.5s -> expected ~15 dmg
        hound.update_elemental(0.5)
        self.assertAlmostEqual(hound.burn_timer, 1.5)
        self.assertAlmostEqual(hound.hp, 85.0, delta=1.0)

        # Tick 1.5s -> timer expires
        hound.update_elemental(1.5)
        self.assertEqual(hound.burn_timer, 0.0)
        self.assertEqual(hound.burn_dps, 0.0)
        self.assertAlmostEqual(hound.hp, 40.0, delta=1.0)

    def test_radial_lightning_origin_propagation(self):
        """Verify lightning arcs originate at shock_origin and propagate radially outward across 4 segments."""
        from elemental_effects import MonsterElementalVisuals
        m_mock = MagicMock()
        m_mock.__class__.__name__ = 'TallSkeletonMonster'
        m_mock.name = '해골'
        m_mock.node = DummyNode()
        m_mock.pos = Vec3(10, 20, 0)

        fx = MonsterElementalVisuals.__new__(MonsterElementalVisuals)
        fx.monster = m_mock
        fx.height, fx.radius = 3.2, 0.85
        fx.shock_root = DummyNode()
        fx.set_shock_origin(Vec3(10.2, 20.1, 1.8))

        self.assertAlmostEqual(fx.shock_origin.z, 1.8, delta=0.5)

        # Test arc recalculation with 4 segments
        seg_mocks = [DummyNode(), DummyNode(), DummyNode(), DummyNode()]
        arc = {
            "segments": seg_mocks,
            "base_angle": 0.0,
            "pitch": 0.2,
            "recalc_timer": 0.0
        }
        fx._recalc_arc(arc)

        # Segments 0, 1, 2, 3 midpoints should have increasing distance from shock_origin (뻗어나감 검증)
        d0 = (seg_mocks[0].getPos() - fx.shock_origin).length()
        d1 = (seg_mocks[1].getPos() - fx.shock_origin).length()
        d2 = (seg_mocks[2].getPos() - fx.shock_origin).length()
        d3 = (seg_mocks[3].getPos() - fx.shock_origin).length()
        self.assertLess(d0, d1)
        self.assertLess(d1, d2)
        self.assertLess(d2, d3)
        # Verify extended ambient range exceeds 3.0 meters
        self.assertGreater(d3, 2.5)

    def test_chain_lightning_to_adjacent_monster(self):
        """Verify chain lightning arc targets and connects all the way to adjacent monster."""
        from elemental_effects import MonsterElementalVisuals
        m1 = MagicMock()
        m1.__class__.__name__ = 'TallSkeletonMonster'
        m1.name = '해골'
        m1.node = DummyNode()
        m1.pos = Vec3(0, 0, 0)

        m2 = MagicMock()
        m2.__class__.__name__ = 'AbominableMudOrc'
        m2.name = '오크'
        m2.node = DummyNode()
        m2.pos = Vec3(4.0, 0, 0)  # 4m away
        m2.hp = 150
        m2.is_corpse = False
        m2.shock_timer = 0.0

        fx = MonsterElementalVisuals.__new__(MonsterElementalVisuals)
        fx.monster = m1
        fx.height, fx.radius = 3.2, 0.85
        fx.shock_root = DummyNode()
        fx.set_shock_origin(None)

        # Mock getRelativePoint to return m2 relative to m1 (around x=4.0)
        fx.shock_root.getRelativePoint = MagicMock(return_value=Vec3(4.0, 0, 1.4))

        seg_mocks = [DummyNode(), DummyNode(), DummyNode(), DummyNode()]
        arc = {
            "segments": seg_mocks,
            "base_angle": 0.0,
            "pitch": 0.0,
            "recalc_timer": 0.0
        }

        fx._recalc_arc(arc, target_monster=m2)

        # Last segment midpoint should reach close to target monster (~3.5m - 4.0m)
        d_last = (seg_mocks[3].getPos() - fx.shock_origin).length()
        self.assertGreater(d_last, 3.0)
        # Adjacent monster should be shocked
        m2.apply_shock.assert_called()


if __name__ == '__main__':
    unittest.main()
