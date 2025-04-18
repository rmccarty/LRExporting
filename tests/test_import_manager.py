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
        
    def _setup_successful_import_mocks(self, mock_nsurl, mock_library, mock_request_class):
        """Helper to set up mocks for successful import."""
        mock_file_url = MagicMock()
        mock_nsurl.fileURLWithPath_.return_value = mock_file_url
        
        mock_shared = MagicMock()
        mock_library.sharedPhotoLibrary.return_value = mock_shared
        
        def perform_changes(block, error):
            block()
            return True
            
        mock_shared.performChangesAndWait_error_.side_effect = perform_changes
        
        mock_request = MagicMock()
        mock_placeholder = MagicMock()
        mock_placeholder.localIdentifier.return_value = "test-id-123"
        mock_request.placeholderForCreatedAsset.return_value = mock_placeholder
        mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
        mock_request_class.creationRequestForAssetFromVideoAtFileURL_.return_value = mock_request
        
        return mock_file_url, mock_shared, mock_request
        
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_photo_then_succeeds(self, mock_nsurl, mock_library):
        """Should successfully import photo."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True):
            
            # Arrange
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(success)
            self.assertEqual(asset_id, "test-id-123")
            mock_nsurl.fileURLWithPath_.assert_called_once_with(str(self.test_file))
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.assert_called_once_with(mock_file_url)
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_nonexistent_photo_then_fails(self, mock_nsurl, mock_library):
        """Should fail when photo doesn't exist."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=False):
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            mock_nsurl.fileURLWithPath_.assert_not_called()
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_import_fails_then_returns_false(self, mock_nsurl, mock_library):
        """Should return False when import fails."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class:
            # Arrange
            mock_file_url = MagicMock()
            mock_nsurl.fileURLWithPath_.return_value = mock_file_url
            
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.return_value = mock_shared
            
            def perform_changes(block, error):
                block()
                return False
                
            mock_shared.performChangesAndWait_error_.side_effect = perform_changes
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = None
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
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
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    @patch('apple_photos_sdk.import_manager.DELETE_ORIGINAL', True)
    def test_when_import_succeeds_but_delete_fails_then_returns_true(self, mock_nsurl, mock_library):
        """Should return True even if deletion fails after successful import."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('os.unlink', side_effect=OSError("Delete failed")), \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True):
            
            # Arrange
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(success)  # Import succeeded, even though delete failed
            self.assertEqual(asset_id, "test-id-123")
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    @patch('apple_photos_sdk.import_manager.DELETE_ORIGINAL', False)
    def test_when_delete_disabled_then_preserves_file(self, mock_nsurl, mock_library):
        """Should preserve original file when deletion is disabled."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('os.unlink') as mock_unlink, \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True):
            
            # Arrange
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(success)
            self.assertEqual(asset_id, "test-id-123")
            mock_unlink.assert_not_called()  # Should not try to delete file
            
    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_photo_then_logs_correctly(self, mock_nsurl, mock_library):
        """Should log appropriate messages during import."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True), \
             self.assertLogs(logger='apple_photos_sdk.import_manager', level='INFO') as log:
            
            # Arrange
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            
            # Act
            self.manager.import_photo(self.test_file)
            
            # Assert
            expected_msg = f"INFO:apple_photos_sdk.import_manager:Importing photo: {self.test_file}"
            self.assertIn(expected_msg, log.output)

    def test_when_getting_asset_type_then_identifies_correctly(self):
        """Should correctly identify asset types based on extension."""
        # Photo tests
        self.assertEqual(self.manager._get_asset_type(Path('test.jpg')), 'photo')
        self.assertEqual(self.manager._get_asset_type(Path('test.jpeg')), 'photo')
        self.assertEqual(self.manager._get_asset_type(Path('test.JPG')), 'photo')
        
        # Video tests
        self.assertEqual(self.manager._get_asset_type(Path('test.mp4')), 'video')
        self.assertEqual(self.manager._get_asset_type(Path('test.mov')), 'video')
        self.assertEqual(self.manager._get_asset_type(Path('test.MOV')), 'video')
        
        # Invalid extension
        with self.assertRaises(ValueError):
            self.manager._get_asset_type(Path('test.txt'))
            
    def test_when_importing_video_then_succeeds(self):
        """Should successfully import video."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('apple_photos_sdk.import_manager.NSURL') as mock_nsurl, \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library, \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True):
            
            # Arrange
            test_video = Path('/test/video.mp4')
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            
            # Act
            success, asset_id = self.manager.import_photo(test_video)
            
            # Assert
            self.assertTrue(success)
            self.assertEqual(asset_id, "test-id-123")
            mock_request_class.creationRequestForAssetFromVideoAtFileURL_.assert_called_once_with(mock_file_url)
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.assert_not_called()
            
    def test_when_verifying_asset_then_retries_on_failure(self):
        """Should retry asset verification before giving up."""
        with patch('apple_photos_sdk.import_manager.PHAsset') as mock_asset_class, \
             patch('time.sleep') as mock_sleep:  # Mock sleep to speed up test
            
            # Arrange
            mock_result = MagicMock()
            mock_result.count.return_value = 0  # Asset not found
            mock_asset_class.fetchAssetsWithLocalIdentifiers_options_.return_value = mock_result
            
            # Act
            result = self.manager._verify_asset_exists('test-id', max_attempts=3, delay=0.1)
            
            # Assert
            self.assertFalse(result)
            self.assertEqual(mock_asset_class.fetchAssetsWithLocalIdentifiers_options_.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)  # Should sleep between retries
            
    def test_when_verifying_asset_then_succeeds_on_retry(self):
        """Should succeed if asset appears on retry."""
        with patch('apple_photos_sdk.import_manager.PHAsset') as mock_asset_class, \
             patch('time.sleep') as mock_sleep:
            
            # Arrange
            fail_result = MagicMock()
            fail_result.count.return_value = 0
            
            success_result = MagicMock()
            success_result.count.return_value = 1
            
            mock_asset_class.fetchAssetsWithLocalIdentifiers_options_.side_effect = [
                fail_result,   # First attempt fails
                success_result # Second attempt succeeds
            ]
            
            # Act
            result = self.manager._verify_asset_exists('test-id', max_attempts=3, delay=0.1)
            
            # Assert
            self.assertTrue(result)
            self.assertEqual(mock_asset_class.fetchAssetsWithLocalIdentifiers_options_.call_count, 2)
            self.assertEqual(mock_sleep.call_count, 1)  # Should only sleep once
            
    def test_when_creating_asset_request_then_handles_errors(self):
        """Should handle errors in asset request creation."""
        with patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class:
            # Test photo request failure
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = None
            request = self.manager._create_asset_request(MagicMock(), 'photo')
            self.assertIsNone(request)
            
            # Test video request failure
            mock_request_class.creationRequestForAssetFromVideoAtFileURL_.return_value = None
            request = self.manager._create_asset_request(MagicMock(), 'video')
            self.assertIsNone(request)
            
            # Test invalid type
            with self.assertRaises(ValueError):
                self.manager._create_asset_request(MagicMock(), 'invalid')

    def test_when_importing_nonexistent_photo_then_fails(self):
        """Should fail when photo doesn't exist."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=False):
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    def test_when_import_fails_then_returns_false(self):
        """Should return False when import fails."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library:
            # Mock shared library
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.return_value = mock_shared
            mock_shared.performChangesAndWait_error_.return_value = False
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    def test_when_photos_library_raises_then_returns_false(self):
        """Should handle Photos library errors gracefully."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library:
            # Mock shared library to raise
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.side_effect = Exception("Photos library error")
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    def test_when_importing_photo_then_handles_get_asset_type_error(self):
        """Should handle errors in asset type detection."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True), \
             patch.object(ImportManager, '_get_asset_type', side_effect=ValueError("Invalid extension")):
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    def test_when_placeholder_is_none_then_fails(self):
        """Should fail when placeholder asset is None."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('apple_photos_sdk.import_manager.NSURL') as mock_nsurl, \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library:
            
            # Mock file URL
            mock_file_url = MagicMock()
            mock_nsurl.fileURLWithPath_.return_value = mock_file_url
            
            # Mock shared library
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.return_value = mock_shared
            
            def perform_changes(block, error):
                block()
                return True
                
            mock_shared.performChangesAndWait_error_.side_effect = perform_changes
            
            # Mock request with None placeholder
            mock_request = MagicMock()
            mock_request.placeholderForCreatedAsset.return_value = None
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)
            
    def test_when_importing_photo_then_handles_placeholder_id_error(self):
        """Should handle errors getting placeholder ID."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('apple_photos_sdk.import_manager.NSURL') as mock_nsurl, \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library:
            
            # Mock file URL
            mock_file_url = MagicMock()
            mock_nsurl.fileURLWithPath_.return_value = mock_file_url
            
            # Mock shared library
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.return_value = mock_shared
            
            def perform_changes(block, error):
                block()
                return True
                
            mock_shared.performChangesAndWait_error_.side_effect = perform_changes
            
            # Mock request with placeholder that raises
            mock_request = MagicMock()
            mock_placeholder = MagicMock()
            mock_placeholder.localIdentifier.side_effect = Exception("ID error")
            mock_request.placeholderForCreatedAsset.return_value = mock_placeholder
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertFalse(success)
            self.assertIsNone(asset_id)

    @patch('subprocess.run')
    def test_when_importing_photo_then_gets_keywords(self, mock_run):
        """Should get keywords from original file before import."""
        # Mock exiftool output for both calls
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="test||photo"),
            MagicMock(returncode=0, stdout="Title")
        ]
        
        # Mock Photos library dependencies
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch('apple_photos_sdk.import_manager.NSURL') as mock_nsurl, \
             patch('apple_photos_sdk.import_manager.PHPhotoLibrary') as mock_library, \
             patch('apple_photos_sdk.import_manager.PHAsset') as mock_asset_class:
            
            # Mock file URL
            mock_file_url = MagicMock()
            mock_nsurl.fileURLWithPath_.return_value = mock_file_url
            
            # Mock shared library
            mock_shared = MagicMock()
            mock_library.sharedPhotoLibrary.return_value = mock_shared
            
            def perform_changes(block, error):
                block()
                return True
            mock_shared.performChangesAndWait_error_.side_effect = perform_changes
            
            # Mock request and placeholder
            mock_request = MagicMock()
            mock_placeholder = MagicMock()
            mock_placeholder.localIdentifier.return_value = 'test-id'
            mock_request.placeholderForCreatedAsset.return_value = mock_placeholder
            mock_request_class.creationRequestForAssetFromImageAtFileURL_.return_value = mock_request
            
            # Mock asset fetch for verification
            mock_result = MagicMock()
            mock_result.count.return_value = 1
            mock_asset_class.fetchAssetsWithLocalIdentifiers_options_.return_value = mock_result
            
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            
            # Assert
            self.assertTrue(success)
            self.assertEqual(asset_id, 'test-id')
            self.assertEqual(mock_run.call_count, 2)
            mock_run.assert_any_call(
                ["exiftool", "-XMP:Subject", "-s", "-s", "-sep", "||", str(self.test_file)],
                capture_output=True,
                text=True
            )
            mock_run.assert_any_call(
                ["exiftool", "-IPTC:ObjectName", "-XMP:Title", "-s", "-s", "-j", str(self.test_file)],
                capture_output=True,
                text=True
            )

    @patch('apple_photos_sdk.import_manager.PHPhotoLibrary')
    @patch('apple_photos_sdk.import_manager.NSURL')
    def test_when_importing_photo_then_does_not_add_to_album(self, mock_nsurl, mock_library):
        """Should not attempt album assignment during import."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('apple_photos_sdk.import_manager.PHAssetCreationRequest') as mock_request_class, \
             patch.object(ImportManager, '_verify_asset_exists', return_value=True) as mock_verify:
            # Arrange
            mock_file_url, mock_shared, mock_request = self._setup_successful_import_mocks(
                mock_nsurl, mock_library, mock_request_class)
            # Act
            success, asset_id = self.manager.import_photo(self.test_file)
            # Assert
            self.assertTrue(success)
            self.assertEqual(asset_id, "test-id-123")
            # There should be no call to any album assignment logic (since it's removed)
            # (If album assignment was a method, we would patch and assert_not_called)

    def test_get_asset_type_photo(self):
        path = Path('test.jpg')
        manager = ImportManager()
        with patch('apple_photos_sdk.import_manager.IMAGE_EXTENSIONS', ['.jpg', '.jpeg']):
            self.assertEqual(manager._get_asset_type(path), 'photo')

    def test_get_asset_type_video(self):
        path = Path('test.mov')
        manager = ImportManager()
        with patch('apple_photos_sdk.import_manager.VIDEO_EXTENSIONS', ['.mov', '.mp4']):
            self.assertEqual(manager._get_asset_type(path), 'video')

    def test_get_asset_type_invalid(self):
        path = Path('test.txt')
        manager = ImportManager()
        with patch('apple_photos_sdk.import_manager.IMAGE_EXTENSIONS', ['.jpg']), \
             patch('apple_photos_sdk.import_manager.VIDEO_EXTENSIONS', ['.mov']):
            with self.assertRaises(ValueError):
                manager._get_asset_type(path)

    def test_is_targeted_keyword(self):
        manager = ImportManager()
        with patch('apple_photos_sdk.import_manager.TARGETED_ALBUM_PREFIXES', ['MyPrefix']):
            self.assertTrue(manager._is_targeted_keyword('MyPrefixSomething'))
            self.assertTrue(manager._is_targeted_keyword('Subject: MyPrefixSomething'))
            self.assertFalse(manager._is_targeted_keyword('OtherPrefixSomething'))

    def test_get_asset_keywords_always_empty(self):
        manager = ImportManager()
        self.assertEqual(manager._get_asset_keywords('any_id'), [])

    def test_handle_image_data_always_empty(self):
        manager = ImportManager()
        self.assertEqual(manager._handle_image_data(None, None, None, None), [])

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_keywords_success(self, mock_run):
        manager = ImportManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'keyword1||keyword2||keyword3'
        mock_run.return_value = mock_result
        with patch('apple_photos_sdk.import_manager.TARGETED_ALBUM_PREFIXES', ['keyword']):
            keywords = manager._get_original_keywords(Path('photo.jpg'))
            self.assertEqual(keywords, ['keyword1', 'keyword2', 'keyword3'])
            mock_run.assert_called_once()

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_keywords_no_keywords(self, mock_run):
        manager = ImportManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ''
        mock_run.return_value = mock_result
        keywords = manager._get_original_keywords(Path('photo.jpg'))
        self.assertEqual(keywords, [])

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_keywords_exception(self, mock_run):
        manager = ImportManager()
        mock_run.side_effect = Exception('fail')
        keywords = manager._get_original_keywords(Path('photo.jpg'))
        self.assertEqual(keywords, [])

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_title_success(self, mock_run):
        manager = ImportManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"ObjectName": "Title1"}]'
        mock_run.return_value = mock_result
        title = manager._get_original_title(Path('photo.jpg'))
        self.assertEqual(title, 'Title1')

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_title_no_title(self, mock_run):
        manager = ImportManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{}]'
        mock_run.return_value = mock_result
        title = manager._get_original_title(Path('photo.jpg'))
        self.assertIsNone(title)

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_title_invalid_json(self, mock_run):
        manager = ImportManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'not json'
        mock_run.return_value = mock_result
        title = manager._get_original_title(Path('photo.jpg'))
        self.assertIsNone(title)

    @patch('apple_photos_sdk.import_manager.subprocess.run')
    def test_get_original_title_exception(self, mock_run):
        manager = ImportManager()
        mock_run.side_effect = Exception('fail')
        title = manager._get_original_title(Path('photo.jpg'))
        self.assertIsNone(title)
