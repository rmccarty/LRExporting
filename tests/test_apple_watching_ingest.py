#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import tempfile
import time

from apple_watching_ingest import AppleWatchingIngest


class TestAppleWatchingIngest(unittest.TestCase):
    """Test cases for AppleWatchingIngest class."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_apple_photos_dir = Path("/test/ron/apple_photos")
        
        self.ingester = AppleWatchingIngest(
            apple_photos_dir=self.test_apple_photos_dir,
            batch_size=5,
            min_file_age=30,
            sleep_time=1
        )
        
    # 1. Initialization Tests
    def test_when_initializing_then_sets_correct_values(self):
        """Should initialize with correct values."""
        self.assertEqual(self.ingester.apple_photos_dir, self.test_apple_photos_dir)
        self.assertEqual(self.ingester.batch_size, 5)
        self.assertEqual(self.ingester.min_file_age, 30)
        self.assertEqual(self.ingester.sleep_time, 1)
        
    def test_when_initializing_with_defaults_then_uses_config(self):
        """Should use config values when not specified."""
        with patch('apple_watching_ingest.APPLE_PHOTOS_PATHS', [self.test_apple_photos_dir]), \
             patch('apple_watching_ingest.MIN_FILE_AGE', 60):
            
            ingester = AppleWatchingIngest()
            self.assertEqual(ingester.apple_photos_dir, self.test_apple_photos_dir)
            self.assertEqual(ingester.min_file_age, 60)
            
    # 2. File Age Testing
    def test_when_file_is_old_enough_then_returns_true(self):
        """Should return True when file is older than min_file_age."""
        mock_path = MagicMock(spec=Path)
        
        # Mock file to be 60 seconds old (older than min_file_age of 30)
        old_time = time.time() - 60
        mock_stat = Mock()
        mock_stat.st_mtime = old_time
        mock_path.stat.return_value = mock_stat
        
        result = self.ingester._is_file_old_enough(mock_path)
        self.assertTrue(result)
        
    def test_when_file_is_too_new_then_returns_false(self):
        """Should return False when file is newer than min_file_age."""
        mock_path = MagicMock(spec=Path)
        
        # Mock file to be 10 seconds old (newer than min_file_age of 30)
        new_time = time.time() - 10
        mock_stat = Mock()
        mock_stat.st_mtime = new_time
        mock_path.stat.return_value = mock_stat
        
        result = self.ingester._is_file_old_enough(mock_path)
        self.assertFalse(result)
        
    def test_when_file_age_check_fails_then_returns_false(self):
        """Should return False when file stat fails."""
        mock_path = MagicMock(spec=Path)
        mock_path.stat.side_effect = OSError("File not accessible")
        
        result = self.ingester._is_file_old_enough(mock_path)
        self.assertFalse(result)
        
    # 3. File Validation Tests
    def test_when_file_does_not_exist_then_cannot_import(self):
        """Should return False when file doesn't exist."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        
        can_import, reason = self.ingester._can_move_file(mock_path)
        self.assertFalse(can_import)
        self.assertEqual(reason, "File does not exist")
        
    def test_when_file_is_not_regular_file_then_cannot_import(self):
        """Should return False when path is not a regular file."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = False
        
        can_import, reason = self.ingester._can_move_file(mock_path)
        self.assertFalse(can_import)
        self.assertEqual(reason, "Not a regular file")
        
    def test_when_file_is_zero_bytes_then_cannot_import(self):
        """Should return False when file is zero bytes."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        
        mock_stat = Mock()
        mock_stat.st_size = 0
        mock_path.stat.return_value = mock_stat
        
        can_import, reason = self.ingester._can_move_file(mock_path)
        self.assertFalse(can_import)
        self.assertEqual(reason, "Zero-byte file")
        
    def test_when_file_is_valid_and_ready_then_can_import(self):
        """Should return True when file is ready to import."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_stat.st_mtime = time.time() - 60  # Old enough
        mock_path.stat.return_value = mock_stat
        
        can_import, reason = self.ingester._can_move_file(mock_path)
        self.assertTrue(can_import)
        self.assertEqual(reason, "OK")
            
    # 4. File Import Tests
    def test_when_file_cannot_import_then_returns_false(self):
        """Should return False when file cannot be imported."""
        mock_file = MagicMock(spec=Path)
        
        with patch.object(self.ingester, '_can_move_file', return_value=(False, "File too new")):
            result = self.ingester.import_file_to_watching(mock_file)
            self.assertFalse(result)
            
    def test_when_apple_photos_disabled_then_returns_false(self):
        """Should return False when Apple Photos is disabled."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch('apple_watching_ingest.ENABLE_APPLE_PHOTOS', False):
            result = self.ingester.import_file_to_watching(mock_file)
            self.assertFalse(result)
            
    def test_when_import_succeeds_then_returns_true(self):
        """Should return True when file is imported successfully."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch('apple_watching_ingest.ENABLE_APPLE_PHOTOS', True), \
             patch('apple_watching_ingest.ApplePhotos') as mock_apple_photos:
            
            mock_apple_photos.return_value.import_photo.return_value = True
            
            result = self.ingester.import_file_to_watching(mock_file)
            
            self.assertTrue(result)
            mock_apple_photos.return_value.import_photo.assert_called_once()
            
    def test_when_import_fails_then_returns_false(self):
        """Should return False when Apple Photos import fails."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch('apple_watching_ingest.ENABLE_APPLE_PHOTOS', True), \
             patch('apple_watching_ingest.ApplePhotos') as mock_apple_photos:
            
            mock_apple_photos.return_value.import_photo.return_value = False
            
            result = self.ingester.import_file_to_watching(mock_file)
            self.assertFalse(result)
            
    def test_when_import_raises_exception_then_returns_false(self):
        """Should return False when import operation fails."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch('apple_watching_ingest.ENABLE_APPLE_PHOTOS', True), \
             patch('apple_watching_ingest.ApplePhotos', side_effect=Exception("Apple Photos error")):
            
            result = self.ingester.import_file_to_watching(mock_file)
            self.assertFalse(result)
            
    # 5. Directory Checking Tests
    def test_when_directory_not_exists_then_returns_zero(self):
        """Should return 0 when Apple Photos directory doesn't exist."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = False
        self.ingester.apple_photos_dir = mock_dir
        
        result = self.ingester.check_directory()
        self.assertEqual(result, 0)
        
    def test_when_directory_has_lre_files_then_processes_them(self):
        """Should process __LRE files found in directory."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "apple_photos"
        
        mock_file1 = MagicMock(spec=Path)
        mock_file1.name = "photo1__LRE.jpg"
        mock_file2 = MagicMock(spec=Path)
        mock_file2.name = "photo2__LRE.mp4"
        
        mock_dir.glob.return_value = [mock_file1, mock_file2]
        self.ingester.apple_photos_dir = mock_dir
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch.object(self.ingester, 'import_file_to_watching', return_value=True):
            result = self.ingester.check_directory()
            
            self.assertEqual(result, 2)
            
    def test_when_directory_has_no_lre_files_then_returns_zero(self):
        """Should return 0 when no __LRE files found."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "empty_dir"
        mock_dir.glob.return_value = []
        self.ingester.apple_photos_dir = mock_dir
        
        result = self.ingester.check_directory()
        self.assertEqual(result, 0)
        
    def test_when_some_files_cannot_import_then_counts_only_imported(self):
        """Should count only successfully imported files."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "apple_photos"
        
        mock_file1 = MagicMock(spec=Path)
        mock_file1.name = "photo1__LRE.jpg"
        mock_file2 = MagicMock(spec=Path)
        mock_file2.name = "photo2__LRE.mp4"
        
        mock_dir.glob.return_value = [mock_file1, mock_file2]
        self.ingester.apple_photos_dir = mock_dir
        
        # Both files can import, but first succeeds and second fails during import
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch.object(self.ingester, 'import_file_to_watching', side_effect=[True, False]):
            result = self.ingester.check_directory()
            self.assertEqual(result, 1)
            
    # 6. Batch Processing Tests
    def test_when_processing_batch_then_imports_all_files(self):
        """Should process all files in batch."""
        mock_file1 = MagicMock(spec=Path)
        mock_file2 = MagicMock(spec=Path)
        mock_files = [mock_file1, mock_file2]
        
        with patch.object(self.ingester, 'import_file_to_watching', return_value=True):
            results = self.ingester.process_batch(mock_files)
            
            self.assertEqual(len(results), 2)
            self.assertTrue(all(results))
            
    def test_when_processing_batch_with_mixed_results_then_returns_mixed(self):
        """Should return mixed results for batch with some failures."""
        mock_file1 = MagicMock(spec=Path)
        mock_file2 = MagicMock(spec=Path)
        mock_files = [mock_file1, mock_file2]
        
        with patch.object(self.ingester, 'import_file_to_watching', side_effect=[True, False]):
            results = self.ingester.process_batch(mock_files)
            
            self.assertEqual(len(results), 2)
            self.assertEqual(results, [True, False])
            
    def test_when_checking_directory_with_batching_then_processes_in_batches(self):
        """Should process files in configured batch sizes."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "apple_photos"
        
        # Create 7 mock files (more than batch size of 5)
        mock_files = [MagicMock(spec=Path) for _ in range(7)]
        for i, mock_file in enumerate(mock_files):
            mock_file.name = f"photo{i}__LRE.jpg"
            
        mock_dir.glob.return_value = mock_files
        self.ingester.apple_photos_dir = mock_dir
        
        with patch.object(self.ingester, '_can_move_file', return_value=(True, "OK")), \
             patch.object(self.ingester, 'process_batch', return_value=[True] * 5) as mock_process_batch:
            
            result = self.ingester.check_directory_with_batching()
            
            # Should be called twice: once with 5 files, once with 2 files
            self.assertEqual(mock_process_batch.call_count, 2)
            # First call with 5 files, second with 2 files
            first_call_args = mock_process_batch.call_args_list[0][0][0]
            second_call_args = mock_process_batch.call_args_list[1][0][0]
            self.assertEqual(len(first_call_args), 5)
            self.assertEqual(len(second_call_args), 2)
            
    # 7. Cycle Processing Tests
    def test_when_running_cycle_then_processes_directory(self):
        """Should process directory during cycle."""
        with patch.object(self.ingester, 'check_directory_with_batching', return_value=3) as mock_check:
            self.ingester.run_cycle()
            
            mock_check.assert_called_once()
            
    def test_when_cycle_has_exception_then_handles_gracefully(self):
        """Should handle exceptions during cycle processing."""
        with patch.object(self.ingester, 'check_directory_with_batching', side_effect=Exception("Test error")):
            # Should not raise exception
            try:
                self.ingester.run_cycle()
            except Exception:
                self.fail("run_cycle should not raise exceptions")
                
    # 8. Integration Tests with Real Filesystem
    def test_integration_with_real_files(self):
        """Integration test with actual temporary files and directories."""
        # Create temporary directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test Apple Photos directory
            apple_photos_dir = temp_path / "apple_photos"
            apple_photos_dir.mkdir()
            
            # Create a test __LRE file
            test_file = apple_photos_dir / "test__LRE.jpg"
            test_file.write_text("fake image content")
            
            # Wait to ensure file is old enough (mock shorter age for test)
            ingester = AppleWatchingIngest(
                apple_photos_dir=apple_photos_dir,
                min_file_age=0,  # No age requirement for test
                sleep_time=1
            )
            
            # Mock the Apple Photos import
            with patch('apple_watching_ingest.ENABLE_APPLE_PHOTOS', True), \
                 patch('apple_watching_ingest.ApplePhotos') as mock_apple_photos:
                
                mock_apple_photos.return_value.import_photo.return_value = True
                
                # Check the directory
                imported = ingester.check_directory()
                
                # Verify file was processed
                self.assertEqual(imported, 1)
                mock_apple_photos.return_value.import_photo.assert_called_once()


if __name__ == '__main__':
    unittest.main()