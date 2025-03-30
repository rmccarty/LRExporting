"""Handles importing photos into Apple Photos."""

import logging
import os
from pathlib import Path

from Photos import (
    PHAssetChangeRequest,
    PHAssetCreationRequest,
    PHPhotoLibrary,
)
from Foundation import (
    NSURL,
    NSError,
)

from .config import DELETE_ORIGINAL

class ImportManager:
    """Manages photo import operations for Apple Photos."""
    
    def __init__(self):
        """Initialize the import manager."""
        self.logger = logging.getLogger(__name__)
        
    def import_photo(self, photo_path: Path) -> bool:
        """
        Import a photo into Apple Photos.
        
        Args:
            photo_path: Path to the photo file
            
        Returns:
            bool: True if import successful (regardless of deletion), False if import failed
        """
        try:
            # Check if file exists
            if not photo_path.exists():
                self.logger.error(f"Photo does not exist: {photo_path}")
                return False
                
            # Log the ingest
            self.logger.info(f"Ingesting photo: {photo_path}")
            
            # Convert path to NSURL
            file_url = NSURL.fileURLWithPath_(str(photo_path))
            
            # Get shared photo library
            shared = PHPhotoLibrary.sharedPhotoLibrary()
            
            # Create a flag to track import success
            def changes():
                creation_request = PHAssetCreationRequest.creationRequestForAssetFromImageAtFileURL_(file_url)
                if creation_request is None:
                    raise Exception("Import failed")
            
            success = shared.performChangesAndWait_error_(changes, None)
            
            if success and DELETE_ORIGINAL:
                try:
                    photo_path.unlink()
                    self.logger.info(f"Photo ingested and original deleted: {photo_path}")
                except Exception as e:
                    # Log deletion error but don't fail the import
                    self.logger.error(f"Import succeeded but failed to delete original: {e}")
                    
            return success
                
        except Exception as e:
            self.logger.error(f"Import failed for {photo_path}: {e}")
            return False
