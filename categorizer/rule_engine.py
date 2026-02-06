"""
Intelligent Rule Engine for Transaction Categorization.

This module provides a flexible, configurable rule matching system that:
- Supports keyword groups and fuzzy matching
- Handles user-defined custom rules from YAML
- Uses semantic understanding of transaction types
- Provides confidence-weighted matching
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import yaml

from config import RULE_BASED_CONFIDENCE


@dataclass
class MatchResult:
    """Result of a rule match attempt."""
    matched: bool
    category: str = ""
    subcategory: str = ""
    confidence: float = 0.0
    rule_name: str = ""
    match_reason: str = ""
    flag_for_review: bool = False
    suggested_category: str = ""
    suggested_subcategory: str = ""


class KeywordMatcher:
    """
    Intelligent keyword matching with various strategies.

    Supports:
    - Exact word matching
    - Partial matching
    - Word boundary detection
    - Negative keywords (exclusions)
    - Fuzzy matching via normalized keywords
    """

    # Common word variations/abbreviations to normalize
    NORMALIZATIONS: Dict[str, List[str]] = {
        "amazon": ["amzn", "amazon.com", "amazon.in", "amazonpay"],
        "flipkart": ["flpkrt", "flipkart.com"],
        "swiggy": ["swigy", "swiggy.com"],
        "zomato": ["zomto", "zomato.com"],
        "uber": ["uber.com", "uber india"],
        "ola": ["ola cabs", "olacabs", "ola money"],
        "netflix": ["netflix.com", "nflx"],
        "google": ["googl", "google.com", "google pay", "gpay"],
        "paytm": ["paytm.com", "paytm mall"],
        "salary": ["sal", "payroll", "wages", "compensation"],
        "refund": ["rfnd", "reversal", "cashback", "cash back"],
        "transfer": ["tfr", "xfer", "trf"],
        "withdrawal": ["wdl", "wd", "w/d", "wtdrwl"],
        "deposit": ["dep", "dpt"],
        "interest": ["int", "intrst"],
        "insurance": ["insur", "ins"],
    }

    def __init__(self):
        # Build reverse mapping for quick lookup
        self._reverse_normalizations: Dict[str, str] = {}
        for canonical, variations in self.NORMALIZATIONS.items():
            for var in variations:
                self._reverse_normalizations[var.lower()] = canonical

    def normalize_text(self, text: str) -> str:
        """
        Normalize transaction description for better matching.

        - Lowercase
        - Remove extra whitespace
        - Expand common abbreviations
        - Remove special characters that don't aid matching
        """
        if not text:
            return ""

        text = text.lower().strip()

        # Remove special characters but keep alphanumeric and spaces
        text = re.sub(r'[^\w\s]', ' ', text)

        # Normalize whitespace
        text = ' '.join(text.split())

        # Expand known abbreviations
        words = text.split()
        normalized_words = []
        for word in words:
            if word in self._reverse_normalizations:
                normalized_words.append(self._reverse_normalizations[word])
            else:
                normalized_words.append(word)

        return ' '.join(normalized_words)

    def match_keyword(
        self,
        text: str,
        keyword: str,
        use_word_boundary: bool = True
    ) -> bool:
        """
        Check if a keyword matches in the text.

        Args:
            text: The text to search in (should be normalized)
            keyword: The keyword to find
            use_word_boundary: For short keywords, use word boundaries

        Returns:
            True if keyword is found
        """
        keyword = keyword.lower().strip()

        # For very short keywords (1-2 chars), always use word boundary
        if len(keyword) <= 2:
            pattern = r'(?:^|\s)' + re.escape(keyword) + r'(?:\s|$)'
            return bool(re.search(pattern, text))

        # For short keywords (3-4 chars), use word boundary by default
        if len(keyword) <= 4 and use_word_boundary:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            return bool(re.search(pattern, text))

        # For longer keywords, simple substring is fine
        return keyword in text

    def match_any_keyword(
        self,
        text: str,
        keywords: List[str],
        negative_keywords: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Check if any keyword from the list matches.

        Args:
            text: Text to search
            keywords: List of keywords (any must match)
            negative_keywords: Keywords that must NOT be present

        Returns:
            Tuple of (matched, matching_keyword)
        """
        text_normalized = self.normalize_text(text)

        # Check negative keywords first
        if negative_keywords:
            for neg_kw in negative_keywords:
                if self.match_keyword(text_normalized, neg_kw):
                    return False, ""

        # Check positive keywords
        for keyword in keywords:
            # Handle negative keywords inline (prefixed with !)
            if keyword.startswith('!'):
                if self.match_keyword(text_normalized, keyword[1:]):
                    return False, ""
                continue

            if self.match_keyword(text_normalized, keyword):
                return True, keyword

        return False, ""

    def match_all_keywords(
        self,
        text: str,
        keywords: List[str]
    ) -> bool:
        """
        Check if ALL keywords match (AND logic).
        """
        text_normalized = self.normalize_text(text)

        for keyword in keywords:
            if keyword.startswith('!'):
                # Negative keyword - must NOT match
                if self.match_keyword(text_normalized, keyword[1:]):
                    return False
            else:
                # Positive keyword - must match
                if not self.match_keyword(text_normalized, keyword):
                    return False

        return True


