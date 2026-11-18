
from pathlib import Path
import pandas as pd

# ============================================================
# 1. PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

MANIFEST_PATH = (
    ROOT / "data" / "processed" / "extraction_manifest.csv"
)

TEXT_DIR = (
    ROOT / "data" / "processed" / "transcripts_text"
)

OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. EXPECTED COMPANIES
# ============================================================

COMPANIES = [
    "BSOFT",
    "COFORGE",
    "CYIENT",
    "HAPPSTMNDS",
    "HCLTECH",
    "INFY",
    "INTELLECT",
    "KPITTECH",
    "LTIM",
    "MASTEK",
    "MPHASIS",
    "NEWGEN",
    "OFSS",
    "PERSISTENT",
    "SONATSOFTW",
    "TATAELXSI",
    "TCS",
    "TECHM",
    "WIPRO",
    "ZENSARTECH"
]


# ============================================================
# 3. EXPECTED QUARTERS
# FY23 Q1 THROUGH FY27 Q1 = 17 QUARTERS
# ============================================================

QUARTERS = [
    "FY23_Q1",
    "FY23_Q2",
    "FY23_Q3",
    "FY23_Q4",

    "FY24_Q1",
    "FY24_Q2",
    "FY24_Q3",
    "FY24_Q4",

    "FY25_Q1",
    "FY25_Q2",
    "FY25_Q3",
    "FY25_Q4",

    "FY26_Q1",
    "FY26_Q2",
    "FY26_Q3",
    "FY26_Q4",

    "FY27_Q1"
]

print("=" * 75)
print("QUARTER CONFIGURATION CHECK")
print("=" * 75)

print("Number of companies:", len(COMPANIES))
print("Number of quarters:", len(QUARTERS))
print("First quarter:", QUARTERS[0])
print("Last quarter:", QUARTERS[-1])

EXPECTED_TOTAL = len(COMPANIES) * len(QUARTERS)

print("Expected company-quarter records:", EXPECTED_TOTAL)

if len(COMPANIES) != 20:
    raise ValueError("Expected exactly 20 companies.")

if len(QUARTERS) != 17:
    raise ValueError("Expected exactly 17 quarters.")

if EXPECTED_TOTAL != 340:
    raise ValueError("Expected exactly 340 records.")


# ============================================================
# 4. KNOWN INVALID DOCUMENTS
# ============================================================

# This document contains an exchange filing cover letter,
# not the actual WIPRO earnings-call transcript.

INVALID_DOCUMENTS = {
    "WIPRO_FY23_Q4_transcript.pdf": {
        "classification": "WRONG_DOCUMENT_TYPE",
        "reason": (
            "Exchange filing cover letter instead of "
            "actual earnings-call transcript"
        )
    }
}


# ============================================================
# 5. LOAD EXTRACTION MANIFEST
# ============================================================

print("\n" + "=" * 75)
print("LOADING EXTRACTION MANIFEST")
print("=" * 75)

if not MANIFEST_PATH.exists():
    raise FileNotFoundError(
        f"Manifest not found: {MANIFEST_PATH}"
    )

manifest = pd.read_csv(MANIFEST_PATH)

required_columns = [
    "filename",
    "ticker",
    "fy",
    "quarter",
    "text_file",
    "status"
]

missing_columns = [
    col for col in required_columns
    if col not in manifest.columns
]

if missing_columns:
    raise ValueError(
        f"Missing required columns: {missing_columns}"
    )

for col in ["filename", "ticker", "fy", "quarter", "text_file", "status"]:
    manifest[col] = manifest[col].fillna("").astype(str).str.strip()

manifest["quarter_key"] = (
    manifest["fy"] + "_" + manifest["quarter"]
)

print("Manifest records:", len(manifest))


# ============================================================
# 6. CHECK DOCUMENTS AND TEXT FILES
# ============================================================

print("\n" + "=" * 75)
print("CHECKING DOCUMENTS AND EXTRACTED TEXT")
print("=" * 75)

document_results = []

