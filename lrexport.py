#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
from datetime import datetime
import shutil
import time
import xml.etree.ElementTree as ET
from mutagen.mp4 import MP4
import re  
import glob
import os
import fcntl
from PIL import Image
from datetime import timedelta
from abc import ABC, abstractmethod

from config import (
    WATCH_DIRS, 
    BOTH_INCOMING, 
    LOG_LEVEL, 
    SLEEP_TIME,
    XML_NAMESPACES,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX,
    JPEG_QUALITY,
    JPEG_COMPRESS,
    TRANSFER_PATHS,
    MIN_FILE_AGE
)

from watchers.base_watcher import BaseWatcher
from processors.media_processor import MediaProcessor
from processors.jpeg_processor import JPEGExifProcessor
from processors.video_processor import VideoProcessor

class Transfer:
    """
    Handles safe transfer of processed files to their destination directories.
    Ensures files are not active/being written to before moving them.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def _can_access_file(self, file_path: Path, timeout: int = 5) -> bool:
        """
        Try to get exclusive access to a file using flock.
        
        Args:
            file_path: Path to the file to check
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            bool: True if exclusive access was obtained, False otherwise
        """
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    with open(file_path, 'rb') as f:
                        # Try non-blocking exclusive lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # If we get here, we got the lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return True
                except (IOError, OSError):
                    # File is locked or inaccessible
                    time.sleep(0.1)
            return False
        except Exception as e:
            self.logger.error(f"Error checking file access: {e}")
            return False
            
    def _is_file_old_enough(self, file_path: Path) -> bool:
        """
        Check if file's last modification time is at least MIN_FILE_AGE seconds old.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            bool: True if file is old enough, False otherwise
        """
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            age_threshold = datetime.now() - timedelta(seconds=MIN_FILE_AGE)
            return mtime <= age_threshold
        except Exception as e:
            self.logger.error(f"Error checking file age: {e}")
            return False
            
    def transfer_file(self, file_path: Path) -> bool:
        """
        Safely transfer a file to its destination directory if conditions are met:
        1. File ends with _LRE
        2. Source directory has a configured destination
        3. File is at least MIN_FILE_AGE seconds old
        4. File can be opened with exclusive access
        
        Args:
            file_path: Path to the file to transfer
            
        Returns:
            bool: True if transfer was successful, False otherwise
        """
        try:
            if not file_path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False
                
            # Check if this is a processed file
            if not file_path.name.endswith('__LRE' + file_path.suffix):
                self.logger.debug(f"Not a processed file: {file_path}")
                return False
                
            # Check if we have a destination for this source directory
            source_dir = file_path.parent
            if source_dir not in TRANSFER_PATHS:
                self.logger.error(f"No transfer path configured for: {source_dir}")
                return False
                
            # Check if file is old enough
            if not self._is_file_old_enough(file_path):
                self.logger.debug(f"File too new to transfer: {file_path}")
                return False
                
            # Check if we can get exclusive access
            if not self._can_access_file(file_path):
                self.logger.debug(f"Cannot get exclusive access to file: {file_path}")
                return False
                
            # All checks passed, perform the transfer
            dest_dir = TRANSFER_PATHS[source_dir]
            dest_path = dest_dir / file_path.name
            
            # Create destination directory if it doesn't exist
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            file_path.rename(dest_path)
            self.logger.info(f"Transferred {file_path.name} to {dest_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error transferring file {file_path}: {e}")
            return False

class TransferWatcher:
    """Watches for _LRE files and transfers them to their destination directories."""
    
    def __init__(self, directories=None):
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
        self.transfer = Transfer()
        
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file by attempting to transfer it.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            bool: True if transfer was successful or not needed, False if error
        """
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
            for file_path in directory.glob('*__LRE.*'):
                self.process_file(file_path)
                
        except Exception as e:
            self.logger.error(f"Error checking directory {directory}: {e}")

