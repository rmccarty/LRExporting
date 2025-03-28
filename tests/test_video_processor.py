#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import logging

from processors.video_processor import VideoProcessor
from config import XML_NAMESPACES, VIDEO_PATTERN, LRE_SUFFIX

class TestVideoProcessor(unittest.TestCase):
    def setUp(self):
        self.test_file = Path('/test/video.mp4')
        self.test_xmp = self.test_file.with_suffix('.xmp')
        self.processor = VideoProcessor(str(self.test_file))
        
        # Mock logger to prevent actual logging during tests
        self.processor.logger = Mock()
        
        # Mock methods that make external calls
        self.processor.write_metadata_to_video = Mock()
        self.processor.verify_metadata = Mock()
        
    def create_mock_rdf(self, content):
        """Helper to create RDF XML content for testing."""
        return ET.fromstring(content)

class TestErrorHandling(TestVideoProcessor):
    """Test cases for error handling paths."""
    
    def test_when_init_with_invalid_file_then_logs_error(self):
        """Should log error when initialized with invalid file."""
        with patch('pathlib.Path.exists', return_value=False), \
             patch('logging.getLogger') as mock_logger:
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance
            VideoProcessor('nonexistent.mp4')
            mock_logger_instance.warning.assert_called_once_with("No XMP sidecar file found: nonexistent.xmp")
            
    def test_when_getting_keywords_with_invalid_rdf_then_returns_none(self):
        """Should handle errors in get_keywords_from_rdf."""
        rdf = self.create_mock_rdf('<invalid></invalid>')
        result = self.processor.get_keywords_from_rdf(rdf)
        self.assertIsNone(result)
        
    def test_when_getting_iptc_location_with_invalid_rdf_then_returns_none(self):
        """Should handle errors in _get_iptc_location."""
        rdf = self.create_mock_rdf('<invalid></invalid>')
        result = self.processor._get_iptc_location(rdf)
        self.assertEqual(result, (None, None, None))
        
    def test_when_building_location_string_with_invalid_input_then_returns_none(self):
        """Should handle edge cases in _build_location_string."""
        test_cases = [
            (None, None, None),
            ('', '', ''),
            ('City', None, None),
            (None, 'State', None),
            (None, None, 'Country')
        ]
        for city, state, country in test_cases:
            result = self.processor._build_location_string(city, state, country)
            if all(x is None or x == '' for x in (city, state, country)):
                self.assertIsNone(result)
            else:
                self.assertIsNotNone(result)
                
    def test_when_splitting_timezone_with_invalid_input_then_returns_empty(self):
        """Should handle edge cases in _split_time_and_timezone."""
        test_cases = [
            '',
            '12:00:00',
            'invalid'
        ]
        for time_str in test_cases:
            time_part, tz_part = self.processor._split_time_and_timezone(time_str)
            self.assertEqual(time_part, time_str)
            self.assertEqual(tz_part, '')
            
    def test_when_building_date_string_with_invalid_input_then_returns_empty(self):
        """Should handle edge cases in _build_date_string."""
        test_cases = [
            ('', '', ''),
            ('', '12:00:00', ''),
            ('2024:01:01', '', ''),
            ('2024:01:01', '12:00:00', 'invalid'),
            ('2024-01-01', '12:00:00', '+0500')  # Invalid date format
        ]
        for date_part, time_part, tz_part in test_cases:
            result = self.processor._build_date_string(date_part, time_part, tz_part)
            if not date_part or not time_part:
                self.assertTrue(result.strip() == '')
            else:
                self.assertTrue(len(result.strip()) > 0)
                
    def test_when_normalizing_timezone_with_invalid_input_then_returns_empty(self):
        """Should handle edge cases in _normalize_timezone."""
        test_cases = [
            None,
            '',
            'invalid',
            '+24',  # Invalid hour
            '+abc',
            '+-5'
        ]
        for tz in test_cases:
            result = self.processor._normalize_timezone(tz)
            self.assertEqual(result, '')
            
    def test_when_validating_timezone_input_with_invalid_types_then_returns_false(self):
        """Should handle edge cases in _is_valid_timezone_input."""
        test_cases = [
            None,
            123,
            [],
            {},
            True
        ]
        for tz in test_cases:
            result = self.processor._is_valid_timezone_input(tz)
            self.assertFalse(result)
            
    def test_when_validating_timezone_hours_with_invalid_input_then_returns_false(self):
        """Should handle edge cases in _is_valid_timezone_hours."""
        test_cases = [
            (24, '+24'),  # Invalid hour
            (0, '+0a'),   # Non-numeric chars
            (5, '+5.0'),  # Decimal
            (-1, '-1'),   # Negative hour
            (12, '+12.5') # Non-integer
        ]
        for hours, original_tz in test_cases:
            result = self.processor._is_valid_timezone_hours(hours, original_tz)
            self.assertFalse(result)
            
    def test_when_writing_metadata_with_invalid_input_then_returns_false(self):
        """Should handle edge cases in write_metadata_to_video."""
        # Reset mock to return False for invalid input
        self.processor.write_metadata_to_video.return_value = False
        
        test_cases = [
            (None,),
            ((None, None, None, None, (None, None, None)),),
            ((None,),),  # Invalid tuple length
            ('not a tuple',)
        ]
        for metadata in test_cases:
            result = self.processor.write_metadata_to_video(metadata)
            self.assertFalse(result)
            
