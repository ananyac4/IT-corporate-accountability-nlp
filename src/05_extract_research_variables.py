"""
05_extract_research_variables.py

Purpose:
  Read data/processed/transcripts_text.csv and extract sentence-level candidates
  for the three qualitative research modules:
    1) Explanation persistence
    2) Forecast accountability / management guidance
    3) Communication specificity / certainty / uncertainty

IMPORTANT:
  This is a candidate-generation and annotation-support tool, NOT an automatic
  truth labeler. It preserves source transcript filename, company, quarter,
  speaker (where detected), and page marker (where detected). Human review is
  required before using any extracted sentence as a research observation.

Run from project root:
  python src/05_extract_research_variables.py
"""
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "transcripts_text.csv"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# Terms are deliberately broad to retrieve candidate passages for review.
EXPLANATION_TERMS = {
    "DEMAND_AND_MACRO": [
        "macroeconomic", "macro environment", "uncertainty", "uncertain",
        "client spending", "customer spending", "demand environment",
        "recession", "geopolitical", "budget constraints", "discretionary spend"
    ],
    "DEAL_DELAY_AND_CONVERSION": [
        "deal delay", "delayed deal", "deal conversion", "deal closure",
        "ramp up", "ramp-up", "project start", "deferred", "postponed",
        "decision making", "decision-making", "client approval"
    ],
    "MARGIN_AND_COST_PRESSURE": [
        "margin pressure", "margin headwind", "wage hike", "salary increase",
        "subcontractor", "utilization", "utilisation", "bench", "onsite cost",
        "offshore mix", "cost optimization", "cost optimisation"
    ],
    "TALENT_AND_ATTRITION": [
        "attrition", "hiring", "talent supply", "joining ratio",
        "employee costs", "retention", "fresher hiring"
    ],
    "EXECUTION_AND_DELIVERY": [
        "execution", "delivery issue", "productivity", "transition",
        "transformation program", "implementation delay", "ramp down",
        "ramp-down"
    ],
}

GUIDANCE_TERMS = [
    "guidance", "outlook", "we expect", "we believe", "we anticipate",
    "we target", "we aim", "we aspire", "we are confident",
    "should deliver", "will deliver", "growth of", "margin of",
    "remain flat", "improve", "decline", "mid-teens", "high single digit",
    "low single digit", "double digit", "basis points", "bps"
]

CERTAINTY_TERMS = [
    "confident", "committed", "will", "definitely", "certain", "expect",
    "strongly believe", "on track", "we remain confident", "we are sure"
]
UNCERTAINTY_TERMS = [
    "may", "might", "could", "uncertain", "challenging", "subject to",
    "depending on", "difficult to predict", "visibility", "cautious",
    "not sure", "not certain", "unknown", "volatile"
]
SPECIFICITY_TERMS = [
    "percent", "%", "basis points", "bps", "million", "billion",
    "crore", "rupees", "dollar", "quarter", "financial year", "by q"
]

# Speaker labels in extracted transcripts commonly appear as "Speaker Name: words".
SPEAKER_LINE = re.compile(r"^\s*([A-Z][A-Za-z.'’ -]{1,70}):\s*(.*)$")
PAGE_LINE = re.compile(r"\bPage\s+(\d+)\s+of\s+\d+\b", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).replace("\x00", " ").strip()

def sentence_rows(full_text):
    """Split transcript into sentence candidates while carrying speaker/page context."""
    current_speaker = ""
    current_page = ""
    current_parts = []
    rows = []

    def flush():
        nonlocal current_parts
        joined = " ".join(current_parts).strip()
        current_parts = []
        if not joined:
            return
        # Avoid tiny fragments and obvious boilerplate.
        for sentence in SENTENCE_SPLIT.split(joined):
            sentence = re.sub(r"\s+", " ", sentence).strip(" \t-")
            if len(sentence) < 45:
                continue
            if sentence.lower().startswith(("moderator:", "thank you for joining")):
                continue
            rows.append({
                "speaker": current_speaker,
                "page": current_page,
                "sentence": sentence
            })

    for raw_line in full_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        page_match = PAGE_LINE.search(line)
        if page_match:
            flush()
            current_page = page_match.group(1)
            # Don't lose text that may occur after a page marker.
            line = PAGE_LINE.sub("", line).strip()
            if not line:
                continue

        speaker_match = SPEAKER_LINE.match(line)
        if speaker_match:
            flush()
            current_speaker = speaker_match.group(1).strip()
            tail = speaker_match.group(2).strip()
            if tail:
                current_parts.append(tail)
        else:
            # Skip repeated document headers / footers.
            low = line.lower()
            if "earnings call" in low and len(line) < 100:
                continue
            if re.match(r"^page\s+\d+\s+of\s+\d+$", low):
                continue
            current_parts.append(line)

    flush()
    return rows

