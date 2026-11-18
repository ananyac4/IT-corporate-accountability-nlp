
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# ==========================================================
# 1. PROJECT PATHS
# ==========================================================

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

# Use the pilot observations file if present.
# Otherwise, fall back to the file already in your project.
PILOT_OPTIONS = [
    DATA / "pilot_verified_observations.csv",
    DATA / "pilot_verified_observations_filled.csv",
    DATA / "pilot_guidance_verified.csv"
]

PILOT = next((p for p in PILOT_OPTIONS if p.exists()), None)

# ==========================================================
# 2. CHECK INPUT FILES
# ==========================================================

required = [MASTER, COVERAGE, ACTUALS]

missing = [str(p) for p in required if not p.exists()]

if missing:
    raise FileNotFoundError(
        "Missing required input files:\n" + "\n".join(missing)
    )

df = pd.read_csv(MASTER)
coverage = pd.read_csv(COVERAGE)
actuals = pd.read_csv(ACTUALS)

pilot = pd.read_csv(PILOT) if PILOT else pd.DataFrame()

companies = ["INFY", "PERSISTENT", "BSOFT"]

print("\n========== INPUT VALIDATION ==========")
print("Master candidate rows:", len(df))
print("Coverage rows:", len(coverage))
print("Financial actual rows:", len(actuals))
print("Pilot observations file:",
      PILOT.name if PILOT else "Not available - skipped")

# Required master columns
required_master_columns = [
    "ticker", "quarter", "statement_excerpt"
]

for col in required_master_columns:
    if col not in df.columns:
        raise ValueError(f"Master dataset missing column: {col}")

# Check companies
print("\nCompany distribution:")
print(df["ticker"].value_counts(dropna=False))

# Check duplicate candidate IDs if available
if "candidate_id" in df.columns:
    print("Duplicate candidate IDs:",
          df["candidate_id"].duplicated().sum())

# ==========================================================
# 3. TRANSCRIPT COVERAGE
# ==========================================================

coverage_summary = (
    coverage.groupby("ticker")
    .agg(
        expected_quarters=("quarter", "count"),
        available_transcripts=("file_present", "sum")
    )
    .reset_index()
)

coverage_summary["coverage_percentage"] = (
    coverage_summary["available_transcripts"] /
    coverage_summary["expected_quarters"] * 100
)

coverage_summary.to_csv(
    RESULTS / "coverage_summary.csv", index=False
)

print("\nCoverage summary:")
print(coverage_summary.to_string(index=False))

# ==========================================================
# 4. CANDIDATE STATEMENT COUNTS
# ==========================================================

candidate_counts = (
    df.groupby(["ticker", "quarter"], dropna=False)
    .size()
    .reset_index(name="candidate_count")
)

candidate_counts.to_csv(
    RESULTS / "candidate_volume_by_quarter.csv",
    index=False
)

company_summary = (
    df.groupby("ticker")
    .size()
    .reset_index(name="total_candidate_statements")
)

company_summary.to_csv(
    RESULTS / "candidate_volume_by_company.csv",
    index=False
)

# ==========================================================
# 5. CANDIDATE VOLUME CHARTS
# ==========================================================

quarter_order = [
    f"FY{fy}_Q{q}"
    for fy in [23, 24]
    for q in range(1, 5)
]

for ticker in companies:

    subset = candidate_counts[
        candidate_counts["ticker"] == ticker
    ].copy()

    subset["quarter"] = pd.Categorical(
        subset["quarter"],
        categories=quarter_order,
        ordered=True
    )

    subset = subset.sort_values("quarter")

    plt.figure(figsize=(11, 5))

    plt.bar(
        subset["quarter"].astype(str),
        subset["candidate_count"]
    )

    plt.title(
        f"{ticker}: Candidate Statements Across FY23-FY24"
    )
    plt.xlabel("Fiscal Quarter")
    plt.ylabel("Number of Candidate Statements")
    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.savefig(
        FIGURES / f"{ticker.lower()}_candidate_volume.png",
        dpi=300
    )

    plt.close()

# ==========================================================
# 6. REVIEW DECISION DISTRIBUTION
# ==========================================================

decision_columns = [
    "review_decision",
    "guidance_decision",
    "explanation_decision",
    "communication_decision"
]

review_results = []

for col in decision_columns:

    if col not in df.columns:
        continue

    temp = (
        df.groupby(
            ["ticker", col],
            dropna=False
        )
        .size()
        .reset_index(name="count")
    )

    temp = temp.rename(columns={col: "decision"})
    temp["review_module"] = col

    review_results.append(temp)

