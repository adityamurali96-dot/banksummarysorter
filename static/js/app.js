/**
 * Bank Statement Processor - JavaScript Application
 * Built by V Raghavendran and Co.
 */

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const clearFileBtn = document.getElementById('clear-file');
    const processBtn = document.getElementById('process-btn');
    const thresholdSlider = document.getElementById('confidence-threshold');
    const thresholdValue = document.getElementById('threshold-value');
    const useApiCheckbox = document.getElementById('use-api');

    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    const resultsSection = document.getElementById('results-section');
    const previewSection = document.getElementById('preview-section');
    const downloadBtn = document.getElementById('download-btn');

    // State
    let selectedFile = null;
    let outputFileName = null;

    // ==========================================================================
    // File Upload Handling
    // ==========================================================================

    // Click to upload
    dropZone.addEventListener('click', function() {
        fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Drag and drop events
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');

        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    // Handle file selection
    function handleFileSelect(file) {
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));

        if (!validExtensions.includes(fileExt)) {
            alert('Please upload a CSV or XLSX file.');
            return;
        }

        selectedFile = file;
        fileName.textContent = file.name;
        fileInfo.style.display = 'flex';
        processBtn.disabled = false;

        // Reset results
        hideResults();
    }

    // Clear file
    clearFileBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        selectedFile = null;
        fileInput.value = '';
        fileInfo.style.display = 'none';
        processBtn.disabled = true;
        hideResults();
    });

    // ==========================================================================
    // Threshold Slider
    // ==========================================================================

    thresholdSlider.addEventListener('input', function() {
        const value = Math.round(this.value * 100);
        thresholdValue.textContent = value + '%';
    });

    // ==========================================================================
    // Process Button
    // ==========================================================================

    processBtn.addEventListener('click', function() {
        if (!selectedFile) return;
        processFile();
    });

    // ==========================================================================
    // File Processing
    // ==========================================================================

    async function processFile() {
        // Show progress
        showProgress();
        updateProgress(10, 'Uploading file...');

        // Prepare form data
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('threshold', thresholdSlider.value);
        formData.append('use_api', useApiCheckbox.checked ? 'true' : 'false');

        try {
            updateProgress(30, 'Processing transactions...');

            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            updateProgress(70, 'Categorizing transactions...');

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Processing failed');
            }

            updateProgress(90, 'Generating report...');

            // Store output filename
            outputFileName = data.output_file;

            // Display results
            setTimeout(() => {
                updateProgress(100, 'Complete!');
                setTimeout(() => {
                    hideProgress();
                    displayResults(data);
                }, 500);
            }, 300);

        } catch (error) {
            hideProgress();
            alert('Error: ' + error.message);
        }
    }

    // ==========================================================================
    // Progress Display
    // ==========================================================================

    function showProgress() {
        progressSection.style.display = 'block';
        resultsSection.style.display = 'none';
        previewSection.style.display = 'none';
        progressFill.style.width = '0%';
    }

    function hideProgress() {
        progressSection.style.display = 'none';
    }

    function updateProgress(percent, text) {
        progressFill.style.width = percent + '%';
        progressText.textContent = text;
    }

    function hideResults() {
        resultsSection.style.display = 'none';
        previewSection.style.display = 'none';
    }

    // ==========================================================================
    // Results Display
    // ==========================================================================

    function displayResults(data) {
        // Update statistics
        document.getElementById('stat-total').textContent = data.statistics.total;
        document.getElementById('stat-rules').textContent = data.statistics.rules_matched;
        document.getElementById('stat-ai').textContent = data.statistics.haiku_matched;
        document.getElementById('stat-flagged').textContent = data.statistics.flagged;

        // Update financial summary
        document.getElementById('sum-debits').textContent = data.statistics.total_debits;
        document.getElementById('sum-credits').textContent = data.statistics.total_credits;
        document.getElementById('sum-net').textContent = data.statistics.net_flow;
        document.getElementById('date-range').textContent = data.statistics.date_range;

        // Show results section
        resultsSection.style.display = 'block';

        // Display transaction preview
        if (data.transactions && data.transactions.length > 0) {
            displayPreview(data.transactions, data.total_transactions);
        }

        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    function displayPreview(transactions, total) {
        const tbody = document.getElementById('preview-body');
        tbody.innerHTML = '';

        transactions.forEach(txn => {
            const row = document.createElement('tr');
            if (txn.source === 'flagged') {
                row.classList.add('flagged');
            }

            row.innerHTML = `
                <td>${txn.date}</td>
                <td>${escapeHtml(txn.description)}</td>
                <td class="debit">${txn.debit}</td>
                <td class="credit">${txn.credit}</td>
                <td><strong>${txn.category}</strong><br><small>${txn.subcategory}</small></td>
                <td>${formatSource(txn.source)} (${txn.confidence})</td>
            `;

            tbody.appendChild(row);
        });

        // Update preview note
        const previewNote = document.getElementById('preview-note');
        if (total > transactions.length) {
            previewNote.textContent = `Showing ${transactions.length} of ${total} transactions. Download the Excel file for the complete data.`;
        } else {
            previewNote.textContent = `Showing all ${total} transactions.`;
        }

        previewSection.style.display = 'block';
    }

    function formatSource(source) {
        switch(source) {
            case 'rules': return 'Rules';
            case 'haiku': return 'AI';
            case 'flagged': return 'Review';
            default: return source;
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ==========================================================================
    // Download Button
    // ==========================================================================

    downloadBtn.addEventListener('click', function() {
        if (outputFileName) {
            window.location.href = '/download/' + outputFileName;
        }
    });
});
