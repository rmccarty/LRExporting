"""Tests for the Apple Photos SDK album manager."""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
from apple_photos_sdk.album import AlbumManager

class TestAlbumManager(unittest.TestCase):
    """Test cases for the AlbumManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = AlbumManager()
        # Create a temporary file for testing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        self.test_photo = Path(self.temp_file.name)
        self.test_album = "Test Album"
        
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_file.close()
        if self.test_photo.exists():
            self.test_photo.unlink()
        
    def test_create_album_success(self):
        """Should successfully create an album."""
        result = self.manager.create_album(self.test_album)
        self.assertTrue(result)
            
    def test_add_to_album_success(self):
        """Should successfully add a photo to an album."""
        # First create the album
        self.manager.create_album(self.test_album)
        result = self.manager.add_to_album(self.test_photo, self.test_album)
        self.assertTrue(result)
        
    def test_add_to_album_nonexistent_photo(self):
        """Should handle non-existent photos."""
        self.manager.create_album(self.test_album)
        result = self.manager.add_to_album(Path("/nonexistent/photo.jpg"), self.test_album)
        self.assertFalse(result)
        
    def test_add_to_album_nonexistent_album(self):
        """Should handle non-existent albums."""
        result = self.manager.add_to_album(self.test_photo, "Nonexistent Album")
        self.assertFalse(result)
