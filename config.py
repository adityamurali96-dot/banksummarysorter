"""
Configuration and constants for the bank statement processor.

This module provides:
- Default configurations for parsing and categorization
- Support for user-configurable settings via environment variables
- Loading custom rules from YAML files
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

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

# Using Claude 3.5 Haiku (latest model)
HAIKU_MODEL: str = "claude-3-5-haiku-latest"
HAIKU_MAX_TOKENS: int = 100

# =============================================================================
# Application Info
# =============================================================================

APP_NAME: str = "Bank Statement Processor"
APP_VERSION: str = "1.0.0"
APP_AUTHOR: str = "V Raghavendran and Co."

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
    "utf-8-sig",      # Excel CSV with BOM
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


# =============================================================================
# Flexible Configuration System
# =============================================================================

class Config:
    """
    Flexible configuration manager that supports:
    - Environment variables
    - Custom YAML configuration files
    - Runtime overrides
    """

    _instance: Optional["Config"] = None
    _custom_rules: Dict[str, Any] = {}
    _settings: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_defaults()
            cls._instance._load_custom_config()
        return cls._instance

    def _load_defaults(self) -> None:
        """Load default settings."""
        self._settings = {
            # Parsing settings
            "date_format_preference": os.environ.get("DATE_FORMAT", "dmy"),
            "amount_format": os.environ.get("AMOUNT_FORMAT", "indian"),
            "default_currency": os.environ.get("DEFAULT_CURRENCY", "INR"),

            # Categorization settings
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "rule_based_confidence": RULE_BASED_CONFIDENCE,
            "use_smart_rules": os.environ.get("USE_SMART_RULES", "true").lower() == "true",
            "flag_low_confidence": os.environ.get("FLAG_LOW_CONFIDENCE", "true").lower() == "true",

            # API settings
            "haiku_model": HAIKU_MODEL,
            "haiku_max_tokens": HAIKU_MAX_TOKENS,
            "api_retry_count": int(os.environ.get("API_RETRY_COUNT", "3")),
            "api_timeout": int(os.environ.get("API_TIMEOUT", "30")),

            # File settings
            "supported_encodings": FILE_ENCODINGS,
            "max_rows_preview": int(os.environ.get("MAX_ROWS_PREVIEW", "10")),

            # Bank detection
            "auto_detect_bank": os.environ.get("AUTO_DETECT_BANK", "true").lower() == "true",
            "default_bank_profile": os.environ.get("DEFAULT_BANK_PROFILE", "generic"),
        }

    def _load_custom_config(self) -> None:
        """Load custom configuration from YAML file if available."""
        # Look for config file in multiple locations
        config_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path(__file__).parent / "config.yaml",
            Path.home() / ".banksummarysorter" / "config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        custom_config = yaml.safe_load(f) or {}
                        self._settings.update(custom_config)
                        print(f"Loaded config from {config_path}")
                        break
                except Exception as e:
                    print(f"Warning: Could not load config from {config_path}: {e}")

        # Load custom rules
        self._load_custom_rules()

    def _load_custom_rules(self) -> None:
        """Load custom categorization rules from YAML."""
        rules_paths = [
            Path.cwd() / "custom_rules.yaml",
            Path.cwd() / "custom_rules.yml",
            Path(__file__).parent / "custom_rules.yaml",
            Path.home() / ".banksummarysorter" / "custom_rules.yaml",
        ]

        for rules_path in rules_paths:
            if rules_path.exists():
                try:
                    with open(rules_path, 'r', encoding='utf-8') as f:
                        self._custom_rules = yaml.safe_load(f) or {}
                        print(f"Loaded custom rules from {rules_path}")
                        break
                except Exception as e:
                    print(f"Warning: Could not load custom rules from {rules_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value at runtime."""
        self._settings[key] = value

    @property
    def custom_rules(self) -> Dict[str, Any]:
        """Get custom categorization rules."""
        return self._custom_rules

    @property
    def keyword_groups(self) -> Dict[str, List[str]]:
        """Get keyword groups from custom rules."""
        return self._custom_rules.get("keyword_groups", {})

    @property
    def regional_settings(self) -> Dict[str, Any]:
        """Get regional settings from custom rules."""
        return self._custom_rules.get("regional", {
            "date_format": "dmy",
            "currency": "INR",
            "decimal_separator": ".",
            "thousand_separator": ",",
            "indian_numbering": True,
        })

    def get_date_format_preference(self) -> str:
        """Get the preferred date format (dmy, mdy, ymd)."""
        regional = self.regional_settings
        return regional.get("date_format", self.get("date_format_preference", "dmy"))

    def is_indian_numbering(self) -> bool:
        """Check if Indian numbering system should be used."""
        regional = self.regional_settings
        return regional.get("indian_numbering", True)

    def reload(self) -> None:
        """Reload configuration from files."""
        self._load_defaults()
        self._load_custom_config()


def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()


# =============================================================================
# Helper Functions for Backward Compatibility
# =============================================================================

def get_date_formats() -> List[str]:
    """Get date formats in preference order based on config."""
    config = get_config()
    preference = config.get_date_format_preference()

    if preference == "mdy":
        # US format first
        return [
            "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y",
        ] + DATE_FORMATS
    elif preference == "ymd":
        # ISO format first
        return [
            "%Y-%m-%d", "%Y/%m/%d",
        ] + DATE_FORMATS
    else:
        # Default DMY (most countries including India)
        return DATE_FORMATS


def get_column_keywords() -> Dict[str, List[str]]:
    """Get all column keywords as a dictionary."""
    return {
        "date": DATE_COLUMN_KEYWORDS,
        "description": DESCRIPTION_COLUMN_KEYWORDS,
        "debit": DEBIT_COLUMN_KEYWORDS,
        "credit": CREDIT_COLUMN_KEYWORDS,
        "balance": BALANCE_COLUMN_KEYWORDS,
    }


def get_skip_keywords() -> List[str]:
    """Get keywords that indicate rows to skip."""
    return SKIP_ROW_KEYWORDS
