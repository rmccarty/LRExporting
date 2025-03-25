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
    print(f"Checking {BOTH_INCOMING} for new files...")
    try:
        # Iterate through all files in the Both_Incoming directory
        for file in BOTH_INCOMING.glob('*'):
            # Check if the file is open
            try:
                with open(file, 'r+'):
                    pass  # File is not open, proceed to copy
            except IOError:
                print(f"File {file.name} is currently open. Skipping copy.")
                continue  # Skip to the next file
            
            # Copy the file to all incoming directories
            for incoming_dir in INCOMING_DIRS:
                shutil.copy(file, incoming_dir / file.name)
                print(f"Copied {file.name} to {incoming_dir.name} directory.")
            
            # Delete the original file
            file.unlink()
            print(f"Deleted {file.name} from Both_Incoming.")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    watch_and_process()