for _, row in manifest.iterrows():

    filename = row["filename"]
    ticker = row["ticker"]
    quarter_key = row["quarter_key"]

    relative_path = row["text_file"].replace("\\", "/")

    text_path = ROOT / relative_path

    result = {
        "ticker": ticker,
        "quarter_key": quarter_key,
        "filename": filename,
        "text_file": relative_path,
        "extraction_status": row["status"],
        "document_classification": "",
        "file_exists": text_path.exists(),
        "character_count": 0,
        "word_count": 0,
        "usable_for_coverage": False,
        "review_reason": ""
    }

    # Check known invalid document
    if filename in INVALID_DOCUMENTS:

        result["document_classification"] = (
            INVALID_DOCUMENTS[filename]["classification"]
        )

        result["review_reason"] = (
            INVALID_DOCUMENTS[filename]["reason"]
        )

    # Check missing text file
    elif not text_path.exists():

        result["document_classification"] = "MISSING_TEXT_FILE"

        result["review_reason"] = (
            "Extracted text file does not exist"
        )

    # Check extraction status
    elif row["status"].upper() != "OK":

        result["document_classification"] = "EXTRACTION_ERROR"

        result["review_reason"] = (
            f"Extraction status: {row['status']}"
        )

    else:

        try:
            content = text_path.read_text(
                encoding="utf-8",
                errors="replace"
            )

            character_count = len(content.strip())
            word_count = len(content.split())

            result["character_count"] = character_count
            result["word_count"] = word_count

            if character_count == 0:

                result["document_classification"] = "EMPTY_TEXT"

                result["review_reason"] = (
                    "Extracted text is empty"
                )

            elif character_count < 1000:

                result["document_classification"] = (
                    "SHORT_TEXT_REQUIRES_REVIEW"
                )

                result["review_reason"] = (
                    "Text contains fewer than 1000 characters"
                )

            else:

                result["document_classification"] = (
                    "VALID_PENDING_CONTENT_REVIEW"
                )

                result["usable_for_coverage"] = True

        except Exception as exc:

            result["document_classification"] = "READ_ERROR"
            result["review_reason"] = str(exc)

    document_results.append(result)


documents = pd.DataFrame(document_results)


# ============================================================
# 7. CREATE EXPECTED COMPANY-QUARTER RECORDS
# ============================================================

print("\n" + "=" * 75)
print("GENERATING EXPECTED COMPANY-QUARTER RECORDS")
print("=" * 75)

expected = pd.MultiIndex.from_product(
    [COMPANIES, QUARTERS],
    names=["ticker", "quarter_key"]
).to_frame(index=False)

print("Expected records:", len(expected))


# ============================================================
# 8. FILTER VALID DOCUMENTS
# ============================================================

valid_documents = documents[
    documents["usable_for_coverage"]
].copy()

# Keep only planned companies and quarters
valid_documents = valid_documents[
    valid_documents["ticker"].isin(COMPANIES)
    & valid_documents["quarter_key"].isin(QUARTERS)
].copy()

# Identify duplicate company-quarter records
duplicate_records = valid_documents[
    valid_documents.duplicated(
        subset=["ticker", "quarter_key"],
        keep=False
    )
].copy()

# One or more valid documents make a company-quarter available
available = valid_documents[
    ["ticker", "quarter_key"]
].drop_duplicates()

available["present"] = True


# ============================================================
# 9. COMPARE EXPECTED AND AVAILABLE RECORDS
# ============================================================

coverage = expected.merge(
    available,
    on=["ticker", "quarter_key"],
    how="left"
)

coverage["present"] = (
    coverage["present"]
    .fillna(False)
    .astype(bool)
)

missing_quarters = coverage[
    ~coverage["present"]
].copy()


# ============================================================
# 10. COMPANY-WISE COVERAGE SUMMARY
# ============================================================

summary = coverage.groupby("ticker").agg(
    expected_quarters=("quarter_key", "count"),
    available_quarters=("present", "sum")
).reset_index()

summary["missing_quarters"] = (
    summary["expected_quarters"]
    - summary["available_quarters"]
)

summary["coverage_percentage"] = (
    summary["available_quarters"]
    / summary["expected_quarters"]
    * 100
).round(2)


# ============================================================
# 11. OVERALL COVERAGE
# ============================================================

expected_count = len(expected)
available_count = len(available)
missing_count = len(missing_quarters)

overall_coverage = (
    available_count / expected_count * 100
    if expected_count > 0
    else 0
)

overall_summary = pd.DataFrame([{
    "expected_records": expected_count,
    "available_records": available_count,
    "missing_records": missing_count,
    "coverage_percentage": round(overall_coverage, 2)
}])


# ============================================================
# 12. DOCUMENT CLASSIFICATION SUMMARY
# ============================================================

