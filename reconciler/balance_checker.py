"""
Balance Reconciliation Module.

Validates parsed transactions by:
1. Sorting transactions by date
2. Calculating running balance
3. Comparing calculated vs displayed balance
4. Flagging discrepancies to detect missing entries
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple
from parsers.base_parser import Transaction


@dataclass
class ReconciliationResult:
    """Result of balance reconciliation for a transaction."""
    transaction: Transaction
    calculated_balance: Optional[float]
    balance_difference: Optional[float]
    is_mismatch: bool
    mismatch_reason: str


class BalanceReconciler:
    """
    Reconciles bank statement transactions by verifying balances.

    This helps detect:
    - Missing transactions
    - Duplicate transactions
    - Incorrect amounts
    """

    def __init__(self, tolerance: float = 0.01):
        """
        Initialize the reconciler.

        Args:
            tolerance: Allowed difference between calculated and displayed balance
                       (default 0.01 to handle rounding)
        """
        self.tolerance = tolerance

    def reconcile(
        self,
        transactions: List[Transaction],
        opening_balance: Optional[float] = None
    ) -> Tuple[List[ReconciliationResult], dict]:
        """
        Reconcile transactions and verify balances.

        Args:
            transactions: List of parsed transactions
            opening_balance: Starting balance (if known). If None, will be inferred.

        Returns:
            Tuple of (reconciliation results, summary stats)
        """
        if not transactions:
            return [], {"error": "No transactions to reconcile"}

        # Sort transactions by date
        sorted_txns = sorted(transactions, key=lambda t: t.date or datetime.min)

        # Infer opening balance if not provided
        if opening_balance is None:
            opening_balance = self._infer_opening_balance(sorted_txns)

        results: List[ReconciliationResult] = []
        running_balance = opening_balance
        mismatches = 0
        total_transactions = len(sorted_txns)

        for txn in sorted_txns:
            # Calculate new balance based on debit/credit
            if txn.debit:
                running_balance -= txn.debit
            if txn.credit:
                running_balance += txn.credit

            # Compare with displayed balance
            is_mismatch = False
            mismatch_reason = ""
            balance_diff = None

            if txn.balance is not None:
                balance_diff = round(running_balance - txn.balance, 2)

                if abs(balance_diff) > self.tolerance:
                    is_mismatch = True
                    mismatches += 1

                    if balance_diff > 0:
                        mismatch_reason = f"Calculated {balance_diff:.2f} MORE than displayed (possible missing debit)"
                    else:
                        mismatch_reason = f"Calculated {abs(balance_diff):.2f} LESS than displayed (possible missing credit)"

                    # Reset running balance to displayed to continue checking
                    running_balance = txn.balance

            results.append(ReconciliationResult(
                transaction=txn,
                calculated_balance=round(running_balance, 2),
                balance_difference=balance_diff,
                is_mismatch=is_mismatch,
                mismatch_reason=mismatch_reason
            ))

        # Generate summary
        summary = {
            "total_transactions": total_transactions,
            "opening_balance": opening_balance,
            "closing_balance": running_balance,
            "mismatches_found": mismatches,
            "reconciliation_status": "PASS" if mismatches == 0 else "FAIL - Review Required",
            "total_debits": sum(t.debit or 0 for t in sorted_txns),
            "total_credits": sum(t.credit or 0 for t in sorted_txns),
        }

        return results, summary

    def _infer_opening_balance(self, sorted_txns: List[Transaction]) -> float:
        """
        Infer the opening balance from the first transaction.

        Logic: opening_balance = first_balance + first_debit - first_credit
        """
        first_txn = sorted_txns[0]

        if first_txn.balance is None:
            # Can't infer without balance, assume 0
            return 0.0

        opening = first_txn.balance
        if first_txn.debit:
            opening += first_txn.debit
        if first_txn.credit:
            opening -= first_txn.credit

        return round(opening, 2)

    def get_sorted_transactions(self, transactions: List[Transaction]) -> List[Transaction]:
        """
        Return transactions sorted by date.

        Args:
            transactions: List of transactions

        Returns:
            Sorted list of transactions
        """
        return sorted(transactions, key=lambda t: t.date or datetime.min)
