import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from watchers.transfer_watcher import TransferWatcher

class TestTransferWatcher(unittest.TestCase):
    def setUp(self):
        self.test_dirs = ['/test/dir1', '/test/dir2']

    # 1. Initialization Tests
    def test_when_initializing_with_default_dirs_then_sets_directories(self):
        with patch('watchers.transfer_watcher.WATCH_DIRS', self.test_dirs):
            watcher = TransferWatcher()
            self.assertEqual([str(d) for d in watcher.directories], self.test_dirs)
            self.assertFalse(watcher.running)
            self.assertIsNotNone(watcher.logger)
            self.assertIsNotNone(watcher.transfer)

    def test_when_initializing_with_custom_dirs_then_uses_custom_dirs(self):
        watcher = TransferWatcher(directories=self.test_dirs)
        self.assertEqual([str(d) for d in watcher.directories], self.test_dirs)

    # 2. process_file Tests
    def test_when_processing_file_then_calls_transfer_file_and_returns_result(self):
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        with patch.object(watcher.transfer, 'transfer_file', return_value=True) as mock_transfer:
            result = watcher.process_file(mock_path)
            mock_transfer.assert_called_once_with(mock_path)
            self.assertTrue(result)
        with patch.object(watcher.transfer, 'transfer_file', return_value=False) as mock_transfer:
            result = watcher.process_file(mock_path)
            mock_transfer.assert_called_once_with(mock_path)
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
