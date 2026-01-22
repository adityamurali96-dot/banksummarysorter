"""
Main categorization orchestrator.

Combines rule-based and Haiku API categorization with confidence-based flagging.
"""
from typing import List, Optional, Tuple

from config import DEFAULT_CONFIDENCE_THRESHOLD
from categorizer.haiku_client import HaikuCategorizer
from categorizer.rules import rule_based_categorize
from parsers.base_parser import Transaction


class TransactionCategorizer:
    """
    Orchestrates transaction categorization using rules and Haiku API.

    Strategy:
    1. Try rule-based categorization first (fast, no API cost)
    2. If no rule matches, use Haiku API
    3. If Haiku confidence < threshold, flag for manual review
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    ):
        """
        Initialize the categorizer.

        Args:
            api_key: Anthropic API key for Haiku
            confidence_threshold: Minimum confidence to accept Haiku result
        """
        self.confidence_threshold = confidence_threshold
        self._haiku_client: Optional[HaikuCategorizer] = None

        if api_key:
            self._haiku_client = HaikuCategorizer(api_key)

        # Statistics
        self._stats = {
            'total': 0,
            'rules_matched': 0,
            'haiku_matched': 0,
            'flagged': 0,
            'haiku_failed': 0,
        }

    def categorize_all(self, transactions: List[Transaction]) -> List[Transaction]:
        """
        Categorize all transactions.

        Args:
            transactions: List of transactions to categorize

        Returns:
            Same list of transactions with categorization fields populated
        """
        total = len(transactions)
        self._stats = {
            'total': total,
            'rules_matched': 0,
            'haiku_matched': 0,
            'flagged': 0,
            'haiku_failed': 0,
        }

        print(f"\nCategorizing {total} transactions...")
        print(f"Confidence threshold: {self.confidence_threshold}")

        # First pass: rule-based categorization
        need_haiku: List[int] = []  # Indices of transactions needing Haiku

        for i, txn in enumerate(transactions):
            result = rule_based_categorize(txn.description)

            if result:
                category, subcategory, confidence = result
                txn.category = category
                txn.subcategory = subcategory
                txn.categorization_confidence = confidence
                txn.categorization_source = "rules"
                self._stats['rules_matched'] += 1
            else:
                need_haiku.append(i)

        print(f"  Rule-based matches: {self._stats['rules_matched']}")
        print(f"  Need Haiku: {len(need_haiku)}")

        # Second pass: Haiku API for unmatched transactions
        if need_haiku and self._haiku_client and self._haiku_client.is_available():
            print(f"  Calling Haiku API for {len(need_haiku)} transactions...")

            for idx, i in enumerate(need_haiku):
                if (idx + 1) % 20 == 0 or idx == len(need_haiku) - 1:
                    print(f"    Progress: {idx + 1}/{len(need_haiku)}")

                txn = transactions[i]
                self._categorize_with_haiku(txn)

        elif need_haiku and (not self._haiku_client or not self._haiku_client.is_available()):
            print("  Warning: Haiku not available, flagging remaining transactions")
            for i in need_haiku:
                txn = transactions[i]
                txn.category = "Review Required"
                txn.subcategory = "Manual Review Needed"
                txn.categorization_confidence = 0.0
                txn.categorization_source = "flagged"
                txn.haiku_suggestion = "Haiku API not available"
                self._stats['flagged'] += 1

        # Print summary
        self._print_summary()

        return transactions

    def _categorize_with_haiku(self, txn: Transaction) -> None:
        """
        Categorize a single transaction using Haiku API.

        Args:
            txn: Transaction to categorize (modified in place)
        """
        # Determine if debit or credit
        is_debit = txn.debit is not None and txn.debit > 0
        amount = txn.debit if is_debit else txn.credit

        result = self._haiku_client.categorize(
            description=txn.description,
            amount=amount,
            is_debit=is_debit
        )

        if result is None:
            # Haiku failed
            txn.category = "Review Required"
            txn.subcategory = "Manual Review Needed"
            txn.categorization_confidence = 0.0
            txn.categorization_source = "flagged"
            txn.haiku_suggestion = "Haiku API call failed"
            self._stats['flagged'] += 1
            self._stats['haiku_failed'] += 1
            return

        category, subcategory, confidence = result

        if confidence >= self.confidence_threshold:
            # Accept Haiku's categorization
            txn.category = category
            txn.subcategory = subcategory
            txn.categorization_confidence = confidence
            txn.categorization_source = "haiku"
            self._stats['haiku_matched'] += 1
        else:
            # Flag for review but store Haiku's suggestion
            txn.category = "Review Required"
            txn.subcategory = "Manual Review Needed"
            txn.categorization_confidence = confidence
            txn.categorization_source = "flagged"
            txn.haiku_suggestion = f"{category} > {subcategory} (conf: {confidence:.2f})"
            self._stats['flagged'] += 1

    def _print_summary(self) -> None:
        """Print categorization summary."""
        total = self._stats['total']
        if total == 0:
            return

        rules_pct = (self._stats['rules_matched'] / total) * 100
        haiku_pct = (self._stats['haiku_matched'] / total) * 100
        flagged_pct = (self._stats['flagged'] / total) * 100

        print("\n--- Categorization Summary ---")
        print(f"  Total transactions: {total}")
        print(f"  Rules matched: {self._stats['rules_matched']} ({rules_pct:.1f}%)")
        print(f"  Haiku matched: {self._stats['haiku_matched']} ({haiku_pct:.1f}%)")
        print(f"  Flagged for review: {self._stats['flagged']} ({flagged_pct:.1f}%)")
        if self._stats['haiku_failed'] > 0:
            print(f"  Haiku failures: {self._stats['haiku_failed']}")
        print()

    def get_statistics(self) -> dict:
        """
        Get categorization statistics.

        Returns:
            Dictionary with categorization stats
        """
        return self._stats.copy()

    def categorize_single(self, description: str, is_debit: bool = True) -> Tuple[str, str, float, str]:
        """
        Categorize a single description (for testing/debugging).

        Args:
            description: Transaction description
            is_debit: Whether this is a debit transaction

        Returns:
            Tuple of (category, subcategory, confidence, source)
        """
        # Try rules first
        result = rule_based_categorize(description)
        if result:
            return (*result, "rules")

        # Try Haiku
        if self._haiku_client and self._haiku_client.is_available():
            result = self._haiku_client.categorize(
                description=description,
                is_debit=is_debit
            )
            if result:
                category, subcategory, confidence = result
                if confidence >= self.confidence_threshold:
                    return (category, subcategory, confidence, "haiku")
                else:
                    return ("Review Required", "Manual Review Needed",
                            confidence, "flagged")

        return ("Review Required", "Manual Review Needed", 0.0, "flagged")


def test_categorizer():
    """Test the transaction categorizer."""
    import os

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')

    categorizer = TransactionCategorizer(
        api_key=api_key,
        confidence_threshold=0.8
    )

    test_descriptions = [
        ("SAL FOR OCT 2024", True),
        ("SWIGGY ORDER 12345", True),
        ("AMAZON PAY INDIA", True),
        ("ACME CORP PAYMENT", False),
        ("RANDOM XYZ TRANSACTION", True),
    ]

    print("\n--- Single Transaction Test ---\n")
    for desc, is_debit in test_descriptions:
        cat, subcat, conf, source = categorizer.categorize_single(desc, is_debit)
        print(f"'{desc}' -> {cat} > {subcat} (conf: {conf:.2f}, source: {source})")
    print()


if __name__ == "__main__":
    test_categorizer()