if review_results:

    review_summary = pd.concat(
        review_results,
        ignore_index=True
    )

    review_summary.to_csv(
        RESULTS / "review_decision_counts.csv",
        index=False
    )

# ==========================================================
# 7. STRICTLY REVIEWED MANAGEMENT STATEMENTS
# ==========================================================

strict_parts = []

module_settings = [
    ("GENERAL", "review_decision"),
    ("GUIDANCE", "guidance_decision"),
    ("EXPLANATION", "explanation_decision"),
    ("COMMUNICATION", "communication_decision")
]

for module, decision_col in module_settings:

    if decision_col not in df.columns:
        continue

    # Use verified role when available.
    role_columns = [
        "verified_speaker_role",
        "speaker_role_guess"
    ]

    role_col = next(
        (c for c in role_columns if c in df.columns),
        None
    )

    if role_col is None:
        continue

    mask = (
        df[decision_col]
        .astype(str)
        .str.upper()
        .eq("INCLUDE")
        &
        df[role_col]
        .astype(str)
        .str.upper()
        .eq("MANAGEMENT")
    )

    selected = df.loc[mask].copy()

    if not selected.empty:
        selected["reviewed_module"] = module
        strict_parts.append(selected)

if strict_parts:

    strict = pd.concat(
        strict_parts,
        ignore_index=True
    )

    strict.to_csv(
        RESULTS / "strict_management_review_subset.csv",
        index=False
    )

    strict_counts = (
        strict.groupby(
            ["ticker", "quarter", "reviewed_module"]
        )
        .size()
        .reset_index(name="verified_candidate_count")
    )

    strict_counts.to_csv(
        RESULTS / "strict_management_review_counts.csv",
        index=False
    )

    print("\nStrictly included management rows:", len(strict))

else:

    strict = pd.DataFrame()

    print(
        "\nNo rows met the strict INCLUDE + MANAGEMENT criteria."
    )

# ==========================================================
# 8. FINANCIAL ACTUALS COMPLETENESS
# ==========================================================

actuals_required = [
    "ticker",
    "quarter",
    "revenue_growth_cc_pct",
    "ebit_margin_pct"
]

for col in actuals_required:
    if col not in actuals.columns:
        raise ValueError(
            f"Actuals dataset missing column: {col}"
        )

actuals_summary = (
    actuals.groupby("ticker")
    .agg(
        quarters=("quarter", "count"),
        revenue_values=("revenue_growth_cc_pct", "count"),
        ebit_margin_values=("ebit_margin_pct", "count")
    )
    .reset_index()
)

actuals_summary.to_csv(
    RESULTS / "actuals_completeness.csv",
    index=False
)

print("\nFinancial actuals completeness:")
print(actuals_summary.to_string(index=False))

# ==========================================================
# 9. PILOT GUIDANCE OBSERVATIONS (OPTIONAL)
# ==========================================================

if not pilot.empty:

    print("\nPilot observation columns:")
    print(pilot.columns.tolist())

    if "module" in pilot.columns:

        guidance = pilot[
            pilot["module"]
            .astype(str)
            .str.upper()
            .eq("GUIDANCE")
        ].copy()

        numeric_cols = [
            "guidance_value_low",
            "guidance_value_high",
            "actual_value"
        ]

        if all(c in guidance.columns for c in numeric_cols):

            for col in numeric_cols:
                guidance[col] = pd.to_numeric(
                    guidance[col],
                    errors="coerce"
                )

            scorable = guidance.dropna(
                subset=numeric_cols
            ).copy()

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

                print(
                    "Scorable pilot guidance rows:",
                    len(scorable)
                )

            else:
                print(
                    "No pilot guidance rows have all three "
                    "numeric values."
                )

        else:
            print(
                "Pilot guidance schema differs from expected "
                "columns. Scoring skipped."
            )

    else:
        print(
            "Pilot file has no module column. "
            "Guidance scoring skipped."
        )

else:
    print("\nPilot observations unavailable. Optional section skipped.")

# ==========================================================
# 10. FINAL REPORT
# ==========================================================

print("\n========================================")
print("THREE-COMPANY PILOT ANALYSIS COMPLETED")
print("========================================")

print("Companies:", companies)
print("Candidate statements:", len(df))
print("Transcript coverage records:", len(coverage))
print("Financial actual records:", len(actuals))

print("\nResults directory:")
print(RESULTS)

print("\nFigures directory:")
print(FIGURES)

print(
    "\nNOTE: Candidate volume and automated classifications "
    "are exploratory. They are not verified research findings."
)

print(
    "Forecast accountability requires verified management "
    "guidance matched to the correct subsequent financial actuals."
)
