#!/usr/bin/env python3

import logging
import time

from config import (
    LOG_LEVEL, 
    SLEEP_TIME
)

from watchers import ApplePhotoWatcher

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create Apple Photo Watcher for processing Watching album
    apple_photo_watcher = ApplePhotoWatcher()
    
    try:
        # Start watcher
        apple_photo_watcher.running = True
        
        while apple_photo_watcher.running:
            # Check Apple Photos watching album for category detection and album placement
            apple_photo_watcher.check_album()
            
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping Apple Photo Watcher")
        apple_photo_watcher.running = False