#!/usr/bin/env python3

from abc import ABC, abstractmethod
from pathlib import Path
import logging

from config import WATCH_DIRS, SLEEP_TIME

class BaseWatcher(ABC):
    """Base class for watching directories for media files."""
    
    # Class-level sequence counter (1-9999)
    _sequence = 0
    
    @classmethod
    def _get_next_sequence(cls) -> str:
        """Get next sequence number as 4-digit string."""
        cls._sequence = (cls._sequence % 9999) + 1  # Roll over to 1 after 9999
        return f"{cls._sequence:04d}"  # Format as 4 digits with leading zeros
    
    def __init__(self, directories=None):
        """
        Initialize the watcher.
        
        Args:
            directories: List of directories to watch. If None, uses WATCH_DIRS
        """
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def process_file(self, file_path: Path):
        """Process a single media file. Must be implemented by subclasses."""
        pass
