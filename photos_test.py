#!/usr/bin/env python3

import subprocess
import logging

class PhotosTest:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def execute_applescript(self, script: str) -> str:
        """Execute AppleScript and return the result."""
        try:
            # First ensure Photos is running and ready
            init_script = '''
            tell application "Photos"
                activate
                delay 1
                -- Wait for Photos to be ready
                repeat until application "Photos" is running
                    delay 1
                end repeat
                -- Additional delay to ensure library is loaded
                delay 2
                
                -- Try to get first photo's info
                set firstPhoto to first media item
                return title of firstPhoto
            end tell
            '''
            result = subprocess.run(['osascript', '-e', init_script], 
                                 capture_output=True, 
                                 text=True, 
                                 check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"AppleScript error: {e.stderr}")
            self.logger.error("Make sure Photos is installed and you've granted automation permissions")
            self.logger.error("You may need to go to System Preferences > Security & Privacy > Privacy > Automation")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tester = PhotosTest()
    try:
        result = tester.execute_applescript("")
        print(f"Successfully connected to Photos. First photo title: {result}")
    except Exception as e:
        logging.error(f"Test failed: {str(e)}") 