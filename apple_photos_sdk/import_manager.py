"""Handles importing photos into Apple Photos."""

import logging
import os
import time
from pathlib import Path

from Photos import (
    PHAssetChangeRequest,
    PHAssetCreationRequest,
    PHPhotoLibrary,
    PHAsset,
    PHAssetMediaType,
    PHFetchOptions,
)
from Foundation import (
    NSURL,
    NSError,
)

from .config import DELETE_ORIGINAL, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

class ImportManager:
    """Manages photo import operations for Apple Photos."""
    
    def __init__(self):
        """Initialize the import manager."""
        self.logger = logging.getLogger(__name__)
        
    def _get_asset_type(self, file_path: Path) -> str:
        """
        Determine if the file is a photo or video based on extension.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            str: 'photo' or 'video'
        """
        ext = file_path.suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return 'photo'
        elif ext in VIDEO_EXTENSIONS:
            return 'video'
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
            
    def _verify_asset_exists(self, local_id: str, max_attempts: int = 3, delay: float = 0.5) -> bool:
        """
        Verify that an asset exists in the Photos library by its local identifier.
        
        Args:
            local_id: The local identifier of the asset to verify
            max_attempts: Maximum number of attempts to verify
            delay: Delay in seconds between attempts
            
        Returns:
            bool: True if asset exists and is accessible
        """
        for attempt in range(max_attempts):
            try:
                # Try to fetch the asset
                result = PHAsset.fetchAssetsWithLocalIdentifiers_options_([local_id], None)
                if result and result.count() > 0:
                    self.logger.info(f"Asset verified in Photos library: {local_id}")
                    return True
            except Exception as e:
                self.logger.error(f"Error verifying asset {local_id}: {e}")
                return False
                
            if attempt < max_attempts - 1:
                self.logger.debug(f"Asset not found yet, retrying in {delay}s (attempt {attempt + 1}/{max_attempts})")
                time.sleep(delay)
                
        self.logger.error(f"Failed to verify asset in Photos library after {max_attempts} attempts: {local_id}")
        return False
            
    def _create_asset_request(self, file_url, asset_type: str):
        """
        Create the appropriate asset request based on media type.
        
        Args:
            file_url: NSURL for the media file
            asset_type: Either 'photo' or 'video'
            
        Returns:
            PHAssetCreationRequest: The creation request object
        """
        if asset_type == 'photo':
            return PHAssetCreationRequest.creationRequestForAssetFromImageAtFileURL_(file_url)
        elif asset_type == 'video':
            return PHAssetCreationRequest.creationRequestForAssetFromVideoAtFileURL_(file_url)
        else:
            raise ValueError(f"Unsupported asset type: {asset_type}")
            
    def import_photo(self, photo_path: Path) -> bool:
        """Import a photo or video into Apple Photos."""
        try:
            if not photo_path.exists():
                self.logger.error(f"File does not exist: {photo_path}")
                return False

            # Identify asset type
            try:
                asset_type = self._get_asset_type(photo_path)
                self.logger.info(f"Importing {asset_type}: {photo_path}")
            except ValueError as e:
                self.logger.error(str(e))
                return False
                
            file_url = NSURL.fileURLWithPath_(str(photo_path))
            shared = PHPhotoLibrary.sharedPhotoLibrary()
            
            # Store the placeholder asset's local identifier
            placeholder_id = None
            
            def changes():
                nonlocal placeholder_id
                request = self._create_asset_request(file_url, asset_type)
                if request is None:
                    raise Exception(f"Failed to create {asset_type} import request")
                placeholder = request.placeholderForCreatedAsset()
                if placeholder is None:
                    raise Exception("Failed to get placeholder asset")
                placeholder_id = placeholder.localIdentifier()
            
            error = None
            success = shared.performChangesAndWait_error_(changes, error)
            
            if not success:
                self.logger.error(f"Import failed for {photo_path}")
                return False
                
            # Verify the asset exists in Photos library
            if placeholder_id:
                if not self._verify_asset_exists(placeholder_id):
                    self.logger.error(f"Import appeared to succeed but asset not found in Photos library: {photo_path}")
                    return False
                    
            if DELETE_ORIGINAL:
                try:
                    photo_path.unlink()
                except Exception as e:
                    self.logger.error(f"Import succeeded but failed to delete original: {e}")
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to import {photo_path}: {e}")
            return False
