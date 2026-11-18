"""SCRIPT 26 V2: FINANCIAL ACTUALS QUALITY SCREEN

Screens candidate rows for structural completeness and obvious anomalies.
MEDIUM confidence is not automatically a failure: it is classified as
CANDIDATE_FOR_SAMPLE_AUDIT, never as independently verified.
"""
from pathlib import Path
import re
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data/processed/financial_actuals_period_mapped.csv"
OUT = ROOT / "data/processed/financial_actuals_quality_checked.csv"
EXC = ROOT / "data/processed/financial_actuals_quality_exceptions.csv"
SUM = ROOT / "outputs/financial_actuals_quality_check_summary.txt"

PERCENT_METRICS = {
    "EBITDA_MARGIN", "EBIT_MARGIN", "PAT_MARGIN", "OPERATING_MARGIN", "REVENUE_GROWTH"
}
MONETARY_METRICS = {
    "REVENUE", "EBITDA", "EBIT", "PAT_NET_PROFIT", "PBT", "OPERATING_CASH_FLOW"
}

def main():
    if not IN.exists():
        sys.exit(f"Missing {IN}. Run Script 25 first.")
    d = pd.read_csv(IN, low_memory=False, dtype=str).fillna("")
    if d.empty:
        d.to_csv(OUT, index=False)
        pd.DataFrame().to_csv(EXC, index=False)
        SUM.parent.mkdir(parents=True, exist_ok=True)
        SUM.write_text("No mapped observations available.", encoding="utf-8")
        print(SUM.read_text())
        return

    required = ["ticker", "observation_quarter_key", "metric_category", "value",
                "unit", "source_filename", "source_pdf_page", "evidence_text"]
    missing = [c for c in required if c not in d.columns]
    if missing:
        sys.exit("Missing required columns: " + ", ".join(missing))

    d["value_numeric"] = pd.to_numeric(d["value"], errors="coerce")
    d["quality_flags"] = ""
    d["quality_status"] = "CANDIDATE_FOR_SAMPLE_AUDIT"
    flags = []

    for _, r in d.iterrows():
        f = []
        v = r["value_numeric"]
        metric = r["metric_category"].upper()
        unit = r["unit"].upper()
        quarter = r["observation_quarter_key"]
        if pd.isna(v): f.append("NON_NUMERIC_VALUE")
        if not r["ticker"].strip(): f.append("MISSING_TICKER")
        if not re.fullmatch(r"FY\d{2}_Q[1-4]", quarter): f.append("INVALID_OR_UNKNOWN_QUARTER")
        if not r["source_filename"].strip(): f.append("MISSING_SOURCE_FILE")
        if not r["source_pdf_page"].strip(): f.append("MISSING_SOURCE_PAGE")
        if not r["evidence_text"].strip(): f.append("MISSING_EVIDENCE_TEXT")
        if metric in PERCENT_METRICS:
            if unit != "PERCENT": f.append("PERCENT_METRIC_UNIT_MISMATCH")
            if pd.notna(v) and (v < -100 or v > 200): f.append("PERCENTAGE_OUTSIDE_EXPECTED_RANGE")
        elif metric in MONETARY_METRICS:
            if unit not in {"INR", "USD", "EUR", "GBP"}: f.append("UNKNOWN_CURRENCY")
            if pd.notna(v) and v < 0 and metric != "OPERATING_CASH_FLOW":
                f.append("NEGATIVE_VALUE_REQUIRES_REVIEW")
        else:
            f.append("UNRECOGNIZED_METRIC_CATEGORY")
        if r.get("unit_scale", "") in {"", "UNSPECIFIED"} and metric in MONETARY_METRICS:
            f.append("UNIT_SCALE_UNSPECIFIED")
        # Source-quarter mapping is based on report metadata, but basis still needs audit.
        if r.get("mapping_confidence", "").upper() != "HIGH":
            f.append("MEDIUM_OR_UNCONFIRMED_MAPPING_CONFIDENCE")
        if r.get("growth_type", "") == "UNSPECIFIED_GROWTH_BASIS":
            f.append("GROWTH_BASIS_UNSPECIFIED")
        flags.append(";".join(f))

    d["quality_flags"] = flags
    # Repeated mentions are retained; mark duplicates separately rather than invalidating all rows.
    dup_key = ["ticker", "observation_quarter_key", "metric_category", "unit", "unit_scale", "value"]
    d["possible_duplicate"] = d.duplicated(dup_key, keep=False)
    d["duplicate_group_size"] = d.groupby(dup_key, dropna=False)["record_id"].transform("size") if "record_id" in d else d.groupby(dup_key, dropna=False)["value"].transform("size")
    d.loc[d["possible_duplicate"], "quality_flags"] = d.loc[d["possible_duplicate"], "quality_flags"].apply(
        lambda x: (x + ";" if x else "") + "POSSIBLE_DUPLICATE_OBSERVATION"
    )
    # Rows with hard structural/semantic flags require review. Medium mapping and duplicate
    # flags alone are retained as candidates for sample audit, not silently rejected.
    hard_flags = {
        "NON_NUMERIC_VALUE", "MISSING_TICKER", "INVALID_OR_UNKNOWN_QUARTER",
        "MISSING_SOURCE_FILE", "MISSING_SOURCE_PAGE", "MISSING_EVIDENCE_TEXT",
        "PERCENT_METRIC_UNIT_MISMATCH", "PERCENTAGE_OUTSIDE_EXPECTED_RANGE",
        "UNKNOWN_CURRENCY", "NEGATIVE_VALUE_REQUIRES_REVIEW",
        "UNRECOGNIZED_METRIC_CATEGORY", "GROWTH_BASIS_UNSPECIFIED",
    }
    def has_hard_flag(s):
        return any(x in set(str(s).split(";")) for x in hard_flags)
    d.loc[d["quality_flags"].apply(has_hard_flag), "quality_status"] = "REVIEW_REQUIRED"
    d.loc[d["quality_status"] == "CANDIDATE_FOR_SAMPLE_AUDIT", "research_eligibility"] = "SAMPLE_AUDIT_REQUIRED"
    d.loc[d["quality_status"] == "REVIEW_REQUIRED", "research_eligibility"] = "EXCLUDE_PENDING_REVIEW"
    d.to_csv(OUT, index=False, encoding="utf-8-sig")
    d[d["quality_status"] == "REVIEW_REQUIRED"].to_csv(EXC, index=False, encoding="utf-8-sig")

    status_counts = d["quality_status"].value_counts().to_dict()
    metrics = d["metric_category"].value_counts().to_dict()
    lines = [
        "SCRIPT 26 V2: FINANCIAL ACTUALS QUALITY SCREEN", "=" * 58,
        f"Input candidates: {len(d):,}",
        f"Candidates for sample audit (not verified): {status_counts.get('CANDIDATE_FOR_SAMPLE_AUDIT', 0):,}",
        f"Rows requiring review: {status_counts.get('REVIEW_REQUIRED', 0):,}",
        f"Possible duplicate rows (retained): {int(d['possible_duplicate'].sum()):,}",
        f"Companies: {d['ticker'].nunique():,}",
        f"Observation quarters: {d['observation_quarter_key'].nunique():,}",
        "BY METRIC:"
    ]
    lines += [f"{k}: {v:,}" for k, v in metrics.items()]
    lines += [
        "", "IMPORTANT:",
        "- CANDIDATE_FOR_SAMPLE_AUDIT is not a verified financial actual.",
        "- MEDIUM mapping confidence is not promoted to HIGH.",
        "- Possible duplicates are retained and flagged; they are not deleted.",
        "- Monetary values with unspecified scale remain candidates but require normalization review.",
        f"Checked data: {OUT.relative_to(ROOT)}", f"Exceptions: {EXC.relative_to(ROOT)}"
    ]
    SUM.parent.mkdir(parents=True, exist_ok=True)
    SUM.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
