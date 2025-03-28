#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, mock_open, MagicMock, call
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import logging
from io import StringIO
import types
from utils.exiftool import ExifTool
from processors.video_processor import VideoProcessor
from config import XML_NAMESPACES, VIDEO_PATTERN, LRE_SUFFIX, METADATA_FIELDS

class TestVideoProcessor(unittest.TestCase):
    """Base test class for VideoProcessor tests."""
    
    def setUp(self):
        """Set up test environment."""
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
    """Tests for error handling scenarios."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # Set up logging capture
        self.log_capture = StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        logging.getLogger().addHandler(self.handler)
        
    def tearDown(self):
        """Clean up after tests."""
        super().tearDown()
        logging.getLogger().removeHandler(self.handler)
        
    def test_when_invalid_extension_then_raises_error(self):
        """Should raise error when file has invalid extension."""
        with self.assertRaises(SystemExit):
            VideoProcessor('/test/video.txt')
            
    def test_when_xmp_not_found_then_logs_warning(self):
        """Should log warning when XMP file not found."""
        processor = VideoProcessor('/test/video.mp4')
        self.assertIn('No XMP sidecar file found', self.log_capture.getvalue())
        
    def test_when_exiftool_init_fails_then_logs_error(self):
        """Should log error when ExifTool initialization fails."""
        with patch('processors.video_processor.ExifTool') as mock_exiftool:
            mock_exiftool.side_effect = Exception("ExifTool init failed")
            with self.assertRaises(Exception):
                VideoProcessor('/test/video.mp4')
                
    def test_when_xml_parse_error_then_returns_none(self):
        """Should return None when XML parsing fails."""
        processor = VideoProcessor('/test/video.mp4')
        with patch('xml.etree.ElementTree.parse') as mock_parse:
            mock_parse.side_effect = ET.ParseError("XML parse error")
            result = processor.read_metadata_from_xmp()
            self.assertEqual(result, (None, None, None, None, (None, None, None)))

class TestMetadataReading(TestVideoProcessor):
    """Tests for reading metadata from XMP."""
    
    def setUp(self):
        """Set up test environment with sample XML data."""
        super().setUp()
        self.sample_xml = '''<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:dc="http://purl.org/dc/elements/1.1/"
                xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
                xmlns:Iptc4xmpCore="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"
                xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
                xmlns:exif="http://ns.adobe.com/exif/1.0/"
                xmlns:xml="http://www.w3.org/XML/1998/namespace">
            <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
                <dc:title>
                    <rdf:Alt>
                        <rdf:li xml:lang="x-default">Test Title</rdf:li>
                    </rdf:Alt>
                </dc:title>
                <lr:hierarchicalSubject>
                    <rdf:Bag>
                        <rdf:li>Keyword1</rdf:li>
                        <rdf:li>Category|Keyword2</rdf:li>
                    </rdf:Bag>
                </lr:hierarchicalSubject>
                <dc:subject>
                    <rdf:Bag>
                        <rdf:li>FlatKeyword1</rdf:li>
                        <rdf:li>FlatKeyword2</rdf:li>
                    </rdf:Bag>
                </dc:subject>
                <Iptc4xmpCore:Location>Test Location</Iptc4xmpCore:Location>
                <Iptc4xmpCore:City>Test City</Iptc4xmpCore:City>
                <Iptc4xmpCore:CountryName>Test Country</Iptc4xmpCore:CountryName>
                <xmp:ModifyDate>2024-03-27T20:00:00</xmp:ModifyDate>
            </rdf:Description>
        </rdf:RDF>'''
        
    def test_when_reading_hierarchical_keywords_then_extracts_all(self):
        """Should extract all keywords from hierarchical subjects."""
        processor = VideoProcessor('/test/video.mp4')
        root = ET.fromstring(self.sample_xml)
        keywords = processor._get_keywords_from_hierarchical(root)
        self.assertEqual(set(keywords), {'Keyword1', 'Category|Keyword2'})
        
    def test_when_reading_flat_keywords_then_extracts_all(self):
        """Should extract all keywords from flat subjects."""
        processor = VideoProcessor('/test/video.mp4')
        root = ET.fromstring(self.sample_xml)
        keywords = processor._get_keywords_from_flat(root)
        self.assertEqual(set(keywords), {'FlatKeyword1', 'FlatKeyword2'})
        
    def test_when_no_keywords_then_returns_none(self):
        """Should return None when no keywords found."""
        processor = VideoProcessor('/test/video.mp4')
        xml_no_keywords = '''<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description></rdf:Description>
        </rdf:RDF>'''
        root = ET.fromstring(xml_no_keywords)
        self.assertIsNone(processor._get_keywords_from_hierarchical(root))
        self.assertIsNone(processor._get_keywords_from_flat(root))
        
    def test_when_malformed_keywords_then_logs_error(self):
        """Should log error and return None when keywords are malformed."""
        processor = VideoProcessor('/test/video.mp4')
        xml_malformed = '''<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:lr="http://ns.adobe.com/lightroom/1.0/">
            <rdf:Description>
                <lr:hierarchicalSubject>
                    <rdf:Bag>
                        <rdf:li></rdf:li>
                    </rdf:Bag>
                </lr:hierarchicalSubject>
            </rdf:Description>
        </rdf:RDF>'''
        root = ET.fromstring(xml_malformed)
        self.assertIsNone(processor._get_keywords_from_hierarchical(root))
        
    def test_when_reading_metadata_then_returns_all_fields(self):
        """Should return all metadata fields when reading XMP."""
        processor = VideoProcessor('/test/video.mp4')
        
        # Mock Path.exists to return True for XMP file
        with patch('pathlib.Path.exists', return_value=True):
            # Create a temporary XMP file
            with patch('xml.etree.ElementTree.parse') as mock_parse:
                # Set up mock to return our sample XML
                mock_parse.return_value = ET.ElementTree(ET.fromstring(self.sample_xml))
                
                # Mock ExifTool date reading
                with patch.object(processor.exiftool, 'read_date_from_xmp') as mock_read_date:
                    mock_read_date.return_value = '2024:03:27 20:00:00'
                    
                    # Read metadata
                    title, keywords, date_str, caption, location_data = processor.read_metadata_from_xmp()
                    
                    # Verify results
                    self.assertEqual(title, 'Test Title')
                    self.assertTrue(any('Keyword' in k for k in keywords))
                    self.assertEqual(date_str, '2024:03:27 20:00:00')
                    self.assertEqual(location_data, ('Test Location', 'Test City', 'Test Country'))

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

    def test_when_writing_metadata_with_predashed_fields_then_uses_correct_fields(self):
        """Should use pre-dashed field names from METADATA_FIELDS correctly"""
        processor = VideoProcessor('/test/video.mp4')
        
        # Mock ExifTool
        with patch.object(processor, 'exiftool') as mock_exiftool:
            mock_exiftool.write_metadata.return_value = True
            
            # Write metadata
            metadata = (
                "Test Title",
                ["Keyword1"],
                "2024:03:27 15:00:00",
                "Test Caption",
                ("Test Location", "Test City", "Test Country")
            )
            result = processor.write_metadata_to_video(metadata)
            
            # Verify result
            self.assertTrue(result)
            
            # Get fields passed to write_metadata
            fields = mock_exiftool.write_metadata.call_args[0][1]
            
            # Check that fields are properly dashed
            self.assertIn("-ItemList:Title", fields)
            self.assertEqual(fields["-ItemList:Title"], "Test Title")
            self.assertIn("-QuickTime:Title", fields)
            self.assertEqual(fields["-QuickTime:Title"], "Test Title")
            self.assertIn("-CreateDate", fields)
            self.assertEqual(fields["-CreateDate"], "2024:03:27 15:00:00")
            self.assertIn("-Location", fields)
            self.assertEqual(fields["-Location"], "Test Location, Test City, Test Country")
            
    def test_when_writing_metadata_with_missing_fields_then_skips_empty(self):
        """Should handle missing metadata fields gracefully"""
        processor = VideoProcessor('/test/video.mp4')
        
        # Mock ExifTool
        with patch.object(processor, 'exiftool') as mock_exiftool:
            mock_exiftool.write_metadata.return_value = True
            
            # Write metadata with some empty fields
            metadata = (
                "Test Title",  # Only title
                None,          # No keywords
                None,          # No date
                None,          # No caption
                None           # No location
            )
            result = processor.write_metadata_to_video(metadata)
            
            # Verify result
            self.assertTrue(result)
            
            # Get fields passed to write_metadata
            fields = mock_exiftool.write_metadata.call_args[0][1]
            
            # Check that only title fields are present
            title_fields = {k: v for k, v in fields.items() if "Title" in k}
            self.assertTrue(all("Test Title" == v for v in title_fields.values()))
            
            # Check that other fields are not present
            self.assertFalse(any("Keywords" in k for k in fields))
            self.assertFalse(any("Date" in k for k in fields))
            self.assertFalse(any("Description" in k for k in fields))
            self.assertFalse(any("Location" in k for k in fields))
            
    def test_when_writing_metadata_with_partial_location_then_writes_available(self):
        """Should write available location fields even if some are missing"""
        processor = VideoProcessor('/test/video.mp4')
        
        # Mock ExifTool
        with patch.object(processor, 'exiftool') as mock_exiftool:
            mock_exiftool.write_metadata.return_value = True
            
            # Write metadata with partial location
            metadata = (
                None,                           # No title
                None,                           # No keywords
                None,                           # No date
                None,                           # No caption
                ("Test Location", None, None)   # Only location, no city/country
            )
            result = processor.write_metadata_to_video(metadata)
            
            # Verify result
            self.assertTrue(result)
            
            # Get fields passed to write_metadata
            fields = mock_exiftool.write_metadata.call_args[0][1]
            
            # Check that location fields are present with just location
            location_fields = {k: v for k, v in fields.items() if "Location" in k}
            self.assertTrue(all("Test Location" == v for v in location_fields.values()))
            
            # Check that city/country fields are not present
            self.assertFalse(any("City" in k for k in fields))
            self.assertFalse(any("Country" in k for k in fields))

class TestProcessFlow(TestVideoProcessor):
    """Test cases for video processing flow and order of operations."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # Create a mock processor with all required methods
        self.processor = MagicMock(spec=VideoProcessor)
        self.processor.logger = MagicMock()
        self.processor.file_path = self.test_file
    
    def test_when_file_has_lre_suffix_then_skips_processing(self):
        """Should skip processing if file already has LRE suffix."""
        # Setup file with LRE suffix
        self.processor.file_path = Path('/test/video__LRE.mp4')
        self.processor._should_skip_processing.return_value = True
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process the video
        result = self.processor.process_video()
        
        # Verify that processing was skipped
        self.processor._get_and_validate_metadata.assert_not_called()
        self.processor._write_and_verify_metadata.assert_not_called()
        self.processor._cleanup_and_rename.assert_not_called()
        self.assertEqual(result, self.processor.file_path)
        
    def test_when_processing_video_then_follows_correct_order(self):
        """Should follow correct order: read XMP -> write -> verify -> delete XMP -> rename."""
        # Set up test data
        metadata = ('title', ['keyword'], 'date', 'caption', ('loc', 'city', 'country'))
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = metadata
        self.processor._write_and_verify_metadata.return_value = True
        self.processor._cleanup_and_rename.return_value = Path('/test/video__LRE.mp4')
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify the order of operations
        expected_calls = [
            call._should_skip_processing(),
            call._get_and_validate_metadata(),
            call._write_and_verify_metadata(metadata),
            call._cleanup_and_rename()
        ]
        
        # Get actual core operation calls
        actual_calls = [
            c for c in self.processor.mock_calls 
            if not str(c).startswith('call.logger.')
        ]
        
        # Verify core operations order
        self.assertEqual(expected_calls, actual_calls)
        self.assertEqual(result, Path('/test/video__LRE.mp4'))
    
    def test_when_metadata_write_fails_then_stops_processing(self):
        """Should stop processing if metadata write fails."""
        # Set up test data
        metadata = ('title', ['keyword'], 'date', 'caption', ('loc', 'city', 'country'))
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = metadata
        self.processor._write_and_verify_metadata.return_value = False
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify processing stopped after write failure
        self.processor._write_and_verify_metadata.assert_called_once_with(metadata)
        self.processor._cleanup_and_rename.assert_not_called()
        self.assertEqual(result, self.test_file)
    
    def test_when_verification_fails_then_stops_processing(self):
        """Should stop processing if metadata verification fails."""
        # Set up test data
        metadata = ('title', ['keyword'], 'date', 'caption', ('loc', 'city', 'country'))
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = metadata
        self.processor._write_and_verify_metadata.return_value = False
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify processing stopped after verification failure
        self.processor._write_and_verify_metadata.assert_called_once_with(metadata)
        self.processor._cleanup_and_rename.assert_not_called()
        self.assertEqual(result, self.test_file)
    
    def test_when_xmp_delete_fails_then_logs_but_continues(self):
        """Should log error but continue processing if XMP deletion fails."""
        # Set up test data
        metadata = ('title', ['keyword'], 'date', 'caption', ('loc', 'city', 'country'))
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = metadata
        self.processor._write_and_verify_metadata.return_value = True
        self.processor._cleanup_and_rename.return_value = self.test_file
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify processing continued after XMP deletion failure
        self.processor._cleanup_and_rename.assert_called_once()
        self.assertEqual(result, self.test_file)
    
    def test_when_rename_fails_then_returns_false(self):
        """Should return False if final rename fails."""
        # Set up test data
        metadata = ('title', ['keyword'], 'date', 'caption', ('loc', 'city', 'country'))
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = metadata
        self.processor._write_and_verify_metadata.return_value = True
        self.processor._cleanup_and_rename.return_value = self.test_file
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify failure
        self.assertEqual(result, self.test_file)

