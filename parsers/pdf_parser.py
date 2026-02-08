"""
PDF Parser for extracting Profit & Loss (P&L) line items from PDF documents.

Handles:
- Large PDFs (annual reports) where P&L may be on any page
- Page identification using keyword scoring
- Multiple table extraction strategies (bordered tables, text-based columns)
- Indian financial statement formats (Ind AS / Companies Act)
- Multi-period columns (current year, previous year)
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

from normalizer.amount_parser import parse_amount

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PnLLineItem:
    """A single line item extracted from a P&L statement."""
    label: str
    amounts: List[Optional[float]] = field(default_factory=list)
    note_ref: Optional[str] = None
    indent_level: int = 0          # 0 = section header, 1 = item, 2 = sub-item
    is_total: bool = False
    page_number: int = 0
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "amounts": self.amounts,
            "note_ref": self.note_ref,
            "indent_level": self.indent_level,
            "is_total": self.is_total,
            "page_number": self.page_number,
        }


@dataclass
class PnLPageMatch:
    """Represents a page identified as containing P&L data."""
    page_number: int          # 1-based
    score: float
    matched_keywords: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Keyword configuration for identification
# ---------------------------------------------------------------------------

# High-confidence indicators that a page IS a P&L statement
_PNL_PRIMARY_KEYWORDS = [
    "statement of profit and loss",
    "profit and loss account",
    "profit and loss statement",
    "income statement",
    "statement of income",
    "consolidated statement of profit",
    "standalone statement of profit",
    "statement of profit & loss",
    "profit & loss account",
    "profit & loss statement",
]

# Medium-confidence indicators – typical P&L line item labels
_PNL_SECONDARY_KEYWORDS = [
    "revenue from operations",
    "other income",
    "total income",
    "total revenue",
    "cost of materials consumed",
    "cost of goods sold",
    "employee benefit",
    "employee benefits expense",
    "finance cost",
    "depreciation and amortisation",
    "depreciation and amortization",
    "total expenses",
    "profit before tax",
    "profit before exceptional",
    "profit after tax",
    "profit for the period",
    "profit for the year",
    "profit/(loss)",
    "profit / (loss)",
    "loss for the period",
    "loss for the year",
    "tax expense",
    "current tax",
    "deferred tax",
    "earnings per equity share",
    "earnings per share",
    "basic eps",
    "diluted eps",
    "other comprehensive income",
    "total comprehensive income",
]

# Keywords that indicate this is NOT a P&L page (reduce false positives)
_PNL_NEGATIVE_KEYWORDS = [
    "balance sheet",
    "statement of financial position",
    "cash flow statement",
    "statement of cash flows",
    "statement of changes in equity",
    "notes to financial statements",
    "notes forming part",
    "schedule",
    "auditor",
    "director",
    "board of directors",
    "corporate governance",
    "management discussion",
]

# Total / subtotal keywords to flag line items
_TOTAL_KEYWORDS = [
    "total income",
    "total revenue",
    "total expenses",
    "profit before",
    "profit after",
    "profit for the",
    "profit/(loss)",
    "profit / (loss)",
    "loss before",
    "loss after",
    "loss for the",
    "net profit",
    "net loss",
    "total comprehensive",
    "total other comprehensive",
]


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------

class PDFPnLParser:
    """
    Extracts P&L line items from PDF files.

    Usage::

        parser = PDFPnLParser("annual_report.pdf")
        pages = parser.identify_pnl_pages()
        items = parser.extract_all()
    """

    def __init__(
        self,
        filepath: str,
        *,
        page_range: Optional[Tuple[int, int]] = None,
        min_identification_score: float = 3.0,
    ):
        if not _HAS_PDFPLUMBER:
            raise ImportError(
                "pdfplumber is required for PDF parsing. "
                "Install it with: pip install pdfplumber"
            )

        self.filepath = filepath
        self.page_range = page_range
        self.min_identification_score = min_identification_score

        self._pdf = None
        self._pnl_pages: List[PnLPageMatch] = []
        self._line_items: List[PnLLineItem] = []
        self._column_headers: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def identify_pnl_pages(self) -> List[PnLPageMatch]:
        """
        Scan the PDF and return pages that likely contain P&L data,
        sorted by confidence score (highest first).
        """
        self._pnl_pages = []

        with pdfplumber.open(self.filepath) as pdf:
            start = (self.page_range[0] - 1) if self.page_range else 0
            end = self.page_range[1] if self.page_range else len(pdf.pages)

            for page_idx in range(start, min(end, len(pdf.pages))):
                page = pdf.pages[page_idx]
                page_num = page_idx + 1  # 1-based

                text = (page.extract_text() or "").lower()
                if not text.strip():
                    continue

                score, matched = self._score_page(text)

                if score >= self.min_identification_score:
                    self._pnl_pages.append(PnLPageMatch(
                        page_number=page_num,
                        score=score,
                        matched_keywords=matched,
                    ))

        # Sort by score descending
        self._pnl_pages.sort(key=lambda p: p.score, reverse=True)

        if self._pnl_pages:
            logger.info(
                "Identified %d P&L page(s): %s",
                len(self._pnl_pages),
                [(p.page_number, round(p.score, 1)) for p in self._pnl_pages],
            )
        else:
            logger.warning("No P&L pages identified in %s", self.filepath)

        return self._pnl_pages

    def extract_all(self) -> List[PnLLineItem]:
        """
        Full pipeline: identify pages then extract line items from each.
        Returns all extracted P&L line items.
        """
        if not self._pnl_pages:
            self.identify_pnl_pages()

        if not self._pnl_pages:
            raise ExtractionError(
                "Could not identify any pages containing P&L data. "
                "The PDF may not contain a Profit & Loss statement, "
                "or the format is not recognised."
            )

        self._line_items = []

        with pdfplumber.open(self.filepath) as pdf:
            for pm in self._pnl_pages:
                page = pdf.pages[pm.page_number - 1]
                items = self._extract_from_page(page, pm.page_number)
                self._line_items.extend(items)

        if not self._line_items:
            pages_str = ", ".join(str(p.page_number) for p in self._pnl_pages)
            raise ExtractionError(
                f"Could not extract any P&L line items from page(s) {pages_str}. "
                "The PDF table structure may not be supported."
            )

        return self._line_items

    def extract_from_specific_page(self, page_number: int) -> List[PnLLineItem]:
        """Extract P&L line items from a specific page (1-based)."""
        with pdfplumber.open(self.filepath) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                raise ValueError(
                    f"Page {page_number} out of range (PDF has {len(pdf.pages)} pages)"
                )
            page = pdf.pages[page_number - 1]
            return self._extract_from_page(page, page_number)

    @property
    def line_items(self) -> List[PnLLineItem]:
        return self._line_items

    @property
    def pnl_pages(self) -> List[PnLPageMatch]:
        return self._pnl_pages

    @property
    def column_headers(self) -> List[str]:
        return self._column_headers

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_line_items": len(self._line_items),
            "pages_identified": len(self._pnl_pages),
            "page_numbers": [p.page_number for p in self._pnl_pages],
            "column_headers": self._column_headers,
        }

    # ------------------------------------------------------------------
    # Page scoring / identification
    # ------------------------------------------------------------------

    def _score_page(self, text: str) -> Tuple[float, List[str]]:
        """
        Score a page for likelihood of containing P&L data.

        Returns (score, list_of_matched_keywords).
        """
        score = 0.0
        matched: List[str] = []

        # Primary keywords (high value)
        for kw in _PNL_PRIMARY_KEYWORDS:
            if kw in text:
                score += 5.0
                matched.append(kw)

        # Secondary keywords (medium value)
        for kw in _PNL_SECONDARY_KEYWORDS:
            if kw in text:
                score += 1.0
                matched.append(kw)

        # Negative keywords (reduce score)
        for kw in _PNL_NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 2.0

        # Bonus: presence of Indian currency formatting (₹ or Rs or Lakhs/Crores)
        if re.search(r'[₹]|rs\.?\s|in\s+(lakhs?|crores?|thousands?|millions?)', text):
            score += 1.0

        # Bonus: note reference numbers typical in Indian financials
        if re.search(r'note\s*(?:no\.?)?\s*\d', text):
            score += 0.5

        # Bonus: column headers like "Year ended" or "For the year"
        if re.search(r'(?:year|period)\s+ended|for\s+the\s+(?:year|period)', text):
            score += 1.5
            matched.append("period header")

        # Bonus: looks like it has amounts in Indian format
        indian_amounts = re.findall(r'\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?', text)
        if len(indian_amounts) >= 5:
            score += 1.0

        return max(score, 0.0), matched

    # ------------------------------------------------------------------
    # Line item extraction from a single page
    # ------------------------------------------------------------------

    def _extract_from_page(
        self, page: Any, page_number: int
    ) -> List[PnLLineItem]:
        """
        Try multiple strategies to extract P&L line items from a page.

        Strategy order:
        1. pdfplumber table extraction (works for bordered/ruled tables)
        2. Text-based column position extraction (works for borderless tables)
        """
        items: List[PnLLineItem] = []

        # Strategy 1: Table extraction
        items = self._extract_via_tables(page, page_number)
        if items:
            logger.info(
                "Page %d: extracted %d items via table strategy",
                page_number, len(items),
            )
            return items

        # Strategy 2: Text-based extraction using word positions
        items = self._extract_via_text_positions(page, page_number)
        if items:
            logger.info(
                "Page %d: extracted %d items via text-position strategy",
                page_number, len(items),
            )
            return items

        # Strategy 3: Line-by-line regex extraction (last resort)
        items = self._extract_via_line_regex(page, page_number)
        if items:
            logger.info(
                "Page %d: extracted %d items via line-regex strategy",
                page_number, len(items),
            )
            return items

        logger.warning("Page %d: all extraction strategies failed", page_number)
        return []

    # ------------------------------------------------------------------
    # Strategy 1: pdfplumber table extraction
    # ------------------------------------------------------------------

    def _extract_via_tables(
        self, page: Any, page_number: int
    ) -> List[PnLLineItem]:
        """Extract using pdfplumber's built-in table finder."""
        tables = page.extract_tables(
            table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 5,
                "join_tolerance": 5,
            }
        )

        if not tables:
            # Try with text strategy (for borderless tables)
            tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 5,
                    "join_tolerance": 5,
                    "min_words_vertical": 2,
                    "min_words_horizontal": 1,
                }
            )

        if not tables:
            return []

        items: List[PnLLineItem] = []

        for table in tables:
            if not table or len(table) < 2:
                continue

            # Find the header row and amount columns
            header_idx, amount_cols = self._find_table_structure(table)
            if amount_cols is None:
                continue

            # Extract header labels for amount columns
            if header_idx is not None and header_idx < len(table):
                header_row = table[header_idx]
                self._column_headers = [
                    self._clean_text(header_row[c]) if c < len(header_row) else ""
                    for c in amount_cols
                ]

            # Process data rows
            data_start = (header_idx + 1) if header_idx is not None else 0
            for row in table[data_start:]:
                item = self._parse_table_row(row, amount_cols, page_number)
                if item:
                    items.append(item)

        return items

    def _find_table_structure(
        self, table: List[List[Optional[str]]]
    ) -> Tuple[Optional[int], Optional[List[int]]]:
        """
        Find the header row and which columns contain amounts.

        Returns (header_row_index, list_of_amount_column_indices).
        """
        # Look for header row in first few rows
        for row_idx, row in enumerate(table[:5]):
            if not row:
                continue

            row_text = " ".join(
                self._clean_text(c) for c in row if c
            ).lower()

            # Check for P&L header indicators
            has_label = any(
                kw in row_text
                for kw in ["particulars", "note", "description", "items"]
            )
            has_period = bool(re.search(
                r'(?:year|period)\s+ended|20\d{2}|march|31st|fy\s*\d{2}',
                row_text,
            ))

            if has_label or has_period:
                # Identify amount columns: columns that contain year/period info
                # or are numeric in subsequent rows
                amount_cols = self._identify_amount_columns(table, row_idx)
                if amount_cols:
                    return row_idx, amount_cols

        # No header found; try to infer from data
        amount_cols = self._identify_amount_columns_from_data(table)
        if amount_cols:
            return None, amount_cols

        return None, None

    def _identify_amount_columns(
        self, table: List[List[Optional[str]]], header_idx: int
    ) -> List[int]:
        """Identify which columns hold amounts by checking data rows below the header."""
        if header_idx + 1 >= len(table):
            return []

        num_cols = max(len(row) for row in table if row)
        amount_scores = [0] * num_cols
        has_large_number = [False] * num_cols  # Track if column has financial-sized numbers

        # Also check the header row for "note" keyword to exclude note columns
        note_cols: set = set()
        if header_idx < len(table) and table[header_idx]:
            for ci, hcell in enumerate(table[header_idx]):
                if hcell and re.search(r'\bnote\b', self._clean_text(hcell).lower()):
                    note_cols.add(ci)

        # Check a sample of data rows
        sample = table[header_idx + 1: header_idx + 10]
        for row in sample:
            for col_idx in range(min(len(row), num_cols)):
                cell = self._clean_text(row[col_idx]) if row[col_idx] else ""
                if self._looks_like_amount(cell):
                    amount_scores[col_idx] += 1
                    # Check if this is a "real" financial amount (has comma or decimal
                    # or is a larger number, not just a 1-2 digit note ref)
                    clean = cell.replace("(", "").replace(")", "").replace("-", "")
                    if "," in clean or "." in clean or len(clean.replace(" ", "")) >= 4:
                        has_large_number[col_idx] = True

        # Columns where >40% of sample rows have amounts
        # BUT exclude columns that only have small numbers (likely note refs)
        threshold = max(1, len(sample) * 0.4)
        amount_cols = [
            i for i, s in enumerate(amount_scores)
            if s >= threshold
            and i > 0  # skip first column (usually label)
            and i not in note_cols  # skip note columns
            and has_large_number[i]  # must have at least one financial-sized number
        ]

        return amount_cols

    def _identify_amount_columns_from_data(
        self, table: List[List[Optional[str]]]
    ) -> List[int]:
        """Infer amount columns purely from data patterns (no header found)."""
        if len(table) < 3:
            return []

        num_cols = max(len(row) for row in table if row)
        amount_scores = [0] * num_cols

        for row in table:
            for col_idx in range(min(len(row), num_cols)):
                cell = self._clean_text(row[col_idx]) if row[col_idx] else ""
                if self._looks_like_amount(cell):
                    amount_scores[col_idx] += 1

        threshold = max(2, len(table) * 0.3)
        amount_cols = [
            i for i, s in enumerate(amount_scores)
            if s >= threshold and i > 0
        ]

        return amount_cols

    def _parse_table_row(
        self,
        row: List[Optional[str]],
        amount_cols: List[int],
        page_number: int,
    ) -> Optional[PnLLineItem]:
        """Parse a single table row into a PnLLineItem."""
        if not row:
            return None

        # First non-empty cell that isn't in an amount column is the label
        label = ""
        note_ref = None

        for col_idx, cell in enumerate(row):
            if col_idx in amount_cols:
                continue
            text = self._clean_text(cell) if cell else ""
            if not text:
                continue

            # Check if this cell is a note reference (small number, 1-3 digits)
            if re.match(r'^\d{1,3}[a-z]?$', text):
                note_ref = text
                continue

            if not label:
                label = text
            else:
                # Additional text after label that isn't a note ref
                label += " " + text

        if not label:
            return None

        # Skip rows that are clearly not line items
        label_lower = label.lower().strip()
        skip_patterns = [
            r'^page\s+\d+',
            r'^note\s*$',
            r'^particulars\s*$',
            r'^sr\.?\s*no',
            r'^s\.?\s*no',
            r'^\(?\s*₹',
            r'^in\s+(lakhs?|crores?|thousands?|millions?)',
            r'^amount\s+in',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, label_lower):
                return None

        # Extract amounts
        amounts: List[Optional[float]] = []
        for col_idx in amount_cols:
            if col_idx < len(row) and row[col_idx]:
                cell_text = self._clean_text(row[col_idx])
                amt = self._parse_financial_amount(cell_text)
                amounts.append(amt)
            else:
                amounts.append(None)

        # Skip rows with no amounts at all (section headers without numbers
        # are kept only if they look like headings)
        has_any_amount = any(a is not None for a in amounts)
        if not has_any_amount and not self._looks_like_section_header(label):
            return None

        # Determine indent level
        indent = self._detect_indent(label)

        # Determine if this is a total row
        is_total = any(kw in label_lower for kw in _TOTAL_KEYWORDS)

        return PnLLineItem(
            label=label.strip(),
            amounts=amounts,
            note_ref=note_ref,
            indent_level=indent,
            is_total=is_total,
            page_number=page_number,
            raw_text=" | ".join(str(c) for c in row if c),
        )

    # ------------------------------------------------------------------
    # Strategy 2: Text position-based extraction
    # ------------------------------------------------------------------

    def _extract_via_text_positions(
        self, page: Any, page_number: int
    ) -> List[PnLLineItem]:
        """
        Extract using word-level bounding boxes to reconstruct columns.

        This works for borderless tables where pdfplumber's table finder
        fails but text is still columnar.
        """
        words = page.extract_words(
            keep_blank_chars=True,
            x_tolerance=3,
            y_tolerance=3,
        )

        if not words:
            return []

        # Group words into lines by y-coordinate
        lines = self._group_words_into_lines(words)
        if len(lines) < 3:
            return []

        # Detect column boundaries from amount positions
        amount_x_ranges = self._detect_amount_columns_from_positions(lines)
        if not amount_x_ranges:
            return []

        items: List[PnLLineItem] = []

        for line_words in lines:
            item = self._parse_positioned_line(
                line_words, amount_x_ranges, page_number
            )
            if item:
                items.append(item)

        return items

    def _group_words_into_lines(
        self, words: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Group words into lines based on y-coordinate proximity."""
        if not words:
            return []

        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
        lines: List[List[Dict[str, Any]]] = []
        current_line: List[Dict[str, Any]] = [sorted_words[0]]
        current_top = sorted_words[0]["top"]

        for word in sorted_words[1:]:
            if abs(word["top"] - current_top) < 5:
                current_line.append(word)
            else:
                current_line.sort(key=lambda w: w["x0"])
                lines.append(current_line)
                current_line = [word]
                current_top = word["top"]

        if current_line:
            current_line.sort(key=lambda w: w["x0"])
            lines.append(current_line)

        return lines

    def _detect_amount_columns_from_positions(
        self, lines: List[List[Dict[str, Any]]]
    ) -> List[Tuple[float, float]]:
        """
        Detect column x-ranges for amounts by finding clusters of
        right-aligned numbers.
        """
        # Collect x1 (right edge) of all amount-like words
        amount_rights: List[float] = []
        for line in lines:
            for word in line:
                text = word.get("text", "")
                if self._looks_like_amount(text):
                    amount_rights.append(word["x1"])

        if len(amount_rights) < 3:
            return []

        # Cluster the right edges (amounts in the same column align right)
        clusters = self._cluster_values(amount_rights, tolerance=15)

        # For each cluster, determine the x-range
        x_ranges: List[Tuple[float, float]] = []
        for cluster in clusters:
            if len(cluster) < 3:
                continue
            right = max(cluster)
            # Look left from the right edge to find the start of numbers
            left = right - 120  # Typical column width
            x_ranges.append((left, right))

        x_ranges.sort(key=lambda r: r[0])
        return x_ranges

    def _cluster_values(
        self, values: List[float], tolerance: float = 15
    ) -> List[List[float]]:
        """Simple 1D clustering."""
        if not values:
            return []

        sorted_vals = sorted(values)
        clusters: List[List[float]] = [[sorted_vals[0]]]

        for val in sorted_vals[1:]:
            if val - clusters[-1][-1] <= tolerance:
                clusters[-1].append(val)
            else:
                clusters.append([val])

        return clusters

    def _parse_positioned_line(
        self,
        line_words: List[Dict[str, Any]],
        amount_x_ranges: List[Tuple[float, float]],
        page_number: int,
    ) -> Optional[PnLLineItem]:
        """Parse a line of positioned words into a PnLLineItem."""
        label_parts: List[str] = []
        amounts: List[Optional[float]] = [None] * len(amount_x_ranges)
        note_ref = None

        for word in line_words:
            text = word.get("text", "").strip()
            if not text:
                continue

            # Check if word falls in an amount column
            word_center = (word["x0"] + word["x1"]) / 2
            placed = False
            for col_idx, (x_left, x_right) in enumerate(amount_x_ranges):
                if x_left <= word_center <= x_right + 10:
                    if self._looks_like_amount(text):
                        amt = self._parse_financial_amount(text)
                        if amounts[col_idx] is None:
                            amounts[col_idx] = amt
                        placed = True
                    break

            if not placed:
                # Check if it's a note ref
                if re.match(r'^\d{1,3}[a-z]?$', text) and not label_parts:
                    note_ref = text
                else:
                    label_parts.append(text)

        label = " ".join(label_parts).strip()
        if not label:
            return None

        # Skip non-line-item rows
        label_lower = label.lower()
        skip_patterns = [
            r'^page\s+\d+',
            r'^note\s*$',
            r'^particulars\s*$',
            r'^\(?\s*₹',
            r'^in\s+(lakhs?|crores?)',
            r'^amount\s+in',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, label_lower):
                return None

        has_any_amount = any(a is not None for a in amounts)
        if not has_any_amount and not self._looks_like_section_header(label):
            return None

        is_total = any(kw in label_lower for kw in _TOTAL_KEYWORDS)
        indent = self._detect_indent(label)

        return PnLLineItem(
            label=label,
            amounts=amounts,
            note_ref=note_ref,
            indent_level=indent,
            is_total=is_total,
            page_number=page_number,
            raw_text=" ".join(w.get("text", "") for w in line_words),
        )

    # ------------------------------------------------------------------
    # Strategy 3: Line-by-line regex extraction (last resort)
    # ------------------------------------------------------------------

    def _extract_via_line_regex(
        self, page: Any, page_number: int
    ) -> List[PnLLineItem]:
        """
        Fallback: extract text line-by-line and use regex to split
        label from amounts.
        """
        text = page.extract_text()
        if not text:
            return []

        items: List[PnLLineItem] = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            item = self._parse_text_line(line, page_number)
            if item:
                items.append(item)

        return items

    def _parse_text_line(
        self, line: str, page_number: int
    ) -> Optional[PnLLineItem]:
        """
        Parse a single text line into a PnLLineItem.

        Typical patterns:
          "Revenue from Operations   25   1,234.56   1,100.23"
          "Total Income              1,280.23   1,139.13"
          "(a) Cost of materials consumed  26  (500.00)  (450.00)"
        """
        # Find all amount-like tokens (including negative/parenthesised)
        # Pattern matches: 1,234.56 or (1,234.56) or -1,234.56 or 1234
        amount_pattern = re.compile(
            r'[\(\-]?\d{1,3}(?:[,]\d{2,3})*(?:\.\d{1,2})?[\)]?'
        )

        # Split into potential tokens
        matches = list(amount_pattern.finditer(line))

        if not matches:
            return None

        # The label is everything before the first amount
        # Heuristic: real financial amounts contain commas or decimal points,
        # or are at least 4 digits (to exclude years like "2024" or note refs)
        real_amounts: List[re.Match] = []
        for m in matches:
            val_text = m.group()
            clean = val_text.replace("(", "").replace(")", "").replace("-", "").replace(",", "")
            if "," in val_text or "." in val_text or len(clean) >= 4:
                real_amounts.append(m)

        if not real_amounts:
            return None

        # Label ends at the first real amount
        label_end = real_amounts[0].start()
        label = line[:label_end].strip()

        # Remove trailing note reference from label
        note_ref = None
        note_match = re.search(r'\s+(\d{1,3}[a-z]?)\s*$', label)
        if note_match:
            note_ref = note_match.group(1)
            label = label[:note_match.start()].strip()

        if not label or len(label) < 2:
            return None

        # Skip non-line-item labels
        label_lower = label.lower()
        skip_patterns = [
            r'^page\s+\d+',
            r'^note\s+no',
            r'^sl\.?\s*no',
            r'^sr\.?\s*no',
            r'^particulars\s*$',
            r'^\(?\s*₹',
            r'^in\s+(lakhs?|crores?)',
            r'^amount\s+in',
            r'^\d+\s*$',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, label_lower):
                return None

        # Parse amounts
        amounts: List[Optional[float]] = []
        for m in real_amounts:
            amt = self._parse_financial_amount(m.group())
            amounts.append(amt)

        has_any = any(a is not None for a in amounts)
        if not has_any and not self._looks_like_section_header(label):
            return None

        is_total = any(kw in label_lower for kw in _TOTAL_KEYWORDS)
        indent = self._detect_indent(label)

        return PnLLineItem(
            label=label,
            amounts=amounts,
            note_ref=note_ref,
            indent_level=indent,
            is_total=is_total,
            page_number=page_number,
            raw_text=line,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(cell: Optional[str]) -> str:
        """Clean cell text: strip, collapse whitespace, remove CID placeholders."""
        if cell is None:
            return ""
        text = str(cell).strip()
        # Remove PDF CID placeholders (e.g. (cid:10) = newline)
        text = re.sub(r'\(cid:\d+\)', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def _looks_like_amount(text: str) -> bool:
        """Check if text looks like a financial amount."""
        if not text:
            return False
        text = text.strip()
        # Matches: 1,234.56 or (1,234.56) or -1,234.56 or 1234.56 or 1,23,456.78
        return bool(re.match(
            r'^[\(\-]?\d{1,3}(?:[,]\d{2,3})*(?:\.\d{1,2})?[\)]?$',
            text.replace(" ", ""),
        ))

    @staticmethod
    def _parse_financial_amount(text: str) -> Optional[float]:
        """
        Parse a financial amount string, handling:
        - Indian format: 1,23,456.78
        - Parentheses for negatives: (1,234.56)
        - Hyphens/dashes for nil: - or --
        """
        if not text:
            return None

        text = text.strip()

        # Nil indicators
        if text in ("-", "--", "–", "—", "nil", "Nil", "NIL", ""):
            return None

        # Check for negative (parentheses)
        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative = True
            text = text[1:-1]
        elif text.startswith("-"):
            negative = True
            text = text[1:]

        # Remove commas and spaces
        text = text.replace(",", "").replace(" ", "")

        if not text:
            return None

        try:
            value = float(text)
            return -value if negative else value
        except ValueError:
            return None

    @staticmethod
    def _looks_like_section_header(label: str) -> bool:
        """Check if a label looks like a P&L section header."""
        label_lower = label.lower().strip()
        section_keywords = [
            "income", "revenue", "expenses", "expenditure",
            "continuing operations", "discontinued operations",
            "other comprehensive", "items that will",
            "items that may", "i.", "ii.", "iii.", "iv.", "v.",
            "a.", "b.", "c.", "d.",
        ]
        return any(kw in label_lower for kw in section_keywords)

    @staticmethod
    def _detect_indent(label: str) -> int:
        """Detect indentation level from label formatting."""
        label_stripped = label.lstrip()
        leading_spaces = len(label) - len(label_stripped)

        # Explicit indent markers
        if label_stripped.startswith(("(a)", "(b)", "(c)", "(d)", "(i)", "(ii)")):
            return 2
        if re.match(r'^[a-z]\)', label_stripped):
            return 2
        if re.match(r'^[ivxIVX]+[\.\)]', label_stripped):
            return 2

        # Space-based indent
        if leading_spaces >= 8:
            return 2
        elif leading_spaces >= 4:
            return 1

        return 0


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ExtractionError(Exception):
    """Raised when P&L extraction fails."""
    pass
