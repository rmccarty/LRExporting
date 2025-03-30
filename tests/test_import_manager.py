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
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class:
            mock_request = MagicMock()
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(result)
            mock_nsurl.fileURLWithPath_.assert_called_once_with(str(self.test_file))
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.assert_called_once_with(mock_file_url)
            
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
            return False
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class:
            mock_request = MagicMock()
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = None
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(result)
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_photos_library_raises_then_returns_false(self, mock_nsurl, mock_library):
        """Should handle Photos library errors gracefully."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        mock_shared.performChangesAndWait_error_.side_effect = Exception("Photos library error")
        
        with patch('pathlib.Path.exists', return_value=True):
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(result)
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    @patch('apple_photos_sdk.import_manager.DELETE_ORIGINAL', True)
    def test_when_import_succeeds_but_delete_fails_then_returns_true(self, mock_nsurl, mock_library):
        """Should return True even if deletion fails after successful import."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('os.unlink', side_effect=OSError("Delete failed")):
            mock_request = MagicMock()
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(result)  # Import succeeded, even though delete failed
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    @patch('apple_photos_sdk.import_manager.DELETE_ORIGINAL', False)
    def test_when_delete_disabled_then_preserves_file(self, mock_nsurl, mock_library):
        """Should preserve original file when deletion is disabled."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('os.unlink') as mock_unlink:
            mock_request = MagicMock()
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            result = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(result)
            mock_unlink.assert_not_called()  # Should not try to delete file

    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_photo_then_logs_correctly(self, mock_nsurl, mock_library):
        """Should log appropriate messages during import."""
        # Arrange
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             self.assertLogs(logger='apple_photos_sdk.import_manager', level='INFO') as log:
            mock_request = MagicMock()
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            self.manager.import_photo(self.test_file)
            
            # Assert
            expected_msg = f"INFO:apple_photos_sdk.import_manager:Ingesting photo: {self.test_file}"
            self.assertIn(expected_msg, log.output)
