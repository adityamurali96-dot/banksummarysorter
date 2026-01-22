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
        transactions: List[Dict]
    ) -> List[Optional[Tuple[str, str, float]]]:
        """
        Categorize multiple transactions.

        Args:
            transactions: List of dicts with 'description', 'amount', 'is_debit'

        Returns:
            List of categorization results (same order as input)
        """
        results = []

        for i, txn in enumerate(transactions):
            if (i + 1) % 10 == 0:
                print(f"  Categorizing with Haiku: {i + 1}/{len(transactions)}")

            result = self.categorize(
                description=txn.get('description', ''),
                amount=txn.get('amount'),
                is_debit=txn.get('is_debit', True)
            )
            results.append(result)

        return results

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
