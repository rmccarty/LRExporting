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
    
    def _has_xmp_file(self, file_path: Path) -> bool:
        """Check if a video file has an associated XMP file."""
        # Check for .xmp extension
        xmp_path = file_path.with_suffix('.xmp')
        if xmp_path.exists():
            return True
            
        # Check for .MOV.xmp or .mp4.xmp pattern
        xmp_path = Path(str(file_path) + '.xmp')
        return xmp_path.exists()
    
    def process_file(self, file_path):
        """Process a single video file."""
        try:
            file_path = Path(file_path)
            if not self._has_xmp_file(file_path):
                return  # Skip if no XMP file
            
            # Process video
            self.logger.info(f"Found new video: {file_path.name}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
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
            # Skip if no XMP file
            if not self._has_xmp_file(file_path):
                continue
                
            self.logger.info(f"Found new video: {file_path.name}")
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
            processor.process_video()
