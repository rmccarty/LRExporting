#!/usr/bin/env python3
"""
Simplified utility script to add images from Apple Photos library to the "Watching" album.

This script:
1. Connects to the Apple Photos library
2. Iterates through all photos/videos
3. Adds them to the "Watching" album in batches
4. Provides progress updates and error handling

All smart category detection and album placement is handled by the Apple Photos Watcher.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import Apple Photos SDK and related modules
try:
    from apple_photos_sdk import ApplePhotos
    from apple_photos_sdk.album import AlbumManager
    from config import APPLE_PHOTOS_WATCHING
    import Photos
    from objc import autorelease_pool
        
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

class SimpleApplePhotosAdder:
    """Simplified utility to add photos from Apple Photos library to the Watching album."""
    
    def __init__(self, batch_size=100, pause_duration=2):
        """Initialize the Simple Apple Photos Adder.
        
        Args:
            batch_size: Number of assets to process before pausing
            pause_duration: Seconds to pause between batches
        """
        self.batch_size = batch_size
        self.pause_duration = pause_duration
        
        self.apple_photos = ApplePhotos()
        self.album_manager = AlbumManager()
        self.watching_album_name = str(APPLE_PHOTOS_WATCHING).rstrip('/')
        
        logger.info(f"Initialized Simple Apple Photos Adder")
        logger.info(f"Batch size: {batch_size}, Pause duration: {pause_duration}s")
        
    def find_or_create_watching_album(self):
        """Find or create the Watching album."""
        try:
            with autorelease_pool():
                logger.info(f"Searching for album: '{self.watching_album_name}'")
                
                # Search for the Watching album
                fetch_options = Photos.PHFetchOptions.alloc().init()
                predicate = Photos.NSPredicate.predicateWithFormat_("localizedTitle == %@", self.watching_album_name)
                fetch_options.setPredicate_(predicate)
                
                album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithType_subtype_options_(
                    Photos.PHAssetCollectionTypeAlbum,
                    Photos.PHAssetCollectionSubtypeAny,
                    fetch_options
                )
                
                if album_result.count() > 0:
                    album = album_result.objectAtIndex_(0)
                    logger.info(f"Found existing album: '{self.watching_album_name}'")
                    return album
                else:
                    # Create the album if it doesn't exist
                    logger.info(f"Album '{self.watching_album_name}' not found, creating it...")
                    success, album_id = self.album_manager.create_album(self.watching_album_name)
                    if success:
                        logger.info(f"Successfully created album: '{self.watching_album_name}'")
                        # Fetch the newly created album
                        album_result = Photos.PHAssetCollection.fetchAssetCollectionsWithLocalIdentifiers_options_([album_id], None)
                        if album_result.count() > 0:
                            return album_result.objectAtIndex_(0)
                    
                    logger.error(f"Failed to create album: '{self.watching_album_name}'")
                    return None
                    
        except Exception as e:
            logger.error(f"Error finding/creating album: {e}")
            return None

    def get_all_photos_batched(self, batch_size=1000):
        """Get all photos from the library, yielding batches for memory efficiency."""
        try:
            with autorelease_pool():
                # Fetch all assets (photos and videos)
                fetch_options = Photos.PHFetchOptions.alloc().init()
                fetch_options.setSortDescriptors_([
                    Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_("creationDate", False)
                ])
                
                all_assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
                total_count = all_assets.count()
                logger.info(f"Found {total_count} total assets in library")
                
                # Process in batches
                for start_idx in range(0, total_count, batch_size):
                    end_idx = min(start_idx + batch_size, total_count)
                    batch_assets = []
                    
                    for i in range(start_idx, end_idx):
                        asset = all_assets.objectAtIndex_(i)
                        batch_assets.append(asset)
                    
                    logger.info(f"Yielding batch {start_idx//batch_size + 1}: assets {start_idx+1}-{end_idx} of {total_count}")
                    yield batch_assets
                    
        except Exception as e:
            logger.error(f"Error fetching photos: {e}")
            yield []

    def add_assets_to_watching_album(self, assets, watching_album):
        """Add assets to the Watching album in batches."""
        if not watching_album or not assets:
            return 0
            
        added_count = 0
        try:
            with autorelease_pool():
                # Add assets to the album using Photos API directly
                success = False
                
                def add_assets():
                    nonlocal success
                    try:
                        # Create change request for the album
                        change_request = Photos.PHAssetCollectionChangeRequest.changeRequestForAssetCollection_(watching_album)
                        if change_request:
                            change_request.addAssets_(assets)
                            success = True
                    except Exception as e:
                        logger.error(f"Error in add_assets change request: {e}")
                        success = False
                
                # Perform the changes
                result, error = Photos.PHPhotoLibrary.sharedPhotoLibrary().performChangesAndWait_error_(
                    add_assets, None
                )
                
                if result and success:
                    added_count = len(assets)
                    logger.info(f"Successfully added {added_count} assets to '{self.watching_album_name}' album")
                else:
                    logger.warning(f"Failed to add assets to '{self.watching_album_name}' album")
                    if error:
                        logger.error(f"Photos API error: {error}")
                    
        except Exception as e:
            logger.error(f"Error adding assets to album: {e}")
            
        return added_count

    def process_entire_library(self, max_assets=None):
        """Process the entire library, adding all assets to the Watching album."""
        logger.info("Starting to process entire Apple Photos library...")
        
        # Find or create the Watching album
        watching_album = self.find_or_create_watching_album()
        if not watching_album:
            logger.error("Could not find or create Watching album. Exiting.")
            return
        
        total_added = 0
        total_processed = 0
        batch_count = 0
        
        try:
            for batch_assets in self.get_all_photos_batched(self.batch_size):
                if not batch_assets:
                    continue
                    
                batch_count += 1
                batch_size = len(batch_assets)
                
                # Check if we've reached the max assets limit
                if max_assets and total_processed + batch_size > max_assets:
                    # Trim the batch to not exceed max_assets
                    remaining = max_assets - total_processed
                    batch_assets = batch_assets[:remaining]
                    batch_size = len(batch_assets)
                
                logger.info(f"Processing batch {batch_count} with {batch_size} assets...")
                
                # Add all assets in this batch to the Watching album
                added_count = self.add_assets_to_watching_album(batch_assets, watching_album)
                
                total_added += added_count
                total_processed += batch_size
                
                logger.info(f"Batch {batch_count} complete: {added_count}/{batch_size} assets added")
                logger.info(f"Total progress: {total_processed} processed, {total_added} added to Watching album")
                
                # Check if we've reached the max assets limit
                if max_assets and total_processed >= max_assets:
                    logger.info(f"Reached maximum asset limit of {max_assets}")
                    break
                
                # Pause between batches to avoid overwhelming the system
                if self.pause_duration > 0:
                    logger.info(f"Pausing for {self.pause_duration} seconds...")
                    time.sleep(self.pause_duration)
                    
        except KeyboardInterrupt:
            logger.info("Process interrupted by user")
        except Exception as e:
            logger.error(f"Error during processing: {e}")
        
        logger.info(f"Processing complete!")
        logger.info(f"Total assets processed: {total_processed}")
        logger.info(f"Total assets added to Watching album: {total_added}")
        logger.info(f"The Apple Photos Watcher will now handle smart album placement based on categories")

    def run(self, max_assets=None):
        """Main execution method."""
        logger.info("=== Simple Apple Photos Adder ===")
        logger.info("This script adds photos to the Watching album for processing by Apple Photos Watcher")
        
        try:
            self.process_entire_library(max_assets)
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)

def main():
    """Main entry point with command line argument support."""
    parser = argparse.ArgumentParser(description='Add Apple Photos library assets to Watching album')
    parser.add_argument('--max-assets', type=int, default=None,
                        help='Maximum number of assets to process (default: all)')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Number of assets to process in each batch (default: 100)')
    parser.add_argument('--pause-duration', type=float, default=2.0,
                        help='Seconds to pause between batches (default: 2.0)')
    
    args = parser.parse_args()
    
    # Create and run the adder
    adder = SimpleApplePhotosAdder(
        batch_size=args.batch_size,
        pause_duration=args.pause_duration
    )
    
    adder.run(max_assets=args.max_assets)

if __name__ == "__main__":
    main()
