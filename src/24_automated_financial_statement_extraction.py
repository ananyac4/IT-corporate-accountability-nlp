"""
SCRIPT 24: AUTOMATED FINANCIAL STATEMENT EXTRACTION
=================================================

Purpose
-------
Extract structured financial actual candidates from the existing page-level
financial report text corpus. This script does NOT claim that machine-extracted
values are fully verified. It assigns confidence and routes ambiguous evidence
to a review queue.

Inputs
------
data/processed/financial_report_page_text.csv
data/processed/financial_report_text.csv   (optional metadata)

Outputs
-------
data/processed/financial_actuals_auto_extracted.csv
data/processed/financial_actuals_auto_review.csv
data/processed/financial_actuals_extraction_errors.csv
outputs/financial_actuals_extraction_summary.txt

Run from project root:
    python src/24_automated_financial_statement_extraction.py

Dependencies:
    pandas
    numpy
"""

from __future__ import annotations

import re
import sys
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAGE_FILE = ROOT / "data" / "processed" / "financial_report_page_text.csv"
META_FILE = ROOT / "data" / "processed" / "financial_report_text.csv"

OUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs"

OUT_AUTO = OUT_DIR / "financial_actuals_auto_extracted.csv"
OUT_REVIEW = OUT_DIR / "financial_actuals_auto_review.csv"
OUT_ERRORS = OUT_DIR / "financial_actuals_extraction_errors.csv"
OUT_SUMMARY = REPORT_DIR / "financial_actuals_extraction_summary.txt"

# Canonical metric patterns. More specific labels are checked before broad ones.
METRICS = [
    ("REVENUE", r"\b(revenue from operations|total revenue|revenue)\b", "currency"),
    ("EBITDA_MARGIN", r"\b(ebitda margin)\b", "percent"),
    ("EBITDA", r"\b(ebitda)\b", "currency"),
    ("EBIT_MARGIN", r"\b(ebit margin|ebit margin %)\b", "percent"),
    ("EBIT", r"\b(ebit)\b", "currency"),
    ("OPERATING_MARGIN", r"\b(operating profit margin|operating margin)\b", "percent"),
    ("OPERATING_INCOME", r"\b(operating income)\b", "currency"),
    ("PAT_MARGIN", r"\b(pat margin|net profit margin)\b", "percent"),
    ("PAT_NET_PROFIT", r"\b(profit for the period|profit after tax|pat|net profit)\b", "currency"),
    ("PBT", r"\b(profit before tax|pbt)\b", "currency"),
    ("REVENUE_GROWTH", r"\b(revenue growth|revenue.*growth)\b", "growth"),
    ("OPERATING_CASH_FLOW", r"\b(cash generated from operations|net cash flow from operating activities|operating cash flow)\b", "currency"),
    ("TOTAL_ASSETS", r"\btotal assets\b", "currency"),
    ("TOTAL_EQUITY_LIABILITIES", r"\btotal equity and liabilities\b", "currency"),
]

# Numeric tokens; supports comma separators, decimals, negatives and parentheses.
NUM_RE = re.compile(r"(?<![A-Za-z])\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?\)?|\(?-?\d+(?:\.\d+)?%?\)?")

def norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")

