
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# 15_FINAL_PILOT_ANALYSIS.PY
# Project: Corporate Claims vs. Financial Reality
# Pilot: INFY, PERSISTENT, BSOFT | FY23 Q1 - FY24 Q4
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "outputs" / "final_pilot"
RESULTS = OUTPUT / "results"
FIGURES = OUTPUT / "figures"

RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

FILES = {
    "master": PROCESSED / "master_candidate_statements_3company_pilot.csv",
    "coverage": PROCESSED / "transcript_coverage_3company_8q.csv",
    "template": PROCESSED / "actuals_template_3company_pilot.csv",
    "financial": PROCESSED / "financial_actuals_BSOFT_PERSISTENT_FY23_FY24_combined.csv",
    "observations": PROCESSED / "pilot_verified_observations_filled.csv",
}

for name, path in FILES.items():
    if not path.exists():
        raise FileNotFoundError(
            f"Missing input '{name}': {path}\n"
            "Check that the required CSV is in data/processed/."
        )

def read_csv(path):
    return pd.read_csv(path, low_memory=False)

def save_csv(df, name):
    path = RESULTS / name
    df.to_csv(path, index=False)
    print(f"Saved: {path}")

def clean_text(series):
    return series.fillna("").astype(str).str.strip()

def quarter_order(value):
    # FY23_Q1 -> (23, 1)
    try:
        fy, q = str(value).replace("FY", "").split("_Q")
        return int(fy), int(q)
    except Exception:
        return (999, 999)

# ------------------------------------------------------------
# 1. LOAD AND VALIDATE INPUTS
# ------------------------------------------------------------

master = read_csv(FILES["master"])
coverage = read_csv(FILES["coverage"])
actual_template = read_csv(FILES["template"])
financial = read_csv(FILES["financial"])
observations = read_csv(FILES["observations"])

print("\n========== INPUT VALIDATION ==========")
print("Candidate statements:", len(master))
print("Coverage records:", len(coverage))
print("Financial actual rows supplied:", len(financial))
print("Pilot observations:", len(observations))

print("\nCandidate statements by company:")
print(master.groupby("ticker").size())

print("\nTranscript coverage:")
print(
    coverage.groupby("ticker")
    .agg(
        quarters=("quarter", "nunique"),
        available=("file_present", "sum")
    )
)

# Candidate IDs must be unique.
if "candidate_id" in master.columns:
    duplicates = master["candidate_id"].duplicated().sum()
    print("\nDuplicate candidate IDs:", duplicates)
    if duplicates:
        raise ValueError("Duplicate candidate IDs found. Resolve before analysis.")

# ------------------------------------------------------------
# 2. PREPARE ACTUALS DATASET
# ------------------------------------------------------------

# Preserve separate definitions:
# - CC YoY growth
# - reported YoY growth
# - CC QoQ growth
# - EBIT margin
# - EBITDA margin
#
# Never substitute EBITDA margin for EBIT margin.
# Never substitute reported growth for CC growth.

financial["ticker"] = clean_text(financial["ticker"]).str.upper()
financial["quarter"] = clean_text(financial["quarter"])

actuals = actual_template.copy()
actuals["ticker"] = clean_text(actuals["ticker"]).str.upper()
actuals["quarter"] = clean_text(actuals["quarter"])

financial_columns = [
    "ticker",
    "quarter",
    "revenue_growth_cc_yoy_pct",
    "revenue_growth_reported_yoy_pct",
    "revenue_growth_cc_qoq_pct",
    "ebit_margin_pct",
    "ebitda_margin_pct",
    "source_file",
    "source_page_pdf",
    "verification_status",
    "notes",
]

financial = financial[
    [c for c in financial_columns if c in financial.columns]
]

actuals = actuals.merge(
    financial,
    on=["ticker", "quarter"],
    how="left",
    suffixes=("", "_financial")
)

