#!/usr/bin/env python3

from pathlib import Path
import logging

from config import WATCH_DIRS, SLEEP_TIME, APPLE_PHOTOS_PATHS, ENABLE_APPLE_PHOTOS, WATCHER_QUEUE_SIZE, TRANSFER_BATCH_SIZE
from transfers import Transfer

class TransferWatcher:
    """Watches for _LRE files and transfers them to their destination directories, including Apple Photos imports."""
    
    def __init__(self, directories=None):
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
        self.transfer = Transfer()
        self.queue_size = WATCHER_QUEUE_SIZE
        self.processed_count = 0  # Track files processed in current cycle
    
    def reset_queue_counter(self):
        """Reset the processed count for a new cycle."""
        self.processed_count = 0
    
    def check_apple_photos_dirs(self):
        """Check Apple Photos directories for media files and transfer them."""
        if not ENABLE_APPLE_PHOTOS:
            return

        for photos_path in APPLE_PHOTOS_PATHS:
            print(f"🔄 TRANSFER WATCHER: Checking {photos_path} for media files...")
            self.check_directory(photos_path)
        
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
        
        # Import to Apple Photos Watcher album for further processing by Apple Photo Watcher
        return self.transfer.transfer_file(file_path)
    
    def process_batch(self, file_paths: list) -> list:
        """
        Process a batch of files together for improved efficiency.
        
        Args:
            file_paths: List of Path objects to process
            
        Returns:
            list: List of boolean results indicating success/failure for each file
        """
        if not file_paths:
            return []
            
        self.logger.info(f"Processing batch of {len(file_paths)} files")
        
        # Don't pre-validate files here - let transfer_file() handle validation
        # This allows Apple Photos directories to be processed correctly
        valid_files = file_paths
        results = [None] * len(file_paths)  # Will be updated with actual results
        
        # Group files by processing type for batch optimization
        apple_photos_files, regular_files = self._group_files_by_type(valid_files)
        
        # Process Apple Photos files in batches (most performance gain here)
        apple_photos_results = self._process_apple_photos_batch(apple_photos_files)
        
        # Process regular files (less optimization opportunity but still useful)
        regular_results = self._process_regular_batch(regular_files)
        
        # Merge results back to original order
        for i, file_path in enumerate(file_paths):
            if file_path in apple_photos_files:
                ap_index = apple_photos_files.index(file_path)
                results[i] = apple_photos_results[ap_index]
            elif file_path in regular_files:
                reg_index = regular_files.index(file_path)
                results[i] = regular_results[reg_index]
            else:
                # This shouldn't happen, but handle gracefully
                results[i] = False
        
        success_count = sum(1 for r in results if r)
        self.logger.info(f"Batch processing complete: {success_count}/{len(file_paths)} files successful")
        
        return results
    
    def _group_files_by_type(self, file_paths: list) -> tuple:
        """
        Group files into Apple Photos vs regular transfer categories.
        
        Args:
            file_paths: List of Path objects to group
            
        Returns:
            tuple: (apple_photos_files, regular_files)
        """
        apple_photos_files = []
        regular_files = []
        
        for file_path in file_paths:
            # Check if file should go to Apple Photos
            if ENABLE_APPLE_PHOTOS and any(file_path.parent == photos_path for photos_path in APPLE_PHOTOS_PATHS):
                apple_photos_files.append(file_path)
            else:
                regular_files.append(file_path)
        
        return apple_photos_files, regular_files
    
    def _process_apple_photos_batch(self, file_paths: list) -> list:
        """
        Process a batch of files destined for Apple Photos.
        
        Args:
            file_paths: List of Path objects for Apple Photos import
            
        Returns:
            list: List of boolean results for each file
        """
        if not file_paths:
            return []
        
        self.logger.info(f"Processing Apple Photos batch of {len(file_paths)} files")
        results = []
        
        # For now, process individually but with batch logging
        # TODO: Implement true batch Apple Photos import in Transfer class
        for file_path in file_paths:
            try:
                result = self.transfer.transfer_file(file_path)
                results.append(result)
                if result:
                    self.logger.debug(f"✓ Apple Photos import successful: {file_path.name}")
                else:
                    self.logger.warning(f"✗ Apple Photos import failed: {file_path.name}")
            except Exception as e:
                self.logger.error(f"✗ Error processing Apple Photos file {file_path.name}: {e}")
                results.append(False)
        
        return results
    
    def _process_regular_batch(self, file_paths: list) -> list:
        """
        Process a batch of files for regular transfer.
        
        Args:
            file_paths: List of Path objects for regular transfer
            
        Returns:
            list: List of boolean results for each file
        """
        if not file_paths:
            return []
        
        self.logger.info(f"Processing regular transfer batch of {len(file_paths)} files")
        results = []
        
        # Process each file individually (regular transfers are already fast)
        for file_path in file_paths:
            try:
                result = self.transfer.transfer_file(file_path)
                results.append(result)
                if result:
                    self.logger.debug(f"✓ Regular transfer successful: {file_path.name}")
                else:
                    self.logger.warning(f"✗ Regular transfer failed: {file_path.name}")
            except Exception as e:
                self.logger.error(f"✗ Error processing regular file {file_path.name}: {e}")
                results.append(False)
        
        return results

        
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
            # Check for __LRE files only (both regular and Apple Photos directories)
            print(f"🔄 TRANSFER WATCHER: Checking {directory} for __LRE files... (Queue: {self.processed_count}/{self.queue_size})")
            
            batch = []
            total_found = 0
            
            for file_path in directory.glob('*__LRE.*'):
                if self.processed_count >= self.queue_size:
                    # Process remaining batch before hitting queue limit
                    if batch:
                        self.process_batch(batch)
                        self.processed_count += len(batch)
                    print(f"   ⚠️  Queue limit reached ({self.queue_size} files) - {total_found} files found, {len(batch)} processed in final batch")
                    break
                
                total_found += 1
                batch.append(file_path)
                
                # Process batch when it reaches the configured size
                if len(batch) >= TRANSFER_BATCH_SIZE:
                    print(f"   📦 Processing batch of {len(batch)} files...")
                    try:
                        results = self.process_batch(batch)
                        successful = sum(1 for r in results if r)
                        if successful < len(batch):
                            print(f"   ⚠️  Batch partially successful: {successful}/{len(batch)} files")
                        else:
                            print(f"   ✅ Batch successful: {successful}/{len(batch)} files")
                    except Exception as e:
                        self.logger.error(f"Batch processing failed, falling back to individual processing: {e}")
                        # Fallback: process files individually
                        for file_path in batch:
                            try:
                                self.process_file(file_path)
                            except Exception as file_e:
                                self.logger.error(f"Individual file processing also failed for {file_path}: {file_e}")
                    
                    self.processed_count += len(batch)
                    batch.clear()
                    
                    # Check if we hit queue limit after processing this batch
                    if self.processed_count >= self.queue_size:
                        print(f"   ⚠️  Queue limit reached ({self.queue_size} files) after processing batch")
                        break
            
            # Process any remaining files in the final batch
            if batch:
                print(f"   📦 Processing final batch of {len(batch)} files...")
                try:
                    results = self.process_batch(batch)
                    successful = sum(1 for r in results if r)
                    if successful < len(batch):
                        print(f"   ⚠️  Final batch partially successful: {successful}/{len(batch)} files")
                    else:
                        print(f"   ✅ Final batch successful: {successful}/{len(batch)} files")
                except Exception as e:
                    self.logger.error(f"Final batch processing failed, falling back to individual processing: {e}")
                    # Fallback: process files individually
                    for file_path in batch:
                        try:
                            self.process_file(file_path)
                        except Exception as file_e:
                            self.logger.error(f"Individual file processing also failed for {file_path}: {file_e}")
                
                self.processed_count += len(batch)
                
            if total_found == 0:
                print(f"   ✅ No __LRE files to transfer in {directory.name}")
            else:
                print(f"   ✅ Processed {min(self.processed_count, total_found)} of {total_found} __LRE files in {directory.name}")
                
        except Exception as e:
            self.logger.error(f"Error checking directory {directory}: {e}")
