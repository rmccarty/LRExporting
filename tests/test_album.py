"""Tests for the album module."""

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from apple_photos_sdk.album import AlbumManager

class TestAlbumManager(unittest.TestCase):
    """Test cases for AlbumManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = AlbumManager()
        self.test_album = "Test Album"
        self.test_photo = Path("/test/photo.jpg")
        
    def test_when_creating_album_then_succeeds(self):
        """Should successfully create an album."""
        # Act
        result = self.manager.create_album(self.test_album)
        
        # Assert
        self.assertTrue(result)
        self.assertIn(self.test_album, self.manager._albums)
        
    def test_when_creating_album_then_handles_error(self):
        """Should handle errors during album creation."""
        # Arrange
        mock_albums = MagicMock(spec=set)
        mock_albums.add.side_effect = Exception("Create error")
        self.manager._albums = mock_albums
        
        # Act
        result = self.manager.create_album(self.test_album)
        
        # Assert
        self.assertFalse(result)
        mock_albums.add.assert_called_once_with(self.test_album)
            
    def test_when_adding_to_nonexistent_album_then_fails(self):
        """Should fail when adding to nonexistent album."""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True):
            # Act
            result = self.manager.add_to_album(self.test_photo, "Nonexistent Album")
            
            # Assert
            self.assertFalse(result)
            
    def test_when_adding_nonexistent_photo_then_fails(self):
        """Should fail when adding nonexistent photo."""
        # Arrange
        self.manager.create_album(self.test_album)
        with patch('pathlib.Path.exists', return_value=False):
            # Act
            result = self.manager.add_to_album(self.test_photo, self.test_album)
            
            # Assert
            self.assertFalse(result)
            
    def test_when_adding_to_album_then_succeeds(self):
        """Should successfully add photo to album."""
        # Arrange
        self.manager.create_album(self.test_album)
        with patch('pathlib.Path.exists', return_value=True):
            # Act
            result = self.manager.add_to_album(self.test_photo, self.test_album)
            
            # Assert
            self.assertTrue(result)
            
    def test_when_adding_to_album_then_handles_error(self):
        """Should handle errors during photo addition."""
        # Arrange
        self.manager.create_album(self.test_album)
        with patch('pathlib.Path.exists', side_effect=Exception("Path error")):
            # Act
            result = self.manager.add_to_album(self.test_photo, self.test_album)
            
            # Assert
            self.assertFalse(result)
            
    def test_when_creating_album_then_logs_error(self):
        """Should log error when album creation fails."""
        # Arrange
        mock_albums = MagicMock(spec=set)
        mock_albums.add.side_effect = Exception("Create error")
        self.manager._albums = mock_albums
        
        with self.assertLogs(level='ERROR') as log:
            # Act
            self.manager.create_album(self.test_album)
            
            # Assert
            self.assertIn(f"Failed to create album {self.test_album}", log.output[0])
                
    def test_when_adding_to_album_then_logs_nonexistent_album_error(self):
        """Should log error when album does not exist."""
        # Arrange
        with self.assertLogs(level='ERROR') as log:
            with patch('pathlib.Path.exists', return_value=True):
                # Act
                self.manager.add_to_album(self.test_photo, "Nonexistent Album")
                
                # Assert
                self.assertIn("Album does not exist: Nonexistent Album", log.output[0])
                
    def test_when_adding_to_album_then_logs_nonexistent_photo_error(self):
        """Should log error when photo does not exist."""
        # Arrange
        self.manager.create_album(self.test_album)
        with self.assertLogs(level='ERROR') as log:
            with patch('pathlib.Path.exists', return_value=False):
                # Act
                self.manager.add_to_album(self.test_photo, self.test_album)
                
                # Assert
                self.assertIn(f"Photo does not exist: {self.test_photo}", log.output[0])
            
    def test_when_adding_to_album_then_logs_general_error(self):
        """Should log error when photo addition fails."""
        # Arrange
        self.manager.create_album(self.test_album)
        with self.assertLogs(level='ERROR') as log:
            with patch('pathlib.Path.exists', side_effect=Exception("Path error")):
                # Act
                self.manager.add_to_album(self.test_photo, self.test_album)
                
                # Assert
                self.assertIn(f"Failed to add {self.test_photo} to album {self.test_album}", log.output[0])

    def test_is_targeted_album_keyword(self):
        """Test _is_targeted_album_keyword with various prefixes and formats."""
        # Should match targeted prefixes
        self.assertTrue(self.manager._is_targeted_album_keyword("01/Family"))
        self.assertTrue(self.manager._is_targeted_album_keyword("02/Travel/Europe"))
        # Should match with 'Subject: ' prefix
        self.assertTrue(self.manager._is_targeted_album_keyword("Subject: 03/Events/Birthday"))
        # Should NOT match non-targeted
        self.assertFalse(self.manager._is_targeted_album_keyword("Random/Album"))
        self.assertFalse(self.manager._is_targeted_album_keyword("Subject: NotAnAlbum"))

    @patch("apple_photos_sdk.album.autorelease_pool")
    @patch("apple_photos_sdk.album.Photos")
    def test_create_folder_success_and_error(self, mock_photos, mock_pool):
        """Test _create_folder for success and error handling."""
        # Mock successful folder creation
        mock_folder = MagicMock()
        mock_placeholder = MagicMock()
        mock_placeholder.localIdentifier.return_value = "folder-id-123"
        mock_folder.placeholderForCreatedCollectionList.return_value = mock_placeholder
        mock_photos.PHCollectionListChangeRequest.creationRequestForCollectionListWithTitle_.return_value = mock_folder

        def perform_changes_and_wait_effect(callback, _):
            callback()  # This sets success/folder_id in the implementation
            return (True, None)
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = perform_changes_and_wait_effect

        success, folder_id = self.manager._create_folder("Test Folder")
        self.assertTrue(success)
        self.assertEqual(folder_id, "folder-id-123")

        # Mock failure (result False)
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = lambda cb, _: (False, None)
        success, folder_id = self.manager._create_folder("Fail Folder")
        self.assertFalse(success)
        self.assertIsNone(folder_id)

        # Mock exception
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = Exception("API error")
        success, folder_id = self.manager._create_folder("Error Folder")
        self.assertFalse(success)
        self.assertIsNone(folder_id)

    @patch("apple_photos_sdk.album.autorelease_pool")
    @patch("apple_photos_sdk.album.Photos")
    def test_create_album_in_folder_success_and_error(self, mock_photos, mock_pool):
        """Test _create_album_in_folder for success, already exists, and error handling."""
        # Setup for album already exists
        self.manager._find_album_in_folder = MagicMock(return_value="existing-album-id")
        success, album_id = self.manager._create_album_in_folder("Existing Album", "parent-folder-id")
        self.assertTrue(success)
        self.assertEqual(album_id, "existing-album-id")

        # Setup for new album creation success (with parent)
        self.manager._find_album_in_folder = MagicMock(return_value=None)
        mock_album = MagicMock()
        mock_placeholder = MagicMock()
        mock_placeholder.localIdentifier.return_value = "album-id-456"
        mock_album.placeholderForCreatedAssetCollection.return_value = mock_placeholder
        mock_photos.PHAssetCollectionChangeRequest.creationRequestForAssetCollectionWithTitle_.return_value = mock_album

        # Mock parent folder fetch
        mock_parent_result = MagicMock()
        mock_parent_result.count.return_value = 1
        mock_parent = MagicMock()
        mock_parent_result.objectAtIndex_.return_value = mock_parent
        mock_photos.PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_.return_value = mock_parent_result
        # Mock parent change request
        mock_parent_change = MagicMock()
        mock_photos.PHCollectionListChangeRequest.changeRequestForCollectionList_.return_value = mock_parent_change

        def perform_changes_and_wait_effect(callback, _):
            callback()  # This sets success/album_id in the implementation
            return (True, None)
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = perform_changes_and_wait_effect

        success, album_id = self.manager._create_album_in_folder("New Album", "parent-folder-id")
        self.assertTrue(success)
        self.assertEqual(album_id, "album-id-456")

        # Setup for failure (result False)
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = lambda cb, _: (False, None)
        success, album_id = self.manager._create_album_in_folder("Fail Album", "parent-folder-id")
        self.assertFalse(success)
        self.assertIsNone(album_id)

        # Setup for exception
        mock_photos.PHPhotoLibrary.sharedPhotoLibrary.return_value.performChangesAndWait_error_.side_effect = Exception("API error")
        success, album_id = self.manager._create_album_in_folder("Error Album", "parent-folder-id")
        self.assertFalse(success)
        self.assertIsNone(album_id)

    @patch("apple_photos_sdk.album.autorelease_pool")
    @patch("apple_photos_sdk.album.Photos")
    def test_add_asset_to_targeted_albums(self, mock_photos, mock_pool):
        """Test add_asset_to_targeted_albums for normal, partial, and error cases."""
        # Setup mocks for _create_folder_path, _create_album_in_folder, _add_to_album
        asset_id = "asset-123"
        targeted_keywords = ["01/Family/2020", "02/Travel/Europe"]

        # All succeed
        self.manager._create_folder_path = MagicMock(return_value=(True, "folder-1"))
        self.manager._create_album_in_folder = MagicMock(return_value=(True, "album-1"))
        self.manager._add_to_album = MagicMock(return_value=True)
        result = self.manager.add_asset_to_targeted_albums(asset_id, targeted_keywords)
        self.assertTrue(result)
        self.assertEqual(self.manager._create_folder_path.call_count, 2)
        self.assertEqual(self.manager._create_album_in_folder.call_count, 2)
        self.assertEqual(self.manager._add_to_album.call_count, 2)

        # One album fails to create
        self.manager._create_folder_path.reset_mock()
        self.manager._create_album_in_folder.reset_mock()
        self.manager._add_to_album.reset_mock()
        self.manager._create_folder_path.side_effect = [(True, "folder-1"), (False, None)]
        result = self.manager.add_asset_to_targeted_albums(asset_id, targeted_keywords)
        self.assertFalse(result)
        self.assertEqual(self.manager._create_folder_path.call_count, 2)
        self.assertEqual(self.manager._create_album_in_folder.call_count, 1)
        self.assertEqual(self.manager._add_to_album.call_count, 1)

        # _add_to_album fails
        self.manager._create_folder_path = MagicMock(return_value=(True, "folder-1"))
        self.manager._create_album_in_folder = MagicMock(return_value=(True, "album-1"))
        self.manager._add_to_album = MagicMock(side_effect=[True, False])
        result = self.manager.add_asset_to_targeted_albums(asset_id, targeted_keywords)
        self.assertFalse(result)
        self.assertEqual(self.manager._add_to_album.call_count, 2)

        # Exception in _create_album_in_folder
        self.manager._create_folder_path = MagicMock(return_value=(True, "folder-1"))
        self.manager._create_album_in_folder = MagicMock(side_effect=Exception("API error"))
        self.manager._add_to_album = MagicMock(return_value=True)
        with self.assertRaises(Exception):
            self.manager.add_asset_to_targeted_albums(asset_id, targeted_keywords)
