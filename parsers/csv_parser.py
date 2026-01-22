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

        # Docling format support
        self._is_docling_format: bool = False
        self._docling_type_col: Optional[int] = None
        self._docling_content_col: Optional[int] = None
        self._docling_field_mapping: Dict[str, int] = {}  # For table format

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
        # Check for Docling format first
        if self._detect_docling_format(rows):
            self._is_docling_format = True
            self._setup_docling_columns(rows)
            print("Detected Docling CSV format")
            return

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

    def _detect_docling_format(self, rows: List[List[str]]) -> bool:
        """
        Check if CSV uses Docling format.
        Docling CSVs have 'type' column with values like 'text', 'table', 'section_header'.
        """
        if not rows or len(rows) < 2:
            return False

        # Check if any column header contains 'type'
        header = [str(c).strip().lower() for c in rows[0]]
        if 'type' not in header:
            return False

        # Verify by checking if rows have 'text' or 'table' type values
        type_col = header.index('type')
        for row in rows[1:min(20, len(rows))]:
            if len(row) > type_col:
                val = str(row[type_col]).strip().lower()
                if val in ('text', 'table', 'section_header', 'page_header'):
                    return True
        return False

    def _setup_docling_columns(self, rows: List[List[str]]) -> None:
        """Identify Type and Content column positions."""
        header = [str(c).strip().lower() for c in rows[0]]

        for idx, col in enumerate(header):
            if col == 'type':
                self._docling_type_col = idx
            elif col in ('content', 'text'):
                self._docling_content_col = idx

        # If no explicit content column, assume it's the last column
        if self._docling_content_col is None:
            self._docling_content_col = len(header) - 1

        print(f"Docling columns - Type: {self._docling_type_col}, Content: {self._docling_content_col}")

        # Detect which format is predominant and find field mappings
        self._analyze_docling_structure(rows)

    def _analyze_docling_structure(self, rows: List[List[str]]) -> None:
        """
        Analyze Docling CSV to determine:
        1. If table rows exist with pipe-separated headers
        2. The field order for text-based multi-row transactions
        """
        type_col = self._docling_type_col
        content_col = self._docling_content_col

        if type_col is None or content_col is None:
            return

        # Look for table header row (contains field names with pipes)
        for row in rows[1:]:
            if len(row) <= max(type_col, content_col):
                continue

            row_type = str(row[type_col]).strip().lower()
            content = str(row[content_col]).strip()

            if row_type == 'table' and '|' in content:
                # Check if this looks like a header (contains keywords)
                content_lower = content.lower()
                if any(kw in content_lower for kw in ['date', 'description', 'debit', 'credit', 'balance']):
                    self._docling_field_mapping = self._parse_pipe_header(content)
                    print(f"Found table header mapping: {self._docling_field_mapping}")
                    break

    def _parse_pipe_header(self, header_content: str) -> Dict[str, int]:
        """Parse pipe-separated header to map field names to indices."""
        fields = [f.strip().lower() for f in header_content.split('|')]
        mapping: Dict[str, int] = {}

        for idx, field in enumerate(fields):
            # Date column (prefer txn date over value date)
            if 'date' not in mapping and self._matches_keywords(field, DATE_COLUMN_KEYWORDS):
                mapping['date'] = idx
            # Description
            if 'description' not in mapping and self._matches_keywords(field, DESCRIPTION_COLUMN_KEYWORDS):
                mapping['description'] = idx
            # Debit
            if 'debit' not in mapping and self._matches_keywords(field, DEBIT_COLUMN_KEYWORDS):
                mapping['debit'] = idx
            # Credit
            if 'credit' not in mapping and self._matches_keywords(field, CREDIT_COLUMN_KEYWORDS):
                mapping['credit'] = idx
            # Balance
            if 'balance' not in mapping and self._matches_keywords(field, BALANCE_COLUMN_KEYWORDS):
                mapping['balance'] = idx

        return mapping

    def _extract_transactions_docling(self, rows: List[List[str]]) -> List[Transaction]:
        """
        Extract transactions from Docling format.
        Handles both:
        - Table rows (pipe-separated fields)
        - Text rows (multi-row transactions between #### delimiters)
        """
        transactions: List[Transaction] = []
        type_col = self._docling_type_col
        content_col = self._docling_content_col

        if type_col is None or content_col is None:
            return transactions

        # State for text-format multi-row transactions
        current_text_fields: List[str] = []
        in_transaction = False
        transaction_start_row = 0

        # Track if we've seen the table header
        table_header_seen = False

        for row_idx, row in enumerate(rows[1:], start=2):
            if len(row) <= max(type_col, content_col):
                continue

            row_type = str(row[type_col]).strip().lower()
            content = str(row[content_col]).strip()

            if not content:
                continue

            # === Handle TEXT rows (multi-row format) ===
            if row_type == 'text':
                if content.startswith('###') or content == '############':
                    # Delimiter - either start or end of transaction
                    if in_transaction and current_text_fields:
                        # End of transaction - parse collected fields
                        txn = self._parse_text_transaction(current_text_fields, transaction_start_row, row_idx)
                        if txn:
                            transactions.append(txn)
                        current_text_fields = []

                    # Toggle state
                    in_transaction = not in_transaction
                    if in_transaction:
                        transaction_start_row = row_idx
                elif in_transaction:
                    # Collect field value
                    current_text_fields.append(content)

            # === Handle TABLE rows (pipe-separated format) ===
            elif row_type == 'table' and '|' in content:
                # Skip header row
                if not table_header_seen:
                    content_lower = content.lower()
                    if any(kw in content_lower for kw in ['date', 'description', 'debit', 'credit']):
                        table_header_seen = True
                        continue

                # Parse data row
                txn = self._parse_table_transaction(content, row_idx)
                if txn:
                    transactions.append(txn)

        # Handle any remaining text transaction
        if in_transaction and current_text_fields:
            txn = self._parse_text_transaction(current_text_fields, transaction_start_row, row_idx)
            if txn:
                transactions.append(txn)

        return transactions

    def _parse_text_transaction(
        self,
        fields: List[str],
        start_row: int,
        end_row: int
    ) -> Optional[Transaction]:
        """
        Parse a transaction from collected text fields.

        Expected field order (may vary):
        [Date, Cheque No, Description, Reference, Branch, Debit/Credit, Balance]

        We identify fields by their format:
        - Date: parseable as date
        - Amount: contains numbers with commas (Indian format)
        - Description: text that's not date or amount
        """
        if len(fields) < 3:
            return None

        date_val = None
        description_parts: List[str] = []
        amounts: List[float] = []

        for field in fields:
            field = field.strip()
            if not field:
                continue

            # Try to parse as date
            if date_val is None:
                parsed = parse_date(field)
                if parsed:
                    date_val = parsed
                    continue

            # Check if it's an amount (Indian format: 2,19,436.87)
            if has_valid_amount(field) and re.search(r'[\d,]+\.?\d*', field):
                # Verify it's primarily numeric
                numeric_chars = sum(1 for c in field if c.isdigit() or c in ',.₹')
                if numeric_chars > len(field) * 0.5:
                    amounts.append(parse_amount(field))
                    continue

            # Otherwise treat as description/reference
            # Skip pure numeric strings that aren't amounts (like cheque numbers)
            if not field.replace(' ', '').isdigit():
                description_parts.append(field)

        if date_val is None:
            return None

        # Determine debit/credit from amounts
        # Usually: second-to-last is debit OR credit, last is balance
        debit = None
        credit = None
        balance = None

        if len(amounts) >= 2:
            balance = amounts[-1]
            # The transaction amount - need context to know if debit or credit
            # For now, assume it's debit (most common for expenses)
            debit = amounts[-2] if amounts[-2] != 0 else None
        elif len(amounts) == 1:
            balance = amounts[0]

        description = ' '.join(description_parts)

        return Transaction(
            date=date_val,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
            raw_text=' | '.join(fields),
            row_numbers=list(range(start_row, end_row + 1))
        )

    def _parse_table_transaction(self, content: str, row_idx: int) -> Optional[Transaction]:
        """Parse a pipe-separated table row into a transaction."""
        fields = [f.strip() for f in content.split('|')]
        fm = self._docling_field_mapping

        if not fm:
            return None

        # Extract date
        date_idx = fm.get('date')
        if date_idx is None or date_idx >= len(fields):
            return None

        date_val = parse_date(fields[date_idx])
        if date_val is None:
            return None

        # Extract other fields safely
        def get_field(key: str) -> str:
            idx = fm.get(key)
            if idx is not None and idx < len(fields):
                return fields[idx]
            return ''

        description = get_field('description')

        debit = None
        credit = None
        balance = None

        debit_str = get_field('debit')
        if debit_str and has_valid_amount(debit_str):
            debit = abs(parse_amount(debit_str))
            if debit == 0:
                debit = None

        credit_str = get_field('credit')
        if credit_str and has_valid_amount(credit_str):
            credit = abs(parse_amount(credit_str))
            if credit == 0:
                credit = None

        balance_str = get_field('balance')
        if balance_str and has_valid_amount(balance_str):
            balance = parse_amount(balance_str)

        return Transaction(
            date=date_val,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
            raw_text=content,
            row_numbers=[row_idx]
        )

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
        # Use Docling extraction if detected
        if self._is_docling_format:
            return self._extract_transactions_docling(rows)

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
