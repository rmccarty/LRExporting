#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import json

from utils.exiftool import ExifTool

class TestExifTool(unittest.TestCase):
    def setUp(self):
        self.exiftool = ExifTool()
        self.test_file = Path('/test/path/file.mov')
        self.test_xmp = Path('/test/path/file.xmp')

    @patch('shutil.which')
    def test_when_exiftool_not_installed_then_exits(self, mock_which):
        """Should exit if exiftool is not found in PATH"""
        mock_which.return_value = None
        with self.assertRaises(SystemExit):
            ExifTool()

    @patch('subprocess.run')
    def test_when_reading_metadata_then_returns_parsed_json(self, mock_run):
        """Should return parsed metadata when exiftool succeeds"""
        expected_metadata = {
            'Title': 'Test Video',
            'CreateDate': '2025:03:26 15:30:00',
            'Keywords': ['test', 'video']
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([expected_metadata])
        )

        result = self.exiftool.read_all_metadata(self.test_file)
        self.assertEqual(result, expected_metadata)
        mock_run.assert_called_once_with(
            ['exiftool', '-j', '-m', '-G', str(self.test_file)],
            capture_output=True,
            text=True
        )

    @patch('subprocess.run')
    def test_when_reading_metadata_fails_then_returns_empty_dict(self, mock_run):
        """Should return empty dict when exiftool fails"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='Error reading metadata'
        )

        result = self.exiftool.read_all_metadata(self.test_file)
        self.assertEqual(result, {})

    @patch('subprocess.run')
    def test_when_reading_metadata_raises_error_then_returns_empty_dict(self, mock_run):
        """Should return empty dict when subprocess raises error"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
        result = self.exiftool.read_all_metadata(self.test_file)
        self.assertEqual(result, {})

    @patch('subprocess.run')
    def test_when_reading_metadata_invalid_json_then_returns_empty_dict(self, mock_run):
        """Should return empty dict when JSON is invalid"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='invalid json'
        )
        result = self.exiftool.read_all_metadata(self.test_file)
        self.assertEqual(result, {})

    @patch('subprocess.run')
    def test_when_reading_date_then_returns_formatted_date(self, mock_run):
        """Should return properly formatted date from XMP"""
        expected_date = '2025:03:26 15:30:00'
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f'DateTimeOriginal: {expected_date}\n'
        )

        result = self.exiftool.read_date_from_xmp(self.test_xmp)
        self.assertEqual(result, expected_date)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        self.assertEqual(cmd_args[:2], ['exiftool', '-s'])
        self.assertEqual(cmd_args[-2:], ['-DateTimeOriginal', str(self.test_xmp)])

    @patch('subprocess.run')
    def test_when_date_not_in_xmp_then_returns_none(self, mock_run):
        """Should return None when date not found in XMP"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=''
        )

        result = self.exiftool.read_date_from_xmp(self.test_xmp)
        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_when_reading_date_raises_error_then_returns_none(self, mock_run):
        """Should return None when subprocess raises error"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
        result = self.exiftool.read_date_from_xmp(self.test_xmp)
        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_when_writing_metadata_then_formats_command_correctly(self, mock_run):
        """Should format exiftool command with correct flags and values"""
        mock_run.return_value = MagicMock(returncode=0)
        fields = {
            'Title': 'Test Video',
            'Keywords': ['test', 'video'],
            'Empty': None  # Should be skipped
        }

        result = self.exiftool.write_metadata(self.test_file, fields)
        self.assertTrue(result)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        self.assertIn('-Title=Test Video', cmd_args)
        self.assertIn('-Keywords=test,video', cmd_args)  # Keywords are joined with commas
        self.assertNotIn('-Empty', cmd_args)

    @patch('subprocess.run')
    def test_when_writing_metadata_fails_then_returns_false(self, mock_run):
        """Should return False when exiftool fails to write metadata"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
        fields = {'Title': 'Test Video'}

        result = self.exiftool.write_metadata(self.test_file, fields)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_when_writing_metadata_nonzero_exit_then_returns_false(self, mock_run):
        """Should return False when exiftool returns non-zero"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='Some error'
        )
        fields = {'Title': 'Test Video'}

        result = self.exiftool.write_metadata(self.test_file, fields)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_when_writing_metadata_with_predashed_fields_then_preserves_dash(self, mock_run):
        """Should preserve existing dashes in field names and not add extra ones"""
        mock_run.return_value = MagicMock(returncode=0)
        fields = {
            'Title': 'Test Video',  # Regular field
            '-ItemList:Title': 'Test Video',  # Pre-dashed field
            '-QuickTime:Title': 'Test Video'  # Another pre-dashed field
        }

        result = self.exiftool.write_metadata(self.test_file, fields)
        self.assertTrue(result)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        
        # Regular field should get dash added
        self.assertIn('-Title=Test Video', cmd_args)
        # Pre-dashed fields should not get extra dash
        self.assertIn('-ItemList:Title=Test Video', cmd_args)
        self.assertIn('-QuickTime:Title=Test Video', cmd_args)
        # Make sure no double-dashes were created
        self.assertNotIn('--', ' '.join(cmd_args))

    @patch('subprocess.run')
    def test_when_copying_metadata_then_formats_command_correctly(self, mock_run):
        """Should format copy metadata command correctly"""
        mock_run.return_value = MagicMock(returncode=0)
        source = Path('/test/source.mov')
        target = Path('/test/target.mov')

        result = self.exiftool.copy_metadata(source, target)
        self.assertTrue(result)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        self.assertEqual(cmd_args[-3:], ['-TagsFromFile', str(source), str(target)])

    @patch('subprocess.run')
    def test_when_copying_metadata_fails_then_returns_false(self, mock_run):
        """Should return False when copy metadata fails"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
        source = Path('/test/source.mov')
        target = Path('/test/target.mov')

        result = self.exiftool.copy_metadata(source, target)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_when_copying_metadata_nonzero_exit_then_returns_false(self, mock_run):
        """Should return False when copy returns non-zero"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='Some error'
        )
        source = Path('/test/source.mov')
        target = Path('/test/target.mov')

        result = self.exiftool.copy_metadata(source, target)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_when_updating_keywords_then_formats_command_correctly(self, mock_run):
        """Should format keywords command with correct flags and values"""
        mock_run.return_value = MagicMock(returncode=0)
        keywords = ['test', 'video']

        result = self.exiftool.update_keywords(self.test_file, keywords)
        self.assertTrue(result)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        self.assertIn('-keywords=test,video', cmd_args)

    @patch('subprocess.run')
    def test_when_updating_keywords_fails_then_returns_false(self, mock_run):
        """Should return False when exiftool fails to update keywords"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
        keywords = ['test']

        result = self.exiftool.update_keywords(self.test_file, keywords)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_when_updating_keywords_nonzero_exit_then_returns_false(self, mock_run):
        """Should return False when keywords update returns non-zero"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='Some error'
        )
        keywords = ['test']

        result = self.exiftool.update_keywords(self.test_file, keywords)
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
