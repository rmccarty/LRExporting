#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
from datetime import datetime
import shutil
import time
import xml.etree.ElementTree as ET
from mutagen.mp4 import MP4
import re  
import glob
import os
import fcntl
from PIL import Image
from datetime import timedelta
from abc import ABC, abstractmethod

from config import (
    WATCH_DIRS, 
    BOTH_INCOMING, 
    LOG_LEVEL, 
    SLEEP_TIME,
    XML_NAMESPACES,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX,
    JPEG_QUALITY,
    JPEG_COMPRESS,
    TRANSFER_PATHS,
    MIN_FILE_AGE
)

from watchers import BaseWatcher, TransferWatcher, DirectoryWatcher, VideoWatcher
from processors.media_processor import MediaProcessor
from processors.video_processor import VideoProcessor
from transfers import Transfer

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create watchers
    jpeg_watcher = DirectoryWatcher(
        watch_dirs=WATCH_DIRS,
        both_incoming_dir=BOTH_INCOMING
    )
    video_watcher = VideoWatcher(directories=WATCH_DIRS)
    transfer_watcher = TransferWatcher(directories=WATCH_DIRS)
    
    try:
        # Start watchers
        jpeg_watcher.running = True
        video_watcher.running = True
        transfer_watcher.running = True
        
        while jpeg_watcher.running and video_watcher.running and transfer_watcher.running:
            # Process both incoming directory first for JPEGs
            jpeg_watcher.process_both_incoming()
            
            # Check each directory
            for directory in WATCH_DIRS:
                # Check for JPEGs
                jpeg_watcher.check_directory(directory)
                # Check for videos
                video_watcher.check_directory(directory)
                # Check for transfers
                transfer_watcher.check_directory(directory)
                
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping watchers")
        jpeg_watcher.running = False
        video_watcher.running = False
        transfer_watcher.running = False