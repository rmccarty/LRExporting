#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime

from processors.media_processor import MediaProcessor
from utils.exiftool import ExifTool

class TestMediaProcessor(MediaProcessor):
    """Concrete class for testing MediaProcessor."""
    def get_metadata_components(self):
        """Implementation of abstract method for testing."""
        return (
            self.exif_data.get('DateTimeOriginal', ''),
            self.exif_data.get('Title', ''),
            self.exif_data.get('Location', ''),
            self.exif_data.get('City', ''),
            self.exif_data.get('Country', '')
        )

class TestGenerateFilename(unittest.TestCase):
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)

    def test_when_only_date_then_returns_date_based_name(self):
        """Should generate filename with just date when only date is available"""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26'
        }
        expected = '2025_03_26__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_all_metadata_then_includes_all_components(self):
        """Should include all metadata components in filename when available"""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'Sunset View',
            'Location': 'Beach',
            'City': 'Miami',
            'Country': 'USA'
        }
        expected = '2025_03_26_Sunset_View_Beach_Miami_USA__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_no_date_then_uses_title_only(self):
        """Should use only title when no date is available"""
        self.processor.exif_data = {
            'Title': 'Sunset View'
        }
        result = self.processor.generate_filename()
        expected = 'Sunset_View__LRE.mov'
        self.assertEqual(result, expected)

    def test_when_no_metadata_then_uses_original_name(self):
        """Should use original filename with LRE suffix when no metadata is available"""
        self.processor.exif_data = {}
        result = self.processor.generate_filename()
        expected = 'test__LRE.mov'
        self.assertEqual(result, expected)

    def test_when_location_in_title_then_skips_duplicate(self):
        """Should skip location if it's already part of the title"""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'Miami Beach Sunset',
            'Location': 'Miami Beach',
            'City': 'Miami',
            'Country': 'USA'
        }
        expected = '2025_03_26_Miami_Beach_Sunset_USA__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_sequence_provided_then_includes_sequence(self):
        """Should include sequence number when provided"""
        self.processor = TestMediaProcessor(
            str(self.test_file),
            exiftool=self.mock_exiftool,
            sequence='001'
        )
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'Sunset'
        }
        expected = '2025_03_26_Sunset_001__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_components_need_cleaning_then_cleans_them(self):
        """Should clean filename components that contain invalid characters"""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'My Photo: A Nice/View?',
            'Location': 'Beach & Shore',
            'City': 'San Francisco/CA',
            'Country': 'USA!'
        }
        expected = '2025_03_26_My_Photo_A_Nice_View_Beach_Shore_San_Francisco_CA_USA__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_components_are_json_then_skips_them(self):
        """Should skip components that look like JSON"""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': '{"key": "value"}',
            'Location': '[1,2,3]',
            'City': 'Miami',
            'Country': 'USA'
        }
        expected = '2025_03_26_Miami_USA__LRE.mov'
        result = self.processor.generate_filename()
        self.assertEqual(result, expected)

    def test_when_components_too_long_then_truncates_them(self):
        """Should truncate components that are too long"""
        long_title = 'This_is_a_very_long_title_that_should_be_truncated_because_it_exceeds_the_maximum_length'
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': long_title,
            'City': 'Miami'
        }
        result = self.processor.generate_filename()
        self.assertLess(len(result), 255)  # Standard filesystem limit
        self.assertTrue(result.startswith('2025_03_26_This_is_a_very_long_title'))
        self.assertTrue(result.endswith('__LRE.mov'))

class TestMetadataExtraction(unittest.TestCase):
    """Tests for metadata extraction methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)

    def test_when_reading_exif_title_with_group_prefix_then_returns_title(self):
        """Should extract title from EXIF data with group prefix."""
        self.processor.exif_data = {
            'XMP:Title': 'My Title',
            'IPTC:Title': 'Wrong Title'
        }
        result = self.processor.get_exif_title()
        self.assertEqual(result, 'My Title')

    def test_when_no_title_found_then_generates_from_location(self):
        """Should generate title from location when no title found."""
        self.processor.exif_data = {
            'XMP:Location': 'Beach',
            'XMP:City': 'Miami',
            'XMP:Country': 'USA'
        }
        result = self.processor.get_exif_title()
        self.assertEqual(result, 'Beach Miami USA')

    def test_when_getting_location_data_then_returns_tuple(self):
        """Should return location data as tuple."""
        self.processor.exif_data = {
            'XMP:Location': 'Beach',
            'XMP:City': 'Miami',
            'XMP:Country': 'USA'
        }
        location, city, country = self.processor.get_location_data()
        self.assertEqual(location, 'Beach')
        self.assertEqual(city, 'Miami')
        self.assertEqual(country, 'USA')

    def test_when_location_data_missing_then_returns_empty_strings(self):
        """Should return empty strings for missing location data."""
        self.processor.exif_data = {}
        location, city, country = self.processor.get_location_data()
        self.assertEqual(location, '')
        self.assertEqual(city, '')
        self.assertEqual(country, '')

    def test_when_generating_title_with_partial_location_then_uses_available_parts(self):
        """Should generate title using available location parts."""
        self.processor.exif_data = {
            'XMP:City': 'Miami',
            'XMP:Country': 'USA'
        }
        result = self.processor.generate_title()
        self.assertEqual(result, 'Miami USA')

    def test_when_no_location_data_then_returns_empty_title(self):
        """Should return empty string when no location data available."""
        self.processor.exif_data = {}
        result = self.processor.generate_title()
        self.assertEqual(result, '')

class TestRatingHandling(unittest.TestCase):
    """Tests for rating-related methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)

    def test_when_rating_missing_then_returns_zero(self):
        """Should return 0 when rating is missing."""
        self.processor.exif_data = {}
        result = self.processor.get_image_rating()
        self.assertEqual(result, 0)

    def test_when_rating_invalid_then_returns_zero(self):
        """Should return 0 when rating is invalid."""
        self.processor.exif_data = {'Rating': 'invalid'}
        result = self.processor.get_image_rating()
        self.assertEqual(result, 0)

class TestKeywordHandling(unittest.TestCase):
    """Tests for keyword-related methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)
        self.today = datetime.now().strftime('%Y_%m_%d')

class TestFileOperations(unittest.TestCase):
    """Tests for file operation methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)

    @patch('pathlib.Path.rename')
    def test_when_renaming_file_then_returns_new_path(self, mock_rename):
        """Should return new path when rename succeeds."""
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'Test'
        }
        new_path = self.processor.rename_file()
        self.assertIsNotNone(new_path)
        mock_rename.assert_called_once()

    @patch('pathlib.Path.rename')
    def test_when_rename_fails_then_returns_original_path(self, mock_rename):
        """Should return original path when rename fails."""
        mock_rename.side_effect = OSError("Failed to rename")
        self.processor.exif_data = {
            'DateTimeOriginal': '2025_03_26',
            'Title': 'Test'
        }
        new_path = self.processor.rename_file()
        self.assertEqual(new_path, self.test_file)

    @patch('pathlib.Path.rename')
    def test_when_no_metadata_then_renames_with_lre_suffix(self, mock_rename):
        """Should rename file with just LRE suffix when no metadata."""
        self.processor.exif_data = {}
        new_path = self.processor.rename_file()
        expected = self.test_file.parent / 'test__LRE.mov'
        mock_rename.assert_called_once_with(expected)

if __name__ == '__main__':
    unittest.main()
