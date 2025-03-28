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
            
    def test_when_validating_date_string_with_valid_input_then_returns_true(self):
        """Should return True for valid date strings."""
        valid_dates = [
            '2024-01-01 12:00:00',
            '2024:01:01 12:00:00',
            '2024-01-01 12:00:00 UTC'
        ]
        for date_str in valid_dates:
            with self.subTest(date_str=date_str):
                result = self.normalizer._is_valid_date_string(date_str)
                self.assertTrue(result)
                
    def test_when_validating_date_string_with_invalid_input_then_returns_false(self):
        """Should return False for invalid date strings."""
        invalid_dates = [
            None,
            '',
            123,
            [],
            {}
        ]
        for date_str in invalid_dates:
            with self.subTest(date_str=date_str):
                result = self.normalizer._is_valid_date_string(date_str)
                self.assertFalse(result)
                
    def test_when_validating_time_format_with_valid_input_then_returns_true(self):
        """Should return True for valid time formats."""
        valid_times = [
            '12:00:00',
            '23:59:59',
            '00:00:00'
        ]
        for time_str in valid_times:
            with self.subTest(time_str=time_str):
                result = self.normalizer._is_valid_time_format(time_str)
                self.assertTrue(result)
                
    def test_when_validating_time_format_with_invalid_input_then_returns_false(self):
        """Should return False for invalid time formats."""
        invalid_times = [
            'abc',
            '12:ab:00',
            '12 00 00'
        ]
        for time_str in invalid_times:
            with self.subTest(time_str=time_str):
                result = self.normalizer._is_valid_time_format(time_str)
                self.assertFalse(result)
                
    def test_when_normalizing_date_component_then_replaces_dashes_with_colons(self):
        """Should replace dashes with colons in date components."""
        test_cases = [
            ('2024-01-01', '2024:01:01'),
            ('2024:01:01', '2024:01:01'),
            ('2024-01:01', '2024:01:01')
        ]
        for input_date, expected in test_cases:
            with self.subTest(input_date=input_date):
                result = self.normalizer._normalize_date_component(input_date)
                self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