# Retain original template columns and add the more detailed financial fields.
for col in [
    "revenue_growth_cc_yoy_pct",
    "revenue_growth_reported_yoy_pct",
    "revenue_growth_cc_qoq_pct",
    "ebitda_margin_pct",
    "source_file",
    "source_page_pdf",
]:
    if col not in actuals.columns:
        actuals[col] = np.nan

# Where source financial data provides an EBIT margin, use it.
# Do not overwrite the template's EBIT field with EBITDA.
if "ebit_margin_pct_financial" in actuals.columns:
    actuals["ebit_margin_pct"] = actuals[
        "ebit_margin_pct_financial"
    ].combine_first(actuals["ebit_margin_pct"])

# Add source status without falsely promoting extracted data to verified.
if "verification_status_financial" in actuals.columns:
    actuals["financial_source_status"] = actuals[
        "verification_status_financial"
    ]
else:
    actuals["financial_source_status"] = "MISSING"

actuals["financial_source_status"] = (
    actuals["financial_source_status"].fillna("MISSING")
)

save_csv(actuals, "01_three_company_actuals_merged.csv")

# Financial completeness report
completeness = (
    actuals.groupby("ticker")
    .agg(
        quarters=("quarter", "nunique"),
        cc_yoy_values=("revenue_growth_cc_yoy_pct", "count"),
        reported_yoy_values=("revenue_growth_reported_yoy_pct", "count"),
        cc_qoq_values=("revenue_growth_cc_qoq_pct", "count"),
        ebit_values=("ebit_margin_pct", "count"),
        ebitda_values=("ebitda_margin_pct", "count"),
    )
    .reset_index()
)

save_csv(completeness, "02_financial_actuals_completeness.csv")

# ------------------------------------------------------------
# 3. TRANSCRIPT COVERAGE ANALYSIS
# ------------------------------------------------------------

coverage["ticker"] = clean_text(coverage["ticker"]).str.upper()
coverage["quarter"] = clean_text(coverage["quarter"])

coverage_summary = (
    coverage.groupby("ticker")
    .agg(
        expected_quarters=("quarter", "nunique"),
        available_transcripts=("file_present", "sum"),
        total_characters=("characters", "sum"),
    )
    .reset_index()
)

coverage_summary["coverage_pct"] = (
    coverage_summary["available_transcripts"]
    / coverage_summary["expected_quarters"] * 100
)

save_csv(coverage_summary, "03_transcript_coverage_summary.csv")

# ------------------------------------------------------------
# 4. CANDIDATE STATEMENT VOLUME
# ------------------------------------------------------------

master["ticker"] = clean_text(master["ticker"]).str.upper()
master["quarter"] = clean_text(master["quarter"])

candidate_by_company = (
    master.groupby("ticker")
    .size()
    .reset_index(name="candidate_statements")
)

candidate_by_quarter = (
    master.groupby(["ticker", "quarter"])
    .size()
    .reset_index(name="candidate_statements")
)

candidate_by_quarter["_sort"] = candidate_by_quarter["quarter"].apply(
    quarter_order
)
candidate_by_quarter = (
    candidate_by_quarter.sort_values(["ticker", "_sort"])
    .drop(columns="_sort")
)

save_csv(candidate_by_company, "04_candidate_volume_by_company.csv")
save_csv(candidate_by_quarter, "05_candidate_volume_by_quarter.csv")

# ------------------------------------------------------------
# 5. STRICT MANAGEMENT STATEMENT SUBSET
# ------------------------------------------------------------

# IMPORTANT:
# Use only explicitly verified speaker roles.
# Do not fall back to speaker_role_guess.

if "verified_speaker_role" not in master.columns:
    raise ValueError("verified_speaker_role column is missing.")

role = clean_text(master["verified_speaker_role"]).str.upper()
decision = clean_text(master.get("review_decision", pd.Series("", index=master.index))).str.upper()

strict_management = master[
    (role == "MANAGEMENT") &
    (decision == "INCLUDE")
].copy()

