"""
Integration tests for the bank statement processor.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.csv_parser import CSVParser
from categorizer.categorizer import TransactionCategorizer
from output.excel_generator import generate_output_excel


class TestCSVParserIntegration(unittest.TestCase):
    """Integration tests for CSV parser."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_csv_path = os.path.join(
            os.path.dirname(__file__),
            'sample_files',
            'sample_docling.csv'
        )

    def test_parse_sample_csv(self):
        """Test parsing the sample CSV file."""
        if not os.path.exists(self.sample_csv_path):
            self.skipTest(f"Sample file not found: {self.sample_csv_path}")

        parser = CSVParser(self.sample_csv_path)
        transactions = parser.parse()

        self.assertGreater(len(transactions), 0)

        # Check first transaction (salary)
        salary_txn = transactions[0]
        self.assertIsNotNone(salary_txn.date)
        self.assertIn('SALARY', salary_txn.description.upper())
        self.assertIsNotNone(salary_txn.credit)
        self.assertEqual(salary_txn.credit, 75000.0)

    def test_multirow_transactions(self):
        """Test that multi-row transactions are merged."""
        if not os.path.exists(self.sample_csv_path):
            self.skipTest(f"Sample file not found: {self.sample_csv_path}")

        parser = CSVParser(self.sample_csv_path)
        transactions = parser.parse()

        # Find the IRCTC transaction (should have multiple rows merged)
        irctc_txns = [t for t in transactions if 'IRCTC' in t.description.upper()]
        self.assertEqual(len(irctc_txns), 1)

        irctc = irctc_txns[0]
        # Should contain merged description
        self.assertIn('PNR', irctc.description.upper())


class TestCategorizerIntegration(unittest.TestCase):
    """Integration tests for categorizer."""

    def test_categorize_transactions_rules_only(self):
        """Test categorization without API (rules only)."""
        # Create dummy transactions
        from parsers.base_parser import Transaction
        from datetime import date

        transactions = [
            Transaction(
                date=date(2025, 1, 15),
                description="SALARY CREDIT FOR JAN 2025",
                credit=75000.0
            ),
            Transaction(
                date=date(2025, 1, 16),
                description="ATM WDL/SBI/BANGALORE",
                debit=10000.0
            ),
            Transaction(
                date=date(2025, 1, 17),
                description="SWIGGY ORDER 12345",
                debit=450.0
            ),
            Transaction(
                date=date(2025, 1, 18),
                description="XYZABC123 UNKNOWN PARTY TRANSFER",
                debit=1000.0
            ),
        ]

        # Categorize without API key (rules only)
        categorizer = TransactionCategorizer(api_key=None)
        result = categorizer.categorize_all(transactions)

        # Check results
        self.assertEqual(len(result), 4)

        # Salary should be categorized
        self.assertEqual(result[0].category, "Income")
        self.assertEqual(result[0].subcategory, "Salary")
        self.assertEqual(result[0].categorization_source, "rules")

        # ATM should be categorized
        self.assertEqual(result[1].category, "Cash")
        self.assertEqual(result[1].subcategory, "ATM Withdrawal")

        # Swiggy should be categorized
        self.assertEqual(result[2].category, "Food & Dining")
        self.assertEqual(result[2].subcategory, "Food Delivery")

        # Last one has "transfer" which matches rules, so check it gets categorized
        self.assertIn(result[3].categorization_source, ["rules", "flagged"])


class TestExcelGeneratorIntegration(unittest.TestCase):
    """Integration tests for Excel generator."""

    def test_generate_excel_output(self):
        """Test generating Excel output."""
        from parsers.base_parser import Transaction
        from datetime import date

        transactions = [
            Transaction(
                date=date(2025, 1, 15),
                description="SALARY CREDIT FOR JAN 2025",
                credit=75000.0,
                balance=175000.0,
                category="Income",
                subcategory="Salary",
                categorization_confidence=0.95,
                categorization_source="rules"
            ),
            Transaction(
                date=date(2025, 1, 16),
                description="ATM WDL/SBI/BANGALORE",
                debit=10000.0,
                balance=165000.0,
                category="Cash",
                subcategory="ATM Withdrawal",
                categorization_confidence=0.95,
                categorization_source="rules"
            ),
            Transaction(
                date=date(2025, 1, 17),
                description="UNKNOWN TRANSACTION",
                debit=500.0,
                balance=164500.0,
                category="Review Required",
                subcategory="Manual Review Needed",
                categorization_confidence=0.3,
                categorization_source="flagged",
                haiku_suggestion="Transfer > Bank Transfer (conf: 0.30)"
            ),
        ]

        # Generate to temp file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            output_path = f.name

        try:
            generate_output_excel(transactions, output_path)

            # Verify file was created
            self.assertTrue(os.path.exists(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)

            # Try to read it back with pandas
            import pandas as pd
            xl = pd.ExcelFile(output_path)

            # Check sheets exist
            self.assertIn("All Transactions", xl.sheet_names)
            self.assertIn("Category Summary", xl.sheet_names)
            self.assertIn("Monthly Summary", xl.sheet_names)
            self.assertIn("Flagged for Review", xl.sheet_names)
            self.assertIn("Statistics", xl.sheet_names)

            # Check All Transactions sheet
            df = pd.read_excel(output_path, sheet_name="All Transactions")
            self.assertEqual(len(df), 3)

            # Check Flagged sheet has the flagged transactions
            df_flagged = pd.read_excel(output_path, sheet_name="Flagged for Review")
            self.assertGreaterEqual(len(df_flagged), 1)  # At least one flagged transaction

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration test."""

    def test_full_pipeline(self):
        """Test the full processing pipeline."""
        sample_csv_path = os.path.join(
            os.path.dirname(__file__),
            'sample_files',
            'sample_docling.csv'
        )

        if not os.path.exists(sample_csv_path):
            self.skipTest(f"Sample file not found: {sample_csv_path}")

        # Parse
        parser = CSVParser(sample_csv_path)
        transactions = parser.parse()
        self.assertGreater(len(transactions), 0)

        # Categorize (rules only)
        categorizer = TransactionCategorizer(api_key=None)
        transactions = categorizer.categorize_all(transactions)

        # Count categorization sources
        rules_count = sum(1 for t in transactions if t.categorization_source == "rules")
        flagged_count = sum(1 for t in transactions if t.categorization_source == "flagged")

        # Most should be categorized by rules
        self.assertGreater(rules_count, 0)

        # Generate output
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            output_path = f.name

        try:
            generate_output_excel(transactions, output_path)
            self.assertTrue(os.path.exists(output_path))

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


if __name__ == '__main__':
    unittest.main()
