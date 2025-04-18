"""Tests for the Apple Photos SDK main interface."""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from apple_photos_sdk import ApplePhotos

class TestApplePhotos(unittest.TestCase):
    """Test cases for the ApplePhotos class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.photos = ApplePhotos()
        self.test_photo = Path("/test/photo.jpg")
        
    def test_import_photo_success(self):
        """Should successfully import a photo."""
        with patch('apple_photos_sdk.import_manager.ImportManager.import_photo', return_value=(True, "mock_asset_id")):
            result = self.photos.import_photo(self.test_photo)
            self.assertTrue(result)
            
    def test_import_photo_failure(self):
        """Should handle import failures gracefully."""
        with patch('apple_photos_sdk.import_manager.ImportManager.import_photo', return_value=False):
            result = self.photos.import_photo(self.test_photo)
            self.assertFalse(result)
            
    def test_import_photo_exception(self):
        """Should handle exceptions during import."""
        with patch('apple_photos_sdk.import_manager.ImportManager.import_photo', side_effect=Exception("Import failed")):
            result = self.photos.import_photo(self.test_photo)
            self.assertFalse(result)
