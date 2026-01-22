"""
Rule-based categorization for bank transactions.

Contains regex patterns for matching transaction descriptions to categories.
"""
import re
from typing import Dict, List, Optional, Tuple

from config import RULE_BASED_CONFIDENCE

# Type alias for category rules
# Each rule is: (pattern, category, subcategory)
CategoryRule = Tuple[str, str, str]

# =============================================================================
# Category Rules
# Ordered by specificity - more specific patterns should come first
# =============================================================================

CATEGORY_RULES: List[CategoryRule] = [
    # =========================================================================
    # INCOME PATTERNS
    # =========================================================================

    # Salary
    (r'salary|sal\s+for|payroll|monthly\s*salary', 'Income', 'Salary'),

    # Interest
    (r'interest\s*(credit|paid|recd|on\s+dep)|int\s+cr|int\.\s*cr|'
     r'interest\s+earned|savings\s+interest', 'Income', 'Interest'),

    # Dividend
    (r'dividend|div\s+on|div\s+paid', 'Income', 'Dividend'),

    # Tax Refunds
    (r'gst\s*refund|igst\s*refund|cgst\s*refund|sgst\s*refund', 'Taxes', 'Tax Refund'),
    (r'it\s*refund|income\s*tax\s*refund|refund.*cpc|cpc.*refund|'
     r'refund.*income\s*tax', 'Taxes', 'Tax Refund'),

    # Other Refunds
    (r'refund|reversal|cashback', 'Income', 'Refund'),

    # Rental Income
    (r'rent\s*(received|recd|credit)|rental\s+income', 'Income', 'Rental Income'),

    # =========================================================================
    # FOOD & DINING PATTERNS
    # =========================================================================

    # Food Delivery
    (r'swiggy|zomato|uber\s*eats|dunzo\s*food|food\s*panda', 'Food & Dining', 'Food Delivery'),

    # Restaurants & Fast Food
    (r'dominos|pizza\s*hut|mcdonalds|burger\s*king|kfc|subway|'
     r'taco\s*bell|papa\s*johns|wendys', 'Food & Dining', 'Restaurant'),

    # Cafe/Coffee
    (r'starbucks|cafe\s*coffee\s*day|ccd|barista|costa\s*coffee|'
     r'blue\s*tokai|third\s*wave', 'Food & Dining', 'Cafe/Coffee'),

    # =========================================================================
    # SHOPPING PATTERNS
    # =========================================================================

    # Groceries - Online
    (r'blinkit|zepto|bigbasket|grofers|jiomart|amazon\s*fresh|'
     r'instamart|swiggy\s*instamart', 'Shopping', 'Groceries'),

    # Groceries - Retail
    (r'dmart|reliance\s*(retail|fresh|smart)|big\s*bazaar|more\s*retail|'
     r'spencer|star\s*bazaar|spar|nature.*basket', 'Shopping', 'Groceries'),

    # Online Shopping
    (r'amazon|flipkart|myntra|ajio|nykaa|meesho|snapdeal|'
     r'tatacliq|shopclues|paytm\s*mall', 'Shopping', 'Online Shopping'),

    # Electronics
    (r'croma|reliance\s*digital|vijay\s*sales|samsung\s*store|'
     r'apple\s*store|mi\s*store', 'Shopping', 'Electronics'),

    # Clothing
    (r'zara|h&m|uniqlo|pantaloons|lifestyle|westside|max\s*fashion|'
     r'benetton|levis|pepe\s*jeans', 'Shopping', 'Clothing'),

    # =========================================================================
    # TRANSPORT PATTERNS
    # =========================================================================

    # Cab/Taxi (careful to exclude uber eats)
    (r'uber(?!\s*eats)|ola\s*cabs|ola\s*money|rapido|meru\s*cabs|'
     r'mega\s*cabs|tab\s*cab', 'Transport', 'Cab/Taxi'),

    # Fuel
    (r'petrol|diesel|fuel|hp\s*pay|indian\s*oil|iocl|bpcl|hpcl|'
     r'shell|essar|reliance\s*petrol', 'Transport', 'Fuel'),

    # Train
    (r'irctc|railway|train\s*ticket|indian\s*railways', 'Transport', 'Train'),

    # Flight
    (r'makemytrip|mmt|goibibo|cleartrip|yatra|flight|indigo|spicejet|'
     r'air\s*india|vistara|akasa|jet\s*airways', 'Transport', 'Flight'),

    # Public Transport
    (r'metro\s*card|dmrc|bmrc|cmrl|hmrl|nmrc|metro\s*recharge|'
     r'bus\s*pass|bmtc|best\s*bus', 'Transport', 'Public Transport'),

    # =========================================================================
    # BILLS & UTILITIES PATTERNS
    # =========================================================================

    # Electricity
    (r'electricity|bescom|tata\s*power|adani\s*(elec|power|gas)|bses|msedcl|'
     r'dgvcl|pgvcl|torrent\s*power|cesc', 'Bills & Utilities', 'Electricity'),

    # Mobile/Internet - Telecom
    (r'airtel|jio\s|reliance\s*jio|vodafone|vi\s|bsnl|idea\s|'
     r'mobile\s*recharge|prepaid\s*recharge', 'Bills & Utilities', 'Mobile/Internet'),

    # Mobile/Internet - Broadband
    (r'act\s*fibernet|hathway|tikona|broadband|fiber|wifi|'
     r'spectra|excitel|you\s*broadband', 'Bills & Utilities', 'Mobile/Internet'),

    # Subscriptions & OTT
    (r'netflix|hotstar|disney|prime\s*video|amazon\s*prime|spotify|'
     r'youtube\s*premium|apple\s*music|gaana|jio\s*saavn|'
     r'zee5|sonyliv|voot|alt\s*balaji', 'Entertainment', 'OTT Subscriptions'),

    # Other Subscriptions
    (r'subscription|membership|annual\s*plan|monthly\s*plan', 'Bills & Utilities', 'Subscriptions'),

    # Rent
    (r'rent\s*(paid|payment|transfer|for)|house\s*rent|flat\s*rent|'
     r'monthly\s*rent|rent\s+to', 'Bills & Utilities', 'Rent'),

    # Gas/LPG
    (r'lpg|indane|hp\s*gas|bharat\s*gas|gas\s*cylinder|piped\s*gas|'
     r'mahanagar\s*gas|igl|adani\s*gas', 'Bills & Utilities', 'Gas'),

    # Water
    (r'water\s*(bill|charge)|bwssb|water\s*board|water\s*supply', 'Bills & Utilities', 'Water'),

    # =========================================================================
    # INVESTMENT PATTERNS
    # =========================================================================

    # Mutual Funds
    (r'mutual\s*fund|mf\s*(purchase|sip|inv)|sip\s*(payment|pur|inv)|'
     r'systematic\s*inv|kuvera|groww\s*mf|coin\s*by\s*zerodha|'
     r'amc|nippon|hdfc\s*mf|icici\s*pru.*mf|sbi\s*mf|axis\s*mf', 'Investments', 'Mutual Funds'),

    # Stocks/Brokers
    (r'zerodha|groww|upstox|angel\s*(one|broking)|icici\s*direct|'
     r'hdfc\s*sec|kotak\s*sec|5paisa|paytm\s*money|share\s*khan|'
     r'motilal\s*oswal|iifl\s*sec', 'Investments', 'Stocks'),

    # PPF
    (r'ppf|public\s*provident', 'Investments', 'PPF'),

    # NPS
    (r'nps|national\s*pension|pfrda|tier\s*[12]', 'Investments', 'NPS'),

    # Fixed Deposit
    (r'fd\s*(opening|booking|placement)|fixed\s*deposit|'
     r'term\s*deposit|td\s*booking', 'Investments', 'Fixed Deposit'),

    # =========================================================================
    # INSURANCE PATTERNS
    # =========================================================================

    # Life Insurance
    (r'lic|life\s*insurance|hdfc\s*life|icici\s*pru.*life|sbi\s*life|'
     r'max\s*life|bajaj\s*(allianz\s*)?life|tata\s*aia|'
     r'kotak\s*life|edelweiss\s*tokio', 'Insurance', 'Life Insurance'),

    # Health Insurance
    (r'health\s*insurance|mediclaim|star\s*health|care\s*health|'
     r'niva\s*bupa|max\s*bupa|hdfc\s*ergo.*health|'
     r'icici\s*lombard.*health|aditya\s*birla\s*health', 'Insurance', 'Health Insurance'),

    # Vehicle Insurance
    (r'vehicle\s*insurance|motor\s*insurance|car\s*insurance|'
     r'bike\s*insurance|two\s*wheeler\s*insurance|'
     r'acko|digit|policy\s*bazaar', 'Insurance', 'Vehicle Insurance'),

    # =========================================================================
    # TAX PATTERNS
    # =========================================================================

    # GST Payment
    (r'gst\s*(payment|challan|pmt|deposit)|cgst|sgst|igst|'
     r'gst\s*portal', 'Taxes', 'GST Payment'),

    # Income Tax
    (r'advance\s*tax|self\s*assessment\s*tax|income\s*tax\s*(pmt|payment)|'
     r'it\s*payment|challan\s*280|challan\s*281', 'Taxes', 'Income Tax'),

    # TDS
    (r'tds\s*(payment|deposit|challan)', 'Taxes', 'TDS'),

    # Professional Tax
    (r'professional\s*tax|pt\s*payment|p\s*tax', 'Taxes', 'Professional Tax'),

    # =========================================================================
    # HEALTHCARE PATTERNS
    # =========================================================================

    # Hospital
    (r'hospital|apollo|fortis|max\s*healthcare|manipal|narayana|'
     r'medanta|aiims|aster|columbia\s*asia', 'Healthcare', 'Hospital'),

    # Pharmacy
    (r'pharmacy|pharmeasy|netmeds|1mg|medplus|apollo\s*pharmacy|'
     r'medlife|wellness\s*forever', 'Healthcare', 'Pharmacy'),

    # Doctor/Labs
    (r'dr\s*\.?|doctor|consultation|diagnostic|lab|thyrocare|'
     r'lal\s*path|metropolis|srl|practo', 'Healthcare', 'Doctor/Consultation'),

    # =========================================================================
    # EDUCATION PATTERNS
    # =========================================================================

    # Schools/Colleges
    (r'school|college|university|institute|academy|fees|tuition|'
     r'education', 'Education', 'School/College Fees'),

    # Online Courses
    (r'udemy|coursera|unacademy|byju|whitehat|upgrad|simplilearn|'
     r'great\s*learning|edureka|skillshare', 'Education', 'Online Courses'),

    # =========================================================================
    # ENTERTAINMENT PATTERNS
    # =========================================================================

    # Movies
    (r'pvr|inox|cinepolis|bookmyshow|movie|cinema|multiplex', 'Entertainment', 'Movies'),

    # Gaming
    (r'steam|playstation|xbox|gaming|pubg|cod|mobile\s*game|'
     r'google\s*play\s*game', 'Entertainment', 'Gaming'),

    # Events
    (r'event|concert|show|ticket|paytm\s*insider|insider', 'Entertainment', 'Events'),

    # =========================================================================
    # CASH & BANK PATTERNS
    # =========================================================================

    # ATM Withdrawal
    (r'atm\s*(wdl|withdrawal|w/d|wd)|cash\s*withdrawal|nfs\s*(wdl|wd)|'
     r'atm\s*cash|cash\s*at\s*atm', 'Cash', 'ATM Withdrawal'),

    # Cash Deposit
    (r'cash\s*deposit|cdm\s*deposit|cash\s*dep', 'Cash', 'Cash Deposit'),

    # Service Charges
    (r'(service|maintenance|account)\s*charge|sms\s*charge|'
     r'annual\s*fee|yearly\s*fee|debit\s*card\s*fee', 'Bank Charges', 'Service Charges'),

    # Penalties
    (r'(insufficient|bounce|return|penalty)\s*charge|ecs\s*return|'
     r'nach\s*return|cheque\s*bounce|min\s*bal', 'Bank Charges', 'Penalties'),

    # Interest Paid (Loans)
    (r'interest\s*(debit|paid|charged)|int\s+dr|int\.\s*dr|'
     r'loan\s*emi|emi\s*payment|home\s*loan|car\s*loan|'
     r'personal\s*loan', 'Bank Charges', 'Interest Paid'),

    # =========================================================================
    # TRANSFER PATTERNS (Lower priority - often needs manual review)
    # =========================================================================

    # Self Transfer
    (r'self\s*transfer|transfer\s*to\s*self|own\s*account|'
     r'between\s*accounts', 'Transfer', 'Self Transfer'),

    # Bank Transfer
    (r'neft|rtgs|imps', 'Transfer', 'Bank Transfer'),
    (r'upi', 'Transfer', 'Bank Transfer'),
    (r'fund\s*transfer|bank\s*transfer', 'Transfer', 'Bank Transfer'),

    # =========================================================================
    # BUSINESS EXPENSE PATTERNS
    # =========================================================================

    (r'vendor|supplier|professional\s*fee|consultant|'
     r'legal\s*fee|audit\s*fee', 'Business Expense', 'Professional Services'),
    (r'office\s*supplies|stationery|printing', 'Business Expense', 'Office Supplies'),
]


