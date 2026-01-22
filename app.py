#!/usr/bin/env python3
"""
Bank Statement Processor - Web Interface

A Flask-based web application for processing and categorizing bank statements.
Built by V Raghavendran and Co.
"""
import os
import tempfile
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, render_template, request, jsonify, send_file, session

from config import (
    APP_NAME, APP_VERSION, APP_AUTHOR,
    DEFAULT_CONFIDENCE_THRESHOLD, get_api_key, CATEGORIES
)
from parsers.csv_parser import CSVParser
from parsers.xlsx_parser import XLSXParser
from categorizer.categorizer import TransactionCategorizer
from output.excel_generator import generate_output_excel


app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bank-statement-processor-secret-key')

# Store for processed files (in production, use proper storage)
UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()


@app.route('/')
def index():
    """Render the main page."""
    return render_template(
        'index.html',
        app_name=APP_NAME,
        app_version=APP_VERSION,
        app_author=APP_AUTHOR,
        categories=CATEGORIES
    )


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and processing."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Get processing options
    confidence_threshold = float(request.form.get('threshold', DEFAULT_CONFIDENCE_THRESHOLD))
    use_api = request.form.get('use_api', 'false').lower() == 'true'

    # Save uploaded file
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.csv', '.xlsx', '.xls']:
        return jsonify({'error': 'Unsupported file format. Please upload CSV or XLSX files.'}), 400

    # Generate unique filename
    unique_id = str(uuid.uuid4())[:8]
    input_filename = f"input_{unique_id}{file_ext}"
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    file.save(input_path)

    try:
        # Parse the file
        if file_ext in ['.xlsx', '.xls']:
            parser = XLSXParser(input_path)
        else:
            parser = CSVParser(input_path)

        transactions = parser.parse()

        if not transactions:
            return jsonify({'error': 'No transactions found in the file'}), 400

        # Get validation issues
        issues = parser.validate()

        # Categorize transactions
        api_key = get_api_key() if use_api else None
        categorizer = TransactionCategorizer(
            api_key=api_key,
            confidence_threshold=confidence_threshold
        )
        transactions = categorizer.categorize_all(transactions)

        # Generate output Excel
        output_filename = f"categorized_{unique_id}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        generate_output_excel(transactions, output_path)

        # Calculate statistics
        stats = categorizer.get_statistics()
        summary = parser.get_summary()

        # Prepare response data
        transaction_data = []
        for txn in transactions:
            transaction_data.append({
                'date': txn.date.strftime('%d-%b-%Y') if txn.date else '',
                'description': txn.description[:80] + '...' if len(txn.description) > 80 else txn.description,
                'debit': f"₹{txn.debit:,.2f}" if txn.debit else '',
                'credit': f"₹{txn.credit:,.2f}" if txn.credit else '',
                'category': txn.category,
                'subcategory': txn.subcategory,
                'source': txn.categorization_source,
                'confidence': f"{txn.categorization_confidence:.0%}"
            })

        return jsonify({
            'success': True,
            'output_file': output_filename,
            'statistics': {
                'total': stats['total'],
                'rules_matched': stats['rules_matched'],
                'haiku_matched': stats['haiku_matched'],
                'flagged': stats['flagged'],
                'total_debits': f"₹{summary['total_debits']:,.2f}",
                'total_credits': f"₹{summary['total_credits']:,.2f}",
                'net_flow': f"₹{summary['net_flow']:,.2f}",
                'date_range': f"{summary['date_range'][0]} to {summary['date_range'][1]}" if summary['date_range'][0] else 'N/A'
            },
            'transactions': transaction_data[:50],  # Send first 50 for preview
            'total_transactions': len(transaction_data),
            'validation_issues': len(issues)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # Clean up input file
        if os.path.exists(input_path):
            os.unlink(input_path)


@app.route('/download/<filename>')
def download_file(filename):
    """Download the processed Excel file."""
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=f"bank_statement_categorized_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )


@app.route('/api/categories')
def get_categories():
    """Return the list of categories."""
    return jsonify(CATEGORIES)


@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'app': APP_NAME,
        'version': APP_VERSION
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
