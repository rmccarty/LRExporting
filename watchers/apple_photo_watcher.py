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
            uuid = self._extract_asset_uuid(asset)
            photo_asset = self._fetch_photokit_asset(uuid)
            
            if not photo_asset:
                return None
                
            return self._extract_caption_from_photo_asset(photo_asset)
            
        except Exception as e:
            self.logger.debug(f"PhotoKit caption extraction error: {e}")
            return None

    def _extract_asset_uuid(self, asset):
        """Extract UUID from PHAsset."""
        asset_id = asset.localIdentifier()
        uuid = asset_id.split('/')[0]
        self.logger.debug(f"Extracting caption for asset UUID: {uuid}")
        return uuid

    def _fetch_photokit_asset(self, uuid):
        """Fetch photo asset from photokit using multiple fallback methods."""
        photo_library = photokit.PhotoLibrary()
        
        methods_to_try = [
            ('fetch_uuid', lambda: photo_library.fetch_uuid(uuid)),
            ('get_photo', lambda: photo_library.get_photo(uuid)),
            ('photo', lambda: photo_library.photo(uuid)),
            ('asset', lambda: photo_library.asset(uuid)),
            ('get_asset', lambda: photo_library.get_asset(uuid)),
            ('fetch_asset', lambda: photo_library.fetch_asset(uuid)),
        ]
        
        for method_name, method_call in methods_to_try:
            photo_asset = self._try_photokit_method(method_name, method_call, photo_library)
            if photo_asset:
                self.logger.debug(f"PhotoKit found asset: {photo_asset}")
                return photo_asset
        
        self.logger.debug(f"PhotoKit could not find asset for UUID: {uuid} - tried all available methods")
        return None

    def _try_photokit_method(self, method_name, method_call, photo_library):
        """Try a single photokit method and return result or None if failed."""
        if not hasattr(photo_library, method_name):
            return None
            
        try:
            self.logger.debug(f"Trying PhotoKit method: {method_name}")
            photo_asset = method_call()
            if photo_asset:
                self.logger.debug(f"Success with {method_name}: {photo_asset}")
                return photo_asset
        except Exception as e:
            self.logger.debug(f"Method {method_name} failed: {e}")
        
        return None

    def _extract_caption_from_photo_asset(self, photo_asset):
        """Extract caption from photo asset by checking multiple fields."""
        caption_fields = [
            ('description', 'description'),
            ('caption', 'caption field'),
            ('comment', 'comment')
        ]
        
        for field_name, display_name in caption_fields:
            caption = self._get_caption_from_field(photo_asset, field_name, display_name)
            if caption:
                return caption
        
        self.logger.debug("No caption found in any field (description, caption, comment)")
        return None

    def _get_caption_from_field(self, photo_asset, field_name, display_name):
        """Get caption from a specific field if it exists and has content."""
        if hasattr(photo_asset, field_name):
            field_value = getattr(photo_asset, field_name)
            if field_value:
                caption = field_value.strip()
                if caption:  # Only return non-empty captions
                    self.logger.debug(f"Found caption in {display_name}: '{caption}'")
                    return caption
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
                album = self._fetch_album_collection()
                if not album:
                    return []
                
                assets = self._fetch_assets_from_album(album)
                return self._convert_assets_to_list(assets)
                
        except Exception as e:
            self.logger.error(f"Error getting assets from album: {e}")
            return []

    def _fetch_album_collection(self):
        """Fetch the album collection by ID."""
        print(f"   🔍 DEBUG: Fetching album collection with ID: {self.watching_album_id}")
        album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_(
            [self.watching_album_id], None
        )
        
        print(f"   🔍 DEBUG: Album fetch result count: {album_result.count()}")
        
        if album_result.count() == 0:
            print(f"   ❌ DEBUG: Album not found with ID: {self.watching_album_id}")
            self.logger.warning(f"'{self.album_name}' album not found")
            return None
        
        album = album_result.objectAtIndex_(0)
        print(f"   ✅ DEBUG: Found album: {album}")
        print(f"   🔍 DEBUG: Album title: {album.localizedTitle()}")
        return album

    def _fetch_assets_from_album(self, album):
        """Fetch assets from the album collection."""
        print(f"   🔍 DEBUG: Fetching assets in album...")
        assets = Photos.PHAsset.fetchAssetsInAssetCollection_options_(album, None)
        print(f"   📊 DEBUG: Assets fetch result count: {assets.count()}")
        return assets

    def _convert_assets_to_list(self, assets):
        """Convert PHAsset collection to list of asset info dictionaries."""
        asset_list = []
        for i in range(assets.count()):
            asset = assets.objectAtIndex_(i)
            asset_info = self._create_asset_info(asset, i)
            asset_list.append(asset_info)
        return asset_list

    def _create_asset_info(self, asset, index):
        """Create asset info dictionary from PHAsset."""
        title = self._extract_asset_title(asset)
        
        return {
            'id': asset.localIdentifier(),
            'filename': asset.valueForKey_('filename') or f"Asset_{index}",
            'title': title,
            'media_type': 'photo' if asset.mediaType() == Photos.PHAssetMediaTypeImage else 'video',
            'asset_obj': asset  # Include the actual PHAsset object for Transfer
        }

    def _extract_asset_title(self, asset):
        """Extract title from asset with fallback methods."""
        try:
            title = asset.valueForKey_('title')
            if not title:
                title = asset.valueForKey_('localizedTitle')
            return title
        except:
            return None
    
    def _remove_asset_from_album(self, asset_id: str) -> bool:
        """Remove an asset from the watching album."""
        if not self.watching_album_id:
            return False
            
        try:
            with autorelease_pool():
                album, asset = self._fetch_album_and_asset_for_removal(asset_id)
                if not album or not asset:
                    return False
                
                return self._perform_asset_removal(album, asset, asset_id)
                
        except Exception as e:
            self.logger.error(f"Error removing asset {asset_id}: {e}")
            return False

    def _fetch_album_and_asset_for_removal(self, asset_id):
        """Fetch album and asset objects for removal operation."""
        album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_(
            [self.watching_album_id], None
        )
        asset_result = Photos.PHAsset.fetchAssetsWithLocalIdentifiers_options_(
            [asset_id], None
        )
        
        album = album_result.objectAtIndex_(0) if album_result.count() > 0 else None
        asset = asset_result.objectAtIndex_(0) if asset_result.count() > 0 else None
        
        return album, asset

    def _perform_asset_removal(self, album, asset, asset_id):
        """Perform the actual asset removal operation."""
        success = False
        
        def remove_asset():
            nonlocal success
            album_change = Photos.PHAssetCollectionChangeRequest.changeRequestForAssetCollection_(album)
            if album_change:
                album_change.removeAssets_([asset])
                success = True
        
        result, error = Photos.PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(
            remove_asset, None
        )
        
        if not result or not success:
            self.logger.error(f"Failed to remove asset {asset_id}")
            if error:
                self.logger.error(f"Error: {error}")
            return False
        
        return True
    
    def check_album(self):
        """Check the watching album for new assets."""
        print(f"\n🔍 APPLE PHOTO WATCHER - Checking '{self.album_name}' album...")
        
        if not self.watching_album_id:
            print(f"❌ No '{self.album_name}' album available")
            self.logger.debug("No watching album available")
            return
            
        try:
            assets = self._get_assets_for_processing()
            if not assets:
                return
                
            print(f"📊 Found {len(assets)} asset(s) in '{self.album_name}' album")
            
            for i, asset_data in enumerate(assets, 1):
                self._process_single_asset(asset_data, i, len(assets))
                    
        except Exception as e:
            self.logger.error(f"Error checking album: {e}")

    def _get_assets_for_processing(self):
        """Get assets from the watching album, returning None if no assets to process."""
        print(f"📂 Getting assets from '{self.album_name}' album...")
        assets = self._get_assets_in_album()
        
        if not assets:
            print(f"✅ No assets found in '{self.album_name}' album - nothing to process")
            self.logger.debug(f"No assets found in '{self.album_name}' album")
            return None
            
        return assets

    def _process_single_asset(self, asset_data, index, total):
        """Process a single asset for category detection and album placement."""
        print(f"\n📸 Processing asset {index}/{total}: {asset_data['filename']}")
        print(f"   Type: {asset_data['media_type']}")
        self.logger.info(f"Found {asset_data['media_type']}: {asset_data['filename']}")
        
        # Extract title, caption, and keywords
        asset_obj = asset_data['asset_obj']
        title = asset_data['title']
        caption = self._extract_caption_with_logging(asset_obj, asset_data['filename'])
        keywords = self._extract_keywords_with_logging(asset_obj, asset_data['filename'])
        
        # Log title, caption, and keywords
        self._log_title_caption_and_keywords(title, caption, keywords)
        
        # Detect categories and process accordingly
        categories = self._detect_categories_from_all_sources(title, caption, keywords)
        
        if categories['has_any']:
            success = self._process_asset_with_categories(asset_obj, title, caption, keywords, categories)
            self._handle_processing_result(success, asset_data)
        else:
            self._handle_asset_without_categories(asset_data)

    def _extract_caption_with_logging(self, asset_obj, filename):
        """Extract caption with appropriate logging."""
        print(f"   🔍 Extracting caption using photokit...")
        self.logger.debug(f"Starting caption extraction for {filename}")
        caption = self._extract_caption_with_photokit(asset_obj)
        self.logger.debug(f"Caption extraction completed. Result: {repr(caption)}")
        return caption

    def _extract_keywords_with_logging(self, asset_obj, filename):
        """Extract keywords with appropriate logging."""
        print(f"   🏷️  Extracting keywords from asset...")
        self.logger.debug(f"Starting keyword extraction for {filename}")
        keywords = self._extract_keywords_from_asset(asset_obj)
        self.logger.debug(f"Keyword extraction completed. Result: {repr(keywords)}")
        return keywords

    def _extract_keywords_from_asset(self, asset_obj):
        """Extract keywords from PHAsset using multiple methods."""
        try:
            # Try direct PHAsset keyword extraction
            keywords = self._extract_direct_keywords(asset_obj)
            
            # Try alternative keyword fields if direct method failed
            if not keywords:
                keywords = self._extract_alternative_keywords(asset_obj)
            
            # Try photokit integration if other methods failed
            if not keywords:
                keywords = self._extract_photokit_keywords(asset_obj)
            
            return keywords
            
        except Exception as e:
            self.logger.debug(f"Keyword extraction error: {e}")
            return []

    def _extract_direct_keywords(self, asset_obj):
        """Extract keywords directly from PHAsset."""
        keywords = []
        if not hasattr(asset_obj, 'valueForKey_'):
            return keywords
            
        try:
            asset_keywords = asset_obj.valueForKey_('keywords')
            if asset_keywords:
                keywords = self._convert_nsarray_to_list(asset_keywords)
        except Exception as e:
            self.logger.debug(f"Direct keyword extraction failed: {e}")
        
        return keywords

    def _extract_alternative_keywords(self, asset_obj):
        """Extract keywords from alternative PHAsset fields."""
        keywords = []
        try:
            for field in ['tags', 'keywordTitles', 'keywordNames']:
                field_value = asset_obj.valueForKey_(field)
                if field_value:
                    keywords = self._convert_nsarray_to_list(field_value)
                    if keywords:
                        break
        except Exception as e:
            self.logger.debug(f"Alternative keyword extraction failed: {e}")
        
        return keywords

    def _extract_photokit_keywords(self, asset_obj):
        """Extract keywords using photokit integration."""
        if not PHOTOKIT_AVAILABLE:
            return []
            
        try:
            uuid = self._extract_asset_uuid(asset_obj)
            photo_library = photokit.PhotoLibrary()
            return self._try_photokit_keyword_methods(photo_library, uuid)
        except Exception as e:
            self.logger.debug(f"Photokit keyword extraction failed: {e}")
            return []

    def _try_photokit_keyword_methods(self, photo_library, uuid):
        """Try different photokit methods to extract keywords."""
        for method_name, method_call in [
            ('fetch_uuid', lambda: photo_library.fetch_uuid(uuid)),
            ('get_photo', lambda: photo_library.get_photo(uuid)),
        ]:
            if hasattr(photo_library, method_name):
                keywords = self._extract_keywords_from_photokit_asset(method_call)
                if keywords:
                    return keywords
        return []

    def _extract_keywords_from_photokit_asset(self, method_call):
        """Extract keywords from a photokit asset using the provided method."""
        try:
            photo_asset = method_call()
            if photo_asset and hasattr(photo_asset, 'keywords'):
                photo_keywords = photo_asset.keywords
                if photo_keywords:
                    return list(photo_keywords)
        except Exception:
            pass
        return []

    def _convert_nsarray_to_list(self, nsarray_obj):
        """Convert NSArray to Python list of keywords."""
        keywords = []
        if hasattr(nsarray_obj, 'count'):
            for i in range(nsarray_obj.count()):
                keyword = nsarray_obj.objectAtIndex_(i)
                if keyword:
                    keywords.append(str(keyword))
        else:
            keywords = list(nsarray_obj)
        return keywords

    def _log_title_caption_and_keywords(self, title, caption, keywords):
        """Log title, caption, and keywords information."""
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
            
        if keywords:
            print(f"   🏷️  Keywords: {keywords}")
            self.logger.info(f"  Keywords: {keywords}")
        else:
            print(f"   🏷️  Keywords: None")
            self.logger.info(f"  Keywords: None")

    def _detect_categories_from_all_sources(self, title, caption, keywords):
        """Detect category format in title, caption, and keywords."""
        has_title_category = title and ':' in title
        has_caption_category = caption and ':' in caption
        keyword_categories = self._extract_keyword_categories(keywords)
        has_keyword_categories = len(keyword_categories) > 0
        
        self._log_category_detection_results(has_title_category, has_caption_category, has_keyword_categories, keyword_categories)
        
        return {
            'has_title': has_title_category,
            'has_caption': has_caption_category,
            'has_keywords': has_keyword_categories,
            'keyword_categories': keyword_categories,
            'has_any': has_title_category or has_caption_category or has_keyword_categories
        }

    def _extract_keyword_categories(self, keywords):
        """Extract keywords that contain category format (colon)."""
        keyword_categories = []
        if keywords:
            for keyword in keywords:
                if keyword and ':' in keyword:
                    keyword_categories.append(keyword)
        return keyword_categories

    def _log_category_detection_results(self, has_title_category, has_caption_category, has_keyword_categories, keyword_categories):
        """Log category detection results for debugging."""
        print(f"   🎯 Category Detection:")
        print(f"      - Title has colon (:): {has_title_category}")
        print(f"      - Caption has colon (:): {has_caption_category}")
        print(f"      - Keywords with colon (:): {has_keyword_categories}")
        if has_keyword_categories:
            print(f"      - Category keywords: {keyword_categories}")
        
        self.logger.debug(f"Category detection - Title: {has_title_category}, Caption: {has_caption_category}, Keywords: {has_keyword_categories}")
        if keyword_categories:
            self.logger.debug(f"Category keywords found: {keyword_categories}")

    def _process_asset_with_categories(self, asset_obj, title, caption, keywords, categories):
        """Process asset that has category format in title, caption, and/or keywords."""
        print(f"   ✅ CATEGORY DETECTED - Processing asset:")
        
        if categories['has_title']:
            print(f"      📝 Category in TITLE: '{title}'")
            self.logger.info(f"  Category detected in TITLE: '{title}'")
        if categories['has_caption']:
            print(f"      💬 Category in CAPTION: '{caption}'")
            self.logger.info(f"  Category detected in CAPTION: '{caption}'")
        if categories['has_keywords']:
            print(f"      🏷️  Category in KEYWORDS: {categories['keyword_categories']}")
            self.logger.info(f"  Category detected in KEYWORDS: {categories['keyword_categories']}")
        
        return self._perform_multi_album_placement(asset_obj, title, caption, keywords, categories)

    def _perform_multi_album_placement(self, asset_obj, title, caption, keywords, categories):
        """Perform multi-album placement for title, caption, and/or keyword categories."""
        print(f"   🔄 Processing categories for multi-album placement...")
        
        success_count = 0
        total_attempts = 0
        
        # Process title category if present
        if categories['has_title']:
            success_count += self._process_title_category(asset_obj, title)
            total_attempts += 1
        
        # Process caption category if present
        if categories['has_caption']:
            success_count += self._process_caption_category(asset_obj, caption)
            total_attempts += 1
        
        # Process keyword categories if present
        if categories['has_keywords']:
            for keyword in categories['keyword_categories']:
                success_count += self._process_keyword_category(asset_obj, keyword)
                total_attempts += 1
        
        success = success_count > 0
        print(f"   📊 Album placement summary: {success_count}/{total_attempts} successful")
        return success

    def _process_title_category(self, asset_obj, title):
        """Process title category and return 1 if successful, 0 if failed."""
        category_parts = title.split(':', 1)
        category = category_parts[0].strip()
        title_album = f"02/{category}/{title}"
        print(f"   🎯 Processing title album: '{title_album}'")
        
        try:
            success = self.transfer.transfer_asset(asset_obj)
            if success:
                print(f"   ✅ SUCCESS - Added to title-based album: '{title_album}'")
                return 1
            else:
                print(f"   ❌ FAILED - Could not add to title-based album: '{title_album}'")
                return 0
        except Exception as e:
            print(f"   ❌ ERROR - Title album processing failed: {e}")
            return 0

    def _process_caption_category(self, asset_obj, caption):
        """Process caption category and return 1 if successful, 0 if failed."""
        category_parts = caption.split(':', 1)
        category = category_parts[0].strip()
        caption_album = f"02/{category}/{caption}"
        print(f"   🎯 Processing caption album: '{caption_album}'")
        
        try:
            success = self.transfer.transfer_asset(asset_obj, custom_title=caption)
            if success:
                print(f"   ✅ SUCCESS - Added to caption-based album: '{caption_album}'")
                return 1
            else:
                print(f"   ❌ FAILED - Could not add to caption-based album: '{caption_album}'")
                return 0
        except Exception as e:
            print(f"   ❌ ERROR - Caption album processing failed: {e}")
            return 0

    def _process_keyword_category(self, asset_obj, keyword):
        """Process keyword category and return 1 if successful, 0 if failed."""
        category_parts = keyword.split(':', 1)
        category = category_parts[0].strip()
        keyword_album = f"02/{category}/{keyword}"
        print(f"   🏷️  Processing keyword album: '{keyword_album}'")
        
        try:
            success = self.transfer.transfer_asset(asset_obj, custom_title=keyword)
            if success:
                print(f"   ✅ SUCCESS - Added to keyword-based album: '{keyword_album}'")
                return 1
            else:
                print(f"   ❌ FAILED - Could not add to keyword-based album: '{keyword_album}'")
                return 0
        except Exception as e:
            print(f"   ❌ ERROR - Keyword album processing failed: {e}")
            return 0

    def _handle_processing_result(self, success, asset_data):
        """Handle the result of asset processing (success or failure)."""
        if success:
            print(f"   ✅ SUCCESS - Transfer system processed asset successfully")
            self.logger.info(f"Successfully processed {asset_data['filename']}")
            self._remove_processed_asset(asset_data)
        else:
            print(f"   ❌ FAILED - Transfer system could not process asset")
            self.logger.error(f"Failed to process {asset_data['filename']}")

    def _handle_asset_without_categories(self, asset_data):
        """Handle asset that doesn't have category format."""
        print(f"   ❌ NO CATEGORY DETECTED - Skipping asset (no colon in title or caption)")
        self.logger.info(f"  No category format detected (no colon in title or caption) - skipping")
        
        print(f"   🗑️  Removing from '{self.album_name}' album...")
        if self._remove_asset_from_album(asset_data['id']):
            print(f"   ✅ Removed '{asset_data['filename']}' from '{self.album_name}' album")
            self.logger.info(f"Removed {asset_data['filename']} from '{self.album_name}' album (no category)")
        else:
            print(f"   ❌ Failed to remove '{asset_data['filename']}' from '{self.album_name}' album")

    def _remove_processed_asset(self, asset_data):
        """Remove successfully processed asset from the watching album."""
        print(f"   🗑️  Removing processed asset from '{self.album_name}' album...")
        if self._remove_asset_from_album(asset_data['id']):
            print(f"   ✅ Removed '{asset_data['filename']}' from '{self.album_name}' album")
            self.logger.info(f"Removed {asset_data['filename']} from '{self.album_name}' album")
        else:
            print(f"   ❌ Failed to remove '{asset_data['filename']}' from '{self.album_name}' album")
            self.logger.error(f"Failed to remove {asset_data['filename']} from album")

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
