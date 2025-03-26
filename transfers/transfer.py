#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import fcntl
from datetime import datetime, timedelta

from config import MIN_FILE_AGE, TRANSFER_PATHS

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
