#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import shutil
import logging

from watchers.image_watcher import ImageWatcher

class TestImageWatcher(unittest.TestCase):
    """Test cases for ImageWatcher class."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dirs = ['/test/dir1', '/test/dir2']
        self.both_incoming = '/test/both_incoming'
        
    def test_when_initializing_then_sets_directories(self):
        """Should properly initialize directories and both_incoming."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        self.assertEqual(len(self.watcher.directories), 2)
        self.assertEqual(str(self.watcher.directories[0]), self.test_dirs[0])
        self.assertEqual(str(self.watcher.directories[1]), self.test_dirs[1])
        self.assertEqual(str(self.watcher.both_incoming), self.both_incoming)
        
    def test_when_initializing_without_both_incoming_then_sets_none(self):
        """Should set both_incoming to None when not provided."""
        watcher = ImageWatcher(self.test_dirs)
        self.assertIsNone(watcher.both_incoming)
        
    def test_when_processing_both_incoming_with_no_dir_then_returns_false(self):
        """Should return False when both_incoming is not set."""
        watcher = ImageWatcher(self.test_dirs)  # No both_incoming
        self.assertFalse(watcher.process_both_incoming())
        
    @patch('pathlib.Path.glob')
    @patch('pathlib.Path.unlink')
    @patch('shutil.copy')
    def test_when_processing_both_incoming_then_copies_and_deletes(self, mock_copy, mock_unlink, mock_glob):
        """Should copy files to all directories and delete originals."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
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
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
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
            expected_msg = f"WARNING:watchers.image_watcher:File test.jpg is currently open. Skipping copy."
            self.assertIn(expected_msg, log.output)
            
    @patch('pathlib.Path.glob')
    def test_when_processing_both_incoming_with_error_then_logs(self, mock_glob):
        """Should log error and continue when exception occurs."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        mock_glob.side_effect = Exception("Test error")
        
        with self.assertLogs(level='ERROR') as log:
            found = self.watcher.process_both_incoming()
            
            self.assertFalse(found)
            # Print log messages for debugging
            print("\nLog messages:")
            for msg in log.output:
                print(f"  {msg}")
            # Verify error was logged with exact message
            expected_msg = f"ERROR:watchers.image_watcher:Error processing Both_Incoming: Test error"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_lre_file_then_skips(self):
        """Should skip files with __LRE in name."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        file = Mock(spec=Path)
        file.name = 'test__LRE.jpg'
        
        with patch.object(logging.getLogger(), 'info') as mock_log:
            self.watcher.process_file(file)
            mock_log.assert_not_called()
            
    def test_when_processing_zero_byte_file_then_logs_warning(self):
        """Should log warning for zero-byte files."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
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
            expected_msg = f"WARNING:watchers.image_watcher:Skipping zero-byte file: /test/dir/test.jpg"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_file_then_processes_successfully(self):
        """Should process valid files successfully."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
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
            expected_msg = f"INFO:watchers.image_watcher:Image processed successfully: {new_path}"
            self.assertIn(expected_msg, log.output)
            
    def test_when_processing_file_with_error_then_logs_error(self):
        """Should log error when processing fails."""
        # Arrange
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = "test.jpg"
        mock_file.__str__.return_value = "/test/dir/test.jpg"
        mock_file.parent = Path("/test/dir")  # Not in APPLE_PHOTOS_PATHS
        mock_file.suffix = ".jpg"
        
        with patch('processors.jpeg_processor.JPEGExifProcessor.__init__', return_value=None) as mock_init, \
             patch('processors.jpeg_processor.JPEGExifProcessor.process_image') as mock_process:
            mock_init.return_value = None
            mock_process.side_effect = Exception("Test error")
            
            # Act
            with self.assertLogs(logger='watchers.image_watcher', level='ERROR') as log:
                self.watcher.process_file(mock_file)
                
            # Assert
            expected_msg = f"ERROR:watchers.image_watcher:Error processing file {mock_file}: Test error"
            self.assertIn(expected_msg, log.output)
            
    def test_when_checking_nonexistent_directory_then_returns(self):
        """Should return early for non-existent directories."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.glob') as mock_glob:
            self.watcher.check_directory('/nonexistent')
            mock_glob.assert_not_called()
            
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.glob')
    def test_when_checking_directory_then_processes_jpeg_files(self, mock_glob, mock_exists):
        """Should process all JPEG files in directory."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        mock_file = Mock(spec=Path)
        mock_file.name = 'test.jpg'
        mock_glob.return_value = [mock_file]
        
        with patch.object(self.watcher, 'process_file') as mock_process:
            self.watcher.check_directory('/test/dir')
            mock_process.assert_called_once_with(mock_file)
            
    def test_when_starting_watcher_then_starts_and_stops(self):
        """Should properly start and stop the watcher."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        # Verify watcher starts correctly
        self.watcher.running = True
        self.assertTrue(self.watcher.running)
        
        # Verify watcher stops correctly
        self.watcher.running = False
        self.assertFalse(self.watcher.running)
            
    @patch('watchers.image_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos1'), Path('/test/photos2')])
    def test_when_checking_apple_photos_dirs_then_logs_directories(self):
        """Should log each Apple Photos directory being checked."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.iterdir', return_value=[]), \
             self.assertLogs(level='INFO') as log:
            self.watcher.check_apple_photos_dirs()
            
            # Should log each directory
            self.assertIn('INFO:watchers.image_watcher:Checking /test/photos1 for new media files...', log.output)
            self.assertIn('INFO:watchers.image_watcher:Checking /test/photos2 for new media files...', log.output)

    def test_when_processing_non_file_then_returns_early(self):
        """Should return early when path is not a file."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        mock_path = MagicMock(spec=Path)
        mock_path.is_file.return_value = False
        
        with patch.object(self.watcher.logger, 'info') as mock_log:
            self.watcher.process_file(mock_path)
            mock_log.assert_not_called()

    @patch('watchers.image_watcher.ENABLE_APPLE_PHOTOS', True)
    @patch('watchers.image_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos')])
    def test_when_processing_apple_photos_jpeg_with_category_then_transfers(self):
        """Should process JPEG in Apple Photos directory with category format."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.jpg'
        mock_file.suffix = '.jpg'
        mock_file.__str__.return_value = '/test/photos/test.jpg'
        mock_file.parent = Path('/test/photos')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            # Mock processor to return title with category format
            mock_processor = MagicMock()
            mock_processor.get_metadata_components.return_value = (None, 'US CA: Test Title', None, None, None, None)
            mock_processor_cls.return_value = mock_processor
            
            self.watcher.process_file(mock_file)
            
            # Should extract metadata
            mock_processor_cls.assert_called_once_with(str(mock_file))
            mock_processor.get_metadata_components.assert_called_once()
            
            # Should transfer file
            mock_transfer.assert_called_once_with(mock_file)
            
            # Verify logging
            self.assertIn('INFO:watchers.image_watcher:Found file in Apple Photos directory: /test/photos/test.jpg', log.output)
            self.assertIn("INFO:watchers.image_watcher:Extracted title: 'US CA: Test Title'", log.output)
            self.assertIn("INFO:watchers.image_watcher:Title 'US CA: Test Title' has category format - importing to Apple Photos Watcher album", log.output)

    @patch('watchers.image_watcher.ENABLE_APPLE_PHOTOS', True)
    @patch('watchers.image_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos')])
    def test_when_processing_apple_photos_jpeg_without_category_then_transfers(self):
        """Should process JPEG in Apple Photos directory without category format."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.jpg'
        mock_file.suffix = '.jpg'
        mock_file.__str__.return_value = '/test/photos/test.jpg'
        mock_file.parent = Path('/test/photos')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            # Mock processor to return title without category format
            mock_processor = MagicMock()
            mock_processor.get_metadata_components.return_value = (None, 'Regular Title', None, None, None, None)
            mock_processor_cls.return_value = mock_processor
            
            self.watcher.process_file(mock_file)
            
            # Should transfer file
            mock_transfer.assert_called_once_with(mock_file)
            
            # Verify logging
            self.assertIn("INFO:watchers.image_watcher:Title 'Regular Title' does not have category format - importing to Apple Photos Watcher album", log.output)

    @patch('watchers.image_watcher.ENABLE_APPLE_PHOTOS', True)
    @patch('watchers.image_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos')])
    def test_when_processing_apple_photos_video_then_transfers_without_metadata(self):
        """Should process video in Apple Photos directory without metadata extraction."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.mp4'
        mock_file.suffix = '.mp4'
        mock_file.__str__.return_value = '/test/photos/test.mp4'
        mock_file.parent = Path('/test/photos')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            self.watcher.process_file(mock_file)
            
            # Should not extract metadata for video
            mock_processor_cls.assert_not_called()
            
            # Should transfer file
            mock_transfer.assert_called_once_with(mock_file)
            
            # Verify logging
            self.assertIn('INFO:watchers.image_watcher:Video file - no metadata extraction in this flow', log.output)

    def test_when_processing_regular_jpeg_with_category_title_then_transfers_processed_file(self):
        """Should process regular JPEG file and transfer with category format."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.jpg'
        mock_file.suffix = '.jpg'
        mock_file.__str__.return_value = '/test/dir/test.jpg'
        mock_file.parent = Path('/test/dir')
        
        new_path = Path('/test/dir/test__LRE.jpg')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher, '_get_next_sequence', return_value=42), \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            # First processor for processing
            mock_processor1 = MagicMock()
            mock_processor1.process_image.return_value = new_path
            
            # Second processor for title extraction
            mock_processor2 = MagicMock()
            mock_processor2.get_metadata_components.return_value = (None, 'US TX: Category Title', None, None, None, None)
            
            mock_processor_cls.side_effect = [mock_processor1, mock_processor2]
            
            self.watcher.process_file(mock_file)
            
            # Should process and extract metadata
            self.assertEqual(mock_processor_cls.call_count, 2)
            mock_processor_cls.assert_any_call(str(mock_file), sequence=42)
            mock_processor_cls.assert_any_call(str(new_path))
            
            # Should transfer processed file
            mock_transfer.assert_called_once_with(new_path)
            
            # Verify logging
            self.assertIn("INFO:watchers.image_watcher:Extracted title: 'US TX: Category Title'", log.output)
            self.assertIn("INFO:watchers.image_watcher:Title 'US TX: Category Title' has category format - importing to Apple Photos Watcher album", log.output)

    def test_when_processing_regular_jpeg_without_category_title_then_transfers(self):
        """Should process regular JPEG file and transfer without category format."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.jpg'
        mock_file.suffix = '.jpg'
        mock_file.__str__.return_value = '/test/dir/test.jpg'
        mock_file.parent = Path('/test/dir')
        
        new_path = Path('/test/dir/test__LRE.jpg')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher, '_get_next_sequence', return_value=42), \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            # First processor for processing
            mock_processor1 = MagicMock()
            mock_processor1.process_image.return_value = new_path
            
            # Second processor for title extraction
            mock_processor2 = MagicMock()
            mock_processor2.get_metadata_components.return_value = (None, 'No Category', None, None, None, None)
            
            mock_processor_cls.side_effect = [mock_processor1, mock_processor2]
            
            self.watcher.process_file(mock_file)
            
            # Should transfer processed file
            mock_transfer.assert_called_once_with(new_path)
            
            # Verify logging
            self.assertIn("INFO:watchers.image_watcher:Title 'No Category' does not have category format - importing to Apple Photos Watcher album", log.output)

    def test_when_processing_regular_video_then_transfers_without_processing(self):
        """Should transfer video files without processing."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.return_value = Mock(st_size=100)
        mock_file.name = 'test.mp4'
        mock_file.suffix = '.mp4'
        mock_file.__str__.return_value = '/test/dir/test.mp4'
        mock_file.parent = Path('/test/dir')
        
        with patch('watchers.image_watcher.JPEGExifProcessor') as mock_processor_cls, \
             patch.object(self.watcher.transfer, 'transfer_file') as mock_transfer, \
             self.assertLogs(level='INFO') as log:
            
            self.watcher.process_file(mock_file)
            
            # Should not process video
            mock_processor_cls.assert_not_called()
            
            # Should transfer original file
            mock_transfer.assert_called_once_with(mock_file)
            
            # Verify logging
            self.assertIn('INFO:watchers.image_watcher:Video file - no metadata extraction in this flow', log.output)

    @patch('watchers.image_watcher.ENABLE_APPLE_PHOTOS', False)
    def test_when_apple_photos_disabled_then_logs_and_returns(self):
        """Should log and return when Apple Photos is disabled."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        with patch.object(self.watcher, 'check_directory') as mock_check, \
             self.assertLogs(level='INFO') as log:
            
            self.watcher.check_apple_photos_dirs()
            
            # Should not check any directories
            mock_check.assert_not_called()
            
            # Verify logging
            self.assertIn('INFO:watchers.image_watcher:Apple Photos processing is disabled. Skipping checks.', log.output)

    @patch('watchers.image_watcher.APPLE_PHOTOS_PATHS', [Path('/test/photos')])
    @patch('watchers.image_watcher.ALL_PATTERN', ['*.jpg', '*.mp4'])
    def test_when_checking_apple_photos_directory_then_processes_all_patterns(self):
        """Should process all file patterns in Apple Photos directories."""
        self.watcher = ImageWatcher(self.test_dirs, self.both_incoming)
        
        mock_jpg = MagicMock(spec=Path)
        mock_jpg.name = 'photo.jpg'
        mock_mp4 = MagicMock(spec=Path)
        mock_mp4.name = 'video.mp4'
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.glob') as mock_glob, \
             patch.object(self.watcher, 'process_file') as mock_process, \
             self.assertLogs(level='DEBUG') as log:
            
            def glob_side_effect(pattern):
                if pattern == '*.jpg':
                    return [mock_jpg]
                elif pattern == '*.mp4':
                    return [mock_mp4]
                return []
            
            mock_glob.side_effect = glob_side_effect
            
            self.watcher.check_directory(Path('/test/photos'))
            
            # Should process both files
            self.assertEqual(mock_process.call_count, 2)
            mock_process.assert_any_call(mock_jpg)
            mock_process.assert_any_call(mock_mp4)
            
            # Verify debug logging
            self.assertIn('DEBUG:watchers.image_watcher:Looking for patterns: [\'*.jpg\', \'*.mp4\']', log.output)
            # Should log found files (using mock objects)
            found_files = [msg for msg in log.output if 'Found file:' in msg]
            self.assertEqual(len(found_files), 2)

if __name__ == '__main__':
    unittest.main()