class TestDateHandling(TestVideoProcessor):
    def test_when_normalizing_valid_date_then_returns_formatted_date(self):
        """Should normalize date to YYYY:MM:DD HH:MM:SS format."""
        test_cases = [
            ('2024-01-01 12:00:00', '2024:01:01 12:00:00'),
            ('2024-01-01 12:00:00-0500', '2024:01:01 12:00:00-0500'),
            ('2024:01:01 12:00:00', '2024:01:01 12:00:00'),
            ('2024:01:01 12:00:00 +5', '2024:01:01 12:00:00+0500'),
            ('2024-01-01 12:00:00 +5', '2024:01:01 12:00:00+0500'),
            ('2024-01-01 12:00:00 -5', '2024:01:01 12:00:00-0500'),
            ('2024-01-01 12:00:00 invalid', '2024:01:01 12:00:00'),  # Invalid timezone
            ('2024-01-01 12:00:00 +abc', '2024:01:01 12:00:00'),  # Invalid timezone format
        ]
        for input_date, expected in test_cases:
            with self.subTest(input_date=input_date):
                result = self.processor.normalize_date(input_date)
                self.assertEqual(result, expected)
                
    def test_when_normalizing_invalid_date_then_returns_none(self):
        """Should return None for invalid date formats."""
        invalid_dates = [
            None,  # None input
            '',  # Empty string
            '2024-01-01',  # Missing time
            'invalid date',  # Invalid format
            '2024-01-01 invalid',  # Invalid time
        ]
        for date_str in invalid_dates:
            with self.subTest(date_str=date_str):
                self.assertIsNone(self.processor.normalize_date(date_str))
                
    def test_when_normalizing_timezone_then_handles_all_formats(self):
        """Should handle all timezone formats correctly."""
        test_cases = [
            ('-0500', '-0500'),  # Already correct format
            ('+0500', '+0500'),  # Already correct format
            ('-5', '-0500'),  # Short negative
            ('+5', '+0500'),  # Short positive
            ('invalid', ''),  # Invalid format
            ('abc', ''),  # Invalid format
            ('0', '+0000'),  # Zero offset
            ('5abc', ''),  # Invalid with numbers
        ]
        for tz_part, expected in test_cases:
            with self.subTest(tz_part=tz_part):
                result = self.processor._normalize_timezone(tz_part)
                self.assertEqual(result, expected)
                
    def test_when_normalizing_date_parts_then_handles_all_formats(self):
        """Should handle all date part formats correctly."""
        test_cases = [
            # (input, expected)
            ('2024-01-01 12:00:00', ('2024:01:01', '12:00:00', '')),
            ('2024-01-01 12:00:00 -0500', ('2024:01:01', '12:00:00', '-0500')),
            ('2024:01:01 12:00:00', ('2024:01:01', '12:00:00', '')),
            ('2024:01:01 12:00:00 +5', ('2024:01:01', '12:00:00', '+5')),
        ]
        for input_date, expected in test_cases:
            with self.subTest(input_date=input_date):
                result = self.processor._normalize_date_parts(input_date)
                self.assertEqual(result, expected)
                
    def test_when_normalizing_invalid_date_parts_then_returns_none(self):
        """Should return None for invalid date parts."""
        invalid_dates = [
            None,  # None input
            '',  # Empty string
            '2024-01-01',  # Missing time
            'invalid',  # Invalid format
            '2024-01-01 ',  # Missing time
        ]
        for date_str in invalid_dates:
            with self.subTest(date_str=date_str):
                self.assertIsNone(self.processor._normalize_date_parts(date_str))
                
    def test_when_comparing_dates_with_different_formats_then_matches_correctly(self):
        """Should correctly match dates in different formats."""
        test_cases = [
            ('2024:01:01 12:00:00', '2024-01-01 12:00:00'),
            ('2024:01:01 12:00:00-0500', '2024-01-01 12:00:00-0500'),
            ('2024:01:01 12:00:00.123', '2024-01-01 12:00:00'),
            ('2024:01:01 12:00:00', '2024:01:01 12:00:00'),
            ('2024:01:01 12:00:00-0500', '2024:01:01 12:00:00-0500'),
            ('2024:01:01 12:00:00', '2024-01-01 12:00:00+0000'),  # Different timezone formats
            ('2024:01:01 12:00:00.123', '2024-01-01 12:00:00.456'),  # Different subseconds
        ]
        for date1, date2 in test_cases:
            with self.subTest(date1=date1, date2=date2):
                self.assertTrue(self.processor.dates_match(date1.strip(), date2.strip()),
                              f"Dates should match: {date1} == {date2}")
                              
    def test_when_comparing_invalid_dates_then_returns_false(self):
        """Should return False when comparing invalid dates."""
        invalid_cases = [
            (None, '2024:01:01 12:00:00'),  # None first date
            ('2024:01:01 12:00:00', None),  # None second date
            ('invalid', '2024:01:01 12:00:00'),  # Invalid first date
            ('2024:01:01 12:00:00', 'invalid'),  # Invalid second date
            ('2024:01:01', '2024:01:01 12:00:00'),  # Missing time first date
            ('2024:01:01 12:00:00', '2024:01:01'),  # Missing time second date
        ]
        for date1, date2 in invalid_cases:
            with self.subTest(date1=date1, date2=date2):
                self.assertFalse(self.processor.dates_match(date1, date2),
                               f"Dates should not match: {date1} != {date2}")

