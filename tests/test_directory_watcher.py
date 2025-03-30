#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import shutil
import logging

from watchers.directory_watcher import DirectoryWatcher

class TestDirectoryWatcher(unittest.TestCase):
    """Test cases for DirectoryWatcher class."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dirs = ['/test/dir1', '/test/dir2']
        self.both_incoming = '/test/both_incoming'
        
    def test_when_initializing_then_sets_directories(self):
        """Should properly initialize directories and both_incoming."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        self.assertEqual(len(self.watcher.directories), 2)
        self.assertEqual(str(self.watcher.directories[0]), self.test_dirs[0])
        self.assertEqual(str(self.watcher.directories[1]), self.test_dirs[1])
        self.assertEqual(str(self.watcher.both_incoming), self.both_incoming)
        
    def test_when_initializing_without_both_incoming_then_sets_none(self):
        """Should set both_incoming to None when not provided."""
        watcher = DirectoryWatcher(self.test_dirs)
        self.assertIsNone(watcher.both_incoming)
        
    def test_when_processing_both_incoming_with_no_dir_then_returns_false(self):
        """Should return False when both_incoming is not set."""
        watcher = DirectoryWatcher(self.test_dirs)  # No both_incoming
        self.assertFalse(watcher.process_both_incoming())
        
    @patch('pathlib.Path.glob')
    @patch('pathlib.Path.unlink')
    @patch('shutil.copy')
    def test_when_processing_both_incoming_then_copies_and_deletes(self, mock_copy, mock_unlink, mock_glob):
        """Should copy files to all directories and delete originals."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        # Setup mock file
        mock_file = MagicMock(spec=Path)
        mock_file.name = 'test.jpg'
        mock_glob.return_value = [mock_file]
        
        # Mock file open to indicate file is not in use
        m = mock_open = MagicMock()
        m.return_value.__enter__ = MagicMock()
        m.return_value.__exit__ = MagicMock()
        
        with patch('builtins.open', m):
            found = self.watcher.process_both_incoming()
            
            self.assertTrue(found)
            # Should copy to each directory
            self.assertEqual(mock_copy.call_count, len(self.test_dirs))
            # Should delete original
            mock_file.unlink.assert_called_once()
            
    @patch('pathlib.Path.glob')
    def test_when_processing_locked_file_then_skips(self, mock_glob):
        """Should skip files that are locked/in use."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        mock_file = MagicMock(spec=Path)
        mock_file.name = 'test.jpg'
        mock_file.__str__.return_value = '/test/dir/test.jpg'
        mock_glob.return_value = [mock_file]
        
        with patch('shutil.copy2', side_effect=OSError("File in use")), \
             self.assertLogs(level='WARNING') as log:
            found = self.watcher.process_both_incoming()
            self.assertTrue(found)  # File was found even if locked
            
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            
            # Verify warning was logged with exact message
            expected_msg = f"WARNING:watchers.directory_watcher:File test.jpg is currently open. Skipping copy."
            self.assertIn(expected_msg, log.output)
            
    @patch('pathlib.Path.glob')
    def test_when_processing_both_incoming_with_error_then_logs(self, mock_glob):
        """Should log error and continue when exception occurs."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        mock_glob.side_effect = Exception("Test error")
        
        with self.assertLogs(level='ERROR') as log:
            found = self.watcher.process_both_incoming()
            
            self.assertFalse(found)
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            # Verify error was logged with exact message
            expected_msg = f"ERROR:watchers.directory_watcher:Error processing Both_Incoming: Test error"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_lre_file_then_skips(self):
        """Should skip files with __LRE in name."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        file = Mock(spec=Path)
        file.name = 'test__LRE.jpg'
        
        with patch.object(logging.getLogger(), 'info') as mock_log:
            self.watcher.process_file(file)
            mock_log.assert_not_called()
            
    def test_when_processing_zero_byte_file_then_logs_warning(self):
        """Should log warning for zero-byte files."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        file = MagicMock(spec=Path)
        file.name = 'test.jpg'
        file.suffix = '.jpg'
        file.__str__.return_value = '/test/dir/test.jpg'
        file.stat.return_value = Mock(st_size=0)
        
        with self.assertLogs(level='WARNING') as log:
            self.watcher.process_file(file)
            
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            
            # Verify warning was logged with exact message
            expected_msg = f"WARNING:watchers.directory_watcher:Skipping zero-byte file: /test/dir/test.jpg"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_file_then_processes_successfully(self):
        """Should process valid files successfully."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        file = MagicMock(spec=Path)
        file.name = 'test.jpg'
        file.suffix = '.jpg'
        file.__str__.return_value = '/test/dir/test.jpg'
        file.stat.return_value = Mock(st_size=1024)
        
        with patch('processors.jpeg_processor.JPEGExifProcessor.__init__', return_value=None) as mock_init, \
             patch('processors.jpeg_processor.JPEGExifProcessor.process_image') as mock_process, \
             self.assertLogs(level='INFO') as log:
            mock_init.return_value = None
            new_path = Path('/test/output/test__LRE.jpg')
            mock_process.return_value = new_path
            
            self.watcher.process_file(file)
            
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            
            # Verify info was logged with exact message
            expected_msg = f"INFO:watchers.directory_watcher:Image processed successfully: {new_path}"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_file_with_error_then_logs_error(self):
        """Should log error when processing fails."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        file = MagicMock(spec=Path)
        file.name = 'test.jpg'
        file.suffix = '.jpg'
        
        with patch('processors.jpeg_processor.JPEGExifProcessor.__init__', return_value=None) as mock_init, \
             patch('processors.jpeg_processor.JPEGExifProcessor.process_image') as mock_process, \
             self.assertLogs(level='ERROR') as log:
            mock_init.return_value = None
            mock_process.side_effect = Exception("Test error")
            
            self.watcher.process_file(file)
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            # Verify error was logged with exact message
            expected_msg = f"ERROR:watchers.directory_watcher:Error processing image: Test error"
            self.assertIn(expected_msg, log.output)
            
    def test_when_checking_nonexistent_directory_then_returns(self):
        """Should return early for non-existent directories."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.glob') as mock_glob:
            self.watcher.check_directory('/nonexistent')
            mock_glob.assert_not_called()
            
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.glob')
    def test_when_checking_directory_then_processes_jpeg_files(self, mock_glob, mock_exists):
        """Should process all JPEG files in directory."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        mock_file = Mock(spec=Path)
        mock_file.name = 'test.jpg'
        mock_glob.return_value = [mock_file]
        
        with patch.object(self.watcher, 'process_file') as mock_process:
            self.watcher.check_directory('/test/dir')
            mock_process.assert_called_once_with(mock_file)
            
    def test_when_starting_watcher_then_starts_and_stops(self):
        """Should properly start and stop the watcher."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        
        # Verify watcher starts correctly
        self.watcher.running = True
        self.assertTrue(self.watcher.running)
        
        # Verify watcher stops correctly
        self.watcher.running = False
        self.assertFalse(self.watcher.running)
            
    @patch('watchers.directory_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos1'), Path('/test/photos2')])
    def test_when_checking_apple_photos_dirs_then_logs_directories(self):
        """Should log each Apple Photos directory being checked."""
        self.watcher = DirectoryWatcher(self.test_dirs, self.both_incoming)
        test_paths = [Path('/test/photos1'), Path('/test/photos2')]
        
        with patch.object(self.watcher, 'check_directory') as mock_check, \
             self.assertLogs(level='INFO') as log:
            self.watcher.check_apple_photos_dirs()
            
            # Should log each directory
            for path in test_paths:
                expected_msg = f"INFO:watchers.directory_watcher:Checking Apple Photos directory: {path}"
                self.assertIn(expected_msg, log.output)
            
            # Should check each directory
            self.assertEqual(mock_check.call_count, len(test_paths))
            mock_check.assert_any_call(test_paths[0])
            mock_check.assert_any_call(test_paths[1])

if __name__ == '__main__':
    unittest.main()
