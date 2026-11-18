"""
SCRIPT 22: BUILD VERIFIED FINANCIAL ACTUALS DATASET

Input:
  data/processed/financial_actuals_manual_review.csv

Outputs:
  data/processed/financial_actuals_verified.csv
  data/processed/financial_actuals_not_yet_verified.csv
  outputs/financial_actuals_consolidation_summary.txt

Before running, manually review the queue and:
  - set review_status = VERIFIED only for values checked against the PDF;
  - fill reviewed_value, reviewed_unit, period_basis;
  - fill source_evidence_checked;
  - preserve the original source filename and PDF page.

This script does not promote unverified candidates.
"""

from pathlib import Path
from datetime import datetime
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/financial_actuals_manual_review.csv"
VERIFIED_OUT = ROOT / "data/processed/financial_actuals_verified.csv"
PENDING_OUT = ROOT / "data/processed/financial_actuals_not_yet_verified.csv"
SUMMARY = ROOT / "outputs/financial_actuals_consolidation_summary.txt"

REQUIRED = [
    "ticker", "quarter_key", "metric_category", "source_filename",
    "source_pdf_page", "review_status", "reviewed_value", "reviewed_unit",
    "period_basis", "source_evidence_checked",
]

def clean(series):
    return series.fillna("").astype(str).str.strip()

def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"{INPUT} not found. Run Script 21 first and review its CSV."
        )

    df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Review file is missing required columns: {missing}")

    status = clean(df["review_status"]).str.upper()
    value = clean(df["reviewed_value"])
    unit = clean(df["reviewed_unit"])
    basis = clean(df["period_basis"]).str.upper()
    evidence = clean(df["source_evidence_checked"])
    page = clean(df["source_pdf_page"])
    filename = clean(df["source_filename"])

    # VERIFIED rows must have every minimum audit field.
    is_verified = status.eq("VERIFIED")
    complete = (
        value.ne("") & unit.ne("") & basis.isin(["QUARTER", "YTD", "ANNUAL"])
        & evidence.ne("") & page.ne("") & filename.ne("")
    )
    invalid_verified = is_verified & ~complete

    if invalid_verified.any():
        examples = df.loc[invalid_verified, [
            "ticker", "quarter_key", "metric_category", "source_filename",
            "source_pdf_page"
        ]].head(10).to_string(index=False)
        raise ValueError(
            f"{int(invalid_verified.sum())} rows are marked VERIFIED but lack "
            "required value/unit/period/evidence/source fields. Fix them first.\n"
            f"Examples:\n{examples}"
        )

    verified = df.loc[is_verified & complete].copy()
    pending = df.loc[~(is_verified & complete)].copy()

    # Normalize the verified value to numeric only when safely parseable;
    # retain the exact original reviewed_value string in all cases.
    verified["reviewed_value_numeric"] = pd.to_numeric(
        clean(verified["reviewed_value"]).str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False),
        errors="coerce"
    )
    verified["period_basis"] = clean(verified["period_basis"]).str.upper()
    verified["review_status"] = "VERIFIED"

    # Flag possible duplicate observations; do not silently drop them.
    dup_cols = ["ticker", "quarter_key", "metric_category", "period_basis"]
    verified["possible_observation_duplicate"] = verified.duplicated(
        dup_cols, keep=False
    )

    VERIFIED_OUT.parent.mkdir(parents=True, exist_ok=True)
    verified.to_csv(VERIFIED_OUT, index=False, encoding="utf-8-sig")
    pending.to_csv(PENDING_OUT, index=False, encoding="utf-8-sig")

    lines = [
        "FINANCIAL ACTUALS CONSOLIDATION SUMMARY",
        f"Run date: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Review queue rows: {len(df)}",
        f"Verified rows exported: {len(verified)}",
        f"Rows remaining unverified/pending: {len(pending)}",
        f"Verified rows with non-numeric reviewed_value: {int(verified['reviewed_value_numeric'].isna().sum())}",
        f"Possible duplicate observations flagged: {int(verified['possible_observation_duplicate'].sum())}",
        "",
        "VERIFIED ROWS BY METRIC",
    ]
    if verified.empty:
        lines.append("No verified rows yet.")
    else:
        lines.extend(
            f"{k}: {v}" for k, v in verified["metric_category"].value_counts().items()
        )
    lines += [
        "",
        f"Verified dataset: {VERIFIED_OUT}",
        f"Pending review file: {PENDING_OUT}",
        "Only rows explicitly marked VERIFIED with complete audit fields are exported.",
        "Possible duplicate observations are flagged, not deleted.",
    ]
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print("\nScript 22 completed successfully.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
