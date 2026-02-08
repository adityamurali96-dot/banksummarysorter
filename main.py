#!/usr/bin/env python3
"""
Bank Statement Processor - Main Entry Point

Processes bank statements in CSV or XLSX format, categorizes transactions
using a hybrid approach (rules + Claude Haiku API), and generates a
comprehensive Excel report.

Usage:
    python main.py --input <filepath> --output <output.xlsx> [options]

Examples:
    python main.py --input statement.xlsx --output categorized.xlsx
    python main.py --input docling_output.csv --output result.xlsx --api-key $ANTHROPIC_API_KEY
"""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from config import DEFAULT_CONFIDENCE_THRESHOLD, get_api_key
from parsers.base_parser import Transaction
from parsers.csv_parser import CSVParser
from parsers.xlsx_parser import XLSXParser
from parsers.pdf_parser import PDFPnLParser, ExtractionError
from categorizer.categorizer import TransactionCategorizer
from output.excel_generator import generate_output_excel, generate_pnl_excel


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process and categorize bank statement transactions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --input statement.xlsx --output categorized.xlsx
  python main.py --input statement.csv --output result.xlsx --type csv
  python main.py --input statement.csv --date-col 0 --desc-col 1 --debit-col 2 --credit-col 3

Environment Variables:
  ANTHROPIC_API_KEY              - Claude API key for Haiku categorization
  CATEGORIZER_CONFIDENCE_THRESHOLD - Default confidence threshold (default: 0.8)
        """
    )

    # Required arguments
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to the input bank statement file (CSV or XLSX)'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Path for the output Excel file'
    )

    # Optional arguments
    parser.add_argument(
        '--api-key', '-k',
        default=None,
        help='Anthropic API key (or set ANTHROPIC_API_KEY env var)'
    )
    parser.add_argument(
        '--type', '-t',
        choices=['xlsx', 'csv', 'pdf'],
        default=None,
        help='File type (auto-detected by extension if not specified)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f'Confidence threshold for flagging (default: {DEFAULT_CONFIDENCE_THRESHOLD})'
    )

    # CSV-specific arguments
    parser.add_argument(
        '--date-col',
        type=int,
        default=None,
        help='Column index for date (0-based, for CSV files)'
    )
    parser.add_argument(
        '--desc-col',
        type=int,
        action='append',
        dest='desc_cols',
        default=None,
        help='Column index for description (can specify multiple, for CSV)'
    )
    parser.add_argument(
        '--debit-col',
        type=int,
        default=None,
        help='Column index for debit amount (for CSV)'
    )
    parser.add_argument(
        '--credit-col',
        type=int,
        default=None,
        help='Column index for credit amount (for CSV)'
    )
    parser.add_argument(
        '--amount-col',
        type=int,
        default=None,
        help='Column index for single amount column (for CSV, if no separate debit/credit)'
    )
    parser.add_argument(
        '--balance-col',
        type=int,
        default=None,
        help='Column index for balance (for CSV)'
    )

    # XLSX-specific arguments
    parser.add_argument(
        '--sheet',
        default=None,
        help='Sheet name to process (for XLSX, defaults to first sheet)'
    )

    # PDF-specific arguments
    parser.add_argument(
        '--page-range',
        default=None,
        help='Page range to scan for P&L (e.g. "170-190"), defaults to all pages'
    )
    parser.add_argument(
        '--pnl-page',
        type=int,
        default=None,
        help='Extract P&L from a specific page number (skip identification)'
    )

    # Other options
    parser.add_argument(
        '--include-raw',
        action='store_true',
        help='Include raw text column in output'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Enable interactive mode for CSV column selection'
    )
    parser.add_argument(
        '--skip-categorization',
        action='store_true',
        help='Skip categorization (just parse and output)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    return parser.parse_args()


def detect_file_type(filepath: str) -> str:
    """
    Detect file type from extension.

    Args:
        filepath: Path to the file

    Returns:
        'xlsx', 'csv', or 'pdf'
    """
    ext = Path(filepath).suffix.lower()
    if ext in ('.xlsx', '.xls'):
        return 'xlsx'
    elif ext in ('.csv', '.txt'):
        return 'csv'
    elif ext == '.pdf':
        return 'pdf'
    else:
        raise ValueError(f"Unknown file extension: {ext}. Use --type to specify.")


def interactive_csv_setup(parser: CSVParser) -> None:
    """
    Interactive mode for CSV column selection.

    Args:
        parser: CSVParser instance
    """
    print("\n--- Interactive CSV Column Setup ---\n")

    # Preview rows
    rows = parser.preview_rows(10)
    if not rows:
        print("Error: Could not read CSV file")
        return

    print("First 10 rows of the file:")
    print("-" * 80)
    for i, row in enumerate(rows):
        cols = " | ".join(f"[{j}]{v[:20]}" for j, v in enumerate(row))
        print(f"Row {i}: {cols}")
    print("-" * 80)

    # Get date column
    date_col = input("\nWhich column contains the DATE? (enter column number): ")
    try:
        parser.date_col = int(date_col.strip())
    except ValueError:
        print("Invalid column number")
        return

    # Get description columns
    desc_cols = input("Which column(s) contain the DESCRIPTION? (comma-separated): ")
    try:
        parser.desc_cols = [int(c.strip()) for c in desc_cols.split(',')]
    except ValueError:
        print("Invalid column numbers")
        return

    # Get amount columns
    print("\nHow are amounts represented?")
    print("  1. Separate debit and credit columns")
    print("  2. Single amount column (with DR/CR indicator or negative)")
    amount_type = input("Enter 1 or 2: ").strip()

    if amount_type == '1':
        debit_col = input("Which column is DEBIT? ")
        credit_col = input("Which column is CREDIT? ")
        try:
            parser.debit_col = int(debit_col.strip())
            parser.credit_col = int(credit_col.strip())
        except ValueError:
            print("Invalid column numbers")
            return
    else:
        amount_col = input("Which column is AMOUNT? ")
        try:
            parser.amount_col = int(amount_col.strip())
        except ValueError:
            print("Invalid column number")
            return

    # Get balance column (optional)
    balance_col = input("Which column is BALANCE? (press Enter to skip): ").strip()
    if balance_col:
        try:
            parser.balance_col = int(balance_col)
        except ValueError:
            pass

    print("\nColumn mapping set. Proceeding with parsing...\n")


def main() -> int:
    """Main entry point."""
    args = parse_arguments()

    # Validate input file
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1

    # Detect or use specified file type
    try:
        file_type = args.type or detect_file_type(args.input)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"\n{'='*60}")
    print("Bank Statement Processor")
    print(f"{'='*60}")
    print(f"Input file: {args.input}")
    print(f"Output file: {args.output}")
    print(f"File type: {file_type}")
    print(f"Confidence threshold: {args.threshold}")
    print(f"{'='*60}\n")

    # PDF files use the P&L extraction pipeline
    if file_type == 'pdf':
        return _process_pdf(args)

    # Parse the file
    transactions: List[Transaction] = []

    if file_type == 'xlsx':
        parser = XLSXParser(args.input, sheet_name=args.sheet)
        transactions = parser.parse()
    else:
        parser = CSVParser(
            args.input,
            date_col=args.date_col,
            desc_cols=args.desc_cols,
            debit_col=args.debit_col,
            credit_col=args.credit_col,
            amount_col=args.amount_col,
            balance_col=args.balance_col,
        )

        # Interactive mode if requested and no columns specified
        if args.interactive and args.date_col is None:
            interactive_csv_setup(parser)

        transactions = parser.parse()

    if not transactions:
        print("Error: No transactions found in the file")
        return 1

    # Validate transactions
    issues = parser.validate()
    if issues:
        print(f"\nValidation warnings ({len(issues)}):")
        for issue in issues[:10]:
            print(f"  - Row {issue.row_numbers}: {issue.message}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
        print()

    # Print parsing summary
    summary = parser.get_summary()
    print(f"\n--- Parsing Summary ---")
    print(f"Total transactions: {summary['total_transactions']}")
    print(f"Total debits: ₹{summary['total_debits']:,.2f}")
    print(f"Total credits: ₹{summary['total_credits']:,.2f}")
    print(f"Net flow: ₹{summary['net_flow']:,.2f}")
    if summary['date_range'][0]:
        print(f"Date range: {summary['date_range'][0]} to {summary['date_range'][1]}")

    # Categorize transactions
    if not args.skip_categorization:
        api_key = args.api_key or get_api_key()
        if not api_key:
            print("\nWarning: No API key provided. "
                  "Transactions not matched by rules will be flagged for review.")

        categorizer = TransactionCategorizer(
            api_key=api_key,
            confidence_threshold=args.threshold
        )
        transactions = categorizer.categorize_all(transactions)
    else:
        print("\nSkipping categorization (--skip-categorization flag set)")
        for txn in transactions:
            txn.category = "Uncategorized"
            txn.subcategory = "Skipped"
            txn.categorization_source = "skipped"

    # Generate output
    generate_output_excel(
        transactions,
        args.output,
        include_raw_text=args.include_raw
    )

    print(f"\n{'='*60}")
    print("Processing complete!")
    print(f"Output saved to: {args.output}")
    print(f"{'='*60}\n")

    return 0


def _process_pdf(args) -> int:
    """Handle PDF P&L extraction."""
    print("\nMode: PDF P&L Extraction")
    print(f"{'='*60}")

    # Parse page range if provided
    page_range = None
    if args.page_range:
        try:
            parts = args.page_range.split('-')
            page_range = (int(parts[0]), int(parts[1]))
            print(f"Scanning pages {page_range[0]} to {page_range[1]}")
        except (ValueError, IndexError):
            print(f"Error: Invalid page range '{args.page_range}'. Use format: 170-190")
            return 1

    pdf_parser = PDFPnLParser(
        args.input,
        page_range=page_range,
    )

    # Step 1: Identify or use specific page
    if args.pnl_page:
        print(f"\nExtracting P&L from page {args.pnl_page} (skipping identification)")
        try:
            line_items = pdf_parser.extract_from_specific_page(args.pnl_page)
        except (ExtractionError, ValueError) as e:
            print(f"Error: {e}")
            return 1
    else:
        print("\nStep 1: Identifying P&L pages...")
        pnl_pages = pdf_parser.identify_pnl_pages()

        if not pnl_pages:
            print("Error: Could not identify any pages containing P&L data.")
            print("Tips:")
            print("  - Use --page-range to narrow the search (e.g. --page-range 170-190)")
            print("  - Use --pnl-page to specify the exact page number")
            print("  - Ensure the PDF contains extractable text (not a scanned image)")
            return 1

        print(f"\nFound P&L data on {len(pnl_pages)} page(s):")
        for pm in pnl_pages:
            print(f"  Page {pm.page_number} (score: {pm.score:.1f}) - matched: {', '.join(pm.matched_keywords[:5])}")

        # Step 2: Extract line items
        print("\nStep 2: Extracting P&L line items...")
        try:
            line_items = pdf_parser.extract_all()
        except ExtractionError as e:
            print(f"Error: {e}")
            return 1

    if not line_items:
        print("Error: No line items extracted")
        return 1

    # Print extraction summary
    print(f"\n--- Extraction Summary ---")
    print(f"Total line items: {len(line_items)}")
    if pdf_parser.column_headers:
        print(f"Column headers: {', '.join(pdf_parser.column_headers)}")

    print("\nExtracted line items:")
    for item in line_items:
        indent = "  " * item.indent_level
        amounts_str = " | ".join(
            f"{a:,.2f}" if a is not None else "-"
            for a in item.amounts
        )
        note = f" [Note {item.note_ref}]" if item.note_ref else ""
        total_marker = " **" if item.is_total else ""
        print(f"  {indent}{item.label}{note}: {amounts_str}{total_marker}")

    # Generate output Excel
    summary = pdf_parser.get_summary()
    generate_pnl_excel(
        line_items,
        args.output,
        column_headers=pdf_parser.column_headers,
        summary=summary,
    )

    print(f"\n{'='*60}")
    print("P&L extraction complete!")
    print(f"Output saved to: {args.output}")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
