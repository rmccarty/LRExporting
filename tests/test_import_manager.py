"""Tests for the ImportManager class."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apple_photos_sdk.import_manager import ImportManager

class TestImportManager(unittest.TestCase):
    """Test cases for ImportManager."""
    
    def setUp(self):
        """Set up test cases."""
        self.manager = ImportManager()
        self.test_file = Path('/test/photo.jpg')
        
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_photo_then_succeeds(self, mock_nsurl, mock_library):
        """Should successfully import photo."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChanges_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request:
            mock_request.creationRequestForAssetFromImageAtFileURL_.return_value = MagicMock()
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(result)
            mock_nsurl.fileURLWithPath_.assert_called_once_with(str(self.test_file))
            mock_request.creationRequestForAssetFromImageAtFileURL_.assert_called_once_with(mock_file_url)
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_nonexistent_photo_then_fails(self, mock_nsurl, mock_library):
        """Should fail when photo doesn't exist."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=False):
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(result)
            mock_nsurl.fileURLWithPath_.assert_not_called()
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_import_fails_then_returns_false(self, mock_nsurl, mock_library):
        """Should return False when import fails."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChanges_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request:
            mock_request.creationRequestForAssetFromImageAtFileURL_.return_value = None
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(result)
