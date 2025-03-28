#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
from datetime import datetime, timedelta
import fcntl
import time

from transfers.transfer import Transfer
from config import MIN_FILE_AGE, TRANSFER_PATHS

class TestTransfer(unittest.TestCase):
    def setUp(self):
        self.transfer = Transfer()
        self.test_file = Path('/test/source/file__LRE.jpg')
        self.test_dir = self.test_file.parent
        self.dest_dir = Path('/test/destination')
        
        # Mock TRANSFER_PATHS for testing
        self.transfer_paths_patch = patch('transfers.transfer.TRANSFER_PATHS', {
            self.test_dir: self.dest_dir
        })
        self.transfer_paths_patch.start()
        
    def tearDown(self):
        self.transfer_paths_patch.stop()
        
    def test_when_file_does_not_exist_then_returns_false(self):
        """Should return False when file doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = self.transfer.transfer_file(self.test_file)
            self.assertFalse(result)
            
    def test_when_file_not_lre_then_returns_false(self):
        """Should return False when file doesn't have __LRE suffix."""
        non_lre_file = Path('/test/source/file.jpg')
        with patch.object(Path, 'exists', return_value=True):
            result = self.transfer.transfer_file(non_lre_file)
            self.assertFalse(result)
            
    def test_when_source_dir_not_configured_then_returns_false(self):
        """Should return False when source directory has no configured destination."""
        unconfigured_file = Path('/unconfigured/dir/file__LRE.jpg')
        with patch.object(Path, 'exists', return_value=True):
            result = self.transfer.transfer_file(unconfigured_file)
            self.assertFalse(result)
            
    def test_when_file_too_new_then_returns_false(self):
        """Should return False when file is newer than MIN_FILE_AGE."""
        with patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'stat') as mock_stat:
             
            # Mock file as being too new
            mock_stat.return_value.st_mtime = time.time()
            result = self.transfer.transfer_file(self.test_file)
            self.assertFalse(result)
            
    def test_when_cannot_get_exclusive_access_then_returns_false(self):
        """Should return False when can't get exclusive access to file."""
        with patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'stat') as mock_stat, \
             patch('builtins.open', side_effect=IOError):
             
            # Mock file as being old enough
            mock_stat.return_value.st_mtime = time.time() - (MIN_FILE_AGE + 10)
            result = self.transfer.transfer_file(self.test_file)
            self.assertFalse(result)
            
    def test_when_all_conditions_met_then_transfers_file(self):
        """Should transfer file when all conditions are met."""
        with patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'stat') as mock_stat, \
             patch('builtins.open', MagicMock()), \
             patch('fcntl.flock'), \
             patch.object(Path, 'rename') as mock_rename, \
             patch.object(Path, 'mkdir') as mock_mkdir:
             
            # Mock file as being old enough
            mock_stat.return_value.st_mtime = time.time() - (MIN_FILE_AGE + 10)
            
            result = self.transfer.transfer_file(self.test_file)
            
            self.assertTrue(result)
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mock_rename.assert_called_once_with(self.dest_dir / self.test_file.name)
            
    def test_when_checking_file_age_with_invalid_file_then_returns_false(self):
        """Should return False when checking age of invalid/inaccessible file."""
        with patch.object(Path, 'stat', side_effect=OSError):
            result = self.transfer._is_file_old_enough(self.test_file)
            self.assertFalse(result)
            
    def test_when_checking_file_age_with_old_file_then_returns_true(self):
        """Should return True when file is older than MIN_FILE_AGE."""
        with patch.object(Path, 'stat') as mock_stat:
            mock_stat.return_value.st_mtime = time.time() - (MIN_FILE_AGE + 10)
            result = self.transfer._is_file_old_enough(self.test_file)
            self.assertTrue(result)
            
    def test_when_checking_file_age_with_new_file_then_returns_false(self):
        """Should return False when file is newer than MIN_FILE_AGE."""
        with patch.object(Path, 'stat') as mock_stat:
            mock_stat.return_value.st_mtime = time.time()
            result = self.transfer._is_file_old_enough(self.test_file)
            self.assertFalse(result)
            
    def test_when_getting_file_access_with_timeout_then_returns_false(self):
        """Should return False after timeout when can't get file access."""
        with patch('builtins.open', side_effect=IOError), \
             patch('time.sleep') as mock_sleep:
             
            start_time = time.time()
            result = self.transfer._can_access_file(self.test_file, timeout=1)
            end_time = time.time()
            
            self.assertFalse(result)
            self.assertTrue(end_time - start_time >= 1)
            mock_sleep.assert_called()
            
    def test_when_getting_file_access_with_success_then_returns_true(self):
        """Should return True when file access is obtained."""
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        
        with patch('builtins.open', return_value=mock_file), \
             patch('fcntl.flock') as mock_flock:
             
            result = self.transfer._can_access_file(self.test_file)
            
            self.assertTrue(result)
            self.assertEqual(mock_flock.call_count, 2)  # Lock and unlock
            mock_flock.assert_any_call(mock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            mock_flock.assert_any_call(mock_file.fileno(), fcntl.LOCK_UN)
            
    def test_when_transfer_raises_exception_then_returns_false(self):
        """Should return False and log error when transfer raises exception."""
        with patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'stat') as mock_stat, \
             patch('builtins.open', MagicMock()), \
             patch('fcntl.flock'), \
             patch.object(Path, 'rename', side_effect=OSError("Test error")), \
             patch.object(Path, 'mkdir'):
             
            # Mock file as being old enough
            mock_stat.return_value.st_mtime = time.time() - (MIN_FILE_AGE + 10)
            
            with self.assertLogs(level='ERROR') as log:
                result = self.transfer.transfer_file(self.test_file)
                
            self.assertFalse(result)
            self.assertTrue(any("Test error" in record.message for record in log.records))

if __name__ == '__main__':
    unittest.main()
