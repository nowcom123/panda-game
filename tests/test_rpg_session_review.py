import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rpg import load_catalog, SaveStore, RPGSession


class SessionReviewTests(unittest.TestCase):
    def test_menu_load_does_not_write_starters(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as temp:
            store = SaveStore(Path(temp) / 'profile.json', catalog)
            session = RPGSession(store, catalog)
            self.assertTrue(session.initialize(grant_starters=False))
            self.assertFalse(store.path.exists())
            self.assertEqual(session.profile.items, {})
            self.assertTrue(session.initialize())
            self.assertEqual(len(session.profile.items), 4)

    def test_starter_write_failure_blocks_session(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as temp:
            store = SaveStore(Path(temp) / 'profile.json', catalog)
            session = RPGSession(store, catalog)
            with patch.object(store, 'save', side_effect=PermissionError('read only')):
                self.assertFalse(session.initialize())
            self.assertFalse(session.is_valid)
            self.assertIsNone(session.profile)
            self.assertIn('read only', session.load_error)
            self.assertFalse(store.path.exists())
