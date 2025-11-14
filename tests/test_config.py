#!/usr/bin/env python3

import unittest
from pathlib import Path

from config import (
    VERIFY_FIELDS,
    TRANSFER_PATHS,
    APPLE_PHOTOS_PATHS,
    MIN_FILE_AGE,
    FILENAME_REPLACEMENTS,
    LRE_SUFFIX,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    RON_INCOMING,
    CLAUDIA_INCOMING,
    TRANSFER_BATCH_SIZE
)

class TestConfig(unittest.TestCase):
    """Test configuration values and types."""
    
    def test_verify_fields_contains_required_fields(self):
        """Should contain all required metadata fields."""
        expected_fields = {
            'Title',
            'Keywords',
            'CreateDate',
            'Location',
            'City',
            'Country'
        }
        self.assertEqual(set(VERIFY_FIELDS), expected_fields)
        
    def test_transfer_paths_structure(self):
        """Should have correct paths for each incoming directory."""
        # Check Ron's path
        self.assertIn(RON_INCOMING, TRANSFER_PATHS)
        self.assertIsInstance(TRANSFER_PATHS[RON_INCOMING], Path)
        self.assertEqual(
            str(TRANSFER_PATHS[RON_INCOMING]),
            "/Users/rmccarty/Transfers/Ron/Ron_Apple_Photos"
        )
        
        # Check Claudia's path
        self.assertIn(CLAUDIA_INCOMING, TRANSFER_PATHS)
        self.assertIsInstance(TRANSFER_PATHS[CLAUDIA_INCOMING], Path)
        self.assertEqual(
            str(TRANSFER_PATHS[CLAUDIA_INCOMING]),
            "/Users/rmccarty/Library/Mobile Documents/com~apple~CloudDocs/Shared/OldPhotographs"
        )
        
    def test_apple_photos_paths_structure(self):
        """Should correctly identify Apple Photos destinations."""
        ron_path = Path("/Users/rmccarty/Transfers/Ron/Ron_Apple_Photos")
        claudia_path = Path("/Users/rmccarty/Library/Mobile Documents/com~apple~CloudDocs/Shared/OldPhotographs")
        
        # Ron's path should be in APPLE_PHOTOS_PATHS
        self.assertIn(ron_path, APPLE_PHOTOS_PATHS)
        # Claudia's path should NOT be in APPLE_PHOTOS_PATHS
        self.assertNotIn(claudia_path, APPLE_PHOTOS_PATHS)

    def test_min_file_age(self):
        """Should have positive integer value for minimum file age."""
        self.assertIsInstance(MIN_FILE_AGE, int)
        self.assertGreater(MIN_FILE_AGE, 0)
        
    def test_filename_replacements(self):
        """Should have valid character replacements."""
        # Check types
        self.assertIsInstance(FILENAME_REPLACEMENTS, dict)
        for key, value in FILENAME_REPLACEMENTS.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
            
        # Check specific replacements
        self.assertEqual(FILENAME_REPLACEMENTS[':'], ' -')
        self.assertEqual(FILENAME_REPLACEMENTS['/'], '_')
        
    def test_lre_suffix(self):
        """Should have correct LRE suffix."""
        self.assertEqual(LRE_SUFFIX, '__LRE')
        
    def test_mccartys_strings(self):
        """Should have correct McCartys strings."""
        self.assertEqual(MCCARTYS_PREFIX, 'The McCartys ')
        self.assertEqual(MCCARTYS_REPLACEMENT, 'The McCartys: ')
        
    def test_transfer_and_apple_photos_paths_consistency(self):
        """Should have matching paths between TRANSFER_PATHS values and APPLE_PHOTOS_PATHS."""
        transfer_paths = {str(path) for path in TRANSFER_PATHS.values()}
        apple_photos_paths = {str(path) for path in APPLE_PHOTOS_PATHS}
        
        # All Apple Photos paths should be in transfer paths
        self.assertTrue(apple_photos_paths.issubset(transfer_paths))

    def test_transfer_batch_size(self):
        """Should have positive integer value for transfer batch size."""
        self.assertIsInstance(TRANSFER_BATCH_SIZE, int)
        self.assertGreater(TRANSFER_BATCH_SIZE, 0)
        # Should be reasonable for batch processing (not too high)
        self.assertLessEqual(TRANSFER_BATCH_SIZE, 100)

if __name__ == '__main__':
    unittest.main()
