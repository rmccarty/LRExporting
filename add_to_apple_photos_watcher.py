#!/usr/bin/env python3
"""
Utility script to add images from Apple Photos library to the "Watching" album
for processing by the Apple Photos watcher system.

This script:
1. Connects to the Apple Photos library
2. Iterates through all photos/videos
3. Adds them to the "Watching" album in batches
4. Pauses for 5 seconds after every 20 images
5. Provides progress updates and error handling
"""

import sys
import time
import logging
import argparse
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from apple_photos_sdk import ApplePhotos
from apple_photos_sdk.album import AlbumManager
from config import APPLE_PHOTOS_WATCHING
import Photos
from objc import autorelease_pool
import photokit

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

class ApplePhotosWatcherAdder:
    """Utility to add photos from Apple Photos library to the Watching album."""
    
    def __init__(self, search_mode='title', batch_size=20, pause_duration=5):
        """Initialize the Apple Photos Watcher Adder.
        
        Args:
            search_mode: 'title' (recommended), 'caption', or 'both' - where to look for category format
            batch_size: Number of assets to process before pausing
            pause_duration: Seconds to pause between batches
        """
        self.apple_photos = ApplePhotos()
        self.album_manager = AlbumManager()
        # Use album name from config (strip trailing slash and convert to string)
        self.watching_album_name = str(APPLE_PHOTOS_WATCHING).rstrip('/')
        self.batch_size = batch_size
        self.pause_duration = pause_duration  # seconds
        self.search_mode = search_mode
        
        logger.info(f"Initialized with search mode: {search_mode}")
        if search_mode == 'title':
            logger.info("Will look for ':' in titles only")
        elif search_mode == 'caption':
            logger.info("Will look for ':' in captions/descriptions only")
        else:
            logger.info("Will look for ':' in both titles and captions/descriptions")
        
    def find_or_create_watching_album(self):
        """Find or create the Watching album."""
        try:
            with autorelease_pool():
                logger.info(f"Searching for album: '{self.watching_album_name}'")
                print(f"DEBUG: Searching for album: '{self.watching_album_name}'")
                
                # Try direct predicate search with different property names
                search_attempts = [
                    ("localizedTitle", "Watching"),
                    ("title", "Watching"), 
                    ("localizedTitle", self.watching_album_name),
                    ("title", self.watching_album_name)
                ]
                
                for property_name, search_value in search_attempts:
                    try:
                        fetch_options = Photos.PHFetchOptions.alloc().init()
                        predicate = Photos.NSPredicate.predicateWithFormat_(f"{property_name} == %@", search_value)
                        fetch_options.setPredicate_(predicate)
                        
                        album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                            Photos.PHAssetCollectionTypeAlbum,
                            Photos.PHAssetCollectionSubtypeAny,
                            fetch_options
                        )
                        
                        if album_result.count() > 0:
                            album = album_result.objectAtIndex_(0)
                            logger.info(f"Found album using {property_name} == '{search_value}': '{album.localizedTitle()}'")
                            print(f"DEBUG: Found album using {property_name} == '{search_value}': '{album.localizedTitle()}'")
                            return album
                        else:
                            print(f"DEBUG: No results for {property_name} == '{search_value}'")
                            
                    except Exception as e:
                        print(f"DEBUG: Error with {property_name} search: {e}")
                        continue
                
                # If predicate searches failed, fall back to iteration (but limit to first 100 for efficiency)
                print("DEBUG: Predicate searches failed, trying direct iteration...")
                fetch_options = Photos.PHFetchOptions.alloc().init()
                all_albums = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                    Photos.PHAssetCollectionTypeAlbum,
                    Photos.PHAssetCollectionSubtypeAny,
                    fetch_options
                )
                
                print(f"DEBUG: Found {all_albums.count()} total albums, checking first 100...")
                
                for i in range(min(100, all_albums.count())):
                    album = all_albums.objectAtIndex_(i)
                    album_title = album.localizedTitle()
                    if album_title == "Watching":
                        logger.info(f"Found 'Watching' album at position {i+1}")
                        print(f"DEBUG: Found 'Watching' album at position {i+1}")
                        return album
                
                # If still not found, continue with test mode
                logger.warning(f"Album not found. Continuing in test mode.")
                print("DEBUG: Album not found, continuing in test mode")
                return "test_mode"
                
        except Exception as e:
            logger.error(f"Error finding album: {e}")
            print(f"DEBUG: Error finding album: {e}")
            return None
    
    def get_limited_photos(self, limit=50):
        """Get a limited number of photos from the Apple Photos library for testing."""
        try:
            print(f"DEBUG: Starting to fetch {limit} photos from library...")
            with autorelease_pool():
                fetch_options = Photos.PHFetchOptions.alloc().init()
                # Sort by creation date (newest first)
                fetch_options.setSortDescriptors_([
                    Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_("creationDate", False)
                ])
                # Set fetch limit for efficiency
                fetch_options.setFetchLimit_(limit)
                
                print(f"DEBUG: Calling PHAsset.fetchAssetsWithOptions_ with limit {limit}...")
                # Fetch limited assets
                limited_assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
                print(f"DEBUG: Fetch completed, found {limited_assets.count()} assets")
                return limited_assets
                
        except Exception as e:
            logger.error(f"Error fetching photos from library: {e}")
            print(f"DEBUG: Error fetching photos: {e}")
            return None
    
    def get_all_photos_batched(self, batch_size=1000):
        """Get all photos from the library, yielding batches for memory efficiency."""
        try:
            print(f"DEBUG: Starting to fetch ALL photos from library in batches of {batch_size}...")
            with autorelease_pool():
                fetch_options = Photos.PHFetchOptions.alloc().init()
                # Sort by creation date (newest first) for consistent ordering
                fetch_options.setSortDescriptors_([
                    Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_("creationDate", False)
                ])
                
                print(f"DEBUG: Fetching all assets from library...")
                # Fetch ALL assets (no limit)
                all_assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
                total_count = all_assets.count()
                print(f"DEBUG: Found {total_count} total assets in library")
                
                # Process in batches
                for start_index in range(0, total_count, batch_size):
                    end_index = min(start_index + batch_size, total_count)
                    batch_count = end_index - start_index
                    
                    print(f"DEBUG: Processing batch {start_index//batch_size + 1}: assets {start_index+1}-{end_index} ({batch_count} assets)")
                    
                    # Create a list to hold the batch
                    batch_assets = []
                    for i in range(start_index, end_index):
                        asset = all_assets.objectAtIndex_(i)
                        batch_assets.append((i, asset))  # Include index for progress tracking
                    
                    yield batch_assets, start_index, end_index, total_count
                
        except Exception as e:
            logger.error(f"Error fetching photos from library: {e}")
            print(f"DEBUG: Error fetching photos: {e}")
            return None
    
    def add_assets_to_watching_album(self, assets, watching_album):
        """Add assets to the Watching album in batches with pauses."""
        if not assets or not watching_album:
            logger.error("Invalid assets or watching album")
            return False
        
        total_assets = assets.count()
        logger.info(f"Processing {total_assets} assets...")
        
        added_count = 0
        processed_count = 0
        added_count = 0
        error_count = 0
        skipped_count = 0
        batch_count = 0
        title_matches = 0
        caption_matches = 0
        title_added = 0      # Assets added because title had ':'
        caption_added = 0    # Assets added because caption had ':'
        logger.info(f"Starting to add {total_assets} assets to '{self.watching_album_name}' album...")
        logger.info(f"Processing in batches of {self.batch_size} with {self.pause_duration}s pauses")
        
        try:
            with autorelease_pool():
                for i in range(total_assets):
                    asset = assets.objectAtIndex_(i)
                    
                    try:
                        # Get asset info for logging and filtering
                        asset_id = asset.localIdentifier()
                        creation_date = asset.creationDate()
                        media_type = "photo" if asset.mediaType() == Photos.PHAssetMediaTypeImage else "video"
                        title = asset.valueForKey_('title')
                        
                        # Only print debug info for titles with colons
                        if title and ':' in title:
                            print(f"DEBUG: Processing {media_type} {i+1}/{total_assets} - Title: '{title}'")
                        
                        # Get caption (placeholder for now - will be None)
                        caption = None  # TODO: Implement actual caption extraction
                        
                        # Category detection: Title first, then caption fallback
                        has_category = False
                        category_source = None
                        category_text = None
                        
                        if title and ':' in title:
                            # Primary: Title has category format
                            has_category = True
                            category_source = "title"
                            category_text = title
                            title_matches += 1
                            print(f"DEBUG: Asset {i+1}: Category in TITLE: '{title}'")
                        elif caption and ':' in caption:
                            # Fallback: Caption has category format
                            has_category = True
                            category_source = "caption"
                            category_text = caption
                            caption_matches += 1
                            print(f"DEBUG: Asset {i+1}: Category in CAPTION: '{caption}'")
                        
                        # Show debug for any asset with category format
                        if has_category:
                            print(f"DEBUG: Category detected in {category_source}: '{category_text}'")
                        
                        if has_category:
                            # Add asset to Watching album
                            print(f"DEBUG: Adding {media_type} to Watching album")
                            success = self.album_manager._add_to_album(asset_id, watching_album.localIdentifier())
                            
                            if success:
                                added_count += 1
                                
                                # Track the specific reason for addition
                                if category_source == "title":
                                    title_added += 1
                                elif category_source == "caption":
                                    caption_added += 1
                                
                                logger.info(f"Added {media_type} {added_count} ({category_source}): '{category_text}' ({asset_id[:8]}...)")
                                print(f"DEBUG: Successfully added! Total added: {added_count} (Title: {title_added}, Caption: {caption_added})")
                                
                                # Pause after every 1000 successfully added photos
                                if added_count % 1000 == 0:
                                    logger.info(f"Reached {added_count} added photos - pausing for 10 seconds...")
                                    time.sleep(10)
                            else:
                                error_count += 1
                                logger.warning(f"Failed to add asset {i+1}/{total_assets}: '{title}' ({asset_id[:8]}...)")
                                print(f"DEBUG: Failed to add! Total errors: {error_count}")
                        else:
                            # Skip assets without category-format titles
                            skipped_count += 1
                            if skipped_count <= 10:  # Only log first 10 skips to avoid spam
                                logger.info(f"Skipped {media_type} {skipped_count} (no colon in title): '{title}' ({asset_id[:8]}...)")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing asset {i+1}/{total_assets}: {e}")
                    
                    # Log progress after every batch_size assets
                    if (added_count + error_count) % self.batch_size == 0:
                        batch_count += 1
                        logger.info(f"Completed batch {batch_count} ({added_count} added, {error_count} errors, {skipped_count} skipped)")
        
        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            return False
        
        # Final summary
        logger.info("=" * 60)
        logger.info("BULK ADD COMPLETE")
        logger.info(f"Total assets processed: {total_assets}")
        logger.info(f"Successfully added: {added_count}")
        
        # Show breakdown by addition reason
        logger.info(f"  - Title Added: {title_added}")
        logger.info(f"  - Caption Added: {caption_added}")
        
        # Show detection stats
        logger.info(f"Detection stats:")
        logger.info(f"  - Title matches found: {title_matches}")
        logger.info(f"  - Caption matches found: {caption_matches}")
        
        logger.info(f"Skipped (no category format): {skipped_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"Batches processed: {batch_count}")
        logger.info("=" * 60)
        
        return True
    
    def process_entire_library_batched(self, watching_album):
        """Process the entire library in batches for memory efficiency."""
        logger.info("Starting full library processing...")
        
        # Initialize counters
        total_added = 0
        total_errors = 0
        total_skipped = 0
        total_title_added = 0
        total_caption_added = 0
        total_title_matches = 0
        total_caption_matches = 0
        
        batch_number = 0
        
        try:
            # Process library in batches
            for batch_data in self.get_all_photos_batched(batch_size=self.batch_size):
                if batch_data is None:
                    logger.error("Failed to get batch data")
                    break
                    
                batch_assets, start_index, end_index, total_count = batch_data
                batch_number += 1
                
                logger.info(f"Processing batch {batch_number}: assets {start_index+1}-{end_index} of {total_count}")
                print(f"DEBUG: Batch {batch_number} - processing {len(batch_assets)} assets")
                
                # Process each asset in the batch
                batch_added = 0
                batch_errors = 0
                batch_skipped = 0
                batch_title_added = 0
                batch_caption_added = 0
                
                for asset_index, asset in batch_assets:
                    try:
                        with autorelease_pool():
                            asset_id = asset.localIdentifier()
                            media_type = "photo" if asset.mediaType() == Photos.PHAssetMediaTypeImage else "video"
                            title = asset.valueForKey_('title')
                            
                            # Get caption (placeholder for now - will be None)
                            caption = None  # TODO: Implement actual caption extraction
                            
                            # Category detection: Title first, then caption fallback
                            has_category = False
                            category_source = None
                            category_text = None
                            
                            if title and ':' in title:
                                # Primary: Title has category format
                                has_category = True
                                category_source = "title"
                                category_text = title
                                total_title_matches += 1
                                if title and ':' in title:
                                    print(f"DEBUG: Asset {asset_index+1}: Category in TITLE: '{title}'")
                            elif caption and ':' in caption:
                                # Fallback: Caption has category format
                                has_category = True
                                category_source = "caption"
                                category_text = caption
                                total_caption_matches += 1
                                print(f"DEBUG: Asset {asset_index+1}: Category in CAPTION: '{caption}'")
                            
                            if has_category:
                                # Add asset to Watching album
                                print(f"DEBUG: Adding {media_type} to Watching album")
                                success = self.album_manager._add_to_album(asset_id, watching_album.localIdentifier())
                                
                                if success:
                                    total_added += 1
                                    batch_added += 1
                                    
                                    # Track the specific reason for addition
                                    if category_source == "title":
                                        total_title_added += 1
                                        batch_title_added += 1
                                    elif category_source == "caption":
                                        total_caption_added += 1
                                        batch_caption_added += 1
                                    
                                    logger.info(f"Added {media_type} {total_added} ({category_source}): '{category_text}' ({asset_id[:8]}...)")
                                    
                                    # Pause after every 1000 successfully added photos
                                    if total_added % 1000 == 0:
                                        logger.info(f"Reached {total_added} added photos - pausing for 10 seconds...")
                                        time.sleep(10)
                                else:
                                    total_errors += 1
                                    batch_errors += 1
                                    logger.warning(f"Failed to add asset {asset_index+1}: '{category_text}' ({asset_id[:8]}...)")
                            else:
                                # Skip assets without category-format titles
                                total_skipped += 1
                                batch_skipped += 1
                                if total_skipped <= 10:  # Only log first 10 skips to avoid spam
                                    logger.info(f"Skipped {media_type} {total_skipped} (no colon in title): '{title}' ({asset_id[:8]}...)")
                    
                    except Exception as e:
                        total_errors += 1
                        batch_errors += 1
                        logger.error(f"Error processing asset {asset_index+1}: {e}")
                
                # Batch summary with running totals
                logger.info(f"Batch {batch_number} complete: {batch_added} added, {batch_errors} errors, {batch_skipped} skipped")
                logger.info(f"Running totals: {total_added} total added (Title: {total_title_added}, Caption: {total_caption_added}), {total_errors} errors, {total_skipped} skipped")
                print(f"DEBUG: Batch {batch_number} - Added: {batch_added} (Title: {batch_title_added}, Caption: {batch_caption_added})")
                print(f"DEBUG: Running totals - Added: {total_added} (Title: {total_title_added}, Caption: {total_caption_added}), Errors: {total_errors}, Skipped: {total_skipped}")
                
                # Pause between batches
                if batch_number % 10 == 0:  # Pause every 10 batches
                    logger.info(f"Completed {batch_number} batches - pausing for {self.pause_duration} seconds...")
                    time.sleep(self.pause_duration)
        
        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            return False
        
        # Final summary
        logger.info("=" * 60)
        logger.info("FULL LIBRARY PROCESSING COMPLETE")
        logger.info(f"Total assets processed: {start_index + len(batch_assets) if 'start_index' in locals() else 0}")
        logger.info(f"Successfully added: {total_added}")
        
        # Show breakdown by addition reason
        logger.info(f"  - Title Added: {total_title_added}")
        logger.info(f"  - Caption Added: {total_caption_added}")
        
        # Show detection stats
        logger.info(f"Detection stats:")
        logger.info(f"  - Title matches found: {total_title_matches}")
        logger.info(f"  - Caption matches found: {total_caption_matches}")
        
        logger.info(f"Skipped (no category format): {total_skipped}")
        logger.info(f"Errors: {total_errors}")
        logger.info(f"Batches processed: {batch_number}")
        logger.info("=" * 60)
        
        return True
    
    def test_caption_detection(self, assets, max_assets=None):
        """Test caption detection without album operations."""
        if not assets:
            logger.error("No assets provided for testing")
            return False
        
        total_assets = assets.count()
        test_limit = min(max_assets or 20, total_assets, 20)  # Limit to 20 for testing
        
        logger.info(f"Testing caption detection on {test_limit} assets...")
        
        title_matches = 0
        caption_matches = 0
        processed_count = 0
        
        try:
            with autorelease_pool():
                for i in range(test_limit):
                    asset = assets.objectAtIndex_(i)
                    processed_count += 1
                    
                    # Get title
                    title = asset.valueForKey_('title')
                    
                    # Get caption/description based on search mode using RhetTbull photokit
                    caption = None
                    if self.search_mode in ['caption', 'both']:
                        try:
                            # Use RhetTbull photokit to get photo metadata
                            asset_id = asset.localIdentifier()
                            logger.debug(f"Trying to get photokit asset for ID: {asset_id}")
                            
                            # Create PhotoAsset from the asset ID
                            photo_asset = photokit.PhotoAsset(asset_id)
                            logger.debug(f"Created PhotoAsset: {photo_asset}")
                            
                            # Try to get description/caption from photokit
                            if hasattr(photo_asset, 'description') and photo_asset.description:
                                caption = photo_asset.description.strip()
                                logger.info(f"Found caption via photokit description: '{caption}'")
                            elif hasattr(photo_asset, 'caption') and photo_asset.caption:
                                caption = photo_asset.caption.strip()
                                logger.info(f"Found caption via photokit caption: '{caption}'")
                            elif hasattr(photo_asset, 'comment') and photo_asset.comment:
                                caption = photo_asset.comment.strip()
                                logger.info(f"Found caption via photokit comment: '{caption}'")
                            else:
                                # Try other possible attributes
                                attrs = ['title', 'keywords', 'description_text']
                                for attr in attrs:
                                    if hasattr(photo_asset, attr):
                                        value = getattr(photo_asset, attr)
                                        if value and isinstance(value, str) and value.strip():
                                            caption = value.strip()
                                            logger.info(f"Found caption via photokit {attr}: '{caption}'")
                                            break
                            
                        except Exception as e:
                            logger.debug(f"Error extracting caption with photokit: {e}")
                            caption = None
                    
                    # Check for category format
                    has_category_title = title and ':' in title
                    has_category_caption = caption and ':' in caption
                    
                    if has_category_title:
                        title_matches += 1
                    if has_category_caption:
                        caption_matches += 1
                    
                    # Log findings
                    logger.info(f"Asset {processed_count}: title='{title}', caption='{caption}'")
                    if has_category_title:
                        logger.info(f"  ✓ Category format in title: '{title}'")
                    if has_category_caption:
                        logger.info(f"  ✓ Category format in caption: '{caption}'")
                    
                    if processed_count >= 10:  # Show detailed info for first 10
                        break
                        
        except Exception as e:
            logger.error(f"Error during caption testing: {e}")
            return False
        
        # Final summary
        logger.info("=" * 60)
        logger.info("CAPTION DETECTION TEST COMPLETE")
        logger.info(f"Search mode: {self.search_mode}")
        logger.info(f"Assets tested: {processed_count}")
        logger.info(f"Title matches: {title_matches}")
        logger.info(f"Caption matches: {caption_matches}")
        logger.info("=" * 60)
        
        return True
    
    def run(self, max_assets=None):
        """Main execution method."""
        logger.info("Starting Apple Photos Watcher Adder utility...")
        logger.info(f"Search mode: {self.search_mode}")
        logger.info(f"Max assets: {max_assets}")
        
        # Step 1: Find or create Watching album
        logger.info("Step 1: Finding or creating Watching album...")
        watching_album = self.find_or_create_watching_album()
        if not watching_album:
            logger.error("Could not find or create Watching album. Exiting.")
            return False
        logger.info("Watching album ready")
        
        # Step 2: Get limited photos from library for efficient testing
        fetch_limit = max_assets or 50  # Use max_assets or default to 50
        logger.info(f"Step 2: Getting {fetch_limit} photos from library...")
        print(f"DEBUG: About to call get_limited_photos({fetch_limit})...")
        all_assets = self.get_limited_photos(fetch_limit)
        print("DEBUG: get_limited_photos() returned")
        if not all_assets:
            logger.error("Could not fetch photos from library. Exiting.")
            print("DEBUG: get_limited_photos() returned None")
            return False
        logger.info(f"Found {all_assets.count()} assets for testing")
        print(f"DEBUG: Found {all_assets.count()} assets for testing")
        
        # Step 3: Process photos from library
        if max_assets:
            # Limited processing for testing
            logger.info(f"Step 3: Processing limited set of {max_assets} assets...")
            all_assets = self.get_limited_photos(max_assets)
            print("DEBUG: get_limited_photos() returned")
            if not all_assets:
                logger.error("Could not fetch photos from library. Exiting.")
                print("DEBUG: get_limited_photos() returned None")
                return False
            logger.info(f"Found {all_assets.count()} assets for testing")
            print(f"DEBUG: Found {all_assets.count()} assets for testing")
            
            # Step 4: Add assets to Watching album (or test caption detection)
            print(f"DEBUG: Step 4 - watching_album type: {type(watching_album)}, value: {watching_album}")
            if watching_album == "test_mode":
                logger.info("Step 4: Testing caption detection without album operations...")
                print("DEBUG: Running in test mode - calling test_caption_detection")
                success = self.test_caption_detection(all_assets, max_assets)
            else:
                logger.info("Step 4: Adding assets to Watching album...")
                print("DEBUG: Adding assets to Watching album - calling add_assets_to_watching_album")
                success = self.add_assets_to_watching_album(all_assets, watching_album)
        else:
            # Full library processing in batches
            logger.info("Step 3: Processing ENTIRE library in batches...")
            print("DEBUG: Processing entire library using batch method")
            success = self.process_entire_library_batched(watching_album)
        
        if success:
            logger.info("Utility completed successfully!")
            logger.info(f"Assets are now in the '{self.watching_album_name}' album and will be processed by the watcher.")
        else:
            logger.error("Utility completed with errors.")
        
        return success


def main():
    """Main entry point with command line argument support."""
    parser = argparse.ArgumentParser(
        description="Add Apple Photos library images to Watching album",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Search Mode Options:
  title    - Look for ':' in titles only
  caption  - Look for ':' in captions/descriptions only
  both     - Look for ':' in both titles and captions (default)

Examples:
  python add_to_apple_photos_watcher.py                    # Search both title and caption
  python add_to_apple_photos_watcher.py title              # Search title only
  python add_to_apple_photos_watcher.py caption            # Search caption only
  python add_to_apple_photos_watcher.py --max-assets 100   # Limit to 100 assets
        """
    )
    
    # Positional argument for search mode
    parser.add_argument(
        "search_mode",
        nargs='?',
        choices=['title', 'caption', 'both'],
        default='both',
        help="Where to look for ':' - title, caption, or both (default: both)"
    )
    
    parser.add_argument(
        "--max-assets", 
        type=int, 
        help="Maximum number of assets to process (for testing)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of assets to process before pausing (default: 100)"
    )
    parser.add_argument(
        "--pause-duration",
        type=int,
        default=5,
        help="Seconds to pause between batches (default: 5)"
    )
    
    args = parser.parse_args()
    
    # Create and configure the adder with search mode
    adder = ApplePhotosWatcherAdder(search_mode=args.search_mode)
    if args.batch_size:
        adder.batch_size = args.batch_size
    if args.pause_duration:
        adder.pause_duration = args.pause_duration
    
    # Run the utility
    try:
        success = adder.run(max_assets=args.max_assets)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
