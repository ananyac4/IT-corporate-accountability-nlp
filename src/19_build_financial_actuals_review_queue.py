"""
19_build_financial_actuals_review_queue.py

Prepare a human-review queue from Script 18's metric candidates.

Input:
    data/processed/financial_metric_candidates.csv
    data/processed/actuals_template.csv (optional)

Outputs:
    data/processed/financial_actuals_review_queue.csv
    data/processed/financial_actuals_verified_template.csv
    outputs/financial_actuals_review_queue_summary.txt

This script does NOT convert candidate text into verified financial values.
A reviewer must inspect the original PDF and record the exact value, unit,
period, metric definition, source page and evidence before a row is verified.
"""

from pathlib import Path
import csv
from collections import Counter
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_CSV = PROJECT_ROOT / "data" / "processed" / "financial_metric_candidates.csv"
ACTUALS_TEMPLATE = PROJECT_ROOT / "data" / "processed" / "actuals_template.csv"

QUEUE_CSV = PROJECT_ROOT / "data" / "processed" / "financial_actuals_review_queue.csv"
VERIFIED_TEMPLATE_CSV = PROJECT_ROOT / "data" / "processed" / "financial_actuals_verified_template.csv"
SUMMARY_TXT = PROJECT_ROOT / "outputs" / "financial_actuals_review_queue_summary.txt"

METRIC_TO_FIELD = {
    "REVENUE": "revenue",
    "REVENUE_GROWTH": "revenue_growth",
    "EBITDA": "ebitda",
    "EBIT": "ebit_or_operating_profit",
    "OPERATING_MARGIN": "operating_margin",
    "PAT_NET_PROFIT": "pat_or_net_profit",
    "GROSS_MARGIN": "gross_margin",
    "CASH_FLOW": "cash_flow",
    "ORDER_BOOK": "order_book_or_deal_wins",
}

QUEUE_FIELDS = [
    "candidate_id",
    "ticker",
    "filename_quarter",
    "verified_quarter_from_script17",
    "period_mention_in_text",
    "metric_category",
    "suggested_metric_field",
    "numeric_tokens",
    "unit_tokens",
    "has_numeric_value",
    "source_filename",
    "source_sha256",
    "verification_status_from_script17",
    "include_in_analysis_from_script17",
    "evidence_unit_number",
    "evidence_text",
    "review_priority",
    "review_status",
    "verified_value",
    "verified_unit",
    "verified_period",
    "metric_definition",
    "source_page",
    "source_evidence",
    "reviewer_notes",
]

