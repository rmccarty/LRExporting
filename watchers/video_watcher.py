#!/usr/bin/env python3

import os
import logging
from pathlib import Path

from config import WATCH_DIRS, SLEEP_TIME, VIDEO_PATTERN
from processors.video_processor import VideoProcessor
from watchers.base_watcher import BaseWatcher

class VideoWatcher(BaseWatcher):
    """
    A class to watch directories for video files.
    """
    
    def process_file(self, file_path):
        """Process a single video file."""
        try:
            # Check for XMP file
            xmp_path = os.path.splitext(file_path)[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = file_path + ".xmp"
                if not os.path.exists(xmp_path):
                    return  # Skip if no XMP file
            
            # Process video
            self.logger.info(f"Found new video: {os.path.basename(file_path)}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(file_path, sequence=sequence)
            processor.process_video()
            
        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new video files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        self.logger.info(f"\nChecking {directory} for new video files...")
        video_files = []
        # Handle both upper and lower case extensions
        for pattern in VIDEO_PATTERN:
            video_files.extend(directory.glob(pattern.lower()))
            video_files.extend(directory.glob(pattern.upper()))
        
        if video_files:
            self.logger.info(f"Found files: {[str(f) for f in video_files]}")
            
        for file_path in video_files:
            self.logger.info(f"Found new video: {file_path.name}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
            processor.process_video()
