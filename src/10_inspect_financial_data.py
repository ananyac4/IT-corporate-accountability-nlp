
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

main_file = PROCESSED / "actuals_template.csv"
ofss_file = PROCESSED / "OFSS_quarterly_actuals.csv"

main = pd.read_csv(main_file)
ofss = pd.read_csv(ofss_file)

print("\n" + "=" * 65)
print("1. MAIN ACTUALS TEMPLATE - FIRST 10 ROWS")
print("=" * 65)

print(main.head(10).to_string(index=False))

print("\nMain dataset missing-value counts:")
print(main.isna().sum().to_string())

print("\n" + "=" * 65)
print("2. OFSS FINANCIAL ACTUALS - FIRST 10 ROWS")
print("=" * 65)

print(ofss.head(10).to_string(index=False))

print("\nOFSS missing-value counts:")
print(ofss.isna().sum().to_string())

print("\n" + "=" * 65)
print("3. OFSS FINANCIAL MEASURES")
print("=" * 65)

numeric_columns = [
    "total_revenue_inr_mn",
    "total_revenue_yoy_pct",
    "operating_income_inr_mn",
    "operating_margin_pct",
    "net_income_inr_mn",
    "net_margin_pct"
]

for column in numeric_columns:
    if column in ofss.columns:
        print(f"\n{column}")
        print(ofss[column].describe().to_string())

print("\n" + "=" * 65)
print("4. QUARTER IDENTIFIERS")
print("=" * 65)

print("Main template:")
print(main[["ticker", "quarter_key"]].head(10).to_string(index=False))

print("\nOFSS:")
print(ofss[["ticker", "financial_year", "quarter"]].to_string(index=False))

print("\nInspection complete. No original files modified.")
