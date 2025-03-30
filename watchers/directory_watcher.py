#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import shutil

from config import (
    WATCH_DIRS, BOTH_INCOMING, APPLE_PHOTOS_PATHS,
    JPEG_PATTERN, ALL_PATTERN
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
    
    def process_both_incoming(self):
        """Check Both_Incoming directory and copy files to individual incoming directories."""
        if not self.both_incoming:
            return False
            
        found_files = False
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob("*"):
                found_files = True  # Mark as found even if locked
                # Check if the file is open
                try:
                    with open(file, 'r+'):
                        # File is not open, proceed to copy
                        # Copy the file to all incoming directories
                        for incoming_dir in self.directories:
                            shutil.copy(file, incoming_dir / file.name)
                            self.logger.info(f"Copied {file.name} to {incoming_dir.name} directory.")
                        
                        # Delete the original file
                        file.unlink()
                        self.logger.info(f"Deleted {file.name} from Both_Incoming.")
                except IOError:
                    self.logger.warning(f"File {file.name} is currently open. Skipping copy.")
                    continue  # Skip to the next file
        
        except Exception as e:
            self.logger.error(f"Error processing Both_Incoming: {e}")
            found_files = False
        
        return found_files
    
    def process_file(self, file_path: Path):
        """Process a single file."""
        if not file_path.is_file():
            return
            
        # Skip already processed files
        if "__LRE" in file_path.name:
            return
            
        # Check for zero-byte files
        if file_path.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {str(file_path)}")
            return
            
        try:
            # For files in Apple Photos directories, directly import without processing
            if any(Path(str(file_path)).parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                self.logger.info(f"Found file in Apple Photos directory: {file_path}")
                self.transfer.transfer_file(file_path)
                return
                
            # For files in regular directories, process and transfer
            self.logger.info(f"Processing file: {file_path}")
            
            # Process the file based on type
            if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                sequence = self._get_next_sequence()
                processor = JPEGExifProcessor(str(file_path), sequence=sequence)
                new_path = processor.process_image()
                self.logger.info(f"Image processed successfully: {new_path}")
            else:
                # For videos, just transfer without processing
                new_path = file_path
                
            # Transfer to destination
            if new_path:
                self.transfer.transfer_file(new_path)
                
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new JPEG files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        # Don't log for Apple Photos directories since check_apple_photos_dirs already does
        if not any(Path(directory) == photos_path for photos_path in APPLE_PHOTOS_PATHS):
            self.logger.info(f"Checking {directory} for new JPEG files...")
            # Regular directory - only process JPG files
            for file in directory.glob(JPEG_PATTERN):
                self.process_file(file)
        else:
            # Apple Photos directory - process all supported files
            self.logger.debug(f"Looking for patterns: {ALL_PATTERN}")
            for pattern in ALL_PATTERN:
                self.logger.debug(f"Searching with pattern: {pattern}")
                for file in directory.glob(pattern):
                    self.logger.debug(f"Found file: {file}")
                    self.process_file(file)
    
    def check_apple_photos_dirs(self):
        """Check Apple Photos directories for media files and transfer them."""
        for photos_path in APPLE_PHOTOS_PATHS:
            self.logger.info(f"Checking {photos_path} for new media files...")
            self.check_directory(photos_path)
