"""
Amount parser for handling Indian number formats and currency.
"""
import re
from typing import Optional, Tuple, Union


def parse_amount(value: Union[str, int, float, None]) -> float:
    """
    Parse an amount value from various formats into a float.

    Handles:
    - Indian number format: "9,17,390.58" (lakhs format with commas)
    - International format: "917,390.58"
    - Currency symbols: ₹, Rs, Rs., INR
    - Negative formats: -1000, (1000), 1000 DR, 1000 CR

    Args:
        value: A string/number that might be an amount

    Returns:
        A float value (positive or negative), or 0.0 if unparseable
    """
    if value is None:
        return 0.0

    # If already a number
    if isinstance(value, (int, float)):
        return float(value)

    # Convert to string and clean up
    value_str = str(value).strip()

    if not value_str:
        return 0.0

    # Parse the amount
    amount, _ = _parse_amount_with_sign(value_str)
    return amount


def _parse_amount_with_sign(value_str: str) -> Tuple[float, str]:
    """
    Parse an amount string and determine its sign.

    Args:
        value_str: Raw amount string

    Returns:
        Tuple of (amount as float, sign indicator: 'CR', 'DR', or '')
    """
    original = value_str
    value_str = value_str.strip()

    # Check for sign indicators
    is_negative = False
    sign_indicator = ""

    # Check for DR/CR suffix (case-insensitive)
    dr_match = re.search(r'\s*(DR|Dr|dr)\s*$', value_str)
    cr_match = re.search(r'\s*(CR|Cr|cr)\s*$', value_str)

    if dr_match:
        is_negative = True
        sign_indicator = "DR"
        value_str = value_str[:dr_match.start()]
    elif cr_match:
        is_negative = False
        sign_indicator = "CR"
        value_str = value_str[:cr_match.start()]

    # Check for parentheses: (1000) means negative
    if value_str.startswith('(') and value_str.endswith(')'):
        is_negative = True
        value_str = value_str[1:-1]

    # Check for leading minus sign
    if value_str.startswith('-'):
        is_negative = True
        value_str = value_str[1:]

    # Check for trailing minus sign (some formats use this)
    if value_str.endswith('-'):
        is_negative = True
        value_str = value_str[:-1]

    # Remove currency symbols
    value_str = _remove_currency_symbols(value_str)

    # Clean up and parse the numeric value
    value_str = value_str.strip()

    if not value_str:
        return 0.0, sign_indicator

    # Remove all commas (handles both Indian and international format)
    value_str = value_str.replace(',', '')

    # Remove spaces that might be used as thousand separators
    value_str = value_str.replace(' ', '')

    # Handle cases where decimal is represented differently
    # Some formats use space before decimal: "1000 50" = 1000.50

    try:
        amount = float(value_str)
        if is_negative:
            amount = -abs(amount)
        return amount, sign_indicator
    except ValueError:
        return 0.0, sign_indicator


def _remove_currency_symbols(value_str: str) -> str:
    """
    Remove currency symbols from a string.

    Args:
        value_str: String potentially containing currency symbols

    Returns:
        String with currency symbols removed
    """
    # Remove common currency symbols and prefixes
    patterns = [
        r'₹\s*',           # Rupee symbol
        r'Rs\.?\s*',       # Rs or Rs.
        r'INR\s*',         # INR
        r'USD\s*',         # USD
        r'\$\s*',          # Dollar
        r'€\s*',           # Euro
        r'£\s*',           # Pound
    ]

    for pattern in patterns:
        value_str = re.sub(pattern, '', value_str, flags=re.IGNORECASE)

    return value_str


def has_valid_amount(value: Union[str, int, float, None]) -> bool:
    """
    Check if a value contains a parseable amount.

    Args:
        value: A value to check

    Returns:
        True if the value contains a valid amount, False otherwise
    """
    if value is None:
        return False

    if isinstance(value, (int, float)):
        return True

    value_str = str(value).strip()

    if not value_str:
        return False

    # Remove known non-numeric parts
    cleaned = _remove_currency_symbols(value_str)
    cleaned = re.sub(r'(DR|CR|Dr|Cr|dr|cr)\s*$', '', cleaned)
    cleaned = cleaned.strip()

    # Remove parentheses
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1]

    # Remove sign
    cleaned = cleaned.lstrip('-').rstrip('-')

    # Remove commas and spaces
    cleaned = cleaned.replace(',', '').replace(' ', '')

    if not cleaned:
        return False

    # Check if it's a valid number
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def parse_debit_credit(
    value: Union[str, int, float, None],
    column_type: Optional[str] = None
) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse a value into debit and credit amounts.

    Args:
        value: The value to parse
        column_type: Hint for the column type ('debit', 'credit', or None)

    Returns:
        Tuple of (debit_amount, credit_amount) - one will be None
    """
    if value is None:
        return None, None

    amount, sign_indicator = _parse_amount_with_sign(str(value).strip())

    if amount == 0.0 and not has_valid_amount(value):
        return None, None

    # If sign indicator is present, use it
    if sign_indicator == "DR":
        return abs(amount), None
    elif sign_indicator == "CR":
        return None, abs(amount)

    # If column type is specified, use it
    if column_type == "debit":
        if amount != 0.0:
            return abs(amount), None
        return None, None
    elif column_type == "credit":
        if amount != 0.0:
            return None, abs(amount)
        return None, None

    # Default: negative = debit, positive = credit
    if amount < 0:
        return abs(amount), None
    elif amount > 0:
        return None, amount
    else:
        return None, None


def format_indian_currency(amount: Optional[float], include_symbol: bool = True) -> str:
    """
    Format an amount in Indian currency format.

    Args:
        amount: The amount to format
        include_symbol: Whether to include the ₹ symbol

    Returns:
        Formatted currency string
    """
    if amount is None:
        return ""

    # Handle negative amounts
    is_negative = amount < 0
    amount = abs(amount)

    # Split into integer and decimal parts
    # Use round to avoid floating-point precision issues (e.g. 1000.00 - 1000 = 5.6e-11)
    integer_part = int(amount)
    decimal_part = round(amount - integer_part, 2)

    # Format integer part with Indian grouping (lakhs format)
    int_str = str(integer_part)

    if len(int_str) > 3:
        # First group of 3 from right
        result = int_str[-3:]
        int_str = int_str[:-3]

        # Remaining groups of 2
        while int_str:
            result = int_str[-2:] + ',' + result
            int_str = int_str[:-2]
    else:
        result = int_str

    # Add decimal part
    if decimal_part > 0:
        decimal_str = f"{decimal_part:.2f}"[1:]  # Remove leading 0
        result = result + decimal_str
    else:
        result = result + ".00"

    # Add sign and symbol
    if is_negative:
        result = "-" + result

    if include_symbol:
        result = "₹" + result

    return result