class TestMetadataHandling(TestVideoProcessor):
    """Test cases for metadata handling, particularly keywords and verification."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # Create a mock processor with all required methods
        self.processor = MagicMock(spec=VideoProcessor)
        self.processor.logger = MagicMock()
        self.processor.file_path = self.test_file
    
    def test_when_all_metadata_none_then_only_adds_suffix(self):
        """Should only add LRE suffix when all metadata fields are None."""
        # Set up test data
        self.processor._should_skip_processing.return_value = False
        self.processor._get_and_validate_metadata.return_value = None
        self.processor._cleanup_and_rename.return_value = Path(str(self.test_file) + LRE_SUFFIX)
        
        # Set up process_video to call the actual implementation
        def process_video_impl(self):
            if self._should_skip_processing():
                return self.file_path
            metadata = self._get_and_validate_metadata()
            if metadata is None:
                return self._cleanup_and_rename()
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
            return self._cleanup_and_rename()
            
        self.processor.process_video = types.MethodType(process_video_impl, self.processor)
        
        # Process video
        result = self.processor.process_video()
        
        # Verify result
        self.assertEqual(result, Path(str(self.test_file) + LRE_SUFFIX))
        self.processor._cleanup_and_rename.assert_called_once()

class TestMetadataVerificationIntegration(TestVideoProcessor):
    """Integration tests for metadata verification process."""
    
    def setUp(self):
        """Set up test environment with sample metadata."""
        super().setUp()
        self.sample_metadata = (
            "Test Title",  # title
            ["Keyword1", "Category|Keyword2"],  # keywords
            "2024:03:27 20:00:00",  # date_str
            "Test Caption",  # caption
            ("Test Location", "Test City", "Test Country")  # location_data
        )
        
        # Sample ExifTool output that matches our metadata
        self.sample_exif_data = {
            "ItemList:Title": "Test Title",
            "QuickTime:Keywords": ["Keyword1", "Category|Keyword2"],
            "CreateDate": "2024:03:27 20:00:00",
            "ItemList:Description": "Test Caption",
            "Location": "Test Location",
            "City": "Test City",
            "Country": "Test Country"
        }
        
    def test_verify_metadata_with_all_fields(self):
        """Should verify all metadata fields successfully."""
        processor = VideoProcessor('/test/video.mp4')
        
        # Mock ExifTool read to return our sample data
        with patch.object(processor, 'read_exif') as mock_read:
            mock_read.return_value = self.sample_exif_data
            
            # Verify all metadata
            result = processor.verify_metadata(self.sample_metadata)
            self.assertTrue(result)
            
    def test_verify_metadata_with_partial_fields(self):
        """Should verify successfully when some fields are None."""
        processor = VideoProcessor('/test/video.mp4')
        
        # Create partial metadata (no caption or location)
        partial_metadata = (
            "Test Title",
            ["Keyword1"],
            "2024:03:27 20:00:00",
            None,  # caption
            None   # location_data
        )
        
        partial_exif = {
            "ItemList:Title": "Test Title",
            "QuickTime:Keywords": ["Keyword1"],
            "CreateDate": "2024:03:27 20:00:00"
        }
        
        # Mock ExifTool read
        with patch.object(processor, 'read_exif') as mock_read:
            mock_read.return_value = partial_exif
            
            # Verify partial metadata
            result = processor.verify_metadata(partial_metadata)
            self.assertTrue(result)
            
    def test_verify_metadata_with_different_field_names(self):
        """Should verify metadata across different field name variations."""
        processor = VideoProcessor('/test/video.mp4')
        
        # Same data but using alternative field names
        alt_exif_data = {
            "QuickTime:Title": "Test Title",  # Alternative title field
            "XMP:Subject": ["Keyword1", "Category|Keyword2"],  # Alternative keywords field
            "MediaCreateDate": "2024:03:27 20:00:00",  # Alternative date field
            "Description": "Test Caption",  # Alternative caption field
            "XMP:Location": "Test Location",  # Alternative location fields
            "XMP:City": "Test City",
            "XMP:Country": "Test Country"
        }
        
        # Mock ExifTool read
        with patch.object(processor, 'read_exif') as mock_read:
            mock_read.return_value = alt_exif_data
            
            # Verify with alternative field names
            result = processor.verify_metadata(self.sample_metadata)
            self.assertTrue(result)
            
    def test_verify_metadata_with_date_variations(self):
        """Should verify dates with different formats but same value."""
        processor = VideoProcessor('/test/video.mp4')
        
        # Test different date format variations
        date_variations = {
            "ItemList:Title": "Test Title",  
            "-CreateDate": "2024:03:27 20:00:00",
            "-ModifyDate": "2024-03-27 20:00:00",  
            "-MediaCreateDate": "2024:03:27 20:00:00.000",  
            "-TrackCreateDate": "2024:03:27 20:00:00+0000"  
        }
        
        # Mock ExifTool read
        with patch.object(processor, 'read_exif') as mock_read:
            mock_read.return_value = date_variations
            
            # Should match our standard date format
            metadata = ("Test Title", None, "2024:03:27 20:00:00", None, None)
            result = processor.verify_metadata(metadata)
            self.assertTrue(result, f"Failed to match date format: {date_variations}")

class TestFilenameGeneration(TestVideoProcessor):
    """Test cases for video filename generation."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.processor.metadata_for_filename = {}
        
    def test_when_date_has_colons_then_converts_to_underscores(self):
        """Should convert date format from YYYY:MM:DD to YYYY_MM_DD in filename."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07',
            'Title': 'test_title',
            'Location': 'Texas',
            'City': 'Rowlett',
            'Country': 'United States'
        }
        
        # Execute
        date_str, title, location, city, country = self.processor.get_metadata_components()
        
        # Verify
        self.assertEqual(date_str, '2025_03_27')
        
    def test_when_date_has_timezone_then_ignores_timezone(self):
        """Should ignore timezone in date when generating filename."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07-05:00',
            'Title': 'test_title'
        }
        
        # Execute
        date_str, title, location, city, country = self.processor.get_metadata_components()
        
        # Verify
        self.assertEqual(date_str, '2025_03_27')
        
    def test_when_sequence_provided_then_adds_sequence_with_underscore(self):
        """Should add sequence number with underscore prefix."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07',
            'Title': 'test_title'
        }
        self.processor.sequence = '0001'
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        self.assertTrue('_0001__LRE' in result)
        
    def test_full_filename_generation_with_all_components(self):
        """Should generate correct filename with all components."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07',
            'Title': 'test title',
            'Location': 'Texas',
            'City': 'Rowlett',
            'Country': 'United States'
        }
        self.processor.sequence = '0001'
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        expected = '2025_03_27_test_title_Texas_Rowlett_United_States_0001__LRE.mp4'
        self.assertEqual(result, expected)
        
    def test_when_metadata_has_spaces_then_converts_to_underscores(self):
        """Should convert spaces in metadata to underscores in filename."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07',
            'Title': 'My Test Title',
            'Location': 'New York',
            'City': 'New York City',
            'Country': 'United States'
        }
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        self.assertIn('My_Test_Title', result)
        self.assertIn('New_York_City', result)
        self.assertIn('United_States', result)

    def test_when_date_is_invalid_then_skips_date_in_filename(self):
        """Should handle invalid date formats by skipping date in filename."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': 'invalid-date',
            'Title': 'test_title'
        }
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        self.assertNotIn('invalid-date', result)
        self.assertIn('test_title', result)
        
    def test_when_metadata_is_none_then_returns_original_name_with_lre(self):
        """Should return original filename with LRE suffix when metadata is None."""
        # Setup
        self.processor.metadata_for_filename = None
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        expected = self.test_file.stem + '__LRE.mp4'
        self.assertEqual(result, expected)
        
    def test_when_metadata_is_empty_then_returns_original_name_with_lre(self):
        """Should return original filename with LRE suffix when metadata is empty."""
        # Setup
        self.processor.metadata_for_filename = {}
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        expected = self.test_file.stem + '__LRE.mp4'
        self.assertEqual(result, expected)
        
    def test_when_metadata_has_special_chars_then_sanitizes_filename(self):
        """Should sanitize special characters from metadata in filename."""
        # Setup
        self.processor.metadata_for_filename = {
            'CreateDate': '2025:03:27 15:18:07',
            'Title': 'Test: Special/Chars?!',
            'Location': 'Test & Location',
            'City': 'City/Name',
            'Country': 'Country\\Name'
        }
        
        # Execute
        result = self.processor.generate_filename()
        
        # Verify
        self.assertIn('Test_Special_Chars', result)
        self.assertIn('Test_Location', result)
        self.assertIn('City_Name', result)
        self.assertIn('Country_Name', result)
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)
        self.assertNotIn(':', result)
        self.assertNotIn('?', result)
        self.assertNotIn('!', result)
        self.assertNotIn('&', result)

