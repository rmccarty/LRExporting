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
    LOG_LEVEL, 
    SLEEP_TIME,
    XML_NAMESPACES,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX,
    TRANSFER_PATHS,
    MIN_FILE_AGE
)

from watchers import BaseWatcher, TransferWatcher, ApplePhotoWatcher
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
    transfer_watcher = TransferWatcher(directories=WATCH_DIRS)
    apple_photo_watcher = ApplePhotoWatcher()
    
    try:
        # Start watchers
        transfer_watcher.running = True
        apple_photo_watcher.running = True
        
        while transfer_watcher.running and apple_photo_watcher.running:
            # Reset TransferWatcher queue and check Apple Photos directories for __LRE files
            transfer_watcher.reset_queue_counter()
            transfer_watcher.check_apple_photos_dirs()
            
            # Check Apple Photos watching album
            apple_photo_watcher.check_album()
            
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping watchers")
        transfer_watcher.running = False
        apple_photo_watcher.running = False