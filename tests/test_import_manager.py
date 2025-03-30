"""Tests for the Apple Photos SDK import manager."""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
from apple_photos_sdk.import_manager import ImportManager

class TestImportManager(unittest.TestCase):
    """Test cases for the ImportManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = ImportManager()
        # Create a temporary file for testing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        self.test_photo = Path(self.temp_file.name)
        
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_file.close()
        if self.test_photo.exists():
            self.test_photo.unlink()
        
    def test_import_photo_success(self):
        """Should successfully import a photo."""
        result = self.manager.import_photo(self.test_photo)
        self.assertTrue(result)
        
    def test_import_photo_nonexistent_file(self):
        """Should handle non-existent files."""
        result = self.manager.import_photo(Path("/nonexistent/photo.jpg"))
        self.assertFalse(result)