classification_summary = (
    documents.groupby("document_classification")
    .size()
    .reset_index(name="document_count")
)

review_documents = documents[
    ~documents["usable_for_coverage"]
].copy()


# ============================================================
# 13. PRINT OVERALL RESULTS
# ============================================================

print("\n" + "=" * 75)
print("1. OVERALL COVERAGE")
print("=" * 75)

print("Expected records:", expected_count)
print("Valid unique transcript records:", available_count)
print("Missing company-quarter records:", missing_count)

print(
    "Overall coverage:",
    round(overall_coverage, 2),
    "%"
)


# ============================================================
# 14. PRINT COMPANY-WISE COVERAGE
# ============================================================

print("\n" + "=" * 75)
print("2. COMPANY-WISE COVERAGE")
print("=" * 75)

print(summary.to_string(index=False))


# ============================================================
# 15. PRINT MISSING QUARTERS
# ============================================================

print("\n" + "=" * 75)
print("3. MISSING QUARTERS")
print("=" * 75)

if missing_quarters.empty:

    print("No missing quarters.")

else:

    print(
        missing_quarters[
            ["ticker", "quarter_key"]
        ].to_string(index=False)
    )


# ============================================================
# 16. PRINT DOCUMENT CLASSIFICATION
# ============================================================

print("\n" + "=" * 75)
print("4. DOCUMENT CLASSIFICATION")
print("=" * 75)

print(classification_summary.to_string(index=False))


# ============================================================
# 17. PRINT DOCUMENTS REQUIRING REVIEW
# ============================================================

print("\n" + "=" * 75)
print("5. DOCUMENTS REQUIRING REVIEW")
print("=" * 75)

if review_documents.empty:

    print("No documents require review.")

else:

    print(
        review_documents[
            [
                "ticker",
                "quarter_key",
                "filename",
                "document_classification",
                "review_reason"
            ]
        ].to_string(index=False)
    )


# ============================================================
# 18. PRINT DUPLICATE RECORDS
# ============================================================

print("\n" + "=" * 75)
print("6. DUPLICATE COMPANY-QUARTER RECORDS")
print("=" * 75)

print("Duplicate rows:", len(duplicate_records))

if not duplicate_records.empty:

    print(
        duplicate_records[
            ["ticker", "quarter_key", "filename"]
        ].to_string(index=False)
    )


# ============================================================
# 19. SAVE AUDIT REPORTS
# ============================================================

print("\n" + "=" * 75)
print("SAVING AUDIT REPORTS")
print("=" * 75)

coverage.to_csv(
    OUTPUT_DIR / "transcript_quarter_coverage_detail.csv",
    index=False
)

summary.to_csv(
    OUTPUT_DIR / "transcript_quarter_coverage.csv",
    index=False
)

missing_quarters.to_csv(
    OUTPUT_DIR / "missing_transcript_quarters.csv",
    index=False
)

documents.to_csv(
    OUTPUT_DIR / "transcript_document_classification.csv",
    index=False
)

review_documents.to_csv(
    OUTPUT_DIR / "transcript_document_review.csv",
    index=False
)

duplicate_records.to_csv(
    OUTPUT_DIR / "duplicate_transcript_records.csv",
    index=False
)

classification_summary.to_csv(
    OUTPUT_DIR / "transcript_classification_summary.csv",
    index=False
)

overall_summary.to_csv(
    OUTPUT_DIR / "transcript_overall_coverage.csv",
    index=False
)


# ============================================================
# 20. FINAL REPORT
# ============================================================

print("\n" + "=" * 75)
print("AUDIT COMPLETE")
print("=" * 75)

print("Companies:", len(COMPANIES))
print("Quarters per company:", len(QUARTERS))
print("Expected records:", expected_count)
print("Available records:", available_count)
print("Missing records:", missing_count)
print("Coverage:", round(overall_coverage, 2), "%")

print("\nReports saved in:")
print(OUTPUT_DIR)

print("\nGenerated files:")

print("1. transcript_quarter_coverage_detail.csv")
print("2. transcript_quarter_coverage.csv")
print("3. missing_transcript_quarters.csv")
print("4. transcript_document_classification.csv")
print("5. transcript_document_review.csv")
print("6. duplicate_transcript_records.csv")
print("7. transcript_classification_summary.csv")
print("8. transcript_overall_coverage.csv")

print("\nOriginal datasets were not modified.")
