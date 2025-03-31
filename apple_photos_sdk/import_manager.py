"""Handles importing photos into Apple Photos."""

import logging
import os
import time
from pathlib import Path
from objc import autorelease_pool

from Photos import (
    PHAssetChangeRequest,
    PHAssetCreationRequest,
    PHPhotoLibrary,
    PHAsset,
    PHAssetMediaType,
    PHFetchOptions,
    PHAssetResource,
    PHAssetResourceType,
    PHContentEditingInputRequestOptions,
    PHImageRequestOptions,
    PHImageRequestOptionsVersion,
    PHImageRequestOptionsDeliveryMode,
    PHImageManager,
    PHAssetResourceRequestOptions,
    PHAssetResourceManager,
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
            
    def _get_asset_keywords(self, local_id: str) -> list[str]:
        """Get keywords from an asset."""
        try:
            with autorelease_pool():
                # Fetch the asset
                result = PHAsset.fetchAssetsWithLocalIdentifiers_options_([local_id], None)
                if result.count() == 0:
                    return []
                
                asset = result.firstObject()
                
                # Try to get keywords through PHAssetResource
                resources = PHAssetResource.assetResourcesForAsset_(asset)
                if resources and resources.count() > 0:
                    for idx in range(resources.count()):
                        resource = resources.objectAtIndex_(idx)
                        logging.debug(f"Found resource type: {resource.type()}")
                        
                        # Try to get metadata through resource
                        try:
                            # Try to get metadata directly from the resource
                            metadata = resource.value()
                            if metadata:
                                logging.debug(f"Got metadata from resource: {metadata}")
                                if hasattr(metadata, 'keywords'):
                                    keywords = metadata.keywords
                                    logging.debug(f"Found keywords in metadata: {keywords}")
                                    return list(keywords)
                        except Exception as e:
                            logging.debug(f"Error getting metadata from resource: {e}")
                            
                            # Try alternate method
                            try:
                                info = resource.valueForKey_("info")
                                if info:
                                    logging.debug(f"Got info from resource: {info}")
                                    if hasattr(info, 'keywords'):
                                        keywords = info.keywords
                                        logging.debug(f"Found keywords in info: {keywords}")
                                        return list(keywords)
                            except Exception as e:
                                logging.debug(f"Error getting info from resource: {e}")
                
                return []
                
        except Exception as e:
            logging.error(f"Error getting keywords for asset {local_id}: {str(e)}")
            return []
            
    def _handle_image_data(self, imageData, dataUTI, orientation, info):
        """Handle image data result."""
        try:
            if imageData and info:
                metadata = info.get('metadata')
                if metadata and hasattr(metadata, 'keywords'):
                    return list(metadata.keywords)
        except Exception as e:
            self.logger.error(f"Error getting keywords from image data: {e}")
        return []
            
    def _get_original_keywords(self, photo_path: Path) -> list[str]:
        """Get keywords from original photo before import."""
        try:
            # Run exiftool to get keywords
            import subprocess
            cmd = ["exiftool", "-Keywords", "-s3", str(photo_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                keywords = result.stdout.strip().split(", ")
                logging.debug(f"Found original keywords: {keywords}")
                return keywords
            return []
        except Exception as e:
            logging.error(f"Error getting original keywords: {e}")
            return []

    def import_photo(self, photo_path: Path) -> tuple[bool, str | None]:
        """
        Import a photo or video into Apple Photos.
        
        Args:
            photo_path: Path to the photo or video to import
            
        Returns:
            tuple[bool, str | None]: (success, asset_id) where success is True if import succeeded,
                                   and asset_id is the local identifier of the imported asset
        """
        try:
            if not photo_path.exists():
                self.logger.error(f"File does not exist: {photo_path}")
                return False, None

            # Get original keywords before import
            original_keywords = self._get_original_keywords(photo_path)
            if original_keywords:
                self.logger.info(f"Original keywords for {photo_path}: {original_keywords}")

            # Identify asset type
            try:
                asset_type = self._get_asset_type(photo_path)
                self.logger.info(f"Importing {asset_type}: {photo_path}")
            except ValueError as e:
                self.logger.error(str(e))
                return False, None
                
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
                return False, None
                
            # Verify the asset exists in Photos library
            if placeholder_id:
                if not self._verify_asset_exists(placeholder_id):
                    self.logger.error(f"Import appeared to succeed but asset not found in Photos library: {photo_path}")
                    return False, None
                    
                # Get and print keywords
                keywords = self._get_asset_keywords(placeholder_id)
                if keywords:
                    self.logger.info(f"Keywords for {photo_path}: {', '.join(keywords)}")
                else:
                    self.logger.info(f"No keywords found for {photo_path}")
                    
            if DELETE_ORIGINAL:
                try:
                    photo_path.unlink()
                except Exception as e:
                    self.logger.error(f"Import succeeded but failed to delete original: {e}")
                    
            return True, placeholder_id
            
        except Exception as e:
            self.logger.error(f"Failed to import {photo_path}: {e}")
            return False, None