class DirectoryWatcher:
    """
    A class to watch directories for new JPEG files and process them.
    """
    
    # Class-level sequence counter (1-9999)
    _sequence = 0
    
    @classmethod
    def _get_next_sequence(cls) -> str:
        """Get next sequence number as 4-digit string."""
        cls._sequence = (cls._sequence % 9999) + 1  # Roll over to 1 after 9999
        return f"{cls._sequence:04d}"  # Format as 4 digits with leading zeros
    
    def __init__(self, watch_dirs, both_incoming_dir=None):
        """
        Initialize the directory watcher.
        
        Args:
            watch_dirs: List of Path objects for directories to watch
            both_incoming_dir: Optional Path object for a shared incoming directory
        """
        self.directories = [Path(d) for d in watch_dirs]
        self.both_incoming = Path(both_incoming_dir) if both_incoming_dir else None
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
    def process_both_incoming(self):
        """Check Both_Incoming directory and copy files to individual incoming directories."""
        if not self.both_incoming:
            return False
            
        found_files = False
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob("*"):
                # Check if the file is open
                try:
                    with open(file, 'r+'):
                        pass  # File is not open, proceed to copy
                except IOError:
                    self.logger.warning(f"File {file.name} is currently open. Skipping copy.")
                    continue  # Skip to the next file
                
                found_files = True
                # Copy the file to all incoming directories
                for incoming_dir in self.directories:
                    shutil.copy(file, incoming_dir / file.name)
                    self.logger.info(f"Copied {file.name} to {incoming_dir.name} directory.")
                
                # Delete the original file
                file.unlink()
                self.logger.info(f"Deleted {file.name} from Both_Incoming.")
        
        except Exception as e:
            self.logger.error(f"Error processing Both_Incoming: {e}")
        
        return found_files
    
    def process_file(self, file):
        """Process a single JPEG file."""
        if "__LRE" in file.name:  # Skip already processed files
            return
            
        self.logger.info(f"Found file to process: {file}")
        
        # Check for zero-byte files
        if file.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {file}")
            return
            
        # Process the file
        sequence = self._get_next_sequence()
        processor = JPEGExifProcessor(str(file), sequence=sequence)
        try:
            new_path = processor.process_image()
            self.logger.info(f"Image processed successfully: {new_path}")
        except Exception as e:
            self.logger.error(f"Error processing image: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new JPEG files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        self.logger.info(f"\nChecking {directory} for new JPEG files...")
        for file in directory.glob("*.jpg"):
            self.process_file(file)

class VideoWatcher:
    """
    A class to watch directories for video files.
    """
    
    # Class-level sequence counter (1-9999)
    _sequence = 0
    
    @classmethod
    def _get_next_sequence(cls) -> str:
        """Get next sequence number as 4-digit string."""
        cls._sequence = (cls._sequence % 9999) + 1  # Roll over to 1 after 9999
        return f"{cls._sequence:04d}"  # Format as 4 digits with leading zeros
    
    def __init__(self, directories=None):
        """
        Initialize the video watcher.
        
        Args:
            directories: List of Path objects for directories to watch
        """
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
    def process_file(self, file_path):
        """Process a single video file."""
        try:
            # Check for XMP file
            xmp_path = os.path.splitext(file_path)[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = file_path + ".xmp"
                if not os.path.exists(xmp_path):
                    return  # Skip if no XMP file
            
            # Process video
            self.logger.info(f"Found new video: {os.path.basename(file_path)}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(file_path, sequence=sequence)
            processor.process_video()
            
        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new video files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        self.logger.info(f"\nChecking {directory} for new video files...")
        video_files = []
        # Handle both upper and lower case extensions
        for pattern in VIDEO_PATTERN:
            video_files.extend(directory.glob(pattern.lower()))
            video_files.extend(directory.glob(pattern.upper()))
        
        if video_files:
            self.logger.info(f"Found files: {[str(f) for f in video_files]}")
            
        for file_path in video_files:
            self.logger.info(f"Found new video: {file_path.name}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
            processor.process_video()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Create watchers
    jpeg_watcher = DirectoryWatcher(
        watch_dirs=WATCH_DIRS,
        both_incoming_dir=BOTH_INCOMING
    )
    video_watcher = VideoWatcher(directories=WATCH_DIRS)
    transfer_watcher = TransferWatcher(directories=WATCH_DIRS)
    
    try:
        # Start both watchers
        while True:
            # Process both incoming directory first for JPEGs
            jpeg_watcher.process_both_incoming()
            
            # Check all watch directories for both types
            for directory in WATCH_DIRS:
                directory = Path(directory)
                jpeg_watcher.check_directory(directory)
                # Check for videos
                video_watcher.check_directory(directory)
                # Check for transfers
                transfer_watcher.check_directory(directory)
                
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping watchers")
        jpeg_watcher.running = False
        video_watcher.running = False
        transfer_watcher.running = False