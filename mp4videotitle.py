#!/usr/bin/env python3

# Requires: pip install mutagen
from mutagen.mp4 import MP4
import os
import time
from datetime import datetime

def log_message(message):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def add_metadata(file_path):
    video = MP4(file_path)
    
    # Generate title from filename
    title = os.path.splitext(os.path.basename(file_path))[0]
    title = title.replace("The McCartys ", "The McCartys: ")
    video["\xa9nam"] = title
    log_message(f"Using filename-based title: {title}")
    
    video.save()
    
    # Add __LRE to filename, preserve original extension
    directory = os.path.dirname(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    extension = os.path.splitext(file_path)[1]
    new_filename = f"{base_name}__LRE{extension}"
    new_path = os.path.join(directory, new_filename)
    os.rename(file_path, new_path)
    return new_path, title

def watch_downloads():
    downloads_path = os.path.expanduser("~/Downloads")
    processed_files = set()
    
    log_message(f"Watching Downloads folder for 'The McCartys' video files...")
    try:
        while True:
            # Check all MP4/MOV files in Downloads
            for filename in os.listdir(downloads_path):
                if (filename.lower().endswith(('.mp4', '.mov')) and 
                    filename.startswith("The McCartys ") and
                    not filename.endswith("__LRE.mp4") and
                    not filename.endswith("__LRE.mov")):
                    file_path = os.path.join(downloads_path, filename)
                    
                    # Only process new files
                    if file_path not in processed_files:
                        log_message(f"New McCartys video detected: {filename}")
                        try:
                            # Wait a moment to ensure file is fully written
                            time.sleep(1)
                            new_path, title = add_metadata(file_path)
                            processed_files.add(new_path)
                            log_message(f"Successfully processed file with title: {title}")
                            log_message(f"Renamed to: {os.path.basename(new_path)}")
                            log_message("-" * 50)
                        except Exception as e:
                            log_message(f"Error processing {filename}: {e}")
            
            # Sleep before next check
            time.sleep(1)
            
    except KeyboardInterrupt:
        log_message("\nStopping watch...")

if __name__ == "__main__":
    watch_downloads()