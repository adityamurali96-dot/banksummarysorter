"""
Unit tests for date and amount parsers.
"""
import unittest
from datetime import date

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalizer.date_parser import parse_date, is_valid_date, extract_date_from_string
from normalizer.amount_parser import (
    parse_amount, has_valid_amount, parse_debit_credit, format_indian_currency
)


class TestDateParser(unittest.TestCase):
    """Tests for date parsing functions."""

    def test_dd_mm_yyyy_slash(self):
        """Test DD/MM/YYYY format."""
        result = parse_date("15/01/2025")
        self.assertEqual(result, date(2025, 1, 15))

    def test_dd_mm_yyyy_dash(self):
        """Test DD-MM-YYYY format."""
        result = parse_date("15-01-2025")
        self.assertEqual(result, date(2025, 1, 15))

    def test_dd_mm_yy_slash(self):
        """Test DD/MM/YY format."""
        result = parse_date("15/01/25")
        self.assertEqual(result, date(2025, 1, 15))

    def test_iso_format(self):
        """Test YYYY-MM-DD format."""
        result = parse_date("2025-01-15")
        self.assertEqual(result, date(2025, 1, 15))

    def test_dd_mmm_yyyy(self):
        """Test DD MMM YYYY format."""
        result = parse_date("15 Jan 2025")
        self.assertEqual(result, date(2025, 1, 15))

    def test_dd_mmm_yyyy_dash(self):
        """Test DD-MMM-YYYY format."""
        result = parse_date("15-Jan-2025")
        self.assertEqual(result, date(2025, 1, 15))

    def test_dd_month_yyyy(self):
        """Test DD Month YYYY format."""
        result = parse_date("15 January 2025")
        self.assertEqual(result, date(2025, 1, 15))

    def test_extra_spaces(self):
        """Test handling of extra spaces."""
        result = parse_date("  15/01/2025  ")
        self.assertEqual(result, date(2025, 1, 15))

    def test_invalid_date(self):
        """Test invalid date returns None."""
        result = parse_date("not a date")
        self.assertIsNone(result)

    def test_empty_string(self):
        """Test empty string returns None."""
        result = parse_date("")
        self.assertIsNone(result)

    def test_none_input(self):
        """Test None input returns None."""
        result = parse_date(None)
        self.assertIsNone(result)

    def test_is_valid_date_true(self):
        """Test is_valid_date returns True for valid dates."""
        self.assertTrue(is_valid_date("15/01/2025"))
        self.assertTrue(is_valid_date("2025-01-15"))

    def test_is_valid_date_false(self):
        """Test is_valid_date returns False for invalid dates."""
        self.assertFalse(is_valid_date("not a date"))
        self.assertFalse(is_valid_date(""))
        self.assertFalse(is_valid_date(None))

    def test_extract_date_from_string(self):
        """Test extracting date from text."""
        result = extract_date_from_string("Transaction on 15/01/2025 for amount")
        self.assertEqual(result, date(2025, 1, 15))


class TestAmountParser(unittest.TestCase):
    """Tests for amount parsing functions."""

    def test_simple_number(self):
        """Test simple number."""
        result = parse_amount("1000")
        self.assertEqual(result, 1000.0)

    def test_decimal_number(self):
        """Test decimal number."""
        result = parse_amount("1000.50")
        self.assertEqual(result, 1000.50)

    def test_indian_format(self):
        """Test Indian number format (lakhs)."""
        result = parse_amount("9,17,390.58")
        self.assertEqual(result, 917390.58)

    def test_international_format(self):
        """Test international format."""
        result = parse_amount("917,390.58")
        self.assertEqual(result, 917390.58)

    def test_rupee_symbol(self):
        """Test with rupee symbol."""
        result = parse_amount("₹1000")
        self.assertEqual(result, 1000.0)

    def test_rs_prefix(self):
        """Test with Rs prefix."""
        result = parse_amount("Rs. 1000")
        self.assertEqual(result, 1000.0)

    def test_inr_prefix(self):
        """Test with INR prefix."""
        result = parse_amount("INR 1000")
        self.assertEqual(result, 1000.0)

    def test_negative_minus(self):
        """Test negative with minus sign."""
        result = parse_amount("-1000")
        self.assertEqual(result, -1000.0)

    def test_negative_parentheses(self):
        """Test negative with parentheses."""
        result = parse_amount("(1000)")
        self.assertEqual(result, -1000.0)

    def test_dr_suffix(self):
        """Test DR suffix (debit = negative)."""
        result = parse_amount("1000 DR")
        self.assertEqual(result, -1000.0)

    def test_cr_suffix(self):
        """Test CR suffix (credit = positive)."""
        result = parse_amount("1000 CR")
        self.assertEqual(result, 1000.0)

    def test_empty_string(self):
        """Test empty string returns 0."""
        result = parse_amount("")
        self.assertEqual(result, 0.0)

    def test_none_input(self):
        """Test None input returns 0."""
        result = parse_amount(None)
        self.assertEqual(result, 0.0)

    def test_numeric_input(self):
        """Test numeric input passes through."""
        result = parse_amount(1000.50)
        self.assertEqual(result, 1000.50)

    def test_has_valid_amount_true(self):
        """Test has_valid_amount returns True for valid amounts."""
        self.assertTrue(has_valid_amount("1000"))
        self.assertTrue(has_valid_amount("₹1000.50"))
        self.assertTrue(has_valid_amount("9,17,390.58"))

    def test_has_valid_amount_false(self):
        """Test has_valid_amount returns False for invalid amounts."""
        self.assertFalse(has_valid_amount(""))
        self.assertFalse(has_valid_amount(None))
        self.assertFalse(has_valid_amount("not a number"))

    def test_parse_debit_credit_dr(self):
        """Test parse_debit_credit with DR indicator."""
        debit, credit = parse_debit_credit("1000 DR")
        self.assertEqual(debit, 1000.0)
        self.assertIsNone(credit)

    def test_parse_debit_credit_cr(self):
        """Test parse_debit_credit with CR indicator."""
        debit, credit = parse_debit_credit("1000 CR")
        self.assertIsNone(debit)
        self.assertEqual(credit, 1000.0)

    def test_parse_debit_credit_column_type(self):
        """Test parse_debit_credit with column type hint."""
        debit, credit = parse_debit_credit("1000", column_type="debit")
        self.assertEqual(debit, 1000.0)
        self.assertIsNone(credit)

    def test_format_indian_currency(self):
        """Test Indian currency formatting."""
        result = format_indian_currency(917390.58)
        self.assertEqual(result, "₹9,17,390.58")

    def test_format_indian_currency_negative(self):
        """Test Indian currency formatting with negative."""
        result = format_indian_currency(-1000.00)
        self.assertEqual(result, "₹-1,000.00")


if __name__ == '__main__':
    unittest.main()
