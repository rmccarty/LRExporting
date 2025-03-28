"""Tests for date normalization utility."""
import unittest
from utils.date_normalizer import DateNormalizer

class TestDateNormalizer(unittest.TestCase):
    """Test cases for DateNormalizer class."""
    
    def setUp(self):
        """Set up test cases."""
        self.normalizer = DateNormalizer()
        
    def test_when_normalizing_empty_date_then_returns_none(self):
        """Should return None for empty date string."""
        # Test cases
        empty_dates = ['', None, '   ']
        
        for date_str in empty_dates:
            # Execute
            result = self.normalizer.normalize(date_str)
            
            # Verify
            self.assertIsNone(result)
            
    def test_when_validating_empty_date_then_returns_false(self):
        """Should return False for empty date string."""
        # Test cases
        empty_dates = ['', None, '   ']
        
        for date_str in empty_dates:
            # Execute
            result = self.normalizer.validate(date_str)
            
            # Verify
            self.assertFalse(result)
            
if __name__ == '__main__':
    unittest.main()
