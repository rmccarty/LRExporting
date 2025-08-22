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
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "State", "Country")):
             
            self.processor.exif_data = {'EXIF:DateTimeOriginal': test_date}
            date, title, location, city, state, country = self.processor.get_metadata_components()
            
            self.assertEqual(date, expected_date)
            self.assertEqual(title, "Test Title")
            self.assertEqual(location, "Location")
            self.assertEqual(city, "City")
            self.assertEqual(state, "State")
            self.assertEqual(country, "Country")
            
    def test_when_getting_metadata_with_invalid_date_then_returns_none(self):
        """Should return None for date when date format is invalid."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "State", "Country")):
             
            # Test with invalid date format that will fail the split
            self.processor.exif_data = {'EXIF:DateTimeOriginal': "invalid"}  # No spaces or colons
            date, title, location, city, state, country = self.processor.get_metadata_components()
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

    def test_when_exif_data_empty_then_calls_read_exif(self):
        """Should call read_exif when exif_data is empty (line 44)."""
        # Ensure exif_data is empty
        self.processor.exif_data = None
        
        with patch.object(self.processor, 'read_exif') as mock_read, \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "State", "Country")):
            
            # Mock exif_data after read_exif is called
            def set_exif_data():
                self.processor.exif_data = {'EXIF:DateTimeOriginal': '2024:01:01 12:00:00'}
            mock_read.side_effect = set_exif_data
            
            self.processor.get_metadata_components()
            mock_read.assert_called_once()


    def test_when_date_has_wrong_parts_count_then_logs_error_and_returns_none(self):
        """Should log error and return None when date has wrong number of parts (lines 58-59)."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Location", "City", "State", "Country")), \
             patch.object(self.processor.logger, 'error') as mock_log:
            
            # Date with wrong number of parts (only 2 parts instead of 3)
            self.processor.exif_data = {'EXIF:DateTimeOriginal': '2024:01 12:00:00'}
            
            date, title, location, city, state, country = self.processor.get_metadata_components()
            
            self.assertIsNone(date)
            mock_log.assert_any_call("Invalid date format: 2024:01 12:00:00")

    def test_when_getting_location_data_then_logs_city_and_state(self):
        """Should log city and state information (lines 68-69)."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Test Location", "Test City", "Test State", "Test Country")), \
             patch.object(self.processor.logger, 'info') as mock_log:
            
            self.processor.exif_data = {'EXIF:DateTimeOriginal': '2024:01:01 12:00:00'}
            
            date, title, location, city, state, country = self.processor.get_metadata_components()
            
            # Verify logging calls for city and state (lines 68-69)
            mock_log.assert_any_call("Extracted city from EXIF: Test City")
            mock_log.assert_any_call("Extracted state from EXIF: Test State")

    def test_when_get_metadata_components_returns_all_values(self):
        """Should return all 6 values including state (line 71)."""
        with patch.object(self.processor, 'read_exif'), \
             patch.object(self.processor, 'get_exif_title', return_value="Test Title"), \
             patch.object(self.processor, 'get_location_data', return_value=("Test Location", "Test City", "Test State", "Test Country")):
            
            self.processor.exif_data = {'EXIF:DateTimeOriginal': '2024:01:01 12:00:00'}
            
            result = self.processor.get_metadata_components()
            
            # Should return tuple with 6 elements (line 71)
            self.assertEqual(len(result), 6)
            date, title, location, city, state, country = result
            self.assertEqual(date, "2024_01_01")
            self.assertEqual(title, "Test Title")
            self.assertEqual(location, "Test Location")
            self.assertEqual(city, "Test City")
            self.assertEqual(state, "Test State")
            self.assertEqual(country, "Test Country")

if __name__ == '__main__':
    unittest.main()
