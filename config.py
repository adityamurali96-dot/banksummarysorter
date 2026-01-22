"""
Configuration and constants for the bank statement processor.
"""
import os
from typing import Dict, List, Tuple

# =============================================================================
# Date Formats
# =============================================================================

# Supported date formats in order of preference
DATE_FORMATS: List[str] = [
    "%d/%m/%Y",      # DD/MM/YYYY
    "%d-%m-%Y",      # DD-MM-YYYY
    "%d/%m/%y",      # DD/MM/YY
    "%d-%m-%y",      # DD-MM-YY
    "%Y-%m-%d",      # YYYY-MM-DD (ISO format)
    "%d %b %Y",      # DD MMM YYYY (like "15 Jan 2025")
    "%d-%b-%Y",      # DD-MMM-YYYY (like "15-Jan-2025")
    "%d %B %Y",      # DD Month YYYY (like "15 January 2025")
    "%d-%B-%Y",      # DD-Month-YYYY
    "%d.%m.%Y",      # DD.MM.YYYY (European format)
    "%d.%m.%y",      # DD.MM.YY
]

# =============================================================================
# Category Taxonomy
# =============================================================================

CATEGORIES: Dict[str, List[str]] = {
    "Income": [
        "Salary",
        "Business Income",
        "Interest",
        "Dividend",
        "Refund",
        "Rental Income",
        "Other Income",
    ],
    "Shopping": [
        "Online Shopping",
        "Groceries",
        "Electronics",
        "Clothing",
        "Home & Furniture",
        "Other Shopping",
    ],
    "Food & Dining": [
        "Restaurant",
        "Food Delivery",
        "Cafe/Coffee",
        "Other Food",
    ],
    "Transport": [
        "Fuel",
        "Cab/Taxi",
        "Public Transport",
        "Flight",
        "Train",
        "Other Travel",
    ],
    "Bills & Utilities": [
        "Electricity",
        "Mobile/Internet",
        "Water",
        "Gas",
        "Rent",
        "Subscriptions",
        "Other Bills",
    ],
    "Investments": [
        "Mutual Funds",
        "Stocks",
        "Fixed Deposit",
        "PPF",
        "NPS",
        "Other Investment",
    ],
    "Insurance": [
        "Life Insurance",
        "Health Insurance",
        "Vehicle Insurance",
        "Other Insurance",
    ],
    "Transfer": [
        "Bank Transfer",
        "Self Transfer",
        "Family Transfer",
    ],
    "Healthcare": [
        "Hospital",
        "Pharmacy",
        "Doctor/Consultation",
        "Lab Tests",
    ],
    "Education": [
        "School/College Fees",
        "Books",
        "Online Courses",
    ],
    "Entertainment": [
        "Movies",
        "Events",
        "Gaming",
        "OTT Subscriptions",
    ],
    "Taxes": [
        "GST Payment",
        "Income Tax",
        "TDS",
        "Professional Tax",
        "Tax Refund",
    ],
    "Business Expense": [
        "Vendor Payment",
        "Professional Services",
        "Office Supplies",
    ],
    "Cash": [
        "ATM Withdrawal",
        "Cash Deposit",
    ],
    "Bank Charges": [
        "Service Charges",
        "Penalties",
        "Interest Paid",
    ],
    "Other": [
        "Uncategorized",
    ],
    "Review Required": [
        "Manual Review Needed",
    ],
}

# =============================================================================
# Column Name Mappings for Parser
# =============================================================================

# Keywords to identify date columns
DATE_COLUMN_KEYWORDS: List[str] = [
    "date",
    "txn date",
    "transaction date",
    "value date",
    "posting date",
    "txn dt",
    "trans date",
]

# Keywords to identify description columns
DESCRIPTION_COLUMN_KEYWORDS: List[str] = [
    "description",
    "narration",
    "particulars",
    "remarks",
    "details",
    "transaction details",
    "txn description",
]

# Keywords to identify debit columns
DEBIT_COLUMN_KEYWORDS: List[str] = [
    "debit",
    "withdrawal",
    "dr",
    "debit amount",
    "withdrawal amt",
    "debit amt",
    "withdrawals",
]

# Keywords to identify credit columns
CREDIT_COLUMN_KEYWORDS: List[str] = [
    "credit",
    "deposit",
    "cr",
    "credit amount",
    "deposit amt",
    "credit amt",
    "deposits",
]

# Keywords to identify balance columns
BALANCE_COLUMN_KEYWORDS: List[str] = [
    "balance",
    "running balance",
    "closing balance",
    "available balance",
    "bal",
]

# Keywords to identify header rows
HEADER_KEYWORDS: List[str] = [
    "date",
    "description",
    "narration",
    "particulars",
    "debit",
    "credit",
    "withdrawal",
    "deposit",
    "balance",
]

# Keywords to skip rows (summary/garbage rows)
SKIP_ROW_KEYWORDS: List[str] = [
    "total",
    "opening balance",
    "closing balance",
    "statement summary",
    "account summary",
    "grand total",
    "sub total",
    "subtotal",
]

# =============================================================================
# Haiku API Settings
# =============================================================================

HAIKU_MODEL: str = "claude-3-5-haiku-latest"
HAIKU_MAX_TOKENS: int = 100

# =============================================================================
# Categorization Settings
# =============================================================================

# Default confidence threshold for flagging transactions
DEFAULT_CONFIDENCE_THRESHOLD: float = float(
    os.environ.get("CATEGORIZER_CONFIDENCE_THRESHOLD", "0.8")
)

# Confidence level for rule-based matches
RULE_BASED_CONFIDENCE: float = 0.95

# =============================================================================
# File Encodings to Try
# =============================================================================

FILE_ENCODINGS: List[str] = [
    "utf-8",
    "cp1252",
    "iso-8859-1",
    "utf-16",
]

# =============================================================================
# API Key
# =============================================================================

def get_api_key() -> str:
    """Get the Anthropic API key from environment variable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return api_key


def get_category_list_for_prompt() -> str:
    """Generate a formatted category list for the Haiku prompt."""
    lines = []
    for category, subcategories in CATEGORIES.items():
        if category not in ("Review Required",):
            subcats = ", ".join(subcategories)
            lines.append(f"- {category}: {subcats}")
    return "\n".join(lines)
