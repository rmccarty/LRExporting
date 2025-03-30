"""Main interface for Apple Photos operations."""

import logging
from pathlib import Path
from .import_manager import ImportManager
from .album import AlbumManager

class ApplePhotos:
    """Main interface for Apple Photos operations."""
    
    def __init__(self):
        """Initialize Apple Photos interface."""
        self.logger = logging.getLogger(__name__)
        self.import_manager = ImportManager()
        self.album_manager = AlbumManager()
        
    def import_photo(self, photo_path: Path) -> bool:
        """
        Import a single photo into Apple Photos.
        
        Args:
            photo_path: Path to the photo file
            
        Returns:
            bool: True if import successful, False if failed
        """
        try:
            return self.import_manager.import_photo(photo_path)
        except Exception as e:
            self.logger.error(f"Failed to import {photo_path}: {e}")
            return False
