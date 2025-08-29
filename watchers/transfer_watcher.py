#!/usr/bin/env python3

from pathlib import Path
import logging

from config import WATCH_DIRS, SLEEP_TIME, APPLE_PHOTOS_PATHS, ENABLE_APPLE_PHOTOS, WATCHER_QUEUE_SIZE
from transfers import Transfer

class TransferWatcher:
    """Watches for _LRE files and transfers them to their destination directories, including Apple Photos imports."""
    
    def __init__(self, directories=None):
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
        self.transfer = Transfer()
        self.queue_size = WATCHER_QUEUE_SIZE
        self.processed_count = 0  # Track files processed in current cycle
    
    def reset_queue_counter(self):
        """Reset the processed count for a new cycle."""
        self.processed_count = 0
    
    def check_apple_photos_dirs(self):
        """Check Apple Photos directories for media files and transfer them."""
        if not ENABLE_APPLE_PHOTOS:
            return

        for photos_path in APPLE_PHOTOS_PATHS:
            print(f"🔄 TRANSFER WATCHER: Checking {photos_path} for media files...")
            self.check_directory(photos_path)
        
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file by attempting to transfer it.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            bool: True if transfer was successful or not needed, False if error
        """
        # Simplified logic: Import ALL photos to Apple Photos and add to Watching album
        # Let Apple Photo Watcher handle the smart category detection and placement logic
        from config import APPLE_PHOTOS_WATCHING
        self.logger.info(f"Importing {file_path.name} to Apple Photos and adding to Watching album for processing")
        
        # Import to Apple Photos Watcher album for further processing by Apple Photo Watcher
        return self.transfer.transfer_file(file_path)

        
    def check_directory(self, directory: Path):
        """
        Check a directory for _LRE files ready to be transferred.
        
        Args:
            directory: Directory to check
        """
        if not directory.exists():
            self.logger.warning(f"Directory does not exist: {directory}")
            return
            
        try:
            # Check for __LRE files only (both regular and Apple Photos directories)
            print(f"🔄 TRANSFER WATCHER: Checking {directory} for __LRE files... (Queue: {self.processed_count}/{self.queue_size})")
            found_count = 0
            for file_path in directory.glob('*__LRE.*'):
                if self.processed_count >= self.queue_size:
                    print(f"   ⚠️  Queue limit reached ({self.queue_size} files) - {found_count} files processed, more files pending")
                    break
                found_count += 1
                print(f"   📦 [{self.processed_count + 1}/{self.queue_size}] Found __LRE file: {file_path.name}")
                self.process_file(file_path)
                self.processed_count += 1
            if found_count == 0:
                print(f"   ✅ No __LRE files to transfer in {directory.name}")
                
        except Exception as e:
            self.logger.error(f"Error checking directory {directory}: {e}")
