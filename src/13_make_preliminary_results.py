"""
13_make_preliminary_results.py

Run from the project root:
    python src/13_make_preliminary_results.py

Creates:
  outputs/figures/transcript_coverage_by_company.png
  outputs/figures/ofss_operating_margin_trend.png
  outputs/figures/ofss_revenue_and_profit_trend.png
  outputs/preliminary_results_summary.csv
  outputs/pilot_guidance_review.csv
  outputs/pilot_explanation_review.csv (if explanation_candidates.csv exists)
  outputs/pilot_communication_review.csv (if communication_candidates.csv exists)

IMPORTANT:
- Candidate statements are NOT verified management guidance.
- This script does not calculate forecast accuracy from unverified candidates.
- OFSS source is quarterly financial-results releases, not earnings-call transcripts.
"""

from pathlib import Path
import re
import warnings
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
OUT.mkdir(exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

def locate(*names):
    for name in names:
        for folder in (DATA, OUT):
            p = folder / name
            if p.exists():
                return p
    raise FileNotFoundError(
        "Could not find any of these files in data/processed: " + ", ".join(names)
    )

def read_csv_if_exists(path):
    return pd.read_csv(path) if path.exists() else None

# 1) Transcript coverage chart and summary
coverage_path = locate("transcript_quarter_coverage.csv")
coverage = pd.read_csv(coverage_path)

required = {"ticker", "coverage_percentage", "available_quarters", "expected_quarters"}
if not required.issubset(coverage.columns):
    raise ValueError(f"{coverage_path.name} must contain {sorted(required)}")

coverage = coverage.sort_values(["coverage_percentage", "ticker"], ascending=[True, True])
plt.figure(figsize=(11, 8))
plt.barh(coverage["ticker"], coverage["coverage_percentage"])
plt.axvline(100, linestyle="--", linewidth=1)
plt.xlabel("Transcript coverage (%)")
plt.ylabel("Company")
plt.title("Earnings-call transcript coverage by company")
plt.xlim(0, 105)
plt.tight_layout()
plt.savefig(FIG / "transcript_coverage_by_company.png", dpi=220)
plt.close()

# 2) OFSS actuals: use either extracted or integrated file
ofss_path = locate("OFSS_quarterly_actuals.csv", "OFSS_quarterly_actuals_extracted.csv")
ofss = pd.read_csv(ofss_path)

# Support both raw extractor and normalized columns in actuals_template
if "operating_margin_pct" not in ofss.columns:
    raise ValueError("OFSS file has no operating_margin_pct column.")

ofss["financial_year"] = ofss["financial_year"].astype(str)
ofss["quarter"] = ofss["quarter"].astype(str)
ofss["fy_num"] = pd.to_numeric(ofss["financial_year"].str.extract(r"(\d{4})")[0], errors="coerce")
ofss["q_num"] = pd.to_numeric(ofss["quarter"].str.extract(r"(\d+)")[0], errors="coerce")
ofss = ofss.dropna(subset=["fy_num", "q_num"]).copy()
ofss["period"] = "FY" + (ofss["fy_num"].astype(int) % 100).astype(str).str.zfill(2) + "_Q" + ofss["q_num"].astype(int).astype(str)
ofss = ofss.sort_values(["fy_num", "q_num"])

margin = pd.to_numeric(ofss["operating_margin_pct"], errors="coerce")
valid_margin = margin.dropna()
if len(valid_margin):
    plt.figure(figsize=(11, 5))
    plt.plot(ofss.loc[margin.notna(), "period"], margin.dropna(), marker="o", linewidth=1.8)
    plt.xticks(rotation=55, ha="right")
    plt.ylabel("Operating margin (%)")
    plt.xlabel("Fiscal quarter")
    plt.title("OFSS reported operating margin by quarter")
    plt.tight_layout()
    plt.savefig(FIG / "ofss_operating_margin_trend.png", dpi=220)
    plt.close()

# Revenue and net income YoY growth are reported INR growth, not constant currency.
growth_cols = [c for c in ["total_revenue_yoy_pct", "net_income_yoy_pct"] if c in ofss.columns]
if growth_cols:
    plt.figure(figsize=(11, 5))
    for c in growth_cols:
        vals = pd.to_numeric(ofss[c], errors="coerce")
        plt.plot(ofss["period"], vals, marker="o", label=c.replace("_", " ").replace(" pct", " (%)"))
    plt.xticks(rotation=55, ha="right")
    plt.ylabel("Reported year-on-year growth (%)")
    plt.xlabel("Fiscal quarter")
    plt.title("OFSS reported INR revenue and net-income growth")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG / "ofss_revenue_and_profit_trend.png", dpi=220)
    plt.close()

