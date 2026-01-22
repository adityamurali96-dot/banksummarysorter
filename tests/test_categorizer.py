"""
Unit tests for transaction categorization.
"""
import unittest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from categorizer.rules import rule_based_categorize, get_matching_rule


class TestRuleBasedCategorizer(unittest.TestCase):
    """Tests for rule-based categorization."""

    def test_salary(self):
        """Test salary pattern matching."""
        result = rule_based_categorize("SAL FOR OCT 2024")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Income")
        self.assertEqual(result[1], "Salary")

    def test_salary_payroll(self):
        """Test payroll pattern."""
        result = rule_based_categorize("PAYROLL CREDIT FROM ACME CORP")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Income")
        self.assertEqual(result[1], "Salary")

    def test_food_delivery_swiggy(self):
        """Test Swiggy pattern."""
        result = rule_based_categorize("SWIGGY ORDER 12345")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Food & Dining")
        self.assertEqual(result[1], "Food Delivery")

    def test_food_delivery_zomato(self):
        """Test Zomato pattern."""
        result = rule_based_categorize("ZOMATO FOOD DELIVERY")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Food & Dining")
        self.assertEqual(result[1], "Food Delivery")

    def test_online_shopping_amazon(self):
        """Test Amazon pattern."""
        result = rule_based_categorize("AMAZON PAY INDIA")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Shopping")
        self.assertEqual(result[1], "Online Shopping")

    def test_online_shopping_flipkart(self):
        """Test Flipkart pattern."""
        result = rule_based_categorize("FLIPKART MARKETPLACE")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Shopping")
        self.assertEqual(result[1], "Online Shopping")

    def test_groceries_blinkit(self):
        """Test Blinkit pattern."""
        result = rule_based_categorize("BLINKIT DELIVERY")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Shopping")
        self.assertEqual(result[1], "Groceries")

    def test_cab_uber(self):
        """Test Uber cab pattern."""
        result = rule_based_categorize("UBER TRIP PAYMENT")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Transport")
        self.assertEqual(result[1], "Cab/Taxi")

    def test_uber_eats_not_cab(self):
        """Test Uber Eats goes to Food, not Transport."""
        result = rule_based_categorize("UBER EATS ORDER")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Food & Dining")
        self.assertEqual(result[1], "Food Delivery")

    def test_fuel(self):
        """Test fuel pattern."""
        result = rule_based_categorize("HP PETROL PUMP")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Transport")
        self.assertEqual(result[1], "Fuel")

    def test_atm_withdrawal(self):
        """Test ATM withdrawal pattern."""
        result = rule_based_categorize("ATM WDL 15000")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Cash")
        self.assertEqual(result[1], "ATM Withdrawal")

    def test_atm_nfs(self):
        """Test NFS ATM pattern."""
        result = rule_based_categorize("NFS WDL/ATM/SBI")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Cash")
        self.assertEqual(result[1], "ATM Withdrawal")

    def test_mutual_fund_sip(self):
        """Test SIP pattern."""
        result = rule_based_categorize("SIP PAYMENT HDFC MF")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Investments")
        self.assertEqual(result[1], "Mutual Funds")

    def test_zerodha(self):
        """Test Zerodha pattern."""
        result = rule_based_categorize("ZERODHA BROKING")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Investments")
        self.assertEqual(result[1], "Stocks")

    def test_insurance_lic(self):
        """Test LIC pattern."""
        result = rule_based_categorize("LIC PREMIUM PAYMENT")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Insurance")
        self.assertEqual(result[1], "Life Insurance")

    def test_electricity_bill(self):
        """Test electricity bill pattern."""
        result = rule_based_categorize("BESCOM ELECTRICITY BILL")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Bills & Utilities")
        self.assertEqual(result[1], "Electricity")

    def test_mobile_recharge(self):
        """Test mobile recharge pattern."""
        result = rule_based_categorize("AIRTEL PREPAID RECHARGE")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Bills & Utilities")
        self.assertEqual(result[1], "Mobile/Internet")

    def test_netflix_subscription(self):
        """Test Netflix pattern."""
        result = rule_based_categorize("NETFLIX SUBSCRIPTION")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Entertainment")
        self.assertEqual(result[1], "OTT Subscriptions")

    def test_rent_payment(self):
        """Test rent payment pattern."""
        result = rule_based_categorize("RENT PAYMENT FOR DEC")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Bills & Utilities")
        self.assertEqual(result[1], "Rent")

    def test_gst_payment(self):
        """Test GST payment pattern."""
        result = rule_based_categorize("GST PAYMENT CHALLAN")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Taxes")
        self.assertEqual(result[1], "GST Payment")

    def test_bank_transfer(self):
        """Test bank transfer patterns."""
        result = rule_based_categorize("NEFT CR FROM XYZ")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Transfer")
        self.assertEqual(result[1], "Bank Transfer")

    def test_upi_transfer(self):
        """Test UPI pattern."""
        result = rule_based_categorize("UPI/123456789/PAYMENT")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Transfer")
        self.assertEqual(result[1], "Bank Transfer")

    def test_service_charge(self):
        """Test service charge pattern."""
        result = rule_based_categorize("SMS CHARGE FOR Q3")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Bank Charges")
        self.assertEqual(result[1], "Service Charges")

    def test_no_match(self):
        """Test no match returns None."""
        result = rule_based_categorize("RANDOM UNKNOWN TRANSACTION XYZ")
        self.assertIsNone(result)

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        result = rule_based_categorize("swiggy order 12345")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Food & Dining")

    def test_empty_string(self):
        """Test empty string returns None."""
        result = rule_based_categorize("")
        self.assertIsNone(result)

    def test_confidence(self):
        """Test confidence is returned."""
        result = rule_based_categorize("SWIGGY ORDER")
        self.assertIsNotNone(result)
        self.assertEqual(result[2], 0.95)  # RULE_BASED_CONFIDENCE

    def test_interest_credit(self):
        """Test interest credit pattern."""
        result = rule_based_categorize("INT CR ON SAVINGS")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Income")
        self.assertEqual(result[1], "Interest")

    def test_train_ticket(self):
        """Test IRCTC pattern."""
        result = rule_based_categorize("IRCTC TICKET BOOKING")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Transport")
        self.assertEqual(result[1], "Train")

    def test_hospital(self):
        """Test hospital pattern."""
        result = rule_based_categorize("APOLLO HOSPITAL PAYMENT")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Healthcare")
        self.assertEqual(result[1], "Hospital")


class TestGetMatchingRule(unittest.TestCase):
    """Tests for get_matching_rule function."""

    def test_returns_pattern(self):
        """Test that matching pattern is returned."""
        pattern = get_matching_rule("SWIGGY ORDER")
        self.assertIsNotNone(pattern)
        self.assertIn("swiggy", pattern)

    def test_no_match_returns_none(self):
        """Test no match returns None."""
        pattern = get_matching_rule("RANDOM XYZ")
        self.assertIsNone(pattern)


if __name__ == '__main__':
    unittest.main()
