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

    # 3. check_directory Tests
    def test_when_directory_does_not_exist_then_logs_warning(self):
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = False
        with self.assertLogs(watcher.logger, level='WARNING') as log:
            watcher.check_directory(mock_dir)
            self.assertIn(f"Directory does not exist: {mock_dir}", log.output[0])

    def test_when_directory_exists_then_processes_files(self):
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_file1 = MagicMock(spec=Path)
        mock_file2 = MagicMock(spec=Path)
        mock_dir.glob.return_value = [mock_file1, mock_file2]
        with patch.object(watcher, 'process_batch', return_value=[True, True]) as mock_process_batch:
            watcher.check_directory(mock_dir)
            # Should call process_batch with both files
            mock_process_batch.assert_called_once_with([mock_file1, mock_file2])

    def test_when_exception_occurs_then_logs_error(self):
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.glob.side_effect = Exception("Test error")
        with self.assertLogs(watcher.logger, level='ERROR') as log:
            watcher.check_directory(mock_dir)
            self.assertIn("Error checking directory", log.output[0])

    # 4. Batch Processing Tests
    def test_when_process_batch_with_valid_files_then_processes_successfully(self):
        """Should process batch of files and return results."""
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_file1 = MagicMock(spec=Path)
        mock_file2 = MagicMock(spec=Path)
        mock_files = [mock_file1, mock_file2]
        
        # Mock file grouping and processing
        with patch.object(watcher, '_group_files_by_type', return_value=([], mock_files)), \
             patch.object(watcher, '_process_regular_batch', return_value=[True, True]) as mock_regular:
            
            results = watcher.process_batch(mock_files)
            
            self.assertEqual(len(results), 2)
            self.assertTrue(all(results))
            mock_regular.assert_called_once_with(mock_files)
    
    def test_when_process_batch_with_mixed_file_types_then_groups_correctly(self):
        """Should group Apple Photos and regular files correctly."""
        watcher = TransferWatcher(directories=self.test_dirs)
        mock_file1 = MagicMock(spec=Path)
        mock_file2 = MagicMock(spec=Path)
        mock_files = [mock_file1, mock_file2]
        
        # Mock grouping with one Apple Photos file and one regular file
        with patch.object(watcher, '_group_files_by_type', return_value=([mock_file1], [mock_file2])), \
             patch.object(watcher, '_process_apple_photos_batch', return_value=[True]), \
             patch.object(watcher, '_process_regular_batch', return_value=[True]):
            
            results = watcher.process_batch(mock_files)
            
            self.assertEqual(len(results), 2)
            self.assertTrue(all(results))  # Both files should succeed

if __name__ == '__main__':
    unittest.main()
