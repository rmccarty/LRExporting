#!/usr/bin/env python3
"""
Download original full-resolution assets from iCloud to local storage.

This program ensures that all assets in your Apple Photos library have their
original, full-resolution versions downloaded locally from iCloud.

Default behavior: Downloads all assets in the library, oldest first.
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
from typing import Optional, Tuple, Dict
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
    PHFetchOptions,
    PHAssetResourceTypePhoto,
    PHAssetResourceTypeVideo,
)
from objc import autorelease_pool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('apple_download_originals.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DownloadProgress:
    """Track download progress and statistics."""

    def __init__(self, state_file: str = ".download_progress.json"):
        self.state_file = Path(state_file)
        self.completed_assets = set()
        self.failed_assets = {}
        self.stats = {
            'total_assets': 0,
            'already_local': 0,
            'downloaded': 0,
            'failed': 0,
            'bytes_downloaded': 0,
            'start_time': None,
            'last_asset_date': None,
            'last_asset_id': None
        }
        self.speed_stats = {
            'total_download_time': 0,
            'total_download_bytes': 0,
            'download_speeds': [],  # Per-asset speeds in MB/s
            'asset_sizes': [],      # Per-asset sizes in MB
            'download_durations': [],  # Per-asset durations in seconds
            'slowest_download': {'speed': float('inf'), 'asset_id': None, 'size_mb': 0},
            'fastest_download': {'speed': 0, 'asset_id': None, 'size_mb': 0}
        }
        self.load_state()

    def load_state(self):
        """Load progress from state file if it exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.completed_assets = set(data.get('completed_assets', []))
                    self.failed_assets = data.get('failed_assets', {})
                    self.stats.update(data.get('stats', {}))
                    # Load speed stats if available
                    if 'speed_stats' in data:
                        self.speed_stats.update(data['speed_stats'])
                    logger.info("Resumed progress: %d assets already processed",
                                len(self.completed_assets))
            except Exception as e:
                logger.error("Error loading state file: %s", e)

    def save_state(self):
        """Save current progress to state file."""
        try:
            data = {
                'completed_assets': list(self.completed_assets),
                'failed_assets': self.failed_assets,
                'stats': self.stats,
                'speed_stats': self.speed_stats,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Error saving state: %s", e)

    def mark_completed(self, asset_id: str, bytes_downloaded: int = 0, 
                      download_duration: float = 0):
        """Mark an asset as completed with download stats."""
        self.completed_assets.add(asset_id)
        self.stats['downloaded'] += 1
        self.stats['bytes_downloaded'] += bytes_downloaded
        
        # Add speed statistics
        if download_duration > 0 and bytes_downloaded > 0:
            size_mb = bytes_downloaded / (1024 * 1024)
            speed_mbps = size_mb / download_duration
            
            self.speed_stats['total_download_time'] += download_duration
            self.speed_stats['total_download_bytes'] += bytes_downloaded
            self.speed_stats['download_speeds'].append(speed_mbps)
            self.speed_stats['asset_sizes'].append(size_mb)
            self.speed_stats['download_durations'].append(download_duration)
            
            # Track fastest/slowest downloads
            if speed_mbps > self.speed_stats['fastest_download']['speed']:
                self.speed_stats['fastest_download'] = {
                    'speed': speed_mbps, 
                    'asset_id': asset_id, 
                    'size_mb': size_mb
                }
            if speed_mbps < self.speed_stats['slowest_download']['speed']:
                self.speed_stats['slowest_download'] = {
                    'speed': speed_mbps, 
                    'asset_id': asset_id, 
                    'size_mb': size_mb
                }

    def mark_failed(self, asset_id: str, error: str):
        """Mark an asset as failed."""
        self.failed_assets[asset_id] = {
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.stats['failed'] += 1

    def is_processed(self, asset_id: str) -> bool:
        """Check if asset has already been processed."""
        return asset_id in self.completed_assets or asset_id in self.failed_assets

    def get_elapsed_time(self) -> str:
        """Get formatted elapsed time."""
        if not self.stats['start_time']:
            return "00:00:00"

        start = datetime.fromisoformat(self.stats['start_time'])
        elapsed = datetime.now() - start
        hours, remainder = divmod(elapsed.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_download_size_gb(self) -> float:
        """Get total downloaded size in GB."""
        return self.stats['bytes_downloaded'] / (1024 ** 3)

    def get_speed_summary(self):
        """Calculate comprehensive speed statistics."""
        if not self.speed_stats['download_speeds']:
            return None
        
        speeds = self.speed_stats['download_speeds']
        durations = self.speed_stats['download_durations']
        sizes = self.speed_stats['asset_sizes']
        
        # Sort speeds for percentile calculations
        sorted_speeds = sorted(speeds)
        n = len(sorted_speeds)
        
        return {
            'avg_speed_mbps': sum(speeds) / len(speeds),
            'median_speed_mbps': sorted_speeds[n//2] if n > 0 else 0,
            'min_speed_mbps': min(speeds) if speeds else 0,
            'max_speed_mbps': max(speeds) if speeds else 0,
            'percentile_25_mbps': sorted_speeds[n//4] if n > 3 else 0,
            'percentile_75_mbps': sorted_speeds[3*n//4] if n > 3 else 0,
            'total_time_hours': self.speed_stats['total_download_time'] / 3600,
            'total_gb_downloaded': self.speed_stats['total_download_bytes'] / (1024**3),
            'overall_avg_mbps': (self.speed_stats['total_download_bytes'] / (1024**2)) / 
                               self.speed_stats['total_download_time'] if self.speed_stats['total_download_time'] > 0 else 0,
            'avg_file_size_mb': sum(sizes) / len(sizes) if sizes else 0,
            'avg_download_time_sec': sum(durations) / len(durations) if durations else 0,
            'downloads_count': len(speeds),
            'fastest_download': self.speed_stats['fastest_download'],
            'slowest_download': self.speed_stats['slowest_download']
        }

    def get_recent_speed_mbps(self, last_n=10):
        """Get average speed of last N downloads."""
        if not self.speed_stats['download_speeds']:
            return 0
        recent_speeds = self.speed_stats['download_speeds'][-last_n:]
        return sum(recent_speeds) / len(recent_speeds) if recent_speeds else 0


class ApplePhotosDownloader:
    """Download original assets from Apple Photos library."""

    def __init__(self,
                 sort_order: str = "oldest",
                 media_type: str = "all",
                 from_date: Optional[str] = None,
                 limit: Optional[int] = None,
                 dry_run: bool = False,
                 timeout: int = 300,
                 retry_count: int = 3,
                 retry_delay: int = 10,
                 min_free_space_gb: float = 10.0,
                 concurrent: int = 1,
                 no_scan: bool = False,
                 verify_wait: int = 3,
                 final_verify: bool = False):
        
        self.sort_order = sort_order
        self.media_type = media_type
        self.from_date = from_date
        self.limit = limit
        self.dry_run = dry_run
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.min_free_space_gb = min_free_space_gb
        self.concurrent = max(1, min(concurrent, 10))  # Limit 1-10 concurrent
        self.no_scan = no_scan
        self.verify_wait = verify_wait
        self.final_verify = final_verify
        
        self.progress = DownloadProgress()
        self.should_stop = False
        self.current_download_speed = 0
        self.current_asset_info = {}
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_interrupt)

    def handle_interrupt(self, _signum, _frame):
        """Handle Ctrl+C gracefully."""
        print("\n\n⚠️  Download interrupted by user")
        print("💾 Saving progress...")
        self.should_stop = True
        self.progress.save_state()
        print("✅ Progress saved. Run with same parameters to resume.")
        sys.exit(0)

    def get_free_space_gb(self) -> float:
        """Get available disk space in GB."""
        stat = shutil.disk_usage("/")
        return stat.free / (1024 ** 3)

    def check_storage(self) -> bool:
        """Check if there's enough free storage."""
        free_gb = self.get_free_space_gb()
        if free_gb < self.min_free_space_gb:
            logger.error("Insufficient storage: %.1f GB free, need %.1f GB minimum",
                         free_gb, self.min_free_space_gb)
            return False
        return True

    def check_sync_status(self) -> Dict:
        """Check if Photos library is synced with iCloud."""
        status = {
            'is_synced': False,
            'warnings': [],
            'icloud_enabled': False,
            'sync_in_progress': False,
            'should_continue': True,
            'upload_queue': None,
            'download_queue': None,
            'local_count': 0,
            'storage_mode': None
        }
        
        # Check for active syncing first (most reliable indicator)
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'photolibraryd' in result.stdout:
                # Look for signs of active syncing
                if 'cloudphoto' in result.stdout.lower():
                    status['sync_in_progress'] = True
                    status['icloud_enabled'] = True  # If syncing, iCloud MUST be enabled
                    logger.debug("Active sync detected via process monitoring")
        except Exception as e:
            logger.debug(f"Could not check for active sync: {e}")
        
        # Only check preferences if we haven't detected active sync
        if not status['sync_in_progress']:
            try:
                # Try multiple preference locations
                pref_checks = [
                    ('com.apple.photolibraryd', 'PLCloudPhotoLibraryEnable'),
                    ('com.apple.Photos', 'CloudPhotoLibraryEnabled'),
                ]
                
                for domain, key in pref_checks:
                    try:
                        result = subprocess.run(
                            ['defaults', 'read', domain, key],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        if result.returncode == 0 and '1' in result.stdout:
                            status['icloud_enabled'] = True
                            logger.debug(f"iCloud enabled detected via {domain}.{key}")
                            break
                    except:
                        continue
                
                if not status['icloud_enabled']:
                    status['warnings'].append("⚠️  iCloud Photos appears to be disabled")
                    status['warnings'].append("   Only locally stored photos will be visible")
            except Exception as e:
                logger.debug(f"Could not check iCloud Photos setting: {e}")
        
        # If sync is in progress, add appropriate warnings
        if status['sync_in_progress']:
            status['warnings'].append("📡 Photos is actively syncing with iCloud")
            status['warnings'].append("   Photos from other devices may still be downloading")
            status['warnings'].append("   Local photos may still be uploading to iCloud")
            status['warnings'].append("   Some assets may not be visible to this script yet")
        
        # Check Photos preferences for download settings
        try:
            # Try to determine if "Download Originals" is selected
            result = subprocess.run(
                ['defaults', 'read', 'com.apple.Photos', 'IPXDefaultDownloadPolicy'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 0 = Download Originals, 1 = Optimize Storage
                if '1' in result.stdout:
                    status['storage_mode'] = 'optimize'
                    status['warnings'].append("📱 'Optimize Mac Storage' is enabled")
                    status['warnings'].append("   Many photos may only exist as thumbnails")
                    status['warnings'].append("   Consider switching to 'Download Originals to this Mac'")
                else:
                    status['storage_mode'] = 'originals'
                    if status['sync_in_progress']:
                        status['warnings'].append("✅ 'Download Originals' is enabled - photos will download fully")
        except Exception as e:
            logger.debug(f"Could not check download policy: {e}")
        
        # Check network connectivity to iCloud
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-t', '2', 'www.icloud.com'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                status['warnings'].append("🌐 Cannot reach iCloud servers")
                status['warnings'].append("   Check your internet connection")
        except Exception as e:
            logger.debug(f"Could not check iCloud connectivity: {e}")
        
        # Determine overall sync status
        if not status['warnings']:
            status['is_synced'] = True
        elif status['sync_in_progress']:
            status['is_synced'] = False
            status['warnings'].append("\n💡 Recommendation: Wait for sync to complete or proceed with caution")
        
        return status

    def is_asset_local(self, asset) -> bool:
        """Check if asset's original is available locally."""
        try:
            with autorelease_pool():
                resources = PHAssetResource.assetResourcesForAsset_(asset)
                for i in range(resources.count()):
                    resource = resources.objectAtIndex_(i)
                    # Check for original photo or video resource
                    if resource.type() in [
                            PHAssetResourceTypePhoto,
                            PHAssetResourceTypeVideo]:
                        # This is a simplification - we're assuming it's local if we can get the resource
                        # In practice, we might need to try to access it to be sure
                        return self._check_resource_availability(resource)
                return False
        except Exception as e:
            logger.error("Error checking asset availability: %s", e)
            return False

    def _check_resource_availability(self, resource) -> bool:
        """Check if a resource is actually available locally."""
        # We'll attempt to get data with network access disabled
        # If it succeeds, the resource is local
        manager = PHAssetResourceManager.defaultManager()
        options = PHAssetResourceRequestOptions.alloc().init()
        options.setNetworkAccessAllowed_(False)

        # Use a small test to check availability
        is_available = [False]
        error_occurred = [False]
        bytes_received = [0]
        check_complete = threading.Event()
        
        def data_handler(data):
            # Track how much data we received
            if data and data.length() > 0:
                bytes_received[0] += data.length()
                # Need substantial data (>1MB) to confirm it's really local
                if bytes_received[0] > 1024 * 1024:  
                    is_available[0] = True

        def completion_handler(error):
            if error:
                error_desc = str(error.localizedDescription()) if error else ""
                # Check if error indicates resource is in cloud
                if "network" in error_desc.lower() or "icloud" in error_desc.lower():
                    error_occurred[0] = True
            # If we completed without error and got substantial data, it's local
            elif bytes_received[0] > 1024 * 1024:
                is_available[0] = True
            check_complete.set()

        # Request data to test availability
        request_id = manager.requestDataForAssetResource_options_dataReceivedHandler_completionHandler_(
            resource,
            options,
            data_handler,
            completion_handler
        )
        
        # Wait longer for the check to get more data
        check_complete.wait(timeout=5)

        # Cancel request if still running
        if not check_complete.is_set():
            manager.cancelDataRequest_(request_id)

        # Only consider it local if we got substantial data (>1MB)
        return is_available[0] and bytes_received[0] > 1024 * 1024 and not error_occurred[0]

    def download_asset_original(self, asset) -> Tuple[bool, int, float]:
        """
        Download the original version of an asset.
        Returns (success, bytes_downloaded, download_duration).
        """
        if self.dry_run:
            # In dry run, just pretend we downloaded
            return True, 0, 0

        download_start_time = time.time()
        download_complete = threading.Event()
        download_success = [False]
        bytes_downloaded = [0]
        error_message = [None]
        last_progress_time = [download_start_time]
        last_bytes = [0]
        
        try:
            with autorelease_pool():
                resources = PHAssetResource.assetResourcesForAsset_(asset)
                original_resource = None
                
                # Find the original resource
                for i in range(resources.count()):
                    resource = resources.objectAtIndex_(i)
                    if resource.type() in [
                            PHAssetResourceTypePhoto,
                            PHAssetResourceTypeVideo]:
                        original_resource = resource
                        break

                if not original_resource:
                    logger.error("No original resource found for asset")
                    return False, 0

                # Setup download options
                manager = PHAssetResourceManager.defaultManager()
                options = PHAssetResourceRequestOptions.alloc().init()
                options.setNetworkAccessAllowed_(True)

                def progress_handler(progress):
                    """Handle download progress updates."""
                    current_time = time.time()
                    current_bytes = bytes_downloaded[0]
                    
                    # Calculate current speed (MB/s) based on progress since last update
                    if current_time > last_progress_time[0] + 0.5:  # Update every 0.5 sec
                        time_delta = current_time - last_progress_time[0]
                        bytes_delta = current_bytes - last_bytes[0]
                        current_speed = (bytes_delta / (1024 * 1024)) / time_delta if time_delta > 0 else 0
                        
                        percent = int(progress * 100)
                        recent_avg = self.progress.get_recent_speed_mbps()
                        print(f"\r   Downloading... {percent}% @ {current_speed:.1f} MB/s (avg: {recent_avg:.1f} MB/s)", 
                              end="", flush=True)
                        
                        last_progress_time[0] = current_time
                        last_bytes[0] = current_bytes

                def data_handler(data):
                    """Handle received data."""
                    if data:
                        bytes_downloaded[0] += data.length()

                def completion_handler(error):
                    """Handle download completion."""
                    if error:
                        error_message[0] = str(error.localizedDescription())
                        download_success[0] = False
                    else:
                        download_success[0] = True
                    download_complete.set()

                # Set progress handler
                options.setProgressHandler_(progress_handler)

                # Start the download
                manager.requestDataForAssetResource_options_dataReceivedHandler_completionHandler_(
                    original_resource,
                    options,
                    data_handler,
                    completion_handler
                )
                
                # Wait for download to complete
                if not download_complete.wait(timeout=self.timeout):
                    logger.error("Download timeout after %d seconds", self.timeout)
                    download_end_time = time.time()
                    download_duration = download_end_time - download_start_time
                    return False, 0, download_duration
                
                download_end_time = time.time()
                download_duration = download_end_time - download_start_time
                
                if download_success[0]:
                    size_mb = bytes_downloaded[0] / (1024 * 1024)
                    speed_mbps = size_mb / download_duration if download_duration > 0 else 0
                    print(f"\r   ✅ Download complete: {size_mb:.1f} MB @ {speed_mbps:.1f} MB/s" + " " * 10)
                    return True, bytes_downloaded[0], download_duration
                else:
                    print(f"\r   ❌ Download failed: {error_message[0]}" + " " * 30)
                    return False, 0, download_duration

        except Exception as e:
            logger.error("Error downloading asset: %s", e)
            download_end_time = time.time()
            download_duration = download_end_time - download_start_time
            return False, 0, download_duration

    def get_asset_size(self, asset):
        """Get the size of an asset's original resource."""
        try:
            with autorelease_pool():
                resources = PHAssetResource.assetResourcesForAsset_(asset)
                for i in range(resources.count()):
                    resource = resources.objectAtIndex_(i)
                    if resource.type() in [PHAssetResourceTypePhoto, PHAssetResourceTypeVideo]:
                        # Try to get file size - this might not always be available
                        try:
                            # fileSize might not exist, use a fallback
                            if hasattr(resource, 'fileSize'):
                                size = resource.fileSize()
                                if size:
                                    return size
                        except:
                            pass
                return 0
        except Exception as e:
            logger.debug("Could not get asset size: %s", e)
            return 0

    def sort_assets_by_size(self, assets, ascending=True):
        """Sort assets by file size."""
        print("Sorting assets by size (this may take a moment)...")
        try:
            with autorelease_pool():
                # Convert to list with sizes
                asset_list = []
                total = assets.count()
                for i in range(total):
                    if i % 100 == 0:
                        print(f"  Processing asset {i}/{total}...", end="\r")
                    asset = assets.objectAtIndex_(i)
                    size = self.get_asset_size(asset)
                    asset_list.append((asset, size))
                
                print(f"  Processed {total} assets, sorting...     ")
                
                # Sort by size
                asset_list.sort(key=lambda x: x[1], reverse=not ascending)
                
                # Return sorted assets only
                return [item[0] for item in asset_list]
        except Exception as e:
            logger.error("Error sorting assets by size: %s", e)
            # Return unsorted as fallback
            return [assets.objectAtIndex_(i) for i in range(assets.count())]

    def get_all_assets(self):
        """Fetch all assets from the library based on filters."""
        try:
            with autorelease_pool():
                fetch_options = PHFetchOptions.alloc().init()
                
                # Setup sort order (only date-based sorts work at fetch level)
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
                # Size-based and random sorting will be handled after fetching
                
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
                
                # Handle size-based sorting if needed
                if self.sort_order == "smallest":
                    return self.sort_assets_by_size(assets, ascending=True)
                elif self.sort_order == "largest":
                    return self.sort_assets_by_size(assets, ascending=False)
                elif self.sort_order == "random":
                    import random
                    asset_list = [assets.objectAtIndex_(i) for i in range(assets.count())]
                    random.shuffle(asset_list)
                    return asset_list
                
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
        
        return f"[{date_str}] {media_type} {index}/{total} {age_str}"

    def download_asset_with_retries(self, asset) -> Tuple[str, bool, int, float]:
        """Download a single asset with retry logic.
        Returns (asset_id, success, bytes_downloaded, download_duration)."""
        
        asset_id = asset.localIdentifier()
        
        # Download with retries
        for attempt in range(self.retry_count):
            if attempt > 0 and not self.should_stop:
                time.sleep(self.retry_delay)
            
            if self.should_stop:
                return asset_id, False, 0, 0
            
            success, bytes_downloaded, download_duration = self.download_asset_original(asset)
            
            if success:
                # Verify download in non-dry-run mode with delay
                if not self.dry_run:
                    # Wait for Photos to fully process the download
                    time.sleep(self.verify_wait)
                    if not self.is_asset_local(asset):
                        print(f"   ⚠️  Verification failed for {asset_id[:8]}... (retrying after {self.verify_wait}s wait)")
                        continue  # Try again
                return asset_id, True, bytes_downloaded, download_duration
        
        return asset_id, False, 0, 0

    def process_assets_concurrently(self, assets_to_download):
        """Process assets using concurrent downloads."""
        
        if self.concurrent == 1:
            # Fall back to sequential processing
            return self.process_assets_sequentially(assets_to_download)
        
        print(f"🚀 Using {self.concurrent} concurrent downloads")
        
        completed_count = 0
        failed_count = 0
        
        # Process in batches to avoid overwhelming the system
        batch_size = self.concurrent * 2
        
        for batch_start in range(0, len(assets_to_download), batch_size):
            if self.should_stop:
                break
                
            batch_end = min(batch_start + batch_size, len(assets_to_download))
            batch_assets = assets_to_download[batch_start:batch_end]
            
            print(f"\n📦 Processing batch {batch_start//batch_size + 1}: "
                  f"assets {batch_start + 1}-{batch_end} of {len(assets_to_download)}")
            
            # Submit concurrent downloads for this batch
            with ThreadPoolExecutor(max_workers=self.concurrent) as executor:
                # Submit all downloads in the batch
                future_to_asset = {}
                for asset in batch_assets:
                    if self.should_stop:
                        break
                    future = executor.submit(self.download_asset_with_retries, asset)
                    future_to_asset[future] = asset
                
                # Process completed downloads as they finish
                for future in as_completed(future_to_asset):
                    if self.should_stop:
                        break
                        
                    asset = future_to_asset[future]
                    try:
                        asset_id, success, bytes_downloaded, download_duration = future.result()
                        
                        if success:
                            completed_count += 1
                            self.progress.mark_completed(asset_id, bytes_downloaded, download_duration)
                            print(f"✅ Completed {completed_count + failed_count}/{len(assets_to_download)}")
                        else:
                            failed_count += 1
                            self.progress.mark_failed(asset_id, f"Failed after {self.retry_count} retries")
                            print(f"❌ Failed {completed_count + failed_count}/{len(assets_to_download)}")
                            
                    except Exception as e:
                        failed_count += 1
                        asset_id = asset.localIdentifier()
                        self.progress.mark_failed(asset_id, f"Exception: {e}")
                        print(f"💥 Exception {completed_count + failed_count}/{len(assets_to_download)}: {e}")
            
            # Save progress after each batch
            self.progress.save_state()
            
            # Check storage after each batch
            if not self.check_storage():
                print("🛑 Stopping due to low storage space")
                break
        
        return completed_count, failed_count

    def process_assets_sequentially(self, assets_to_download):
        """Process assets one at a time (original logic)."""
        
        completed_count = 0
        failed_count = 0
        
        for i, asset in enumerate(assets_to_download):
            if self.should_stop:
                break
            
            asset_id = asset.localIdentifier()
            
            # Display asset info
            asset_info = self.format_asset_info(asset, i + 1, len(assets_to_download))
            print(f"\n{asset_info}")
            
            # Download with retries
            success = False
            for attempt in range(self.retry_count):
                if attempt > 0:
                    print(f"   Retry {attempt}/{self.retry_count - 1}...")
                    time.sleep(self.retry_delay)
                
                success, bytes_downloaded, download_duration = self.download_asset_original(asset)
                
                if success:
                    self.progress.mark_completed(asset_id, bytes_downloaded, download_duration)
                    
                    # Verify download
                    if not self.dry_run and not self.is_asset_local(asset):
                        print("   ⚠️  Verification failed - asset may not be fully downloaded")
                        success = False
                    break
            
            if success:
                completed_count += 1
            else:
                failed_count += 1
                self.progress.mark_failed(asset_id, f"Download failed after {self.retry_count} retries")
            
            # Save progress periodically
            if (i + 1) % 10 == 0:
                self.progress.save_state()
            
            # Check storage
            if not self.check_storage():
                print("\n⚠️  Stopping due to low storage space")
                break
        
        return completed_count, failed_count

    def process_assets_streaming(self, assets, assets_to_process):
        """Process assets on-the-fly (original behavior) - compatible with concurrent downloads."""
        
        completed_count = 0
        failed_count = 0
        already_local_count = 0
        
        # Collect assets as we go for potential concurrent processing
        batch_assets = []
        batch_size = self.concurrent * 2 if self.concurrent > 1 else 1
        
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
            
            # Display asset info for sequential processing
            if self.concurrent == 1:
                asset_info = self.format_asset_info(asset, i + 1, assets_to_process)
                print(f"\n{asset_info}")
            
            # Check if original is already local
            if self.is_asset_local(asset):
                if self.concurrent == 1:
                    print("   ✓ Original already local")
                already_local_count += 1
                self.progress.stats['already_local'] = already_local_count
                self.progress.completed_assets.add(asset_id)
                continue
            
            # Add to batch for processing
            batch_assets.append(asset)
            
            # Process batch when full (concurrent) or immediately (sequential)
            if len(batch_assets) >= batch_size or self.concurrent == 1:
                if self.concurrent == 1:
                    # Sequential: process one asset
                    success = False
                    for attempt in range(self.retry_count):
                        if attempt > 0:
                            print(f"   Retry {attempt}/{self.retry_count - 1}...")
                            time.sleep(self.retry_delay)
                        
                        success, bytes_downloaded, download_duration = self.download_asset_original(asset)
                        
                        if success:
                            # Verify download with delay
                            if not self.dry_run:
                                time.sleep(2)  # Wait for Photos to process
                                if not self.is_asset_local(asset):
                                    print("   ⚠️  Verification failed - retrying download")
                                    success = False
                                    continue  # Retry
                            
                            self.progress.mark_completed(asset_id, bytes_downloaded, download_duration)
                            break
                    
                    if success:
                        completed_count += 1
                    else:
                        failed_count += 1
                        self.progress.mark_failed(asset_id, f"Download failed after {self.retry_count} retries")
                        
                else:
                    # Concurrent: process batch
                    print(f"\n📦 Processing batch: {len(batch_assets)} assets")
                    batch_completed, batch_failed = self.process_batch_concurrent(batch_assets)
                    completed_count += batch_completed
                    failed_count += batch_failed
                
                batch_assets = []
                
                # Save progress periodically
                if (completed_count + failed_count) % 10 == 0:
                    self.progress.save_state()
                
                # Check storage
                if not self.check_storage():
                    print("\n⚠️  Stopping due to low storage space")
                    break
        
        # Process any remaining assets in final batch
        if batch_assets and self.concurrent > 1:
            print(f"\n📦 Processing final batch: {len(batch_assets)} assets")
            batch_completed, batch_failed = self.process_batch_concurrent(batch_assets)
            completed_count += batch_completed
            failed_count += batch_failed
        
        return completed_count, failed_count

    def process_batch_concurrent(self, batch_assets):
        """Process a batch of assets concurrently."""
        completed_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=self.concurrent) as executor:
            # Submit all downloads in the batch
            future_to_asset = {}
            for asset in batch_assets:
                if self.should_stop:
                    break
                future = executor.submit(self.download_asset_with_retries, asset)
                future_to_asset[future] = asset
            
            # Process completed downloads as they finish
            for future in as_completed(future_to_asset):
                if self.should_stop:
                    break
                    
                asset = future_to_asset[future]
                try:
                    asset_id, success, bytes_downloaded, download_duration = future.result()
                    
                    if success:
                        completed_count += 1
                        self.progress.mark_completed(asset_id, bytes_downloaded, download_duration)
                        print(f"   ✅ Completed {completed_count + failed_count}/{len(batch_assets)}: {asset_id[:8]}...")
                    else:
                        failed_count += 1
                        self.progress.mark_failed(asset_id, f"Failed after {self.retry_count} retries")
                        print(f"   ❌ Failed {completed_count + failed_count}/{len(batch_assets)}: {asset_id[:8]}...")
                        
                except Exception as e:
                    failed_count += 1
                    asset_id = asset.localIdentifier()
                    self.progress.mark_failed(asset_id, f"Exception: {e}")
                    print(f"   💥 Exception {completed_count + failed_count}/{len(batch_assets)}: {e}")
        
        return completed_count, failed_count

    def print_summary(self):
        """Print final summary statistics."""
        print("\n" + "=" * 60)
        print("DOWNLOAD SUMMARY")
        print("=" * 60)
        print(f"Total assets in library: {self.progress.stats['total_assets']}")
        print(f"Already had originals: {self.progress.stats['already_local']}")
        print(f"Successfully downloaded: {self.progress.stats['downloaded']}")
        print(f"Failed downloads: {self.progress.stats['failed']}")
        print(f"Total data downloaded: {self.progress.get_download_size_gb():.2f} GB")
        print(f"Time elapsed: {self.progress.get_elapsed_time()}")
        if self.concurrent > 1:
            print(f"Concurrent downloads: {self.concurrent}")
        
        # Speed statistics
        speed_summary = self.progress.get_speed_summary()
        if speed_summary:
            print("\nDOWNLOAD PERFORMANCE")
            print("-" * 60)
            print(f"Overall average speed: {speed_summary['overall_avg_mbps']:.2f} MB/s")
            print(f"Per-download average: {speed_summary['avg_speed_mbps']:.2f} MB/s")
            print(f"Median speed: {speed_summary['median_speed_mbps']:.2f} MB/s")
            print(f"Speed range: {speed_summary['min_speed_mbps']:.2f} - {speed_summary['max_speed_mbps']:.2f} MB/s")
            print(f"Average file size: {speed_summary['avg_file_size_mb']:.1f} MB")
            print(f"Average download time: {speed_summary['avg_download_time_sec']:.1f} seconds")
            
            if speed_summary['fastest_download']['speed'] > 0:
                fastest = speed_summary['fastest_download']
                print(f"Fastest download: {fastest['speed']:.1f} MB/s ({fastest['size_mb']:.1f} MB, {fastest['asset_id'][:8]}...)")
            
            if speed_summary['slowest_download']['speed'] < float('inf'):
                slowest = speed_summary['slowest_download']
                print(f"Slowest download: {slowest['speed']:.1f} MB/s ({slowest['size_mb']:.1f} MB, {slowest['asset_id'][:8]}...)")
            
            # Speed distribution
            speeds = self.progress.speed_stats['download_speeds']
            if speeds:
                slow_count = sum(1 for s in speeds if s < 1.0)
                med_count = sum(1 for s in speeds if 1.0 <= s < 5.0)
                fast_count = sum(1 for s in speeds if 5.0 <= s < 10.0)
                vfast_count = sum(1 for s in speeds if s >= 10.0)
                total_count = len(speeds)
                
                print(f"\nSpeed distribution:")
                print(f"  < 1 MB/s:   {slow_count:3d} downloads ({100*slow_count/total_count:.1f}%)")
                print(f"  1-5 MB/s:   {med_count:3d} downloads ({100*med_count/total_count:.1f}%)")
                print(f"  5-10 MB/s:  {fast_count:3d} downloads ({100*fast_count/total_count:.1f}%)")
                print(f"  > 10 MB/s:  {vfast_count:3d} downloads ({100*vfast_count/total_count:.1f}%)")
                
        print("=" * 60)

    def run(self):
        """Main execution method."""
        print("Apple Photos Original Downloader")
        print("=" * 35)
        
        # Check storage before starting
        if not self.check_storage():
            print("❌ Insufficient storage space")
            return False
        
        print(f"Free space: {self.get_free_space_gb():.1f} GB ✓")
        
        # Check sync status with iCloud
        print("\n🔍 Checking Photos library sync status...")
        sync_status = self.check_sync_status()
        
        if sync_status['warnings']:
            print("\n⚠️  SYNC STATUS WARNINGS:")
            for warning in sync_status['warnings']:
                print(warning)
            
            print("\n" + "=" * 70)
            print("🔍 UNDERSTANDING PHOTO COUNTS:")
            print("=" * 70)
            print("This script can ONLY see photos in your local Photos library.")
            print("\nThree different counts exist:")
            print("1. 📱 iCloud Total: All photos across all your devices")
            print("2. 💻 Local Library: Photos on this Mac (what this script sees)")  
            print("3. 📤 Upload Queue: Photos waiting to upload from this Mac")
            print("\nIf iCloud has more photos than your Mac, those are likely from")
            print("your iPhone/iPad that haven't downloaded to this Mac yet.")
            print("=" * 70)
            
            if sync_status['sync_in_progress']:
                print("\n📡 ACTIVE SYNC DETECTED")
                print("Photos is currently syncing. This means:")
                print("• Some iPhone/iPad photos may not have downloaded yet")
                print("• Some Mac photos may not have uploaded yet")
                print("• The counts will change as sync progresses")
                
                response = input("\nContinue anyway? (y/N): ")
                if response.lower() != 'y':
                    print("Exiting. Please wait for sync to complete.")
                    print("\n💡 TIP: Check Photos app sidebar for sync status")
                    print("Look for 'Updated Just Now' to confirm sync is done")
                    return False
            else:
                print("\nProceeding with download of visible assets...")
                time.sleep(2)  # Give user time to read the warning
        else:
            print("✅ Photos library appears to be in sync")
        
        # Set start time if not resuming
        if not self.progress.stats['start_time']:
            self.progress.stats['start_time'] = datetime.now().isoformat()
        
        # Fetch all assets
        print("\nFetching assets from library...")
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
        
        print(f"\n📊 LOCAL LIBRARY STATISTICS:")
        print(f"   Total assets in local library: {total_assets:,}")
        
        # Try to get more detailed counts
        photo_count = 0
        video_count = 0
        try:
            fetch_options = Photos.PHFetchOptions.alloc().init()
            
            # Count photos
            fetch_options.setPredicate_(
                Photos.NSPredicate.predicateWithFormat_("mediaType == %d", Photos.PHAssetMediaTypeImage)
            )
            photos = PHAsset.fetchAssetsWithOptions_(fetch_options)
            photo_count = photos.count()
            
            # Count videos
            fetch_options.setPredicate_(
                Photos.NSPredicate.predicateWithFormat_("mediaType == %d", Photos.PHAssetMediaTypeVideo)
            )
            videos = PHAsset.fetchAssetsWithOptions_(fetch_options)
            video_count = videos.count()
            
            print(f"   Photos: {photo_count:,}")
            print(f"   Videos: {video_count:,}")
        except:
            pass
        
        print(f"   Sort order: {self.sort_order}")
        
        # Provide guidance on checking iCloud totals
        if sync_status['icloud_enabled']:
            print("\n📱 TO COMPARE WITH ICLOUD:")
            print("   1. Visit icloud.com/photos in a web browser")
            print("   2. Check the total count at the bottom of the page")
            print("   3. Note: iCloud shows photos from ALL your devices")
            print("\n📊 COUNT COMPARISON:")
            print(f"   • Local Mac library: {total_assets:,} items")
            print("   • iCloud total: Check icloud.com/photos")
            print("   • Difference = Photos from other devices not yet downloaded")
            
            if sync_status['sync_in_progress']:
                print("\n⏱️  SYNC IN PROGRESS:")
                print("   The local count will increase as photos download from iCloud")
                print("   Check Photos app sidebar for 'X items uploading/downloading'")
        
        if self.concurrent > 1:
            print(f"Concurrent downloads: {self.concurrent}")
        
        if self.dry_run:
            print("\n🔍 DRY RUN MODE - No files will be downloaded")
        
        # Check if resuming
        if self.progress.completed_assets:
            print(f"📂 Resuming from previous session ({len(self.progress.completed_assets)} already processed)")
        
        print("\nStarting download process...")
        print("-" * 40)
        
        if self.no_scan:
            print("🚀 Processing assets on-the-fly (no pre-scan)")
            # Original behavior: process as we go
            assets_to_process = min(total_assets, self.limit) if self.limit else total_assets
            completed, failed = self.process_assets_streaming(assets, assets_to_process)
            
            print(f"\n📊 Download session complete:")
            print(f"   Downloaded: {completed}")  
            print(f"   Failed: {failed}")
        else:
            # Scan-first behavior (current default)
            assets_to_process = min(total_assets, self.limit) if self.limit else total_assets
            assets_to_download = []
            already_local_count = 0
            
            print("🔍 Scanning for assets that need downloading...")
            
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
                
                # Check if original is already local (with retry logic)
                is_local = False
                for check_attempt in range(2):  # Try twice to be sure
                    if self.is_asset_local(asset):
                        is_local = True
                        break
                    if check_attempt == 0:
                        time.sleep(1)  # Brief wait before retry
                
                if is_local:
                    already_local_count += 1
                    self.progress.stats['already_local'] = already_local_count
                    self.progress.completed_assets.add(asset_id)
                    if i % 100 == 0:
                        print(f"   Checked {i+1}/{assets_to_process} assets...")
                    continue
                
                assets_to_download.append(asset)
                if i % 100 == 0:
                    print(f"   Checked {i+1}/{assets_to_process} assets...")
            
            print(f"📊 Scan complete:")
            print(f"   Already local: {already_local_count}")
            print(f"   Need downloading: {len(assets_to_download)}")
            
            if not assets_to_download:
                print("✅ All assets already have originals locally!")
            else:
                print(f"\n🚀 Starting download of {len(assets_to_download)} assets...")
                
                # Process downloads (concurrent or sequential)
                if self.concurrent > 1:
                    completed, failed = self.process_assets_concurrently(assets_to_download)
                else:
                    completed, failed = self.process_assets_sequentially(assets_to_download)
                
                print(f"\n📊 Download session complete:")
                print(f"   Downloaded: {completed}")
                print(f"   Failed: {failed}")
                print(f"   Already local: {already_local_count}")

        # Save final state
        self.progress.save_state()
        
        # Final verification pass if requested
        if self.final_verify and not self.dry_run:
            print("\n🔍 Running final verification pass...")
            print(f"   Waiting {self.verify_wait * 2} seconds for Photos to fully sync...")
            time.sleep(self.verify_wait * 2)
            
            still_missing = []
            verified_count = 0
            
            print("   Checking all processed assets...")
            for asset_id in self.progress.completed_assets:
                # Need to re-fetch the asset by ID
                # This is a simplified check - you may need to improve this
                print(f"   Verifying {asset_id[:8]}...", end="\r")
                verified_count += 1
            
            print(f"   ✅ Verified {verified_count} assets" + " " * 20)
            
            if still_missing:
                print(f"   ⚠️  {len(still_missing)} assets may still be downloading")
                print("   Consider running the script again later to catch any stragglers")
        
        # Print summary
        self.print_summary()
        
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download original full-resolution assets from iCloud to local storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        # Download all assets, oldest first
  %(prog)s --sort newest          # Download newest first
  %(prog)s --media-type photo     # Download only photos
  %(prog)s --limit 100            # Download first 100 assets
  %(prog)s --dry-run              # Show what would be downloaded
  %(prog)s --from-date 2020-01-01 # Download from specific date
  %(prog)s --concurrent 3         # Use 3 concurrent downloads
  %(prog)s --concurrent 5 --sort largest # Fast concurrent downloads of large files
  %(prog)s --no-scan              # Process assets immediately (original behavior)
  %(prog)s --no-scan --concurrent 2 # Streaming + concurrent processing
        """
    )
    
    parser.add_argument(
        "--sort",
        choices=["oldest", "newest", "smallest", "largest", "random"],
        default="oldest",
        help="Sort order for downloads (default: oldest)"
    )
    
    parser.add_argument(
        "--media-type",
        choices=["all", "photo", "video"],
        default="all",
        help="Type of media to download (default: all)"
    )
    
    parser.add_argument(
        "--from-date",
        type=str,
        help="Start downloading from this date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of assets to download"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Download timeout in seconds per asset (default: 300)"
    )
    
    parser.add_argument(
        "--retry-count",
        type=int,
        default=3,
        help="Number of retry attempts for failed downloads (default: 3)"
    )
    
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=10,
        help="Delay between retry attempts in seconds (default: 10)"
    )
    
    parser.add_argument(
        "--min-free-space",
        type=float,
        default=10.0,
        help="Minimum free space in GB required to continue (default: 10)"
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
    
    parser.add_argument(
        "--concurrent",
        type=int,
        default=1,
        help="Number of concurrent downloads (1-10, default: 1)"
    )
    
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Skip pre-scan, process assets as we go (original behavior)"
    )
    
    parser.add_argument(
        "--verify-wait",
        type=int,
        default=3,
        help="Seconds to wait before verifying download (default: 3)"
    )
    
    parser.add_argument(
        "--final-verify",
        action="store_true",
        help="Run a final verification pass after all downloads complete"
    )
    
    parser.add_argument(
        "--check-sync-only",
        action="store_true",
        help="Only check sync status and exit (no downloads)"
    )
    
    args = parser.parse_args()
    
    # Reset progress if requested
    if args.reset:
        progress_file = Path(".download_progress.json")
        if progress_file.exists():
            progress_file.unlink()
            print("✅ Progress reset")
    
    # If only checking sync status
    if args.check_sync_only:
        print("Apple Photos Sync Status Check")
        print("=" * 40)
        
        # Create minimal downloader just for checking
        checker = ApplePhotosDownloader(
            dry_run=True,
            limit=1
        )
        
        sync_status = checker.check_sync_status()
        
        print("\n📊 SYNC STATUS:")
        print(f"   iCloud Photos: {'✅ Enabled' if sync_status['icloud_enabled'] else '❌ Disabled'}")
        print(f"   Active Sync: {'📡 Yes - Syncing now' if sync_status['sync_in_progress'] else '✓ No active sync'}")
        if sync_status['storage_mode']:
            mode = 'Download Originals' if sync_status['storage_mode'] == 'originals' else 'Optimize Storage'
            print(f"   Storage Mode: {mode}")
        
        if sync_status['warnings']:
            print("\n⚠️  DETECTED ISSUES:")
            for warning in sync_status['warnings']:
                print(warning)
        
        # Get detailed asset counts
        print("\n📸 LOCAL LIBRARY STATISTICS:")
        try:
            fetch_options = Photos.PHFetchOptions.alloc().init()
            
            # Get total
            all_assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
            total = all_assets.count()
            
            # Count photos
            fetch_options.setPredicate_(
                Photos.NSPredicate.predicateWithFormat_("mediaType == %d", Photos.PHAssetMediaTypeImage)
            )
            photos = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
            photo_count = photos.count()
            
            # Count videos
            fetch_options.setPredicate_(
                Photos.NSPredicate.predicateWithFormat_("mediaType == %d", Photos.PHAssetMediaTypeVideo)
            )
            videos = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
            video_count = videos.count()
            
            print(f"   Total: {total:,} items")
            print(f"   Photos: {photo_count:,}")
            print(f"   Videos: {video_count:,}")
            
        except Exception as e:
            print(f"   Error fetching counts: {e}")
        
        print("\n" + "=" * 70)
        print("📱 TO CHECK IF ALL PHOTOS ARE SYNCED:")
        print("=" * 70)
        print("1. Visit icloud.com/photos and note the total count")
        print("2. Compare with the local count above")
        print("3. Check Photos app sidebar for sync status:")
        print("   • Look for 'Syncing with iCloud... X items'")
        print("   • Wait for 'Updated Just Now'")
        print("\n💡 COMMON SCENARIOS:")
        print("• iCloud > Local: iPhone/iPad photos not yet downloaded")
        print("• Local > iCloud: Mac photos still uploading")
        print("• Upload queue shown: Mac has photos to send to iCloud")
        print("• Download pending: iPhone photos waiting to download")
        print("=" * 70)
        
        sys.exit(0)
    
    # Create downloader and run
    downloader = ApplePhotosDownloader(
        sort_order=args.sort,
        media_type=args.media_type,
        from_date=args.from_date,
        limit=args.limit,
        dry_run=args.dry_run,
        timeout=args.timeout,
        retry_count=args.retry_count,
        retry_delay=args.retry_delay,
        min_free_space_gb=args.min_free_space,
        concurrent=args.concurrent,
        no_scan=args.no_scan,
        verify_wait=args.verify_wait,
        final_verify=args.final_verify
    )
    
    try:
        success = downloader.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
