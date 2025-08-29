#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import shutil

from config import (
    WATCH_DIRS, BOTH_INCOMING, APPLE_PHOTOS_PATHS,
    JPEG_PATTERN, ALL_PATTERN, ENABLE_APPLE_PHOTOS, APPLE_PHOTOS_WATCHING,
    WATCHER_QUEUE_SIZE
)
from .base_watcher import BaseWatcher
from transfers.transfer import Transfer
from processors.jpeg_processor import JPEGExifProcessor

class DirectoryWatcher(BaseWatcher):
    """
    A class to watch directories for new files and process them.
    """
    
    def __init__(self, watch_dirs=None, both_incoming_dir=None):
        """Initialize the directory watcher."""
        super().__init__(directories=watch_dirs)
        self.both_incoming = Path(both_incoming_dir) if both_incoming_dir else None
        self.transfer = Transfer()
        self.logger = logging.getLogger(__name__)  # Override base logger
        self.queue_size = WATCHER_QUEUE_SIZE
        self.processed_count = 0  # Track files processed in current cycle
    
    def reset_queue_counter(self):
        """Reset the processed count for a new cycle."""
        if self.processed_count > 0:
            print(f"📊 DIRECTORY WATCHER: Processed {self.processed_count} files in this cycle")
        self.processed_count = 0
    
    def process_both_incoming(self):
        """Check Both_Incoming directory and copy files to individual incoming directories."""
        if not self.both_incoming:
            return False
            
        print(f"🔍 BOTH_INCOMING: Checking {self.both_incoming} for files to distribute...")
        found_files = False
        file_count = 0
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob("*"):
                found_files = True  # Mark as found even if locked
                file_count += 1
                # Check if the file is open
                try:
                    with open(file, 'r+'):
                        # File is not open, proceed to copy
                        print(f"   📤 Distributing: {file.name}")
                        # Copy the file to all incoming directories
                        for incoming_dir in self.directories:
                            shutil.copy(file, incoming_dir / file.name)
                            self.logger.info(f"Copied {file.name} to {incoming_dir.name} directory.")
                            print(f"      → Copied to {incoming_dir.name}")
                        
                        # Delete the original file
                        file.unlink()
                        self.logger.info(f"Deleted {file.name} from Both_Incoming.")
                        print(f"      ✓ Deleted from Both_Incoming")
                except IOError:
                    self.logger.warning(f"File {file.name} is currently open. Skipping copy.")
                    print(f"   ⏳ File {file.name} is locked - will retry later")
                    continue  # Skip to the next file
        
        except Exception as e:
            self.logger.error(f"Error processing Both_Incoming: {e}")
            found_files = False
        
        if file_count == 0:
            print(f"   ✅ No files to distribute from Both_Incoming")
        
        return found_files
    
    def process_file(self, file_path: Path):
        """Process a single file."""
        if not file_path.is_file():
            return
            
        # Check for zero-byte files
        if file_path.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {str(file_path)}")
            return
            
        try:
            # For files in Apple Photos directories, process regardless of suffix
            if ENABLE_APPLE_PHOTOS and any(Path(str(file_path)).parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                self.logger.info(f"Found file in Apple Photos directory: {file_path}")
                
                # Extract title to check for category format
                title = None
                if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                    processor = JPEGExifProcessor(str(file_path))
                    _, title, _, _, _, _ = processor.get_metadata_components()
                    self.logger.info(f"Extracted title: '{title}'")
                else:
                    self.logger.info("Video file - no metadata extraction in this flow")
                
                # Check if title has category format (contains colon) for Watching album
                if title and ':' in title:
                    self.logger.info(f"Title '{title}' has category format - importing to Apple Photos Watcher album")
                    # Import to Apple Photos Watcher album for further processing
                    self.transfer.transfer_file(file_path)
                else:
                    self.logger.info(f"Title '{title}' does not have category format - importing to Apple Photos Watcher album")
                    # Import to Apple Photos Watcher album
                    self.transfer.transfer_file(file_path)
                return
                
            # For files in regular directories, skip if already processed
            if "__LRE" in file_path.name:
                self.logger.debug(f"Skipping already processed file: {file_path}")
                return
                
            # For files in regular directories, process and transfer
            self.logger.info(f"Processing file: {file_path}")
            print(f"      🎨 PROCESSING: {file_path.name}")
            
            # Process the file based on type
            if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                sequence = self._get_next_sequence()
                processor = JPEGExifProcessor(str(file_path), sequence=sequence)
                new_path = processor.process_image()
                self.logger.info(f"Image processed successfully: {new_path}")
                print(f"         ✓ Processed to: {Path(new_path).name}")
                
                # Extract title to check for category format
                post_processor = JPEGExifProcessor(str(new_path))
                _, title, _, _, _, _ = post_processor.get_metadata_components()
                self.logger.info(f"Extracted title: '{title}'")
                
            else:
                # For videos, just transfer without processing
                new_path = file_path
                title = None
                self.logger.info("Video file - no metadata extraction in this flow")
                
            # Transfer to Apple Photos
            if new_path:
                # Check if title has category format (contains colon) for Watching album
                if title and ':' in title:
                    self.logger.info(f"Title '{title}' has category format - importing to Apple Photos Watcher album")
                    # Import to Apple Photos Watcher album for further processing
                    self.transfer.transfer_file(new_path)
                else:
                    self.logger.info(f"Title '{title}' does not have category format - importing to Apple Photos Watcher album")
                    # Import to Apple Photos Watcher album
                    self.transfer.transfer_file(new_path)
                
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new JPEG files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        # Check if we've hit the queue limit
        if self.processed_count >= self.queue_size:
            print(f"   ⚠️  Queue limit reached ({self.queue_size} files) - yielding to other watchers")
            return
            
        # Don't log for Apple Photos directories since check_apple_photos_dirs already does
        if not any(Path(directory) == photos_path for photos_path in APPLE_PHOTOS_PATHS):
            self.logger.info(f"Checking {directory} for new JPEG files...")
            print(f"🔍 DIRECTORY WATCHER: Checking {directory} for new JPEG files... (Queue: {self.processed_count}/{self.queue_size})")
            # Regular directory - only process JPG files
            found_count = 0
            for file in directory.glob(JPEG_PATTERN):
                if self.processed_count >= self.queue_size:
                    print(f"   ⚠️  Queue limit reached ({self.queue_size} files) - {found_count} files processed, more files pending")
                    break
                found_count += 1
                print(f"   📷 [{self.processed_count + 1}/{self.queue_size}] Found JPEG: {file.name}")
                self.process_file(file)
                self.processed_count += 1
            if found_count == 0:
                print(f"   ✅ No new JPEGs to process in {directory.name}")
        else:
            # Apple Photos directory - process all supported files
            self.logger.debug(f"Looking for patterns: {ALL_PATTERN}")
            for pattern in ALL_PATTERN:
                self.logger.debug(f"Searching with pattern: {pattern}")
                for file in directory.glob(pattern):
                    if self.processed_count >= self.queue_size:
                        print(f"   ⚠️  Queue limit reached ({self.queue_size} files) - more files pending in Apple Photos directory")
                        return
                    self.logger.debug(f"Found file: {file}")
                    print(f"   📷 [{self.processed_count + 1}/{self.queue_size}] Found media file: {file.name}")
                    self.process_file(file)
                    self.processed_count += 1
    
    def check_apple_photos_dirs(self):
        """Check Apple Photos directories for media files and transfer them."""
        if not ENABLE_APPLE_PHOTOS:
            self.logger.info("Apple Photos processing is disabled. Skipping checks.")
            return

        for photos_path in APPLE_PHOTOS_PATHS:
            self.logger.info(f"Checking {photos_path} for new media files...")
            self.check_directory(photos_path)