def find_col(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    lookup = {norm_col(c): c for c in df.columns}
    for alias in aliases:
        if norm_col(alias) in lookup:
            return lookup[norm_col(alias)]
    # partial match fallback
    for alias in aliases:
        a = norm_col(alias)
        for k, original in lookup.items():
            if a in k or k in a:
                return original
    return None

def safe_str(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).replace("\x00", " ").strip()

def parse_number(token: str) -> Optional[float]:
    t = token.strip().replace(",", "")
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    t = t.replace("%", "")
    try:
        value = float(t)
        return -value if negative else value
    except ValueError:
        return None

def detect_unit(text: str, filename: str = "") -> str:
    s = (text + " " + filename).lower()
    if re.search(r"\b(inr|₹|rs\.?|rupees?)\b", s):
        return "INR"
    if re.search(r"\b(usd|us\$|\$|in \$ m)\b", s):
        return "USD"
    if re.search(r"\b(eur|€)\b", s):
        return "EUR"
    if re.search(r"\b(gbp|£)\b", s):
        return "GBP"
    return "UNKNOWN_CURRENCY"

def detect_scale(text: str) -> str:
    s = text.lower()
    if re.search(r"\b(billion|bn)\b", s):
        return "BILLION"
    if re.search(r"\b(million|mn|inr m|₹ m|\$ m)\b", s):
        return "MILLION"
    if re.search(r"\b(thousand|'000)\b", s):
        return "THOUSAND"
    if re.search(r"\b(crore|cr)\b", s):
        return "CRORE"
    return "UNSPECIFIED"

def detect_period_basis(text: str) -> str:
    s = text.lower()
    if re.search(r"\bytd\b|year to date|six months ended|nine months ended", s):
        return "YTD"
    if re.search(r"\byear ended|full year|annual", s):
        return "ANNUAL"
    if re.search(r"\bquarter ended\b|quarterly|three months ended", s):
        return "QUARTER"
    return "UNKNOWN"

def detect_growth_type(text: str) -> str:
    s = text.lower()
    if "yoy" in s or "year-on-year" in s or "year on year" in s:
        return "YOY"
    if "qoq" in s or "quarter-on-quarter" in s or "quarter on quarter" in s:
        return "QOQ"
    return "UNSPECIFIED"

def detect_quarter_from_text(text: str, filename: str) -> str:
    combined = f"{filename} {text}".upper()
    # Prefer filename keys to avoid accidentally taking comparative periods.
    m = re.search(r"\bFY\s?(\d{2})[_ -]?Q([1-4])\b", filename.upper())
    if m:
        return f"FY{m.group(1)}_Q{m.group(2)}"
    m = re.search(r"\bQ([1-4])\s*FY\s*['’]?(\d{2,4})\b", combined)
    if m:
        fy = m.group(2)[-2:]
        return f"FY{fy}_Q{m.group(1)}"
    m = re.search(r"\bFY\s?(\d{2})[_ -]?Q([1-4])\b", combined)
    if m:
        return f"FY{m.group(1)}_Q{m.group(2)}"
    return ""

def detect_ticker(filename: str, row: pd.Series) -> str:
    # Filename convention from the project: TICKER_FYxx_Qx_financial_report.pdf
    stem = Path(filename).stem
    m = re.match(r"([A-Z0-9]+)_FY\d{2}_Q[1-4]", stem.upper())
    if m:
        return m.group(1)
    for col in row.index:
        if norm_col(col) in {"ticker", "company", "symbol"}:
            value = safe_str(row[col]).upper()
            if value:
                return value
    return ""

def get_numeric_tokens(text: str) -> list[float]:
    vals = []
    for token in NUM_RE.findall(text):
        v = parse_number(token)
        if v is not None:
            vals.append(v)
    return vals

def metric_matches(line: str):
    low = line.lower()
    found = []
    for metric, pattern, kind in METRICS:
        if re.search(pattern, low, flags=re.I):
            found.append((metric, kind))
    # Avoid double tagging a specific metric as a broad metric.
    if any(m == "EBITDA_MARGIN" for m, _ in found):
        found = [(m, k) for m, k in found if m != "EBITDA"]
    if any(m == "EBIT_MARGIN" for m, _ in found):
        found = [(m, k) for m, k in found if m != "EBIT"]
    if any(m == "PAT_MARGIN" for m, _ in found):
        found = [(m, k) for m, k in found if m != "PAT_NET_PROFIT"]
    return found

def infer_confidence(metric: str, values: list[float], line: str,
                     unit: str, scale: str, basis: str, quarter: str) -> tuple[str, int, str]:
    score = 0
    reasons = []
    if values:
        score += 20
        reasons.append("numeric_values_present")
    if len(values) >= 3:
        score += 15
        reasons.append("multiple_period_values")
    if len(values) >= 5:
        score += 5
    if unit != "UNKNOWN_CURRENCY" or metric.endswith("MARGIN") or metric == "REVENUE_GROWTH":
        score += 10
        reasons.append("unit_or_percentage_identified")
    if scale != "UNSPECIFIED" or metric.endswith("MARGIN") or metric == "REVENUE_GROWTH":
        score += 10
        reasons.append("scale_identified_or_not_required")
    if basis != "UNKNOWN":
        score += 15
        reasons.append("period_basis_identified")
    if quarter:
        score += 15
        reasons.append("company_quarter_identified")
    if len(line) >= 18:
        score += 5
    if re.search(r"\b(qoq|yoy|bps)\b", line, re.I):
        score += 5
        reasons.append("growth_or_basis_context")
    if len(values) > 8:
        score -= 10
        reasons.append("many_numeric_tokens_ambiguous")
    if unit == "UNKNOWN_CURRENCY" and metric not in {"EBIT_MARGIN", "EBITDA_MARGIN", "PAT_MARGIN", "OPERATING_MARGIN", "REVENUE_GROWTH"}:
        score -= 10
    score = max(0, min(100, score))
    if score >= 75:
        level = "HIGH"
    elif score >= 50:
        level = "MEDIUM"
    else:
        level = "LOW"
    return level, score, ";".join(reasons)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not PAGE_FILE.exists():
        print(f"ERROR: Missing input file: {PAGE_FILE}")
        print("Run Script 17 first to create financial_report_page_text.csv.")
        sys.exit(1)

    pages = pd.read_csv(PAGE_FILE, low_memory=False)
    if pages.empty:
        print("ERROR: Page-level text input is empty.")
        sys.exit(1)

    # Flexible schema detection for Script 17 output.
    text_col = find_col(pages, ["page_text", "text", "extracted_text", "content"])
    file_col = find_col(pages, ["source_filename", "filename", "source_file", "pdf_filename", "file_name"])
    page_col = find_col(pages, ["source_pdf_page", "pdf_page", "page_number", "page_num", "page"])
    if not text_col or not file_col:
        print("ERROR: Could not identify required text/filename columns.")
        print("Detected columns:", pages.columns.tolist())
        print("Expected aliases for text: page_text/text/extracted_text/content")
        print("Expected aliases for filename: source_filename/filename/source_file/pdf_filename")
        sys.exit(1)

    # Optional metadata merge, if available.
    metadata = {}
    if META_FILE.exists():
        try:
            meta = pd.read_csv(META_FILE, low_memory=False)
            meta_file_col = find_col(meta, ["source_filename", "filename", "source_file", "pdf_filename", "file_name"])
            if meta_file_col:
                metadata = {safe_str(r[meta_file_col]): r.to_dict() for _, r in meta.iterrows()}
        except Exception:
            metadata = {}

    extracted, review, errors = [], [], []
    pages_scanned = 0
    metric_counts = {}

    for idx, row in pages.iterrows():
        try:
            filename = safe_str(row[file_col])
            page_text = safe_str(row[text_col])
            if not filename or not page_text:
                continue
            pages_scanned += 1
            page_num = safe_str(row[page_col]) if page_col else ""
            ticker = detect_ticker(filename, row)
            quarter = detect_quarter_from_text("", filename)
            if not quarter:
                quarter = detect_quarter_from_text(page_text[:1500], filename)
            meta_row = metadata.get(filename, {})
            if not ticker:
                for k, v in meta_row.items():
                    if norm_col(k) in {"ticker", "company", "symbol"} and safe_str(v):
                        ticker = safe_str(v).upper()
                        break
            if not quarter:
                for k, v in meta_row.items():
                    if norm_col(k) in {"quarter_key", "quarter", "period"} and safe_str(v):
                        quarter = safe_str(v)
                        break

            # Split into lines, but keep table rows intact.
            lines = [re.sub(r"\s+", " ", x).strip(" \t|") for x in page_text.splitlines()]
            lines = [x for x in lines if x]
            for line_no, line in enumerate(lines, start=1):
                matches = metric_matches(line)
                if not matches:
                    continue
                values = get_numeric_tokens(line)
                if not values:
                    continue

                # Determine contextual metadata from the page and line.
                context = page_text[:2500] + " " + line
                unit = "PERCENT" if any(k in {"percent", "growth"} for _, k in matches) else detect_unit(context, filename)
                scale = "NOT_APPLICABLE" if unit == "PERCENT" else detect_scale(context)
                basis = detect_period_basis(context)
                growth_type = detect_growth_type(line)
                for metric, kind in matches:
                    level, score, reasons = infer_confidence(
                        metric, values, line, unit, scale, basis, quarter
                    )
                    row_id = hashlib.sha1(
                        f"{filename}|{page_num}|{line_no}|{metric}|{line}".encode("utf-8", "ignore")
                    ).hexdigest()[:16]
                    record = {
                        "record_id": row_id,
                        "ticker": ticker,
                        "quarter_key": quarter,
                        "metric_category": metric,
                        "candidate_values": " | ".join(str(v) for v in values),
                        "candidate_value_count": len(values),
                        "unit_currency": unit,
                        "unit_scale": scale,
                        "growth_type": growth_type if metric == "REVENUE_GROWTH" else "",
                        "period_basis": basis,
                        "source_filename": filename,
                        "source_pdf_page": page_num,
                        "source_line_number": line_no,
                        "evidence_text": line,
                        "confidence_level": level,
                        "confidence_score": score,
                        "confidence_reasons": reasons,
                        "validation_status": "NOT_YET_VALIDATED",
                        "review_status": "AUTO_CANDIDATE",
                    }
                    metric_counts[metric] = metric_counts.get(metric, 0) + 1

                    # A line with multiple values is not mapped to a specific quarter
                    # unless the source line explicitly has a single numeric value.
                    # Keep multi-column rows in review; do not guess column position.
                    if (level == "HIGH" and len(values) == 1 and ticker and quarter
                            and basis != "UNKNOWN"):
                        record["review_status"] = "HIGH_CONFIDENCE_CANDIDATE"
                        extracted.append(record)
                    else:
                        record["review_status"] = "REQUIRES_REVIEW"
                        review.append(record)

        except Exception as exc:
            errors.append({
                "input_row": idx,
                "source_filename": safe_str(row[file_col]) if file_col else "",
                "error": repr(exc),
            })

    auto_df = pd.DataFrame(extracted)
    review_df = pd.DataFrame(review)
    error_df = pd.DataFrame(errors)

    # Always write headers, including for empty outputs.
    columns = [
        "record_id", "ticker", "quarter_key", "metric_category",
        "candidate_values", "candidate_value_count", "unit_currency",
        "unit_scale", "growth_type", "period_basis", "source_filename",
        "source_pdf_page", "source_line_number", "evidence_text",
        "confidence_level", "confidence_score", "confidence_reasons",
        "validation_status", "review_status"
    ]
    for df, path in [(auto_df, OUT_AUTO), (review_df, OUT_REVIEW), (error_df, OUT_ERRORS)]:
        if df.empty:
            df = pd.DataFrame(columns=columns if path != OUT_ERRORS else ["input_row", "source_filename", "error"])
        df.to_csv(path, index=False, encoding="utf-8-sig")

    total_candidates = len(auto_df) + len(review_df)
    lines = [
        "SCRIPT 24: AUTOMATED FINANCIAL STATEMENT EXTRACTION",
        "=" * 62,
        f"Run timestamp: {pd.Timestamp.now()}",
        f"Input page rows: {len(pages):,}",
        f"Pages with non-empty text scanned: {pages_scanned:,}",
        f"Candidate records: {total_candidates:,}",
        f"High-confidence single-value candidates: {len(auto_df):,}",
        f"Review-queue candidates: {len(review_df):,}",
        f"Processing errors: {len(error_df):,}",
        "",
        "CANDIDATES BY METRIC",
        "-" * 30,
    ]
    for metric, count in sorted(metric_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"{metric}: {count:,}")
    lines += [
        "",
        "IMPORTANT LIMITATIONS",
        "-" * 30,
        "1. These are machine-extracted candidates, not fully verified financial actuals.",
        "2. Multi-column financial table rows are routed to review; column positions are not guessed.",
        "3. Confidence scores are heuristic and must be calibrated against a representative sample.",
        "4. Currency, scale and period-basis detection may be ambiguous when headings are on other pages.",
        "5. Standalone and consolidated statements may coexist; inspect source context before combining.",
        "6. This script does not overwrite the existing manual-review or verified datasets.",
        "",
        "OUTPUT FILES",
        "-" * 30,
        str(OUT_AUTO.relative_to(ROOT)),
        str(OUT_REVIEW.relative_to(ROOT)),
        str(OUT_ERRORS.relative_to(ROOT)),
    ]
    OUT_SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