VERIFIED_FIELDS = [
    "ticker",
    "quarter_key",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_definition",
    "period_basis",
    "source_filename",
    "source_page",
    "source_url",
    "source_evidence",
    "verification_status",
    "reviewer_notes",
]


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def truthy(value):
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def main():
    if not CANDIDATES_CSV.exists():
        raise SystemExit(
            f"Missing input: {CANDIDATES_CSV}\n"
            "Run Script 18 successfully before running Script 19."
        )

    candidates = read_csv(CANDIDATES_CSV)
    queue = []
    counts = Counter()
    metric_counts = Counter()

    # Numeric candidates are prioritized, but non-numeric mentions are retained
    # because some qualitative metrics (e.g. order-book commentary) matter.
    for index, row in enumerate(candidates, start=1):
        include_flag = row.get("include_in_analysis_from_script17", "")
        has_numeric = truthy(row.get("has_numeric_value", ""))

        if include_flag and not truthy(include_flag):
            counts["excluded_duplicate_candidates"] += 1
            continue

        category = row.get("metric_category", "")
        priority = "P1_NUMERIC_REVIEW" if has_numeric else "P2_CONTEXT_REVIEW"

        queue.append({
            "candidate_id": f"FC{index:07d}",
            "ticker": row.get("ticker", ""),
            "filename_quarter": row.get("filename_quarter", ""),
            "verified_quarter_from_script17": row.get("verified_quarter_from_script17", ""),
            "period_mention_in_text": row.get("period_mention_in_text", ""),
            "metric_category": category,
            "suggested_metric_field": METRIC_TO_FIELD.get(category, "manual_classification"),
            "numeric_tokens": row.get("numeric_tokens", ""),
            "unit_tokens": row.get("unit_tokens", ""),
            "has_numeric_value": has_numeric,
            "source_filename": row.get("source_filename", ""),
            "source_sha256": row.get("source_sha256", ""),
            "verification_status_from_script17": row.get("verification_status_from_script17", ""),
            "include_in_analysis_from_script17": include_flag,
            "evidence_unit_number": row.get("evidence_unit_number", ""),
            "evidence_text": row.get("evidence_text", ""),
            "review_priority": priority,
            "review_status": "NOT_REVIEWED",
            "verified_value": "",
            "verified_unit": "",
            "verified_period": "",
            "metric_definition": "",
            "source_page": "",
            "source_evidence": "",
            "reviewer_notes": "",
        })
        counts[priority] += 1
        metric_counts[category] += 1

    # Sort so numeric evidence is reviewed first, while preserving a stable order.
    queue.sort(key=lambda row: (
        0 if row["review_priority"] == "P1_NUMERIC_REVIEW" else 1,
        row["ticker"],
        row["filename_quarter"],
        row["metric_category"],
        row["source_filename"],
        int(row["evidence_unit_number"] or 0),
    ))

    write_csv(QUEUE_CSV, QUEUE_FIELDS, queue)

    # A clean, empty verified dataset schema. Do not populate it automatically:
    # only reviewed source evidence belongs here.
    verified_rows = []
    if ACTUALS_TEMPLATE.exists():
        for row in read_csv(ACTUALS_TEMPLATE):
            verified_rows.append({
                "ticker": row.get("ticker", ""),
                "quarter_key": row.get("quarter_key", ""),
                "metric_name": "",
                "metric_value": "",
                "metric_unit": "",
                "metric_definition": "",
                "period_basis": "",
                "source_filename": "",
                "source_page": "",
                "source_url": "",
                "source_evidence": "",
                "verification_status": "NOT_VERIFIED",
                "reviewer_notes": "Populate only after checking original PDF evidence.",
            })

    write_csv(VERIFIED_TEMPLATE_CSV, VERIFIED_FIELDS, verified_rows)

    SUMMARY_TXT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "FINANCIAL ACTUALS REVIEW QUEUE SUMMARY",
        f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Candidate input: {CANDIDATES_CSV}",
        "",
        f"Candidate rows read: {len(candidates)}",
        f"Review queue rows created: {len(queue)}",
        f"Numeric candidates prioritized (P1): {counts['P1_NUMERIC_REVIEW']}",
        f"Context candidates (P2): {counts['P2_CONTEXT_REVIEW']}",
        f"Excluded duplicate candidates: {counts['excluded_duplicate_candidates']}",
        f"Pre-existing actuals template rows copied as blank review rows: {len(verified_rows)}",
        "",
        "QUEUE COUNTS BY METRIC",
    ]
    for metric, count in metric_counts.most_common():
        lines.append(f"{metric}: {count}")

    lines.extend([
        "",
        "REVIEW RULES",
        "1. Open the original PDF named in source_filename.",
        "2. Find the exact metric and reporting period in the PDF.",
        "3. Record the exact value and unit; do not infer a value from nearby numbers.",
        "4. Record the PDF page number and a short source_evidence quotation or table label.",
        "5. Record the metric definition and period basis (quarter, YTD, or full year).",
        "6. Distinguish standalone-quarter values from cumulative/YTD values.",
        "7. Do not combine constant-currency growth with reported-currency growth.",
        "8. Do not treat EBITDA margin, EBIT margin and operating margin as interchangeable.",
        "9. Keep unresolved, missing or ambiguous values blank; never replace them with zero.",
        "10. Only copy reviewed values into the verified actuals dataset.",
        "",
        f"Review queue: {QUEUE_CSV}",
        f"Verified dataset template: {VERIFIED_TEMPLATE_CSV}",
        f"Summary: {SUMMARY_TXT}",
        "",
        "No financial values were automatically verified or calculated.",
    ])
    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print("\nScript 19 completed successfully.")


if __name__ == "__main__":
    main()
