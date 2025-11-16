#!/usr/bin/env python3

"""
Incoming Mover - Moves processed __LRE files from incoming directories to destinations

Monitors and transfers files from:
1. Ron_Incoming → Ron_Apple_Photos (for Apple Photos import)
2. Claudia_Incoming → Claudia_Transfer (local staging)

Additional features:
- iCloud Backfill: Maintains 50 files in iCloud OldPhotographs by moving oldest files
  from Claudia_Transfer when iCloud directory has fewer than target count

Only moves files that are not locked and have __LRE suffix.
"""

from pathlib import Path
import logging
import time
import shutil
import sys
from typing import Optional, Dict

from config import (
    TRANSFER_PATHS, 
    MIN_FILE_AGE, 
    CLAUDIA_INCOMING,
    ICLOUD_OLDPHOTOGRAPHS,
    ICLOUD_TARGET_FILE_COUNT
)
from datetime import datetime, timedelta

# Get Claudia's transfer directory from config
CLAUDIA_TRANSFER = TRANSFER_PATHS[CLAUDIA_INCOMING]


class IncomingMover:
    """
    Moves processed __LRE files from incoming directories to their destinations.
    """
    
    def __init__(self, 
                 transfer_paths: Optional[Dict[Path, Path]] = None,
                 min_file_age: int = None,
                 sleep_time: int = 2):
        """Initialize the incoming mover."""
        self.transfer_paths = transfer_paths or TRANSFER_PATHS
        self.min_file_age = min_file_age if min_file_age is not None else MIN_FILE_AGE
        self.sleep_time = sleep_time
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        print(f"🚚 INCOMING MOVER: Initialized")
        print(f"   📁 Transfer paths:")
        for source, dest in self.transfer_paths.items():
            print(f"      {source} → {dest}")
        print(f"   ⏰ Min file age: {self.min_file_age} seconds")
        print(f"   ⏰ Sleep time: {self.sleep_time} seconds")
        
    def _is_file_locked(self, file_path: Path) -> bool:
        """
        Check if a file is currently locked (being written).
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            bool: True if file is locked, False if available
        """
        try:
            with open(file_path, 'r+b'):
                return False  # File opened successfully - not locked
        except (IOError, OSError):
            return True  # File is locked or inaccessible
            
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
            age_threshold = datetime.now() - timedelta(seconds=self.min_file_age)
            return mtime <= age_threshold
        except Exception as e:
            self.logger.error(f"Error checking file age for {file_path}: {e}")
            return False
            
    def _can_move_file(self, file_path: Path) -> tuple[bool, str]:
        """
        Check if a file can be moved (not locked and old enough).
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            tuple: (can_move, reason)
        """
        if not file_path.exists():
            return False, "File does not exist"
            
        if not file_path.is_file():
            return False, "Not a regular file"
            
        if file_path.stat().st_size == 0:
            return False, "Zero-byte file"
            
        if not self._is_file_old_enough(file_path):
            return False, f"File too new (< {self.min_file_age} seconds old)"
            
        if self._is_file_locked(file_path):
            return False, "File is locked"
            
        return True, "OK"
        
    def move_file(self, file_path: Path, dest_dir: Path) -> bool:
        """
        Move a single file to its destination directory.
        
        Args:
            file_path: Source file path
            dest_dir: Destination directory
            
        Returns:
            bool: True if move succeeded, False otherwise
        """
        try:
            # Check if file can be moved
            can_move, reason = self._can_move_file(file_path)
            if not can_move:
                self.logger.debug(f"Cannot move {file_path.name}: {reason}")
                return False
                
            # Ensure destination directory exists
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Construct destination path
            dest_path = dest_dir / file_path.name
            
            # Check if destination already exists
            if dest_path.exists():
                self.logger.warning(f"Destination already exists: {dest_path}")
                return False
                
            # Move the file
            self.logger.info(f"Moving: {file_path} → {dest_path}")
            print(f"   📦 Moving: {file_path.name} → {dest_dir.name}")
            
            shutil.move(str(file_path), str(dest_path))
            
            # Check if original file still exists (can happen with iCloud destinations)
            if file_path.exists():
                self.logger.info(f"Original file still exists after move, deleting: {file_path}")
                file_path.unlink()
            
            self.logger.info(f"Successfully moved: {file_path.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error moving file {file_path}: {e}")
            print(f"   ❌ Error moving {file_path.name}: {e}")
            return False
    
    def check_directory(self, source_dir: Path, dest_dir: Path) -> int:
        """
        Check a source directory for __LRE files and move them to destination.
        
        Args:
            source_dir: Source directory to check
            dest_dir: Destination directory for files
            
        Returns:
            int: Number of files moved
        """
        if not source_dir.exists():
            self.logger.warning(f"Source directory does not exist: {source_dir}")
            return 0
            
        try:
            print(f"🔍 MOVER: Checking {source_dir.name} for __LRE files...")
            
            moved_count = 0
            found_count = 0
            skipped_count = 0
            
            # Look for __LRE files
            for file_path in source_dir.glob('*__LRE.*'):
                found_count += 1
                
                can_move, reason = self._can_move_file(file_path)
                if can_move:
                    if self.move_file(file_path, dest_dir):
                        moved_count += 1
                    else:
                        skipped_count += 1
                else:
                    if "locked" in reason.lower() or "too new" in reason.lower():
                        print(f"   ⏳ Skipping {file_path.name}: {reason}")
                    skipped_count += 1
                    
            if found_count == 0:
                print(f"   ✅ No __LRE files found in {source_dir.name}")
            else:
                print(f"   ✅ Found {found_count}, moved {moved_count}, skipped {skipped_count} in {source_dir.name}")
                
            return moved_count
            
        except Exception as e:
            self.logger.error(f"Error checking directory {source_dir}: {e}")
            return 0

    def _count_files_in_directory(self, directory: Path) -> int:
        """Count total files in a directory."""
        if not directory.exists():
            return 0
        try:
            return len([f for f in directory.iterdir() if f.is_file()])
        except Exception as e:
            self.logger.error(f"Error counting files in {directory}: {e}")
            return 0

    def backfill_icloud(self) -> int:
        """
        Backfill iCloud OldPhotographs directory from Claudia_Transfer if needed.
        
        Maintains ICLOUD_TARGET_FILE_COUNT files in iCloud by moving files
        from Claudia_Transfer when iCloud has fewer files.
        
        Returns:
            int: Number of files moved to iCloud
        """
        try:
            # Count current files in iCloud
            icloud_count = self._count_files_in_directory(ICLOUD_OLDPHOTOGRAPHS)
            
            # Check if backfill is needed
            if icloud_count >= ICLOUD_TARGET_FILE_COUNT:
                self.logger.debug(f"iCloud has {icloud_count} files (>= {ICLOUD_TARGET_FILE_COUNT}), no backfill needed")
                return 0
                
            # Calculate how many files to move
            files_needed = ICLOUD_TARGET_FILE_COUNT - icloud_count
            
            # Check if Claudia_Transfer has files available
            if not CLAUDIA_TRANSFER.exists():
                self.logger.warning(f"Claudia_Transfer directory does not exist: {CLAUDIA_TRANSFER}")
                return 0
                
            # Get available files from Claudia_Transfer (oldest first)
            available_files = []
            try:
                for file_path in CLAUDIA_TRANSFER.iterdir():
                    if file_path.is_file():
                        available_files.append(file_path)
                        
                # Sort by modification time (oldest first)
                available_files.sort(key=lambda f: f.stat().st_mtime)
                
            except Exception as e:
                self.logger.error(f"Error listing files in {CLAUDIA_TRANSFER}: {e}")
                return 0
            
            if not available_files:
                self.logger.debug(f"No files available in {CLAUDIA_TRANSFER} for backfill")
                return 0
                
            # Move files to iCloud
            files_to_move = min(files_needed, len(available_files))
            moved_count = 0
            
            print(f"🔄 ICLOUD BACKFILL: Need {files_needed} files, moving {files_to_move}")
            print(f"   📊 iCloud: {icloud_count} files, Transfer: {len(available_files)} files")
            
            for i in range(files_to_move):
                file_path = available_files[i]
                
                # Check if file can be moved
                can_move, reason = self._can_move_file(file_path)
                if not can_move:
                    self.logger.debug(f"Cannot move {file_path.name} to iCloud: {reason}")
                    continue
                    
                # Move to iCloud
                if self.move_file(file_path, ICLOUD_OLDPHOTOGRAPHS):
                    moved_count += 1
                    print(f"      ☁️  Moved {file_path.name} to iCloud")
                else:
                    self.logger.warning(f"Failed to move {file_path.name} to iCloud")
                    
            if moved_count > 0:
                print(f"   ✅ Backfilled {moved_count} files to iCloud")
            else:
                print(f"   ⚠️  No files could be moved to iCloud")
                
            return moved_count
            
        except Exception as e:
            self.logger.error(f"Error during iCloud backfill: {e}")
            print(f"   ❌ iCloud backfill failed: {e}")
            return 0
    
    def run_cycle(self) -> None:
        """Run one complete move cycle."""
        print(f"\n{'='*60}")
        print(f"🚚 INCOMING MOVER: Starting move cycle")
        print(f"{'='*60}")
        
        total_moved = 0
        
        try:
            # Process each configured transfer path
            for source_dir, dest_dir in self.transfer_paths.items():
                moved = self.check_directory(source_dir, dest_dir)
                total_moved += moved
            
            # Perform iCloud backfill
            backfilled = self.backfill_icloud()
            
            # Summary
            print(f"{'='*60}")
            print(f"✅ INCOMING MOVER: Cycle complete")
            if total_moved > 0:
                print(f"   📊 Total files moved: {total_moved}")
            else:
                print(f"   📊 No files moved this cycle")
            if backfilled > 0:
                print(f"   ☁️  iCloud backfilled: {backfilled}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.error(f"Error during move cycle: {e}")
            print(f"❌ INCOMING MOVER: Cycle failed - {e}")
    
    def run(self) -> None:
        """Run the incoming mover continuously."""
        print(f"\n🎬 INCOMING MOVER: Starting continuous monitoring...")
        print(f"Press Ctrl+C to stop")
        
        try:
            while True:
                self.run_cycle()
                time.sleep(self.sleep_time)
                
        except KeyboardInterrupt:
            print(f"\n🛑 INCOMING MOVER: Stopping...")
            self.logger.info("Incoming mover stopped by user")


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler('incoming_mover.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main entry point."""
    # Setup logging
    setup_logging("DEBUG")
    
    # Create and run the incoming mover
    mover = IncomingMover()
    mover.run()


if __name__ == "__main__":
    main()