save_csv(strict_management, "06_verified_management_statements.csv")

management_counts = (
    strict_management.groupby(["ticker", "quarter"])
    .size()
    .reset_index(name="verified_management_statements")
)

management_counts["_sort"] = management_counts["quarter"].apply(quarter_order)
management_counts = (
    management_counts.sort_values(["ticker", "_sort"])
    .drop(columns="_sort")
)

save_csv(management_counts, "07_verified_management_counts.csv")

# ------------------------------------------------------------
# 6. EXPLANATION PERSISTENCE
# ------------------------------------------------------------

# Use only explicitly included explanation annotations.
# This measures annotated recurrence candidates, not automatically
# verified semantic equivalence.

if "explanation_decision" in master.columns:
    explanation_decision = clean_text(
        master["explanation_decision"]
    ).str.upper()
else:
    explanation_decision = pd.Series("", index=master.index)

explanations = master[
    explanation_decision == "INCLUDE"
].copy()

if len(explanations):
    theme_col = (
        "explanation_theme"
        if "explanation_theme" in explanations.columns
        else "explanation_category"
    )

    explanations["theme"] = clean_text(explanations[theme_col])
    explanations = explanations[explanations["theme"] != ""]

    explanation_recurrence = (
        explanations.groupby(["ticker", "theme"])
        .agg(
            candidate_statements=("candidate_id", "count"),
            quarters_observed=("quarter", "nunique"),
            quarters=("quarter", lambda x: "; ".join(sorted(
                set(x), key=quarter_order
            ))),
        )
        .reset_index()
        .sort_values(
            ["ticker", "quarters_observed", "candidate_statements"],
            ascending=[True, False, False]
        )
    )
else:
    explanation_recurrence = pd.DataFrame(
        columns=[
            "ticker", "theme", "candidate_statements",
            "quarters_observed", "quarters"
        ]
    )

save_csv(explanations, "08_included_explanation_candidates.csv")
save_csv(explanation_recurrence, "09_explanation_recurrence.csv")

# ------------------------------------------------------------
# 7. COMMUNICATION CHANGE
# ------------------------------------------------------------

# Include only rows explicitly marked INCLUDE.
# INCLUDE_REVIEW and NEEDS_CONTEXT remain excluded.

if "communication_decision" in master.columns:
    communication_decision = clean_text(
        master["communication_decision"]
    ).str.upper()
else:
    communication_decision = pd.Series("", index=master.index)

communication = master[
    communication_decision == "INCLUDE"
].copy()

save_csv(communication, "10_included_communication_candidates.csv")

communication_summary = pd.DataFrame()

if len(communication):
    group_cols = ["ticker"]

    for col in [
        "communication_certainty",
        "communication_specificity",
    ]:
        if col in communication.columns:
            temp = (
                communication.groupby(["ticker", col])
                .size()
                .reset_index(name="statement_count")
            )
            temp = temp.rename(columns={col: "classification"})
            temp["feature"] = col
            communication_summary = pd.concat(
                [communication_summary, temp],
                ignore_index=True
            )

save_csv(communication_summary, "11_communication_feature_counts.csv")

# ------------------------------------------------------------
# 8. FORECAST ACCOUNTABILITY
# ------------------------------------------------------------

# Only score an observation if:
# 1. It is explicitly marked VERIFIED_SOURCE_AND_MATCHED.
# 2. It has a numerical low and high guidance range.
# 3. It has a numerical actual value.
#
# Do not score source-only observations or unresolved matches.

observations["review_status_clean"] = clean_text(
    observations["review_status"]
).str.upper()

for col in [
    "guidance_value_low",
    "guidance_value_high",
    "actual_value",
]:
    observations[col] = pd.to_numeric(
        observations[col], errors="coerce"
    )

scorable = observations[
    (observations["review_status_clean"] == "VERIFIED_SOURCE_AND_MATCHED") &
    observations["guidance_value_low"].notna() &
    observations["guidance_value_high"].notna() &
    observations["actual_value"].notna()
].copy()

