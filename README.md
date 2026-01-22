# Bank Statement Processor

A Python-based bank statement processing system that extracts, normalizes, and categorizes transactions from Indian bank statements.

## Features

- **Multi-format support**: Accepts bank statements in CSV (from Docling PDF conversion) and XLSX (direct bank downloads)
- **Smart parsing**: Handles multi-row transactions, repeated headers, and various date/amount formats
- **Hybrid categorization**: Uses rule-based matching first (fast, no API cost), then Claude Haiku API for unmatched transactions
- **Comprehensive output**: Generates Excel reports with categorized transactions, summaries, and flagged items for review
- **Indian format support**: Handles Indian date formats (DD/MM/YYYY) and number formats (9,17,390.58 lakhs format)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd banksummarysorter

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Process an XLSX bank statement
python main.py --input statement.xlsx --output categorized.xlsx

# Process a CSV file (from Docling PDF conversion)
python main.py --input statement.csv --output result.xlsx

# Use Claude Haiku for better categorization
export ANTHROPIC_API_KEY=your_api_key
python main.py --input statement.xlsx --output categorized.xlsx
```

## Usage

### Basic Usage

```bash
python main.py --input <filepath> --output <output.xlsx> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--input`, `-i` | Input bank statement file (CSV or XLSX) |
| `--output`, `-o` | Output Excel file path |
| `--api-key`, `-k` | Anthropic API key (or set `ANTHROPIC_API_KEY` env var) |
| `--type`, `-t` | File type (`xlsx` or `csv`), auto-detected if not specified |
| `--threshold` | Confidence threshold for flagging (default: 0.8) |
| `--interactive` | Enable interactive mode for CSV column selection |
| `--skip-categorization` | Skip categorization (just parse and output) |
| `--include-raw` | Include raw text column in output |
| `--verbose`, `-v` | Enable verbose output |

### CSV-specific Options

| Option | Description |
|--------|-------------|
| `--date-col` | Column index for date (0-based) |
| `--desc-col` | Column index(es) for description (can specify multiple) |
| `--debit-col` | Column index for debit amount |
| `--credit-col` | Column index for credit amount |
| `--amount-col` | Column index for single amount column |
| `--balance-col` | Column index for balance |

### XLSX-specific Options

| Option | Description |
|--------|-------------|
| `--sheet` | Sheet name to process (defaults to first sheet) |

## Examples

### Processing XLSX files

```bash
# Basic processing
python main.py -i hdfc_statement.xlsx -o categorized.xlsx

# Specify sheet name
python main.py -i statement.xlsx -o output.xlsx --sheet "Account Statement"

# Skip categorization (just extract transactions)
python main.py -i statement.xlsx -o output.xlsx --skip-categorization
```

### Processing CSV files

```bash
# Auto-detect columns
python main.py -i docling_output.csv -o output.xlsx

# Specify columns manually
python main.py -i statement.csv -o output.xlsx \
    --date-col 0 --desc-col 1 --debit-col 2 --credit-col 3 --balance-col 4

# Interactive mode (prompts for column selection)
python main.py -i statement.csv -o output.xlsx --interactive
```

### Using Claude Haiku API

```bash
# Set API key via environment variable
export ANTHROPIC_API_KEY=sk-ant-...
python main.py -i statement.xlsx -o output.xlsx

# Or pass API key directly
python main.py -i statement.xlsx -o output.xlsx --api-key sk-ant-...

