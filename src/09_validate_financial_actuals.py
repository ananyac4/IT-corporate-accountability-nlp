
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

ACTUALS_FILE = PROCESSED / "actuals_template.csv"
OFSS_FILE = PROCESSED / "OFSS_quarterly_actuals.csv"

required_columns = [
    "ticker",
    "quarter_key",
    "revenue_growth_cc_pct",
    "ebit_margin_pct",
    "source_url",
    "source_page",
    "notes"
]

# 1. Load main financial template
if not ACTUALS_FILE.exists():
    raise FileNotFoundError(f"Missing file: {ACTUALS_FILE}")

df = pd.read_csv(ACTUALS_FILE)

missing_columns = [
    col for col in required_columns if col not in df.columns
]

if missing_columns:
    raise ValueError(f"Missing columns: {missing_columns}")

# 2. Check missing values
df["revenue_missing"] = df["revenue_growth_cc_pct"].isna()
df["margin_missing"] = df["ebit_margin_pct"].isna()
df["source_missing"] = df["source_url"].isna() | (
    df["source_url"].astype(str).str.strip() == ""
)

# 3. Check duplicate company-quarter combinations
df["duplicate_company_quarter"] = df.duplicated(
    subset=["ticker", "quarter_key"],
    keep=False
)

# 4. Company-level summary
summary = (
    df.groupby("ticker")
    .agg(
        quarter_rows=("quarter_key", "count"),
        revenue_values=("revenue_growth_cc_pct", "count"),
        margin_values=("ebit_margin_pct", "count"),
        source_values=("source_url", "count"),
        duplicate_rows=("duplicate_company_quarter", "sum")
    )
    .reset_index()
)

summary["revenue_missing"] = (
    summary["quarter_rows"] - summary["revenue_values"]
)
summary["margin_missing"] = (
    summary["quarter_rows"] - summary["margin_values"]
)
summary["source_missing"] = (
    summary["quarter_rows"] - summary["source_values"]
)

# 5. Detailed rows requiring review
review = df[
    df["revenue_missing"]
    | df["margin_missing"]
    | df["source_missing"]
    | df["duplicate_company_quarter"]
].copy()

# 6. OFSS separate data audit
if OFSS_FILE.exists():
    ofss = pd.read_csv(OFSS_FILE)

    ofss_summary = pd.DataFrame({
        "field": ofss.columns,
        "non_missing_values": [
            ofss[col].notna().sum() for col in ofss.columns
        ],
        "missing_values": [
            ofss[col].isna().sum() for col in ofss.columns
        ]
    })

    ofss_summary.to_csv(
        OUTPUTS / "OFSS_financial_field_audit.csv",
        index=False
    )

    print("\nOFSS DATA")
    print("Rows:", len(ofss))
    print("Columns:", list(ofss.columns))
else:
    print("\nOFSS quarterly actuals file not found.")

# 7. Save reports
summary.to_csv(
    OUTPUTS / "financial_actuals_company_summary.csv",
    index=False
)

review.to_csv(
    OUTPUTS / "financial_actuals_review.csv",
    index=False
)

print("\nFINANCIAL ACTUALS VALIDATION COMPLETE")
print("Total rows:", len(df))
print("Companies:", df["ticker"].nunique())
print("Duplicate company-quarter rows:",
      int(df["duplicate_company_quarter"].sum()))
print("Rows requiring review:", len(review))

print("\nCompany summary:")
print(summary.to_string(index=False))

print("\nReports saved in outputs/")