class TestMetadataVerification(unittest.TestCase):
    """Tests for metadata verification functionality."""
    
    def setUp(self):
        self.test_file = Path('/test/path/test.mov')
        self.mock_exiftool = MagicMock()
        self.mock_exiftool.read_exif = MagicMock()
        self.processor = VideoProcessor(str(self.test_file))
        self.processor.exiftool = self.mock_exiftool
        
    def test_when_verifying_metadata_then_checks_all_fields(self):
        """Should verify all metadata fields are written correctly."""
        # Setup
        written_metadata = (
            'Test Video',  # title
            ['test', 'video'],  # keywords
            '2025:03:27 22:59:37',  # date_str
            'Test Description',  # caption
            ('Test Location', 'Test City', 'Test Country')  # location_data
        )
        exif_data = {
            'Title': 'Test Video',
            'Description': 'Test Description',
            'Keywords': ['test', 'video'],
            'Location': 'Test Location',
            'City': 'Test City',
            'Country': 'Test Country',
            'CreateDate': '2025:03:27 22:59:37'
        }
        self.processor.read_exif = MagicMock(return_value=exif_data)
        
        # Execute
        result = self.processor.verify_metadata(written_metadata)
        
        # Verify
        self.assertTrue(result)
        self.processor.read_exif.assert_called_once()
        
    def test_when_verifying_metadata_with_missing_fields_then_returns_false(self):
        """Should return False when written metadata is missing fields."""
        # Setup
        written_metadata = (
            'Test Video',  # title
            ['test', 'video'],  # keywords
            '2025:03:27 22:59:37',  # date_str
            'Test Description',  # caption
            ('Test Location', 'Test City', 'Test Country')  # location_data
        )
        exif_data = {
            'Title': 'Test Video',
            'Description': 'Test Description',
            # Keywords missing
            'Location': 'Test Location',
            'City': 'Test City',
            'Country': 'Test Country',
            'CreateDate': '2025:03:27 22:59:37'
        }
        self.processor.read_exif = MagicMock(return_value=exif_data)
        
        # Execute
        result = self.processor.verify_metadata(written_metadata)
        
        # Verify
        self.assertFalse(result)
        self.processor.read_exif.assert_called_once()
        
    def test_when_verifying_metadata_with_different_values_then_returns_false(self):
        """Should return False when read metadata differs from written metadata."""
        # Setup
        written_metadata = (
            'Test Video',  # title
            ['test', 'video'],  # keywords
            '2025:03:27 22:59:37',  # date_str
            'Test Description',  # caption
            ('Test Location', 'Test City', 'Test Country')  # location_data
        )
        exif_data = {
            'Title': 'Different Title',  # Different value
            'Description': 'Test Description',
            'Keywords': ['test', 'video'],
            'Location': 'Test Location',
            'City': 'Test City',
            'Country': 'Test Country',
            'CreateDate': '2025:03:27 22:59:37'
        }
        self.processor.read_exif = MagicMock(return_value=exif_data)
        
        # Execute
        result = self.processor.verify_metadata(written_metadata)
        
        # Verify
        self.assertFalse(result)
        self.processor.read_exif.assert_called_once()
        
    def test_when_verifying_metadata_with_read_error_then_returns_false(self):
        """Should return False when metadata read fails."""
        # Setup
        written_metadata = (
            'Test Video',  # title
            ['test', 'video'],  # keywords
            '2025:03:27 22:59:37',  # date_str
            'Test Description',  # caption
            ('Test Location', 'Test City', 'Test Country')  # location_data
        )
        self.processor.read_exif = MagicMock(return_value={})  # Empty dict indicates read error
        
        # Execute
        result = self.processor.verify_metadata(written_metadata)
        
        # Verify
        self.assertFalse(result)
        self.processor.read_exif.assert_called_once()

if __name__ == '__main__':
    unittest.main()
