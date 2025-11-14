#!/usr/bin/env python3

"""
Apple Watching Ingest - Imports __LRE files from Ron's Apple Photos directory into Watching album

Monitors Ron's Apple Photos directory for __LRE files and imports them into the Apple Photos
"Watching" album for further processing by lrexport.py.

Only handles the import step - all category detection and album placement logic remains in lrexport.py
"""

import logging
import time
from pathlib import Path
import sys
from typing import Optional

from config import APPLE_PHOTOS_PATHS, APPLE_PHOTOS_WATCHING, MIN_FILE_AGE, ENABLE_APPLE_PHOTOS
from apple_photos_sdk import ApplePhotos


class AppleWatchingIngest:
    """
    Imports __LRE files from Ron's Apple Photos directory into the Watching album.
    """
    
    def __init__(self, 
                 apple_photos_dir: Optional[Path] = None,
                 batch_size: int = 10,
                 min_file_age: int = None,
                 sleep_time: int = 10):
        """Initialize the Apple Watching ingester."""
        # Use the first Apple Photos path (Ron's directory) if not specified
        self.apple_photos_dir = apple_photos_dir or list(APPLE_PHOTOS_PATHS)[0]
        self.batch_size = batch_size
        self.min_file_age = min_file_age if min_file_age is not None else MIN_FILE_AGE
        self.sleep_time = sleep_time
        self.watching_album = str(APPLE_PHOTOS_WATCHING).rstrip('/')
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        print(f"📸 APPLE WATCHING INGEST: Initialized")
        print(f"   📁 Apple Photos directory: {self.apple_photos_dir}")
        print(f"   🎯 Target album: {self.watching_album}")
        print(f"   📦 Batch size: {self.batch_size}")
        print(f"   ⏰ Min file age: {self.min_file_age} seconds")
        print(f"   ⏰ Sleep time: {self.sleep_time} seconds")
        print(f"   🔧 Apple Photos enabled: {ENABLE_APPLE_PHOTOS}")
        
    def _is_file_old_enough(self, file_path: Path) -> bool:
        """
        Check if file is old enough to process.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            bool: True if file is old enough, False otherwise
        """
        try:
            import time as time_module
            file_age = time_module.time() - file_path.stat().st_mtime
            return file_age >= self.min_file_age
        except Exception as e:
            self.logger.error(f"Error checking file age for {file_path}: {e}")
            return False
            
    def _can_move_file(self, file_path: Path) -> tuple[bool, str]:
        """
        Check if a file can be imported (exists, is regular file, not zero bytes, old enough).
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            tuple: (can_import, reason)
        """
        if not file_path.exists():
            return False, "File does not exist"
            
        if not file_path.is_file():
            return False, "Not a regular file"
            
        if file_path.stat().st_size == 0:
            return False, "Zero-byte file"
            
        if not self._is_file_old_enough(file_path):
            return False, f"File too new (< {self.min_file_age} seconds old)"
            
        return True, "OK"
        
    def import_file_to_watching(self, file_path: Path) -> bool:
        """
        Import a single file to the Watching album.
        
        Args:
            file_path: Path to the file to import
            
        Returns:
            bool: True if import succeeded, False otherwise
        """
        try:
            # Check if file can be imported
            can_import, reason = self._can_move_file(file_path)
            if not can_import:
                self.logger.debug(f"Cannot import {file_path.name}: {reason}")
                return False
                
            # Check if Apple Photos is enabled
            if not ENABLE_APPLE_PHOTOS:
                self.logger.warning(f"Apple Photos processing is disabled. Skipping import of {file_path}")
                return False
                
            # Import to Apple Photos Watching album
            self.logger.info(f"Importing {file_path.name} to Apple Photos Watching album")
            print(f"📸 IMPORTING: {file_path.name}")
            print(f"📁 TO ALBUM: {self.watching_album}")
            
            success = ApplePhotos().import_photo(file_path, album_paths=[self.watching_album])
            
            if success:
                self.logger.info(f"Successfully imported {file_path} to Apple Photos Watching album")
                return True
            else:
                self.logger.error(f"Failed to import {file_path} to Apple Photos")
                return False
                
        except Exception as e:
            self.logger.error(f"Error importing file {file_path}: {e}")
            print(f"   ❌ Error importing {file_path.name}: {e}")
            return False
    
    def check_directory(self) -> int:
        """
        Check the Apple Photos directory for __LRE files and import them to Watching album.
        
        Returns:
            int: Number of files imported
        """
        if not self.apple_photos_dir.exists():
            self.logger.warning(f"Apple Photos directory does not exist: {self.apple_photos_dir}")
            return 0
            
        try:
            print(f"🔍 INGEST: Checking {self.apple_photos_dir.name} for __LRE files...")
            
            imported_count = 0
            found_count = 0
            skipped_count = 0
            
            # Look for __LRE files
            for file_path in self.apple_photos_dir.glob('*__LRE.*'):
                found_count += 1
                
                can_import, reason = self._can_move_file(file_path)
                if can_import:
                    if self.import_file_to_watching(file_path):
                        imported_count += 1
                    else:
                        skipped_count += 1
                else:
                    if "locked" in reason.lower() or "too new" in reason.lower():
                        print(f"   ⏳ Skipping {file_path.name}: {reason}")
                    skipped_count += 1
                    
            if found_count == 0:
                print(f"   ✅ No __LRE files found in {self.apple_photos_dir.name}")
            else:
                print(f"   ✅ Found {found_count}, imported {imported_count}, skipped {skipped_count}")
                
            return imported_count
            
        except Exception as e:
            self.logger.error(f"Error checking directory {self.apple_photos_dir}: {e}")
            return 0
    
    def process_batch(self, files: list[Path]) -> list[bool]:
        """
        Process a batch of files for import to Watching album.
        
        Args:
            files: List of file paths to process
            
        Returns:
            list[bool]: List of success/failure results
        """
        results = []
        
        print(f"   📦 Processing batch of {len(files)} files...")
        
        for file_path in files:
            success = self.import_file_to_watching(file_path)
            results.append(success)
            
        successful_count = sum(results)
        print(f"   ✅ Batch successful: {successful_count}/{len(files)} files")
        
        return results
    
    def check_directory_with_batching(self) -> int:
        """
        Check directory and process files in batches.
        
        Returns:
            int: Number of files imported
        """
        if not self.apple_photos_dir.exists():
            self.logger.warning(f"Apple Photos directory does not exist: {self.apple_photos_dir}")
            return 0
            
        try:
            print(f"🔍 INGEST: Checking {self.apple_photos_dir.name} for __LRE files...")
            
            # Collect all ready files
            ready_files = []
            found_count = 0
            skipped_count = 0
            
            for file_path in self.apple_photos_dir.glob('*__LRE.*'):
                found_count += 1
                
                can_import, reason = self._can_move_file(file_path)
                if can_import:
                    ready_files.append(file_path)
                else:
                    if "locked" in reason.lower() or "too new" in reason.lower():
                        print(f"   ⏳ Skipping {file_path.name}: {reason}")
                    skipped_count += 1
            
            if found_count == 0:
                print(f"   ✅ No __LRE files found in {self.apple_photos_dir.name}")
                return 0
                
            if not ready_files:
                print(f"   ✅ Found {found_count}, imported 0, skipped {skipped_count}")
                return 0
            
            # Process in batches
            imported_count = 0
            for i in range(0, len(ready_files), self.batch_size):
                batch = ready_files[i:i + self.batch_size]
                results = self.process_batch(batch)
                imported_count += sum(results)
            
            print(f"   ✅ Found {found_count}, imported {imported_count}, skipped {skipped_count}")
            return imported_count
            
        except Exception as e:
            self.logger.error(f"Error checking directory {self.apple_photos_dir}: {e}")
            return 0
    
    def run_cycle(self) -> None:
        """Run one complete ingest cycle."""
        print(f"\n{'='*60}")
        print(f"📸 APPLE WATCHING INGEST: Starting ingest cycle")
        print(f"{'='*60}")
        
        try:
            imported = self.check_directory_with_batching()
            
            # Summary
            print(f"{'='*60}")
            print(f"✅ APPLE WATCHING INGEST: Cycle complete")
            if imported > 0:
                print(f"   📊 Total files imported: {imported}")
            else:
                print(f"   📊 No files imported this cycle")
            print(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.error(f"Error during ingest cycle: {e}")
            print(f"❌ APPLE WATCHING INGEST: Cycle failed - {e}")
    
    def run(self) -> None:
        """Run the Apple Watching ingester continuously."""
        print(f"\n🎬 APPLE WATCHING INGEST: Starting continuous monitoring...")
        print(f"Press Ctrl+C to stop")
        
        try:
            while True:
                self.run_cycle()
                time.sleep(self.sleep_time)
                
        except KeyboardInterrupt:
            print(f"\n🛑 APPLE WATCHING INGEST: Stopping...")
            self.logger.info("Apple Watching ingester stopped by user")


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler('apple_watching_ingest.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main entry point."""
    # Setup logging
    setup_logging("DEBUG")
    
    # Create and run the Apple Watching ingester
    ingester = AppleWatchingIngest()
    ingester.run()


if __name__ == "__main__":
    main()