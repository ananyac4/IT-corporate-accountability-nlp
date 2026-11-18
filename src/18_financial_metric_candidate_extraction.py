"""
18_financial_metric_candidate_extraction.py

Identify possible financial metric mentions in extracted financial-report text.

Input:
    data/processed/financial_report_text.csv
    (created by Script 17)

Outputs:
    data/processed/financial_metric_candidates.csv
    outputs/financial_metric_candidate_summary.txt

This is a candidate-generation script, not a final financial-data extractor.
It preserves the source filename and page-independent text context.
Every candidate must be checked against the original PDF before use.
"""

from pathlib import Path
import csv
import re
from collections import Counter
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT_ROOT / "data" / "processed" / "financial_report_text.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "processed" / "financial_metric_candidates.csv"
SUMMARY_TXT = PROJECT_ROOT / "outputs" / "financial_metric_candidate_summary.txt"

# Match metric terms, then retain the surrounding line as evidence.
METRIC_PATTERNS = {
    "REVENUE": re.compile(
        r"\b(total\s+)?(revenue|revenues|revenue from operations|"
        r"revenue from operation|operating revenue|net sales|gross sales)\b",
        re.IGNORECASE,
    ),
    "REVENUE_GROWTH": re.compile(
        r"\b(revenue growth|sales growth|growth in revenue|"
        r"year[- ]on[- ]year growth|yoy growth|y-o-y growth)\b",
        re.IGNORECASE,
    ),
    "EBITDA": re.compile(r"\b(EBITDA|earnings before interest,? taxes,? depreciation and amorti[sz]ation)\b", re.IGNORECASE),
    "EBIT": re.compile(r"\b(EBIT|earnings before interest and taxes|operating profit)\b", re.IGNORECASE),
    "OPERATING_MARGIN": re.compile(
        r"\b(operating margin|EBIT margin|operating profit margin)\b", re.IGNORECASE
    ),
    "PAT_NET_PROFIT": re.compile(
        r"\b(PAT|profit after tax|net profit|net income)\b", re.IGNORECASE
    ),
    "GROSS_MARGIN": re.compile(r"\b(gross margin|gross profit margin)\b", re.IGNORECASE),
    "CASH_FLOW": re.compile(
        r"\b(operating cash flow|cash flow from operations|free cash flow|FCF)\b",
        re.IGNORECASE,
    ),
    "ORDER_BOOK": re.compile(r"\b(order book|order backlog|deal wins|large deal wins)\b", re.IGNORECASE),
}

# Numeric tokens are retained as text to avoid silently changing units or signs.
NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?\s*"
    r"(?:%|percent|bps|basis points|million|mn|billion|bn|crore|lakhs?|lakh)?",
    re.IGNORECASE,
)

UNIT_PATTERN = re.compile(
    r"\b(INR|Rs\.?|₹|USD|US\$|EUR|GBP|million|mn|billion|bn|crore|lakh|lakhs)\b",
    re.IGNORECASE,
)

FY_QUARTER_PATTERN = re.compile(r"\bFY\s?20\d{2}\s?[-/]?\s?Q[1-4]\b|\bQ[1-4]\s?FY\s?20\d{2}\b", re.IGNORECASE)


def normalize_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def split_into_evidence_units(text):
    """
    Split on newlines and sentence endings. Financial tables are often
    line-oriented, so individual lines are retained as evidence units.
    """
    units = []
    for line in (text or "").replace("\r", "\n").split("\n"):
        line = normalize_space(line)
        if not line:
            continue
        # Keep the original line intact where possible; also split long prose.
        if len(line) > 1200:
            parts = re.split(r"(?<=[.!?])\s+", line)
            units.extend(part.strip() for part in parts if part.strip())
        else:
            units.append(line)
    return units


def get_numbers(text):
    found = []
    for match in NUMBER_PATTERN.finditer(text):
        token = normalize_space(match.group(0))
        if token and re.search(r"\d", token):
            found.append(token)
    # Preserve order but remove exact repeated tokens in the same evidence line.
    return list(dict.fromkeys(found))


def classify_period(text, fallback):
    match = FY_QUARTER_PATTERN.search(text or "")
    if match:
        return normalize_space(match.group(0)).upper().replace(" ", "")
    return fallback


