#!/usr/bin/env python3

"""
Incoming Watcher - Standalone program for processing incoming files

Monitors and processes files from:
1. Both_Incoming → distributes to Ron_Incoming + Claudia_Incoming 
2. Ron_Incoming → processes JPEGs/videos with metadata
3. Claudia_Incoming → processes JPEGs/videos with metadata

Outputs __LRE files ready for transfer to Apple Photos or other destinations.
"""

from pathlib import Path
import logging
import time
import shutil
import sys
from typing import Optional

# Import processors
from processors.jpeg_processor import JPEGExifProcessor
from processors.video_processor import VideoProcessor
import config


class IncomingWatcher:
    """
    Standalone watcher for incoming directories that processes files independently.
    """
    
    def __init__(self, 
                 ron_incoming: Optional[str] = None,
                 claudia_incoming: Optional[str] = None, 
                 both_incoming: Optional[str] = None,
                 sleep_time: int = 10):
        """Initialize the incoming watcher."""
        self.ron_incoming = Path(ron_incoming or config.RON_INCOMING)
        self.claudia_incoming = Path(claudia_incoming or config.CLAUDIA_INCOMING) 
        self.both_incoming = Path(both_incoming or config.BOTH_INCOMING)
        self.sleep_time = sleep_time
        
        # File patterns
        self.jpeg_patterns = ['*.[Jj][Pp][Gg]', '*.[Jj][Pp][Ee][Gg]']
        self.video_patterns = ['*.mp4', '*.mov', '*.m4v', '*.mpg', '*.mpeg', '*.MP4', '*.MOV', '*.M4V', '*.MPG', '*.MPEG']
        
        # Incoming directories to process
        self.incoming_directories = [self.ron_incoming, self.claudia_incoming]
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Sequence counter for filename uniqueness
        self._sequence_counter = 0
        
        print(f"🚀 INCOMING WATCHER: Initialized")
        print(f"   📁 Ron Incoming: {self.ron_incoming}")
        print(f"   📁 Claudia Incoming: {self.claudia_incoming}")
        print(f"   📁 Both Incoming: {self.both_incoming}")
        print(f"   ⏰ Sleep Time: {self.sleep_time} seconds")
        
    def _is_file_ready(self, file_path: Path, min_file_age: int = 5) -> tuple[bool, str]:
        """
        Check if file is ready for distribution.
        
        Args:
            file_path: Path to the file to check
            min_file_age: Minimum age in seconds before file is considered ready
            
        Returns:
            tuple: (is_ready, reason)
        """
        try:
            # Check if file exists
            if not file_path.exists():
                return False, "File does not exist"
                
            # Check if it's a regular file
            if not file_path.is_file():
                return False, "Not a regular file"
                
            # Check file size
            file_size = file_path.stat().st_size
            if file_size == 0:
                return False, "Zero-byte file"
            
            # Check file age
            import time
            file_age = time.time() - file_path.stat().st_mtime
            if file_age < min_file_age:
                return False, f"File too new (< {min_file_age} seconds old)"
            
            # Check if file is locked
            try:
                with open(file_path, 'r+'):
                    pass
            except IOError:
                return False, "File is locked"
            
            return True, "Ready"
            
        except Exception as e:
            return False, f"Error checking file: {e}"
        
    def _get_next_sequence(self) -> str:
        """Get next sequence number for filename uniqueness."""
        self._sequence_counter += 1
        return f"{self._sequence_counter:04d}"
        
    def process_both_incoming(self) -> bool:
        """
        Check Both_Incoming directory and copy files to individual incoming directories.
        
        Returns:
            bool: True if files were found (even if locked), False if no files
        """
        if not self.both_incoming.exists():
            self.logger.warning(f"Both_Incoming directory does not exist: {self.both_incoming}")
            return False
            
        print(f"🔍 BOTH_INCOMING: Checking {self.both_incoming} for files to distribute...")
        found_files = False
        file_count = 0
        
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob("*"):
                if not file.is_file():
                    continue
                    
                found_files = True  # Mark as found even if not ready
                file_count += 1
                
                # Check if file is ready for distribution
                is_ready, reason = self._is_file_ready(file)
                if is_ready:
                    print(f"   📤 Distributing: {file.name}")
                    
                    # Copy the file to all incoming directories
                    for incoming_dir in self.incoming_directories:
                        # Ensure destination directory exists
                        incoming_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = incoming_dir / file.name
                        shutil.copy(file, dest_path)
                        self.logger.info(f"Copied {file.name} to {incoming_dir.name} directory.")
                        print(f"      → Copied to {incoming_dir.name}")
                    
                    # Delete the original file
                    file.unlink()
                    self.logger.info(f"Deleted {file.name} from Both_Incoming.")
                    print(f"      ✓ Deleted from Both_Incoming")
                else:
                    self.logger.warning(f"File {file.name} not ready for distribution: {reason}")
                    print(f"   ⏳ Skipping {file.name}: {reason}")
                    continue  # Skip to the next file
        
        except Exception as e:
            self.logger.error(f"Error processing Both_Incoming: {e}")
            found_files = False
        
        if file_count == 0:
            print(f"   ✅ No files to distribute from Both_Incoming")
        
        return found_files
    
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file (JPEG or video).
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            bool: True if processing succeeded, False otherwise
        """
        if not file_path.is_file():
            return False
            
        # Check for zero-byte files
        if file_path.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {str(file_path)}")
            print(f"   ⚠️  Skipping zero-byte file: {file_path.name}")
            return False
            
        try:
            # Skip files that are already processed
            if "__LRE" in file_path.name:
                self.logger.debug(f"Skipping already processed file: {file_path}")
                return True
                
            print(f"   🎨 PROCESSING: {file_path.name}")
            
            # Process based on file type
            if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                return self._process_jpeg(file_path)
            elif any(file_path.match(pattern) for pattern in self.video_patterns):
                return self._process_video(file_path)
            else:
                self.logger.debug(f"Unsupported file type: {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
            print(f"   ❌ Error processing {file_path.name}: {e}")
            return False
    
    def _process_jpeg(self, file_path: Path) -> bool:
        """Process a JPEG file with metadata extraction and renaming."""
        try:
            sequence = self._get_next_sequence()
            processor = JPEGExifProcessor(str(file_path), sequence=sequence)
            new_path = processor.process_image()
            
            self.logger.info(f"JPEG processed successfully: {new_path}")
            print(f"      ✓ Processed to: {Path(new_path).name}")
            return True
            
        except ValueError as e:
            if "not ready for processing" in str(e):
                self.logger.warning(f"JPEG file not ready, skipping: {file_path} - {e}")
                print(f"      ⏳ File not ready - will retry later: {file_path.name}")
                return False
            else:
                raise
        except Exception as e:
            self.logger.error(f"Error processing JPEG {file_path}: {e}")
            print(f"      ❌ JPEG processing failed: {e}")
            return False
    
    def _process_video(self, file_path: Path) -> bool:
        """Process a video file with metadata extraction and renaming."""
        try:
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
            success = processor.process_video()
            
            if success:
                # Get the new filename (processor renames the file)
                new_name = processor.generate_filename()
                new_path = file_path.parent / new_name
                self.logger.info(f"Video processed successfully: {new_path}")
                print(f"      ✓ Processed to: {new_path.name}")
                return True
            else:
                self.logger.warning(f"Video processing failed: {file_path}")
                print(f"      ❌ Video processing failed: {file_path.name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing video {file_path}: {e}")
            print(f"      ❌ Video processing failed: {e}")
            return False
    
    def check_directory(self, directory: Path) -> int:
        """
        Check a directory for files to process.
        
        Args:
            directory: Directory to check
            
        Returns:
            int: Number of files processed
        """
        if not directory.exists():
            self.logger.warning(f"Directory does not exist: {directory}")
            return 0
            
        try:
            print(f"🔍 INCOMING: Checking {directory.name} for files to process...")
            
            processed_count = 0
            
            # Process JPEG files
            for pattern in self.jpeg_patterns:
                for file_path in directory.glob(pattern):
                    if self.process_file(file_path):
                        processed_count += 1
                    
            # Process video files
            for pattern in self.video_patterns:
                for file_path in directory.glob(pattern):
                    if self.process_file(file_path):
                        processed_count += 1
            
            if processed_count == 0:
                print(f"   ✅ No new files to process in {directory.name}")
            else:
                print(f"   ✅ Processed {processed_count} files in {directory.name}")
                
            return processed_count
            
        except Exception as e:
            self.logger.error(f"Error checking directory {directory}: {e}")
            return 0
    
    def run_cycle(self) -> None:
        """Run one complete processing cycle."""
        print(f"\n{'='*60}")
        print(f"🚀 INCOMING WATCHER: Starting processing cycle")
        print(f"{'='*60}")
        
        total_processed = 0
        
        try:
            # Step 1: Process Both_Incoming distribution
            both_had_files = self.process_both_incoming()
            
            # Step 2: Process individual incoming directories
            for directory in self.incoming_directories:
                processed = self.check_directory(directory)
                total_processed += processed
            
            # Summary
            print(f"{'='*60}")
            print(f"✅ INCOMING WATCHER: Cycle complete")
            if total_processed > 0:
                print(f"   📊 Total files processed: {total_processed}")
            else:
                print(f"   📊 No files processed this cycle")
            print(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.error(f"Error during processing cycle: {e}")
            print(f"❌ INCOMING WATCHER: Cycle failed - {e}")
    
    def run(self) -> None:
        """Run the incoming watcher continuously."""
        print(f"\n🎬 INCOMING WATCHER: Starting continuous monitoring...")
        print(f"Press Ctrl+C to stop")
        
        try:
            while True:
                self.run_cycle()
                time.sleep(self.sleep_time)
                
        except KeyboardInterrupt:
            print(f"\n🛑 INCOMING WATCHER: Stopping...")
            self.logger.info("Incoming watcher stopped by user")


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler('incoming_watcher.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main entry point."""
    # Setup logging
    setup_logging("DEBUG")
    
    # Create and run the incoming watcher
    watcher = IncomingWatcher()
    watcher.run()


if __name__ == "__main__":
    main()