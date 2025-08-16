#!/usr/bin/env python3

import logging
import time
from pathlib import Path
from objc import autorelease_pool
import Photos

from config import SLEEP_TIME
from transfers.transfer import Transfer

# Import photokit for caption extraction
try:
    import photokit
    PHOTOKIT_AVAILABLE = True
except ImportError:
    PHOTOKIT_AVAILABLE = False

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
    
    def _extract_caption_with_photokit(self, asset):
        """Extract caption from asset using photokit library."""
        if not PHOTOKIT_AVAILABLE:
            self.logger.debug("PhotoKit not available for caption extraction")
            return None
            
        try:
            # Get asset ID and extract UUID
            asset_id = asset.localIdentifier()
            uuid = asset_id.split('/')[0]
            self.logger.debug(f"Extracting caption for asset UUID: {uuid}")
            
            # Use photokit PhotoLibrary to fetch photo by UUID
            photo_library = photokit.PhotoLibrary()
            
            # Try different methods to get photo by UUID (same as add_to_apple_photos_watcher.py)
            photo_asset = None
            methods_to_try = [
                ('fetch_uuid', lambda: photo_library.fetch_uuid(uuid)),
                ('get_photo', lambda: photo_library.get_photo(uuid)),
                ('photo', lambda: photo_library.photo(uuid)),
                ('asset', lambda: photo_library.asset(uuid)),
                ('get_asset', lambda: photo_library.get_asset(uuid)),
                ('fetch_asset', lambda: photo_library.fetch_asset(uuid)),
            ]
            
            for method_name, method_call in methods_to_try:
                if hasattr(photo_library, method_name):
                    try:
                        self.logger.debug(f"Trying PhotoKit method: {method_name}")
                        photo_asset = method_call()
                        if photo_asset:
                            self.logger.debug(f"Success with {method_name}: {photo_asset}")
                            break
                    except Exception as e:
                        self.logger.debug(f"Method {method_name} failed: {e}")
                        continue
            
            if not photo_asset:
                self.logger.debug(f"PhotoKit could not find asset for UUID: {uuid} - tried all available methods")
                return None
            
            self.logger.debug(f"PhotoKit found asset: {photo_asset}")
            
            # Try different caption attributes in order of preference
            caption = None
            if hasattr(photo_asset, 'description') and photo_asset.description:
                caption = photo_asset.description.strip()
                self.logger.debug(f"Found caption in description: '{caption}'")
            elif hasattr(photo_asset, 'caption') and photo_asset.caption:
                caption = photo_asset.caption.strip()
                self.logger.debug(f"Found caption in caption field: '{caption}'")
            elif hasattr(photo_asset, 'comment') and photo_asset.comment:
                caption = photo_asset.comment.strip()
                self.logger.debug(f"Found caption in comment: '{caption}'")
            else:
                self.logger.debug("No caption found in any field (description, caption, comment)")
            
            return caption
            
        except Exception as e:
            self.logger.debug(f"PhotoKit caption extraction error: {e}")
            return None
    
    def _initialize_watching_album(self):
        """Initialize the watching album, creating it if it doesn't exist."""
        print(f"🔍 DEBUG: Initializing '{self.album_name}' album...")
        
        try:
            # First try to find existing album
            print(f"🔍 DEBUG: Looking for existing '{self.album_name}' album...")
            album_id = self._find_album_by_name(self.album_name)
            print(f"🔍 DEBUG: Find album result: {album_id}")
            
            if album_id:
                print(f"✅ DEBUG: Found existing '{self.album_name}' album with ID: {album_id}")
                self.logger.info(f"Found existing '{self.album_name}' album")
                self.watching_album_id = album_id
                return
            
            # Create the album if it doesn't exist
            print(f"🔍 DEBUG: Album not found, creating '{self.album_name}' album at top level...")
            self.logger.info(f"Creating '{self.album_name}' album at top level...")
            success, album_id = self._create_top_level_album(self.album_name)
            print(f"🔍 DEBUG: Create album result: success={success}, album_id={album_id}")
            
            if success:
                print(f"✅ DEBUG: Created '{self.album_name}' album successfully with ID: {album_id}")
                self.logger.info(f"Created '{self.album_name}' album successfully")
                self.watching_album_id = album_id
            else:
                print(f"❌ DEBUG: Failed to create '{self.album_name}' album")
                self.logger.error(f"Failed to create '{self.album_name}' album")
                self.watching_album_id = None
                
        except Exception as e:
            print(f"❌ DEBUG: Error initializing watching album: {e}")
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
        print(f"   🔍 DEBUG: Getting assets from album...")
        print(f"   🔍 DEBUG: watching_album_id = {self.watching_album_id}")
        
        if not self.watching_album_id:
            print(f"   ❌ DEBUG: No watching_album_id available")
            return []
            
        try:
            with autorelease_pool():
                # Get the album
                print(f"   🔍 DEBUG: Fetching album collection with ID: {self.watching_album_id}")
                album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_(
                    [self.watching_album_id], None
                )
                
                print(f"   🔍 DEBUG: Album fetch result count: {album_result.count()}")
                
                if album_result.count() == 0:
                    print(f"   ❌ DEBUG: Album not found with ID: {self.watching_album_id}")
                    self.logger.warning(f"'{self.album_name}' album not found")
                    return []
                
                album = album_result.objectAtIndex_(0)
                print(f"   ✅ DEBUG: Found album: {album}")
                print(f"   🔍 DEBUG: Album title: {album.localizedTitle()}")
                
                # Get assets in the album
                print(f"   🔍 DEBUG: Fetching assets in album...")
                assets = Photos.PHAsset.fetchAssetsInAssetCollection_options_(album, None)
                print(f"   📊 DEBUG: Assets fetch result count: {assets.count()}")
                
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
        print(f"\n🔍 APPLE PHOTO WATCHER - Checking '{self.album_name}' album...")
        
        if not self.watching_album_id:
            print(f"❌ No '{self.album_name}' album available")
            self.logger.debug("No watching album available")
            return
            
        try:
            print(f"📂 Getting assets from '{self.album_name}' album...")
            assets = self._get_assets_in_album()
            
            if not assets:
                print(f"✅ No assets found in '{self.album_name}' album - nothing to process")
                self.logger.debug(f"No assets found in '{self.album_name}' album")
                return
            
            print(f"📊 Found {len(assets)} asset(s) in '{self.album_name}' album")
            
            for i, asset_data in enumerate(assets, 1):
                print(f"\n📸 Processing asset {i}/{len(assets)}: {asset_data['filename']}")
                print(f"   Type: {asset_data['media_type']}")
                self.logger.info(f"Found {asset_data['media_type']}: {asset_data['filename']}")
                
                # Get the actual PHAsset object
                asset_obj = asset_data['asset_obj']
                title = asset_data['title']
                
                # Extract caption using photokit
                print(f"   🔍 Extracting caption using photokit...")
                self.logger.debug(f"Starting caption extraction for {asset_data['filename']}")
                caption = self._extract_caption_with_photokit(asset_obj)
                self.logger.debug(f"Caption extraction completed. Result: {repr(caption)}")
                
                # Log title and caption if they exist
                if title:
                    print(f"   📝 Title: '{title}'")
                    self.logger.info(f"  Title: {title}")
                else:
                    print(f"   📝 Title: None")
                    self.logger.info(f"  Title: None")
                    
                if caption:
                    print(f"   💬 Caption: '{caption}'")
                    self.logger.info(f"  Caption: {caption}")
                else:
                    print(f"   💬 Caption: None")
                    self.logger.info(f"  Caption: None")
                
                # Check for category format in title and caption
                has_title_category = title and ':' in title
                has_caption_category = caption and ':' in caption
                
                print(f"   🎯 Category Detection:")
                print(f"      - Title has colon (:): {has_title_category}")
                print(f"      - Caption has colon (:): {has_caption_category}")
                self.logger.debug(f"Category detection - Title has colon: {has_title_category}, Caption has colon: {has_caption_category}")
                
                # If either title or caption has category format, let Transfer handle album placement
                if has_title_category or has_caption_category:
                    print(f"   ✅ CATEGORY DETECTED - Processing asset:")
                    if has_title_category:
                        print(f"      📝 Category in TITLE: '{title}'")
                        self.logger.info(f"  Category detected in TITLE: '{title}'")
                    if has_caption_category:
                        print(f"      💬 Category in CAPTION: '{caption}'")
                        self.logger.info(f"  Category detected in CAPTION: '{caption}'")
                    
                    # Process BOTH title and caption categories by calling transfer_asset for each
                    print(f"   🔄 Processing categories for dual album placement...")
                    
                    success_count = 0
                    total_attempts = 0
                    
                    # Process title category if present
                    if has_title_category:
                        total_attempts += 1
                        category_parts = title.split(':', 1)
                        category = category_parts[0].strip()
                        title_album = f"02/{category}/{title}"
                        print(f"   🎯 Processing title album: '{title_album}'")
                        
                        try:
                            # Use asset's original title (no custom title needed)
                            success_title = self.transfer.transfer_asset(asset_obj)
                            if success_title:
                                success_count += 1
                                print(f"   ✅ SUCCESS - Added to title-based album: '{title_album}'")
                            else:
                                print(f"   ❌ FAILED - Could not add to title-based album: '{title_album}'")
                        except Exception as e:
                            print(f"   ❌ ERROR - Title album processing failed: {e}")
                    
                    # Process caption category if present
                    if has_caption_category:
                        total_attempts += 1
                        category_parts = caption.split(':', 1)
                        category = category_parts[0].strip()
                        caption_album = f"02/{category}/{caption}"
                        print(f"   🎯 Processing caption album: '{caption_album}'")
                        
                        try:
                            # Use caption as custom title for Transfer processing
                            success_caption = self.transfer.transfer_asset(asset_obj, custom_title=caption)
                            if success_caption:
                                success_count += 1
                                print(f"   ✅ SUCCESS - Added to caption-based album: '{caption_album}'")
                            else:
                                print(f"   ❌ FAILED - Could not add to caption-based album: '{caption_album}'")
                        except Exception as e:
                            print(f"   ❌ ERROR - Caption album processing failed: {e}")
                    
                    # Overall success if at least one album placement succeeded
                    success = success_count > 0
                    print(f"   📊 Album placement summary: {success_count}/{total_attempts} successful")
                else:
                    # No category format detected - skip processing
                    print(f"   ❌ NO CATEGORY DETECTED - Skipping asset (no colon in title or caption)")
                    self.logger.info(f"  No category format detected (no colon in title or caption) - skipping")
                    # Remove from Watching album since it doesn't have category format
                    print(f"   🗑️  Removing from '{self.album_name}' album...")
                    if self._remove_asset_from_album(asset_data['id']):
                        print(f"   ✅ Removed '{asset_data['filename']}' from '{self.album_name}' album")
                        self.logger.info(f"Removed {asset_data['filename']} from '{self.album_name}' album (no category)")
                    else:
                        print(f"   ❌ Failed to remove '{asset_data['filename']}' from '{self.album_name}' album")
                    continue
                
                if success:
                    print(f"   ✅ SUCCESS - Transfer system processed asset successfully")
                    self.logger.info(f"Successfully processed {asset_data['filename']}")
                    # Remove asset from album after successful processing
                    print(f"   🗑️  Removing processed asset from '{self.album_name}' album...")
                    if self._remove_asset_from_album(asset_data['id']):
                        print(f"   ✅ Removed '{asset_data['filename']}' from '{self.album_name}' album")
                        self.logger.info(f"Removed {asset_data['filename']} from '{self.album_name}' album")
                    else:
                        print(f"   ❌ Failed to remove '{asset_data['filename']}' from '{self.album_name}' album")
                        self.logger.error(f"Failed to remove {asset_data['filename']} from album")
                else:
                    print(f"   ❌ FAILED - Transfer system could not process asset")
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