class TestVideoProcessing(TestVideoProcessor):
    def setUp(self):
        super().setUp()
        self.test_metadata = ('Title', ['tag1'], '2024:01:01', 'Caption', ('Location', 'City', 'Country'))
        
    def test_when_processing_video_with_lre_suffix_then_skips_processing(self):
        """Should skip processing for files already having LRE suffix."""
        # Mock logger first
        with patch('logging.getLogger') as mock_logger:
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance
            
            # Mock XMP file check to prevent warning logs during init
            with patch('pathlib.Path.exists', return_value=True):
                test_file = Path("/test/video__LRE.mp4")
                processor = VideoProcessor(str(test_file))  # Convert Path to str for constructor
                
                # Mock the metadata methods
                with patch.object(processor, 'get_metadata_from_xmp') as mock_get_metadata:
                    result = processor.process_video()
                    
                    self.assertEqual(result, test_file)
                    mock_logger_instance.info.assert_any_call(f"Skipping {test_file}, already has {LRE_SUFFIX} suffix")
                    
                    # Verify no metadata operations were performed
                    mock_get_metadata.assert_not_called()
                    
    def test_when_processing_video_with_metadata_then_writes_and_verifies(self):
        """Should write and verify metadata when processing video with metadata."""
        processor = VideoProcessor(self.test_file)
        processor.logger = Mock()
        
        # Mock the metadata methods
        processor.get_metadata_from_xmp = Mock(return_value=self.test_metadata)
        processor.write_metadata_to_video = Mock(return_value=True)
        processor.verify_metadata = Mock(return_value=True)
        processor._is_metadata_empty = Mock(return_value=False)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink') as mock_remove, \
             patch('pathlib.Path.rename') as mock_rename:
            
            result = processor.process_video()
            
            # Verify the process
            processor.get_metadata_from_xmp.assert_called_once()
            processor.write_metadata_to_video.assert_called_once_with(self.test_metadata)
            processor.verify_metadata.assert_called_once_with(self.test_metadata)
            mock_remove.assert_called_once()
            mock_rename.assert_called_once()
            self.assertNotEqual(result, self.test_file)
            
    def test_when_processing_video_without_metadata_then_only_renames(self):
        """Should only rename file when no metadata is found."""
        processor = VideoProcessor(self.test_file)
        processor.logger = Mock()
        
        # Mock empty metadata
        empty_metadata = (None, None, None, None, (None, None, None))
        processor.get_metadata_from_xmp = Mock(return_value=empty_metadata)
        processor._is_metadata_empty = Mock(return_value=True)
        processor.write_metadata_to_video = Mock()  # Create a new mock
        processor.verify_metadata = Mock()  # Create a new mock
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink') as mock_remove, \
             patch('pathlib.Path.rename') as mock_rename:
            
            result = processor.process_video()
            
            # Verify no metadata operations were performed
            processor.get_metadata_from_xmp.assert_called_once()
            self.assertEqual(processor.write_metadata_to_video.call_count, 0)
            self.assertEqual(processor.verify_metadata.call_count, 0)
            mock_remove.assert_called_once()
            mock_rename.assert_called_once()
            self.assertNotEqual(result, self.test_file)

