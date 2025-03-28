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

    def test_when_no_date_then_returns_none(self):
        """Should return None when no date is available"""
        self.processor.exif_data = {
            'Title': 'Sunset View'
        }
        result = self.processor.generate_filename()
        self.assertIsNone(result)

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
            'Title': '{"title": "Bad Title"}',
            'Location': '[1, 2, 3]',
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

    def test_when_getting_valid_rating_then_returns_integer(self):
        """Should return integer rating when valid."""
        self.processor.exif_data = {'Rating': '4'}
        result = self.processor.get_image_rating()
        self.assertEqual(result, 4)

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

    def test_when_translating_rating_zero_then_returns_zero_star(self):
        """Should return '0-star' for rating 0 or 1."""
        self.assertEqual(self.processor.translate_rating_to_keyword(0), '0-star')
        self.assertEqual(self.processor.translate_rating_to_keyword(1), '0-star')

    def test_when_translating_rating_above_one_then_returns_n_minus_one_star(self):
        """Should return correct star rating for ratings above 1."""
        self.assertEqual(self.processor.translate_rating_to_keyword(2), '1-star')
        self.assertEqual(self.processor.translate_rating_to_keyword(5), '4-star')

class TestKeywordHandling(unittest.TestCase):
    """Tests for keyword-related methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)
        self.today = datetime.now().strftime('%Y_%m_%d')

    @patch('processors.media_processor.datetime')
    def test_when_updating_keywords_then_adds_all_required_tags(self, mock_datetime):
        """Should add rating, export, and date keywords."""
        mock_datetime.now.return_value = datetime(2025, 3, 26)
        self.processor.exif_data = {
            'Rating': '4',
            'Keywords': ['existing']
        }
        self.mock_exiftool.update_keywords.return_value = True

        self.processor.update_keywords_with_rating_and_export_tags()

        self.mock_exiftool.update_keywords.assert_called_once()
        keywords = self.mock_exiftool.update_keywords.call_args[0][1]
        self.assertIn('existing', keywords)
        self.assertIn('3-star', keywords)
        self.assertIn('Lightroom_Export', keywords)
        self.assertIn('Lightroom_Export_on_2025_03_26', keywords)

    def test_when_updating_claudia_file_then_adds_claudia_keyword(self):
        """Should add Export_Claudia keyword for claudia_ files."""
        self.processor = TestMediaProcessor('/test/path/claudia_test.mov', exiftool=self.mock_exiftool)
        self.processor.exif_data = {'Rating': '3'}
        self.mock_exiftool.update_keywords.return_value = True

        self.processor.update_keywords_with_rating_and_export_tags()

        keywords = self.mock_exiftool.update_keywords.call_args[0][1]
        self.assertIn('Export_Claudia', keywords)

    def test_when_keyword_update_fails_then_raises_error(self):
        """Should raise RuntimeError when keyword update fails."""
        self.processor.exif_data = {'Rating': '3'}
        self.mock_exiftool.update_keywords.return_value = False

        with self.assertRaises(RuntimeError):
            self.processor.update_keywords_with_rating_and_export_tags()

class TestFileOperations(unittest.TestCase):
    """Tests for file operation methods."""
    
    def setUp(self):
        self.mock_exiftool = MagicMock(spec=ExifTool)
        self.test_file = Path('/test/path/test.mov')
        self.processor = TestMediaProcessor(str(self.test_file), exiftool=self.mock_exiftool)

    @patch('pathlib.Path.rename')
    def test_when_renaming_file_then_returns_new_path(self, mock_rename):
        """Should return new path when rename succeeds."""
        self.processor.exif_data = {'DateTimeOriginal': '2025_03_26'}
        new_path = self.processor.rename_file()
        self.assertIsNotNone(new_path)
        mock_rename.assert_called_once()

    @patch('pathlib.Path.rename')
    def test_when_rename_fails_then_returns_none(self, mock_rename):
        """Should return None when rename fails."""
        mock_rename.side_effect = OSError("Permission denied")
        self.processor.exif_data = {'DateTimeOriginal': '2025_03_26'}
        new_path = self.processor.rename_file()
        self.assertIsNone(new_path)

    @patch('pathlib.Path.rename')
    def test_when_filename_generation_fails_then_returns_none(self, mock_rename):
        """Should return None when filename generation fails."""
        self.processor.exif_data = {}  # No date, will cause generate_filename to return None
        new_path = self.processor.rename_file()
        self.assertIsNone(new_path)
        mock_rename.assert_not_called()

if __name__ == '__main__':
    unittest.main()
