#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import shutil

from config import SLEEP_TIME, APPLE_PHOTOS_PATHS
from watchers.base_watcher import BaseWatcher
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
            
        self.logger.info(f"Found file to process: {file_path}")
        
        # Check for zero-byte files
        if file_path.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {str(file_path)}")
            return
            
        try:
            # Process the file
            sequence = self._get_next_sequence()
            processor = JPEGExifProcessor(str(file_path), sequence=sequence)
            new_path = processor.process_image()
            self.logger.info(f"Image processed successfully: {new_path}")
            
            # If it's in an Apple Photos directory, transfer it
            if any(Path(str(file_path)).parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                self.transfer.transfer_file(Path(new_path))
                
        except Exception as e:
            self.logger.error(f"Error processing image: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new JPEG files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        # Don't log for Apple Photos directories since check_apple_photos_dirs already does
        if not any(Path(directory) == photos_path for photos_path in APPLE_PHOTOS_PATHS):
            self.logger.info(f"Checking {directory} for new JPEG files...")
            # Regular directory - only process JPG files
            for file in directory.glob("*.jpg"):
                self.process_file(file)
        else:
            # Apple Photos directory - process all files
            for file in directory.iterdir():
                if file.is_file():
                    self.process_file(file)
    
    def check_apple_photos_dirs(self):
        """Check Apple Photos directories for media files and transfer them."""
        for photos_path in APPLE_PHOTOS_PATHS:
            self.logger.info(f"Checking {photos_path} for new media files...")
            self.check_directory(photos_path)