if len(scorable):
    scorable["guidance_midpoint"] = (
        scorable["guidance_value_low"] +
        scorable["guidance_value_high"]
    ) / 2

    scorable["absolute_midpoint_error"] = (
        scorable["actual_value"] -
        scorable["guidance_midpoint"]
    ).abs()

    scorable["within_guidance_range"] = (
        (scorable["actual_value"] >= scorable["guidance_value_low"]) &
        (scorable["actual_value"] <= scorable["guidance_value_high"])
    )

    scorable["signed_midpoint_error"] = (
        scorable["actual_value"] -
        scorable["guidance_midpoint"]
    )

    scorable["absolute_range_distance"] = np.where(
        scorable["actual_value"] < scorable["guidance_value_low"],
        scorable["guidance_value_low"] - scorable["actual_value"],
        np.where(
            scorable["actual_value"] > scorable["guidance_value_high"],
            scorable["actual_value"] - scorable["guidance_value_high"],
            0
        )
    )

    forecast_summary = (
        scorable.groupby(["ticker", "metric"])
        .agg(
            scored_observations=("actual_value", "count"),
            within_range_count=("within_guidance_range", "sum"),
            mean_absolute_midpoint_error=(
                "absolute_midpoint_error", "mean"
            ),
            mean_absolute_range_distance=(
                "absolute_range_distance", "mean"
            ),
        )
        .reset_index()
    )

    forecast_summary["within_range_rate_pct"] = (
        forecast_summary["within_range_count"] /
        forecast_summary["scored_observations"] * 100
    )
else:
    forecast_summary = pd.DataFrame(
        columns=[
            "ticker", "metric", "scored_observations",
            "within_range_count", "mean_absolute_midpoint_error",
            "mean_absolute_range_distance", "within_range_rate_pct"
        ]
    )

save_csv(scorable, "12_scorable_forecast_observations.csv")
save_csv(forecast_summary, "13_forecast_accountability_summary.csv")

# Save observations that still require review.
unscored = observations[
    ~observations.index.isin(scorable.index)
].copy()

save_csv(unscored, "14_guidance_observations_not_scored.csv")

# ------------------------------------------------------------
# 9. PLOTS
# ------------------------------------------------------------

def save_bar_plot(data, x, y, title, xlabel, ylabel, filename):
    if data.empty:
        print("Skipped empty plot:", filename)
        return

    plt.figure(figsize=(10, 5))
    plt.bar(data[x].astype(str), data[y])
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(FIGURES / filename, dpi=300)
    plt.close()
    print("Saved figure:", FIGURES / filename)

# Figure 1: Candidate volume by company
save_bar_plot(
    candidate_by_company,
    "ticker",
    "candidate_statements",
    "Research Candidate Statements by Company",
    "Company",
    "Candidate statement count",
    "01_candidate_volume_by_company.png"
)

# Figure 2: Candidate volume by quarter
for ticker in sorted(candidate_by_quarter["ticker"].unique()):
    subset = candidate_by_quarter[
        candidate_by_quarter["ticker"] == ticker
    ]

    save_bar_plot(
        subset,
        "quarter",
        "candidate_statements",
        f"{ticker}: Candidate Statements by Quarter",
        "Fiscal quarter",
        "Candidate statement count",
        f"02_{ticker.lower()}_candidate_volume_by_quarter.png"
    )

# Figure 3: Verified management statements by company
if not management_counts.empty:
    mgmt_company = (
        strict_management.groupby("ticker")
        .size()
        .reset_index(name="verified_management_statements")
    )

    save_bar_plot(
        mgmt_company,
        "ticker",
        "verified_management_statements",
        "Explicitly Verified Management Statements",
        "Company",
        "Statement count",
        "03_verified_management_statements.png"
    )

