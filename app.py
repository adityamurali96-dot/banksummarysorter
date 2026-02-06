#!/usr/bin/env python3
"""
Bank Statement Processor - Web Interface

A Flask-based web application for processing and categorizing bank statements.
Built by V Raghavendran and Co.

Optimized for Railway deployment.
"""
import atexit
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from threading import Lock, Thread
from time import sleep
from typing import Dict, List, Optional

from flask import Flask, render_template, request, jsonify, send_file

from config import (
    APP_NAME, APP_VERSION, APP_AUTHOR,
    DEFAULT_CONFIDENCE_THRESHOLD, get_api_key, CATEGORIES
)
from parsers.csv_parser import CSVParser
from parsers.xlsx_parser import XLSXParser
from categorizer.categorizer import TransactionCategorizer
from output.excel_generator import generate_output_excel


# =============================================================================
# Application Configuration
# =============================================================================

app = Flask(__name__)
_secret_key = os.environ.get('FLASK_SECRET_KEY')
if not _secret_key:
    import warnings
    warnings.warn(
        "FLASK_SECRET_KEY not set. Using a random key; sessions will not "
        "persist across workers or restarts. Set FLASK_SECRET_KEY in production.",
        stacklevel=1,
    )
    _secret_key = os.urandom(24).hex()
app.secret_key = _secret_key

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# File storage configuration
UPLOAD_FOLDER = tempfile.mkdtemp(prefix='bank_upload_')
OUTPUT_FOLDER = tempfile.mkdtemp(prefix='bank_output_')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size

app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Track output files for cleanup (guarded by _output_files_lock)
output_files: Dict[str, datetime] = {}
_output_files_lock = Lock()


# =============================================================================
# Cleanup Functions
# =============================================================================

def cleanup_old_files():
    """Background task to clean up old output files (older than 1 hour)."""
    while True:
        try:
            sleep(300)  # Run every 5 minutes
            now = datetime.now()
            files_to_remove = []

            with _output_files_lock:
                for filename, created_at in list(output_files.items()):
                    age_minutes = (now - created_at).total_seconds() / 60
                    if age_minutes > 60:  # 1 hour
                        files_to_remove.append(filename)

            for filename in files_to_remove:
                filepath = os.path.join(OUTPUT_FOLDER, filename)
                try:
                    if os.path.exists(filepath):
                        os.unlink(filepath)
                        logger.info(f"Cleaned up old file: {filename}")
                except Exception as e:
                    logger.error(f"Error cleaning up {filename}: {e}")
                with _output_files_lock:
                    output_files.pop(filename, None)

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")


def cleanup_on_exit():
    """Clean up temporary directories on application exit."""
    try:
        shutil.rmtree(UPLOAD_FOLDER, ignore_errors=True)
        shutil.rmtree(OUTPUT_FOLDER, ignore_errors=True)
        logger.info("Cleaned up temporary directories")
    except Exception as e:
        logger.error(f"Error cleaning up on exit: {e}")


# Register cleanup on exit
atexit.register(cleanup_on_exit)

# Start background cleanup thread (only in production)
if os.environ.get('RAILWAY_ENVIRONMENT') or not os.environ.get('FLASK_DEBUG'):
    cleanup_thread = Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()


# =============================================================================
# Routes
# =============================================================================

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

    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.csv', '.xlsx', '.xls']:
        return jsonify({'error': 'Unsupported file format. Please upload CSV or XLSX files.'}), 400

    # Generate unique filename
    unique_id = str(uuid.uuid4())[:8]
    input_filename = f"input_{unique_id}{file_ext}"
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)

    try:
        # Save uploaded file
        file.save(input_path)
        logger.info(f"File uploaded: {file.filename} -> {input_filename}")

        # Parse the file
        if file_ext in ['.xlsx', '.xls']:
            parser = XLSXParser(input_path)
        else:
            parser = CSVParser(input_path)

        transactions = parser.parse()

        if not transactions:
            return jsonify({'error': 'No transactions found in the file. Please check the file format.'}), 400

        # Get validation issues
        issues = parser.validate()

        # Categorize transactions
        api_key = get_api_key() if use_api else None
        if use_api and not api_key:
            logger.warning("AI categorization requested but no API key configured")

        categorizer = TransactionCategorizer(
            api_key=api_key,
            confidence_threshold=confidence_threshold
        )
        transactions = categorizer.categorize_all(transactions)

        # Generate output Excel
        output_filename = f"categorized_{unique_id}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        generate_output_excel(transactions, output_path)

        # Track output file for cleanup
        with _output_files_lock:
            output_files[output_filename] = datetime.now()

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

        logger.info(f"Processed {len(transactions)} transactions for {file.filename}")

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
        logger.error(f"Error processing file {file.filename}: {e}")
        return jsonify({'error': str(e)}), 500

    finally:
        # Clean up input file
        try:
            if os.path.exists(input_path):
                os.unlink(input_path)
        except Exception as e:
            logger.error(f"Error cleaning up input file: {e}")


@app.route('/download/<filename>')
def download_file(filename):
    """Download the processed Excel file."""
    # Security: only allow alphanumeric filenames with underscores and dots
    if not filename.replace('_', '').replace('.', '').isalnum():
        return jsonify({'error': 'Invalid filename'}), 400

    file_path = os.path.realpath(os.path.join(OUTPUT_FOLDER, filename))
    # Ensure the resolved path is actually within OUTPUT_FOLDER
    if not file_path.startswith(os.path.realpath(OUTPUT_FOLDER) + os.sep):
        return jsonify({'error': 'Invalid filename'}), 400

    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found or expired. Please process the file again.'}), 404

    logger.info(f"File downloaded: {filename}")

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
    """Health check endpoint for Railway."""
    return jsonify({
        'status': 'healthy',
        'app': APP_NAME,
        'version': APP_VERSION,
        'timestamp': datetime.now().isoformat()
    })


@app.errorhandler(413)
def file_too_large(e):
    """Handle file too large error."""
    return jsonify({
        'error': f'File too large. Maximum size is {MAX_CONTENT_LENGTH // (1024 * 1024)} MB.'
    }), 413


@app.errorhandler(500)
def internal_error(e):
    """Handle internal server error."""
    logger.error(f"Internal server error: {e}")
    return jsonify({
        'error': 'An internal error occurred. Please try again.'
    }), 500


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on port {port}")
    logger.info(f"Built by {APP_AUTHOR}")

    app.run(host='0.0.0.0', port=port, debug=debug)
