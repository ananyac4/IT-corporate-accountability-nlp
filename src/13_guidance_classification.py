
"""
Script 13: Guidance Classification

Purpose:
1. Classify existing guidance candidates.
2. Separate quantitative and qualitative guidance.
3. Identify historical performance statements.
4. Detect possible analyst questions.
5. Flag ambiguous and general commentary.
6. Generate review files without modifying source datasets.

Input:
data/processed/unverified_guidance_review.csv

Outputs:
data/processed/guidance_classified.csv
data/processed/guidance_review_required.csv
data/processed/guidance_classification_summary.csv
"""

from pathlib import Path
import re
import pandas as pd


# --------------------------------------------------
# 1. PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    ROOT / "data" / "processed" /
    "unverified_guidance_review.csv"
)

OUTPUT_DIR = ROOT / "data" / "processed"

CLASSIFIED_FILE = OUTPUT_DIR / "guidance_classified.csv"
REVIEW_FILE = OUTPUT_DIR / "guidance_review_required.csv"
SUMMARY_FILE = OUTPUT_DIR / "guidance_classification_summary.csv"


# --------------------------------------------------
# 2. KEYWORD PATTERNS
# --------------------------------------------------

FUTURE_PATTERN = re.compile(
    r"\b("
    r"expect|expects|expected|"
    r"will|shall|"
    r"anticipate|anticipates|"
    r"forecast|forecasts|"
    r"outlook|"
    r"going forward|"
    r"next quarter|next year|"
    r"remain|remains|"
    r"project|projects|"
    r"plan to|plans to|"
    r"aim to|aims to|"
    r"target|targets|"
    r"believe|believes"
    r")\b",
    re.IGNORECASE
)

NUMERIC_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?\s*%|"
    r"\d+(?:\.\d+)?\s*(?:bps|basis points|crores|cr|million|billion)|"
    r"more than \d+|"
    r"at least \d+|"
    r"above \d+|"
    r"below \d+)",
    re.IGNORECASE
)

QUESTION_PATTERN = re.compile(
    r"\?|"
    r"\b("
    r"could you|can you|would you|"
    r"do you expect|"
    r"what is your|"
    r"what are your|"
    r"how do you|"
    r"how should we|"
    r"your thoughts on|"
    r"would like to understand"
    r")\b",
    re.IGNORECASE
)

HISTORICAL_PATTERN = re.compile(
    r"\b("
    r"reported|stood at|"
    r"registered|achieved|"
    r"delivered|recorded|"
    r"grew by|declined by|"
    r"was at|were at|"
    r"has increased|"
    r"has decreased|"
    r"for the quarter|"
    r"during the quarter"
    r")\b",
    re.IGNORECASE
)

GENERIC_PATTERN = re.compile(
    r"\b("
    r"thank you|"
    r"good morning|"
    r"good afternoon|"
    r"welcome everyone|"
    r"moving to the next question|"
    r"next question|"
    r"operator instructions"
    r")\b",
    re.IGNORECASE
)

GUIDANCE_METRICS = {
    "REVENUE": re.compile(
        r"\b(revenue|growth|sales|turnover)\b", re.I
    ),
    "MARGIN": re.compile(
        r"\b(margin|ebit|ebitda|operating profit|"
        r"profitability)\b", re.I
    ),
    "DEMAND": re.compile(
        r"\b(demand|pipeline|order book|deal wins|"
        r"bookings|clients)\b", re.I
    ),
    "COST": re.compile(
        r"\b(cost|expense|utilization|attrition|"
        r"subcontracting|hiring)\b", re.I
    ),
    "CASH_FLOW": re.compile(
        r"\b(cash flow|free cash flow|working capital)\b", re.I
    ),
    "OTHER": re.compile(r".*", re.I)
}


# --------------------------------------------------
# 3. CLASSIFICATION FUNCTION
# --------------------------------------------------

