#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
from pathlib import Path
import tempfile
import shutil
import os

from incoming_watcher import IncomingWatcher


class TestIncomingWatcher(unittest.TestCase):
    """Test cases for IncomingWatcher class."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_ron_incoming = "/test/ron/incoming"
        self.test_claudia_incoming = "/test/claudia/incoming"
        self.test_both_incoming = "/test/both/incoming"
        
        self.watcher = IncomingWatcher(
            ron_incoming=self.test_ron_incoming,
            claudia_incoming=self.test_claudia_incoming,
            both_incoming=self.test_both_incoming,
            sleep_time=1
        )
        
    # 1. Initialization Tests
    def test_when_initializing_then_sets_correct_paths(self):
        """Should initialize with correct directory paths."""
        self.assertEqual(str(self.watcher.ron_incoming), self.test_ron_incoming)
        self.assertEqual(str(self.watcher.claudia_incoming), self.test_claudia_incoming)
        self.assertEqual(str(self.watcher.both_incoming), self.test_both_incoming)
        self.assertEqual(self.watcher.sleep_time, 1)
        
    def test_when_initializing_then_sets_file_patterns(self):
        """Should initialize with correct file patterns."""
        self.assertEqual(self.watcher.jpeg_pattern, '*.[Jj][Pp][Gg]')
        self.assertIn('*.mp4', self.watcher.video_patterns)
        self.assertIn('*.mov', self.watcher.video_patterns)
        self.assertIn('*.m4v', self.watcher.video_patterns)
        
    def test_when_getting_sequence_then_increments_counter(self):
        """Should increment sequence counter and return formatted string."""
        seq1 = self.watcher._get_next_sequence()
        seq2 = self.watcher._get_next_sequence()
        
        self.assertEqual(seq1, "0001")
        self.assertEqual(seq2, "0002")
        
    # 2. Both_Incoming Processing Tests
    def test_when_both_incoming_not_exists_then_returns_false(self):
        """Should return False when Both_Incoming directory doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = self.watcher.process_both_incoming()
            self.assertFalse(result)
            
    def test_when_both_incoming_empty_then_returns_false(self):
        """Should return False when Both_Incoming directory is empty."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.glob.return_value = []  # No files
        
        with patch.object(self.watcher, 'both_incoming', mock_path):
            result = self.watcher.process_both_incoming()
            self.assertFalse(result)
            
    def test_when_both_incoming_has_files_then_copies_and_deletes(self):
        """Should copy files to incoming directories and delete originals."""
        # Setup mock file
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.jpg"
        mock_file.is_file.return_value = True
        
        # Setup mock both_incoming directory
        mock_both_path = MagicMock(spec=Path)
        mock_both_path.exists.return_value = True
        mock_both_path.glob.return_value = [mock_file]
        
        # Setup mock incoming directories
        mock_ron = MagicMock(spec=Path)
        mock_ron.name = "Ron_Incoming"
        mock_claudia = MagicMock(spec=Path)
        mock_claudia.name = "Claudia_Incoming"
        
        with patch.object(self.watcher, 'both_incoming', mock_both_path), \
             patch.object(self.watcher, 'incoming_directories', [mock_ron, mock_claudia]), \
             patch('builtins.open', mock_open()), \
             patch('shutil.copy') as mock_copy:
            
            result = self.watcher.process_both_incoming()
            
            self.assertTrue(result)
            # Should copy to both directories
            self.assertEqual(mock_copy.call_count, 2)
            # Should delete original
            mock_file.unlink.assert_called_once()
            
    def test_when_file_is_locked_then_skips_file(self):
        """Should skip files that are currently open/locked."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "locked.jpg"
        mock_file.is_file.return_value = True
        
        mock_both_path = MagicMock(spec=Path)
        mock_both_path.exists.return_value = True
        mock_both_path.glob.return_value = [mock_file]
        
        with patch.object(self.watcher, 'both_incoming', mock_both_path), \
             patch('builtins.open', side_effect=IOError("File is locked")), \
             patch('shutil.copy') as mock_copy:
            
            result = self.watcher.process_both_incoming()
            
            self.assertTrue(result)  # Found files, even if locked
            mock_copy.assert_not_called()  # Should not copy locked files
            mock_file.unlink.assert_not_called()  # Should not delete locked files
            
    # 3. File Processing Tests
    def test_when_processing_non_file_then_returns_false(self):
        """Should return False when path is not a file."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = False
        
        result = self.watcher.process_file(mock_path)
        self.assertFalse(result)
        
    def test_when_processing_zero_byte_file_then_returns_false(self):
        """Should return False for zero-byte files."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "empty.jpg"
        
        mock_stat = Mock()
        mock_stat.st_size = 0
        mock_path.stat.return_value = mock_stat
        
        result = self.watcher.process_file(mock_path)
        self.assertFalse(result)
        
    def test_when_processing_already_processed_file_then_returns_true(self):
        """Should return True for already processed files (with __LRE suffix)."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "test__LRE.jpg"
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_path.stat.return_value = mock_stat
        
        result = self.watcher.process_file(mock_path)
        self.assertTrue(result)
        
    def test_when_processing_jpeg_then_calls_jpeg_processor(self):
        """Should process JPEG files with JPEGExifProcessor."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "test.jpg"
        mock_path.suffix.lower.return_value = ".jpg"
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_path.stat.return_value = mock_stat
        
        with patch('incoming_watcher.JPEGExifProcessor') as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_image.return_value = Path("/test/processed.jpg")
            mock_processor_class.return_value = mock_processor
            
            result = self.watcher.process_file(mock_path)
            
            self.assertTrue(result)
            mock_processor_class.assert_called_once_with(str(mock_path), sequence="0001")
            mock_processor.process_image.assert_called_once()
            
    def test_when_processing_video_then_calls_video_processor(self):
        """Should process video files with VideoProcessor."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "test.mp4"
        mock_path.match.side_effect = lambda pattern: pattern == "*.mp4"
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_path.stat.return_value = mock_stat
        
        with patch('incoming_watcher.VideoProcessor') as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_video.return_value = True
            mock_processor.generate_filename.return_value = "test__LRE.mp4"
            mock_processor_class.return_value = mock_processor
            
            result = self.watcher.process_file(mock_path)
            
            self.assertTrue(result)
            mock_processor_class.assert_called_once_with(str(mock_path), sequence="0001")
            mock_processor.process_video.assert_called_once()
            
    def test_when_jpeg_processor_fails_with_not_ready_then_returns_false(self):
        """Should handle 'not ready for processing' errors gracefully."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "test.jpg"
        mock_path.suffix.lower.return_value = ".jpg"
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_path.stat.return_value = mock_stat
        
        with patch('incoming_watcher.JPEGExifProcessor') as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_image.side_effect = ValueError("File not ready for processing")
            mock_processor_class.return_value = mock_processor
            
            result = self.watcher.process_file(mock_path)
            
            self.assertFalse(result)
            
    def test_when_processing_unsupported_file_then_returns_false(self):
        """Should return False for unsupported file types."""
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = True
        mock_path.name = "test.txt"
        mock_path.suffix.lower.return_value = ".txt"
        mock_path.match.return_value = False  # No video pattern matches
        
        mock_stat = Mock()
        mock_stat.st_size = 1000
        mock_path.stat.return_value = mock_stat
        
        result = self.watcher.process_file(mock_path)
        self.assertFalse(result)
        
    # 4. Directory Checking Tests
    def test_when_directory_not_exists_then_returns_zero(self):
        """Should return 0 when directory doesn't exist."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = False
        
        result = self.watcher.check_directory(mock_dir)
        self.assertEqual(result, 0)
        
    def test_when_directory_has_files_then_processes_them(self):
        """Should process files found in directory."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "test_dir"
        
        mock_jpeg = MagicMock(spec=Path)
        mock_video = MagicMock(spec=Path)
        
        # Mock glob returns for different patterns
        def glob_side_effect(pattern):
            if pattern == '*.[Jj][Pp][Gg]':
                return [mock_jpeg]
            elif pattern in ['*.mp4', '*.mov', '*.m4v', '*.MP4', '*.MOV', '*.M4V']:
                if pattern == '*.mp4':
                    return [mock_video]
                return []
            return []
            
        mock_dir.glob.side_effect = glob_side_effect
        
        with patch.object(self.watcher, 'process_file', return_value=True) as mock_process:
            result = self.watcher.check_directory(mock_dir)
            
            self.assertEqual(result, 2)  # 1 JPEG + 1 video
            self.assertEqual(mock_process.call_count, 2)
            mock_process.assert_any_call(mock_jpeg)
            mock_process.assert_any_call(mock_video)
            
    def test_when_directory_empty_then_returns_zero(self):
        """Should return 0 when directory has no processable files."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.name = "empty_dir"
        mock_dir.glob.return_value = []  # No files
        
        result = self.watcher.check_directory(mock_dir)
        self.assertEqual(result, 0)
        
    # 5. Cycle Processing Tests
    def test_when_running_cycle_then_processes_both_and_directories(self):
        """Should process Both_Incoming and all incoming directories."""
        with patch.object(self.watcher, 'process_both_incoming', return_value=True) as mock_both, \
             patch.object(self.watcher, 'check_directory', return_value=2) as mock_check:
            
            self.watcher.run_cycle()
            
            mock_both.assert_called_once()
            self.assertEqual(mock_check.call_count, 2)  # Ron + Claudia directories
            
    def test_when_cycle_has_exception_then_handles_gracefully(self):
        """Should handle exceptions during cycle processing."""
        with patch.object(self.watcher, 'process_both_incoming', side_effect=Exception("Test error")):
            # Should not raise exception
            try:
                self.watcher.run_cycle()
            except Exception:
                self.fail("run_cycle should not raise exceptions")
                
    # 6. Integration Tests with Real Filesystem
    def test_integration_with_real_files(self):
        """Integration test with actual temporary files and directories."""
        # Create temporary directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test directories
            both_dir = temp_path / "both"
            ron_dir = temp_path / "ron"
            claudia_dir = temp_path / "claudia"
            
            both_dir.mkdir()
            ron_dir.mkdir()
            claudia_dir.mkdir()
            
            # Create a test file in Both_Incoming
            test_file = both_dir / "test.jpg"
            test_file.write_text("fake jpeg content")
            
            # Create watcher with temp directories
            watcher = IncomingWatcher(
                ron_incoming=str(ron_dir),
                claudia_incoming=str(claudia_dir),
                both_incoming=str(both_dir),
                sleep_time=1
            )
            
            # Process Both_Incoming
            result = watcher.process_both_incoming()
            
            # Verify file was distributed
            self.assertTrue(result)
            self.assertFalse(test_file.exists())  # Original deleted
            self.assertTrue((ron_dir / "test.jpg").exists())  # Copied to Ron
            self.assertTrue((claudia_dir / "test.jpg").exists())  # Copied to Claudia


if __name__ == '__main__':
    unittest.main()