# Adjust confidence threshold
python main.py -i statement.xlsx -o output.xlsx --threshold 0.7
```

## Output Format

The generated Excel file contains multiple sheets:

### 1. All Transactions
Complete list of all transactions with:
- Date, Description, Debit, Credit, Balance
- Category, Subcategory
- Confidence score and categorization source (rules/haiku/flagged)
- Notes (Haiku's suggestion for flagged items)

### 2. Category Summary
Pivot-style summary showing:
- Total debits and credits per category/subcategory
- Net flow per category
- Transaction counts

### 3. Monthly Summary
Month-by-month breakdown:
- Total debits and credits per month
- Net flow per month

### 4. Flagged for Review
Transactions that need manual review:
- All flagged transactions with AI suggestions
- Empty columns for user to fill in correct categories

### 5. Statistics
Summary statistics including:
- Total transaction count
- Categorization breakdown (rules vs Haiku vs flagged)
- Top categories by count and amount

## Supported Categories

| Category | Subcategories |
|----------|--------------|
| Income | Salary, Business Income, Interest, Dividend, Refund, Rental Income, Other Income |
| Shopping | Online Shopping, Groceries, Electronics, Clothing, Home & Furniture, Other Shopping |
| Food & Dining | Restaurant, Food Delivery, Cafe/Coffee, Other Food |
| Transport | Fuel, Cab/Taxi, Public Transport, Flight, Train, Other Travel |
| Bills & Utilities | Electricity, Mobile/Internet, Water, Gas, Rent, Subscriptions, Other Bills |
| Investments | Mutual Funds, Stocks, Fixed Deposit, PPF, NPS, Other Investment |
| Insurance | Life Insurance, Health Insurance, Vehicle Insurance, Other Insurance |
| Transfer | Bank Transfer, Self Transfer, Family Transfer |
| Healthcare | Hospital, Pharmacy, Doctor/Consultation, Lab Tests |
| Education | School/College Fees, Books, Online Courses |
| Entertainment | Movies, Events, Gaming, OTT Subscriptions |
| Taxes | GST Payment, Income Tax, TDS, Professional Tax, Tax Refund |
| Business Expense | Vendor Payment, Professional Services, Office Supplies |
| Cash | ATM Withdrawal, Cash Deposit |
| Bank Charges | Service Charges, Penalties, Interest Paid |
| Other | Uncategorized |

## Project Structure

```
banksummarysorter/
├── main.py                    # CLI entry point
├── config.py                  # Configuration and constants
├── requirements.txt           # Dependencies
│
├── parsers/
│   ├── base_parser.py         # Abstract base class
│   ├── xlsx_parser.py         # Excel file parser
│   └── csv_parser.py          # CSV file parser (Docling output)
│
├── categorizer/
│   ├── rules.py               # Rule-based categorization
│   ├── haiku_client.py        # Claude Haiku API client
│   └── categorizer.py         # Main categorization orchestrator
│
├── normalizer/
│   ├── date_parser.py         # Multi-format date parsing
│   └── amount_parser.py       # Indian number format parsing
│
├── output/
│   └── excel_generator.py     # Excel report generation
│
└── tests/
    ├── test_parsers.py        # Parser unit tests
    ├── test_categorizer.py    # Categorizer unit tests
    ├── test_integration.py    # Integration tests
    └── sample_files/          # Test data
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_parsers.py

# Run with verbose output
python -m pytest tests/ -v
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for Haiku categorization |
| `CATEGORIZER_CONFIDENCE_THRESHOLD` | Default confidence threshold (default: 0.8) |

## How It Works

### 1. Parsing
- **XLSX**: Scans for header row using keywords, maps columns automatically
- **CSV**: Uses date-anchored detection to handle multi-row transactions

### 2. Normalization
- Dates: Supports DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, and more
- Amounts: Handles Indian format (9,17,390.58), currency symbols, DR/CR indicators

### 3. Categorization
1. Rule-based matching (60-70% of transactions)
   - Fast, no API cost
   - Pattern matching using regex
2. Claude Haiku API (for unmatched)
   - AI-powered categorization
   - Confidence scoring
3. Flagging (low confidence)
   - Transactions below threshold flagged for manual review

### 4. Output Generation
- Multi-sheet Excel workbook
- Formatted with colors, filters, and proper number formats
- Flagged items highlighted for easy review

## License

MIT License
