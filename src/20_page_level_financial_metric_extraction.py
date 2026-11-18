"""
SCRIPT 20: PAGE-LEVEL FINANCIAL METRIC CANDIDATE EXTRACTION

Purpose
-------
Extract metric mentions from the page-level financial report text produced by
Script 17. Each candidate retains its source PDF filename and PDF page number.

This is a candidate-generation tool only. It does NOT verify financial values,
infer missing values, or calculate financial actuals.

Inputs
------
data/processed/financial_report_page_text.csv
data/processed/financial_report_text.csv  (used for duplicate/inclusion metadata)

Outputs
-------
data/processed/financial_metric_page_candidates.csv
outputs/financial_metric_page_candidate_summary.txt

Run from the project root:
    python src/20_page_level_financial_metric_extraction.py
"""

from pathlib import Path
from datetime import datetime
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PAGE_INPUT = ROOT / "data" / "processed" / "financial_report_page_text.csv"
FILE_INPUT = ROOT / "data" / "processed" / "financial_report_text.csv"

OUTPUT_DIR = ROOT / "data" / "processed"
SUMMARY_DIR = ROOT / "outputs"
OUTPUT_CSV = OUTPUT_DIR / "financial_metric_page_candidates.csv"
SUMMARY_TXT = SUMMARY_DIR / "financial_metric_page_candidate_summary.txt"

# Metric patterns are deliberately explicit. A match is a mention to review,
# not proof that a nearby number is the correct reported value.
METRIC_PATTERNS = {
    "REVENUE_GROWTH": [
        r"\brevenue\s+(?:growth|increase|decline|de-growth)\b",
        r"\b(?:growth|increase|decline|de-growth)\s+in\s+revenue\b",
        r"\b(?:constant\s+currency|cc)\s+(?:revenue\s+)?growth\b",
        r"\bYoY\s+revenue\b",
    ],
    "REVENUE": [
        r"\btotal\s+revenue\b",
        r"\brevenue\s+from\s+operations\b",
        r"\brevenue\b",
        r"\bturnover\b",
    ],
    "EBITDA": [r"\bEBITDA\b", r"\bEBITDA\s+margin\b"],
    "EBIT": [r"\bEBIT\b", r"\bEBIT\s+margin\b"],
    "OPERATING_MARGIN": [
        r"\boperating\s+margin\b",
        r"\boperating\s+profit\s+margin\b",
        r"\boperating\s+profit\b",
    ],
    "PAT_NET_PROFIT": [
        r"\bprofit\s+after\s+tax\b",
        r"\bPAT\b",
        r"\bnet\s+profit\b",
        r"\bprofit\s+for\s+the\s+period\b",
    ],
    "GROSS_MARGIN": [r"\bgross\s+margin\b", r"\bgross\s+profit\b"],
    "CASH_FLOW": [
        r"\bfree\s+cash\s+flow\b",
        r"\boperating\s+cash\s+flow\b",
        r"\bcash\s+flow\b",
    ],
    "ORDER_BOOK": [
        r"\border\s+book\b",
        r"\bdeal\s+pipeline\b",
        r"\btotal\s+contract\s+value\b",
        r"\bTCV\b",
    ],
}

# Capture number-like tokens only as review aids; these are not automatically
# associated with the metric.
NUMBER_RE = re.compile(
    r"(?<![A-Za-z])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?\s*%?"
)

COLUMN_ALIASES = {
    "filename": ["filename", "source_filename", "file_name", "pdf_filename"],
    "ticker": ["ticker", "company", "symbol"],
    "quarter": ["filename_quarter", "quarter_key", "quarter", "financial_quarter"],
    "fy": ["fy", "financial_year", "fiscal_year"],
    "page": ["page_number", "page_no", "page", "pdf_page", "page_num"],
    "text": ["page_text", "extracted_text", "text", "content"],
}


def find_column(df, logical_name, required=True):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for alias in COLUMN_ALIASES[logical_name]:
        if alias in lower_map:
            return lower_map[alias]
    if required:
        raise ValueError(
            f"Could not identify the '{logical_name}' column. "
            f"Available columns: {list(df.columns)}"
        )
    return None


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).encode("utf-8", errors="replace").decode("utf-8").strip()


def parse_filename(filename):
    name = Path(str(filename)).stem
    match = re.match(
        r"^(?P<ticker>[A-Z0-9]+)_(?P<fy>FY\d{2})_(?P<quarter>Q[1-4])_",
        name,
        flags=re.IGNORECASE,
    )
    if not match:
        return "", "", ""
    ticker = match.group("ticker").upper()
    fy = match.group("fy").upper()
    quarter = match.group("quarter").upper()
    return ticker, fy, f"{fy}_{quarter}"


