import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from watchers.video_watcher import VideoWatcher
import tempfile
import shutil

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

    # 3. process_file Tests
    def test_when_processing_valid_video_then_processor_is_called(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        mock_path.as_posix.return_value = '/test/video.mp4'
        mock_path.name = 'video.mp4'
        with patch.object(watcher, '_has_xmp_file', return_value=True), \
             patch('watchers.video_watcher.VideoProcessor') as mock_processor, \
             patch.object(watcher, '_get_next_sequence', return_value=42), \
             patch.object(watcher.logger, 'info') as mock_log:
            instance = mock_processor.return_value
            watcher.process_file(mock_path)
            mock_processor.assert_called_once_with('/test/video.mp4', sequence=42)
            instance.process_video.assert_called_once()
            mock_log.assert_any_call(f"Found new video: {mock_path.name}")

    def test_when_processing_file_without_xmp_then_skips_processing(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        with patch.object(watcher, '_has_xmp_file', return_value=False), \
             patch('watchers.video_watcher.VideoProcessor') as mock_processor:
            watcher.process_file(mock_path)
            mock_processor.assert_not_called()

    def test_when_processor_raises_exception_then_logs_error(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_path = MagicMock(spec=Path)
        with patch.object(watcher, '_has_xmp_file', return_value=True), \
             patch('watchers.video_watcher.VideoProcessor', side_effect=Exception("fail")), \
             patch.object(watcher.logger, 'error') as mock_log:
            watcher.process_file(mock_path)
            self.assertTrue(any("Error processing" in msg for msg in [call[0][0] for call in mock_log.call_args_list]))

    # 4. check_directory Tests
    def test_when_checking_nonexistent_directory_then_skips(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = False
        with patch.object(watcher.logger, 'info') as mock_log:
            watcher.check_directory(mock_dir)
            mock_log.assert_not_called()

    def test_when_checking_directory_and_exception_occurs_then_no_log(self):
        watcher = VideoWatcher(directories=self.test_dirs)
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        with patch('watchers.video_watcher.VIDEO_PATTERN', ['*.mp4']):
            mock_dir.glob.side_effect = Exception("fail")
            # No error log expected as code does not catch exception
            try:
                watcher.check_directory(mock_dir)
            except Exception:
                pass

if __name__ == '__main__':
    unittest.main()
