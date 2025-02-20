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
    while True:
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in BOTH_INCOMING.glob('*'):
                if "__LRE" in file.name:  # Check if __LRE is in the filename
                    # Copy the file to all incoming directories
                    for incoming_dir in INCOMING_DIRS:
                        shutil.copy(file, incoming_dir / file.name)
                        print(f"Copied {file.name} to {incoming_dir.name} directory.")
                    
                    # Delete the original file
                    file.unlink()
                    print(f"Deleted {file.name} from Both_Incoming.")
                    
            time.sleep(3)  # Wait before checking again
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(3)  # Wait before retrying

if __name__ == "__main__":
    watch_and_process()
