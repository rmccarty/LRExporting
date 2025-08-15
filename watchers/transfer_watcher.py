#!/usr/bin/env python3

from pathlib import Path
import logging

from config import WATCH_DIRS, SLEEP_TIME
from transfers import Transfer

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
        # Extract title to check for category format (same logic as DirectoryWatcher)
        title = None
        if file_path.suffix.lower() in ['.jpg', '.jpeg']:
            try:
                from processors.jpeg_processor import JPEGExifProcessor
                processor = JPEGExifProcessor(str(file_path))
                _, title, _, _, _, _ = processor.get_metadata_components()
                self.logger.info(f"Extracted title: '{title}'")
            except Exception as e:
                self.logger.warning(f"Could not extract title from {file_path}: {e}")
        
        # Check if title has category format (contains colon) for Watching album
        if title and ':' in title:
            from config import APPLE_PHOTOS_WATCHING
            self.logger.info(f"Title '{title}' has category format - importing to Apple Photos and adding to Watching album")
            # Import to Apple Photos with Watching album for further processing
            watching_album_path = str(APPLE_PHOTOS_WATCHING).rstrip('/')
            return self.transfer.transfer_file(file_path, album_paths=[watching_album_path])
        else:
            self.logger.info(f"Title '{title}' does not have category format - importing to Apple Photos only")
            # Import to Apple Photos without any specific album
            return self.transfer.transfer_file(file_path, album_paths=[])
        
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