def find_categories(sentence):
    low = sentence.lower()
    categories = []
    for category, terms in EXPLANATION_TERMS.items():
        if any(term in low for term in terms):
            categories.append(category)
    return categories

def has_any(sentence, terms):
    low = sentence.lower()
    return any(term in low for term in terms)

def likely_numeric(sentence):
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|percent|bps|basis points|million|billion|crore)?", sentence, re.I))

def build_candidates():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT}. First run src/02_extract_transcripts.py."
        )

    df = pd.read_csv(INPUT)
    required = {"ticker", "fy", "quarter", "filename", "text"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"transcripts_text.csv is missing columns: {sorted(missing)}")

    candidates = []
    for _, record in df.iterrows():
        ticker = clean_text(record.get("ticker"))
        fy = clean_text(record.get("fy"))
        quarter = clean_text(record.get("quarter"))
        filename = clean_text(record.get("filename"))
        full_text = clean_text(record.get("text"))

        for item in sentence_rows(full_text):
            sentence = item["sentence"]
            explanation_categories = find_categories(sentence)
            guidance_flag = has_any(sentence, GUIDANCE_TERMS)
            certainty_flag = has_any(sentence, CERTAINTY_TERMS)
            uncertainty_flag = has_any(sentence, UNCERTAINTY_TERMS)
            specificity_flag = has_any(sentence, SPECIFICITY_TERMS) or likely_numeric(sentence)

            # Keep sentences relevant to at least one of the study modules.
            if not (explanation_categories or guidance_flag or certainty_flag
                    or uncertainty_flag or specificity_flag):
                continue

            module_tags = []
            if explanation_categories:
                module_tags.append("EXPLANATION_PERSISTENCE")
            if guidance_flag or (likely_numeric(sentence) and
                                 has_any(sentence, ["expect", "target", "outlook", "guidance", "will", "should"])):
                module_tags.append("FORECAST_ACCOUNTABILITY")
            if certainty_flag or uncertainty_flag or specificity_flag:
                module_tags.append("COMMUNICATION_CHANGE")

            candidates.append({
                "ticker": ticker,
                "quarter_key": f"{fy}_{quarter}",
                "filename": filename,
                "speaker": item["speaker"],
                "page": item["page"],
                "module_tags": "|".join(module_tags),
                "explanation_categories": "|".join(explanation_categories),
                "guidance_candidate": int(guidance_flag),
                "certainty_term_present": int(certainty_flag),
                "uncertainty_term_present": int(uncertainty_flag),
                "specificity_or_numeric_present": int(specificity_flag),
                "numeric_value_present": int(likely_numeric(sentence)),
                "sentence": sentence,
                "review_status": "PENDING",
                "reviewer_decision": "",
                "review_notes": ""
            })

    result = pd.DataFrame(candidates)
    out_path = OUT / "research_sentence_candidates.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    # Separate module-specific files make manual review easier.
    if not result.empty:
        for tag, filename in [
            ("EXPLANATION_PERSISTENCE", "explanation_candidates.csv"),
            ("FORECAST_ACCOUNTABILITY", "guidance_candidates.csv"),
            ("COMMUNICATION_CHANGE", "communication_candidates.csv"),
        ]:
            subset = result[result["module_tags"].fillna("").str.contains(tag, regex=False)]
            subset.to_csv(OUT / filename, index=False, encoding="utf-8-sig")

    # Compact coverage summary of processed transcript files and candidate counts.
    summary = result.groupby("ticker").agg(
        candidate_sentence_count=("sentence", "count"),
        transcript_count=("filename", "nunique"),
        explanation_candidate_count=("explanation_categories", lambda s: int((s.fillna("") != "").sum())),
        guidance_candidate_count=("guidance_candidate", "sum"),
        communication_candidate_count=("module_tags", lambda s: int(s.fillna("").str.contains("COMMUNICATION_CHANGE", regex=False).sum()))
    ).reset_index()
    summary.to_csv(OUT / "candidate_coverage_summary.csv", index=False)

    print(f"Candidate sentences: {len(result)}")
    print(f"Saved: {out_path}")
    print(f"Saved module-specific candidate CSVs and candidate_coverage_summary.csv")
    print("Review candidates against the original PDF before using them as research observations.")

if __name__ == "__main__":
    build_candidates()
