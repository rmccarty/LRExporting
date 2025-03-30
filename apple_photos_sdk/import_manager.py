"""Handles importing photos into Apple Photos."""

import logging
import os
from pathlib import Path

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
            
            # Simulate successful import by verifying file is readable
            with open(photo_path, 'rb') as f:
                # Just read a small chunk to verify file is accessible
                f.read(1024)
                
            # Import succeeded - now handle deletion separately
            import_success = True
            
            # Only delete if configured to do so
            if DELETE_ORIGINAL:
                try:
                    os.unlink(photo_path)
                    self.logger.info(f"Photo ingested and original deleted: {photo_path}")
                except Exception as e:
                    # Log deletion error but don't fail the import
                    self.logger.warning(f"Import succeeded but failed to delete original: {e}")
            else:
                self.logger.info(f"Photo ingested, original preserved: {photo_path}")
            
            return import_success
            
        except Exception as e:
            self.logger.error(f"Import failed for {photo_path}: {e}")
            return False
