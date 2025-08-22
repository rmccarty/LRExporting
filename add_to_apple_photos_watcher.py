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
from config import APPLE_PHOTOS_WATCHING, APPLE_PHOTOS_WATCHING_MAX_SIZE, APPLE_PHOTOS_WATCHING_WATERMARK
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
        self.max_watching_size = APPLE_PHOTOS_WATCHING_MAX_SIZE
        self.watermark_threshold = APPLE_PHOTOS_WATCHING_WATERMARK
        
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
    
    def get_watching_album_count(self, watching_album):
        """Get the current number of assets in the Watching album."""
        try:
            with autorelease_pool():
                if not watching_album:
                    return 0
                
                # Fetch assets in the watching album
                fetch_options = Photos.PHFetchOptions.alloc().init()
                assets = Photos.PHAsset.fetchAssetsInAssetCollection_options_(watching_album, fetch_options)
                count = assets.count()
                
                logger.info(f"Watching album '{self.watching_album_name}' currently contains {count} assets")
                return count
                
        except Exception as e:
            logger.error(f"Error counting assets in Watching album: {e}")
            return 0
    
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
    
    def add_assets_to_watching_album(self, assets, watching_album, max_to_add=None):
        """Add assets to the Watching album in batches with pauses."""
        if not assets or not watching_album:
            logger.error("Invalid assets or watching album")
            return False
        
        total_assets = assets.count()
        # Limit processing to max_to_add if specified
        assets_to_process = min(total_assets, max_to_add) if max_to_add else total_assets
        
        added_count = 0
        error_count = 0
        batch_count = 0
        
        logger.info(f"Starting to add {assets_to_process} assets to '{self.watching_album_name}' album...")
        logger.info(f"Processing in batches of {self.batch_size}")
        
        try:
            with autorelease_pool():
                for i in range(assets_to_process):
                    # Stop if we've reached our limit
                    if max_to_add and (added_count + error_count) >= max_to_add:
                        logger.info(f"Reached maximum assets to add ({max_to_add}), stopping")
                        break
                        
                    asset = assets.objectAtIndex_(i)
                    
                    try:
                        # Get asset info for logging
                        asset_id = asset.localIdentifier()
                        creation_date = asset.creationDate()
                        media_type = "photo" if asset.mediaType() == Photos.PHAssetMediaTypeImage else "video"
                        
                        # Add asset to Watching album
                        success = self.album_manager._add_to_album(asset_id, watching_album.localIdentifier())
                        
                        if success:
                            added_count += 1
                            logger.info(f"Added {media_type} {added_count}/{assets_to_process}: {asset_id[:8]}... (created: {creation_date})")
                        else:
                            error_count += 1
                            logger.warning(f"Failed to add asset {i+1}/{assets_to_process}: {asset_id[:8]}...")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing asset {i+1}/{assets_to_process}: {e}")
                    
                    # Log batch progress
                    if (added_count + error_count) % self.batch_size == 0:
                        batch_count += 1
                        current_watching_count = self.get_watching_album_count(watching_album)
                        logger.info(f"Completed batch {batch_count} ({added_count} added, {error_count} errors)")
                        logger.info(f"Watching album now contains {current_watching_count} assets")
        
        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            return False
        
        # Final summary with watching album size
        final_watching_count = self.get_watching_album_count(watching_album)
        logger.info("=" * 60)
        logger.info("BULK ADD COMPLETE")
        logger.info(f"Total assets processed: {assets_to_process}")
        logger.info(f"Successfully added: {added_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"Batches processed: {batch_count}")
        logger.info(f"Final watching album size: {final_watching_count} assets")
        logger.info("=" * 60)
        
        return True
    
    def add_subset_to_watching_album(self, assets_subset, watching_album):
        """Add a subset of assets to the Watching album."""
        if not assets_subset or not watching_album:
            logger.error("Invalid assets subset or watching album")
            return False
        
        added_count = 0
        error_count = 0
        
        try:
            with autorelease_pool():
                for i, asset in enumerate(assets_subset):
                    try:
                        # Get asset info for logging
                        asset_id = asset.localIdentifier()
                        creation_date = asset.creationDate()
                        media_type = "photo" if asset.mediaType() == Photos.PHAssetMediaTypeImage else "video"
                        
                        # Add asset to Watching album
                        success = self.album_manager._add_to_album(asset_id, watching_album.localIdentifier())
                        
                        if success:
                            added_count += 1
                            logger.info(f"Added {media_type} {added_count}/{len(assets_subset)}: {asset_id[:8]}... (created: {creation_date})")
                        else:
                            error_count += 1
                            logger.warning(f"Failed to add asset {i+1}/{len(assets_subset)}: {asset_id[:8]}...")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing asset {i+1}/{len(assets_subset)}: {e}")
        
        except Exception as e:
            logger.error(f"Error during subset processing: {e}")
            return False
        
        logger.info(f"Subset complete: {added_count} added, {error_count} errors")
        return True
    
    def wait_for_watermark(self, watching_album, check_interval=30):
        """Wait for watching album to drop below watermark threshold."""
        logger.info(f"Monitoring watching album size every {check_interval} seconds...")
        logger.info("Press Ctrl+C to stop monitoring")
        
        try:
            while True:
                current_count = self.get_watching_album_count(watching_album)
                
                if current_count <= self.watermark_threshold:
                    logger.info(f"Watching album now has {current_count} assets (<= {self.watermark_threshold} watermark)")
                    logger.info("Ready to resume adding assets!")
                    return True
                
                logger.info(f"Watching album has {current_count} assets (> {self.watermark_threshold} watermark)")
                logger.info(f"Waiting {check_interval} seconds before next check...")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            return False
    
    def run(self, max_assets=None):
        """Main execution method with continuous watermark-based throttling."""
        logger.info("Starting Apple Photos Watcher Adder utility...")
        logger.info(f"Watermark settings: Max size={self.max_watching_size}, Watermark={self.watermark_threshold}")
        
        # Step 1: Find or create Watching album
        watching_album = self.find_or_create_watching_album()
        if not watching_album:
            logger.error("Could not find or create Watching album. Exiting.")
            return False
        
        # Step 2: Get all photos from library (do this once)
        all_assets = self.get_all_photos()
        if not all_assets:
            logger.error("Could not fetch photos from library. Exiting.")
            return False
        
        total_library_assets = all_assets.count()
        total_processed = 0
        
        # Continuous processing loop
        while total_processed < total_library_assets:
            # Check current Watching album size
            current_count = self.get_watching_album_count(watching_album)
            
            if current_count >= self.max_watching_size:
                logger.warning(f"Watching album has {current_count} assets (>= {self.max_watching_size} max)")
                logger.warning(f"Waiting for album to be processed below {self.watermark_threshold} assets")
                
                # Wait for watermark
                if not self.wait_for_watermark(watching_album):
                    logger.info("Monitoring stopped by user. Exiting.")
                    return True
                
                # Recheck after waiting
                continue
            
            # Calculate how many assets we can safely add
            available_space = self.max_watching_size - current_count
            remaining_assets = total_library_assets - total_processed
            
            if max_assets:
                remaining_limit = max_assets - total_processed
                assets_to_add = min(remaining_limit, available_space, remaining_assets)
            else:
                assets_to_add = min(available_space, remaining_assets)
            
            if assets_to_add <= 0:
                logger.info("No more assets to add")
                break
            
            logger.info(f"Planning to add {assets_to_add} assets (available space: {available_space})")
            
            # Create a subset of assets starting from where we left off
            assets_subset = []
            try:
                with autorelease_pool():
                    for i in range(total_processed, min(total_processed + assets_to_add, total_library_assets)):
                        assets_subset.append(all_assets.objectAtIndex_(i))
            except Exception as e:
                logger.error(f"Error creating asset subset: {e}")
                break
            
            # Add this batch of assets
            success = self.add_subset_to_watching_album(assets_subset, watching_album)
            
            if success:
                total_processed += len(assets_subset)
                logger.info(f"Progress: {total_processed}/{total_library_assets} assets processed")
            else:
                logger.error("Error adding assets batch. Stopping.")
                return False
        
        logger.info("All assets have been processed!")
        logger.info(f"Total assets processed: {total_processed}")
        return True


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
