#!/usr/bin/env python3

from mutagen.mp4 import MP4
import os
import time

def add_title(file_path):
    video = MP4(file_path)
    # Get filename without extension and replace space with colon
    title = os.path.splitext(os.path.basename(file_path))[0]
    title = title.replace("The McCartys ", "The McCartys: ")
    video["\xa9nam"] = title
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
    
    print(f"Watching Downloads folder for 'The McCartys' video files...")
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
                        print(f"New McCartys video detected: {file_path}")
                        try:
                            # Wait a moment to ensure file is fully written
                            time.sleep(1)
                            new_path, title = add_title(file_path)
                            processed_files.add(new_path)
                            print(f"Successfully added title metadata: {title}")
                            print(f"Renamed to: {os.path.basename(new_path)}")
                        except Exception as e:
                            print(f"Error processing {file_path}: {e}")
            
            # Sleep before next check
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping watch...")

if __name__ == "__main__":
    watch_downloads()