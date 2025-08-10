#!/usr/bin/env python3

from pathlib import Path
import logging
import time
import fcntl
from datetime import datetime, timedelta
from dataclasses import dataclass
import shutil
import yaml

from config import MIN_FILE_AGE, TRANSFER_PATHS, APPLE_PHOTOS_PATHS, ENABLE_APPLE_PHOTOS, CATEGORY_PREFIX
from apple_photos_sdk import ApplePhotos
from apple_photos_sdk.album import AlbumManager
import Photos
from objc import autorelease_pool
import sqlite3
import os
from pathlib import Path

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
        self.album_manager = AlbumManager()
        
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
        
    def _get_album_paths_from_keywords(self, keywords: list[str], title: str | None = None) -> list[str]:
        """Given a list of keywords, return album paths based on patterns:
        1. Folder/Album: use album.yaml to map 'Folder' and append 'Album'
        2. Folder/: use album.yaml to map 'Folder' and append photo title
        3. Plain Folder: use album.yaml to map 'Folder' and append photo title
        4. Keyword ending with colon (e.g., 'Travel:'): use as category and create {CATEGORY_PREFIX}/category/title path
        """
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Error loading album.yaml: {e}")
            return []
        album_paths = []
        for kw in keywords:
            # Case 4: Keyword with colon (e.g. "Gravestones: McCarty") - create hierarchical album path
            if ":" in kw and title:
                # Skip keywords ending with just a colon (e.g., "Wedding:")
                if kw.endswith(":") and kw.count(":") == 1:
                    self.logger.debug(f"Ignoring keyword ending with colon: {kw}")
                    continue  # Skip further processing for this keyword
                
                # For all other colon-containing keywords, extract the category and create hierarchical path
                if ":" in kw and kw.count(":") == 1 and ": " in kw:
                    category = kw.split(": ")[0].strip()
                    # Create hierarchical path: CATEGORY_PREFIX/Category/Full Keyword
                    album_path = f"{CATEGORY_PREFIX}/{category}/{kw}"
                    self.logger.info(f"Created hierarchical album path from colon-keyword: {album_path}")
                else:
                    # Fall back to flat structure for non-standard colons
                    album_path = f"{CATEGORY_PREFIX}/{kw}"
                    self.logger.info(f"Created flat album path from non-standard colon-keyword: {album_path}")
                album_paths.append(album_path)
                continue  # Skip further processing for this keyword
                    
            # Normalize keywords that are a single word ending with a slash (e.g., 'RTPC/')
            if kw.endswith("/") and "/" not in kw[:-1]:
                normalized_kw = kw.rstrip("/")
                if normalized_kw in mapping and title:
                    base_path = mapping[normalized_kw].rstrip("/")
                    album_path = f"{base_path}/{title.strip()}"
                    album_paths.append(album_path)
                    continue  # Skip further processing for this kw
            if "/" in kw:
                folder, album = kw.split("/", 1)
                folder = folder.strip()
                album = album.strip()
                if folder in mapping:
                    base_path = mapping[folder].rstrip("/")
                    # Case 1: Folder/Album (album is non-empty)
                    if album:
                        album_path = f"{base_path}/{album}"
                        album_paths.append(album_path)
                    # Case 2: Folder/ (album is empty)
                    elif title:
                        album_path = f"{base_path}/{title.strip()}"
                        album_paths.append(album_path)
            # Case 3: Keyword is just a folder (no slash)
            elif kw in mapping and title:
                base_path = mapping[kw].rstrip("/")
                album_path = f"{base_path}/{title.strip()}"
                album_paths.append(album_path)
            # End normalization logic
        # Deduplicate
        return list(dict.fromkeys(album_paths))

    def _get_album_paths_for_city(self, city: str, title: str = None) -> list[str]:
        """Load album paths for a given city from album.yaml. If mapping ends with '/', append title as sub-album."""
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
            if city in mapping:
                mapped = mapping[city]
                result = []
                # If it's a list, handle each entry
                if isinstance(mapped, list):
                    for m in mapped:
                        if isinstance(m, str) and m.endswith("/") and title:
                            result.append(f"{m}{title.strip()}")
                        elif isinstance(m, str):
                            result.append(m)
                # If it's a string
                elif isinstance(mapped, str):
                    if mapped.endswith("/") and title:
                        result.append(f"{mapped}{title.strip()}")
                    else:
                        result.append(mapped)
                # Deduplicate
                return list(dict.fromkeys(result))
            else:
                self.logger.warning(f"No album mapping found for city: {city}")
                return []
        except Exception as e:
            self.logger.error(f"Error loading album.yaml: {e}")
            return []

    def _get_album_paths_for_location(self, location: str, title: str = None) -> list[str]:
        """Load album paths for a given location from album.yaml. If mapping ends with '/', append title as sub-album."""
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
            if location in mapping:
                mapped = mapping[location]
                result = []
                # If it's a list, handle each entry
                if isinstance(mapped, list):
                    for m in mapped:
                        if isinstance(m, str) and m.endswith("/") and title:
                            result.append(f"{m}{title.strip()}")
                        elif isinstance(m, str):
                            result.append(m)
                # If it's a string
                elif isinstance(mapped, str):
                    if mapped.endswith("/") and title:
                        result.append(f"{mapped}{title.strip()}")
                    else:
                        result.append(mapped)
                # Deduplicate
                return list(dict.fromkeys(result))
            else:
                self.logger.warning(f"No album mapping found for location: {location}")
                return []
        except Exception as e:
            self.logger.error(f"Error loading album.yaml: {e}")
            return []
            
    def _get_album_paths_for_state(self, state: str, title: str = None) -> list[str]:
        """Load album paths for a given state from album.yaml. If mapping ends with '/', append title as sub-album."""
        if not state:
            return []
            
        try:
            with open("album.yaml", "r") as f:
                mapping = yaml.safe_load(f)
            if state in mapping:
                mapped = mapping[state]
                result = []
                # If it's a list, handle each entry
                if isinstance(mapped, list):
                    for m in mapped:
                        if isinstance(m, str) and m.endswith("/") and title:
                            result.append(f"{m}{title.strip()}")
                        elif isinstance(m, str):
                            result.append(m)
                # If it's a string
                elif isinstance(mapped, str):
                    if mapped.endswith("/") and title:
                        result.append(f"{mapped}{title.strip()}")
                    else:
                        result.append(mapped)
                # Deduplicate
                self.logger.debug(f"Found album paths for state '{state}': {result}")
                return list(dict.fromkeys(result))
            else:
                self.logger.debug(f"No album mapping found for state: {state}")
                return []
        except Exception as e:
            self.logger.error(f"Error loading album.yaml for state lookup: {e}")
            return []

    def _import_to_photos(self, photo_path: Path, album_paths: list[str] = None) -> bool:
        """Import a photo into Apple Photos using album.yaml mapping and Folder/Album or Folder/ keywords."""
        from apple_photos_sdk.import_manager import ImportManager
        keywords = ImportManager()._get_original_keywords(photo_path)
        title = ImportManager()._get_original_title(photo_path)
        # --- Unified city and location extraction ---
        city = None
        location = None
        try:
            from processors.jpeg_processor import JPEGExifProcessor
            if photo_path.suffix.lower() in ['.jpg', '.jpeg']:
                exif_logger = JPEGExifProcessor(str(photo_path))
                exif_logger.read_exif()
                city = self.extract_city_from_exif(exif_logger.exif_data)
                # Extract location, city, state, country using get_location_data()
                location, _, state, _ = exif_logger.get_location_data()
                self.logger.info(f"[IMPORT] Extracted city for {photo_path}: {city}")
                self.logger.info(f"[IMPORT] Extracted state for {photo_path}: {state}")
                self.logger.info(f"[IMPORT] Extracted location for {photo_path}: {location}")
        except Exception as ex:
            self.logger.warning(f"Could not extract city/location from EXIF for import: {ex}")
        # Combine city, location, and keyword-based album paths, deduplicated
        keyword_album_paths = self._get_album_paths_from_keywords(keywords, title=title)
        combined_album_paths = []
        # Use city-based album paths if city and title exist
        if city and title:
            city_album_paths = self._get_album_paths_for_city(city, title=title)
            combined_album_paths.extend(city_album_paths)
        # Use state-based album paths if state and title exist
        if state and title:
            state_album_paths = self._get_album_paths_for_state(state, title=title)
            combined_album_paths.extend([p for p in state_album_paths if p not in combined_album_paths])
        # Use location-based album paths if location and title exist
        if location and title:
            location_album_paths = self._get_album_paths_for_location(location, title=title)
            combined_album_paths.extend([p for p in location_album_paths if p not in combined_album_paths])
        # Use category-based album paths from title if title exists and has format "Category: Details"
        if title:
            category_album_paths = self._get_category_based_album_paths(title, keywords=keywords)
            if category_album_paths:
                self.logger.info(f"Adding category-based album paths: {category_album_paths}")
                combined_album_paths.extend([p for p in category_album_paths if p not in combined_album_paths])
        if album_paths is not None:
            combined_album_paths.extend([p for p in album_paths if p not in combined_album_paths])
        if keyword_album_paths:
            combined_album_paths.extend([p for p in keyword_album_paths if p not in combined_album_paths])
        # Final deduplication
        combined_album_paths = list(dict.fromkeys(combined_album_paths))
        
        # Detailed output of all album paths at the latest possible point
        photo_name = photo_path.name
        if combined_album_paths:
            self.logger.info(f"\n============= ALBUM DESTINATIONS FOR {photo_name} =============")
            print(f"\n📸 PLACING IMAGE: {photo_name}")
            print(f"📁 INTO {len(combined_album_paths)} ALBUM(S):")
            for i, path in enumerate(combined_album_paths, 1):
                self.logger.info(f"  Album #{i}: {path}")
                print(f"  {i}. {path}")
            print("============================================\n")
            self.logger.info("=====================================================")
        else:
            self.logger.warning(f"No album paths resolved for import: {photo_path}")
            print(f"⚠️ WARNING: No album paths found for {photo_name}")
            
        success = ApplePhotos().import_photo(photo_path, album_paths=combined_album_paths)
        if success:
            self.logger.info(f"Successfully imported {photo_path} to Apple Photos")
            return True
        else:
            self.logger.error(f"Failed to import {photo_path} to Apple Photos")
            return False

    def _get_category_based_album_paths(self, title: str, keywords: list[str] = None) -> list[str]:
        """
        Parse photo title for category-based album paths.
        If title has format "Category: Details", dynamically create album path
        in format "02/Category/Full Title" without consulting album.yaml.
        
        Args:
            title: Photo title to parse
            keywords: Optional list of keywords to avoid duplication with keyword-based paths
            
        Returns:
            list[str]: List of album paths derived from title category
        """
        if not title:
            return []
        
        # Skip title-based processing if the title is already being used as a keyword
        # This prevents duplicate albums when both title and keyword contain the same text
        if keywords and title in keywords:
            self.logger.info(f"Skipping title processing for '{title}' as it's already a keyword")
            return []
            
        # Allowing both title-based and keyword-based album paths to co-exist
        # No skip logic here - both paths will be created as needed
        
        # Check for "Category: Details" format (single colon followed by space)
        if ":" in title and title.count(":") == 1 and ": " in title:
            category = title.split(": ")[0].strip()
            self.logger.info(f"Extracted category '{category}' from title '{title}'")
            
            if category:
                # Dynamic path creation - use CATEGORY_PREFIX from config and create folder based on category
                # Do not consult album.yaml - create this dynamically
                album_path = f"{CATEGORY_PREFIX}/{category}/{title}"
                self.logger.info(f"Created dynamic category-based album path: {album_path}")
                return [album_path]
                
        return []
    
    def extract_city_from_exif(self, exif_data: dict) -> str:
        """Try to extract city from all common EXIF fields."""
        for key in [
            'IPTC:City', 'XMP:City', 'EXIF:City', 'File:City',
            'IPTC:Sub-location', 'XMP:Location', 'XMP:State', 'IPTC:Province-State'
        ]:
            city = exif_data.get(key)
            if city:
                return city
        return None

    def _perform_transfer(self, file_path: Path, dest_dir: Path, album_paths: list[str] = None) -> bool:
        """
        Transfer a file to its destination.
        """
        self.logger.info(f"[TRANSFER] _perform_transfer called for {file_path} to {dest_dir} with album_paths: {album_paths}")
        try:
            # First move file to destination
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / file_path.name
            self.logger.debug(f"Moving file from {file_path} to {dest_path}")
            file_path.rename(dest_path)
            self.logger.info(f"Successfully moved file to {dest_path}")
            
            if ENABLE_APPLE_PHOTOS and dest_dir in APPLE_PHOTOS_PATHS:
                self.logger.debug(f"Importing {dest_path} to Apple Photos")
                return self._import_to_photos(dest_path, album_paths=album_paths)
            elif dest_dir in APPLE_PHOTOS_PATHS:
                self.logger.info(f"Apple Photos processing is disabled. Skipping import of {dest_path}")
            
            return True
        except Exception as e:
            self.logger.error(f"Transfer failed for {file_path}: {e}")
            return False

    def transfer_file(self, file_path: Path, album_paths: list[str] = None) -> bool:
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
            album_paths: Optional list of album paths to use for import (city-based mapping)
            
        Returns:
            bool: True if transfer succeeded, False otherwise
        """
        self.logger.info(f"[TRANSFER] transfer_file called for {file_path} with album_paths: {album_paths}")
        try:
            # Check if source is an Apple Photos directory
            if ENABLE_APPLE_PHOTOS and any(file_path.parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                # Skip validation for Apple Photos imports
                self.logger.info(f"Importing to Apple Photos: {file_path}")
                return self._import_to_photos(file_path, album_paths=album_paths)
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
            # Log EXIF data before moving
            try:
                from processors.jpeg_processor import JPEGExifProcessor
                if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                    exif_logger = JPEGExifProcessor(str(file_path))
                    exif_logger.read_exif()
                    self.logger.info(f"[EXIF BEFORE MOVE] {file_path}: {exif_logger.exif_data}")
            except Exception as ex:
                self.logger.warning(f"Could not log EXIF before move: {ex}")
            # Move file
            result = self._perform_transfer(file_path, dest_dir, album_paths=album_paths)
            # Log EXIF data after moving
            try:
                if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                    moved_path = dest_dir / file_path.name
                    exif_logger_after = JPEGExifProcessor(str(moved_path))
                    exif_logger_after.read_exif()
                    self.logger.info(f"[EXIF AFTER MOVE] {moved_path}: {exif_logger_after.exif_data}")
            except Exception as ex:
                self.logger.warning(f"Could not log EXIF after move: {ex}")
            return result
        except Exception as e:
            self.logger.error(f"Transfer failed for {file_path}: {e}")
            return False
    
    def transfer_asset(self, asset) -> bool:
        """
        Transfer an Apple Photos asset by applying album placement logic.
        Follows the same pattern as transfer_file() but for Apple Photos assets.
        
        Args:
            asset: Apple Photos PHAsset object
            
        Returns:
            bool: True if transfer succeeded, False otherwise
        """
        try:
            self.logger.info(f"[TRANSFER] transfer_asset called for asset: {asset.localIdentifier()}")
            
            # Extract metadata from Apple Photos asset
            metadata = self._extract_metadata_from_asset(asset)
            self.logger.info(f"[TRANSFER] Extracted metadata: {metadata}")
            
            # Apply existing album placement logic using extracted metadata
            album_paths = self._get_album_paths_for_asset_metadata(metadata)
            
            if album_paths:
                self.logger.info(f"[TRANSFER] Calculated album paths: {album_paths}")
                self.logger.info(f"[TRANSFER] Album paths type check: {[type(path) for path in album_paths]}")
                
                # Validate album paths are strings
                validated_paths = []
                for path in album_paths:
                    if isinstance(path, str):
                        validated_paths.append(path)
                    else:
                        self.logger.error(f"[TRANSFER] Invalid album path type: {type(path)} - {path}")
                        return False
                
                # Actually create albums and add asset to them
                asset_id = asset.localIdentifier()
                self.logger.info(f"[TRANSFER] Asset ID: {asset_id}")
                self.logger.info(f"[TRANSFER] Validated album paths: {validated_paths}")
                success = self.album_manager.add_to_albums(asset_id, validated_paths)
                
                if success:
                    self.logger.info(f"[TRANSFER] Successfully added asset to albums: {album_paths}")
                    return True
                else:
                    self.logger.error(f"[TRANSFER] Failed to add asset to some albums: {album_paths}")
                    return False
            else:
                self.logger.info(f"[TRANSFER] No album paths generated for asset")
                return True  # Not an error - just no placement rules matched
                
        except Exception as e:
            self.logger.error(f"Transfer failed for asset {asset.localIdentifier()}: {e}")
            return False
    
    def _extract_metadata_from_asset(self, asset) -> dict:
        """Extract metadata from Apple Photos asset for album placement."""
        try:
            with autorelease_pool():
                metadata = {
                    'title': asset.valueForKey_('title'),
                    'keywords': self._get_asset_keywords(asset),
                    'city': self._get_asset_city(asset),
                    'date': asset.creationDate(),
                    'media_type': 'photo' if asset.mediaType() == Photos.PHAssetMediaTypeImage else 'video'
                }
                return metadata
        except Exception as e:
            self.logger.error(f"Error extracting metadata from asset: {e}")
            return {}
    
    def _get_asset_keywords(self, asset) -> list[str]:
        """Extract keywords from Apple Photos asset using PhotoKit."""
        try:
            # Try to extract real keywords from Apple Photos
            real_keywords = self._extract_real_keywords_from_asset(asset)
            if real_keywords:
                self.logger.info(f"[PHOTOKIT] Extracted real keywords from asset: {real_keywords}")
                return real_keywords
            
            # FALLBACK TESTING: Simulate keywords based on title for testing category-based keywords
            # This allows us to test the keyword-based category logic when PhotoKit doesn't find keywords
            title = asset.valueForKey_('title')
            if title:
                # For testing: if title contains category patterns, simulate as keyword too
                # This demonstrates how keyword-based categories would work
                if title.startswith(("Party:", "Travel:", "Event:", "RTPC:", "Work:", "Family:", "Birthday:")):
                    self.logger.info(f"[TESTING] Simulating keyword from title: {title}")
                    return [title]  # Simulate the title as a keyword for testing
                
                # Enhanced: Also detect category words in titles (without colon requirement)
                category_words = ["Birthday", "Party", "Travel", "Event", "Work", "Family", "Wedding", "Vacation"]
                for category in category_words:
                    if category.lower() in title.lower():
                        simulated_keyword = f"{category}: {title}"
                        self.logger.info(f"[TESTING] Simulating category keyword from title: {simulated_keyword}")
                        return [simulated_keyword]
            
            return []
        except Exception as e:
            self.logger.debug(f"Could not extract keywords from asset: {e}")
            return []
    
    def _extract_real_keywords_from_asset(self, asset) -> list[str]:
        """Extract real keywords from Apple Photos database."""
        try:
            asset_uuid = asset.localIdentifier().split('/')[0]  # Extract UUID from identifier
            self.logger.debug(f"Asset UUID for keyword lookup: {asset_uuid}")
            
            # Find the Photos library database
            photos_db_path = self._find_photos_database()
            if not photos_db_path:
                self.logger.debug("Could not find Photos database")
                return []
            
            # Query the database for keywords
            keywords = self._query_keywords_from_database(photos_db_path, asset_uuid)
            if keywords:
                self.logger.debug(f"Found keywords in database: {keywords}")
                return keywords
            
            return []
                
        except Exception as e:
            self.logger.debug(f"Real keyword extraction failed: {e}")
            return []
    
    def _find_photos_database(self) -> str | None:
        """Find the Apple Photos database file."""
        try:
            # Common Photos library locations
            home = Path.home()
            possible_paths = [
                home / "Pictures" / "Photos Library.photoslibrary" / "database" / "Photos.sqlite",
                home / "Pictures" / "Photos Library.photoslibrary" / "database" / "photos.db",
            ]
            
            for path in possible_paths:
                if path.exists():
                    self.logger.debug(f"Found Photos database at: {path}")
                    return str(path)
            
            # Try to find any .photoslibrary directory
            pictures_dir = home / "Pictures"
            if pictures_dir.exists():
                for item in pictures_dir.iterdir():
                    if item.is_dir() and item.name.endswith('.photoslibrary'):
                        db_path = item / "database" / "Photos.sqlite"
                        if db_path.exists():
                            self.logger.debug(f"Found Photos database at: {db_path}")
                            return str(db_path)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error finding Photos database: {e}")
            return None
    
    def _query_keywords_from_database(self, db_path: str, asset_uuid: str) -> list[str]:
        """Query keywords from Photos database for a specific asset."""
        try:
            keywords = []
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # First, explore the database schema to find the correct table names
                self.logger.debug("Exploring Photos database schema...")
                
                # Get all table names
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = cursor.fetchall()
                
                keyword_tables = []
                asset_tables = []
                
                for table in tables:
                    table_name = table[0]
                    if 'keyword' in table_name.lower():
                        keyword_tables.append(table_name)
                    if 'asset' in table_name.lower():
                        asset_tables.append(table_name)
                
                self.logger.debug(f"Found keyword-related tables: {keyword_tables}")
                self.logger.debug(f"Found asset-related tables: {asset_tables}")
                
                # Explore the structure of the Z_1KEYWORDS table
                if 'Z_1KEYWORDS' in keyword_tables:
                    try:
                        cursor.execute("PRAGMA table_info(Z_1KEYWORDS)")
                        columns = cursor.fetchall()
                        self.logger.debug(f"Z_1KEYWORDS table structure: {[col[1] for col in columns]}")
                    except Exception as e:
                        self.logger.debug(f"Could not get Z_1KEYWORDS structure: {e}")
                
                # Explore the structure of the ZKEYWORD table
                if 'ZKEYWORD' in keyword_tables:
                    try:
                        cursor.execute("PRAGMA table_info(ZKEYWORD)")
                        columns = cursor.fetchall()
                        self.logger.debug(f"ZKEYWORD table structure: {[col[1] for col in columns]}")
                    except Exception as e:
                        self.logger.debug(f"Could not get ZKEYWORD structure: {e}")
                
                # Try different possible table name combinations based on discovered schema
                possible_queries = [
                    # Query based on discovered schema: Z_1KEYWORDS has Z_1ASSETATTRIBUTES and Z_51KEYWORDS
                    """
                    SELECT DISTINCT k.ZTITLE
                    FROM ZKEYWORD k
                    JOIN Z_1KEYWORDS ak ON k.Z_PK = ak.Z_51KEYWORDS
                    JOIN ZADDITIONALASSETATTRIBUTES attr ON ak.Z_1ASSETATTRIBUTES = attr.Z_PK
                    JOIN ZASSET a ON attr.ZASSET = a.Z_PK
                    WHERE a.ZUUID = ?
                    """,
                    # Alternative: try direct asset connection
                    """
                    SELECT DISTINCT k.ZTITLE
                    FROM ZKEYWORD k
                    JOIN Z_1KEYWORDS ak ON k.Z_PK = ak.Z_51KEYWORDS
                    JOIN ZASSET a ON ak.Z_1ASSETATTRIBUTES = a.Z_PK
                    WHERE a.ZUUID = ?
                    """,
                    # Fallback: original patterns
                    """
                    SELECT DISTINCT k.ZTITLE
                    FROM ZKEYWORD k
                    JOIN Z_1KEYWORDS ak ON k.Z_PK = ak.Z_51KEYWORDS
                    JOIN ZASSET a ON ak.Z_1ASSETATTRIBUTES = a.ZADDITIONALATTRIBUTES
                    WHERE a.ZUUID = ?
                    """
                ]
                
                # Try each query until one works
                for i, query in enumerate(possible_queries):
                    try:
                        self.logger.debug(f"Trying query variant {i+1}")
                        cursor.execute(query, (asset_uuid,))
                        results = cursor.fetchall()
                        
                        for row in results:
                            if row[0]:  # ZTITLE is not null
                                keywords.append(row[0])
                        
                        if keywords:
                            self.logger.debug(f"Query variant {i+1} succeeded, found {len(keywords)} keywords")
                            break
                            
                    except sqlite3.Error as e:
                        self.logger.debug(f"Query variant {i+1} failed: {e}")
                        continue
                
                return keywords
                
        except sqlite3.Error as e:
            self.logger.debug(f"SQLite error querying keywords: {e}")
            return []
        except Exception as e:
            self.logger.debug(f"Error querying keywords from database: {e}")
            return []
    
    def _extract_keywords_from_photokit(self, asset) -> list[str]:
        """Extract keywords using PhotoKit's PHContentEditingInput and metadata."""
        try:
            with autorelease_pool():
                keywords = []
                
                # Method 1: Try PHAssetResource for metadata
                resources = Photos.PHAssetResource.assetResourcesForAsset_(asset)
                for resource in resources:
                    if resource.type() == Photos.PHAssetResourceTypePhoto:
                        # Try to get metadata from resource
                        # Note: This might require additional API calls that aren't directly available
                        pass
                
                # Method 2: Try to use PHContentEditingInput (requires async handling)
                # This is more complex and might need to be implemented differently
                # For now, we'll focus on the simpler approaches
                
                # Method 3: Check if keywords are stored in any accessible properties
                # Try various potential keyword properties
                potential_keyword_properties = [
                    'keywords', 'tags', 'subject', 'description', 'caption'
                ]
                
                for prop in potential_keyword_properties:
                    try:
                        value = asset.valueForKey_(prop)
                        if value:
                            # Filter out non-string values and PHAsset objects
                            if isinstance(value, list):
                                for item in value:
                                    if isinstance(item, str) and not item.startswith('<PHAsset'):
                                        keywords.append(item)
                            elif isinstance(value, str) and not value.startswith('<PHAsset'):
                                # Split on common delimiters
                                keywords.extend([kw.strip() for kw in value.split(',') if kw.strip()])
                    except:
                        continue  # Property doesn't exist or isn't accessible
                
                return list(set(keywords))  # Remove duplicates
                
        except Exception as e:
            self.logger.debug(f"PhotoKit keyword extraction failed: {e}")
            return []
    
    def _get_asset_city(self, asset) -> str | None:
        """Extract city from Apple Photos asset location."""
        try:
            location = asset.location()
            if location:
                return location.locality()
            return None
        except Exception as e:
            self.logger.debug(f"Could not extract city from asset: {e}")
            return None
    
    def _get_album_paths_for_asset_metadata(self, metadata: dict) -> list[str]:
        """Apply existing album placement logic to Apple Photos asset metadata."""
        album_paths = []
        
        try:
            # Apply keyword-based rules (when keywords become available)
            if metadata.get('keywords'):
                keyword_paths = self._get_album_paths_from_keywords(
                    metadata['keywords'], metadata.get('title')
                )
                album_paths.extend(keyword_paths)
                
                # Also check for category-based keywords (e.g., "Party: Bday 1924")
                category_keyword_paths = self._get_category_paths_from_keywords(
                    metadata['keywords']
                )
                album_paths.extend(category_keyword_paths)
            
            # Apply city-based rules
            if metadata.get('city'):
                city_paths = self._get_album_paths_for_city(
                    metadata['city'], metadata.get('title')
                )
                album_paths.extend(city_paths)
            
            # Apply title-based rules (handles "Category: Details" format)
            if metadata.get('title'):
                title_paths = self._get_category_based_album_paths(
                    metadata['title'], metadata.get('keywords', [])
                )
                album_paths.extend(title_paths)
            
            # Remove duplicates while preserving order
            return list(dict.fromkeys(album_paths))
            
        except Exception as e:
            self.logger.error(f"Error calculating album paths for metadata: {e}")
            return []
    
    def _get_category_paths_from_keywords(self, keywords: list[str]) -> list[str]:
        """Extract category-based album paths from keywords (e.g., 'Party: Bday 1924')."""
        album_paths = []
        
        try:
            for keyword in keywords:
                # Check if keyword follows "Category: Details" format
                if ":" in keyword and keyword.count(":") == 1 and ": " in keyword:
                    category = keyword.split(": ")[0].strip()
                    album_path = f"{CATEGORY_PREFIX}/{category}/{keyword}"
                    album_paths.append(album_path)
                    self.logger.info(f"Extracted category '{category}' from keyword '{keyword}'")
                    self.logger.info(f"Created dynamic category-based album path: {album_path}")
            
            return album_paths
            
        except Exception as e:
            self.logger.error(f"Error extracting category paths from keywords: {e}")
            return []
