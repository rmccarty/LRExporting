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
        # Simplified logic: Import ALL photos to Apple Photos and add to Watching album
        # Let Apple Photo Watcher handle the smart category detection and placement logic
        from config import APPLE_PHOTOS_WATCHING
        self.logger.info(f"Importing {file_path.name} to Apple Photos and adding to Watching album for processing")
        
        # Import to Apple Photos with Watching album for further processing by Apple Photo Watcher
        watching_album_path = str(APPLE_PHOTOS_WATCHING).rstrip('/')
        return self.transfer.transfer_file(file_path, album_paths=[watching_album_path])

        
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
