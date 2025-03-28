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

    def test_when_normalizing_timezone_with_edge_cases_then_handles_correctly(self):
        """Should handle timezone edge cases correctly."""
        test_cases = [
            ('+0', '+0000'),      # Short positive zero
            ('-0', '-0000'),      # Short negative zero (preserve sign)
            ('+14', '+1400'),     # Max positive
            ('-14', '-1400'),     # Max negative
            ('UTC', '+0000'),     # UTC string
            ('Z', '+0000'),       # Z timezone
            ('GMT', '+0000'),     # GMT string
            (None, ''),           # None input
            ('', ''),             # Empty string
            ('invalid', ''),      # Invalid string
            ('15:00', ''),        # Missing sign
            ('+1500', ''),        # Invalid hours
            ('+1260', ''),        # Invalid minutes
            ('+15', ''),          # Incomplete format
            ('5abc', ''),         # Invalid with numbers
        ]
        for input_tz, expected_tz in test_cases:
            with self.subTest(input_tz=input_tz):
                result = self.normalizer._normalize_timezone(input_tz)
                self.assertEqual(result, expected_tz,
                    f"Expected {expected_tz} for timezone {input_tz}, got {result}")
                    
    def test_when_validating_timezone_input_with_invalid_types_then_returns_false(self):
        """Should handle edge cases in _is_valid_timezone_input."""
        test_cases = [
            None,
            123,
            [],
            {},
            True
        ]
        for tz in test_cases:
            with self.subTest(tz=tz):
                result = self.normalizer._is_valid_timezone_input(tz)
                self.assertFalse(result)
                
    def test_when_cleaning_timezone_string_then_handles_all_formats(self):
        """Should handle all timezone string formats correctly."""
        test_cases = [
            ('+0500', '+0500'),   # Already clean
            ('-5', '-5'),         # Short format
            ('+abc5', '+5'),      # Remove invalid chars
            ('+-5', '+5'),        # Remove duplicate signs
            ('5', '5'),           # No sign
            ('abc', ''),          # No valid chars
            ('+', ''),            # Only sign
            ('+-', ''),           # Only signs
        ]
        for input_tz, expected in test_cases:
            with self.subTest(input_tz=input_tz):
                result = self.normalizer._clean_timezone_string(input_tz)
                self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
