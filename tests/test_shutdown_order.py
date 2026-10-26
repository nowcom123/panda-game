import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game import LiminalInfiniteLoop


class ShutdownOrderTests(unittest.TestCase):
    def test_workers_join_before_resource_cleanup_and_shutdown_is_idempotent(self):
        order = []
        executor = Mock()
        executor.shutdown.side_effect = lambda **kw: order.append('workers')
        effects = Mock()
        effects.destroy.side_effect = lambda: order.append('effects')
        game = LiminalInfiniteLoop.__new__(LiminalInfiniteLoop)
        game.chunk_executor = executor
        game.active_chunk_futures = {'pending': object()}
        game.combat = SimpleNamespace(casing_effects=effects)
        with patch('game.ShowBase.destroy', side_effect=lambda: order.append('engine')):
            game.destroy()
            game.destroy()
        executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)
        self.assertEqual(order, ['workers', 'effects', 'engine'])
        self.assertEqual(game.active_chunk_futures, {})
