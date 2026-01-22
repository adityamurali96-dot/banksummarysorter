"""
Date parser for handling multiple Indian date formats.
"""
import re
from datetime import date, datetime
from typing import Optional, Union

from config import DATE_FORMATS


def parse_date(value: Union[str, datetime, date, None]) -> Optional[date]:
    """
    Parse a date value from various formats into a Python date object.

    Args:
        value: A string that might be a date, or a datetime/date object

    Returns:
        A date object if parsing succeeds, None otherwise
    """
    if value is None:
        return None

    # If already a date or datetime object
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    # Convert to string and clean up
    value_str = str(value).strip()

    if not value_str:
        return None

    # Normalize the string
    value_str = _normalize_date_string(value_str)

    # Try each date format in order
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value_str, fmt)
            return parsed.date()
        except ValueError:
            continue

    # Try dateutil as a fallback for more flexible parsing
    try:
        from dateutil import parser as dateutil_parser
        # Use dayfirst=True for Indian date format (DD/MM/YYYY)
        parsed = dateutil_parser.parse(value_str, dayfirst=True)
        return parsed.date()
    except (ValueError, TypeError, ImportError):
        pass

    return None


def _normalize_date_string(value: str) -> str:
    """
    Normalize a date string by cleaning up whitespace and separators.

    Args:
        value: Raw date string

    Returns:
        Normalized date string
    """
    # Remove extra whitespace
    value = " ".join(value.split())

    # Remove leading/trailing whitespace
    value = value.strip()

    # Handle mixed separators (e.g., "15/01-2025" -> "15/01/2025")
    # If we have both / and - in a date, standardize to /
    if "/" in value and "-" in value:
        # Check if it looks like a date with mixed separators
        # Be careful not to change formats like "15-Jan-2025"
        if not any(c.isalpha() for c in value):
            value = value.replace("-", "/")

    return value


def is_valid_date(value: Union[str, datetime, date, None]) -> bool:
    """
    Check if a value can be parsed as a valid date.

    Args:
        value: A value to check

    Returns:
        True if the value is a valid date, False otherwise
    """
    return parse_date(value) is not None


def extract_date_from_string(text: str) -> Optional[date]:
    """
    Try to extract a date from a string that might contain other text.

    Args:
        text: A string that might contain a date somewhere

    Returns:
        A date object if a date is found, None otherwise
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # Common date patterns to look for
    date_patterns = [
        # DD/MM/YYYY or DD-MM-YYYY
        r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b',
        # YYYY-MM-DD
        r'\b(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b',
        # DD MMM YYYY or DD-MMM-YYYY
        r'\b(\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-]\d{2,4})\b',
        # DD.MM.YYYY
        r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b',
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            potential_date = match.group(1)
            parsed = parse_date(potential_date)
            if parsed:
                return parsed

    return None


def format_date(dt: Optional[date], fmt: str = "%d-%b-%Y") -> str:
    """
    Format a date object as a string.

    Args:
        dt: Date object to format
        fmt: Output format string (default: DD-MMM-YYYY)

    Returns:
        Formatted date string, or empty string if date is None
    """
    if dt is None:
        return ""
    return dt.strftime(fmt)
