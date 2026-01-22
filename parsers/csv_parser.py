"""
CSV Parser for Docling-converted bank statement files.

Handles:
- Multi-row transactions (description wraps to next row)
- Repeated headers on each page
- Page numbers as rows
- Garbage rows
"""
import csv
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import (
    BALANCE_COLUMN_KEYWORDS,
    CREDIT_COLUMN_KEYWORDS,
    DATE_COLUMN_KEYWORDS,
    DEBIT_COLUMN_KEYWORDS,
    DESCRIPTION_COLUMN_KEYWORDS,
    FILE_ENCODINGS,
    HEADER_KEYWORDS,
    SKIP_ROW_KEYWORDS,
)
from normalizer.amount_parser import parse_amount, has_valid_amount, parse_debit_credit
from normalizer.date_parser import parse_date, is_valid_date
from parsers.base_parser import BaseParser, Transaction, ValidationIssue


class CSVParser(BaseParser):
    """
    Parser for CSV bank statement files (typically from Docling PDF conversion).

    Uses date-anchored detection to handle multi-row transactions:
    - If date column has a valid date -> starts a NEW transaction
    - If date column is empty/invalid -> CONTINUATION of previous transaction
    """

    def __init__(
        self,
        filepath: str,
        date_col: Optional[int] = None,
        desc_cols: Optional[List[int]] = None,
        debit_col: Optional[int] = None,
        credit_col: Optional[int] = None,
        amount_col: Optional[int] = None,
        balance_col: Optional[int] = None,
    ):
        """
        Initialize the CSV parser.

        Args:
            filepath: Path to the CSV file
            date_col: Column index for date (0-based)
            desc_cols: Column indices for description (can be multiple)
            debit_col: Column index for debit amount
            credit_col: Column index for credit amount
            amount_col: Column index for single amount (if not separate debit/credit)
            balance_col: Column index for balance
        """
        super().__init__(filepath)
        self.date_col = date_col
        self.desc_cols = desc_cols or []
        self.debit_col = debit_col
        self.credit_col = credit_col
        self.amount_col = amount_col
        self.balance_col = balance_col

        self._encoding: Optional[str] = None
        self._detected_columns: Dict[str, int] = {}

    def parse(self) -> List[Transaction]:
        """
        Parse the CSV file and return normalized transactions.

        Returns:
            List of Transaction objects
        """
        print(f"Parsing CSV file: {self.filepath}")

        # Read the file with encoding detection
        rows = self._read_csv()

        if not rows:
            print("Warning: Could not read CSV file or file is empty")
            return []

        print(f"Read {len(rows)} rows from CSV")

        # If columns not specified, try to auto-detect
        if self.date_col is None:
            self._auto_detect_columns(rows)

        # Extract transactions using date-anchored detection
        self._transactions = self._extract_transactions_date_anchored(rows)
        print(f"Extracted {len(self._transactions)} transactions")

        return self._transactions

    def _read_csv(self) -> List[List[str]]:
        """
        Read CSV file with encoding fallback.

        Returns:
            List of rows (each row is a list of strings)
        """
        for encoding in FILE_ENCODINGS:
            try:
                with open(self.filepath, 'r', encoding=encoding) as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    self._encoding = encoding
                    print(f"Successfully read CSV with encoding: {encoding}")
                    return rows
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error reading CSV with {encoding}: {e}")
                continue

        print("Failed to read CSV with any supported encoding")
        return []

    def _auto_detect_columns(self, rows: List[List[str]]) -> None:
        """
        Auto-detect column mappings from the CSV.

        Args:
            rows: All rows from the CSV
        """
        # Find a potential header row
        header_row_idx = None
        header_row = None

        for idx, row in enumerate(rows[:20]):
            score = self._score_header_row(row)
            if score >= 3:
                header_row_idx = idx
                header_row = row
                break

        if header_row is None:
            # Use first row as header
            header_row_idx = 0
            header_row = rows[0] if rows else []

        print(f"Using row {header_row_idx} as header: {header_row}")

        # Track which columns have been assigned
        used_cols = set()

        # Map columns - order matters for priority
        for col_idx, col_name in enumerate(header_row):
            col_lower = str(col_name).strip().lower()

            # Check for date column
            if self.date_col is None and col_idx not in used_cols:
                if self._matches_keywords(col_lower, DATE_COLUMN_KEYWORDS):
                    self.date_col = col_idx
                    used_cols.add(col_idx)
                    continue

            # Check for description column
            if not self.desc_cols and col_idx not in used_cols:
                if self._matches_keywords(col_lower, DESCRIPTION_COLUMN_KEYWORDS):
                    self.desc_cols = [col_idx]
                    used_cols.add(col_idx)
                    continue

            # Check for debit column
            if self.debit_col is None and col_idx not in used_cols:
                if self._matches_keywords(col_lower, DEBIT_COLUMN_KEYWORDS):
                    self.debit_col = col_idx
                    used_cols.add(col_idx)
                    continue

            # Check for credit column
            if self.credit_col is None and col_idx not in used_cols:
                if self._matches_keywords(col_lower, CREDIT_COLUMN_KEYWORDS):
                    self.credit_col = col_idx
                    used_cols.add(col_idx)
                    continue

            # Check for balance column
            if self.balance_col is None and col_idx not in used_cols:
                if self._matches_keywords(col_lower, BALANCE_COLUMN_KEYWORDS):
                    self.balance_col = col_idx
                    used_cols.add(col_idx)
                    continue

        # If no separate debit/credit, look for single amount column
        if self.debit_col is None and self.credit_col is None:
            for col_idx, col_name in enumerate(header_row):
                if col_idx in used_cols:
                    continue
                col_lower = str(col_name).strip().lower()
                if 'amount' in col_lower:
                    self.amount_col = col_idx
                    break

        print(f"Auto-detected columns - date: {self.date_col}, "
              f"desc: {self.desc_cols}, debit: {self.debit_col}, "
              f"credit: {self.credit_col}, amount: {self.amount_col}, "
              f"balance: {self.balance_col}")

    def _matches_keywords(self, col_lower: str, keywords: List[str]) -> bool:
        """
        Check if a column name matches any of the keywords.

        Uses word boundary matching for short keywords to avoid false matches.
        E.g., "cr" should match "cr" or "cr amount" but not "description".

        Args:
            col_lower: Lowercase column name
            keywords: List of keywords to match

        Returns:
            True if column matches any keyword
        """
        for keyword in keywords:
            # For short keywords (1-2 chars), use word boundary matching
            if len(keyword) <= 2:
                # Check if keyword is the entire column name or bounded by non-alpha chars
                pattern = r'(?:^|[^a-z])' + re.escape(keyword) + r'(?:[^a-z]|$)'
                if re.search(pattern, col_lower):
                    return True
            else:
                # For longer keywords, substring matching is fine
                if keyword in col_lower:
                    return True
        return False

    def _score_header_row(self, row: List[str]) -> int:
        """
        Score a row based on how likely it is to be a header row.

        Args:
            row: A row from the CSV

        Returns:
            Score (higher = more likely to be header)
        """
        score = 0
        for value in row:
            value_lower = str(value).strip().lower()
            for keyword in HEADER_KEYWORDS:
                if keyword in value_lower:
                    score += 1
                    break
        return score

    def _extract_transactions_date_anchored(
        self,
        rows: List[List[str]]
    ) -> List[Transaction]:
        """
        Extract transactions using date-anchored detection.

        - Rows with valid date in date column start NEW transactions
        - Rows without valid date are CONTINUATIONS of the previous transaction

        Args:
            rows: All rows from the CSV

        Returns:
            List of Transaction objects
        """
        transactions: List[Transaction] = []
        current_txn: Optional[Transaction] = None

        if self.date_col is None:
            print("Warning: No date column identified, cannot parse")
            return []

        for row_idx, row in enumerate(rows):
            row_num = row_idx + 1  # 1-based row number

            # Skip empty rows
            if not row or all(not str(cell).strip() for cell in row):
                continue

            # Skip garbage rows
            if self._is_garbage_row(row):
                continue

            # Check if this row has a valid date
            date_value = self._get_cell(row, self.date_col)
            parsed_date = parse_date(date_value)

            if parsed_date is not None:
                # This is a NEW transaction
                # Save the previous transaction if any
                if current_txn is not None:
                    transactions.append(current_txn)

                # Extract data for new transaction
                description = self._extract_description(row)
                debit, credit = self._extract_amounts(row)
                balance = self._extract_balance(row)
                raw_text = " | ".join(str(c) for c in row if str(c).strip())

                current_txn = Transaction(
                    date=parsed_date,
                    description=description,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                    raw_text=raw_text,
                    row_numbers=[row_num],
                )

            else:
                # This is a CONTINUATION row
                if current_txn is not None:
                    # Append description from this row
                    continuation_desc = self._extract_description(row)
                    if continuation_desc:
                        if current_txn.description:
                            current_txn.description += " " + continuation_desc
                        else:
                            current_txn.description = continuation_desc

                    # Add row number to track source
                    current_txn.row_numbers.append(row_num)

                    # Append to raw text
                    row_text = " | ".join(str(c) for c in row if str(c).strip())
                    if row_text:
                        current_txn.raw_text += " [cont] " + row_text

        # Don't forget the last transaction
        if current_txn is not None:
            transactions.append(current_txn)

        return transactions

    def _get_cell(self, row: List[str], col_idx: Optional[int]) -> str:
        """
        Safely get a cell value from a row.

        Args:
            row: The row
            col_idx: Column index

        Returns:
            Cell value as string, or empty string if invalid
        """
        if col_idx is None or col_idx >= len(row):
            return ""
        return str(row[col_idx]).strip()

    def _extract_description(self, row: List[str]) -> str:
        """
        Extract description from the row.

        Args:
            row: The row

        Returns:
            Description string
        """
        if not self.desc_cols:
            return ""

        parts = []
        for col_idx in self.desc_cols:
            value = self._get_cell(row, col_idx)
            if value:
                parts.append(value)

        return " ".join(parts)

    def _extract_amounts(self, row: List[str]) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract debit and credit amounts from the row.

        Args:
            row: The row

        Returns:
            Tuple of (debit, credit)
        """
        debit = None
        credit = None

        if self.debit_col is not None:
            debit_value = self._get_cell(row, self.debit_col)
            if has_valid_amount(debit_value):
                debit = abs(parse_amount(debit_value))
                if debit == 0:
                    debit = None

        if self.credit_col is not None:
            credit_value = self._get_cell(row, self.credit_col)
            if has_valid_amount(credit_value):
                credit = abs(parse_amount(credit_value))
                if credit == 0:
                    credit = None

        # If using single amount column
        if self.amount_col is not None and debit is None and credit is None:
            amount_value = self._get_cell(row, self.amount_col)
            if has_valid_amount(amount_value):
                debit, credit = parse_debit_credit(amount_value)

        return debit, credit

    def _extract_balance(self, row: List[str]) -> Optional[float]:
        """
        Extract balance from the row.

        Args:
            row: The row

        Returns:
            Balance amount or None
        """
        if self.balance_col is None:
            return None

        balance_value = self._get_cell(row, self.balance_col)
        if has_valid_amount(balance_value):
            return parse_amount(balance_value)

        return None

    def _is_garbage_row(self, row: List[str]) -> bool:
        """
        Check if a row is garbage (should be skipped).

        Args:
            row: The row

        Returns:
            True if the row should be skipped
        """
        row_text = " ".join(str(c).lower() for c in row if str(c).strip())

        # Skip page number rows
        if re.match(r'^page\s*\d+', row_text.strip()):
            return True

        # Skip rows that look like repeated headers
        header_score = self._score_header_row(row)
        if header_score >= 3:
            return True

        # Skip summary rows
        for keyword in SKIP_ROW_KEYWORDS:
            if keyword in row_text:
                return True

        # Skip rows with "continued" or similar
        if 'continued' in row_text or 'contd' in row_text:
            return True

        return False

    def preview_rows(self, num_rows: int = 10) -> List[List[str]]:
        """
        Preview the first N rows of the CSV file.

        Args:
            num_rows: Number of rows to preview

        Returns:
            List of rows
        """
        rows = self._read_csv()
        return rows[:num_rows]

    def set_column_mapping(
        self,
        date_col: Optional[int] = None,
        desc_cols: Optional[List[int]] = None,
        debit_col: Optional[int] = None,
        credit_col: Optional[int] = None,
        amount_col: Optional[int] = None,
        balance_col: Optional[int] = None,
    ) -> None:
        """
        Manually set column mappings.

        Args:
            date_col: Column index for date
            desc_cols: Column indices for description
            debit_col: Column index for debit
            credit_col: Column index for credit
            amount_col: Column index for single amount
            balance_col: Column index for balance
        """
        if date_col is not None:
            self.date_col = date_col
        if desc_cols is not None:
            self.desc_cols = desc_cols
        if debit_col is not None:
            self.debit_col = debit_col
        if credit_col is not None:
            self.credit_col = credit_col
        if amount_col is not None:
            self.amount_col = amount_col
        if balance_col is not None:
            self.balance_col = balance_col
