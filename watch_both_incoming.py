#!/usr/bin/env python3

import os
import shutil
import time
from pathlib import Path

# Define the directories to watch and copy to
BOTH_INCOMING = Path("/Users/rmccarty/Transfers/Both/Both_Incoming")
INCOMING_DIRS = [
    Path("/Users/rmccarty/Transfers/Ron/Ron_Incoming"),
    Path("/Users/rmccarty/Transfers/Claudia/Claudia_Incoming")
]

def watch_and_process():
    found_files = False
    try:
        # Iterate through all files in the Both_Incoming directory
        for file in BOTH_INCOMING.glob('*'):
            # Check if the file is open
            try:
                with open(file, 'r+'):
                    pass  # File is not open, proceed to copy
            except IOError:
                print(f"File {file.name} is currently open. Skipping copy.", flush=True)
                continue  # Skip to the next file
            
            found_files = True
            # Copy the file to all incoming directories
            for incoming_dir in INCOMING_DIRS:
                shutil.copy(file, incoming_dir / file.name)
                print(f"Copied {file.name} to {incoming_dir.name} directory.", flush=True)
            
            # Delete the original file
            file.unlink()
            print(f"Deleted {file.name} from Both_Incoming.", flush=True)
    
    except Exception as e:
        print(f"Error: {e}", flush=True)
    
    return found_files

if __name__ == "__main__":
    print("Warning: watch_both_incoming.py is being run directly. For regular operation, this script should be imported by lrexport.py", flush=True)
    while True:
        try:
            print(f"Checking {BOTH_INCOMING} for new files...", flush=True)
            watch_and_process()
            print("Warning: watch_both_incoming.py is being run directly. For regular operation, this script should be imported by lrexport.py", flush=True)
            time.sleep(3)  # Sleep for 3 seconds between checks
        except KeyboardInterrupt:
            print("\nStopping watch_both_incoming.py", flush=True)
            break
