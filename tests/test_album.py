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