class RuleEngine:
    """
    Main rule engine that combines built-in rules with custom user rules.

    Rule processing order:
    1. User priority rules (from custom_rules.yaml)
    2. User custom merchant mappings
    3. Built-in smart rules (semantic patterns)
    4. Amount-based rules
    5. Default fallback rules
    """

    def __init__(self, custom_rules_path: Optional[str] = None):
        """
        Initialize the rule engine.

        Args:
            custom_rules_path: Path to custom_rules.yaml (optional).
                If None, rules are loaded from the Config singleton to
                avoid reading the YAML file a second time.
        """
        self.matcher = KeywordMatcher()
        self.custom_rules: Dict[str, Any] = {}
        self.keyword_groups: Dict[str, List[str]] = {}

        if custom_rules_path is not None:
            self._load_custom_rules_from_file(custom_rules_path)
        else:
            self._load_custom_rules_from_config()

        self._build_smart_rules()

    def _load_custom_rules_from_config(self) -> None:
        """Load custom rules via the Config singleton (avoids duplicate YAML reads)."""
        try:
            from config import get_config
            config = get_config()
            self.custom_rules = config.custom_rules or {}
            self.keyword_groups = self.custom_rules.get('keyword_groups', {})
        except Exception as e:
            print(f"Warning: Could not load custom rules from config: {e}")
            self.custom_rules = {}

    def _load_custom_rules_from_file(self, path) -> None:
        """Load custom rules directly from a YAML file."""
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    self.custom_rules = yaml.safe_load(f) or {}

                self.keyword_groups = self.custom_rules.get('keyword_groups', {})
            else:
                print(f"No custom rules file found at {path}")
        except Exception as e:
            print(f"Warning: Could not load custom rules: {e}")
            self.custom_rules = {}

    def _expand_keyword_group(self, keywords: List[str]) -> List[str]:
        """
        Expand keyword group references in a keyword list.

        If a keyword is @group_name, expand it to all keywords in that group.
        """
        expanded = []
        for kw in keywords:
            if kw.startswith('@') and kw[1:] in self.keyword_groups:
                expanded.extend(self.keyword_groups[kw[1:]])
            else:
                expanded.append(kw)
        return expanded

    def _build_smart_rules(self) -> None:
        """
        Build smart rules that use semantic understanding.

        These rules understand transaction types, not just merchant names.
        """
        # Smart rules are defined as lambda functions that take (description, amount, is_credit)
        # and return Optional[MatchResult]
        self.smart_rules: List[Tuple[str, Callable]] = [
            # Income detection
            ("salary_detection", self._detect_salary),
            ("interest_income", self._detect_interest),
            ("refund_detection", self._detect_refund),

            # Expense patterns
            ("food_delivery", self._detect_food_delivery),
            ("groceries", self._detect_groceries),
            ("online_shopping", self._detect_online_shopping),
            ("cab_taxi", self._detect_cab_taxi),
            ("fuel", self._detect_fuel),
            ("utilities", self._detect_utilities),
            ("subscriptions", self._detect_subscriptions),
            ("investments", self._detect_investments),
            ("insurance", self._detect_insurance),
            ("healthcare", self._detect_healthcare),
            ("education", self._detect_education),

            # Banking patterns
            ("atm_cash", self._detect_atm_cash),
            ("bank_charges", self._detect_bank_charges),
            ("loan_emi", self._detect_loan_emi),

            # Tax patterns
            ("tax_payment", self._detect_tax_payment),

            # Transfer patterns (lower priority)
            ("transfer", self._detect_transfer),
        ]

    def categorize(
        self,
        description: str,
        amount: Optional[float] = None,
        is_credit: bool = False
    ) -> Optional[Tuple[str, str, float]]:
        """
        Categorize a transaction using the rule engine.

        Args:
            description: Transaction description
            amount: Transaction amount (optional, for amount-based rules)
            is_credit: Whether this is a credit transaction

        Returns:
            Tuple of (category, subcategory, confidence) or None
        """
        if not description:
            return None

        # Try matching in order of priority
        result = self._try_match(description, amount, is_credit)

        if result and result.matched:
            return (result.category, result.subcategory, result.confidence)

        return None

    def _try_match(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Try all matching strategies in priority order."""

        # 1. User priority rules
        result = self._match_priority_rules(description)
        if result and result.matched:
            return result

        # 2. User custom merchants
        result = self._match_custom_merchants(description)
        if result and result.matched:
            return result

        # 3. Smart semantic rules
        for rule_name, rule_func in self.smart_rules:
            result = rule_func(description, amount, is_credit)
            if result and result.matched:
                return result

        # 4. Amount-based rules (if amount provided)
        if amount is not None:
            result = self._match_amount_rules(description, amount, is_credit)
            if result and result.matched:
                return result

        return None

    def _match_priority_rules(self, description: str) -> Optional[MatchResult]:
        """Match against user-defined priority rules."""
        priority_rules = self.custom_rules.get('priority_rules') or []

        for rule in priority_rules:
            if not isinstance(rule, dict):
                continue

            rule_type = rule.get('type', 'keyword')
            matched = False

            if rule_type == 'keyword':
                keywords = rule.get('keywords', [])
                keywords = self._expand_keyword_group(keywords)
                matched, _ = self.matcher.match_any_keyword(description, keywords)

            elif rule_type == 'all_keywords':
                keywords = rule.get('keywords', [])
                keywords = self._expand_keyword_group(keywords)
                matched = self.matcher.match_all_keywords(description, keywords)

            elif rule_type == 'regex':
                pattern = rule.get('pattern', '')
                try:
                    matched = bool(re.search(pattern, description, re.IGNORECASE))
                except re.error:
                    continue

            if matched:
                return MatchResult(
                    matched=True,
                    category=rule.get('category', 'Other'),
                    subcategory=rule.get('subcategory', 'Uncategorized'),
                    confidence=rule.get('confidence', RULE_BASED_CONFIDENCE),
                    rule_name=rule.get('name', 'custom_rule'),
                    match_reason="User priority rule"
                )

        return None

    def _match_custom_merchants(self, description: str) -> Optional[MatchResult]:
        """Match against user-defined merchant mappings."""
        custom_merchants = self.custom_rules.get('custom_merchants') or {}

        if not custom_merchants:
            return None

        desc_normalized = self.matcher.normalize_text(description)

        for merchant_pattern, category_info in custom_merchants.items():
            if not isinstance(category_info, list) or len(category_info) < 2:
                continue

            if self.matcher.match_keyword(desc_normalized, merchant_pattern):
                return MatchResult(
                    matched=True,
                    category=category_info[0],
                    subcategory=category_info[1],
                    confidence=RULE_BASED_CONFIDENCE,
                    rule_name=f"merchant:{merchant_pattern}",
                    match_reason="Custom merchant mapping"
                )

        return None

    def _match_amount_rules(
        self,
        description: str,
        amount: float,
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Match against amount-based rules."""
        amount_rules = self.custom_rules.get('amount_rules') or []

        for rule in amount_rules:
            if not isinstance(rule, dict):
                continue

            # Check amount range
            min_amt = rule.get('min_amount', 0)
            max_amt = rule.get('max_amount', float('inf'))

            if not (min_amt <= amount <= max_amt):
                continue

            # Check if round amount required
            if rule.get('round_amount') and amount % 1000 != 0:
                continue

            # Check transaction type
            rule_type = rule.get('type', 'any')
            if rule_type == 'debit' and is_credit:
                continue
            if rule_type == 'credit' and not is_credit:
                continue

            # Check merchant hints if specified
            hint_keywords = rule.get('merchant_hint_keywords', [])
            if hint_keywords:
                matched, _ = self.matcher.match_any_keyword(description, hint_keywords)
                if not matched:
                    continue

            # Check if this should flag for review
            if rule.get('flag_for_review'):
                return MatchResult(
                    matched=True,
                    flag_for_review=True,
                    category="Review Required",
                    subcategory="Manual Review Needed",
                    confidence=0.5,
                    suggested_category=rule.get('suggestion_category', ''),
                    suggested_subcategory=rule.get('suggestion_subcategory', ''),
                    rule_name=rule.get('name', 'amount_rule'),
                    match_reason="Amount-based suggestion"
                )

            return MatchResult(
                matched=True,
                category=rule.get('category', 'Other'),
                subcategory=rule.get('subcategory', 'Uncategorized'),
                confidence=rule.get('confidence', 0.85),
                rule_name=rule.get('name', 'amount_rule'),
                match_reason="Amount-based rule"
            )

        return None

    # =========================================================================
    # Smart Detection Rules
    # =========================================================================

    def _detect_salary(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect salary/payroll transactions."""
        if not is_credit:
            return None

        keywords = [
            "salary", "sal for", "payroll", "monthly salary", "wages",
            "compensation", "pay from employer", "annual salary"
        ]

        # Expand from keyword groups
        keywords.extend(self.keyword_groups.get('salary_indicators', []))

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Income",
                subcategory="Salary",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="salary_detection",
                match_reason=f"Matched salary keyword: {kw}"
            )
        return None

    def _detect_interest(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect interest income."""
        if not is_credit:
            return None

        keywords = [
            "interest credit", "interest paid", "interest recd",
            "int cr", "interest earned", "savings interest",
            "fd interest", "deposit interest"
        ]

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Income",
                subcategory="Interest",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="interest_income",
                match_reason=f"Matched interest keyword: {kw}"
            )
        return None

    def _detect_refund(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect refund transactions."""
        if not is_credit:
            return None

        # Check for tax refunds first (more specific)
        tax_refund_keywords = [
            "gst refund", "igst refund", "cgst refund", "sgst refund",
            "it refund", "income tax refund", "tds refund", "refund cpc"
        ]

        matched, kw = self.matcher.match_any_keyword(description, tax_refund_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Taxes",
                subcategory="Tax Refund",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="tax_refund",
                match_reason=f"Matched tax refund: {kw}"
            )

        # General refunds
        refund_keywords = ["refund", "reversal", "cashback", "cash back"]
        matched, kw = self.matcher.match_any_keyword(description, refund_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Income",
                subcategory="Refund",
                confidence=0.90,  # Slightly lower - might need review
                rule_name="refund_detection",
                match_reason=f"Matched refund keyword: {kw}"
            )
        return None

    def _detect_food_delivery(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect food delivery services."""
        keywords = self.keyword_groups.get('food_delivery', [
            "swiggy", "zomato", "uber eats", "dunzo", "food panda"
        ])

        # Make sure to exclude uber rides (not uber eats)
        desc_lower = description.lower()
        if 'uber' in desc_lower and 'eats' not in desc_lower:
            return None  # Let cab detection handle it

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Food & Dining",
                subcategory="Food Delivery",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="food_delivery",
                match_reason=f"Matched food delivery: {kw}"
            )

        # Also check for restaurants
        restaurant_keywords = [
            "dominos", "pizza hut", "mcdonalds", "burger king", "kfc",
            "subway", "taco bell", "papa johns", "wendys", "starbucks",
            "cafe coffee day", "ccd", "barista", "restaurant"
        ]

        matched, kw = self.matcher.match_any_keyword(description, restaurant_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Food & Dining",
                subcategory="Restaurant",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="restaurant",
                match_reason=f"Matched restaurant: {kw}"
            )

        return None

    def _detect_groceries(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect grocery purchases."""
        keywords = self.keyword_groups.get('groceries', [
            "blinkit", "zepto", "bigbasket", "grofers", "jiomart",
            "amazon fresh", "instamart", "dmart", "reliance fresh",
            "big bazaar", "spencer", "more retail"
        ])

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Shopping",
                subcategory="Groceries",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="groceries",
                match_reason=f"Matched grocery: {kw}"
            )
        return None

    def _detect_online_shopping(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect online shopping."""
        keywords = self.keyword_groups.get('online_shopping', [
            "amazon", "flipkart", "myntra", "ajio", "nykaa",
            "meesho", "snapdeal", "tatacliq"
        ])

        # Exclude Amazon Fresh (grocery) and Amazon Prime (subscription)
        desc_lower = description.lower()
        if 'amazon' in desc_lower:
            if 'fresh' in desc_lower:
                return None  # Let groceries handle it
            if 'prime' in desc_lower and 'video' not in desc_lower:
                # Might be Prime subscription, not shopping
                pass

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Shopping",
                subcategory="Online Shopping",
                confidence=0.90,  # Slightly lower - amazon/flipkart can be many things
                rule_name="online_shopping",
                match_reason=f"Matched online shopping: {kw}"
            )

        # Electronics stores
        electronics_keywords = [
            "croma", "reliance digital", "vijay sales", "samsung store",
            "apple store", "mi store"
        ]
        matched, kw = self.matcher.match_any_keyword(description, electronics_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Shopping",
                subcategory="Electronics",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="electronics",
                match_reason=f"Matched electronics: {kw}"
            )

        return None

    def _detect_cab_taxi(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect cab/taxi services."""
        keywords = self.keyword_groups.get('cab_services', [
            "uber", "ola cabs", "ola money", "rapido", "meru", "lyft"
        ])

        # Exclude uber eats
        desc_lower = description.lower()
        if 'uber' in desc_lower and 'eats' in desc_lower:
            return None

        matched, kw = self.matcher.match_any_keyword(
            description,
            keywords,
            negative_keywords=["eats", "food"]
        )
        if matched:
            return MatchResult(
                matched=True,
                category="Transport",
                subcategory="Cab/Taxi",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="cab_taxi",
                match_reason=f"Matched cab service: {kw}"
            )
        return None

    def _detect_fuel(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect fuel/petrol purchases."""
        keywords = self.keyword_groups.get('fuel', [
            "petrol", "diesel", "fuel", "hp pay", "indian oil",
            "iocl", "bpcl", "hpcl", "shell", "essar"
        ])

        matched, kw = self.matcher.match_any_keyword(description, keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Transport",
                subcategory="Fuel",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="fuel",
                match_reason=f"Matched fuel: {kw}"
            )

        # Also check for travel bookings
        travel_keywords = [
            "irctc", "railway", "train ticket", "indian railways",
            "makemytrip", "mmt", "goibibo", "cleartrip", "yatra",
            "flight", "indigo", "spicejet", "air india", "vistara"
        ]

        matched, kw = self.matcher.match_any_keyword(description, travel_keywords)
        if matched:
            # Determine if train or flight
            if any(t in description.lower() for t in ["irctc", "railway", "train"]):
                subcategory = "Train"
            else:
                subcategory = "Flight"

            return MatchResult(
                matched=True,
                category="Transport",
                subcategory=subcategory,
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="travel",
                match_reason=f"Matched travel: {kw}"
            )

        return None

    def _detect_utilities(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect utility bill payments."""
        utilities_keywords = self.keyword_groups.get('utilities', [
            "electricity", "bescom", "tata power", "adani", "bses",
            "water bill", "gas bill", "lpg", "indane"
        ])

        telecom_keywords = self.keyword_groups.get('telecom', [
            "airtel", "jio", "vodafone", "bsnl", "idea", "mobile recharge"
        ])

        # Check electricity/water/gas
        matched, kw = self.matcher.match_any_keyword(description, utilities_keywords)
        if matched:
            # Determine specific utility type
            desc_lower = description.lower()
            if any(e in desc_lower for e in ["electricity", "bescom", "power", "bses"]):
                subcategory = "Electricity"
            elif any(w in desc_lower for w in ["water"]):
                subcategory = "Water"
            elif any(g in desc_lower for g in ["lpg", "gas", "indane", "bharat gas"]):
                subcategory = "Gas"
            else:
                subcategory = "Other Bills"

            return MatchResult(
                matched=True,
                category="Bills & Utilities",
                subcategory=subcategory,
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="utilities",
                match_reason=f"Matched utility: {kw}"
            )

        # Check telecom
        matched, kw = self.matcher.match_any_keyword(description, telecom_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bills & Utilities",
                subcategory="Mobile/Internet",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="telecom",
                match_reason=f"Matched telecom: {kw}"
            )

        # Check rent
        rent_keywords = [
            "rent paid", "rent payment", "rent transfer", "house rent",
            "flat rent", "monthly rent", "rent to", "rent for"
        ]
        matched, kw = self.matcher.match_any_keyword(description, rent_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bills & Utilities",
                subcategory="Rent",
                confidence=0.90,  # Rent can sometimes be mislabeled
                rule_name="rent",
                match_reason=f"Matched rent: {kw}"
            )

        return None

    def _detect_subscriptions(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect subscription services."""
        streaming_keywords = self.keyword_groups.get('streaming', [
            "netflix", "hotstar", "disney", "amazon prime", "prime video",
            "spotify", "youtube premium", "apple music"
        ])

        matched, kw = self.matcher.match_any_keyword(description, streaming_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Entertainment",
                subcategory="OTT Subscriptions",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="streaming",
                match_reason=f"Matched streaming: {kw}"
            )

        # Generic subscriptions
        sub_keywords = ["subscription", "membership", "annual plan", "monthly plan"]
        matched, kw = self.matcher.match_any_keyword(description, sub_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bills & Utilities",
                subcategory="Subscriptions",
                confidence=0.85,
                rule_name="subscription",
                match_reason=f"Matched subscription: {kw}"
            )

        return None

    def _detect_investments(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect investment transactions."""
        # Mutual funds
        mf_keywords = [
            "mutual fund", "mf purchase", "mf sip", "sip payment",
            "systematic inv", "kuvera", "groww mf", "coin by zerodha",
            "hdfc mf", "icici pru mf", "sbi mf", "axis mf", "nippon"
        ]

        matched, kw = self.matcher.match_any_keyword(description, mf_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Investments",
                subcategory="Mutual Funds",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="mutual_funds",
                match_reason=f"Matched mutual fund: {kw}"
            )

        # Stocks/Brokers
        broker_keywords = self.keyword_groups.get('investment_platforms', [
            "zerodha", "groww", "upstox", "angel one", "icici direct",
            "hdfc sec", "kotak sec", "5paisa", "paytm money"
        ])

        matched, kw = self.matcher.match_any_keyword(description, broker_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Investments",
                subcategory="Stocks",
                confidence=0.90,  # Could also be MF through broker
                rule_name="stocks",
                match_reason=f"Matched broker: {kw}"
            )

        # PPF/NPS
        ppf_nps_keywords = ["ppf", "public provident", "nps", "national pension", "pfrda"]
        matched, kw = self.matcher.match_any_keyword(description, ppf_nps_keywords)
        if matched:
            subcategory = "PPF" if "ppf" in description.lower() else "NPS"
            return MatchResult(
                matched=True,
                category="Investments",
                subcategory=subcategory,
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="ppf_nps",
                match_reason=f"Matched: {kw}"
            )

        # FD
        fd_keywords = ["fd opening", "fd booking", "fixed deposit", "term deposit"]
        matched, kw = self.matcher.match_any_keyword(description, fd_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Investments",
                subcategory="Fixed Deposit",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="fd",
                match_reason=f"Matched FD: {kw}"
            )

        return None

    def _detect_insurance(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect insurance premium payments."""
        insurance_keywords = self.keyword_groups.get('insurance', [
            "lic", "life insurance", "hdfc life", "icici prudential",
            "sbi life", "max life", "star health", "care health"
        ])

        matched, kw = self.matcher.match_any_keyword(description, insurance_keywords)
        if matched:
            # Determine insurance type
            desc_lower = description.lower()
            if any(h in desc_lower for h in ["health", "mediclaim", "bupa"]):
                subcategory = "Health Insurance"
            elif any(v in desc_lower for v in ["vehicle", "motor", "car", "bike", "acko", "digit"]):
                subcategory = "Vehicle Insurance"
            else:
                subcategory = "Life Insurance"

            return MatchResult(
                matched=True,
                category="Insurance",
                subcategory=subcategory,
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="insurance",
                match_reason=f"Matched insurance: {kw}"
            )

        return None

    def _detect_healthcare(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect healthcare expenses."""
        hospital_keywords = [
            "hospital", "apollo", "fortis", "max healthcare", "manipal",
            "narayana", "medanta", "aiims", "aster"
        ]

        pharmacy_keywords = [
            "pharmacy", "pharmeasy", "netmeds", "1mg", "medplus",
            "apollo pharmacy", "medlife"
        ]

        doctor_keywords = [
            "dr ", "dr.", "doctor", "consultation", "diagnostic",
            "lab", "thyrocare", "lal path", "metropolis", "practo"
        ]

        matched, kw = self.matcher.match_any_keyword(description, hospital_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Healthcare",
                subcategory="Hospital",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="hospital",
                match_reason=f"Matched hospital: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, pharmacy_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Healthcare",
                subcategory="Pharmacy",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="pharmacy",
                match_reason=f"Matched pharmacy: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, doctor_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Healthcare",
                subcategory="Doctor/Consultation",
                confidence=0.90,  # "dr" might match other things
                rule_name="doctor",
                match_reason=f"Matched doctor: {kw}"
            )

        return None

    def _detect_education(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect education expenses."""
        school_keywords = [
            "school", "college", "university", "institute", "academy",
            "fees", "tuition", "education"
        ]

        online_course_keywords = [
            "udemy", "coursera", "unacademy", "byju", "whitehat",
            "upgrad", "simplilearn", "great learning", "edureka", "skillshare"
        ]

        matched, kw = self.matcher.match_any_keyword(description, online_course_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Education",
                subcategory="Online Courses",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="online_courses",
                match_reason=f"Matched online course: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, school_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Education",
                subcategory="School/College Fees",
                confidence=0.85,  # Generic keywords might match other things
                rule_name="education",
                match_reason=f"Matched education: {kw}"
            )

        return None

    def _detect_atm_cash(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect ATM and cash transactions."""
        atm_keywords = [
            "atm wdl", "atm withdrawal", "atm w/d", "atm wd",
            "cash withdrawal", "nfs wdl", "nfs wd", "atm cash",
            "cash at atm"
        ]

        deposit_keywords = ["cash deposit", "cdm deposit", "cash dep"]

        matched, kw = self.matcher.match_any_keyword(description, atm_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Cash",
                subcategory="ATM Withdrawal",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="atm",
                match_reason=f"Matched ATM: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, deposit_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Cash",
                subcategory="Cash Deposit",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="cash_deposit",
                match_reason=f"Matched cash deposit: {kw}"
            )

        return None

    def _detect_bank_charges(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect bank charges and fees."""
        charge_keywords = [
            "service charge", "maintenance charge", "account charge",
            "sms charge", "annual fee", "yearly fee", "debit card fee"
        ]

        penalty_keywords = [
            "insufficient charge", "bounce charge", "return charge",
            "penalty charge", "ecs return", "nach return", "cheque bounce",
            "min bal", "minimum balance"
        ]

        matched, kw = self.matcher.match_any_keyword(description, charge_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bank Charges",
                subcategory="Service Charges",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="service_charge",
                match_reason=f"Matched charge: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, penalty_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bank Charges",
                subcategory="Penalties",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="penalty",
                match_reason=f"Matched penalty: {kw}"
            )

        return None

    def _detect_loan_emi(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect loan EMI payments."""
        emi_keywords = [
            "loan emi", "emi payment", "home loan", "car loan",
            "personal loan", "education loan", "interest debit",
            "interest paid", "interest charged", "int dr"
        ]

        matched, kw = self.matcher.match_any_keyword(description, emi_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Bank Charges",
                subcategory="Interest Paid",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="loan_emi",
                match_reason=f"Matched loan/EMI: {kw}"
            )

        return None

    def _detect_tax_payment(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect tax payments."""
        gst_keywords = [
            "gst payment", "gst challan", "gst pmt", "gst deposit",
            "cgst", "sgst", "igst", "gst portal"
        ]

        it_keywords = [
            "advance tax", "self assessment tax", "income tax pmt",
            "income tax payment", "it payment", "challan 280", "challan 281"
        ]

        tds_keywords = ["tds payment", "tds deposit", "tds challan"]
        pt_keywords = ["professional tax", "pt payment", "p tax"]

        matched, kw = self.matcher.match_any_keyword(description, gst_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Taxes",
                subcategory="GST Payment",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="gst",
                match_reason=f"Matched GST: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, it_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Taxes",
                subcategory="Income Tax",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="income_tax",
                match_reason=f"Matched income tax: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, tds_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Taxes",
                subcategory="TDS",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="tds",
                match_reason=f"Matched TDS: {kw}"
            )

        matched, kw = self.matcher.match_any_keyword(description, pt_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Taxes",
                subcategory="Professional Tax",
                confidence=RULE_BASED_CONFIDENCE,
                rule_name="professional_tax",
                match_reason=f"Matched PT: {kw}"
            )

        return None

    def _detect_transfer(
        self,
        description: str,
        amount: Optional[float],
        is_credit: bool
    ) -> Optional[MatchResult]:
        """Detect bank transfers (lowest priority)."""
        self_transfer_keywords = [
            "self transfer", "transfer to self", "own account",
            "between accounts"
        ]

        matched, kw = self.matcher.match_any_keyword(description, self_transfer_keywords)
        if matched:
            return MatchResult(
                matched=True,
                category="Transfer",
                subcategory="Self Transfer",
                confidence=0.90,
                rule_name="self_transfer",
                match_reason=f"Matched self transfer: {kw}"
            )

        # Generic transfers - low priority, might need review
        transfer_keywords = self.keyword_groups.get('transfer_indicators', [
            "neft", "rtgs", "imps", "upi", "fund transfer", "bank transfer"
        ])

        # Only match these if there's no other categorization hint
        matched, kw = self.matcher.match_any_keyword(description, transfer_keywords)
        if matched:
            # Check if there are any other hints that might indicate category
            desc_lower = description.lower()
            for hint_category, hints in [
                ("salary", ["salary", "payroll", "wages"]),
                ("rent", ["rent"]),
                ("emi", ["emi", "loan"]),
                ("vendor", ["vendor", "supplier"]),
            ]:
                if any(h in desc_lower for h in hints):
                    return None  # Let more specific rules handle it

            return MatchResult(
                matched=True,
                category="Transfer",
                subcategory="Bank Transfer",
                confidence=0.75,  # Low confidence - transfers often need review
                rule_name="transfer",
                match_reason=f"Matched transfer: {kw}"
            )

        return None


# Global rule engine instance
_rule_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    """Get the global rule engine instance."""
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine


def smart_categorize(
    description: str,
    amount: Optional[float] = None,
    is_credit: bool = False
) -> Optional[Tuple[str, str, float]]:
    """
    Convenience function for smart categorization.

    Args:
        description: Transaction description
        amount: Transaction amount (optional)
        is_credit: Whether this is a credit transaction

    Returns:
        Tuple of (category, subcategory, confidence) or None
    """
    engine = get_rule_engine()
    return engine.categorize(description, amount, is_credit)
