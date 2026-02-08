#!/usr/bin/env python3
"""
Upload local-only full-resolution assets from Apple Photos to iCloud.

This program identifies assets in your Apple Photos library that have their
original, full-resolution versions stored only locally and attempts to trigger
their upload to iCloud.

Default behavior: Identifies all local-only assets and triggers upload, oldest first.
"""

import sys
import time
import json
import logging
import argparse
import shutil
import signal
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

import Photos
from Photos import (
    PHAsset,
    PHAssetResource,
    PHAssetResourceManager,
    PHAssetResourceRequestOptions,
    PHAssetChangeRequest,
    PHFetchOptions,
    PHAssetResourceTypePhoto,
    PHAssetResourceTypeVideo,
    PHPhotoLibrary,
    PHObjectChangeDetails,
    PHChange,
)
from objc import autorelease_pool
from Foundation import NSDate, NSError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('apple_upload_originals.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class UploadProgress:
    """Track upload progress and statistics."""

    def __init__(self, state_file: str = ".upload_progress.json"):
        self.state_file = Path(state_file)
        self.triggered_assets = set()
        self.failed_assets = {}
        self.stats = {
            'total_assets': 0,
            'already_in_icloud': 0,
            'local_only': 0,
            'uploads_triggered': 0,
            'failed': 0,
            'start_time': None,
            'last_asset_date': None,
            'last_asset_id': None
        }
        self.load_state()

    def load_state(self):
        """Load progress from state file if it exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.triggered_assets = set(data.get('triggered_assets', []))
                    self.failed_assets = data.get('failed_assets', {})
                    self.stats.update(data.get('stats', {}))
                    logger.info("Resumed progress: %d assets already processed",
                                len(self.triggered_assets))
            except Exception as e:
                logger.error("Error loading state file: %s", e)

    def save_state(self):
        """Save current progress to state file."""
        try:
            data = {
                'triggered_assets': list(self.triggered_assets),
                'failed_assets': self.failed_assets,
                'stats': self.stats,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Error saving state: %s", e)

    def mark_triggered(self, asset_id: str):
        """Mark an asset as having its upload triggered."""
        self.triggered_assets.add(asset_id)
        self.stats['uploads_triggered'] += 1

    def mark_failed(self, asset_id: str, error: str):
        """Mark an asset as failed."""
        self.failed_assets[asset_id] = {
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.stats['failed'] += 1

    def is_processed(self, asset_id: str) -> bool:
        """Check if asset has already been processed."""
        return asset_id in self.triggered_assets or asset_id in self.failed_assets

    def get_elapsed_time(self) -> str:
        """Get formatted elapsed time."""
        if not self.stats['start_time']:
            return "00:00:00"

        start = datetime.fromisoformat(self.stats['start_time'])
        elapsed = datetime.now() - start
        hours, remainder = divmod(elapsed.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class ApplePhotosUploader:
    """Upload local-only assets to iCloud from Apple Photos library."""

    def __init__(self,
                 sort_order: str = "oldest",
                 media_type: str = "all",
                 from_date: Optional[str] = None,
                 limit: Optional[int] = None,
                 dry_run: bool = False,
                 force_sync: bool = False,
                 use_applescript: bool = False,
                 batch_size: int = 10,
                 verify_wait: int = 5):
        
        self.sort_order = sort_order
        self.media_type = media_type
        self.from_date = from_date
        self.limit = limit
        self.dry_run = dry_run
        self.force_sync = force_sync
        self.use_applescript = use_applescript
        self.batch_size = batch_size
        self.verify_wait = verify_wait
        
        self.progress = UploadProgress()
        self.should_stop = False
        self.photo_library = None
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_interrupt)

    def handle_interrupt(self, _signum, _frame):
        """Handle Ctrl+C gracefully."""
        print("\n\n⚠️  Upload process interrupted by user")
        print("💾 Saving progress...")
        self.should_stop = True
        self.progress.save_state()
        print("✅ Progress saved. Run with same parameters to resume.")
        sys.exit(0)

    def is_asset_in_icloud(self, asset) -> bool:
        """
        Check if asset's original is stored in iCloud (not fully local).
        
        An asset is considered "in iCloud" if:
        1. It has resources that would require network access to retrieve
        2. The original resource is not fully cached locally
        """
        try:
            with autorelease_pool():
                resources = PHAssetResource.assetResourcesForAsset_(asset)
                for i in range(resources.count()):
                    resource = resources.objectAtIndex_(i)
                    # Check for original photo or video resource
                    if resource.type() in [
                            PHAssetResourceTypePhoto,
                            PHAssetResourceTypeVideo]:
                        # Check if this resource is NOT fully local
                        if not self._is_resource_local_only(resource):
                            return True
                return False
        except Exception as e:
            logger.error("Error checking asset iCloud status: %s", e)
            return False

    def _is_resource_local_only(self, resource) -> bool:
        """
        Check if a resource is stored only locally (not in iCloud).
        
        Returns True if the resource is fully available locally without needing
        network access, indicating it hasn't been uploaded to iCloud.
        """
        manager = PHAssetResourceManager.defaultManager()
        options = PHAssetResourceRequestOptions.alloc().init()
        options.setNetworkAccessAllowed_(False)

        # Test if we can access the full resource without network
        is_local = [True]
        check_complete = threading.Event()
        bytes_received = [0]
        
        def data_handler(data):
            # If we get substantial data without network, it's local
            if data and data.length() > 0:
                bytes_received[0] += data.length()

        def completion_handler(error):
            if error:
                # Error accessing without network might mean it's in iCloud
                error_desc = str(error.localizedDescription())
                if "network" in error_desc.lower() or "icloud" in error_desc.lower():
                    is_local[0] = False
            check_complete.set()

        # Request data without network access
        request_id = manager.requestDataForAssetResource_options_dataReceivedHandler_completionHandler_(
            resource,
            options,
            data_handler,
            completion_handler
        )
        
        # Wait for check to complete
        check_complete.wait(timeout=5)
        
        # If we got the full resource without network, it's local-only
        # We check if bytes_received is substantial (> 1KB) to confirm it's real data
        return is_local[0] and bytes_received[0] > 1024

    def trigger_upload_with_modification(self, asset) -> bool:
        """
        Trigger upload by making a minor modification to the asset.
        This often causes Photos to sync the asset to iCloud.
        """
        if self.dry_run:
            logger.info("DRY RUN: Would trigger upload via modification")
            return True

        try:
            with autorelease_pool():
                success = [False]
                error_msg = [None]
                
                def perform_changes():
                    try:
                        # Request change access to the asset
                        change_request = PHAssetChangeRequest.changeRequestForAsset_(asset)
                        
                        if change_request:
                            # Toggle the favorite status twice to trigger sync
                            # without leaving a permanent change
                            original_favorite = asset.isFavorite()
                            change_request.setFavorite_(not original_favorite)
                            success[0] = True
                    except Exception as e:
                        error_msg[0] = str(e)
                        success[0] = False

                # Perform the change
                library = PHPhotoLibrary.sharedPhotoLibrary()
                completion_event = threading.Event()
                
                def completion_handler(success_val, error):
                    if error:
                        error_msg[0] = str(error.localizedDescription())
                        success[0] = False
                    else:
                        success[0] = success_val
                    completion_event.set()
                
                library.performChanges_completionHandler_(
                    perform_changes,
                    completion_handler
                )
                
                # Wait for completion
                completion_event.wait(timeout=10)
                
                if success[0]:
                    # Revert the change
                    def revert_changes():
                        try:
                            change_request = PHAssetChangeRequest.changeRequestForAsset_(asset)
                            if change_request:
                                original_favorite = asset.isFavorite()
                                change_request.setFavorite_(not original_favorite)
                        except:
                            pass
                    
                    revert_event = threading.Event()
                    
                    def revert_completion(success_val, error):
                        revert_event.set()
                    
                    library.performChanges_completionHandler_(
                        revert_changes,
                        revert_completion
                    )
                    
                    revert_event.wait(timeout=5)
                    
                    logger.info("Successfully triggered upload via modification")
                    return True
                else:
                    logger.error("Failed to modify asset: %s", error_msg[0])
                    return False
                    
        except Exception as e:
            logger.error("Error triggering upload via modification: %s", e)
            return False

    def trigger_upload_with_applescript(self, asset_ids: List[str]) -> bool:
        """
        Use AppleScript to interact with Photos app and potentially trigger sync.
        This method works on batches of assets.
        """
        if self.dry_run:
            logger.info("DRY RUN: Would trigger upload via AppleScript for %d assets", len(asset_ids))
            return True

        try:
            # Create AppleScript to select assets and trigger sync
            script = '''
            tell application "Photos"
                activate
                delay 1
                
                -- Try to trigger sync by opening and closing the Photos preferences
                tell application "System Events"
                    tell process "Photos"
                        keystroke "," using command down
                        delay 2
                        click button "iCloud" of toolbar 1 of window "Photos Preferences"
                        delay 1
                        click button 1 of window "Photos Preferences"
                    end tell
                end tell
            end tell
            '''
            
            # Run the AppleScript
            process = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if process.returncode == 0:
                logger.info("Successfully triggered Photos sync via AppleScript")
                return True
            else:
                logger.error("AppleScript failed: %s", process.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("AppleScript timed out")
            return False
        except Exception as e:
            logger.error("Error running AppleScript: %s", e)
            return False

    def force_photos_sync(self) -> bool:
        """
        Force Photos app to sync with iCloud using various methods.
        """
        if self.dry_run:
            logger.info("DRY RUN: Would force Photos sync")
            return True

        try:
            # Method 1: Kill and restart photoanalysisd (triggers sync)
            logger.info("Restarting photo analysis daemon to trigger sync...")
            subprocess.run(['killall', 'photoanalysisd'], capture_output=True)
            time.sleep(2)
            
            # Method 2: Kill and restart cloudd (iCloud daemon)
            logger.info("Restarting iCloud daemon...")
            subprocess.run(['killall', 'cloudd'], capture_output=True)
            time.sleep(2)
            
            # Method 3: Trigger Photos app to open (often triggers sync)
            logger.info("Opening Photos app to trigger sync...")
            subprocess.run(['open', '-a', 'Photos'], capture_output=True)
            time.sleep(5)
            
            return True
            
        except Exception as e:
            logger.error("Error forcing Photos sync: %s", e)
            return False

    def get_all_assets(self):
        """Fetch all assets from the library based on filters."""
        try:
            with autorelease_pool():
                fetch_options = PHFetchOptions.alloc().init()
                
                # Setup sort order
                if self.sort_order == "oldest":
                    fetch_options.setSortDescriptors_([
                        Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_(
                            "creationDate", True)
                    ])
                elif self.sort_order == "newest":
                    fetch_options.setSortDescriptors_([
                        Photos.NSSortDescriptor.sortDescriptorWithKey_ascending_(
                            "creationDate", False)
                    ])
                
                # Apply media type filter if specified
                if self.media_type == "photo":
                    fetch_options.setPredicate_(
                        Photos.NSPredicate.predicateWithFormat_(
                            "mediaType == %d", Photos.PHAssetMediaTypeImage)
                    )
                elif self.media_type == "video":
                    fetch_options.setPredicate_(
                        Photos.NSPredicate.predicateWithFormat_(
                            "mediaType == %d", Photos.PHAssetMediaTypeVideo)
                    )
                
                # Fetch assets
                assets = PHAsset.fetchAssetsWithOptions_(fetch_options)
                return assets

        except Exception as e:
            logger.error("Error fetching assets: %s", e)
            return None

    def format_asset_info(self, asset, index: int, total: int) -> str:
        """Format asset information for display."""
        creation_date = asset.creationDate()
        date_str = creation_date.descriptionWithLocale_(None)[:10] if creation_date else "Unknown"
        
        media_type = "Photo" if asset.mediaType() == Photos.PHAssetMediaTypeImage else "Video"
        
        # Calculate age
        if creation_date:
            age = datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")
            years = age.days // 365
            age_str = f"({years} years old)" if years > 0 else "(recent)"
        else:
            age_str = ""
        
        # Get pixel dimensions
        width = asset.pixelWidth()
        height = asset.pixelHeight()
        
        return f"[{date_str}] {media_type} {width}x{height} {index}/{total} {age_str}"

    def process_assets(self, assets, assets_to_process: int):
        """Process assets and trigger uploads for local-only items."""
        
        local_only_count = 0
        already_in_icloud_count = 0
        triggered_count = 0
        failed_count = 0
        batch_assets = []
        
        for i in range(assets_to_process):
            if self.should_stop:
                break
            
            # Handle both list and PHFetchResult types
            if isinstance(assets, list):
                asset = assets[i]
            else:
                asset = assets.objectAtIndex_(i)
            asset_id = asset.localIdentifier()
            
            # Skip if already processed
            if self.progress.is_processed(asset_id):
                continue
            
            # Display progress every 100 assets
            if i % 100 == 0:
                print(f"Checking asset {i+1}/{assets_to_process}...")
            
            # Check if asset is already in iCloud
            if self.is_asset_in_icloud(asset):
                already_in_icloud_count += 1
                self.progress.stats['already_in_icloud'] = already_in_icloud_count
                continue
            
            # This is a local-only asset
            local_only_count += 1
            self.progress.stats['local_only'] = local_only_count
            
            # Display asset info
            asset_info = self.format_asset_info(asset, local_only_count, self.progress.stats['local_only'])
            print(f"\n📱 Local-only asset found: {asset_info}")
            
            # Add to batch for processing
            batch_assets.append(asset)
            
            # Process batch when full
            if len(batch_assets) >= self.batch_size:
                success = self.process_batch(batch_assets)
                if success:
                    triggered_count += len(batch_assets)
                    for batch_asset in batch_assets:
                        self.progress.mark_triggered(batch_asset.localIdentifier())
                else:
                    failed_count += len(batch_assets)
                    for batch_asset in batch_assets:
                        self.progress.mark_failed(
                            batch_asset.localIdentifier(), 
                            "Failed to trigger upload"
                        )
                batch_assets = []
                
                # Save progress periodically
                self.progress.save_state()
        
        # Process remaining assets in final batch
        if batch_assets:
            success = self.process_batch(batch_assets)
            if success:
                triggered_count += len(batch_assets)
                for batch_asset in batch_assets:
                    self.progress.mark_triggered(batch_asset.localIdentifier())
            else:
                failed_count += len(batch_assets)
                for batch_asset in batch_assets:
                    self.progress.mark_failed(
                        batch_asset.localIdentifier(),
                        "Failed to trigger upload"
                    )
        
        return local_only_count, already_in_icloud_count, triggered_count, failed_count

    def process_batch(self, assets: List) -> bool:
        """Process a batch of assets to trigger upload."""
        
        if not assets:
            return True
        
        print(f"🔄 Processing batch of {len(assets)} assets...")
        
        success = False
        
        # Try different methods to trigger upload
        if self.use_applescript:
            # Use AppleScript method
            asset_ids = [asset.localIdentifier() for asset in assets]
            success = self.trigger_upload_with_applescript(asset_ids)
        
        if not success:
            # Try modification method for each asset
            for asset in assets:
                if self.trigger_upload_with_modification(asset):
                    success = True
                time.sleep(0.5)  # Small delay between modifications
        
        if success and self.force_sync:
            # Force a sync after processing batch
            print("⚡ Forcing Photos sync...")
            self.force_photos_sync()
        
        # Verify upload status after triggering
        if success and not self.dry_run:
            print(f"🔍 Verifying upload status (waiting {self.verify_wait}s)...")
            time.sleep(self.verify_wait)  # Give Photos some time to start the upload
            
            successfully_uploaded = []
            still_local = []
            
            for asset in assets:
                if self.is_asset_in_icloud(asset):
                    successfully_uploaded.append(asset)
                    print(f"  ✅ Asset uploaded to iCloud: {asset.localIdentifier()[:8]}...")
                else:
                    still_local.append(asset)
                    print(f"  ⏳ Asset still local (may upload later): {asset.localIdentifier()[:8]}...")
            
            if successfully_uploaded:
                print(f"  📊 {len(successfully_uploaded)}/{len(assets)} assets confirmed in iCloud")
            if still_local:
                print(f"  ⚠️  {len(still_local)} assets still uploading or queued")
        
        return success

    def print_summary(self):
        """Print final summary statistics."""
        print("\n" + "=" * 60)
        print("UPLOAD TRIGGER SUMMARY")
        print("=" * 60)
        print(f"Total assets in library: {self.progress.stats['total_assets']}")
        print(f"Already in iCloud: {self.progress.stats['already_in_icloud']}")
        print(f"Local-only assets found: {self.progress.stats['local_only']}")
        print(f"Upload triggers sent: {self.progress.stats['uploads_triggered']}")
        print(f"Failed triggers: {self.progress.stats['failed']}")
        print(f"Time elapsed: {self.progress.get_elapsed_time()}")
        
        if self.progress.stats['local_only'] > 0:
            print("\n⚠️  Note: Upload may take time depending on:")
            print("   • iCloud storage availability")
            print("   • Network speed and stability")
            print("   • System iCloud Photos settings")
            print("   • Background processing by Photos app")
            print("\n💡 Tip: Keep Photos app open to speed up upload")
            print("   You can monitor upload progress in Photos > Preferences > iCloud")
        
        print("=" * 60)

    def run(self):
        """Main execution method."""
        print("Apple Photos iCloud Upload Trigger")
        print("=" * 35)
        
        # Set start time if not resuming
        if not self.progress.stats['start_time']:
            self.progress.stats['start_time'] = datetime.now().isoformat()
        
        # Initialize Photos library
        print("Initializing Photos library...")
        self.photo_library = PHPhotoLibrary.sharedPhotoLibrary()
        
        # Fetch all assets
        print("Fetching assets from library...")
        assets = self.get_all_assets()
        
        if not assets:
            print("❌ Could not fetch assets from library")
            return False
        
        # Handle both list and PHFetchResult types
        if isinstance(assets, list):
            total_assets = len(assets)
        else:
            total_assets = assets.count()
        self.progress.stats['total_assets'] = total_assets
        
        print(f"Total assets: {total_assets}")
        print(f"Sort order: {self.sort_order}")
        
        if self.dry_run:
            print("\n🔍 DRY RUN MODE - No uploads will be triggered")
        
        # Check if resuming
        if self.progress.triggered_assets:
            print(f"📂 Resuming from previous session ({len(self.progress.triggered_assets)} already processed)")
        
        print("\nScanning for local-only assets...")
        print("-" * 40)
        
        # Process assets
        assets_to_process = min(total_assets, self.limit) if self.limit else total_assets
        local_only, already_in_icloud, triggered, failed = self.process_assets(assets, assets_to_process)
        
        print(f"\n📊 Processing complete:")
        print(f"   Local-only found: {local_only}")
        print(f"   Already in iCloud: {already_in_icloud}")
        print(f"   Uploads triggered: {triggered}")
        print(f"   Failed: {failed}")
        
        # Save final state
        self.progress.save_state()
        
        # Print summary
        self.print_summary()
        
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trigger upload of local-only Apple Photos assets to iCloud",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        # Find and upload all local-only assets
  %(prog)s --sort newest          # Process newest assets first
  %(prog)s --media-type photo     # Upload only photos
  %(prog)s --limit 100            # Process first 100 assets
  %(prog)s --dry-run              # Show what would be uploaded
  %(prog)s --force-sync           # Force Photos sync after each batch
  %(prog)s --use-applescript      # Use AppleScript method for triggering
  %(prog)s --batch-size 20        # Process 20 assets at a time
        """
    )
    
    parser.add_argument(
        "--sort",
        choices=["oldest", "newest"],
        default="newest",
        help="Sort order for processing (default: newest)"
    )
    
    parser.add_argument(
        "--media-type",
        choices=["all", "photo", "video"],
        default="all",
        help="Type of media to process (default: all)"
    )
    
    parser.add_argument(
        "--from-date",
        type=str,
        help="Start processing from this date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of assets to process"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually triggering"
    )
    
    parser.add_argument(
        "--force-sync",
        action="store_true",
        help="Force Photos app to sync after processing batches"
    )
    
    parser.add_argument(
        "--use-applescript",
        action="store_true",
        help="Use AppleScript to trigger uploads (may open Photos app)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of assets to process in each batch (default: 10)"
    )
    
    parser.add_argument(
        "--verify-wait",
        type=int,
        default=5,
        help="Seconds to wait before verifying upload status (default: 5)"
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous interrupted session"
    )
    
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset progress and start fresh"
    )
    
    args = parser.parse_args()
    
    # Reset progress if requested
    if args.reset:
        progress_file = Path(".upload_progress.json")
        if progress_file.exists():
            progress_file.unlink()
            print("✅ Progress reset")
    
    # Create uploader and run
    uploader = ApplePhotosUploader(
        sort_order=args.sort,
        media_type=args.media_type,
        from_date=args.from_date,
        limit=args.limit,
        dry_run=args.dry_run,
        force_sync=args.force_sync,
        use_applescript=args.use_applescript,
        batch_size=args.batch_size,
        verify_wait=args.verify_wait
    )
    
    try:
        success = uploader.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()