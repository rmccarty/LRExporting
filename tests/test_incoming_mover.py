#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
from pathlib import Path
import tempfile
import shutil
import time

from incoming_mover import IncomingMover


class TestIncomingMover(unittest.TestCase):
    """Test cases for IncomingMover class."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_source1 = Path("/test/ron/incoming")
        self.test_dest1 = Path("/test/ron/apple_photos")
        self.test_source2 = Path("/test/claudia/incoming")
        self.test_dest2 = Path("/test/claudia/old_photos")
        
        self.test_transfer_paths = {
            self.test_source1: self.test_dest1,
            self.test_source2: self.test_dest2
        }
        
        self.mover = IncomingMover(
            transfer_paths=self.test_transfer_paths,
            min_file_age=30,
            sleep_time=1
        )
        
    # 1. Initialization Tests
    def test_when_initializing_then_sets_correct_paths(self):
        """Should initialize with correct transfer paths."""
        self.assertEqual(self.mover.transfer_paths, self.test_transfer_paths)
        self.assertEqual(self.mover.min_file_age, 30)
        self.assertEqual(self.mover.sleep_time, 1)
        
    def test_when_initializing_with_defaults_then_uses_config(self):
        """Should use config values when not specified."""
        with patch('incoming_mover.TRANSFER_PATHS', self.test_transfer_paths), \
             patch('incoming_mover.MIN_FILE_AGE', 60):
            
            mover = IncomingMover()
            self.assertEqual(mover.transfer_paths, self.test_transfer_paths)
            self.assertEqual(mover.min_file_age, 60)
            
    # 2. File Lock Testing
    def test_when_file_is_not_locked_then_returns_false(self):
        """Should return False when file can be opened."""
        mock_path = MagicMock(spec=Path)
        
        with patch('builtins.open', mock_open()):
            result = self.mover._is_file_locked(mock_path)
            self.assertFalse(result)
            
    def test_when_file_is_locked_then_returns_true(self):
        """Should return True when file cannot be opened."""
        mock_path = MagicMock(spec=Path)
        
        with patch('builtins.open', side_effect=IOError("File is locked")):
            result = self.mover._is_file_locked(mock_path)
            self.assertTrue(result)
            
    # 3. File Age Testing
    def test_when_file_is_old_enough_then_returns_true(self):
        """Should return True when file is older than min_file_age."""
        mock_path = MagicMock(spec=Path)
        
        # Mock file to be 60 seconds old (older than min_file_age of 30)
        old_time = time.time() - 60
        mock_stat = Mock()
        mock_stat.st_mtime = old_time
        mock_path.stat.return_value = mock_stat
        
        result = self.mover._is_file_old_enough(mock_path)
        self.assertTrue(result)
        
    def test_when_file_is_too_new_then_returns_false(self):
        """Should return False when file is newer than min_file_age."""
        mock_path = MagicMock(spec=Path)
        
        # Mock file to be 10 seconds old (newer than min_file_age of 30)
        new_time = time.time() - 10
        mock_stat = Mock()
        mock_stat.st_mtime = new_time
        mock_path.stat.return_value = mock_stat
        
        result = self.mover._is_file_old_enough(mock_path)
        self.assertFalse(result)
        
    def test_when_file_age_check_fails_then_returns_false(self):
        """Should return False when file stat fails."""
        mock_path = MagicMock(spec=Path)
        mock_path.stat.side_effect = OSError("File not accessible")
        
        result = self.mover._is_file_old_enough(mock_path)
        self.assertFalse(result)
        
    # 4. File Move Validation Tests
    def test_when_file_does_not_exist_then_cannot_move(self):
        """Should return False when file doesn't exist."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        
        can_move, reason = self.mover._can_move_file(mock_path)
        self.assertFalse(can_move)
        self.assertEqual(reason, "File does not exist")
        
    def test_when_file_is_not_regular_file_then_cannot_move(self):
        """Should return False when path is not a regular file."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = False
        
        can_move, reason = self.mover._can_move_file(mock_path)
        self.assertFalse(can_move)
        self.assertEqual(reason, "Not a regular file")
        
    def test_when_file_is_zero_bytes_then_cannot_move(self):
        """Should return False when file is zero bytes."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        
        mock_stat = Mock()
        mock_stat.st_size = 0
        mock_path.stat.return_value = mock_stat
        
        can_move, reason = self.mover._can_move_file(mock_path)
        self.assertFalse(can_move)
        self.assertEqual(reason, "Zero-byte file")
        
    def test_when_file_is_valid_and_ready_then_can_move(self):
        """Should return True when file is ready to move."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_stat.st_mtime = time.time() - 60  # Old enough
        mock_path.stat.return_value = mock_stat
        
        with patch('builtins.open', mock_open()):  # Not locked
            can_move, reason = self.mover._can_move_file(mock_path)
            self.assertTrue(can_move)
            self.assertEqual(reason, "OK")
            
    # 5. File Moving Tests
    def test_when_file_cannot_move_then_returns_false(self):
        """Should return False when file cannot be moved."""
        mock_file = MagicMock(spec=Path)
        mock_dest = MagicMock(spec=Path)
        
        with patch.object(self.mover, '_can_move_file', return_value=(False, "File too new")):
            result = self.mover.move_file(mock_file, mock_dest)
            self.assertFalse(result)
            
    def test_when_destination_exists_then_returns_false(self):
        """Should return False when destination file already exists."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        mock_dest = MagicMock(spec=Path)
        
        mock_dest_file = MagicMock(spec=Path)
        mock_dest_file.exists.return_value = True
        mock_dest.__truediv__.return_value = mock_dest_file
        
        with patch.object(self.mover, '_can_move_file', return_value=(True, "OK")):
            result = self.mover.move_file(mock_file, mock_dest)
            self.assertFalse(result)
            
    def test_when_move_succeeds_then_returns_true(self):
        """Should return True when file is moved successfully."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        mock_dest = MagicMock(spec=Path)
        
        mock_dest_file = MagicMock(spec=Path)
        mock_dest_file.exists.return_value = False
        mock_dest.__truediv__.return_value = mock_dest_file
        
        with patch.object(self.mover, '_can_move_file', return_value=(True, "OK")), \
             patch('shutil.move') as mock_shutil_move:
            
            result = self.mover.move_file(mock_file, mock_dest)
            
            self.assertTrue(result)
            mock_dest.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mock_shutil_move.assert_called_once()
            
    def test_when_move_raises_exception_then_returns_false(self):
        """Should return False when move operation fails."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test__LRE.jpg"
        mock_dest = MagicMock(spec=Path)
        
        with patch.object(self.mover, '_can_move_file', return_value=(True, "OK")), \
             patch('shutil.move', side_effect=OSError("Permission denied")):
            
            result = self.mover.move_file(mock_file, mock_dest)
            self.assertFalse(result)
            
    # 6. Directory Checking Tests
    def test_when_source_directory_not_exists_then_returns_zero(self):
        """Should return 0 when source directory doesn't exist."""
        mock_source = MagicMock(spec=Path)
        mock_source.exists.return_value = False
        mock_dest = MagicMock(spec=Path)
        
        result = self.mover.check_directory(mock_source, mock_dest)
        self.assertEqual(result, 0)
        
    def test_when_directory_has_lre_files_then_processes_them(self):
        """Should process __LRE files found in directory."""
        mock_source = MagicMock(spec=Path)
        mock_source.exists.return_value = True
        mock_source.name = "test_incoming"
        
        mock_file1 = MagicMock(spec=Path)
        mock_file1.name = "photo1__LRE.jpg"
        mock_file2 = MagicMock(spec=Path)
        mock_file2.name = "photo2__LRE.mp4"
        
        mock_source.glob.return_value = [mock_file1, mock_file2]
        mock_dest = MagicMock(spec=Path)
        
        with patch.object(self.mover, '_can_move_file', return_value=(True, "OK")), \
             patch.object(self.mover, 'move_file', return_value=True) as mock_move:
            result = self.mover.check_directory(mock_source, mock_dest)
            
            self.assertEqual(result, 2)
            self.assertEqual(mock_move.call_count, 2)
            mock_move.assert_any_call(mock_file1, mock_dest)
            mock_move.assert_any_call(mock_file2, mock_dest)
            
    def test_when_directory_has_no_lre_files_then_returns_zero(self):
        """Should return 0 when no __LRE files found."""
        mock_source = MagicMock(spec=Path)
        mock_source.exists.return_value = True
        mock_source.name = "empty_dir"
        mock_source.glob.return_value = []
        mock_dest = MagicMock(spec=Path)
        
        result = self.mover.check_directory(mock_source, mock_dest)
        self.assertEqual(result, 0)
        
    def test_when_some_files_cannot_move_then_counts_only_moved(self):
        """Should count only successfully moved files."""
        mock_source = MagicMock(spec=Path)
        mock_source.exists.return_value = True
        mock_source.name = "test_incoming"
        
        mock_file1 = MagicMock(spec=Path)
        mock_file1.name = "photo1__LRE.jpg"
        mock_file2 = MagicMock(spec=Path)
        mock_file2.name = "photo2__LRE.mp4"
        
        mock_source.glob.return_value = [mock_file1, mock_file2]
        mock_dest = MagicMock(spec=Path)
        
        # Both files can move, but first succeeds and second fails during move
        with patch.object(self.mover, '_can_move_file', return_value=(True, "OK")), \
             patch.object(self.mover, 'move_file', side_effect=[True, False]):
            result = self.mover.check_directory(mock_source, mock_dest)
            self.assertEqual(result, 1)
            
    # 7. Cycle Processing Tests
    def test_when_running_cycle_then_processes_all_transfer_paths(self):
        """Should process all configured transfer paths."""
        with patch.object(self.mover, 'check_directory', return_value=2) as mock_check:
            self.mover.run_cycle()
            
            # Should call check_directory for each transfer path
            self.assertEqual(mock_check.call_count, 2)
            mock_check.assert_any_call(self.test_source1, self.test_dest1)
            mock_check.assert_any_call(self.test_source2, self.test_dest2)
            
    def test_when_cycle_has_exception_then_handles_gracefully(self):
        """Should handle exceptions during cycle processing."""
        with patch.object(self.mover, 'check_directory', side_effect=Exception("Test error")):
            # Should not raise exception
            try:
                self.mover.run_cycle()
            except Exception:
                self.fail("run_cycle should not raise exceptions")
                
    # 8. Integration Tests with Real Filesystem
    def test_integration_with_real_files(self):
        """Integration test with actual temporary files and directories."""
        # Create temporary directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test directories
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            
            source_dir.mkdir()
            dest_dir.mkdir()
            
            # Create a test __LRE file
            test_file = source_dir / "test__LRE.jpg"
            test_file.write_text("fake image content")
            
            # Wait to ensure file is old enough (mock shorter age for test)
            test_transfer_paths = {source_dir: dest_dir}
            mover = IncomingMover(
                transfer_paths=test_transfer_paths,
                min_file_age=0,  # No age requirement for test
                sleep_time=1
            )
            
            # Move the file
            moved = mover.check_directory(source_dir, dest_dir)
            
            # Verify file was moved
            self.assertEqual(moved, 1)
            self.assertFalse(test_file.exists())  # Original deleted
            self.assertTrue((dest_dir / "test__LRE.jpg").exists())  # Moved to destination


if __name__ == '__main__':
    unittest.main()