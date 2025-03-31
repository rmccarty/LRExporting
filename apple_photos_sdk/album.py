"""Manages albums in Apple Photos."""

import logging
from objc import autorelease_pool
from pathlib import Path

from Photos import (
    PHAsset,
    PHAssetCollection,
    PHAssetCollectionChangeRequest,
    PHCollectionList,
    PHCollectionListChangeRequest,
    PHCollectionListType,
    PHCollectionListSubtype,
    PHCollectionListTypeFolder,
    PHCollectionListSubtypeRegularFolder,
    PHAssetCollectionTypeAlbum,
    PHAssetCollectionSubtypeAlbumRegular,
    PHFetchOptions,
    PHPhotoLibrary,
)

from .config import PHOTOS_CHANGE_TIMEOUT, PHOTOS_CHANGE_CHECK_INTERVAL, TARGETED_ALBUM_PREFIXES

class AlbumManager:
    """Manages album operations for Apple Photos."""
    
    def __init__(self):
        """Initialize the album manager."""
        self.logger = logging.getLogger(__name__)
        
    def _is_targeted_album_keyword(self, keyword: str) -> bool:
        """Check if a keyword indicates a targeted album by matching top-level folder prefixes."""
        return any(keyword.startswith(prefix) for prefix in TARGETED_ALBUM_PREFIXES)
        
    def _wait_for_changes(self) -> bool:
        """Wait for Photos library changes to complete."""
        # No need to wait since we're using performChangesAndWait_error_
        return True
        
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
                    fetch_options = PHFetchOptions.alloc().init()
                    if current_folder:
                        # Search in current folder
                        folder_list = PHCollectionList.fetchCollectionsInCollectionList_options_(current_folder, fetch_options)
                    else:
                        # Search at root level
                        folder_list = PHCollectionList.fetchCollectionListsWithType_subtype_options_(
                            PHCollectionListTypeFolder,
                            PHCollectionListSubtypeRegularFolder,
                            fetch_options
                        )
                        
                    folder = None
                    for i in range(folder_list.count()):
                        item = folder_list.objectAtIndex_(i)
                        if item.localizedTitle() == part:
                            folder = item
                            break
                            
                    if folder:
                        current_folder = folder
                        self.logger.debug(f"Found existing folder: {path_str}")
                        continue
                        
                    # Need to create this folder
                    self.logger.info(f"Creating folder: {path_str}")
                    success = False
                    placeholder = None
                    
                    def handle_change():
                        nonlocal success, placeholder
                        try:
                            # Create folder list (folder in Apple Photos)
                            folder = PHCollectionListChangeRequest.creationRequestForCollectionListWithTitle_(part)
                            placeholder = folder.placeholderForCreatedCollectionList()
                            
                            if current_folder:
                                # Add to parent folder
                                parent_request = PHCollectionListChangeRequest.changeRequestForCollectionList_(current_folder)
                                parent_request.addChildCollections_([folder])
                            success = True
                        except Exception as e:
                            self.logger.error(f"Error creating folder {path_str}: {e}")
                            success = False
                    
                    # Perform changes in a change block
                    error = None
                    PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(handle_change, error)
                    
                    if not success or not placeholder:
                        self.logger.error(f"Failed to create folder: {path_str}")
                        return False, None
                        
                    # Get the created folder
                    folder_list = PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_([placeholder.localIdentifier()], None)
                    if folder_list.count() > 0:
                        current_folder = folder_list.firstObject()
                    else:
                        self.logger.error(f"Could not find created folder: {path_str}")
                        return False, None
                
                return True, current_folder.localIdentifier() if current_folder else None
                
        except Exception as e:
            self.logger.error(f"Error creating folder path: {e}")
            return False, None
            
    def _create_album_in_folder(self, album_name: str, folder_id: str) -> tuple[bool, str | None]:
        """Create an album in the specified folder. Returns (success, album_id) tuple."""
        try:
            with autorelease_pool():
                # Try to find existing album
                fetch_options = PHFetchOptions.alloc().init()
                album_list = PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                    PHAssetCollectionTypeAlbum,
                    PHAssetCollectionSubtypeAlbumRegular,
                    fetch_options
                )
                
                for i in range(album_list.count()):
                    album = album_list.objectAtIndex_(i)
                    if album.localizedTitle() == album_name:
                        self.logger.debug(f"Found existing album: {album_name}")
                        return True, album.localIdentifier()
                
                # Need to create the album
                self.logger.info(f"Creating album: {album_name}")
                success = False
                placeholder = None
                
                def handle_change():
                    nonlocal success, placeholder
                    try:
                        # Create album
                        album = PHAssetCollectionChangeRequest.creationRequestForAssetCollectionWithTitle_(album_name)
                        placeholder = album.placeholderForCreatedAssetCollection()
                        
                        # Add to folder
                        folder_list = PHCollectionList.fetchCollectionListsWithLocalIdentifiers_options_([folder_id], None)
                        if folder_list.count() > 0:
                            folder = folder_list.firstObject()
                            folder_request = PHCollectionListChangeRequest.changeRequestForCollectionList_(folder)
                            folder_request.addChildCollections_([placeholder])
                            success = True
                    except Exception as e:
                        self.logger.error(f"Error creating album {album_name}: {e}")
                        success = False
                
                # Perform changes in a change block
                error = None
                PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(handle_change, error)
                
                if not success or not placeholder:
                    self.logger.error(f"Failed to create album: {album_name}")
                    return False, None
                    
                # Get the created album
                album_list = PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([placeholder.localIdentifier()], None)
                if album_list.count() > 0:
                    return True, album_list.firstObject().localIdentifier()
                
                self.logger.error(f"Could not find created album: {album_name}")
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error creating album: {e}")
            return False, None
            
    def _add_to_album(self, asset_id: str, album_id: str) -> bool:
        """Add an asset to an album. Returns success boolean."""
        try:
            with autorelease_pool():
                # Get the asset
                asset = PHAsset.fetchAssetsWithLocalIdentifiers_options_([asset_id], None).firstObject()
                if not asset:
                    self.logger.error(f"Asset not found: {asset_id}")
                    return False
                    
                # Get the album
                album = PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([album_id], None).firstObject()
                if not album:
                    self.logger.error(f"Album not found: {album_id}")
                    return False
                
                success = False
                
                def handle_change():
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
                error = None
                PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(handle_change, error)
                
                return success
                
        except Exception as e:
            self.logger.error(f"Error adding to album: {e}")
            return False
            
    def add_asset_to_targeted_albums(self, asset_id: str, targeted_keywords: list[str]) -> bool:
        """
        Add an asset to albums based on targeted keywords.
        Each keyword represents a folder path and album name (e.g. '01/Bands/Album Name').
        
        Args:
            asset_id: Local identifier of the asset to add
            targeted_keywords: List of hierarchical keywords defining folder/album structure
            
        Returns:
            bool: True if all operations succeeded, False if any failed
        """
        success = True
        for keyword in targeted_keywords:
            # Split into folder path and album name
            parts = keyword.split('/')
            if len(parts) < 2:
                self.logger.error(f"Invalid targeted keyword format: {keyword}")
                success = False
                continue
                
            # Last part is album name, everything before is folder path
            album_name = parts[-1]
            folder_parts = parts[:-1]
            
            # Create folder path
            folder_success, folder_id = self._create_folder_path(folder_parts)
            if not folder_success:
                self.logger.error(f"Failed to create folder path: {'/'.join(folder_parts)}")
                success = False
                continue
                
            # Create album in the folder
            album_success, album_id = self._create_album_in_folder(album_name, folder_id)
            if not album_success:
                self.logger.error(f"Failed to create album: {album_name}")
                success = False
                continue
                
            # Add photo to album
            if not self._add_to_album(asset_id, album_id):
                self.logger.error(f"Failed to add photo to album: {album_name}")
                success = False
                
        return success

    def create_album(self, name: str) -> bool:
        """
        Create a new album in Apple Photos.
        
        Args:
            name: Name of the album to create
            
        Returns:
            bool: True if creation successful, False if failed
        """
        try:
            # TODO: Implement album creation logic
            return True
        except Exception as e:
            self.logger.error(f"Failed to create album {name}: {e}")
            return False
            
    def add_to_album(self, photo_path: Path, album_name: str) -> bool:
        """
        Add a photo to an album.
        
        Args:
            photo_path: Path to the photo
            album_name: Name of the target album
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            # Check if file exists
            if not photo_path.exists():
                self.logger.error(f"Photo does not exist: {photo_path}")
                return False
                
            # Check if album exists
            # TODO: Implement album existence check
            
            # TODO: Implement add to album logic
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add {photo_path} to album {album_name}: {e}")
            return False
