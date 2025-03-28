#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import subprocess
from PIL import Image
import io

from processors.jpeg_processor import JPEGExifProcessor
from config import JPEG_QUALITY

class TestJPEGExifProcessor(unittest.TestCase):
    def setUp(self):
        self.test_file = Path('/test/input/photo.jpg')
        self.test_output = Path('/test/output')
        self.processor = JPEGExifProcessor(str(self.test_file), str(self.test_output))
        
    def test_when_initializing_with_non_jpeg_then_exits(self):
        """Should exit when file is not a JPEG."""
        with self.assertRaises(SystemExit):
            JPEGExifProcessor('/test/input/file.png')
            
    def test_when_initializing_without_output_then_uses_input_dir(self):
        """Should use input directory as output when no output specified."""
        processor = JPEGExifProcessor(str(self.test_file))
        self.assertEqual(processor.output_path, self.test_file.parent)
        
    def test_when_compressing_image_then_preserves_metadata(self):
        """Should compress image while preserving metadata."""
        # Mock PIL Image
        mock_image = MagicMock()
        mock_image.mode = 'RGB'
        
        # Mock PIL open context
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_image
        
        with patch('PIL.Image.open', return_value=mock_context) as mock_open, \
             patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink'), \
             patch('pathlib.Path.replace'), \
             patch.object(self.processor.exiftool, 'copy_metadata', return_value=True):
             
            result = self.processor.compress_image()
            
            self.assertTrue(result)
            mock_image.save.assert_called_once_with(
                self.processor.file_path.with_stem(self.processor.file_path.stem + '_temp'),
                'JPEG',
                quality=JPEG_QUALITY,
                optimize=True
            )
            
    def test_when_compressing_rgba_image_then_converts_to_rgb(self):
        """Should convert RGBA images to RGB before compressing."""
        # Mock PIL Image
        mock_image = MagicMock()
        mock_image.mode = 'RGBA'
        
        # Mock PIL open context
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_image
        
        with patch('PIL.Image.open', return_value=mock_context) as mock_open, \
             patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink'), \
             patch('pathlib.Path.replace'), \
             patch.object(self.processor.exiftool, 'copy_metadata', return_value=True):
             
            result = self.processor.compress_image()
            
            self.assertTrue(result)
            mock_image.convert.assert_called_once_with('RGB')
            
    def test_when_compressing_fails_then_cleans_up(self):
        """Should clean up temporary file when compression fails."""
        with patch('PIL.Image.open', side_effect=Exception("Test error")), \
             patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink') as mock_unlink:
             
            result = self.processor.compress_image()
            
            self.assertFalse(result)
            mock_unlink.assert_called_once()
            
    def test_when_getting_metadata_components_then_parses_date(self):
        """Should correctly parse date from metadata."""
        test_date = "2024:03:28 15:30:00"
        expected_date = "2024_03_28"
        
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "Country")):
             
            self.processor.exif_data = {'EXIF:DateTimeOriginal': test_date}
            date, title, location, city, country = self.processor.get_metadata_components()
            
            self.assertEqual(date, expected_date)
            self.assertEqual(title, "Test Title")
            self.assertEqual(location, "Location")
            self.assertEqual(city, "City")
            self.assertEqual(country, "Country")
            
    def test_when_getting_metadata_with_invalid_date_then_returns_none(self):
        """Should return None for date when date format is invalid."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "Country")):
             
            # Test with invalid date format that will fail the split
            self.processor.exif_data = {'EXIF:DateTimeOriginal': "invalid"}  # No spaces or colons
            date, title, location, city, country = self.processor.get_metadata_components()
            self.assertIsNone(date)
            
    def test_when_processing_already_processed_file_then_skips(self):
        """Should skip processing if file already has __LRE suffix."""
        processed_file = Path('/test/input/photo__LRE.jpg')
        processor = JPEGExifProcessor(str(processed_file))
        
        result = processor.process_image()
        
        self.assertEqual(result, processed_file)
        
    def test_when_processing_new_file_then_sets_title_if_none(self):
        """Should set title if one doesn't exist."""
        test_title = "Test Title"
        
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value=test_title), \
             patch.object(self.processor, 'update_keywords_with_rating_and_export_tags'), \
             patch.object(self.processor, 'rename_file', return_value=self.test_file), \
             patch('subprocess.run') as mock_run:
             
            self.processor.exif_data = {}  # No existing title
            result = self.processor.process_image()
            
            self.assertEqual(result, self.test_file)
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            self.assertIn(f'-Title={test_title}', cmd_args)
            
    def test_when_processing_with_compression_enabled_then_compresses(self):
        """Should compress image when JPEG_COMPRESS is True."""
        with patch('processors.jpeg_processor.JPEG_COMPRESS', True), \
             patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value=None), \
             patch.object(self.processor, 'update_keywords_with_rating_and_export_tags'), \
             patch.object(self.processor, 'rename_file', return_value=self.test_file), \
             patch.object(self.processor, 'compress_image') as mock_compress:
             
            result = self.processor.process_image()
            
            self.assertEqual(result, self.test_file)
            mock_compress.assert_called_once()
            
    def test_when_processing_with_compression_disabled_then_skips_compression(self):
        """Should skip compression when JPEG_COMPRESS is False."""
        with patch('processors.jpeg_processor.JPEG_COMPRESS', False), \
             patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value=None), \
             patch.object(self.processor, 'update_keywords_with_rating_and_export_tags'), \
             patch.object(self.processor, 'rename_file', return_value=self.test_file), \
             patch.object(self.processor, 'compress_image') as mock_compress:
             
            result = self.processor.process_image()
            
            self.assertEqual(result, self.test_file)
            mock_compress.assert_not_called()

if __name__ == '__main__':
    unittest.main()
