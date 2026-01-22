"""
Abstract base class for bank statement parsers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class Transaction:
    """
    Represents a normalized bank transaction.
    """
    date: Optional[date]
    description: str
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None
    raw_text: str = ""
    row_numbers: List[int] = field(default_factory=list)

    # Categorization fields (populated later)
    category: str = ""
    subcategory: str = ""
    categorization_confidence: float = 0.0
    categorization_source: str = ""  # "rules", "haiku", or "flagged"
    haiku_suggestion: str = ""  # If flagged, what Haiku suggested

    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to dictionary."""
        return {
            'date': self.date,
            'description': self.description,
            'debit': self.debit,
            'credit': self.credit,
            'balance': self.balance,
            'raw_text': self.raw_text,
            'row_numbers': self.row_numbers,
            'category': self.category,
            'subcategory': self.subcategory,
            'categorization_confidence': self.categorization_confidence,
            'categorization_source': self.categorization_source,
            'haiku_suggestion': self.haiku_suggestion,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create transaction from dictionary."""
        return cls(
            date=data.get('date'),
            description=data.get('description', ''),
            debit=data.get('debit'),
            credit=data.get('credit'),
            balance=data.get('balance'),
            raw_text=data.get('raw_text', ''),
            row_numbers=data.get('row_numbers', []),
            category=data.get('category', ''),
            subcategory=data.get('subcategory', ''),
            categorization_confidence=data.get('categorization_confidence', 0.0),
            categorization_source=data.get('categorization_source', ''),
            haiku_suggestion=data.get('haiku_suggestion', ''),
        )

    @property
    def amount(self) -> float:
        """Get the transaction amount (positive for credit, negative for debit)."""
        if self.credit is not None:
            return self.credit
        elif self.debit is not None:
            return -self.debit
        return 0.0

    @property
    def is_debit(self) -> bool:
        """Check if this is a debit transaction."""
        return self.debit is not None and self.debit > 0

    @property
    def is_credit(self) -> bool:
        """Check if this is a credit transaction."""
        return self.credit is not None and self.credit > 0


@dataclass
class ValidationIssue:
    """
    Represents a validation issue found during parsing.
    """
    row_numbers: List[int]
    issue_type: str
    message: str
    severity: str = "warning"  # "warning" or "error"


class BaseParser(ABC):
    """
    Abstract base class for bank statement parsers.
    """

    def __init__(self, filepath: str):
        """
        Initialize the parser with a file path.

        Args:
            filepath: Path to the bank statement file
        """
        self.filepath = filepath
        self._transactions: List[Transaction] = []
        self._validation_issues: List[ValidationIssue] = []

    @abstractmethod
    def parse(self) -> List[Transaction]:
        """
        Parse the bank statement file and return normalized transactions.

        Returns:
            List of Transaction objects
        """
        pass

    def validate(self) -> List[ValidationIssue]:
        """
        Validate the parsed transactions and return any issues found.

        Returns:
            List of ValidationIssue objects
        """
        issues = []

        for i, txn in enumerate(self._transactions):
            # Check for missing date
            if txn.date is None:
                issues.append(ValidationIssue(
                    row_numbers=txn.row_numbers,
                    issue_type="missing_date",
                    message=f"Transaction {i+1} has no valid date",
                    severity="warning"
                ))

            # Check for empty description
            if not txn.description or not txn.description.strip():
                issues.append(ValidationIssue(
                    row_numbers=txn.row_numbers,
                    issue_type="missing_description",
                    message=f"Transaction {i+1} has no description",
                    severity="warning"
                ))

            # Check for missing amount
            if txn.debit is None and txn.credit is None:
                issues.append(ValidationIssue(
                    row_numbers=txn.row_numbers,
                    issue_type="missing_amount",
                    message=f"Transaction {i+1} has no debit or credit amount",
                    severity="warning"
                ))

            # Check for zero amount
            if (txn.debit == 0 or txn.credit == 0) and txn.debit != txn.credit:
                issues.append(ValidationIssue(
                    row_numbers=txn.row_numbers,
                    issue_type="zero_amount",
                    message=f"Transaction {i+1} has a zero amount",
                    severity="warning"
                ))

        self._validation_issues = issues
        return issues

    @property
    def transactions(self) -> List[Transaction]:
        """Get the parsed transactions."""
        return self._transactions

    @property
    def validation_issues(self) -> List[ValidationIssue]:
        """Get validation issues."""
        return self._validation_issues

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the parsed transactions.

        Returns:
            Dictionary with summary statistics
        """
        if not self._transactions:
            return {
                'total_transactions': 0,
                'total_debits': 0.0,
                'total_credits': 0.0,
                'date_range': (None, None),
            }

        total_debits = sum(t.debit or 0 for t in self._transactions)
        total_credits = sum(t.credit or 0 for t in self._transactions)

        dates = [t.date for t in self._transactions if t.date is not None]
        date_range = (min(dates), max(dates)) if dates else (None, None)

        return {
            'total_transactions': len(self._transactions),
            'total_debits': total_debits,
            'total_credits': total_credits,
            'net_flow': total_credits - total_debits,
            'date_range': date_range,
            'debit_count': sum(1 for t in self._transactions if t.is_debit),
            'credit_count': sum(1 for t in self._transactions if t.is_credit),
        }
