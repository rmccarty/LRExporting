#!/usr/bin/env python3

from pathlib import Path
import logging
import shutil

from config import SLEEP_TIME
from processors.jpeg_processor import JPEGExifProcessor
from watchers.base_watcher import BaseWatcher

class DirectoryWatcher(BaseWatcher):
    """
    A class to watch directories for new JPEG files and process them.
    """
    
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
    
    def process_file(self, file):
        """Process a single JPEG file."""
        if "__LRE" in file.name:  # Skip already processed files
            return
            
        self.logger.info(f"Found file to process: {file}")
        
        # Check for zero-byte files
        if file.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {str(file)}")
            return
            
        # Process the file
        try:
            sequence = self._get_next_sequence()
            processor = JPEGExifProcessor(str(file), sequence=sequence)
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