# Figure 4: Explanation recurrence
if not explanation_recurrence.empty:
    top_themes = (
        explanation_recurrence.sort_values(
            "quarters_observed", ascending=False
        ).head(15)
    )

    plt.figure(figsize=(11, 6))
    labels = top_themes["ticker"] + " - " + top_themes["theme"]
    plt.barh(labels, top_themes["quarters_observed"])
    plt.title("Explanation Themes Observed Across Quarters")
    plt.xlabel("Number of distinct quarters")
    plt.ylabel("Company and explanation theme")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(
        FIGURES / "04_explanation_recurrence.png",
        dpi=300
    )
    plt.close()

# Figure 5: Financial actuals completeness
if not completeness.empty:
    plt.figure(figsize=(10, 5))
    x = np.arange(len(completeness))
    width = 0.25

    plt.bar(
        x - width,
        completeness["cc_yoy_values"],
        width,
        label="CC YoY revenue"
    )
    plt.bar(
        x,
        completeness["ebit_values"],
        width,
        label="EBIT margin"
    )
    plt.bar(
        x + width,
        completeness["ebitda_values"],
        width,
        label="EBITDA margin"
    )

    plt.xticks(x, completeness["ticker"])
    plt.ylabel("Number of quarters with values")
    plt.title("Financial Actuals Completeness by Company")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        FIGURES / "05_financial_actuals_completeness.png",
        dpi=300
    )
    plt.close()

# Figure 6: Forecast accountability, only if scorable rows exist
if not forecast_summary.empty:
    save_bar_plot(
        forecast_summary,
        "ticker",
        "within_range_rate_pct",
        "Management Guidance: Actuals Within Guidance Range",
        "Company",
        "Within-range rate (%)",
        "06_forecast_within_range_rate.png"
    )

# ------------------------------------------------------------
# 10. RESEARCH QUALITY / LIMITATIONS REPORT
# ------------------------------------------------------------

quality = pd.DataFrame([
    ["Transcript records", len(coverage),
     "Coverage records in the pilot"],
    ["Available transcripts",
     int(coverage["file_present"].sum()),
     "Expected target: 24"],
    ["Candidate statements", len(master),
     "Automated candidate pool; not all are verified findings"],
    ["Explicitly verified management statements",
     len(strict_management),
     "verified_speaker_role=MANAGEMENT and review_decision=INCLUDE"],
    ["Included explanation candidates",
     len(explanations),
     "Requires semantic review before claiming recurrence"],
    ["Included communication candidates",
     len(communication),
     "Explicit INCLUDE only"],
    ["Financial actual rows", len(financial),
     "Only the supplied BSOFT and Persistent financial files"],
    ["Scorable guidance observations", len(scorable),
     "Verified source, target match, numerical range and actual"],
], columns=["measure", "value", "interpretation"])

save_csv(quality, "15_research_quality_summary.csv")

# ------------------------------------------------------------
# 11. PRINT FINAL STATUS
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("FINAL THREE-COMPANY PILOT ANALYSIS FINISHED")
print("=" * 60)

print("\nTranscript coverage:")
print(coverage_summary.to_string(index=False))

print("\nFinancial actuals completeness:")
print(completeness.to_string(index=False))

print("\nStrict management statement count:", len(strict_management))
print("Included explanation candidates:", len(explanations))
print("Included communication candidates:", len(communication))
print("Scorable forecast observations:", len(scorable))

print("\nResults folder:")
print(RESULTS)

print("\nFigures folder:")
print(FIGURES)

print("\nIMPORTANT RESEARCH LIMITATIONS:")
print("1. Candidate statements are not automatically verified findings.")
print("2. Only explicitly verified management roles are counted as management.")
print("3. Explanation recurrence requires semantic validation.")
print("4. Communication labels are exploratory annotations.")
print("5. Forecast accountability is scored only for verified matched observations.")
print("6. Missing financial actuals are not imputed.")
print("7. EBITDA margin is never substituted for EBIT margin.")

print("\nDo not report exploratory counts as final empirical findings.")
