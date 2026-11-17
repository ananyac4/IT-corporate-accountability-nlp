"""
06_refine_guidance_and_speakers.py

Purpose
-------
Refines keyword-generated transcript candidates without pretending that
speaker names or keyword matches are ground truth.

First run:
  - reads data/processed/guidance_candidates.csv
  - creates speaker_roles_template.csv for manual speaker-role review
  - creates candidate_classification_review.csv

After reviewing the role template:
  - fill speaker_role with MANAGEMENT / ANALYST / MODERATOR / IR / OTHER
  - save it as data/processed/speaker_roles.csv
  - rerun this script

The script then produces:
  - refined_guidance_candidates.csv  (verified management + forward-looking)
  - unverified_guidance_review.csv   (potential guidance, speaker not verified)
  - refined_explanation_candidates.csv
  - speaker_review_summary.csv
  - candidate_classification_review.csv

No missing values are fabricated. A blank speaker role is treated as UNVERIFIED.
"""

from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

INPUT = PROCESSED / "guidance_candidates.csv"
ROLE_FILE = PROCESSED / "speaker_roles.csv"
ROLE_TEMPLATE = PROCESSED / "speaker_roles_template.csv"

FORWARD_PATTERNS = [
    r"\bwe expect\b", r"\bwe anticipate\b", r"\bwe believe\b",
    r"\bwe aim\b", r"\bwe target\b", r"\bwe are targeting\b",
    r"\bwe are guiding\b", r"\bour guidance\b", r"\bour outlook\b",
    r"\bgoing forward\b", r"\bin the coming quarters?\b",
    r"\bfor (?:the )?(?:next|coming|full) quarter\b",
    r"\bfor fy\s?20\d{2}\b", r"\bfor q[1-4]\b",
    r"\bwe should see\b", r"\bwe see\b", r"\bwe plan to\b",
    r"\bwe intend to\b", r"\bwill remain\b", r"\bremain flat\b",
    r"\bflat to\b", r"\bmore than\s+\d", r"\bat least\s+\d",
    r"\bin the range of\b", r"\bguidance\b", r"\boutlook\b",
    r"\bexpect(?:ed|ing)? to\b", r"\banticipat(?:e|ing)\b",
]

HISTORICAL_PATTERNS = [
    r"\brevenue was\b", r"\brevenues were\b", r"\bwe reported\b",
    r"\bwe delivered\b", r"\bstood at\b", r"\bwas at\b",
    r"\bregistered a\b", r"\bgrew by\b", r"\bincreased by\b",
    r"\bdeclined by\b", r"\bdecreased by\b", r"\bfor the quarter ended\b",
    r"\bduring the quarter\b", r"\byoy growth\b", r"\bsequential growth\b",
    r"\bnet profit was\b", r"\boperating margin was\b",
]

EXPLANATION_PATTERNS = {
    "DEMAND_AND_MACRO": [
        r"\bmacro(?:economic)?\b", r"\bweak demand\b", r"\bslowdown\b",
        r"\bclient spending\b", r"\buncertainty\b", r"\bgeopolitical\b",
    ],
    "DEAL_CONVERSION_AND_PIPELINE": [
        r"\bdeal(?:s)?\b", r"\bpipeline\b", r"\bdeal conversion\b",
        r"\bdefer(?:red|ral)?\b", r"\bdecision making\b",
    ],
    "TALENT_AND_ATTRITION": [
        r"\battrition\b", r"\bhiring\b", r"\butili[sz]ation\b",
        r"\bsubcontract(?:or|ing)\b", r"\bheadcount\b",
    ],
    "CLIENT_OR_PROJECT_SPECIFIC": [
        r"\bclient specific\b", r"\bproject delay\b", r"\b ramp down\b",
        r"\btransition\b", r"\bexecution issue\b",
    ],
    "CURRENCY_AND_PRICING": [
        r"\bcurrency\b", r"\bforeign exchange\b", r"\bpricing\b",
        r"\bprice erosion\b", r"\b rupee\b",
    ],
}

def first_existing_column(df, options, required=False):
    for col in options:
        if col in df.columns:
            return col
    if required:
        raise ValueError(f"Required column not found. Tried: {options}. Found: {list(df.columns)}")
    return None

def clean_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

def any_match(text, patterns):
    return any(re.search(p, text, flags=re.I) for p in patterns)

def classify_sentence(sentence):
    s = clean_text(sentence)
    forward = any_match(s, FORWARD_PATTERNS)
    historical = any_match(s, HISTORICAL_PATTERNS)

    # A specific forward-looking construction takes precedence over generic
    # numerical/historical phrasing, but ambiguous rows remain reviewable.
    if forward and not historical:
        statement_type = "FORWARD_LOOKING"
    elif historical and not forward:
        statement_type = "HISTORICAL_ACTUAL"
    elif forward and historical:
        statement_type = "MIXED_OR_AMBIGUOUS"
    else:
        statement_type = "OTHER"

    guidance_strength = "POTENTIAL_GUIDANCE" if (
        forward and (
            re.search(r"\b(guidance|outlook|target|expect|anticipate|aim|range|flat|more than|at least)\b", s, re.I)
            or re.search(r"\bq[1-4]\b|\bfy\s?20\d{2}\b", s, re.I)
        )
    ) else "NOT_GUIDANCE"

    explanation_tags = [
        tag for tag, patterns in EXPLANATION_PATTERNS.items()
        if any_match(s, patterns)
    ]

    return statement_type, guidance_strength, ";".join(explanation_tags)

