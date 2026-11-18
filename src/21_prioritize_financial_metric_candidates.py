"""
SCRIPT 21: PRIORITIZE FINANCIAL METRIC CANDIDATES

Input:
  data/processed/financial_metric_page_candidates.csv

Outputs:
  data/processed/financial_actuals_manual_review.csv
  outputs/financial_actuals_prioritization_summary.txt

This script ranks candidates for human review. It does not verify or calculate
financial values. It preserves source rows and flags exact duplicate evidence.
"""

from pathlib import Path
from datetime import datetime
import hashlib
import re
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/financial_metric_page_candidates.csv"
OUTPUT = ROOT / "data/processed/financial_actuals_manual_review.csv"
SUMMARY = ROOT / "outputs/financial_actuals_prioritization_summary.txt"

# Metrics most directly useful for comparing guidance with performance.
METRIC_WEIGHT = {
    "REVENUE_GROWTH": 100,
    "REVENUE": 90,
    "EBIT": 85,
    "OPERATING_MARGIN": 85,
    "EBITDA": 75,
    "PAT_NET_PROFIT": 65,
    "GROSS_MARGIN": 55,
    "CASH_FLOW": 45,
    "ORDER_BOOK": 35,
}

REQUIRED = [
    "ticker", "quarter_key", "source_filename", "source_pdf_page",
    "metric_category", "evidence_text", "numeric_tokens_on_line",
]

def norm(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def truthy(value):
    return norm(value).lower() in {"true", "1", "yes", "y"}

def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"Input not found: {INPUT}")

    df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Preserve all candidate rows. Duplicate rows are flagged, not discarded.
    evidence_norm = (
        df["evidence_text"].str.lower()
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    key_cols = ["ticker", "quarter_key", "metric_category", "source_filename",
                "source_pdf_page"]
    dup_key = df[key_cols].astype(str).agg("|".join, axis=1) + "|" + evidence_norm
    df["evidence_hash"] = dup_key.map(
        lambda x: hashlib.sha256(x.encode("utf-8", errors="replace")).hexdigest()
    )
    df["exact_evidence_duplicate"] = df.duplicated("evidence_hash", keep="first")

    df["has_numeric_token"] = df["numeric_tokens_on_line"].map(
        lambda x: bool(norm(x))
    )
    df["metric_weight"] = df["metric_category"].map(METRIC_WEIGHT).fillna(20)
    df["priority_score"] = (
        df["metric_weight"]
        + df["has_numeric_token"].astype(int) * 25
        + df["evidence_text"].str.len().clip(upper=500).div(500) * 5
        - df["exact_evidence_duplicate"].astype(int) * 10
    ).round(2)

    def priority(score):
        if score >= 110:
            return "P1"
        if score >= 85:
            return "P2"
        return "P3"

    df["review_priority"] = df["priority_score"].map(priority)
    df["review_status"] = df.get("review_status", "NOT_VERIFIED")
    df["review_status"] = df["review_status"].replace("", "NOT_VERIFIED")

    # Blank reviewer fields are added only if not already present.
    for col in ["reviewed_value", "reviewed_unit", "period_basis",
                "source_evidence_checked", "reviewer_notes"]:
        if col not in df.columns:
            df[col] = ""

    df = df.sort_values(
        ["review_priority", "ticker", "quarter_key", "metric_category",
         "source_filename", "source_pdf_page"],
        ascending=[True, True, True, True, True, True],
        kind="stable"
    )
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    counts = df["review_priority"].value_counts().to_dict()
    metric_counts = df["metric_category"].value_counts().to_dict()
    lines = [
        "FINANCIAL ACTUALS PRIORITIZATION SUMMARY",
        f"Run date: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Input rows: {len(df)}",
        f"Output review rows: {len(df)}",
        f"Exact duplicate evidence rows flagged (not removed): {int(df['exact_evidence_duplicate'].sum())}",
        f"Rows with numeric tokens: {int(df['has_numeric_token'].sum())}",
        "",
        "PRIORITY COUNTS",
        f"P1: {counts.get('P1', 0)}",
        f"P2: {counts.get('P2', 0)}",
        f"P3: {counts.get('P3', 0)}",
        "",
        "METRIC COUNTS",
    ]
    lines.extend(f"{k}: {v}" for k, v in metric_counts.items())
    lines += [
        "",
        "REVIEW INSTRUCTIONS",
        "1. Open source_filename and inspect source_pdf_page.",
        "2. Confirm the metric label and the exact reported value.",
        "3. Enter reviewed_value and reviewed_unit exactly as reported.",
        "4. Set period_basis to QUARTER, YTD, or ANNUAL.",
        "5. Add a short quotation/table label to source_evidence_checked.",
        "6. Change review_status to VERIFIED only after checking the PDF.",
        "7. Leave uncertain records as NOT_VERIFIED; do not guess.",
        "",
        f"Review queue: {OUTPUT}",
        "All candidate rows are retained; duplicate evidence is flagged, not deleted.",
    ]
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print("\nScript 21 completed successfully.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
