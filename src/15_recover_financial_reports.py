
"""
Script 15: Recover Financial Reports

Purpose:
1. Recover financial PDFs marked DOWNLOADED in the existing manifest.
2. Verify that each response is actually a PDF.
3. Save files in data/raw/financial_reports/.
4. Record local paths and recovery status.
5. Preserve all original files and manifests.

Input:
data/processed/download_manifest.csv
data/processed/coverage_tracker.xlsx

Outputs:
data/raw/financial_reports/*.pdf
data/processed/financial_report_recovery_manifest.csv
outputs/financial_report_recovery_summary.txt
"""

from pathlib import Path
import re
import time
import pandas as pd
import requests


# --------------------------------------------------
# 1. PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

MANIFEST_FILE = (
    ROOT / "data" / "processed" / "download_manifest.csv"
)

TRACKER_FILE = (
    ROOT / "data" / "processed" / "coverage_tracker.xlsx"
)

OUTPUT_DIR = ROOT / "data" / "raw" / "financial_reports"

RECOVERY_MANIFEST = (
    ROOT / "data" / "processed" /
    "financial_report_recovery_manifest.csv"
)

SUMMARY_FILE = (
    ROOT / "outputs" /
    "financial_report_recovery_summary.txt"
)


# --------------------------------------------------
# 2. HELPER FUNCTIONS
# --------------------------------------------------

def safe_name(value):
    return re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        str(value).strip()
    )


def valid_pdf(path):
    """Check file existence, size and PDF signature."""

    if not path.exists():
        return False

    if path.stat().st_size < 500:
        return False

    with path.open("rb") as file:
        signature = file.read(5)

    return signature.startswith(b"%PDF-")


def download_pdf(session, url, destination):
    """Download a PDF safely using a temporary file."""

    temporary = destination.with_suffix(".pdf.part")

    try:
        response = session.get(
            url,
            timeout=60,
            allow_redirects=True
        )

        response.raise_for_status()

        content = response.content

        if len(content) < 500:
            return "INVALID_OR_EMPTY", len(content), response.url

        if not content.startswith(b"%PDF-"):
            return "NOT_A_VALID_PDF", len(content), response.url

        temporary.write_bytes(content)

        if not valid_pdf(temporary):
            temporary.unlink(missing_ok=True)
            return "PDF_VALIDATION_FAILED", len(content), response.url

        temporary.replace(destination)

        return "RECOVERED", len(content), response.url

    except Exception as exc:

        if temporary.exists():
            temporary.unlink()

        return "FAILED", 0, str(exc)[:500]


# --------------------------------------------------
# 3. MAIN
# --------------------------------------------------

def main():

    print("=" * 70)
    print("SCRIPT 15: FINANCIAL REPORT RECOVERY")
    print("=" * 70)

    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(MANIFEST_FILE)

    if not TRACKER_FILE.exists():
        raise FileNotFoundError(TRACKER_FILE)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load original manifest
    manifest = pd.read_csv(MANIFEST_FILE)

    required = {
        "ticker", "fy", "quarter",
        "document_type", "url", "status"
    }

    missing = required - set(manifest.columns)

    if missing:
        raise ValueError(
            f"Manifest is missing columns: {sorted(missing)}"
        )

    # Read tracker to validate company-quarter coverage
    tracker = pd.read_excel(
        TRACKER_FILE,
        sheet_name="coverage"
    )

    tracker.columns = [
        str(column).strip().lower()
        for column in tracker.columns
    ]

    tracker_required = {"ticker", "fy", "q"}

    if not tracker_required.issubset(tracker.columns):
        raise ValueError(
            "Coverage tracker must contain ticker, fy and q columns."
        )

    def normalize(value):
        return str(value).strip().upper()

    tracker_keys = set(
        zip(
            tracker["ticker"].map(normalize),
            tracker["fy"].map(normalize),
            tracker["q"].map(normalize)
        )
    )

    # Only previously downloaded financial reports
    candidates = manifest[
        (manifest["document_type"] == "financial_report")
        & (manifest["status"] == "DOWNLOADED")
        & manifest["url"].notna()
    ].copy()

    print("\nOriginal downloaded records:", len(candidates))
    print("Tracker coverage combinations:", len(tracker_keys))

    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; AcademicResearch/1.0)"
    })

    results = []

    for index, row in candidates.iterrows():

        ticker = safe_name(row["ticker"])
        fy = safe_name(row["fy"])
        quarter = safe_name(row["quarter"])
        url = str(row["url"]).strip()

        key = (
            normalize(row["ticker"]),
            normalize(row["fy"]),
            normalize(row["quarter"])
        )

        filename = (
            f"{ticker}_{fy}_{quarter}_financial_report.pdf"
        )

        destination = OUTPUT_DIR / filename

        print(
            f"\n[{len(results) + 1}/{len(candidates)}] "
            f"{ticker} {fy} {quarter}"
        )

        if key not in tracker_keys:

            status = "NOT_IN_TRACKER"
            size = 0
            detail = "Company-quarter combination absent from tracker."

        elif valid_pdf(destination):

            status = "ALREADY_PRESENT"
            size = destination.stat().st_size
            detail = "Existing local PDF passed validation."

        else:

            status, size, detail = download_pdf(
                session,
                url,
                destination
            )

            if status == "RECOVERED":
                detail = (
                    "PDF signature verified. Final URL: " + detail
                )

        file_exists = valid_pdf(destination)

        results.append({
            "ticker": row["ticker"],
            "fy": row["fy"],
            "quarter": row["quarter"],
            "document_type": "financial_report",
            "source_url": url,
            "recovery_status": status,
            "local_file_path": (
                str(destination) if file_exists else ""
            ),
            "file_exists": file_exists,
            "file_size_bytes": (
                destination.stat().st_size if file_exists else 0
            ),
            "detail": detail
        })

        print("Status:", status)

        time.sleep(0.3)

    # Save a separate recovery manifest
    recovery = pd.DataFrame(results)

    recovery.to_csv(
        RECOVERY_MANIFEST,
        index=False
    )

    # Summary
    status_counts = (
        recovery["recovery_status"]
        .value_counts(dropna=False)
    )

    valid_count = int(recovery["file_exists"].sum())

    summary_lines = [
        "FINANCIAL REPORT RECOVERY SUMMARY",
        "=" * 60,
        f"Original downloaded records: {len(candidates)}",
        f"Recovery records processed: {len(recovery)}",
        f"Valid local PDFs: {valid_count}",
        "",
        "RECOVERY STATUS",
        "-" * 60,
        status_counts.to_string(),
        "",
        f"Recovery manifest: {RECOVERY_MANIFEST}",
        f"PDF directory: {OUTPUT_DIR}",
    ]

    SUMMARY_FILE.write_text(
        "\n".join(summary_lines),
        encoding="utf-8"
    )

    print("\n" + "\n".join(summary_lines))

    print("\nScript 15 completed.")
    print("Original download_manifest.csv was not modified.")


if __name__ == "__main__":
    main()
