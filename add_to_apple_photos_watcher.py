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
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from apple_photos_sdk import ApplePhotos
from apple_photos_sdk.album import AlbumManager
from config import APPLE_PHOTOS_WATCHING
import Photos
from objc import autorelease_pool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ApplePhotosWatcherAdder:
    """Utility to add photos from Apple Photos library to the Watching album."""
    
    def __init__(self):
        self.apple_photos = ApplePhotos()
        self.album_manager = AlbumManager()
        # Use album name from config (strip trailing slash and convert to string)
        self.watching_album_name = str(APPLE_PHOTOS_WATCHING).rstrip('/')
        self.batch_size = 100
        self.pause_duration = 5  # seconds
        
    def find_or_create_watching_album(self):
        """Find or create the Watching album."""
        try:
            with autorelease_pool():
                # Get all albums
                fetch_options = Photos.PHFetchOptions.alloc().init()
                albums = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                    Photos.PHAssetCollectionTypeAlbum,
                    Photos.PHAssetCollectionSubtypeAny,
                    fetch_options
                )
                
                # Look for existing Watching album
                for i in range(albums.count()):
                    album = albums.objectAtIndex_(i)
                    if album.localizedTitle() == self.watching_album_name:
                        logger.info(f"Found existing '{self.watching_album_name}' album")
                        return album
                
                # Create Watching album if it doesn't exist
                logger.info(f"Creating '{self.watching_album_name}' album...")
                success, album_id = self.album_manager._create_album_in_folder_with_logging(
                    self.watching_album_name, None
                )
                
                if success:
                    # Fetch the newly created album
                    albums = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                        Photos.PHAssetCollectionTypeAlbum,
                        Photos.PHAssetCollectionSubtypeAny,
                        fetch_options
                    )
                    
                    for i in range(albums.count()):
                        album = albums.objectAtIndex_(i)
                        if album.localizedTitle() == self.watching_album_name:
                            logger.info(f"Successfully created '{self.watching_album_name}' album")
                            return album
                
                logger.error(f"Failed to create '{self.watching_album_name}' album")
                return None
                
        except Exception as e:
            logger.error(f"Error finding/creating Watching album: {e}")
            return None
    
    def get_all_photos(self):
        """Get all photos and videos from the Apple Photos library."""
        try:
            with autorelease_pool():
                fetch_options = Photos.PHFetchOptions.alloc().init()
                # Sort by creation date (oldest first)
                fetch_options.setSortDescriptors_([
                    Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_("creationDate", True)
                ])
                
                # Fetch all assets (photos and videos)
                assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
                
                logger.info(f"Found {assets.count()} total assets in Apple Photos library")
                return assets
                
        except Exception as e:
            logger.error(f"Error fetching photos from library: {e}")
            return None
    
    def add_assets_to_watching_album(self, assets, watching_album):
        """Add assets to the Watching album in batches with pauses."""
        if not assets or not watching_album:
            logger.error("Invalid assets or watching album")
            return False
        
        total_assets = assets.count()
        added_count = 0
        error_count = 0
        skipped_count = 0
        batch_count = 0
        
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
                        caption = asset.valueForKey_('accessibilityDescription')  # This is the caption/description
                        
                        # Only add assets with titles or captions containing ':' (category format)
                        has_category_title = title and ':' in title
                        has_category_caption = caption and ':' in caption
                        
                        if has_category_title or has_category_caption:
                            # Add asset to Watching album
                            success = self.album_manager._add_to_album(asset_id, watching_album.localIdentifier())
                            
                            if success:
                                added_count += 1
                                # Log which field had the category format
                                category_source = "title" if has_category_title else "caption"
                                category_text = title if has_category_title else caption
                                logger.info(f"Added {media_type} {added_count} (category in {category_source}): '{category_text}' ({asset_id[:8]}...)")
                                
                                # Pause after every 1000 successfully added photos
                                if added_count % 1000 == 0:
                                    logger.info(f"Reached {added_count} added photos - pausing for 10 seconds...")
                                    time.sleep(10)
                            else:
                                error_count += 1
                                category_source = "title" if has_category_title else "caption"
                                category_text = title if has_category_title else caption
                                logger.warning(f"Failed to add asset {i+1}/{total_assets} (category in {category_source}): '{category_text}' ({asset_id[:8]}...)")
                        else:
                            # Skip assets without category-format titles or captions
                            skipped_count += 1
                            if skipped_count <= 10:  # Only log first 10 skips to avoid spam
                                if not title and not caption:
                                    skip_reason = "no title or caption"
                                elif not title:
                                    skip_reason = "no title, caption has no colon"
                                elif not caption:
                                    skip_reason = "no caption, title has no colon"
                                else:
                                    skip_reason = "no colon in title or caption"
                                logger.debug(f"Skipped {media_type} ({skip_reason}): title='{title}', caption='{caption}' ({asset_id[:8]}...)")
                            elif skipped_count == 11:
                                logger.info(f"Skipping additional assets without category titles or captions (will show total at end)...")
                    
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
        logger.info(f"Skipped (no category title): {skipped_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"Batches processed: {batch_count}")
        logger.info("=" * 60)
        
        return True
    
    def run(self, max_assets=None):
        """Main execution method."""
        logger.info("Starting Apple Photos Watcher Adder utility...")
        
        # Step 1: Find or create Watching album
        watching_album = self.find_or_create_watching_album()
        if not watching_album:
            logger.error("Could not find or create Watching album. Exiting.")
            return False
        
        # Step 2: Get all photos from library
        all_assets = self.get_all_photos()
        if not all_assets:
            logger.error("Could not fetch photos from library. Exiting.")
            return False
        
        # Step 3: Limit assets if max_assets specified
        if max_assets and max_assets < all_assets.count():
            logger.info(f"Limiting to first {max_assets} assets (out of {all_assets.count()} total)")
        
        # Step 4: Add assets to Watching album
        success = self.add_assets_to_watching_album(all_assets, watching_album)
        
        if success:
            logger.info("Utility completed successfully!")
            logger.info(f"Assets are now in the '{self.watching_album_name}' album and will be processed by the watcher.")
        else:
            logger.error("Utility completed with errors.")
        
        return success


def main():
    """Main entry point with command line argument support."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Add Apple Photos library images to Watching album")
    parser.add_argument(
        "--max-assets", 
        type=int, 
        help="Maximum number of assets to process (for testing)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of assets to process before pausing (default: 20)"
    )
    parser.add_argument(
        "--pause-duration",
        type=int,
        default=5,
        help="Seconds to pause between batches (default: 5)"
    )
    
    args = parser.parse_args()
    
    # Create and configure the adder
    adder = ApplePhotosWatcherAdder()
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
