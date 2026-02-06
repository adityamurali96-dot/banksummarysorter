"""
XLSX Parser for direct bank download Excel files.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import (
    BALANCE_COLUMN_KEYWORDS,
    CREDIT_COLUMN_KEYWORDS,
    DATE_COLUMN_KEYWORDS,
    DEBIT_COLUMN_KEYWORDS,
    DESCRIPTION_COLUMN_KEYWORDS,
    HEADER_KEYWORDS,
    SKIP_ROW_KEYWORDS,
)
from normalizer.amount_parser import parse_amount, has_valid_amount
from normalizer.date_parser import parse_date, is_valid_date
from parsers.base_parser import BaseParser, Transaction, ValidationIssue


class XLSXParser(BaseParser):
    """
    Parser for XLSX bank statement files (direct bank downloads).
    """

    def __init__(self, filepath: str, sheet_name: Optional[str] = None):
        """
        Initialize the XLSX parser.

        Args:
            filepath: Path to the Excel file
            sheet_name: Optional sheet name to parse (defaults to first sheet)
        """
        super().__init__(filepath)
        self.sheet_name = sheet_name
        self._header_row: Optional[int] = None
        self._column_mapping: Dict[str, str] = {}

    def parse(self) -> List[Transaction]:
        """
        Parse the Excel file and return normalized transactions.

        Returns:
            List of Transaction objects
        """
        print(f"Parsing XLSX file: {self.filepath}")

        # Read the entire Excel file first to find header row
        df_raw = self._read_excel_raw()

        if df_raw is None or df_raw.empty:
            print("Warning: Could not read Excel file or file is empty")
            return []

        # Find the header row
        self._header_row = self._find_header_row(df_raw)
        print(f"Found header row at index: {self._header_row}")

        # Re-read with correct header
        df = self._read_excel_with_header()

        if df is None or df.empty:
            print("Warning: No data found after header")
            return []

        # Map columns to standard names
        self._column_mapping = self._identify_columns(df)
        print(f"Column mapping: {self._column_mapping}")

        # Extract transactions
        self._transactions = self._extract_transactions(df)
        print(f"Extracted {len(self._transactions)} transactions")

        return self._transactions

    def _read_excel_raw(self) -> Optional[pd.DataFrame]:
        """Read Excel file without assuming headers."""
        try:
            df = pd.read_excel(
                self.filepath,
                sheet_name=self.sheet_name or 0,
                header=None,
                dtype=str,
            )
            return df
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            return None

    def _read_excel_with_header(self) -> Optional[pd.DataFrame]:
        """Read Excel file with the identified header row."""
        try:
            df = pd.read_excel(
                self.filepath,
                sheet_name=self.sheet_name or 0,
                header=self._header_row,
                dtype=str,
            )
            # Clean column names
            df.columns = [str(c).strip().lower() if pd.notna(c) else f"col_{i}"
                         for i, c in enumerate(df.columns)]
            return df
        except Exception as e:
            print(f"Error reading Excel file with header: {e}")
            return None

    def _find_header_row(self, df: pd.DataFrame) -> int:
        """
        Find the header row by looking for rows with header keywords.

        Args:
            df: Raw DataFrame

        Returns:
            Index of the header row (0-based)
        """
        max_rows_to_check = min(20, len(df))

        best_row = 0
        best_score = 0

        for idx in range(max_rows_to_check):
            row = df.iloc[idx]
            score = self._score_header_row(row)

            if score > best_score:
                best_score = score
                best_row = idx

        # If no good header found, assume first row
        if best_score < 3:
            print("Warning: Could not reliably identify header row, using row 0")
            return 0

        return best_row

    def _score_header_row(self, row: pd.Series) -> int:
        """
        Score a row based on how likely it is to be a header row.

        Args:
            row: A row from the DataFrame

        Returns:
            Score (higher = more likely to be header)
        """
        score = 0
        row_values = [str(v).strip().lower() for v in row if pd.notna(v)]

        for value in row_values:
            for keyword in HEADER_KEYWORDS:
                if keyword in value:
                    score += 1
                    break

        return score

    def _identify_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        Identify which columns map to date, description, debit, credit, balance.

        Args:
            df: DataFrame with headers

        Returns:
            Dictionary mapping standard names to column names
        """
        mapping = {}

        for col in df.columns:
            col_lower = str(col).lower()

            # Check for date column
            if 'date' not in mapping:
                for keyword in DATE_COLUMN_KEYWORDS:
                    if keyword in col_lower:
                        mapping['date'] = col
                        break

            # Check for description column
            if 'description' not in mapping:
                for keyword in DESCRIPTION_COLUMN_KEYWORDS:
                    if keyword in col_lower:
                        mapping['description'] = col
                        break

            # Check for debit column
            if 'debit' not in mapping:
                for keyword in DEBIT_COLUMN_KEYWORDS:
                    if keyword in col_lower:
                        mapping['debit'] = col
                        break

            # Check for credit column
            if 'credit' not in mapping:
                for keyword in CREDIT_COLUMN_KEYWORDS:
                    if keyword in col_lower:
                        mapping['credit'] = col
                        break

            # Check for balance column
            if 'balance' not in mapping:
                for keyword in BALANCE_COLUMN_KEYWORDS:
                    if keyword in col_lower:
                        mapping['balance'] = col
                        break

        return mapping

    def _extract_transactions(self, df: pd.DataFrame) -> List[Transaction]:
        """
        Extract transactions from the DataFrame.

        Args:
            df: DataFrame with identified columns

        Returns:
            List of Transaction objects
        """
        transactions = []

        date_col = self._column_mapping.get('date')
        desc_col = self._column_mapping.get('description')
        debit_col = self._column_mapping.get('debit')
        credit_col = self._column_mapping.get('credit')
        balance_col = self._column_mapping.get('balance')

        if not date_col:
            print("Warning: No date column identified")
            return []

        for idx, row in df.iterrows():
            # Get actual row number (accounting for header)
            row_num = idx + self._header_row + 2  # +2 for 1-based and header row

            # Check if this row has a valid date
            date_value = row.get(date_col)
            parsed_date = parse_date(date_value)

            if parsed_date is None:
                continue

            # Check if this is a skip row (summary row)
            if self._should_skip_row(row):
                continue

            # Extract description
            description = ""
            if desc_col:
                desc_value = row.get(desc_col)
                if pd.notna(desc_value):
                    description = str(desc_value).strip()

            # Extract amounts
            debit = None
            credit = None
            balance = None

            if debit_col:
                debit_value = row.get(debit_col)
                if pd.notna(debit_value) and has_valid_amount(debit_value):
                    debit = abs(parse_amount(debit_value))
                    if debit == 0:
                        debit = None

            if credit_col:
                credit_value = row.get(credit_col)
                if pd.notna(credit_value) and has_valid_amount(credit_value):
                    credit = abs(parse_amount(credit_value))
                    if credit == 0:
                        credit = None

            if balance_col:
                balance_value = row.get(balance_col)
                if pd.notna(balance_value) and has_valid_amount(balance_value):
                    balance = parse_amount(balance_value)

            # Create raw text for debugging
            raw_text = " | ".join(
                str(v) for v in row.values if pd.notna(v)
            )

            # Create transaction
            txn = Transaction(
                date=parsed_date,
                description=description,
                debit=debit,
                credit=credit,
                balance=balance,
                raw_text=raw_text,
                row_numbers=[row_num],
            )

            transactions.append(txn)

        return transactions

    def _should_skip_row(self, row: pd.Series) -> bool:
        """
        Check if a row should be skipped (summary row, etc.).

        Args:
            row: A row from the DataFrame

        Returns:
            True if the row should be skipped
        """
        row_text = " ".join(
            str(v).lower() for v in row.values if pd.notna(v)
        )

        for keyword in SKIP_ROW_KEYWORDS:
            if keyword in row_text:
                return True

        return False

    def get_available_sheets(self) -> List[str]:
        """
        Get list of available sheet names in the Excel file.

        Returns:
            List of sheet names
        """
        try:
            with pd.ExcelFile(self.filepath) as xl:
                return xl.sheet_names
        except Exception as e:
            print(f"Error reading sheet names: {e}")
            return []
