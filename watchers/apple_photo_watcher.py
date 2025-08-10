#!/usr/bin/env python3

import logging
import time
from pathlib import Path
from objc import autorelease_pool
import Photos

from config import SLEEP_TIME
from transfers.transfer import Transfer

class ApplePhotoWatcher:
    """
    A class to watch the Apple Photos 'Watching' album for photos and videos.
    """
    
    def __init__(self, album_name: str = "Watching"):
        """Initialize the Apple Photos album watcher."""
        self.album_name = album_name
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.watching_album_id = None
        self.transfer = Transfer()  # Add transfer instance for album placement logic
        
        # Initialize the watching album
        self._initialize_watching_album()
    
    def _initialize_watching_album(self):
        """Initialize the watching album, creating it if it doesn't exist."""
        try:
            # First try to find existing album
            album_id = self._find_album_by_name(self.album_name)
            if album_id:
                self.logger.info(f"Found existing '{self.album_name}' album")
                self.watching_album_id = album_id
                return
            
            # Create the album if it doesn't exist
            self.logger.info(f"Creating '{self.album_name}' album at top level...")
            success, album_id = self._create_top_level_album(self.album_name)
            if success:
                self.logger.info(f"Created '{self.album_name}' album successfully")
                self.watching_album_id = album_id
            else:
                self.logger.error(f"Failed to create '{self.album_name}' album")
                self.watching_album_id = None
                
        except Exception as e:
            self.logger.error(f"Error initializing watching album: {e}")
            self.watching_album_id = None
    
    def _find_album_by_name(self, album_name: str) -> str | None:
        """Find an album by name at the top level. Returns album ID if found."""
        try:
            with autorelease_pool():
                fetch_options = Photos.PHFetchOptions.alloc().init()
                fetch_options.setPredicate_(
                    Photos.NSPredicate.predicateWithFormat_("title == %@", album_name)
                )
                
                # Fetch top-level albums (not in folders)
                albums = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                    Photos.PHAssetCollectionTypeAlbum,
                    Photos.PHAssetCollectionSubtypeAny,
                    fetch_options
                )
                
                if albums.count() > 0:
                    album = albums.objectAtIndex_(0)
                    return album.localIdentifier()
                    
                return None
                
        except Exception as e:
            self.logger.error(f"Error finding album '{album_name}': {e}")
            return None
    
    def _create_top_level_album(self, album_name: str) -> tuple[bool, str | None]:
        """Create a top-level album. Returns (success, album_id)."""
        try:
            with autorelease_pool():
                success = False
                album_id = None
                
                def create_album():
                    nonlocal success, album_id
                    # Create a new top-level album
                    album_request = Photos.PHAssetCollectionChangeRequest.creationRequestForAssetCollectionWithTitle_(album_name)
                    placeholder = album_request.placeholderForCreatedAssetCollection()
                    success = True
                    album_id = placeholder.localIdentifier()
                
                # Perform changes
                result, error = Photos.PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(
                    create_album,
                    None
                )
                
                if not result or not success:
                    self.logger.error(f"Failed to create album '{album_name}'")
                    if error:
                        self.logger.error(f"Error: {error}")
                    return False, None
                
                return True, album_id
                
        except Exception as e:
            self.logger.error(f"Error creating album '{album_name}': {e}")
            return False, None
    
    def _get_assets_in_album(self) -> list:
        """Get all assets in the watching album."""
        if not self.watching_album_id:
            return []
            
        try:
            with autorelease_pool():
                # Get the album
                album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_(
                    [self.watching_album_id], None
                )
                
                if album_result.count() == 0:
                    self.logger.warning(f"'{self.album_name}' album not found")
                    return []
                
                album = album_result.objectAtIndex_(0)
                
                # Get assets in the album
                assets = Photos.PHAsset.fetchAssetsInAssetCollection_options_(album, None)
                
                # Convert to list of asset info
                asset_list = []
                for i in range(assets.count()):
                    asset = assets.objectAtIndex_(i)
                    
                    # Get the title from the asset's metadata
                    title = None
                    try:
                        # Try to get the title/caption from the asset
                        title = asset.valueForKey_('title')
                        if not title:
                            # Try alternative methods to get title
                            title = asset.valueForKey_('localizedTitle')
                    except:
                        title = None
                    
                    asset_info = {
                        'id': asset.localIdentifier(),
                        'filename': asset.valueForKey_('filename') or f"Asset_{i}",
                        'title': title,
                        'media_type': 'photo' if asset.mediaType() == Photos.PHAssetMediaTypeImage else 'video',
                        'asset_obj': asset  # Include the actual PHAsset object for Transfer
                    }
                    asset_list.append(asset_info)
                
                return asset_list
                
        except Exception as e:
            self.logger.error(f"Error getting assets from album: {e}")
            return []
    
    def _remove_asset_from_album(self, asset_id: str) -> bool:
        """Remove an asset from the watching album."""
        if not self.watching_album_id:
            return False
            
        try:
            with autorelease_pool():
                success = False
                
                def remove_asset():
                    nonlocal success
                    # Get the album and asset
                    album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_(
                        [self.watching_album_id], None
                    )
                    asset_result = Photos.PHAsset.fetchAssetsWithLocalIdentifiers_options_(
                        [asset_id], None
                    )
                    
                    if album_result.count() > 0 and asset_result.count() > 0:
                        album = album_result.objectAtIndex_(0)
                        asset = asset_result.objectAtIndex_(0)
                        
                        # Remove asset from album
                        album_change = Photos.PHAssetCollectionChangeRequest.changeRequestForAssetCollection_(album)
                        if album_change:
                            album_change.removeAssets_([asset])
                            success = True
                
                # Perform changes
                result, error = Photos.PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(
                    remove_asset,
                    None
                )
                
                if not result or not success:
                    self.logger.error(f"Failed to remove asset {asset_id}")
                    if error:
                        self.logger.error(f"Error: {error}")
                    return False
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error removing asset {asset_id}: {e}")
            return False
    
    def check_album(self):
        """Check the watching album for new assets."""
        if not self.watching_album_id:
            self.logger.debug("No watching album available")
            return
            
        try:
            assets = self._get_assets_in_album()
            
            if not assets:
                self.logger.debug(f"No assets found in '{self.album_name}' album")
                return
            
            for asset_data in assets:
                self.logger.info(f"Found {asset_data['media_type']}: {asset_data['filename']}")
                
                # Log title on separate line if it exists
                if asset_data['title']:
                    self.logger.info(f"  Title: {asset_data['title']}")
                
                # Follow established pattern - let Transfer handle all album placement logic
                asset_obj = asset_data['asset_obj']  # Get the actual PHAsset object
                success = self.transfer.transfer_asset(asset_obj)
                
                if success:
                    self.logger.info(f"Successfully processed {asset_data['filename']}")
                    # Remove asset from album after successful processing
                    if self._remove_asset_from_album(asset_data['id']):
                        self.logger.info(f"Removed {asset_data['filename']} from '{self.album_name}' album")
                    else:
                        self.logger.error(f"Failed to remove {asset_data['filename']} from album")
                else:
                    self.logger.error(f"Failed to process {asset_data['filename']}")
                    
        except Exception as e:
            self.logger.error(f"Error checking album: {e}")

if __name__ == '__main__':
    # For standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    watcher = ApplePhotoWatcher()
    watcher.running = True
    
    try:
        while watcher.running:
            watcher.check_album()
            time.sleep(watcher.sleep_time)
    except KeyboardInterrupt:
        logging.info("Stopping Apple Photos watcher...")
        watcher.running = False
