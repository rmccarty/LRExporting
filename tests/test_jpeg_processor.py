#!/usr/bin/env python3

import unittest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import subprocess

from processors.jpeg_processor import JPEGExifProcessor

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
        
    def test_when_processing_new_file_then_renames(self):
        """Should rename new files with LRE suffix."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'rename_file', return_value=self.test_file):
             
            result = self.processor.process_image()
            self.assertEqual(result, self.test_file)

if __name__ == '__main__':
    unittest.main()
