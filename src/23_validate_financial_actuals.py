"""
SCRIPT 23: VALIDATE VERIFIED FINANCIAL ACTUALS

Input:
  data/processed/financial_actuals_verified.csv

Outputs:
  outputs/financial_actuals_quality_summary.txt
  outputs/financial_actuals_quality_by_company.csv
  outputs/financial_actuals_duplicate_observations.csv
  outputs/financial_actuals_missing_company_quarters.csv

Checks completeness, duplicates, missing company-quarter-metric combinations,
period basis, units and numeric parseability. It does not decide whether a
reported value is economically correct; source verification remains essential.
"""

from pathlib import Path
from datetime import datetime
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/financial_actuals_verified.csv"
OUT_DIR = ROOT / "outputs"

COMPANIES = [
    "BSOFT", "COFORGE", "CYIENT", "HAPPSTMNDS", "HCLTECH", "INFY",
    "INTELLECT", "KPITTECH", "LTIM", "MASTEK", "MPHASIS", "NEWGEN",
    "OFSS", "PERSISTENT", "SONATSOFTW", "TATAELXSI", "TCS", "TECHM",
    "WIPRO", "ZENSARTECH",
]
QUARTERS = [
    f"FY{fy}_Q{q}" for fy in range(23, 27) for q in range(1, 5)
] + ["FY27_Q1"]

def clean(s):
    return s.fillna("").astype(str).str.strip()

def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"{INPUT} not found. Run Script 22 after reviewing candidates."
        )

    df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)
    required = [
        "ticker", "quarter_key", "metric_category", "reviewed_value",
        "reviewed_unit", "period_basis", "source_filename",
        "source_pdf_page", "source_evidence_checked", "review_status",
    ]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Verified dataset missing columns: {missing_cols}")

    for col in required:
        df[col] = clean(df[col])

    df["reviewed_value_numeric"] = pd.to_numeric(
        df["reviewed_value"].str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False),
        errors="coerce"
    )

    df["quality_issue"] = ""
    checks = [
        ("blank_ticker", df["ticker"].eq("")),
        ("blank_quarter", df["quarter_key"].eq("")),
        ("blank_metric", df["metric_category"].eq("")),
        ("blank_value", df["reviewed_value"].eq("")),
        ("blank_unit", df["reviewed_unit"].eq("")),
        ("invalid_period_basis", ~df["period_basis"].isin(["QUARTER", "YTD", "ANNUAL"])),
        ("blank_source_filename", df["source_filename"].eq("")),
        ("blank_pdf_page", df["source_pdf_page"].eq("")),
        ("blank_source_evidence", df["source_evidence_checked"].eq("")),
        ("not_marked_verified", ~df["review_status"].str.upper().eq("VERIFIED")),
        ("non_numeric_value", df["reviewed_value_numeric"].isna()),
    ]
    issue_lists = []
    for idx in range(len(df)):
        issues = [name for name, mask in checks if bool(mask.iloc[idx])]
        issue_lists.append(";".join(issues))
    df["quality_issue"] = issue_lists

    duplicate_cols = ["ticker", "quarter_key", "metric_category", "period_basis"]
    duplicate_mask = df.duplicated(duplicate_cols, keep=False)
    duplicates = df.loc[duplicate_mask].copy()
    duplicates.to_csv(
        OUT_DIR / "financial_actuals_duplicate_observations.csv",
        index=False, encoding="utf-8-sig"
    )

    # Report missing company-quarter combinations across the defined panel.
    present = set(zip(df["ticker"], df["quarter_key"]))
    missing_rows = [
        {"ticker": ticker, "quarter_key": quarter, "status": "NO_VERIFIED_OBSERVATION"}
        for ticker in COMPANIES for quarter in QUARTERS
        if (ticker, quarter) not in present
    ]
    missing_df = pd.DataFrame(missing_rows)
    missing_df.to_csv(
        OUT_DIR / "financial_actuals_missing_company_quarters.csv",
        index=False, encoding="utf-8-sig"
    )

    company_summary = (
        df.groupby("ticker", dropna=False)
        .agg(
            verified_rows=("ticker", "size"),
            unique_quarters=("quarter_key", "nunique"),
            unique_metrics=("metric_category", "nunique"),
            rows_with_quality_issues=("quality_issue", lambda x: (x != "").sum()),
        )
        .reset_index()
    )
    company_summary.to_csv(
        OUT_DIR / "financial_actuals_quality_by_company.csv",
        index=False, encoding="utf-8-sig"
    )

    issue_rows = int((df["quality_issue"] != "").sum())
    lines = [
        "FINANCIAL ACTUALS DATA QUALITY SUMMARY",
        f"Run date: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Verified dataset rows read: {len(df)}",
        f"Companies represented: {df['ticker'].nunique()}",
        f"Company-quarter combinations represented: {df[['ticker','quarter_key']].drop_duplicates().shape[0]}",
        f"Unique metric categories: {df['metric_category'].nunique()}",
        f"Rows with at least one quality issue: {issue_rows}",
        f"Rows in possible duplicate observation groups: {len(duplicates)}",
        f"Missing company-quarter combinations (of 340 expected): {len(missing_df)}",
        f"Numeric values not parseable by simple numeric conversion: {int(df['reviewed_value_numeric'].isna().sum())}",
        "",
        "QUALITY ISSUE COUNTS",
    ]
    for name, mask in checks:
        lines.append(f"{name}: {int(mask.sum())}")
    lines += [
        "",
        "OUTPUTS",
        str(OUT_DIR / "financial_actuals_quality_by_company.csv"),
        str(OUT_DIR / "financial_actuals_duplicate_observations.csv"),
        str(OUT_DIR / "financial_actuals_missing_company_quarters.csv"),
        "",
        "Interpretation: These checks identify structural issues; they do not prove",
        "that values are economically correct or comparable across companies.",
        "Check metric definitions, currency, units, consolidation basis and period basis.",
    ]
    (OUT_DIR / "financial_actuals_quality_summary.txt").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print("\n".join(lines))
    print("\nScript 23 completed successfully.")

if __name__ == "__main__":
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