def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Missing {INPUT}. Run src/05_extract_research_variables.py first."
        )

    df = pd.read_csv(INPUT)
    sentence_col = first_existing_column(
        df, ["sentence", "text", "candidate_sentence", "clean_sentence"], required=True
    )
    ticker_col = first_existing_column(df, ["ticker", "symbol"], required=True)
    speaker_col = first_existing_column(df, ["speaker", "speaker_name", "participant"])
    fy_col = first_existing_column(df, ["fy", "financial_year"])
    q_col = first_existing_column(df, ["q", "quarter"])
    page_col = first_existing_column(df, ["page", "page_number"])

    df["sentence_clean"] = df[sentence_col].map(clean_text)
    classified = df["sentence_clean"].apply(classify_sentence)
    df[["statement_type", "refined_guidance_status", "refined_explanation_tags"]] = pd.DataFrame(
        classified.tolist(), index=df.index
    )

    if speaker_col is None:
        df["speaker_clean"] = ""
    else:
        df["speaker_clean"] = df[speaker_col].map(clean_text)

    # Build one row per ticker/speaker. No name-based role guessing.
    speaker_summary = (
        df.groupby([ticker_col, "speaker_clean"], dropna=False)
          .agg(
              candidate_rows=("sentence_clean", "size"),
              sample_sentences=("sentence_clean", lambda x: " || ".join(x.head(3).tolist()))
          )
          .reset_index()
          .rename(columns={ticker_col: "ticker", "speaker_clean": "speaker"})
    )
    speaker_summary["speaker_role"] = ""
    speaker_summary["reviewer_verified"] = ""
    speaker_summary["review_notes"] = ""

    if not ROLE_TEMPLATE.exists():
        speaker_summary.to_csv(ROLE_TEMPLATE, index=False, encoding="utf-8-sig")

    # Role mapping is only applied after explicit human review.
    if ROLE_FILE.exists():
        roles = pd.read_csv(ROLE_FILE).fillna("")
        needed = {"ticker", "speaker", "speaker_role"}
        if not needed.issubset(roles.columns):
            raise ValueError(f"{ROLE_FILE.name} must contain columns: {sorted(needed)}")
        roles["ticker"] = roles["ticker"].astype(str).str.upper().str.strip()
        roles["speaker"] = roles["speaker"].map(clean_text)
        roles["speaker_role"] = roles["speaker_role"].astype(str).str.upper().str.strip()
        role_map = roles.drop_duplicates(["ticker", "speaker"], keep="last")
        df["ticker_key"] = df[ticker_col].astype(str).str.upper().str.strip()
        df = df.merge(
            role_map[["ticker", "speaker", "speaker_role"]],
            left_on=["ticker_key", "speaker_clean"],
            right_on=["ticker", "speaker"],
            how="left",
            suffixes=("", "_rolemap")
        )
        df["speaker_role"] = df["speaker_role"].fillna("").replace("", "UNVERIFIED")
    else:
        df["speaker_role"] = "UNVERIFIED"

    # Strict inclusion: only explicitly reviewed MANAGEMENT speakers.
    management = df[df["speaker_role"].eq("MANAGEMENT")].copy()
    management_guidance = management[
        management["refined_guidance_status"].eq("POTENTIAL_GUIDANCE")
        & management["statement_type"].isin(["FORWARD_LOOKING", "MIXED_OR_AMBIGUOUS"])
    ].copy()
    unverified_guidance = df[
        df["speaker_role"].eq("UNVERIFIED")
        & df["refined_guidance_status"].eq("POTENTIAL_GUIDANCE")
    ].copy()
    management_explanations = management[
        management["refined_explanation_tags"].astype(str).str.len().gt(0)
    ].copy()

    # Useful review file: all rows with classification and source context.
    review_cols = [
        c for c in [
            ticker_col, fy_col, q_col, page_col, speaker_col,
            sentence_col, "statement_type", "refined_guidance_status",
            "refined_explanation_tags", "speaker_role"
        ] if c and c in df.columns
    ]
    df[review_cols].to_csv(
        PROCESSED / "candidate_classification_review.csv",
        index=False, encoding="utf-8-sig"
    )

    management_guidance.to_csv(
        PROCESSED / "refined_guidance_candidates.csv",
        index=False, encoding="utf-8-sig"
    )
    unverified_guidance.to_csv(
        PROCESSED / "unverified_guidance_review.csv",
        index=False, encoding="utf-8-sig"
    )
    management_explanations.to_csv(
        PROCESSED / "refined_explanation_candidates.csv",
        index=False, encoding="utf-8-sig"
    )

    # Refresh summary with role counts from the applied mapping.
    role_counts = (
        df.groupby([ticker_col, "speaker_role"])
          .size().unstack(fill_value=0).reset_index()
          .rename(columns={ticker_col: "ticker"})
    )
    role_counts.to_csv(
        PROCESSED / "speaker_review_summary.csv",
        index=False, encoding="utf-8-sig"
    )

    print("Refinement complete.")
    print(f"Input candidate rows: {len(df):,}")
    print(f"Verified management guidance candidates: {len(management_guidance):,}")
    print(f"Unverified-speaker guidance candidates for review: {len(unverified_guidance):,}")
    print(f"Verified management explanation candidates: {len(management_explanations):,}")
    if not ROLE_FILE.exists():
        print(f"\nNEXT: Review {ROLE_TEMPLATE.name}; fill speaker_role and reviewer_verified.")
        print(f"Save the reviewed file as {ROLE_FILE.name}, then rerun this script.")
    print("\nReminder: candidates require manual source verification before analysis.")

if __name__ == "__main__":
    main()
