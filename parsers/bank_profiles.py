"""
Bank Profiles for Flexible Statement Parsing.

This module provides bank-specific parsing configurations to handle
different statement formats without hardcoding assumptions.

Supported banks include profiles for:
- Indian banks (SBI, HDFC, ICICI, Axis, Canara, etc.)
- International banks (Chase, Wells Fargo, Bank of America, etc.)
- Generic profiles for unknown formats
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple


class DateFormat(Enum):
    """Date format preferences."""
    DMY = "dmy"  # Day/Month/Year (most common outside US)
    MDY = "mdy"  # Month/Day/Year (US format)
    YMD = "ymd"  # Year/Month/Day (ISO format)


class AmountFormat(Enum):
    """Amount format styles."""
    INDIAN = "indian"  # 1,23,456.78 (lakhs system)
    INTERNATIONAL = "international"  # 123,456.78
    EUROPEAN = "european"  # 123.456,78 (comma as decimal)


@dataclass
class ColumnHints:
    """Hints for identifying columns in statements."""
    date_keywords: List[str] = field(default_factory=list)
    description_keywords: List[str] = field(default_factory=list)
    debit_keywords: List[str] = field(default_factory=list)
    credit_keywords: List[str] = field(default_factory=list)
    balance_keywords: List[str] = field(default_factory=list)
    amount_keywords: List[str] = field(default_factory=list)  # Combined amount column


@dataclass
class RowPatterns:
    """Patterns for identifying different row types."""
    # Patterns that indicate a row should be skipped
    skip_patterns: List[str] = field(default_factory=list)

    # Patterns that indicate a header row
    header_patterns: List[str] = field(default_factory=list)

    # Pattern for new transaction start (for multi-row statements)
    transaction_start_pattern: Optional[str] = None

    # Page marker patterns
    page_patterns: List[str] = field(default_factory=list)


@dataclass
class BankProfile:
    """
    Configuration profile for a specific bank's statement format.

    This allows the parser to adapt to different bank formats without
    hardcoding assumptions.
    """
    # Basic info
    name: str
    aliases: List[str] = field(default_factory=list)  # Other names for this bank

    # Format preferences
    date_format: DateFormat = DateFormat.DMY
    amount_format: AmountFormat = AmountFormat.INDIAN
    currency: str = "INR"

    # Column identification
    column_hints: ColumnHints = field(default_factory=ColumnHints)

    # Row handling
    row_patterns: RowPatterns = field(default_factory=RowPatterns)

    # Specific parsing rules
    has_separate_debit_credit: bool = True  # False if single amount column
    has_balance_column: bool = True
    has_value_date: bool = False  # Some banks have separate value date
    multi_row_transactions: bool = False  # Description wraps to next row

    # Docling-specific settings (for PDF conversion)
    docling_datetime_pattern: Optional[str] = None
    docling_field_order: List[str] = field(default_factory=list)

    # Credit/debit detection hints (for single amount column)
    credit_indicators: List[str] = field(default_factory=list)
    debit_indicators: List[str] = field(default_factory=list)

    # Custom parsing functions (optional)
    custom_date_parser: Optional[Callable[[str], Optional[str]]] = None
    custom_amount_parser: Optional[Callable[[str], Optional[float]]] = None

    def matches_bank(self, identifier: str) -> bool:
        """Check if an identifier matches this bank profile."""
        identifier_lower = identifier.lower()
        if self.name.lower() in identifier_lower:
            return True
        for alias in self.aliases:
            if alias.lower() in identifier_lower:
                return True
        return False


# =============================================================================
# Default Column Keywords (shared across profiles)
# =============================================================================

DEFAULT_DATE_KEYWORDS = [
    "date", "txn date", "transaction date", "value date", "posting date",
    "txn dt", "trans date", "tran date", "trn date", "entry date"
]

DEFAULT_DESCRIPTION_KEYWORDS = [
    "description", "narration", "particulars", "remarks", "details",
    "transaction details", "txn description", "memo", "reference",
    "transaction narration", "txn remarks"
]

DEFAULT_DEBIT_KEYWORDS = [
    "debit", "withdrawal", "dr", "debit amount", "withdrawal amt",
    "debit amt", "withdrawals", "dr amount", "dr amt", "paid out",
    "money out", "spent"
]

DEFAULT_CREDIT_KEYWORDS = [
    "credit", "deposit", "cr", "credit amount", "deposit amt",
    "credit amt", "deposits", "cr amount", "cr amt", "paid in",
    "money in", "received"
]

DEFAULT_BALANCE_KEYWORDS = [
    "balance", "running balance", "closing balance", "available balance",
    "bal", "ledger balance", "book balance", "current balance"
]

DEFAULT_SKIP_PATTERNS = [
    "total", "opening balance", "closing balance", "statement summary",
    "account summary", "grand total", "sub total", "subtotal",
    "brought forward", "carried forward", "page total"
]


# =============================================================================
# Bank Profile Definitions
# =============================================================================

def _create_indian_bank_defaults() -> Dict[str, Any]:
    """Create default settings for Indian banks."""
    return {
        "date_format": DateFormat.DMY,
        "amount_format": AmountFormat.INDIAN,
        "currency": "INR",
        "has_separate_debit_credit": True,
        "has_balance_column": True,
        "column_hints": ColumnHints(
            date_keywords=DEFAULT_DATE_KEYWORDS,
            description_keywords=DEFAULT_DESCRIPTION_KEYWORDS,
            debit_keywords=DEFAULT_DEBIT_KEYWORDS,
            credit_keywords=DEFAULT_CREDIT_KEYWORDS,
            balance_keywords=DEFAULT_BALANCE_KEYWORDS,
        ),
        "row_patterns": RowPatterns(
            skip_patterns=DEFAULT_SKIP_PATTERNS,
            page_patterns=[r"page\s*\d+", r"page\s+\d+\s+of\s+\d+"],
        ),
        "credit_indicators": [
            "cr", "credit", "neft cr", "salary", "refund", "interest",
            "dividend", "by transfer", "by clearing", "deposit"
        ],
        "debit_indicators": [
            "dr", "debit", "neft dr", "withdrawal", "emi", "payment",
            "to transfer", "to clearing", "purchase"
        ],
    }


def _create_us_bank_defaults() -> Dict[str, Any]:
    """Create default settings for US banks."""
    return {
        "date_format": DateFormat.MDY,
        "amount_format": AmountFormat.INTERNATIONAL,
        "currency": "USD",
        "has_separate_debit_credit": False,  # US banks often use single amount with +/-
        "has_balance_column": True,
        "column_hints": ColumnHints(
            date_keywords=["date", "transaction date", "post date", "posted"],
            description_keywords=["description", "memo", "details", "transaction"],
            amount_keywords=["amount", "transaction amount"],
            balance_keywords=["balance", "running balance"],
        ),
        "row_patterns": RowPatterns(
            skip_patterns=["beginning balance", "ending balance", "total"],
        ),
    }


# Indian Bank Profiles
CANARA_BANK_PROFILE = BankProfile(
    name="Canara Bank",
    aliases=["canara", "canarabank", "canara bank ltd"],
    **_create_indian_bank_defaults(),
    has_value_date=True,
    multi_row_transactions=True,
    docling_datetime_pattern=r'^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}',
    docling_field_order=[
        "txn_datetime", "value_date", "cheque_no", "description",
        "branch_code", "amount", "balance"
    ],
)

HDFC_BANK_PROFILE = BankProfile(
    name="HDFC Bank",
    aliases=["hdfc", "hdfcbank", "hdfc ltd"],
    **_create_indian_bank_defaults(),
    column_hints=ColumnHints(
        date_keywords=["date", "value dt", "txn date"],
        description_keywords=["narration", "description", "particulars"],
        debit_keywords=["withdrawal amt", "debit"],
        credit_keywords=["deposit amt", "credit"],
        balance_keywords=["closing balance", "balance"],
    ),
)

ICICI_BANK_PROFILE = BankProfile(
    name="ICICI Bank",
    aliases=["icici", "icicibank"],
    **_create_indian_bank_defaults(),
    column_hints=ColumnHints(
        date_keywords=["transaction date", "value date", "date"],
        description_keywords=["transaction remarks", "particulars", "description"],
        debit_keywords=["withdrawal amount", "debit"],
        credit_keywords=["deposit amount", "credit"],
        balance_keywords=["balance"],
    ),
)

SBI_PROFILE = BankProfile(
    name="State Bank of India",
    aliases=["sbi", "state bank", "sbibank"],
    **_create_indian_bank_defaults(),
    column_hints=ColumnHints(
        date_keywords=["txn date", "value date", "date"],
        description_keywords=["description", "narration"],
        debit_keywords=["debit", "withdrawal"],
        credit_keywords=["credit", "deposit"],
        balance_keywords=["balance"],
    ),
)

AXIS_BANK_PROFILE = BankProfile(
    name="Axis Bank",
    aliases=["axis", "axisbank"],
    **_create_indian_bank_defaults(),
)

KOTAK_BANK_PROFILE = BankProfile(
    name="Kotak Mahindra Bank",
    aliases=["kotak", "kotakbank", "kotak mahindra"],
    **_create_indian_bank_defaults(),
)

# US Bank Profiles
CHASE_PROFILE = BankProfile(
    name="JPMorgan Chase",
    aliases=["chase", "jp morgan", "jpmorgan"],
    **_create_us_bank_defaults(),
)

WELLS_FARGO_PROFILE = BankProfile(
    name="Wells Fargo",
    aliases=["wellsfargo", "wells"],
    **_create_us_bank_defaults(),
)

BOA_PROFILE = BankProfile(
    name="Bank of America",
    aliases=["boa", "bofa", "bank of america"],
    **_create_us_bank_defaults(),
)

CITI_PROFILE = BankProfile(
    name="Citibank",
    aliases=["citi", "citibank"],
    **_create_us_bank_defaults(),
)

# UK/EU Bank Profiles
BARCLAYS_PROFILE = BankProfile(
    name="Barclays",
    aliases=["barclays bank"],
    date_format=DateFormat.DMY,
    amount_format=AmountFormat.INTERNATIONAL,
    currency="GBP",
    has_separate_debit_credit=False,
    has_balance_column=True,
)

HSBC_PROFILE = BankProfile(
    name="HSBC",
    aliases=["hsbc bank", "hongkong shanghai"],
    date_format=DateFormat.DMY,
    amount_format=AmountFormat.INTERNATIONAL,
    currency="GBP",
    has_separate_debit_credit=True,
    has_balance_column=True,
)

# Generic profile (fallback)
GENERIC_PROFILE = BankProfile(
    name="Generic",
    aliases=[],
    date_format=DateFormat.DMY,
    amount_format=AmountFormat.INTERNATIONAL,
    currency="INR",
    has_separate_debit_credit=True,
    has_balance_column=True,
    column_hints=ColumnHints(
        date_keywords=DEFAULT_DATE_KEYWORDS,
        description_keywords=DEFAULT_DESCRIPTION_KEYWORDS,
        debit_keywords=DEFAULT_DEBIT_KEYWORDS,
        credit_keywords=DEFAULT_CREDIT_KEYWORDS,
        balance_keywords=DEFAULT_BALANCE_KEYWORDS,
    ),
    row_patterns=RowPatterns(
        skip_patterns=DEFAULT_SKIP_PATTERNS,
        page_patterns=[r"page\s*\d+", r"page\s+\d+\s+of\s+\d+", r"page\s+\d+[-/]\d+"],
    ),
    credit_indicators=[
        "cr", "credit", "neft cr", "salary", "refund", "interest",
        "dividend", "deposit", "received", "by"
    ],
    debit_indicators=[
        "dr", "debit", "neft dr", "withdrawal", "emi", "payment",
        "purchase", "to", "paid"
    ],
)

# All registered profiles
ALL_PROFILES: List[BankProfile] = [
    CANARA_BANK_PROFILE,
    HDFC_BANK_PROFILE,
    ICICI_BANK_PROFILE,
    SBI_PROFILE,
    AXIS_BANK_PROFILE,
    KOTAK_BANK_PROFILE,
    CHASE_PROFILE,
    WELLS_FARGO_PROFILE,
    BOA_PROFILE,
    CITI_PROFILE,
    BARCLAYS_PROFILE,
    HSBC_PROFILE,
]


class BankProfileManager:
    """
    Manager for bank profiles.

    Provides methods to:
    - Detect bank from statement content
    - Get appropriate profile for parsing
    - Merge custom settings with profiles
    """

    def __init__(self):
        self.profiles = {p.name: p for p in ALL_PROFILES}
        self.generic_profile = GENERIC_PROFILE

    def get_profile(self, bank_name: str) -> BankProfile:
        """
        Get a bank profile by name or alias.

        Args:
            bank_name: Bank name or alias

        Returns:
            Matching BankProfile or generic profile
        """
        bank_lower = bank_name.lower()

        # Direct match
        for name, profile in self.profiles.items():
            if name.lower() == bank_lower:
                return profile

        # Alias match
        for profile in self.profiles.values():
            if profile.matches_bank(bank_name):
                return profile

        return self.generic_profile

    def detect_bank_from_content(
        self,
        content: str,
        filename: Optional[str] = None
    ) -> BankProfile:
        """
        Attempt to detect bank from statement content or filename.

        Args:
            content: Statement content (text or first few rows as string)
            filename: Optional filename which might contain bank name

        Returns:
            Best matching BankProfile
        """
        search_text = content.lower()
        if filename:
            search_text += " " + filename.lower()

        # Score each profile
        best_profile = self.generic_profile
        best_score = 0

        for profile in self.profiles.values():
            score = 0

            # Check name
            if profile.name.lower() in search_text:
                score += 10

            # Check aliases
            for alias in profile.aliases:
                if alias.lower() in search_text:
                    score += 5

            if score > best_score:
                best_score = score
                best_profile = profile

        return best_profile

    def detect_bank_from_rows(
        self,
        rows: List[List[str]],
        filename: Optional[str] = None
    ) -> BankProfile:
        """
        Detect bank from parsed CSV/XLSX rows.

        Args:
            rows: List of rows from the file
            filename: Optional filename

        Returns:
            Best matching BankProfile
        """
        # Combine first 20 rows into text for detection
        text_parts = []
        for row in rows[:20]:
            text_parts.extend(str(cell) for cell in row)

        content = " ".join(text_parts)
        return self.detect_bank_from_content(content, filename)

    def get_column_keywords(self, profile: BankProfile) -> Dict[str, List[str]]:
        """
        Get merged column keywords for a profile.

        Combines profile-specific keywords with defaults.
        """
        hints = profile.column_hints

        return {
            "date": list(set(hints.date_keywords or DEFAULT_DATE_KEYWORDS)),
            "description": list(set(hints.description_keywords or DEFAULT_DESCRIPTION_KEYWORDS)),
            "debit": list(set(hints.debit_keywords or DEFAULT_DEBIT_KEYWORDS)),
            "credit": list(set(hints.credit_keywords or DEFAULT_CREDIT_KEYWORDS)),
            "balance": list(set(hints.balance_keywords or DEFAULT_BALANCE_KEYWORDS)),
            "amount": list(set(hints.amount_keywords or ["amount", "transaction amount"])),
        }

    def get_skip_patterns(self, profile: BankProfile) -> List[str]:
        """Get skip patterns for a profile."""
        patterns = profile.row_patterns.skip_patterns or []
        return list(set(patterns + DEFAULT_SKIP_PATTERNS))

    def should_skip_row(self, row: List[str], profile: BankProfile) -> bool:
        """
        Check if a row should be skipped based on profile patterns.

        Args:
            row: Row data
            profile: Bank profile

        Returns:
            True if row should be skipped
        """
        row_text = " ".join(str(c).lower() for c in row if str(c).strip())

        # Check skip patterns
        for pattern in self.get_skip_patterns(profile):
            if pattern.lower() in row_text:
                return True

        # Check page patterns
        for page_pattern in (profile.row_patterns.page_patterns or []):
            if re.search(page_pattern, row_text, re.IGNORECASE):
                return True

        return False

    def is_transaction_start(
        self,
        content: str,
        profile: BankProfile
    ) -> bool:
        """
        Check if content marks the start of a new transaction.

        Used for multi-row transaction detection in Docling format.
        """
        if not profile.multi_row_transactions:
            return False

        pattern = profile.docling_datetime_pattern
        if pattern:
            return bool(re.match(pattern, content))

        # Generic datetime patterns to try
        generic_patterns = [
            r'^\d{2}[-/]\d{2}[-/]\d{4}\s+\d{2}:\d{2}',  # DD-MM-YYYY HH:MM
            r'^\d{2}[-/]\d{2}[-/]\d{4}',  # DD-MM-YYYY
            r'^\d{4}[-/]\d{2}[-/]\d{2}',  # YYYY-MM-DD
        ]

        for p in generic_patterns:
            if re.match(p, content):
                return True

        return False

    def infer_credit_debit(
        self,
        description: str,
        profile: BankProfile
    ) -> str:
        """
        Infer if a transaction is credit or debit from description.

        Args:
            description: Transaction description
            profile: Bank profile

        Returns:
            "credit", "debit", or "unknown"
        """
        desc_lower = description.lower()

        # Check credit indicators
        credit_indicators = profile.credit_indicators or []
        for indicator in credit_indicators:
            if indicator.lower() in desc_lower:
                return "credit"

        # Check debit indicators
        debit_indicators = profile.debit_indicators or []
        for indicator in debit_indicators:
            if indicator.lower() in desc_lower:
                return "debit"

        return "unknown"


# Global instance
_profile_manager: Optional[BankProfileManager] = None


def get_profile_manager() -> BankProfileManager:
    """Get the global profile manager instance."""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = BankProfileManager()
    return _profile_manager


def detect_bank(
    content: str = "",
    rows: Optional[List[List[str]]] = None,
    filename: Optional[str] = None
) -> BankProfile:
    """
    Convenience function to detect bank and get profile.

    Args:
        content: Statement content as text
        rows: Parsed rows (alternative to content)
        filename: Optional filename

    Returns:
        Best matching BankProfile
    """
    manager = get_profile_manager()

    if rows:
        return manager.detect_bank_from_rows(rows, filename)
    elif content:
        return manager.detect_bank_from_content(content, filename)
    else:
        return manager.generic_profile


def get_bank_profile(bank_name: str) -> BankProfile:
    """
    Get a bank profile by name.

    Args:
        bank_name: Bank name or alias

    Returns:
        BankProfile
    """
    manager = get_profile_manager()
    return manager.get_profile(bank_name)