def main():
    if not INPUT_CSV.exists():
        raise SystemExit(
            f"Input not found: {INPUT_CSV}\n"
            "Run Script 17 successfully before running Script 18."
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_TXT.parent.mkdir(parents=True, exist_ok=True)

    candidates = []
    source_files = 0
    missing_text_files = 0
    excluded_duplicates = 0
    metric_counts = Counter()
    candidate_file_count = set()

    with INPUT_CSV.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"ticker", "filename_quarter", "filename", "extracted_text"}
        missing_columns = required - set(reader.fieldnames or [])
        if missing_columns:
            raise SystemExit(
                "Script 17 output is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            source_files += 1
            filename = row.get("filename", "")
            ticker = row.get("ticker", "")
            filename_quarter = row.get("filename_quarter", "")
            verified_quarter = row.get("verified_quarter", "") or filename_quarter
            text = row.get("extracted_text", "") or ""

            include_value = (row.get("include_in_analysis", "True") or "True").strip().lower()
            if include_value in {"false", "0", "no"}:
                excluded_duplicates += 1
                continue

            if not text.strip():
                missing_text_files += 1
                continue

            for evidence_index, evidence in enumerate(split_into_evidence_units(text), start=1):
                matched_categories = []
                for category, pattern in METRIC_PATTERNS.items():
                    if pattern.search(evidence):
                        matched_categories.append(category)

                if not matched_categories:
                    continue

                numbers = get_numbers(evidence)
                unit_matches = list(dict.fromkeys(
                    match.group(0) for match in UNIT_PATTERN.finditer(evidence)
                ))

                for category in matched_categories:
                    candidates.append({
                        "ticker": ticker,
                        "filename_quarter": filename_quarter,
                        "verified_quarter_from_script17": verified_quarter,
                        "period_mention_in_text": classify_period(evidence, ""),
                        "metric_category": category,
                        "numeric_tokens": " | ".join(numbers),
                        "unit_tokens": " | ".join(unit_matches),
                        "has_numeric_value": bool(numbers),
                        "source_filename": filename,
                        "source_sha256": row.get("sha256", ""),
                        "verification_status_from_script17": row.get("verification_status", ""),
                        "include_in_analysis_from_script17": row.get("include_in_analysis", ""),
                        "evidence_unit_number": evidence_index,
                        "evidence_text": evidence,
                        "review_status": "NOT_REVIEWED",
                        "review_notes": "",
                    })
                    metric_counts[category] += 1
                    candidate_file_count.add(filename)

    fieldnames = [
        "ticker", "filename_quarter", "verified_quarter_from_script17",
        "period_mention_in_text", "metric_category", "numeric_tokens",
        "unit_tokens", "has_numeric_value", "source_filename", "source_sha256",
        "verification_status_from_script17", "include_in_analysis_from_script17",
        "evidence_unit_number", "evidence_text", "review_status", "review_notes",
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)

    summary = [
        "FINANCIAL METRIC CANDIDATE EXTRACTION SUMMARY",
        f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input file: {INPUT_CSV}",
        "",
        f"Source PDF records read: {source_files}",
        f"Source files excluded by Script 17 duplicate flag: {excluded_duplicates}",
        f"Files with no extracted text: {missing_text_files}",
        f"Files contributing at least one candidate: {len(candidate_file_count)}",
        f"Total candidate rows: {len(candidates)}",
        "",
        "CANDIDATES BY METRIC CATEGORY",
    ]

    if metric_counts:
        for category, count in metric_counts.most_common():
            summary.append(f"{category}: {count}")
    else:
        summary.append("No metric candidates found.")

    summary.extend([
        "",
        "IMPORTANT LIMITATIONS",
        "- These are keyword-based candidate mentions, not verified financial values.",
        "- Numeric tokens may include dates, page numbers, table references or unrelated values.",
        "- Values may be in INR, USD, millions, crores, percentages or other units.",
        "- A metric label does not guarantee that the adjacent number belongs to that metric.",
        "- Revenue, EBITDA, EBIT, operating profit and margins must not be treated as interchangeable.",
        "- Reporting period and fiscal-quarter labels must be checked against the PDF.",
        "- Rows are marked NOT_REVIEWED; verify every value against its source page before analysis.",
        "",
        f"Candidate CSV: {OUTPUT_CSV}",
        f"Summary: {SUMMARY_TXT}",
    ])

    SUMMARY_TXT.write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    print("\nScript 18 completed successfully.")


if __name__ == "__main__":
    main()
