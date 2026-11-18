
from pathlib import Path
import re
import hashlib
import pandas as pd
from pypdf import PdfReader


# ============================================================
# SCRIPT 16: FINANCIAL REPORT CORPUS AUDIT
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

PDF_DIR = ROOT / "data" / "raw" / "financial_reports"
MANIFEST = (
    ROOT
    / "data"
    / "processed"
    / "financial_report_recovery_manifest.csv"
)
OUTPUT_DIR = ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 1. RESEARCH CONFIGURATION
# ------------------------------------------------------------

TICKERS = [
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


# Expected period: FY23 Q1 through FY27 Q1
EXPECTED_QUARTERS = []

# FY23 Q1 to FY26 Q4
for year in range(2023, 2027):
    for quarter in range(1, 5):
        EXPECTED_QUARTERS.append(
            f"FY{str(year)[-2:]}_Q{quarter}"
        )

# FY27 Q1
EXPECTED_QUARTERS.append("FY27_Q1")


EXPECTED_KEYS = {
    (ticker, quarter)
    for ticker in TICKERS
    for quarter in EXPECTED_QUARTERS
}


# ------------------------------------------------------------
# 2. COMPANY IDENTIFICATION
# ------------------------------------------------------------

def identify_company(filename):
    """
    Identify company ticker from the beginning of the filename.
    """

    upper = filename.upper()

    for ticker in sorted(TICKERS, key=len, reverse=True):

        if (
            upper.startswith(ticker.upper() + "_")
            or upper == ticker.upper()
        ):
            return ticker

    return None


# ------------------------------------------------------------
# 3. QUARTER IDENTIFICATION
# ------------------------------------------------------------

def identify_quarter(filename):
    """
    Identify financial year and quarter from filename.

    Supported examples:
    FY23_Q1
    FY2023_Q1
    FY23Q1
    FY2023Q1
    """

    upper = (
        filename.upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    match = re.search(
        r"FY_?(20\d{2}|\d{2})_?Q([1-4])",
        upper
    )

    if not match:
        return None

    year = match.group(1)

    if len(year) == 4:
        year = year[-2:]

    return f"FY{year}_Q{match.group(2)}"


# ------------------------------------------------------------
# 4. PDF AUDIT FUNCTION
# ------------------------------------------------------------

def audit_pdf(pdf_path):
    """
    Audit an individual PDF.

    Checks:
    - File size
    - SHA-256 hash
    - Company and quarter from filename
    - PDF encryption
    - Empty-password decryption
    - Page count
    - Metadata
    - Text extraction from first 10 pages
    """

    result = {
        "filename": pdf_path.name,
        "file_path": str(pdf_path),
        "file_size_bytes": pdf_path.stat().st_size,

        "ticker": identify_company(pdf_path.name),
        "quarter_key": identify_quarter(pdf_path.name),

        "pdf_readable": False,
        "encrypted": None,
        "decryption_status": "NOT_REQUIRED",

        "page_count": 0,
        "text_chars_first_10_pages": 0,

        "pdf_title": "",
        "sha256": "",

        "audit_status": "NOT_CHECKED",
        "error": ""
    }

    try:

        # ----------------------------------------------------
        # Calculate SHA-256 hash
        # ----------------------------------------------------

        digest = hashlib.sha256()

        with pdf_path.open("rb") as file:

            for chunk in iter(
                lambda: file.read(1024 * 1024),
                b""
            ):
                digest.update(chunk)

        result["sha256"] = digest.hexdigest()

        # ----------------------------------------------------
        # Open PDF
        # ----------------------------------------------------

        reader = PdfReader(
            str(pdf_path),
            strict=False
        )

        # ----------------------------------------------------
        # Check encryption
        # ----------------------------------------------------

        result["encrypted"] = reader.is_encrypted

        if reader.is_encrypted:

            try:

                # Attempt empty-password decryption.
                decrypt_result = reader.decrypt("")

                if not decrypt_result:

                    result["decryption_status"] = (
                        "PASSWORD_REQUIRED"
                    )

                    result["audit_status"] = (
                        "ENCRYPTED_PASSWORD_REQUIRED"
                    )

                    return result

                result["decryption_status"] = (
                    "EMPTY_PASSWORD_SUCCESS"
                )

            except Exception as error:

                result["decryption_status"] = (
                    "DECRYPTION_FAILED"
                )

                result["audit_status"] = (
                    "DECRYPTION_FAILED"
                )

                result["error"] = str(error)

                return result

        # ----------------------------------------------------
        # Page count
        # ----------------------------------------------------

        result["page_count"] = len(reader.pages)

        if len(reader.pages) == 0:

            result["audit_status"] = "ZERO_PAGES"

            return result

        # ----------------------------------------------------
        # PDF metadata
        # ----------------------------------------------------

        metadata = reader.metadata

        if metadata and metadata.title:

            result["pdf_title"] = str(metadata.title)

        # ----------------------------------------------------
        # Extract text from first 10 pages
        # ----------------------------------------------------

        extracted_text = ""

        for page_number in range(
            min(10, len(reader.pages))
        ):

            try:

                page_text = (
                    reader.pages[page_number].extract_text()
                    or ""
                )

                extracted_text += page_text

            except Exception:
                # Continue auditing even if one page fails.
                continue

        text_length = len(extracted_text.strip())

        result["text_chars_first_10_pages"] = text_length

        # PDF successfully opened, even if text extraction is empty.
        result["pdf_readable"] = True

        if text_length == 0:

            result["audit_status"] = (
                "READABLE_NO_TEXT_FIRST_10_PAGES"
            )

        else:

            result["audit_status"] = "READABLE"

    except Exception as error:

        result["error"] = str(error)

        result["audit_status"] = "UNREADABLE"

    return result


# ------------------------------------------------------------
# 5. MAIN AUDIT
# ------------------------------------------------------------

def main():

    print("=" * 68)
    print("SCRIPT 16: FINANCIAL REPORT CORPUS AUDIT")
    print("=" * 68)

    # --------------------------------------------------------
    # Check required directories and files
    # --------------------------------------------------------

    if not PDF_DIR.exists():

        raise FileNotFoundError(
            f"PDF directory not found: {PDF_DIR}"
        )

    if not MANIFEST.exists():

        raise FileNotFoundError(
            f"Recovery manifest not found: {MANIFEST}"
        )

    manifest = pd.read_csv(MANIFEST)

    pdf_files = sorted(
        PDF_DIR.glob("*.pdf")
    )

    print(f"\nPDF files found: {len(pdf_files)}")

    print(
        f"Recovery manifest records: {len(manifest)}"
    )

    print(
        f"Expected companies: {len(TICKERS)}"
    )

    print(
        f"Expected quarters: {len(EXPECTED_QUARTERS)}"
    )

    print(
        f"Expected company-quarter combinations: "
        f"{len(EXPECTED_KEYS)}"
    )

    if len(pdf_files) == 0:

        raise RuntimeError(
            "No PDF files found. Audit stopped."
        )

    # --------------------------------------------------------
    # 6. Audit every PDF
    # --------------------------------------------------------

    print("\nAuditing PDFs. Please wait...\n")

    records = []

    for index, pdf_path in enumerate(
        pdf_files,
        start=1
    ):

        records.append(
            audit_pdf(pdf_path)
        )

        if index % 25 == 0 or index == len(pdf_files):

            print(
                f"Processed {index}/{len(pdf_files)} PDFs"
            )

    audit = pd.DataFrame(records)

    # --------------------------------------------------------
    # 7. Company-quarter identification
    # --------------------------------------------------------

    identified = audit.dropna(
        subset=["ticker", "quarter_key"]
    ).copy()

    identified["company_quarter"] = list(
        zip(
            identified["ticker"],
            identified["quarter_key"]
        )
    )

    # --------------------------------------------------------
    # 8. Company-quarter coverage
    # --------------------------------------------------------

    coverage_records = []

    for ticker in TICKERS:

        for quarter in EXPECTED_QUARTERS:

            matching = identified[
                (identified["ticker"] == ticker)
                &
                (identified["quarter_key"] == quarter)
            ]

            count = len(matching)

            if count == 0:
                status = "MISSING"

            elif count > 1:
                status = "DUPLICATE"

            else:
                status = "PRESENT"

            coverage_records.append({

                "ticker": ticker,

                "quarter_key": quarter,

                "pdf_count": count,

                "coverage_status": status

            })

    coverage = pd.DataFrame(
        coverage_records
    )

    # --------------------------------------------------------
    # 9. Duplicate company-quarter reports
    # --------------------------------------------------------

    duplicates = (
        identified
        .groupby(
            ["ticker", "quarter_key"]
        )
        .filter(
            lambda group: len(group) > 1
        )
        .sort_values(
            ["ticker", "quarter_key"]
        )
    )

    # --------------------------------------------------------
    # 10. Identical PDF hash detection
    # --------------------------------------------------------

    hash_duplicates = (
        audit[
            audit["sha256"] != ""
        ]
        .groupby("sha256")
        .filter(
            lambda group: len(group) > 1
        )
        .sort_values("sha256")
    )

    # --------------------------------------------------------
    # 11. Reports requiring manual review
    # --------------------------------------------------------

    review = audit[
        (audit["audit_status"] != "READABLE")
        |
        (audit["ticker"].isna())
        |
        (audit["quarter_key"].isna())
    ].copy()

    # --------------------------------------------------------
    # 12. Missing company-quarter combinations
    # --------------------------------------------------------

    missing_quarters = coverage[
        coverage["coverage_status"] == "MISSING"
    ].copy()

    # --------------------------------------------------------
    # 13. Save audit outputs
    # --------------------------------------------------------

    audit_path = (
        OUTPUT_DIR / "financial_report_pdf_audit.csv"
    )

    coverage_path = (
        OUTPUT_DIR / "financial_report_quarter_coverage.csv"
    )

    duplicates_path = (
        OUTPUT_DIR / "financial_report_duplicates.csv"
    )

    hashes_path = (
        OUTPUT_DIR / "financial_report_duplicate_hashes.csv"
    )

    review_path = (
        OUTPUT_DIR / "financial_report_review_required.csv"
    )

    missing_path = (
        OUTPUT_DIR / "financial_report_missing_quarters.csv"
    )

    summary_path = (
        OUTPUT_DIR / "financial_report_corpus_audit_summary.txt"
    )

    audit.to_csv(
        audit_path,
        index=False
    )

    coverage.to_csv(
        coverage_path,
        index=False
    )

    duplicates.to_csv(
        duplicates_path,
        index=False
    )

    hash_duplicates.to_csv(
        hashes_path,
        index=False
    )

    review.to_csv(
        review_path,
        index=False
    )

    missing_quarters.to_csv(
        missing_path,
        index=False
    )

    # --------------------------------------------------------
    # 14. Calculate summary statistics
    # --------------------------------------------------------

    total_pdfs = len(audit)

    readable = int(
        audit["pdf_readable"].sum()
    )

    unreadable = total_pdfs - readable

    encrypted = int(
        audit["encrypted"].fillna(False).sum()
    )

    decrypted_successfully = int(
        (
            audit["decryption_status"]
            == "EMPTY_PASSWORD_SUCCESS"
        ).sum()
    )

    present = int(
        (
            coverage["coverage_status"]
            == "PRESENT"
        ).sum()
    )

    missing = int(
        (
            coverage["coverage_status"]
            == "MISSING"
        ).sum()
    )

    duplicate_quarters = int(
        (
            coverage["coverage_status"]
            == "DUPLICATE"
        ).sum()
    )

    # --------------------------------------------------------
    # 15. Generate summary report
    # --------------------------------------------------------

    summary = f"""
FINANCIAL REPORT CORPUS AUDIT SUMMARY
====================================================================

PDF FILES
--------------------------------------------------------------------
PDF files found: {total_pdfs}
Readable PDFs: {readable}
Unreadable PDFs: {unreadable}

ENCRYPTION
--------------------------------------------------------------------
Encrypted PDFs: {encrypted}
Successfully opened with empty password: {decrypted_successfully}

COMPANY IDENTIFICATION
--------------------------------------------------------------------
Expected companies: {len(TICKERS)}
Companies identified: {audit["ticker"].nunique()}
Files with unidentified company: {int(audit["ticker"].isna().sum())}

QUARTER IDENTIFICATION
--------------------------------------------------------------------
Expected quarters: {len(EXPECTED_QUARTERS)}
Files with identified quarter: {int(audit["quarter_key"].notna().sum())}
Files with unidentified quarter: {int(audit["quarter_key"].isna().sum())}

EXPECTED COVERAGE
--------------------------------------------------------------------
Expected company-quarter combinations: {len(EXPECTED_KEYS)}
Present combinations: {present}
Missing combinations: {missing}
Duplicate company-quarter combinations: {duplicate_quarters}

DUPLICATE FILE HASHES
--------------------------------------------------------------------
Files involved in identical-hash groups: {len(hash_duplicates)}

MANUAL REVIEW
--------------------------------------------------------------------
Files requiring manual review: {len(review)}

OUTPUT FILES
--------------------------------------------------------------------
{audit_path}
{coverage_path}
{duplicates_path}
{hashes_path}
{review_path}
{missing_path}
{summary_path}

IMPORTANT
--------------------------------------------------------------------
Quarter coverage is based on filenames, not verified PDF contents.
Identical hashes and incorrectly labelled reports require
additional document-level verification.
====================================================================
"""

    summary_path.write_text(
        summary,
        encoding="utf-8"
    )

    print(summary)

    print("Script 16 completed successfully.")


# ------------------------------------------------------------
# 16. ENTRY POINT
# ------------------------------------------------------------

if __name__ == "__main__":
    main()
