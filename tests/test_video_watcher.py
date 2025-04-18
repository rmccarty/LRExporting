import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from watchers.video_watcher import VideoWatcher

class TestVideoWatcher(unittest.TestCase):
    def setUp(self):
        self.test_dirs = ['/test/dir1', '/test/dir2']

    # 1. Initialization Tests
    def test_when_initializing_then_sets_directories_and_logger(self):
        with patch('watchers.base_watcher.WATCH_DIRS', self.test_dirs):
            watcher = VideoWatcher()
            self.assertEqual([str(d) for d in watcher.directories], self.test_dirs)
            self.assertFalse(watcher.running)
            self.assertIsNotNone(watcher.logger)

    def test_when_initializing_with_custom_dirs_then_uses_custom_dirs(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        self.assertEqual([str(d) for d in watcher.directories], self.test_dirs)

    # 2. File Filtering & Detection
    def test_when_file_has_no_xmp_then_has_xmp_file_returns_false(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        # Simulate both .xmp and .MOV.xmp/.mp4.xmp missing
        mock_path.with_suffix.return_value.exists.return_value = False
        with patch.object(Path, 'exists', return_value=False):
            self.assertFalse(watcher._has_xmp_file(mock_path))

    def test_when_file_has_xmp_then_has_xmp_file_returns_true(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        # Simulate .xmp present
        mock_path.with_suffix.return_value.exists.return_value = True
        self.assertTrue(watcher._has_xmp_file(mock_path))

if __name__ == '__main__':
    unittest.main()
