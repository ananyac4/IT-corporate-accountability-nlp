
"""
Script 14: Improved Guidance Classification

Purpose:
1. Improve identification of management guidance.
2. Exclude forward-looking legal disclaimers.
3. Identify explicit statements that formal guidance is not provided.
4. Detect analyst questions and prompts more carefully.
5. Separate quantitative and qualitative guidance.
6. Flag mixed historical/future statements.
7. Preserve Script 13 classifications for comparison.

Input:
data/processed/guidance_classified.csv

Outputs:
data/processed/guidance_classified_v2.csv
data/processed/guidance_potential_v2.csv
data/processed/guidance_review_required_v2.csv
data/processed/guidance_classification_summary_v2.csv

Original files are never modified.
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
    "guidance_classified.csv"
)

OUTPUT_DIR = ROOT / "data" / "processed"

CLASSIFIED_FILE = OUTPUT_DIR / "guidance_classified_v2.csv"
POTENTIAL_FILE = OUTPUT_DIR / "guidance_potential_v2.csv"
REVIEW_FILE = OUTPUT_DIR / "guidance_review_required_v2.csv"
SUMMARY_FILE = OUTPUT_DIR / "guidance_classification_summary_v2.csv"


# --------------------------------------------------
# 2. CLASSIFICATION PATTERNS
# --------------------------------------------------

DISCLAIMER_PATTERN = re.compile(
    r"forward[- ]looking statement|"
    r"safe harbor|"
    r"subject to risks and uncertainties|"
    r"actual results may differ|"
    r"not a guarantee of future performance|"
    r"should not be relied upon as a guarantee",
    re.I
)

NO_GUIDANCE_PATTERN = re.compile(
    r"we do not give guidance|"
    r"we don't give guidance|"
    r"we are not giving guidance|"
    r"we cannot give guidance|"
    r"we can't give guidance|"
    r"we have not given guidance|"
    r"no formal guidance|"
    r"not provide guidance|"
    r"not providing guidance",
    re.I
)

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
    r"believe|believes|"
    r"should be able to|"
    r"likely to|"
    r"we see|"
    r"we believe|"
    r"we are confident|"
    r"going to"
    r")\b",
    re.I
)

NUMERIC_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*%|"
    r"\b\d+(?:\.\d+)?\s*(?:bps|basis points|"
    r"crores|cr|million|billion)\b|"
    r"\bmore than\s+\d+|"
    r"\bat least\s+\d+|"
    r"\babove\s+\d+|"
    r"\bbelow\s+\d+",
    re.I
)

ANALYST_LANGUAGE_PATTERN = re.compile(
    r"\b("
    r"you will have to|"
    r"you would have to|"
    r"you need to|"
    r"would you expect|"
    r"do you expect|"
    r"could you explain|"
    r"can you explain|"
    r"my question is|"
    r"my first question|"
    r"my second question|"
    r"just wanted to understand|"
    r"i would like to understand|"
    r"your thoughts on"
    r")\b",
    re.I
)

INTERROGATIVE_PATTERN = re.compile(
    r"\b("
    r"could you|"
    r"can you|"
    r"would you|"
    r"do you expect|"
    r"what is your|"
    r"what are your|"
    r"how do you|"
    r"how should we|"
    r"should we expect|"
    r"are you expecting|"
    r"would like to understand"
    r")\b",
    re.I
)

HISTORICAL_PATTERN = re.compile(
    r"\b("
    r"reported|"
    r"stood at|"
    r"registered|"
    r"achieved|"
    r"delivered|"
    r"recorded|"
    r"grew by|"
    r"declined by|"
    r"was at|"
    r"were at|"
    r"has increased|"
    r"has decreased|"
    r"last quarter|"
    r"previous quarter|"
    r"year on year|"
    r"year-over-year|"
    r"quarter on quarter|"
    r"for the quarter|"
    r"during the quarter"
    r")\b",
    re.I
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
    re.I
)

GUIDANCE_METRICS = {
    "REVENUE": re.compile(
        r"\b(revenue|sales|turnover|topline|top line)\b", re.I
    ),
    "MARGIN": re.compile(
        r"\b(margin|ebit|ebitda|operating profit|profitability)\b",
        re.I
    ),
    "DEMAND": re.compile(
        r"\b(demand|pipeline|order book|deal wins|bookings|clients)\b",
        re.I
    ),
    "COST": re.compile(
        r"\b(cost|expense|utilization|attrition|"
        r"subcontracting|hiring)\b",
        re.I
    ),
    "CASH_FLOW": re.compile(
        r"\b(cash flow|free cash flow|working capital)\b",
        re.I
    ),
    "OTHER": re.compile(r".*", re.I)
}


# --------------------------------------------------
# 3. HELPER FUNCTIONS
# --------------------------------------------------

def get_text(row):
    """Get the best available sentence text."""

    text = row.get("sentence_clean", "")

    if pd.isna(text) or not str(text).strip():
        text = row.get("sentence", "")

    if pd.isna(text):
        return ""

    return str(text).strip()


def identify_metric(sentence):
    """Identify the first matching financial/operational metric."""

    for metric_name, pattern in GUIDANCE_METRICS.items():

        if metric_name == "OTHER":
            continue

        if pattern.search(sentence):
            return metric_name

    return "OTHER"


def identify_speaker_type(row):
    """
    Use an existing speaker_role only if it contains
    an explicit role label. Do not infer identity from names.
    """

    role = str(row.get("speaker_role", "")).strip().upper()

    if role in ["NAN", "", "UNVERIFIED"]:
        return "UNVERIFIED"

    if "ANALYST" in role:
        return "ANALYST"

    if "MANAGEMENT" in role or "EXECUTIVE" in role:
        return "MANAGEMENT"

    if "OPERATOR" in role or "MODERATOR" in role:
        return "MODERATOR"

    return "OTHER_OR_UNVERIFIED"


# --------------------------------------------------
# 4. IMPROVED CLASSIFICATION FUNCTION
# --------------------------------------------------

def classify_statement(row):

    sentence = get_text(row)

    if not sentence:
        return pd.Series({
            "initial_classification": row.get("classification", ""),
            "classification_v2": "AMBIGUOUS",
            "guidance_metric_v2": "UNKNOWN",
            "has_future_signal_v2": False,
            "has_numeric_value_v2": False,
            "speaker_type_v2": "UNVERIFIED",
            "classification_reason_v2": "Empty or missing sentence",
            "manual_review_required_v2": True
        })

    # Preserve original Script 13 classification
    initial_classification = row.get("classification", "")

    has_disclaimer = bool(DISCLAIMER_PATTERN.search(sentence))
    has_no_guidance = bool(NO_GUIDANCE_PATTERN.search(sentence))
    has_future = bool(FUTURE_PATTERN.search(sentence))
    has_numeric = bool(NUMERIC_PATTERN.search(sentence))
    has_historical = bool(HISTORICAL_PATTERN.search(sentence))
    has_generic = bool(GENERIC_PATTERN.search(sentence))

    has_analyst_language = bool(
        ANALYST_LANGUAGE_PATTERN.search(sentence)
    )

    has_interrogative_language = bool(
        INTERROGATIVE_PATTERN.search(sentence)
    )

    has_question_mark = "?" in sentence

    speaker_type = identify_speaker_type(row)
    metric = identify_metric(sentence)

    # --------------------------------------------------
    # CLASSIFICATION PRIORITY
    # --------------------------------------------------

    if has_disclaimer:

        category = "FORWARD_LOOKING_DISCLAIMER"
        reason = "Legal or forward-looking disclaimer language"

    elif has_generic:

        category = "GENERAL_COMMENTARY"
        reason = "Generic or procedural transcript language"

    elif (
        speaker_type == "ANALYST"
        and (has_question_mark or has_analyst_language
             or has_interrogative_language)
    ):

        category = "ANALYST_QUESTION"
        reason = "Speaker role identifies analyst asking a question"

    elif (
        has_analyst_language
        or has_interrogative_language
        or has_question_mark
    ):

        category = "QUESTION_OR_ANALYST_PROMPT"
        reason = "Question or analyst-style prompt; speaker role needs verification"

    elif has_no_guidance:

        category = "MANAGEMENT_OUTLOOK_NO_FORMAL_GUIDANCE"
        reason = "Explicit statement that formal guidance is not provided"

    elif has_future and has_historical:

        category = "MIXED_OR_AMBIGUOUS"
        reason = "Sentence contains both future and historical performance signals"

    elif has_future and has_numeric:

        category = "QUANTITATIVE_GUIDANCE"
        reason = "Future-oriented language and numerical information"

    elif has_future:

        category = "QUALITATIVE_GUIDANCE"
        reason = "Future-oriented language without detected numerical target"

    elif has_historical:

        category = "HISTORICAL_PERFORMANCE"
        reason = "Historical performance or reported result language"

    else:

        category = "GENERAL_COMMENTARY"
        reason = "No strong future-guidance signal detected"

    # --------------------------------------------------
    # MANUAL REVIEW RULES
    # --------------------------------------------------

    guidance_categories = [
        "QUANTITATIVE_GUIDANCE",
        "QUALITATIVE_GUIDANCE",
        "MANAGEMENT_OUTLOOK_NO_FORMAL_GUIDANCE"
    ]

    review_required = (
        category in [
            "AMBIGUOUS",
            "MIXED_OR_AMBIGUOUS",
            "QUESTION_OR_ANALYST_PROMPT",
            "ANALYST_QUESTION"
        ]
        or speaker_type == "UNVERIFIED"
        or category in guidance_categories
    )

    # If a statement looks like guidance but speaker is not verified,
    # retain it as a candidate, not confirmed management guidance.

    return pd.Series({
        "initial_classification": initial_classification,
        "classification_v2": category,
        "guidance_metric_v2": metric,
        "has_future_signal_v2": has_future,
        "has_numeric_value_v2": has_numeric,
        "speaker_type_v2": speaker_type,
        "classification_reason_v2": reason,
        "manual_review_required_v2": review_required
    })


# --------------------------------------------------
# 5. MAIN EXECUTION
# --------------------------------------------------

def main():

    print("=" * 70)
    print("SCRIPT 14: IMPROVED GUIDANCE CLASSIFICATION")
    print("=" * 70)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    print("\nInput loaded successfully.")
    print("Records:", len(df))

    # Apply improved classification
    results = df.apply(classify_statement, axis=1)

    classified = pd.concat(
        [
            df.reset_index(drop=True),
            results.reset_index(drop=True)
        ],
        axis=1
    )

    classified["verification_status_v2"] = (
        "PENDING_MANUAL_REVIEW"
    )

    # Potential guidance candidates
    potential_categories = [
        "QUANTITATIVE_GUIDANCE",
        "QUALITATIVE_GUIDANCE",
        "MANAGEMENT_OUTLOOK_NO_FORMAL_GUIDANCE"
    ]

    potential = classified[
        classified["classification_v2"].isin(
            potential_categories
        )
    ].copy()

    # Manual review records
    review = classified[
        classified["manual_review_required_v2"]
    ].copy()

    # Classification summary
    summary = (
        classified
        .groupby(
            ["ticker", "classification_v2"],
            dropna=False
        )
        .size()
        .reset_index(name="record_count")
    )

    # Save new outputs
    classified.to_csv(CLASSIFIED_FILE, index=False)
    potential.to_csv(POTENTIAL_FILE, index=False)
    review.to_csv(REVIEW_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)

    # --------------------------------------------------
    # DISPLAY RESULTS
    # --------------------------------------------------

    print("\nIMPROVED CLASSIFICATION SUMMARY")
    print("-" * 70)

    print(
        classified["classification_v2"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nPOTENTIAL GUIDANCE RECORDS:", len(potential))
    print("MANUAL REVIEW REQUIRED:", len(review))

    print("\nSPEAKER TYPE SUMMARY")
    print("-" * 70)

    print(
        classified["speaker_type_v2"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nCOMPANY COVERAGE")
    print("-" * 70)

    print("Companies:", classified["ticker"].nunique())

    print(
        "Company-quarter combinations:",
        classified[["ticker", "quarter_key"]]
        .drop_duplicates()
        .shape[0]
    )

    print("\nOUTPUT FILES")
    print("-" * 70)

    print(CLASSIFIED_FILE)
    print(POTENTIAL_FILE)
    print(REVIEW_FILE)
    print(SUMMARY_FILE)

    print("\nScript 14 completed successfully.")
    print("Original Script 13 outputs were not modified.")


if __name__ == "__main__":
    main()
