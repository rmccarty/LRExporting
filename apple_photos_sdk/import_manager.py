"""Manages photo import operations for Apple Photos."""

import logging
import os
import time
from pathlib import Path
import subprocess
from objc import autorelease_pool

from Photos import (
    PHAsset,
    PHAssetChangeRequest,
    PHAssetCreationRequest,
    PHAssetResourceCreationOptions,
    PHAssetResourceType,
    PHImageManager,
    PHAssetResourceRequestOptions,
    PHAssetResourceManager,
    PHCollectionList,
    PHAssetCollection,
    PHCollectionListChangeRequest,
    PHAssetCollectionChangeRequest,
    PHAssetMediaType,
    PHFetchOptions,
    PHAssetResource,
    PHContentEditingInputRequestOptions,
    PHImageRequestOptions,
    PHImageRequestOptionsVersion,
    PHImageRequestOptionsDeliveryMode,
    PHPhotoLibrary,
)
from Foundation import (
    NSURL,
    NSError,
    NSData,
    NSString,
)
from .config import (
    DELETE_ORIGINAL,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    TARGETED_ALBUM_PREFIXES,
)
from .album import AlbumManager

class ImportManager:
    """Manages photo import operations for Apple Photos."""
    
    def __init__(self):
        """Initialize the import manager."""
        self.logger = logging.getLogger(__name__)
        self.album_manager = AlbumManager()
        
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
        # This method is deprecated as we now get keywords from original file
        return []
            
    def _handle_image_data(self, imageData, dataUTI, orientation, info):
        """Handle image data result."""
        # This method is deprecated as we now get keywords from original file
        return []
            
    def _is_targeted_keyword(self, keyword: str) -> bool:
        """Check if a keyword indicates a targeted album."""
        # Strip "Subject: " prefix if present
        if keyword.startswith("Subject: "):
            keyword = keyword[9:]
        return any(keyword.startswith(prefix) for prefix in TARGETED_ALBUM_PREFIXES)

    def _get_original_keywords(self, photo_path: Path) -> list[str]:
        """Get keywords from original photo before import."""
        try:
            # Run exiftool to get XMP Subject which contains our hierarchical keywords
            import subprocess
            cmd = ["exiftool", "-XMP:Subject", "-s", "-s", "-sep", "||", str(photo_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                # Split on our custom separator and strip any whitespace
                keywords = [k.strip() for k in result.stdout.strip().split("||")]
                self.logger.debug(f"Found original keywords: {keywords}")
                
                # Check for targeted album keywords
                targeted_keywords = [k for k in keywords if self._is_targeted_keyword(k)]
                if targeted_keywords:
                    self.logger.info(f"Found targeted album keywords: {targeted_keywords}")
                
                return keywords
            return []
        except Exception as e:
            self.logger.error(f"Error getting original keywords: {e}")
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

            # Get targeted album keywords
            targeted_keywords = [k for k in original_keywords if self._is_targeted_keyword(k)]

            # Identify asset type
            try:
                asset_type = self._get_asset_type(photo_path)
            except Exception as e:
                self.logger.error(f"Failed to identify asset type: {e}")
                return False, None

            # Import the photo/video
            self.logger.info(f"Importing photo: {photo_path}")
            success = False
            placeholder = None

            def handle_import():
                nonlocal success, placeholder
                try:
                    # Create asset request
                    url = NSURL.fileURLWithPath_(str(photo_path))
                    creation_request = self._create_asset_request(url, asset_type)
                    if creation_request:
                        # Get the placeholder for the created asset
                        placeholder = creation_request.placeholderForCreatedAsset()
                        success = True
                except Exception as e:
                    self.logger.error(f"Error in creation request: {e}")
                    success = False

            # Perform import in a change block
            error = None
            PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(handle_import, error)

            if not success or not placeholder:
                return False, None

            # Get the imported asset's ID
            asset_id = placeholder.localIdentifier()
            self.logger.debug(f"Asset verified in Photos library: {asset_id}")

            # Add to targeted albums based on keywords
            if targeted_keywords:
                self.logger.info(f"Adding asset to targeted albums: {targeted_keywords}")
                if not self.album_manager.add_asset_to_targeted_albums(asset_id, targeted_keywords):
                    self.logger.error("Failed to add asset to one or more targeted albums")

            # Delete original if configured
            if DELETE_ORIGINAL:
                try:
                    photo_path.unlink()
                    self.logger.debug(f"Deleted original file: {photo_path}")
                except Exception as e:
                    self.logger.error(f"Failed to delete original file: {e}")

            return True, asset_id

        except Exception as e:
            self.logger.error(f"Failed to import {photo_path}: {e}")
            return False, None

    def _create_folder_path(self, path_parts: list[str]) -> tuple[bool, str | None]:
        """Create a folder path in Apple Photos, creating parent folders as needed.
        Returns (success, folder_id) tuple."""
        try:
            with autorelease_pool():
                current_folder = None
                current_path = []
                
                for part in path_parts:
                    current_path.append(part)
                    path_str = "/".join(current_path)
                    
                    # Try to find existing folder at this level
                    folder_list = PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_([path_str], None)
                    if folder_list.count() > 0:
                        current_folder = folder_list.firstObject()
                        self.logger.debug(f"Found existing folder: {path_str}")
                        continue
                        
                    # Need to create this folder
                    self.logger.info(f"Creating folder: {path_str}")
                    success = False
                    
                    def handle_change(changeInstance):
                        nonlocal success
                        try:
                            # Create folder list (folder in Apple Photos)
                            folder = PHCollectionList.creationRequestForCollectionListWithTitle_(part)
                            if current_folder:
                                # Add to parent folder
                                parent_request = PHCollectionListChangeRequest.changeRequestForCollectionList_(current_folder)
                                parent_request.addChildCollections_([folder])
                            success = True
                        except Exception as e:
                            self.logger.error(f"Error creating folder {path_str}: {e}")
                            success = False
                    
                    # Perform changes in a change block
                    PHPhotoLibrary.sharedPhotoLibrary().performChanges_completionHandler_(
                        handle_change,
                        None
                    )
                    
                    if not success:
                        return False, None
                        
                    # Get the created folder
                    folder_list = PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_([path_str], None)
                    if folder_list.count() > 0:
                        current_folder = folder_list.firstObject()
                    else:
                        return False, None
                
                return True, current_folder.localIdentifier if current_folder else None
                
        except Exception as e:
            self.logger.error(f"Error creating folder path: {e}")
            return False, None
            
    def _create_album_in_folder(self, album_name: str, folder_id: str) -> tuple[bool, str | None]:
        """Create an album in the specified folder. Returns (success, album_id) tuple."""
        try:
            with autorelease_pool():
                # Try to find existing album
                album_list = PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([album_name], None)
                if album_list.count() > 0:
                    album = album_list.firstObject()
                    self.logger.debug(f"Found existing album: {album_name}")
                    return True, album.localIdentifier
                
                # Need to create the album
                self.logger.info(f"Creating album: {album_name}")
                success = False
                
                def handle_change(changeInstance):
                    nonlocal success
                    try:
                        # Create album
                        album = PHAssetCollectionChangeRequest.creationRequestForAssetCollectionWithTitle_(album_name)
                        
                        # Add to folder
                        folder_list = PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_([folder_id], None)
                        if folder_list.count() > 0:
                            folder = folder_list.firstObject()
                            folder_request = PHCollectionListChangeRequest.changeRequestForCollectionList_(folder)
                            folder_request.addChildCollections_([album])
                            success = True
                    except Exception as e:
                        self.logger.error(f"Error creating album {album_name}: {e}")
                        success = False
                
                # Perform changes in a change block
                PHPhotoLibrary.sharedPhotoLibrary().performChanges_completionHandler_(
                    handle_change,
                    None
                )
                
                if not success:
                    return False, None
                    
                # Get the created album
                album_list = PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([album_name], None)
                if album_list.count() > 0:
                    album = album_list.firstObject()
                    return True, album.localIdentifier
                
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error creating album: {e}")
            return False, None
            
    def _add_to_album(self, asset_id: str, album_id: str) -> bool:
        """Add an asset to an album. Returns success boolean."""
        try:
            with autorelease_pool():
                # Get the asset and album
                asset_list = PHAsset.fetchAssetsWithLocalIdentifiers_options_([asset_id], None)
                album_list = PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([album_id], None)
                
                if asset_list.count() == 0 or album_list.count() == 0:
                    return False
                    
                asset = asset_list.firstObject()
                album = album_list.firstObject()
                
                success = False
                
                def handle_change(changeInstance):
                    nonlocal success
                    try:
                        # Add asset to album
                        album_request = PHAssetCollectionChangeRequest.changeRequestForAssetCollection_(album)
                        album_request.addAssets_([asset])
                        success = True
                    except Exception as e:
                        self.logger.error(f"Error adding asset to album: {e}")
                        success = False
                
                # Perform changes in a change block
                PHPhotoLibrary.sharedPhotoLibrary().performChanges_completionHandler_(
                    handle_change,
                    None
                )
                
                return success
                
        except Exception as e:
            self.logger.error(f"Error adding to album: {e}")
            return False
