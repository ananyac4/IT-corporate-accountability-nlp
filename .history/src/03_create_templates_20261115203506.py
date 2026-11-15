
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "data" / "processed" / "coverage_tracker.xlsx"
OUT = ROOT / "data" / "processed"

def main():
    coverage = pd.read_excel(TRACKER, sheet_name="coverage")
    coverage.columns = [str(c).strip().lower() for c in coverage.columns]
    base = coverage[["ticker", "fy", "q"]].drop_duplicates().copy()
    base["quarter_key"] = base["fy"].astype(str) + "_" + base["q"].astype(str)

    actuals = base[["ticker", "quarter_key"]].copy()
    actuals["revenue_growth_cc_pct"] = ""
    actuals["ebit_margin_pct"] = ""
    actuals["source_url"] = ""
    actuals["source_page"] = ""
    actuals["notes"] = ""
    actuals.to_csv(OUT / "actuals_template.csv", index=False)

    guidance = base[["ticker", "quarter_key"]].copy()
    guidance["stated_quarter"] = ""
    guidance["target_quarter"] = ""
    guidance["metric"] = "revenue_growth_cc_pct"
    guidance["guidance_type"] = ""
    guidance["low_pct"] = ""
    guidance["high_pct"] = ""
    guidance["target_pct"] = ""
    guidance["direction"] = ""
    guidance["source_sentence"] = ""
    guidance["source_url"] = ""
    guidance["source_page"] = ""
    guidance["notes"] = ""
    guidance.to_csv(OUT / "guidance_template.csv", index=False)

    explanations = pd.DataFrame(columns=[
        "ticker", "quarter_key", "theme", "explanation_text",
        "source_url", "source_page", "annotator_notes"
    ])
    explanations.to_csv(OUT / "explanations_template.csv", index=False)

    print("Created:")
    print(OUT / "actuals_template.csv")
    print(OUT / "guidance_template.csv")
    print(OUT / "explanations_template.csv")
    print("\nFill values only from cited company sources. Leave unavailable values blank.")

if __name__ == "__main__":
    main()
