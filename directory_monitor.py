#!/usr/bin/env python3

"""
Directory Monitor - Monitors file counts in all LRExporting directories

Continuously monitors and reports file counts for:
- Incoming directories: Ron_Incoming, Claudia_Incoming, Both_Incoming
- Destination directories: Ron_Apple_Photos, Claudia's iCloud directory

Updates every few seconds to provide real-time visibility into the system.
"""

import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import sys

from config import (
    RON_INCOMING, 
    CLAUDIA_INCOMING, 
    BOTH_INCOMING,
    TRANSFER_PATHS,
    APPLE_PHOTOS_PATHS
)


class DirectoryMonitor:
    """
    Monitors file counts in all LRExporting directories.
    """
    
    def __init__(self, sleep_time: int = 5):
        """Initialize the directory monitor."""
        self.sleep_time = sleep_time
        
        # Build directory list from config
        self.directories = {
            "Ron_Incoming": RON_INCOMING,
            "Claudia_Incoming": CLAUDIA_INCOMING, 
            "Both_Incoming": BOTH_INCOMING,
        }
        
        # Add destination directories
        for source, dest in TRANSFER_PATHS.items():
            if source == RON_INCOMING:
                self.directories["Ron_Apple_Photos"] = dest
            elif source == CLAUDIA_INCOMING:
                self.directories["Claudia_iCloud"] = dest
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        print(f"📊 DIRECTORY MONITOR: Initialized")
        print(f"   ⏰ Update interval: {self.sleep_time} seconds")
        print(f"   📁 Monitoring {len(self.directories)} directories:")
        for name, path in self.directories.items():
            print(f"      {name}: {path}")
        print()
        
    def _count_files(self, directory: Path) -> Dict[str, int]:
        """
        Count files in a directory by type.
        
        Args:
            directory: Path to count files in
            
        Returns:
            Dict with counts for different file types
        """
        if not directory.exists():
            return {"total": 0, "jpg": 0, "video": 0, "lre": 0, "other": 0}
        
        try:
            files = list(directory.iterdir())
            total = len([f for f in files if f.is_file()])
            
            jpg_count = 0
            video_count = 0
            lre_count = 0
            other_count = 0
            
            for file_path in files:
                if not file_path.is_file():
                    continue
                    
                suffix = file_path.suffix.lower()
                name = file_path.name
                
                # Count __LRE files
                if "__LRE" in name:
                    lre_count += 1
                # Count image files
                elif suffix in ['.jpg', '.jpeg']:
                    jpg_count += 1
                # Count video files
                elif suffix in ['.mp4', '.mov', '.m4v']:
                    video_count += 1
                else:
                    other_count += 1
                    
            return {
                "total": total,
                "jpg": jpg_count, 
                "video": video_count,
                "lre": lre_count,
                "other": other_count
            }
            
        except Exception as e:
            self.logger.error(f"Error counting files in {directory}: {e}")
            return {"total": -1, "jpg": -1, "video": -1, "lre": -1, "other": -1}
    
    def _print_status(self):
        """Print current status of all directories."""
        # Clear screen
        print("\033[2J\033[H", end="")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📊 Directory Status - {timestamp}")
        print("=" * 80)
        
        # Header
        print(f"{'Directory':<20} {'Total':<8} {'JPEG':<8} {'Video':<8} {'__LRE':<8} {'Other':<8} {'Path'}")
        print("-" * 80)
        
        total_files = 0
        total_lre = 0
        
        # Sort directories by name for consistent display
        for name, path in sorted(self.directories.items()):
            counts = self._count_files(path)
            
            if counts["total"] >= 0:
                total_files += counts["total"] 
                total_lre += counts["lre"]
                
                # Format path for display (truncate if too long)
                path_str = str(path)
                if len(path_str) > 30:
                    path_str = "..." + path_str[-27:]
                
                print(f"{name:<20} {counts['total']:<8} {counts['jpg']:<8} {counts['video']:<8} {counts['lre']:<8} {counts['other']:<8} {path_str}")
            else:
                print(f"{name:<20} {'ERROR':<8} {'ERROR':<8} {'ERROR':<8} {'ERROR':<8} {'ERROR':<8} {path}")
        
        print("-" * 80)
        print(f"{'TOTALS':<20} {total_files:<8} {'':<8} {'':<8} {total_lre:<8}")
        print()
        
    def run(self):
        """Run the monitor continuously."""
        try:
            while True:
                self._print_status()
                time.sleep(self.sleep_time)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Directory Monitor stopped by user")
            sys.exit(0)
        except Exception as e:
            self.logger.error(f"Monitor error: {e}")
            sys.exit(1)


def main():
    """Main entry point."""
    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run monitor
    monitor = DirectoryMonitor(sleep_time=5)
    monitor.run()


if __name__ == "__main__":
    main()