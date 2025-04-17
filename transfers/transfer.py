#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import fcntl
from datetime import datetime, timedelta
from dataclasses import dataclass
import shutil
import yaml

from config import MIN_FILE_AGE, TRANSFER_PATHS, APPLE_PHOTOS_PATHS, ENABLE_APPLE_PHOTOS
from apple_photos_sdk import ApplePhotos

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
        self.logger.debug(f"Validating file for transfer: {file_path}")
        
        # Check file exists
        result = self._validate_file_exists(file_path)
        if not result.is_valid:
            self._log_validation_result(result)
            return False
            
        # Check file format and destination
        result = self._validate_file_format(file_path)
        if not result.is_valid:
            self._log_validation_result(result)
            self.logger.debug(f"File format validation failed: {file_path}")
            self.logger.debug(f"Has __LRE suffix: {self._is_processed_file(file_path)}")
            self.logger.debug(f"Has configured destination: {self._has_configured_destination(file_path.parent)}")
            return False
            
        # Check file state
        result = self._validate_file_state(file_path)
        if not result.is_valid:
            self._log_validation_result(result)
            self.logger.debug(f"File state validation failed: {file_path}")
            self.logger.debug(f"Is file old enough: {self._is_file_old_enough(file_path)}")
            self.logger.debug(f"Can access file: {self._can_access_file(file_path)}")
            return False
            
        return True
        
    def _get_album_paths_from_keywords(self, keywords: list[str]) -> list[str]:
        """Given a list of keywords, return album paths based on folder/album keywords and album.yaml mapping."""
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Error loading album.yaml: {e}")
            return []
        album_paths = []
        for kw in keywords:
            if "/" in kw:
                folder, album = kw.split("/", 1)
                folder = folder.strip()
                album = album.strip()
                if folder in mapping:
                    base_path = mapping[folder]
                    # Remove trailing slash if present
                    base_path = base_path.rstrip("/")
                    album_path = f"{base_path}/{album}"
                    album_paths.append(album_path)
        return album_paths
        
    def _get_album_paths_for_city(self, city: str) -> list[str]:
        """Load album paths for a given city from album.yaml."""
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
            if city in mapping:
                return [mapping[city]] if isinstance(mapping[city], str) else list(mapping[city])
            else:
                self.logger.warning(f"No album mapping found for city: {city}")
                return []
        except Exception as e:
            self.logger.error(f"Error loading album.yaml: {e}")
            return []
            
    def _import_to_photos(self, photo_path: Path) -> bool:
        """Import a photo into Apple Photos using album.yaml mapping and Folder/Album keywords."""
        # Extract keywords from the file (using ImportManager logic for consistency)
        from apple_photos_sdk.import_manager import ImportManager
        keywords = ImportManager()._get_original_keywords(photo_path)
        album_paths = self._get_album_paths_from_keywords(keywords)
        success = ApplePhotos().import_photo(photo_path, album_paths=album_paths)
        if success:
            self.logger.info(f"Successfully imported {photo_path} to Apple Photos")
            return True
        else:
            self.logger.error(f"Failed to import {photo_path} to Apple Photos")
            return False

    def _perform_transfer(self, file_path: Path, dest_dir: Path) -> bool:
        """
        Transfer a file to its destination.
        """
        try:
            # First move file to destination
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / file_path.name
            self.logger.debug(f"Moving file from {file_path} to {dest_path}")
            file_path.rename(dest_path)
            self.logger.info(f"Successfully moved file to {dest_path}")
            
            if ENABLE_APPLE_PHOTOS and dest_dir in APPLE_PHOTOS_PATHS:
                # Then import to Apple Photos if needed
                self.logger.debug(f"Importing {dest_path} to Apple Photos")
                # Use album.yaml mapping and Folder/Album keywords
                from apple_photos_sdk.import_manager import ImportManager
                keywords = ImportManager()._get_original_keywords(dest_path)
                album_paths = self._get_album_paths_from_keywords(keywords)
                photos = ApplePhotos()
                success = photos.import_photo(dest_path, album_paths=album_paths)
                if success:
                    self.logger.info(f"Successfully imported {dest_path} to Apple Photos")
                else:
                    self.logger.error(f"Failed to import {dest_path} to Apple Photos")
                return success
            elif dest_dir in APPLE_PHOTOS_PATHS:
                self.logger.info(f"Apple Photos processing is disabled. Skipping import of {dest_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Transfer failed for {file_path}: {e}")
            return False

    def transfer_file(self, file_path: Path) -> bool:
        """
        Transfer a file to its destination. Has two paths:
        1. Apple Photos path: Directly imports media files to Photos
        2. Regular path: Requires these conditions:
           - File ends with _LRE
           - Source directory has a configured destination
           - File is at least MIN_FILE_AGE seconds old
           - File can be opened with exclusive access
        
        Args:
            file_path: Path to the file to transfer
            
        Returns:
            bool: True if transfer was successful, False otherwise
        """
        try:
            # Check if source is an Apple Photos directory
            if ENABLE_APPLE_PHOTOS and any(file_path.parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                # Skip validation for Apple Photos imports
                self.logger.info(f"Importing to Apple Photos: {file_path}")
                return self._import_to_photos(file_path)
            elif any(file_path.parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                self.logger.info(f"Apple Photos processing is disabled. Skipping import of {file_path}")
                return True
                
            # Check if source has a configured destination
            source_dir = file_path.parent
            if source_dir not in TRANSFER_PATHS:
                self.logger.error(f"No configured destination for {source_dir}")
                return False
                
            # For regular transfers, validate and move to destination
            if not self._validate_file_for_transfer(file_path):
                return False
                
            dest_dir = TRANSFER_PATHS[source_dir]
            self.logger.info(f"Moving file to {dest_dir}: {file_path}")
            return self._perform_transfer(file_path, dest_dir)
                
        except Exception as e:
            self.logger.error(f"Transfer failed for {file_path}: {e}")
            return False
