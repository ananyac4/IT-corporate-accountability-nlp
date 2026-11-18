"""SCRIPT 27 V2: CONSOLIDATE FINANCIAL RESEARCH CANDIDATES

Builds an auditable exploratory dataset from Script 26. No candidate is described
as a verified actual. Keeps all candidates and their provenance/quality flags.
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data/processed/financial_actuals_quality_checked.csv"
OUT = ROOT / "data/processed/financial_actuals_research_dataset.csv"
BYCO = ROOT / "outputs/financial_actuals_final_coverage_by_company.csv"
BYQ = ROOT / "outputs/financial_actuals_final_coverage_by_quarter.csv"
SUM = ROOT / "outputs/financial_actuals_final_dataset_summary.txt"

EXPECTED = [
    "BSOFT","COFORGE","CYIENT","HAPPSTMNDS","HCLTECH","INFY","INTELLECT","KPITTECH","LTIM","MASTEK",
    "MPHASIS","NEWGEN","OFSS","PERSISTENT","SONATSOFTW","TATAELXSI","TCS","TECHM","WIPRO","ZENSARTECH"
]
QUARTERS = [f"FY{y}_Q{q}" for y in range(23, 28) for q in range(1, 5)
            if not (y == 27 and q > 1)]

def main():
    if not IN.exists():
        sys.exit(f"Missing {IN}. Run Script 26 first.")
    d = pd.read_csv(IN, low_memory=False, dtype=str).fillna("")
    if d.empty:
        d.to_csv(OUT, index=False)
        SUM.parent.mkdir(parents=True, exist_ok=True)
        SUM.write_text("No financial observations available. Inspect Scripts 25 and 26.", encoding="utf-8")
        print(SUM.read_text())
        return

    # Do not overwrite quality labels; add a transparent research-use classification.
    d["research_eligibility"] = d.get("research_eligibility", "SAMPLE_AUDIT_REQUIRED")
    d.loc[d["quality_status"] == "CANDIDATE_FOR_SAMPLE_AUDIT", "research_eligibility"] = "SAMPLE_AUDIT_REQUIRED"
    d.loc[d["quality_status"] == "REVIEW_REQUIRED", "research_eligibility"] = "EXCLUDE_PENDING_REVIEW"
    d["verified_actual"] = False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT, index=False, encoding="utf-8-sig")

    pairs = pd.MultiIndex.from_product([EXPECTED, QUARTERS], names=["ticker", "quarter_key"]).to_frame(index=False)
    present = d[["ticker", "observation_quarter_key"]].drop_duplicates().rename(
        columns={"observation_quarter_key": "quarter_key"}
    )
    coverage = pairs.merge(present.assign(present=True), on=["ticker", "quarter_key"], how="left")
    coverage["present"] = coverage["present"].fillna(False)
    byco = coverage.groupby("ticker").agg(
        expected_quarters=("quarter_key", "count"),
        quarters_with_any_observation=("present", "sum")
    ).reset_index()
    byco["missing_quarters"] = byco["expected_quarters"] - byco["quarters_with_any_observation"]
    byco["coverage_pct"] = (byco["quarters_with_any_observation"] / byco["expected_quarters"] * 100).round(2)
    byco.to_csv(BYCO, index=False)
    byq = coverage.groupby("quarter_key").agg(
        expected_companies=("ticker", "count"),
        companies_with_any_observation=("present", "sum")
    ).reset_index()
    byq["missing_companies"] = byq["expected_companies"] - byq["companies_with_any_observation"]
    byq["coverage_pct"] = (byq["companies_with_any_observation"] / byq["expected_companies"] * 100).round(2)
    byq.to_csv(BYQ, index=False)

    lines = [
        "SCRIPT 27 V2: FINANCIAL RESEARCH CANDIDATE DATASET", "=" * 62,
        f"Candidate observations retained: {len(d):,}",
        f"Companies represented: {d['ticker'].nunique():,}",
        f"Quarters represented: {d['observation_quarter_key'].nunique():,}",
        f"Candidates for sample audit: {(d['quality_status'] == 'CANDIDATE_FOR_SAMPLE_AUDIT').sum():,}",
        f"Rows requiring review: {(d['quality_status'] == 'REVIEW_REQUIRED').sum():,}",
        f"Possible duplicate rows retained: {int(d.get('possible_duplicate', pd.Series(dtype=bool)).astype(str).str.lower().eq('true').sum()):,}",
        "Metric counts:"
    ]
    lines += [f"{k}: {v:,}" for k, v in d["metric_category"].value_counts().items()]
    lines += ["", "Coverage by company:"]
    lines += [f"{r.ticker}: {int(r.quarters_with_any_observation)}/{int(r.expected_quarters)} ({r.coverage_pct:.2f}%)"
              for r in byco.itertuples()]
    lines += [
        "", "IMPORTANT:",
        "This is an exploratory research-candidate dataset, not a verified financial actuals dataset.",
        "All rows have verified_actual=False until independently supported by source review.",
        "Do not combine different currencies, scales, consolidated/standalone bases, or adjusted/reported definitions.",
        f"Dataset: {OUT.relative_to(ROOT)}",
        f"Company coverage: {BYCO.relative_to(ROOT)}",
        f"Quarter coverage: {BYQ.relative_to(ROOT)}"
    ]
    SUM.parent.mkdir(parents=True, exist_ok=True)
    SUM.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
