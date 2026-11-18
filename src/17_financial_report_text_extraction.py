"""
17_financial_report_text_extraction.py

Extract text from all financial-report PDFs without changing the PDFs.

INPUT:
    data/raw/financial_reports/*.pdf

OUTPUTS:
    data/processed/financial_report_text.csv
    data/processed/financial_report_page_text.csv
    outputs/financial_report_text_extraction_summary.txt

Requires:
    pip install pypdf

Note:
- Encrypted PDFs are opened using an empty password where possible.
- No OCR is performed.
- Pages with no extractable text are recorded.
- Known duplicate/mislabelled files are flagged.
- Invalid Unicode surrogate characters are replaced so CSV export succeeds.
"""

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import csv
import hashlib
import re

try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit(
        "pypdf is not installed. Run:\n"
        "python -m pip install pypdf"
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "financial_reports"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

REPORT_CSV = PROCESSED_DIR / "financial_report_text.csv"
PAGE_CSV = PROCESSED_DIR / "financial_report_page_text.csv"
SUMMARY_TXT = OUTPUT_DIR / "financial_report_text_extraction_summary.txt"

FILENAME_PATTERN = re.compile(
    r"^(?P<ticker>[A-Z0-9]+)_(?P<fy>FY\d{2})_(?P<quarter>Q[1-4])_financial_report\.pdf$",
    re.IGNORECASE,
)

# These pairs were previously confirmed to contain identical PDF content.
# Keep both source files, but exclude the incorrectly labelled copies from analysis.
KNOWN_CORRECTIONS = {
    "COFORGE_FY24_Q1_financial_report.pdf": (
        "FY25_Q1", "MISLABELLED_DUPLICATE_CONTENT", False,
        "Same PDF content as COFORGE_FY25_Q1; document identifies Q1FY25, dated 22-Jul-2024."
    ),
    "COFORGE_FY25_Q1_financial_report.pdf": (
        "FY25_Q1", "KNOWN_DUPLICATE_CANONICAL", True,
        "Document identifies Q1FY25, dated 22-Jul-2024."
    ),
    "NEWGEN_FY24_Q4_financial_report.pdf": (
        "FY25_Q1", "MISLABELLED_DUPLICATE_CONTENT", False,
        "Same PDF content as NEWGEN_FY25_Q1; document refers to quarter ended 30-Jun-2024."
    ),
    "NEWGEN_FY25_Q1_financial_report.pdf": (
        "FY25_Q1", "KNOWN_DUPLICATE_CANONICAL", True,
        "Document refers to quarter ended 30-Jun-2024, dated 18-Jul-2024."
    ),
    "LTIM_FY24_Q2_financial_report.pdf": (
        "FY24_Q3", "MISLABELLED_DUPLICATE_CONTENT", False,
        "Same PDF content as LTIM_FY24_Q3; document identifies Q3FY24, dated 17-Jan-2024."
    ),
    "LTIM_FY24_Q3_financial_report.pdf": (
        "FY24_Q3", "KNOWN_DUPLICATE_CANONICAL", True,
        "Document identifies Q3FY24, dated 17-Jan-2024."
    ),
}

KNOWN_VERIFIED_FILES = {
    "TCS_FY23_Q4_financial_report.pdf": (
        "FY23_Q4",
        "CONTENT_VERIFIED",
        "First page identifies Quarter IV and year ended FY2022-23, dated 12-Apr-2023."
    )
}


def safe_text(value):
    """Make extracted PDF text safe for UTF-8 CSV output."""
    if value is None:
        return ""
    value = str(value).replace("\x00", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    # Replace lone surrogate code points produced by some PDF text extractors.
    return value.encode("utf-8", errors="replace").decode("utf-8").strip()


def parse_filename(filename):
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return "", "", "", ""
    ticker = match.group("ticker").upper()
    fy = match.group("fy").upper()
    quarter = match.group("quarter").upper()
    return ticker, fy, quarter, f"{fy}_{quarter}"


def calculate_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Sanitize every value, not just extracted text.
            clean_row = {
                key: safe_text(value) if isinstance(value, str) else value
                for key, value in row.items()
            }
            writer.writerow(clean_row)


def main():
    if not PDF_DIR.exists():
        raise SystemExit(f"PDF folder does not exist:\n{PDF_DIR}")

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"No PDF files found in:\n{PDF_DIR}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Project: {PROJECT_ROOT}")
    print(f"PDF directory: {PDF_DIR}")
    print(f"PDF files found: {len(pdf_files)}")
    print("\nStarting extraction...\n")

    # Calculate hashes to identify exact duplicate files.
    hashes = {}
    hash_groups = defaultdict(list)
    for pdf_path in pdf_files:
        try:
            digest = calculate_sha256(pdf_path)
        except Exception as exc:
            digest = ""
            print(f"[HASH ERROR] {pdf_path.name}: {exc}")
        hashes[pdf_path.name] = digest
        if digest:
            hash_groups[digest].append(pdf_path.name)

    report_rows = []
    page_rows = []
    extraction_counts = Counter()
    total_pages = 0
    pages_with_text = 0
    total_characters = 0
    encrypted_count = 0
    decrypted_count = 0
    unreadable_count = 0
    no_text_files = 0
    unidentified_names = 0
    duplicate_file_count = 0

    for number, pdf_path in enumerate(pdf_files, start=1):
        filename = pdf_path.name
        ticker, fy, quarter, filename_quarter = parse_filename(filename)
        if not ticker:
            unidentified_names += 1

        digest = hashes.get(filename, "")
        duplicate_names = hash_groups.get(digest, []) if digest else []
        duplicate_size = len(duplicate_names)
        if duplicate_size > 1:
            duplicate_file_count += 1

        if filename in KNOWN_CORRECTIONS:
            verified_quarter, verification_status, include, evidence = KNOWN_CORRECTIONS[filename]
        elif filename in KNOWN_VERIFIED_FILES:
            verified_quarter, verification_status, evidence = KNOWN_VERIFIED_FILES[filename]
            include = True
        elif duplicate_size > 1:
            verified_quarter = filename_quarter
            verification_status = "UNRESOLVED_DUPLICATE_CONTENT"
            include = False
            evidence = "Identical SHA-256 content exists under multiple filenames; review before analysis."
        else:
            verified_quarter = filename_quarter
            verification_status = "FILENAME_ONLY_NEEDS_CONTENT_REVIEW"
            include = True
            evidence = "Quarter is parsed from filename; PDF reporting period has not been independently verified."

        encrypted = False
        decrypted = False
        page_count = 0
        pages_with_text_file = 0
        file_text_parts = []
        error_message = ""
        extraction_status = "READ_ERROR"

        try:
            reader = PdfReader(str(pdf_path), strict=False)
            encrypted = bool(reader.is_encrypted)

            if encrypted:
                encrypted_count += 1
                decrypt_result = reader.decrypt("")
                decrypted = bool(decrypt_result)
                if not decrypted:
                    raise RuntimeError("Could not decrypt using an empty password.")
                decrypted_count += 1

            page_count = len(reader.pages)
            total_pages += page_count

            for page_number, page in enumerate(reader.pages, start=1):
                page_error = ""
                try:
                    page_text = safe_text(page.extract_text())
                except Exception as exc:
                    page_text = ""
                    page_error = safe_text(exc)

                has_text = bool(page_text)
                if has_text:
                    pages_with_text += 1
                    pages_with_text_file += 1
                    total_characters += len(page_text)
                    file_text_parts.append(page_text)

                page_rows.append({
                    "ticker": ticker,
                    "filename_quarter": filename_quarter,
                    "verified_quarter": verified_quarter,
                    "filename": filename,
                    "sha256": digest,
                    "duplicate_group_size": duplicate_size,
                    "page_number": page_number,
                    "has_extractable_text": has_text,
                    "text_char_count": len(page_text),
                    "page_extraction_error": page_error,
                    "page_text": page_text,
                })

            extraction_status = "TEXT_EXTRACTED" if pages_with_text_file else "NO_TEXT_EXTRACTED"
            if extraction_status == "NO_TEXT_EXTRACTED":
                no_text_files += 1

        except Exception as exc:
            error_message = safe_text(exc)
            unreadable_count += 1

        full_text = safe_text("\n\n".join(file_text_parts))

        report_rows.append({
            "ticker": ticker,
            "fy": fy,
            "filename_quarter": filename_quarter,
            "verified_quarter": verified_quarter,
            "filename": filename,
            "sha256": digest,
            "duplicate_group_size": duplicate_size,
            "duplicate_filenames": " | ".join(duplicate_names),
            "verification_status": verification_status,
            "verification_evidence": evidence,
            "include_in_analysis": include,
            "encrypted": encrypted,
            "empty_password_decryption_succeeded": decrypted,
            "page_count": page_count,
            "pages_with_extractable_text": pages_with_text_file,
            "text_char_count": len(full_text),
            "extraction_status": extraction_status,
            "error_message": error_message,
            "extracted_text": full_text,
        })

        extraction_counts[extraction_status] += 1
        print(
            f"[{number}/{len(pdf_files)}] {filename} | "
            f"{extraction_status} | pages={page_count} | "
            f"text_chars={len(full_text)}"
        )

    report_fields = [
        "ticker", "fy", "filename_quarter", "verified_quarter", "filename",
        "sha256", "duplicate_group_size", "duplicate_filenames",
        "verification_status", "verification_evidence", "include_in_analysis",
        "encrypted", "empty_password_decryption_succeeded", "page_count",
        "pages_with_extractable_text", "text_char_count", "extraction_status",
        "error_message", "extracted_text",
    ]
    page_fields = [
        "ticker", "filename_quarter", "verified_quarter", "filename",
        "sha256", "duplicate_group_size", "page_number",
        "has_extractable_text", "text_char_count", "page_extraction_error",
        "page_text",
    ]

    write_csv(REPORT_CSV, report_fields, report_rows)
    write_csv(PAGE_CSV, page_fields, page_rows)

    duplicate_groups = sum(1 for names in hash_groups.values() if len(names) > 1)
    included_count = sum(1 for row in report_rows if row["include_in_analysis"])
    known_verified_count = sum(
        1 for row in report_rows
        if row["verification_status"] in {
            "CONTENT_VERIFIED", "KNOWN_DUPLICATE_CANONICAL"
        }
    )

    summary_lines = [
        "FINANCIAL REPORT TEXT EXTRACTION SUMMARY",
        f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"PDF files found: {len(pdf_files)}",
        f"Files with extractable text: {extraction_counts['TEXT_EXTRACTED']}",
        f"Files with no extractable text: {no_text_files}",
        f"Files with read/decryption errors: {unreadable_count}",
        f"Total PDF pages: {total_pages}",
        f"Pages with extractable text: {pages_with_text}",
        f"Total extracted text characters: {total_characters}",
        "",
        f"Encrypted PDFs: {encrypted_count}",
        f"Encrypted PDFs opened with empty password: {decrypted_count}",
        f"Files with unidentified filename pattern: {unidentified_names}",
        f"Files in identical-content groups: {duplicate_file_count}",
        f"Identical-content groups: {duplicate_groups}",
        "",
        f"Rows marked include_in_analysis=True: {included_count}",
        f"Rows with known content-quarter verification: {known_verified_count}",
        "",
        "IMPORTANT NOTES",
        "TEXT_EXTRACTED means text was extracted; it does not prove the report period or financial figures are correct.",
        "Most reporting quarters still require checking against the PDF contents.",
        "Known mislabelled duplicate copies are excluded from analysis by default.",
        "No source PDFs were renamed, deleted or modified.",
        "No OCR was performed. Image-only pages may contain no extractable text.",
        "",
        "OUTPUT FILES",
        str(REPORT_CSV),
        str(PAGE_CSV),
        str(SUMMARY_TXT),
    ]

    SUMMARY_TXT.write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n" + "\n".join(summary_lines))
    print("\nScript 17 completed successfully.")


if __name__ == "__main__":
    main()
