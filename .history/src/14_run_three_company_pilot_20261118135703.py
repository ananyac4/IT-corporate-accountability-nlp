
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "pilot_fy23_fy24"
RESULTS = OUT / "results"
FIGURES = OUT / "figures"

RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

MASTER = DATA / "master_candidate_statements_3company_pilot.csv"
COVERAGE = DATA / "transcript_coverage_3company_8q.csv"
ACTUALS = DATA / "actuals_template_3company_pilot.csv"
PILOT = DATA / "pilot_verified_observations.csv"

# --------------------------------------------------
# LOAD AND VALIDATE INPUTS
# --------------------------------------------------
required_files = [MASTER, COVERAGE, ACTUALS, PILOT]
for file in required_files:
    if not file.exists():
        raise FileNotFoundError(f"Missing required file: {file}")

df = pd.read_csv(MASTER)
coverage = pd.read_csv(COVERAGE)
actuals = pd.read_csv(ACTUALS)
pilot = pd.read_csv(PILOT)

companies = {"INFY", "PERSISTENT", "BSOFT"}
quarters = {
    f"FY{fy}_Q{q}"
    for fy in [23, 24]
    for q in range(1, 5)
}

assert set(df["ticker"].dropna().unique()) == companies
assert set(coverage["ticker"].dropna().unique()) == companies
assert len(coverage) == 24
assert not df["candidate_id"].duplicated().any()

print("INPUT VALIDATION PASSED")
print("Candidate rows:", len(df))
print("Transcript coverage rows:", len(coverage))

# --------------------------------------------------
# 1. TRANSCRIPT COVERAGE
# --------------------------------------------------
coverage_summary = (
    coverage.groupby("ticker")
    .agg(
        available=("file_present", "sum"),
        expected=("quarter", "count")
    )
    .reset_index()
)

coverage_summary["coverage_pct"] = (
    coverage_summary["available"] /
    coverage_summary["expected"] * 100
)

coverage_summary.to_csv(
    RESULTS / "coverage_summary.csv", index=False
)

# --------------------------------------------------
# 2. CANDIDATE STATEMENT VOLUME
# --------------------------------------------------
candidate_counts = (
    df.groupby(["ticker", "quarter"])
    .size()
    .reset_index(name="candidate_count")
)

candidate_counts.to_csv(
    RESULTS / "candidate_volume_by_quarter.csv",
    index=False
)

for ticker in sorted(companies):
    subset = candidate_counts[
        candidate_counts["ticker"] == ticker
    ].copy()

    subset["quarter"] = pd.Categorical(
        subset["quarter"],
        categories=sorted(quarters),
        ordered=True
    )
    subset = subset.sort_values("quarter")

    plt.figure(figsize=(10, 4))
    plt.bar(subset["quarter"].astype(str),
            subset["candidate_count"])
    plt.title(f"{ticker}: candidate statements by quarter")
    plt.xlabel("Fiscal quarter")
    plt.ylabel("Extracted candidate count")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(
        FIGURES / f"{ticker.lower()}_candidate_volume.png",
        dpi=200
    )
    plt.close()

# --------------------------------------------------
# 3. REVIEW STATUS COUNTS
# --------------------------------------------------
decision_columns = [
    "review_decision",
    "guidance_decision",
    "explanation_decision",
    "communication_decision"
]

review_rows = []

for column in decision_columns:
    if column not in df.columns:
        continue

    counts = (
        df.groupby(["ticker", column], dropna=False)
        .size()
        .reset_index(name="row_count")
    )
    counts["review_field"] = column
    counts = counts.rename(columns={column: "decision"})
    review_rows.append(counts)

if review_rows:
    pd.concat(review_rows, ignore_index=True).to_csv(
        RESULTS / "review_decision_counts.csv",
        index=False
    )

# --------------------------------------------------
# 4. STRICT MANAGEMENT REVIEW SUBSET
# --------------------------------------------------
# Exact INCLUDE only. INCLUDE_REVIEW is not treated
# as verified. Explicit management role required.
strict_parts = []

module_settings = [
    ("GENERAL", "review_decision", "verified_speaker_role"),
    ("GUIDANCE", "guidance_decision", "verified_speaker_role"),
    ("EXPLANATION", "explanation_decision",
     "explanation_speaker_role"),
    ("COMMUNICATION", "communication_decision",
     "communication_speaker_role")
]

for module, decision_col, role_col in module_settings:
    if decision_col not in df.columns or role_col not in df.columns:
        continue

    mask = (
        df[decision_col].astype(str).str.upper().eq("INCLUDE")
        & df[role_col].astype(str).str.upper().eq("MANAGEMENT")
    )

    selected = df.loc[mask].copy()
    selected["reviewed_module"] = module
    strict_parts.append(selected)

if strict_parts:
    strict = pd.concat(strict_parts, ignore_index=True)
    strict.to_csv(
        RESULTS / "strict_management_review_subset.csv",
        index=False
    )

    strict_counts = (
        strict.groupby(["ticker", "quarter", "reviewed_module"])
        .size()
        .reset_index(name="strict_include_count")
    )
    strict_counts.to_csv(
        RESULTS / "strict_management_review_counts.csv",
        index=False
    )
else:
    strict = pd.DataFrame()
    print("No strict INCLUDE + MANAGEMENT rows found.")

# --------------------------------------------------
# 5. FINANCIAL ACTUALS COMPLETENESS
# --------------------------------------------------
actuals_summary = (
    actuals.groupby("ticker")
    .agg(
        quarters=("quarter", "count"),
        revenue_growth_values=("revenue_growth_cc_pct", "count"),
        ebit_margin_values=("ebit_margin_pct", "count")
    )
    .reset_index()
)

actuals_summary.to_csv(
    RESULTS / "actuals_completeness.csv",
    index=False
)

# --------------------------------------------------
# 6. PILOT GUIDANCE: SCORE ONLY MATCHED NUMERIC ROWS
# --------------------------------------------------
if "module" in pilot.columns:
    guidance = pilot[pilot["module"].astype(str).str.upper()
                     == "GUIDANCE"].copy()
else:
    guidance = pd.DataFrame()

if not guidance.empty:
    numeric_cols = [
        "guidance_value_low",
        "guidance_value_high",
        "actual_value"
    ]

    for col in numeric_cols:
        guidance[col] = pd.to_numeric(
            guidance[col], errors="coerce"
        )

    scorable = guidance.dropna(subset=numeric_cols).copy()

    if not scorable.empty:
        scorable["within_guidance_range"] = (
            scorable["actual_value"].between(
                scorable["guidance_value_low"],
                scorable["guidance_value_high"]
            )
        )

        scorable.to_csv(
            RESULTS / "scorable_pilot_guidance.csv",
            index=False
        )
    else:
        print("No numeric guidance rows with matched actuals.")
else:
    print("No guidance observations available in pilot file.")

# --------------------------------------------------
# 7. FINAL STATUS
# --------------------------------------------------
print("\nPILOT ANALYSIS COMPLETE")
print("Companies:", sorted(companies))
print("Expected transcripts:", len(coverage))
print("Candidate statements:", len(df))
print("Strict review rows:", len(strict))
print("\nResults saved to:", RESULTS)
print("Figures saved to:", FIGURES)
print(
    "\nIMPORTANT: Candidate counts are not validated "
    "research findings. Forecast accuracy requires "
    "source-verified actuals and correctly matched "
    "guidance target periods."
)
