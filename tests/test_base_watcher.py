#!/usr/bin/env python3

import unittest
from unittest.mock import patch
from pathlib import Path

from watchers.base_watcher import BaseWatcher
from config import WATCH_DIRS, SLEEP_TIME

class TestBaseWatcher(unittest.TestCase):
    """Test cases for BaseWatcher class."""
    
    def setUp(self):
        """Create a concrete implementation of BaseWatcher for testing."""
        class ConcreteWatcher(BaseWatcher):
            def process_file(self, file_path: Path):
                pass
                
        self.watcher_class = ConcreteWatcher
        self.test_dirs = ['/test/dir1', '/test/dir2']
        
    def test_when_initializing_with_custom_dirs_then_uses_custom_dirs(self):
        """Should use provided directories when initializing."""
        watcher = self.watcher_class(self.test_dirs)
        
        self.assertEqual(len(watcher.directories), 2)
        self.assertEqual(str(watcher.directories[0]), self.test_dirs[0])
        self.assertEqual(str(watcher.directories[1]), self.test_dirs[1])
        
    def test_when_initializing_without_dirs_then_uses_config_dirs(self):
        """Should use WATCH_DIRS from config when no directories provided."""
        with patch('watchers.base_watcher.WATCH_DIRS', self.test_dirs):
            watcher = self.watcher_class()
            
            self.assertEqual(len(watcher.directories), 2)
            self.assertEqual(str(watcher.directories[0]), self.test_dirs[0])
            self.assertEqual(str(watcher.directories[1]), self.test_dirs[1])
            
    def test_when_getting_sequence_then_increments_and_rolls_over(self):
        """Should increment sequence and roll over after 9999."""
        # Test normal increment
        initial_seq = self.watcher_class._sequence
        seq1 = self.watcher_class._get_next_sequence()
        seq2 = self.watcher_class._get_next_sequence()
        
        self.assertEqual(len(seq1), 4)  # Should be 4 digits
        self.assertTrue(seq1.isdigit())  # Should be all digits
        self.assertEqual(int(seq2), (int(seq1) % 9999) + 1)  # Should increment
        
        # Test rollover
        self.watcher_class._sequence = 9999
        seq = self.watcher_class._get_next_sequence()
        self.assertEqual(seq, '0001')  # Should roll over to 0001
        
    def test_when_initializing_then_sets_default_values(self):
        """Should set default values for running and sleep_time."""
        watcher = self.watcher_class()
        
        self.assertFalse(watcher.running)
        self.assertEqual(watcher.sleep_time, SLEEP_TIME)
        self.assertIsNotNone(watcher.logger)
        
    def test_when_converting_paths_then_creates_path_objects(self):
        """Should convert directory strings to Path objects."""
        watcher = self.watcher_class(self.test_dirs)
        
        for directory in watcher.directories:
            self.assertIsInstance(directory, Path)

if __name__ == '__main__':
    unittest.main()
