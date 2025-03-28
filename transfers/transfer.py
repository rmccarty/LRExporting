#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import fcntl
from datetime import datetime, timedelta
from dataclasses import dataclass

from config import MIN_FILE_AGE, TRANSFER_PATHS

@dataclass
class ValidationResult:
    """
    Holds the result of a file validation check.
    """
    is_valid: bool
    message: str = ""
    level: str = "debug"  # debug, error

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
            
    def _is_processed_file(self, file_path: Path) -> bool:
        """
        Check if the file has the __LRE suffix indicating it's been processed.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            bool: True if file has __LRE suffix, False otherwise
        """
        return file_path.name.endswith('__LRE' + file_path.suffix)
        
    def _has_configured_destination(self, source_dir: Path) -> bool:
        """
        Check if the source directory has a configured destination.
        
        Args:
            source_dir: Source directory to check
            
        Returns:
            bool: True if directory has configured destination, False otherwise
        """
        if source_dir not in TRANSFER_PATHS:
            self.logger.error(f"No transfer path configured for: {source_dir}")
            return False
        return True
        
    def _validate_file_exists(self, file_path: Path) -> ValidationResult:
        """
        Check if the file exists.
        
        Args:
            file_path: Path to validate
            
        Returns:
            ValidationResult: Validation result with status and message
        """
        if not file_path.exists():
            return ValidationResult(False, f"File does not exist: {file_path}", "error")
        return ValidationResult(True)
        
    def _validate_file_format(self, file_path: Path) -> ValidationResult:
        """
        Check if the file has the correct format and destination.
        
        Args:
            file_path: Path to validate
            
        Returns:
            ValidationResult: Validation result with status and message
        """
        if not self._is_processed_file(file_path):
            return ValidationResult(False, f"Not a processed file: {file_path}")
            
        if not self._has_configured_destination(file_path.parent):
            # _has_configured_destination already logs error
            return ValidationResult(False)
            
        return ValidationResult(True)
        
    def _validate_file_state(self, file_path: Path) -> ValidationResult:
        """
        Check if the file state allows for transfer (age and accessibility).
        
        Args:
            file_path: Path to validate
            
        Returns:
            ValidationResult: Validation result with status and message
        """
        if not self._is_file_old_enough(file_path):
            return ValidationResult(False, f"File too new to transfer: {file_path}")
            
        if not self._can_access_file(file_path):
            return ValidationResult(False, f"Cannot get exclusive access to file: {file_path}")
            
        return ValidationResult(True)
        
    def _log_validation_result(self, result: ValidationResult) -> None:
        """
        Log validation result with appropriate level.
        
        Args:
            result: ValidationResult to log
        """
        if not result.message:
            return
            
        if result.level == "error":
            self.logger.error(result.message)
        else:
            self.logger.debug(result.message)
            
    def _validate_file_for_transfer(self, file_path: Path) -> bool:
        """
        Validate that a file meets all requirements for transfer.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            bool: True if file is valid for transfer, False otherwise
        """
        validations = [
            self._validate_file_exists(file_path),
            self._validate_file_format(file_path),
            self._validate_file_state(file_path)
        ]
        
        for result in validations:
            if not result.is_valid:
                self._log_validation_result(result)
                return False
                
        return True
        
    def _perform_transfer(self, file_path: Path, dest_dir: Path) -> bool:
        """
        Perform the actual file transfer operation.
        
        Args:
            file_path: Path to the file to transfer
            dest_dir: Destination directory
            
        Returns:
            bool: True if transfer successful, False otherwise
        """
        try:
            # Create destination directory if it doesn't exist
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            dest_path = dest_dir / file_path.name
            file_path.rename(dest_path)
            self.logger.info(f"Transferred {file_path.name} to {dest_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error transferring file {file_path}: {e}")
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
            if not self._validate_file_for_transfer(file_path):
                return False
                
            dest_dir = TRANSFER_PATHS[file_path.parent]
            return self._perform_transfer(file_path, dest_dir)
            
        except Exception as e:
            self.logger.error(f"Error transferring file {file_path}: {e}")
            return False