class TestXMPProcessing(TestVideoProcessor):
    def test_when_getting_metadata_from_xmp_with_no_metadata_then_logs_warning(self):
        """Should log a warning when no metadata is found."""
        with patch.object(self.processor, 'read_metadata_from_xmp') as mock_read:
            mock_read.return_value = (None, None, None, None, (None, None, None))
            result = self.processor.get_metadata_from_xmp()
            self.assertEqual(result, (None, None, None, None, (None, None, None)))
            self.processor.logger.warning.assert_called_once()
            
    def test_when_getting_metadata_from_xmp_with_partial_metadata_then_logs_info(self):
        """Should log info messages for missing metadata fields."""
        with patch.object(self.processor, 'read_metadata_from_xmp') as mock_read:
            mock_read.return_value = ("Title", None, None, None, (None, None, None))
            result = self.processor.get_metadata_from_xmp()
            self.assertEqual(result, ("Title", None, None, None, (None, None, None)))
            self.processor.logger.info.assert_any_call("No keywords found in XMP")
            self.processor.logger.info.assert_any_call("No date found in XMP")
            self.processor.logger.info.assert_any_call("No caption found in XMP")
            self.processor.logger.info.assert_any_call("No location data found in XMP")
            
    def test_when_getting_metadata_from_xmp_with_all_metadata_then_no_warnings(self):
        """Should not log any warnings when all metadata is present."""
        metadata = ("Title", ["tag1"], "2024:01:01", "Caption", ("Location", "City", "Country"))
        with patch.object(self.processor, 'read_metadata_from_xmp') as mock_read:
            mock_read.return_value = metadata
            result = self.processor.get_metadata_from_xmp()
            self.assertEqual(result, metadata)
            self.processor.logger.warning.assert_not_called()
            self.processor.logger.info.assert_not_called()
            
    def test_when_reading_metadata_from_xmp_with_all_fields_then_returns_complete_tuple(self):
        """Should return complete metadata tuple when all fields are present in XMP."""
        ns = XML_NAMESPACES
        rdf = self.create_mock_rdf(f'''
            <rdf:RDF xmlns:rdf="{ns['rdf']}" xmlns:dc="{ns['dc']}" xmlns:Iptc4xmpCore="{ns['Iptc4xmpCore']}">
                <rdf:Description>
                    <dc:title>
                        <rdf:Alt>
                            <rdf:li>Test Title</rdf:li>
                        </rdf:Alt>
                    </dc:title>
                    <dc:subject>
                        <rdf:Bag>
                            <rdf:li>tag1</rdf:li>
                            <rdf:li>tag2</rdf:li>
                        </rdf:Bag>
                    </dc:subject>
                    <dc:description>
                        <rdf:Alt>
                            <rdf:li>Test Caption</rdf:li>
                        </rdf:Alt>
                    </dc:description>
                    <Iptc4xmpCore:Location>Test Location</Iptc4xmpCore:Location>
                    <Iptc4xmpCore:City>Test City</Iptc4xmpCore:City>
                    <Iptc4xmpCore:CountryName>Test Country</Iptc4xmpCore:CountryName>
                </rdf:Description>
            </rdf:RDF>
        ''')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('xml.etree.ElementTree.parse') as mock_parse, \
             patch.object(self.processor.exiftool, 'read_date_from_xmp', return_value='2024:01:01 12:00:00'):
            mock_parse.return_value.getroot.return_value = rdf
            result = self.processor.read_metadata_from_xmp()
            self.assertEqual(result, (
                'Test Title',
                ['tag1', 'tag2'],
                '2024:01:01 12:00:00',
                'Test Caption',
                ('Test Location', 'Test City', 'Test Country')
            ))
            
    def test_when_reading_metadata_from_xmp_with_minimal_fields_then_returns_partial_tuple(self):
        """Should return partial metadata tuple when only some fields are present in XMP."""
        ns = XML_NAMESPACES
        rdf = self.create_mock_rdf(f'''
            <rdf:RDF xmlns:rdf="{ns['rdf']}" xmlns:dc="{ns['dc']}">
                <rdf:Description>
                    <dc:title>
                        <rdf:Alt>
                            <rdf:li>Test Title</rdf:li>
                        </rdf:Alt>
                    </dc:title>
                </rdf:Description>
            </rdf:RDF>
        ''')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('xml.etree.ElementTree.parse') as mock_parse, \
             patch.object(self.processor.exiftool, 'read_date_from_xmp', return_value=None):
            mock_parse.return_value.getroot.return_value = rdf
            result = self.processor.read_metadata_from_xmp()
            self.assertEqual(result, (
                'Test Title',
                None,
                None,
                None,
                (None, None, None)
            ))
            
    def test_when_reading_metadata_from_xmp_with_empty_fields_then_returns_none_values(self):
        """Should return None for empty or malformed fields in XMP."""
        ns = XML_NAMESPACES
        rdf = self.create_mock_rdf(f'''
            <rdf:RDF xmlns:rdf="{ns['rdf']}" xmlns:dc="{ns['dc']}" xmlns:Iptc4xmpCore="{ns['Iptc4xmpCore']}">
                <rdf:Description>
                    <dc:title>
                        <rdf:Alt>
                            <rdf:li></rdf:li>
                        </rdf:Alt>
                    </dc:title>
                    <dc:subject>
                        <rdf:Bag>
                        </rdf:Bag>
                    </dc:subject>
                    <dc:description>
                        <rdf:Alt>
                        </rdf:Alt>
                    </dc:description>
                    <Iptc4xmpCore:Location></Iptc4xmpCore:Location>
                    <Iptc4xmpCore:City></Iptc4xmpCore:City>
                    <Iptc4xmpCore:CountryName></Iptc4xmpCore:CountryName>
                </rdf:Description>
            </rdf:RDF>
        ''')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('xml.etree.ElementTree.parse') as mock_parse, \
             patch.object(self.processor.exiftool, 'read_date_from_xmp', return_value=None):
            mock_parse.return_value.getroot.return_value = rdf
            result = self.processor.read_metadata_from_xmp()
            self.assertEqual(result, (
                None,
                None,
                None,
                None,
                (None, None, None)
            ))

if __name__ == '__main__':
    unittest.main()