def classify_statement(row):

    sentence = str(row.get("sentence_clean", "")).strip()

    if not sentence or sentence.lower() == "nan":
        return pd.Series({
            "classification": "AMBIGUOUS",
            "guidance_metric": "UNKNOWN",
            "has_future_signal": False,
            "has_numeric_target": False,
            "classification_reason": "Empty or missing sentence",
            "manual_review_required": True
        })

    has_future = bool(FUTURE_PATTERN.search(sentence))
    has_numeric = bool(NUMERIC_PATTERN.search(sentence))
    is_question = bool(QUESTION_PATTERN.search(sentence))
    is_historical = bool(HISTORICAL_PATTERN.search(sentence))
    is_generic = bool(GENERIC_PATTERN.search(sentence))

    # Identify possible metric
    metric = "OTHER"

    for metric_name, pattern in GUIDANCE_METRICS.items():
        if metric_name != "OTHER" and pattern.search(sentence):
            metric = metric_name
            break

    # Classification priority

    if is_generic:
        category = "GENERAL_COMMENTARY"
        reason = "Generic or procedural transcript language"

    elif is_question:
        category = "ANALYST_QUESTION"
        reason = "Question format or analyst-style questioning language"

    elif has_future and has_numeric:
        category = "QUANTITATIVE_GUIDANCE"
        reason = "Future-oriented language and numerical information"

    elif has_future:
        category = "QUALITATIVE_GUIDANCE"
        reason = "Future-oriented language without a detected numeric target"

    elif is_historical:
        category = "HISTORICAL_PERFORMANCE"
        reason = "Historical performance or reported result language"

    else:
        category = "GENERAL_COMMENTARY"
        reason = "No strong future-guidance signal detected"

    # Conservative ambiguity flag
    ambiguous = (
        category in ["GENERAL_COMMENTARY", "ANALYST_QUESTION"]
        or (
            has_future
            and is_historical
            and category not in [
                "QUANTITATIVE_GUIDANCE",
                "QUALITATIVE_GUIDANCE"
            ]
        )
    )

    # Speaker identity is not established by sentence classification.
    speaker_role = str(row.get("speaker_role", "UNVERIFIED"))

    speaker_unverified = (
        speaker_role.upper() in ["UNVERIFIED", "NAN", ""]
    )

    review_required = ambiguous or speaker_unverified

    return pd.Series({
        "classification": category,
        "guidance_metric": metric,
        "has_future_signal": has_future,
        "has_numeric_target": has_numeric,
        "classification_reason": reason,
        "manual_review_required": review_required
    })


# --------------------------------------------------
# 4. MAIN EXECUTION
# --------------------------------------------------

def main():

    print("=" * 65)
    print("SCRIPT 13: GUIDANCE CLASSIFICATION")
    print("=" * 65)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_FILE)

    print("\nInput loaded successfully.")
    print("Records:", len(df))

    # Classify every record
    results = df.apply(classify_statement, axis=1)

    classified = pd.concat(
        [df.reset_index(drop=True), results.reset_index(drop=True)],
        axis=1
    )

    # Preserve existing review status.
    # These records are candidates, not verified guidance.
    classified["verification_status"] = "PENDING_MANUAL_REVIEW"

    # Separate records requiring review
    review = classified[
        classified["manual_review_required"]
    ].copy()

    # Classification summary
    summary = (
        classified
        .groupby(
            ["ticker", "classification"],
            dropna=False
        )
        .size()
        .reset_index(name="record_count")
    )

    # Save outputs
    classified.to_csv(CLASSIFIED_FILE, index=False)
    review.to_csv(REVIEW_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)

    # Display results
    print("\nCLASSIFICATION SUMMARY")
    print("-" * 65)

    print(
        classified["classification"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nMANUAL REVIEW REQUIRED:", len(review))

    print("\nCOMPANY COVERAGE:")
    print("Companies:", classified["ticker"].nunique())
    print(
        "Company-quarter combinations:",
        classified[["ticker", "quarter_key"]]
        .drop_duplicates()
        .shape[0]
    )

    print("\nOUTPUT FILES")
    print("-" * 65)
    print(CLASSIFIED_FILE)
    print(REVIEW_FILE)
    print(SUMMARY_FILE)

    print("\nClassification completed.")
    print("Original input file was not modified.")


if __name__ == "__main__":
    main()