def get_metadata_map():
    if not FILE_INPUT.exists():
        return {}
    try:
        meta = pd.read_csv(FILE_INPUT, dtype=str, keep_default_na=False)
    except Exception as exc:
        print(f"WARNING: Could not read file-level metadata: {exc}")
        return {}

    filename_col = find_column(meta, "filename", required=False)
    if not filename_col:
        return {}

    mapping = {}
    for _, row in meta.iterrows():
        filename = clean_text(row.get(filename_col, ""))
        if not filename:
            continue
        include_raw = clean_text(row.get("include_in_analysis", "True")).lower()
        include = include_raw not in {"false", "0", "no", "n"}
        mapping[filename] = {
            "include_in_analysis": include,
            "sha256": clean_text(row.get("sha256", "")),
            "verification_status": clean_text(row.get("verification_status", "")),
            "verified_quarter": clean_text(row.get("verified_quarter", "")),
        }
    return mapping


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    if not PAGE_INPUT.exists():
        raise FileNotFoundError(f"Page-level input not found: {PAGE_INPUT}")

    pages = pd.read_csv(PAGE_INPUT, dtype=str, keep_default_na=False)
    if pages.empty:
        raise ValueError("The page-level input CSV contains no rows.")

    filename_col = find_column(pages, "filename")
    page_col = find_column(pages, "page")
    text_col = find_column(pages, "text")
    ticker_col = find_column(pages, "ticker", required=False)
    quarter_col = find_column(pages, "quarter", required=False)
    fy_col = find_column(pages, "fy", required=False)

    metadata = get_metadata_map()

    candidates = []
    excluded_files = set()
    files_seen = set()
    files_with_candidates = set()
    empty_page_rows = 0

    for _, row in pages.iterrows():
        filename = clean_text(row.get(filename_col, ""))
        if not filename:
            continue

        files_seen.add(filename)
        file_meta = metadata.get(filename, {})
        if file_meta and not file_meta.get("include_in_analysis", True):
            excluded_files.add(filename)
            continue

        page_text = clean_text(row.get(text_col, ""))
        if not page_text:
            empty_page_rows += 1
            continue

        parsed_ticker, parsed_fy, parsed_quarter = parse_filename(filename)
        ticker = clean_text(row.get(ticker_col, "")) if ticker_col else ""
        fy = clean_text(row.get(fy_col, "")) if fy_col else ""
        quarter_key = clean_text(row.get(quarter_col, "")) if quarter_col else ""

        ticker = ticker or parsed_ticker
        fy = fy or parsed_fy
        quarter_key = quarter_key or parsed_quarter

        page_number = clean_text(row.get(page_col, ""))
        # Preserve the source's page value exactly; do not confuse PDF page
        # sequence with printed page labels.
        for line_number, raw_line in enumerate(page_text.splitlines(), start=1):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue

            matched_categories = []
            for category, patterns in METRIC_PATTERNS.items():
                if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns):
                    matched_categories.append(category)

            if not matched_categories:
                continue

            numbers = NUMBER_RE.findall(line)
            context = line[:1200]
            for category in matched_categories:
                candidates.append({
                    "ticker": ticker,
                    "quarter_key": quarter_key,
                    "financial_year": fy,
                    "source_filename": filename,
                    "source_pdf_page": page_number,
                    "source_line_number": line_number,
                    "metric_category": category,
                    "evidence_text": context,
                    "numeric_tokens_on_line": " | ".join(n.strip() for n in numbers),
                    "sha256": file_meta.get("sha256", ""),
                    "verification_status": file_meta.get("verification_status", ""),
                    "verified_quarter_from_metadata": file_meta.get("verified_quarter", ""),
                    "review_status": "NOT_VERIFIED",
                    "reviewed_value": "",
                    "reviewed_unit": "",
                    "period_basis": "",
                    "reviewer_notes": "",
                })
                files_with_candidates.add(filename)

    output = pd.DataFrame(candidates)
    columns = [
        "ticker", "quarter_key", "financial_year", "source_filename",
        "source_pdf_page", "source_line_number", "metric_category",
        "evidence_text", "numeric_tokens_on_line", "sha256",
        "verification_status", "verified_quarter_from_metadata",
        "review_status", "reviewed_value", "reviewed_unit",
        "period_basis", "reviewer_notes",
    ]
    if output.empty:
        output = pd.DataFrame(columns=columns)
    else:
        output = output.reindex(columns=columns)

    output.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    counts = output["metric_category"].value_counts().to_dict() if not output.empty else {}
    lines = [
        "PAGE-LEVEL FINANCIAL METRIC CANDIDATE EXTRACTION SUMMARY",
        f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input file: {PAGE_INPUT}",
        "",
        f"Page-level rows read: {len(pages)}",
        f"Unique source PDFs seen: {len(files_seen)}",
        f"Source PDFs excluded by Script 17 inclusion flag: {len(excluded_files)}",
        f"Page rows with no extracted text: {empty_page_rows}",
        f"Files contributing at least one candidate: {len(files_with_candidates)}",
        f"Total page-level candidate rows: {len(output)}",
        "",
        "CANDIDATES BY METRIC CATEGORY",
    ]
    for category in METRIC_PATTERNS:
        lines.append(f"{category}: {counts.get(category, 0)}")

    lines += [
        "",
        "IMPORTANT LIMITATIONS",
        "- These are page-level keyword matches, not verified financial values.",
        "- Numeric tokens are shown only as review aids; they may be unrelated to the metric.",
        "- Each source_pdf_page is the PDF page sequence supplied by Script 17, not necessarily the printed page label.",
        "- Check reporting period, standalone-quarter versus YTD basis, currency, units and consolidation basis in the PDF.",
        "- Do not treat revenue, EBITDA, EBIT, operating profit or their margins as interchangeable.",
        "- All rows remain NOT_VERIFIED until manually checked against the original PDF.",
        "",
        f"Candidate CSV: {OUTPUT_CSV}",
        f"Summary: {SUMMARY_TXT}",
        "",
        "Script 20 completed successfully.",
    ]
    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("No source PDFs or existing Script 17-19 outputs were modified.")
        sys.exit(1)