# 3) Summary metrics, with explicit scope
summary_rows = []
summary_rows.append({
    "analysis": "transcript_coverage",
    "scope": "20 companies; FY23 Q1-FY27 Q1",
    "n": int(coverage["available_quarters"].sum()),
    "metric": "coverage_percentage",
    "value": round(
        coverage["available_quarters"].sum() /
        coverage["expected_quarters"].sum() * 100, 2
    ),
    "interpretation": "Valid transcript records / expected company-quarter records"
})
summary_rows.append({
    "analysis": "ofss_operating_margin",
    "scope": "OFSS quarterly financial-results releases only",
    "n": int(valid_margin.count()),
    "metric": "mean_operating_margin_pct",
    "value": round(valid_margin.mean(), 2) if len(valid_margin) else None,
    "interpretation": "Descriptive statistic; reported operating margin used as EBIT-margin proxy"
})
summary_rows.append({
    "analysis": "ofss_operating_margin",
    "scope": "OFSS quarterly financial-results releases only",
    "n": int(valid_margin.count()),
    "metric": "median_operating_margin_pct",
    "value": round(valid_margin.median(), 2) if len(valid_margin) else None,
    "interpretation": "Descriptive statistic; not a cross-company finding"
})
summary_rows.append({
    "analysis": "ofss_operating_margin",
    "scope": "OFSS quarterly financial-results releases only",
    "n": int(valid_margin.count()),
    "metric": "min_operating_margin_pct",
    "value": round(valid_margin.min(), 2) if len(valid_margin) else None,
    "interpretation": "Descriptive statistic"
})
summary_rows.append({
    "analysis": "ofss_operating_margin",
    "scope": "OFSS quarterly financial-results releases only",
    "n": int(valid_margin.count()),
    "metric": "max_operating_margin_pct",
    "value": round(valid_margin.max(), 2) if len(valid_margin) else None,
    "interpretation": "Descriptive statistic; investigate exceptional quarters"
})

pd.DataFrame(summary_rows).to_csv(OUT / "preliminary_results_summary.csv", index=False)

# 4) Create manageable human-review files from candidate exports
# Three companies have complete transcript coverage in the uploaded audit.
PILOT = ["INFY", "BSOFT", "PERSISTENT"]

def relevance_score(text):
    text = str(text).lower()
    terms = [
        "guidance", "outlook", "expect", "forecast", "target", "margin",
        "growth", "demand", "pipeline", "uncertain", "visibility",
        "challenging", "headwind", "recovery", "slowdown", "pricing",
        "cost", "utilization", "attrition", "deal", "revenue"
    ]
    return sum(1 for term in terms if term in text)

def make_review(source_name, output_name, text_col_candidates, max_rows=250):
    p = next((folder / source_name for folder in (DATA, OUT)
              if (folder / source_name).exists()), None)
    if p is None:
        print(f"SKIP: {source_name} not found")
        return
    df = pd.read_csv(p)
    if "ticker" not in df.columns:
        print(f"SKIP: {source_name} has no ticker column")
        return
    df = df[df["ticker"].isin(PILOT)].copy()
    text_col = next((c for c in text_col_candidates if c in df.columns), None)
    if text_col:
        df["_review_priority"] = df[text_col].map(relevance_score)
        df = df.sort_values("_review_priority", ascending=False)
    # Keep speaker and page/source identifiers where available.
    df.head(max_rows).drop(columns=["_review_priority"], errors="ignore").to_csv(
        OUT / output_name, index=False
    )
    print(f"Created {output_name}: {min(len(df), max_rows)} review rows")

make_review(
    "guidance_candidates.csv",
    "pilot_guidance_review.csv",
    ["sentence", "source_sentence"],
    max_rows=300
)
make_review(
    "explanation_candidates.csv",
    "pilot_explanation_review.csv",
    ["sentence", "source_sentence", "statement"],
    max_rows=250
)
make_review(
    "communication_candidates.csv",
    "pilot_communication_review.csv",
    ["sentence", "source_sentence", "statement"],
    max_rows=250
)

print("\nPRELIMINARY RESULTS GENERATED")
print(f"Coverage: {coverage['available_quarters'].sum()}/{coverage['expected_quarters'].sum()} "
      f"({coverage['available_quarters'].sum()/coverage['expected_quarters'].sum()*100:.2f}%)")
print(f"OFSS operating-margin observations: {valid_margin.count()}")
print(f"Charts saved in: {FIG}")
print(f"Tables/review files saved in: {OUT}")
print("\nDo not report candidate counts as validated management statements.")
print("Do not calculate guidance accuracy until each guidance statement and target quarter is verified.")
