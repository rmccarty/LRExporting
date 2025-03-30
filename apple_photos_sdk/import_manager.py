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
                self.logger.error(f"File does not exist: {photo_path}")
                return False
                
            # Log the ingest
            self.logger.info(f"Ingesting photo: {photo_path}")
            
            # Convert path to NSURL
            file_url = NSURL.fileURLWithPath_(str(photo_path))
            
            # Get shared photo library
            photo_library = PHPhotoLibrary.sharedPhotoLibrary()
            
            # Create a flag to track import success
            import_success = False
            
            def change_block():
                nonlocal import_success
                try:
                    # Create asset creation request
                    creation_request = PHAssetCreationRequest.creationRequestForAssetFromImageAtFileURL_(file_url)
                    if creation_request is not None:
                        import_success = True
                except Exception as e:
                    self.logger.error(f"Failed to create asset: {e}")
                    import_success = False
            
            # Perform changes in a block
            error = NSError.alloc().init()
            photo_library.performChanges_error_(change_block, error)
            
            if import_success:
                # Import succeeded - now handle deletion separately
                if DELETE_ORIGINAL:
                    try:
                        os.unlink(photo_path)
                        self.logger.info(f"Photo ingested and original deleted: {photo_path}")
                    except Exception as e:
                        # Log deletion error but don't fail the import
                        self.logger.warning(f"Import succeeded but failed to delete original: {e}")
                return True
            else:
                self.logger.error(f"Failed to import {photo_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Import failed for {photo_path}: {e}")
            return False
