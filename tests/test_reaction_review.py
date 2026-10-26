import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from panda3d.core import NodePath, Vec3
from combat_system import CombatSystem
from player_controller import PlayerController
from rpg.quick_use import QuickUseManager


class ReactionReviewTests(unittest.TestCase):
    def test_guard_remains_active_during_counter_warning(self):
        c = CombatSystem.__new__(CombatSystem)
        root = NodePath('root')
        c.render = root
        node = root.attachNewNode('guard')
        m = SimpleNamespace(node=node, hp=100, reaction_role='serpent',
                            is_guarding=True, counter_pending=True, reaction_cooldown=6)
        p = SimpleNamespace(perk_levels={})
        self.assertTrue(c._resolve_monster_reaction(m, Vec3(0, -1, 0), p)['blocked'])
        self.assertFalse(c._resolve_monster_reaction(m, Vec3(0, 1, 0), p)['blocked'])
        root.removeNode()

    def test_dot_bypasses_hit_iframes_without_extending_them(self):
        p = PlayerController.__new__(PlayerController)
        p.hp = p.max_hp = 100
        p.invincible_timer = .5
        p.relics = []
        p.has_perk = lambda _: False
        p.exp = p.level = p.pending_perk_picks = 0
        p.exp_to_next = 100
        p.ui_mgr = Mock()
        p.trigger_quake_shake = Mock()
        for _ in range(30):
            p.take_damage(.4, damage_type='dot')
        self.assertAlmostEqual(p.hp, 88)
        self.assertEqual(p.invincible_timer, .5)
        p.trigger_quake_shake.assert_not_called()

    def test_focus_loss_cancels_and_pauses_without_item_use(self):
        win = SimpleNamespace(getProperties=lambda: SimpleNamespace(getForeground=lambda: False))
        p = SimpleNamespace(lock_mouse=Mock(), key_map={'w': 1}, use_item=Mock())
        g = SimpleNamespace(win=win, player=p, game_state='QUICK_USE', pause_game=Mock())
        q = QuickUseManager(g)
        q.is_open = q.is_key_down = True
        try:
            q.on_window_event(win)
            self.assertFalse(q.is_open)
            self.assertFalse(q.is_key_down)
            self.assertEqual(p.key_map['w'], 0)
            p.use_item.assert_not_called()
            g.pause_game.assert_called_once()
        finally:
            q.cleanup()

    def test_closing_inactive_selector_is_idempotent(self):
        g = SimpleNamespace(player=SimpleNamespace(lock_mouse=Mock()), game_state='INTRO')
        q = QuickUseManager(g)
        try:
            q.close({'id': 'medkit'})
            g.player.lock_mouse.assert_not_called()
        finally:
            q.cleanup()