def rule_based_categorize(
    description: str
) -> Optional[Tuple[str, str, float]]:
    """
    Categorize a transaction description using rule-based matching.

    Args:
        description: The transaction description to categorize

    Returns:
        Tuple of (category, subcategory, confidence) if a match is found,
        None if no rules match
    """
    if not description:
        return None

    # Normalize description for matching
    desc_lower = description.lower().strip()

    # Remove extra whitespace
    desc_lower = ' '.join(desc_lower.split())

    for pattern, category, subcategory in CATEGORY_RULES:
        try:
            if re.search(pattern, desc_lower, re.IGNORECASE):
                return (category, subcategory, RULE_BASED_CONFIDENCE)
        except re.error:
            # Skip invalid patterns
            continue

    return None


def get_matching_rule(description: str) -> Optional[str]:
    """
    Get the pattern that matched a description (for debugging).

    Args:
        description: The transaction description

    Returns:
        The matching pattern string, or None
    """
    if not description:
        return None

    desc_lower = description.lower().strip()
    desc_lower = ' '.join(desc_lower.split())

    for pattern, category, subcategory in CATEGORY_RULES:
        try:
            if re.search(pattern, desc_lower, re.IGNORECASE):
                return pattern
        except re.error:
            continue

    return None


def test_rules():
    """Test the rule-based categorizer with sample descriptions."""
    test_cases = [
        "SAL FOR OCT 2024",
        "SWIGGY ORDER 12345",
        "AMAZON PAY INDIA",
        "ATM WDL 15000",
        "NEFT CR FROM XYZ",
        "SIP PAYMENT HDFC MF",
        "IRCTC TICKET",
        "UBER TRIP",
        "UBER EATS ORDER",
        "LIC PREMIUM",
        "GST PAYMENT CHALLAN",
        "RANDOM UNKNOWN TRANSACTION",
    ]

    print("\n--- Rule-Based Categorization Test ---\n")
    for desc in test_cases:
        result = rule_based_categorize(desc)
        if result:
            cat, subcat, conf = result
            print(f"'{desc}' -> {cat} > {subcat} (conf: {conf})")
        else:
            print(f"'{desc}' -> NO MATCH (will go to Haiku)")
    print()


if __name__ == "__main__":
    test_rules()
