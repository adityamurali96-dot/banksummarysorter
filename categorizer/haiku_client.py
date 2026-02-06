"""
Claude Haiku API client for transaction categorization.
"""
import json
import re
from typing import Dict, List, Optional, Tuple

from config import HAIKU_MAX_TOKENS, HAIKU_MODEL, get_category_list_for_prompt


class HaikuCategorizer:
    """
    Uses Claude Haiku API to categorize bank transactions.
    """

    def __init__(self, api_key: str):
        """
        Initialize the Haiku categorizer.

        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Anthropic client."""
        if not self.api_key:
            print("Warning: No API key provided for Haiku categorizer")
            return

        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        except ImportError:
            print("Warning: anthropic package not installed. "
                  "Run: pip install anthropic")
        except Exception as e:
            print(f"Warning: Failed to initialize Anthropic client: {e}")

    def categorize(
        self,
        description: str,
        amount: Optional[float] = None,
        is_debit: bool = True
    ) -> Optional[Tuple[str, str, float]]:
        """
        Categorize a transaction using Claude Haiku.

        Args:
            description: Transaction description
            amount: Transaction amount (optional, for context)
            is_debit: Whether this is a debit (expense) or credit (income)

        Returns:
            Tuple of (category, subcategory, confidence) or None on failure
        """
        if not self._client:
            return None

        if not description:
            return None

        prompt = self._build_prompt(description, amount, is_debit)

        try:
            response = self._client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=HAIKU_MAX_TOKENS,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract the text response
            response_text = response.content[0].text.strip()

            # Parse the JSON response
            return self._parse_response(response_text)

        except Exception as e:
            print(f"Haiku API error for '{description[:50]}...': {e}")
            return None

    def _build_prompt(
        self,
        description: str,
        amount: Optional[float],
        is_debit: bool
    ) -> str:
        """
        Build the prompt for Haiku.

        Args:
            description: Transaction description
            amount: Transaction amount
            is_debit: Whether this is a debit

        Returns:
            Prompt string
        """
        category_list = get_category_list_for_prompt()

        txn_type = "expense/debit" if is_debit else "income/credit"
        amount_str = f" (Amount: ₹{abs(amount):,.2f})" if amount else ""

        prompt = f"""Categorize this Indian bank transaction into one of the given categories.

Transaction description: {description}{amount_str}
Transaction type: {txn_type}

Available categories:
{category_list}

Analyze the transaction and respond with ONLY a JSON object in this exact format:
{{"category": "CategoryName", "subcategory": "SubcategoryName", "confidence": 0.85}}

Rules:
- confidence should be between 0.0 and 1.0
- Use lower confidence (0.5-0.7) if the description is ambiguous
- Use higher confidence (0.8-0.95) if you're reasonably certain
- If you cannot determine the category, use "Other" > "Uncategorized" with low confidence
- Match the category and subcategory names EXACTLY as listed above

Respond with ONLY the JSON object, no other text."""

        return prompt

    def _parse_response(
        self,
        response_text: str
    ) -> Optional[Tuple[str, str, float]]:
        """
        Parse the JSON response from Haiku.

        Args:
            response_text: Raw response text

        Returns:
            Tuple of (category, subcategory, confidence) or None
        """
        try:
            # Try to extract JSON from response
            # Sometimes the model might add extra text
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_text

            data = json.loads(json_str)

            category = data.get('category', 'Other')
            subcategory = data.get('subcategory', 'Uncategorized')
            confidence = float(data.get('confidence', 0.5))

            # Clamp confidence to valid range
            confidence = max(0.0, min(1.0, confidence))

            return (category, subcategory, confidence)

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Failed to parse Haiku response: {e}")
            print(f"Response was: {response_text[:200]}")
            return None

    def categorize_batch(
        self,
        transactions: List[Dict],
        chunk_size: int = 10,
    ) -> List[Optional[Tuple[str, str, float]]]:
        """
        Categorize multiple transactions, sending several per API call
        to reduce HTTP round-trips.

        Args:
            transactions: List of dicts with 'description', 'amount', 'is_debit'
            chunk_size: Number of transactions per API call (default 10)

        Returns:
            List of categorization results (same order as input)
        """
        if not self._client:
            return [None] * len(transactions)

        results: List[Optional[Tuple[str, str, float]]] = []

        for start in range(0, len(transactions), chunk_size):
            chunk = transactions[start : start + chunk_size]

            if (start + len(chunk)) % 20 == 0 or start + len(chunk) == len(transactions):
                print(f"  Categorizing with Haiku: {start + len(chunk)}/{len(transactions)}")

            chunk_results = self._categorize_chunk(chunk)
            results.extend(chunk_results)

        return results

    def _categorize_chunk(
        self,
        transactions: List[Dict],
    ) -> List[Optional[Tuple[str, str, float]]]:
        """
        Send a chunk of transactions in a single API call.

        Falls back to one-at-a-time if the multi-transaction prompt fails.
        """
        if len(transactions) == 1:
            txn = transactions[0]
            return [self.categorize(
                description=txn.get('description', ''),
                amount=txn.get('amount'),
                is_debit=txn.get('is_debit', True),
            )]

        category_list = get_category_list_for_prompt()

        # Build a numbered list of transactions
        lines = []
        for i, txn in enumerate(transactions, 1):
            desc = txn.get('description', '')
            amount = txn.get('amount')
            is_debit = txn.get('is_debit', True)
            txn_type = "DR" if is_debit else "CR"
            amount_str = f" ₹{abs(amount):,.2f}" if amount else ""
            lines.append(f"{i}. [{txn_type}]{amount_str} {desc}")

        txn_block = "\n".join(lines)

        prompt = f"""Categorize each Indian bank transaction below into one of the given categories.

Transactions:
{txn_block}

Available categories:
{category_list}

Respond with ONLY a JSON array of objects, one per transaction in the same order:
[{{"category": "Cat", "subcategory": "Sub", "confidence": 0.85}}, ...]

Rules:
- confidence between 0.0 and 1.0
- Use lower confidence (0.5-0.7) for ambiguous descriptions
- If unknown, use "Other" > "Uncategorized" with low confidence
- Match category/subcategory names EXACTLY as listed"""

        try:
            response = self._client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=HAIKU_MAX_TOKENS * len(transactions),
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Try to parse as JSON array
            array_match = re.search(r'\[.*\]', text, re.DOTALL)
            if array_match:
                items = json.loads(array_match.group(0))
                if isinstance(items, list) and len(items) == len(transactions):
                    results = []
                    for item in items:
                        cat = item.get('category', 'Other')
                        sub = item.get('subcategory', 'Uncategorized')
                        conf = max(0.0, min(1.0, float(item.get('confidence', 0.5))))
                        results.append((cat, sub, conf))
                    return results

        except Exception as e:
            print(f"Batch Haiku call failed, falling back to individual calls: {e}")

        # Fallback: categorize one at a time
        return [
            self.categorize(
                description=txn.get('description', ''),
                amount=txn.get('amount'),
                is_debit=txn.get('is_debit', True),
            )
            for txn in transactions
        ]

    def is_available(self) -> bool:
        """
        Check if the Haiku client is available.

        Returns:
            True if the client is initialized and ready
        """
        return self._client is not None


def test_haiku_client():
    """Test the Haiku client with sample descriptions."""
    import os

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print("No ANTHROPIC_API_KEY set. Skipping Haiku test.")
        return

    client = HaikuCategorizer(api_key)

    if not client.is_available():
        print("Haiku client not available.")
        return

    test_cases = [
        {"description": "ACME CORP PRIVATE LIMITED", "is_debit": False},
        {"description": "UPI-SHARMA MEDICAL STORE", "is_debit": True},
        {"description": "NEFT-JOHN DOE-REFERENCE 123", "is_debit": True},
    ]

    print("\n--- Haiku Categorization Test ---\n")
    for txn in test_cases:
        result = client.categorize(
            description=txn['description'],
            is_debit=txn['is_debit']
        )
        if result:
            cat, subcat, conf = result
            print(f"'{txn['description']}' -> {cat} > {subcat} (conf: {conf:.2f})")
        else:
            print(f"'{txn['description']}' -> FAILED")
    print()


if __name__ == "__main__":
    test_haiku_client()
