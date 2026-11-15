"""
Read the Excel tracker and download every linked transcript / PR PDF.
Expected input: data/processed/coverage_tracker.xlsx
Expected sheets: companies, coverage
Expected coverage columns: ticker, fy, q, transcript_url, pr_url
Status columns are optional; URLs are the source of truth for download attempts.
"""
from pathlib import Path
import re
import time
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "data" / "processed" / "coverage_tracker.xlsx"
RAW_TRANSCRIPTS = ROOT / "data" / "raw" / "transcripts"
RAW_REPORTS = ROOT / "data" / "raw" / "financial_reports"
OUT = ROOT / "data" / "processed" / "download_manifest.csv"

for folder in (RAW_TRANSCRIPTS, RAW_REPORTS, OUT.parent):
    folder.mkdir(parents=True, exist_ok=True)

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())

def download(session, url, destination):
    if destination.exists() and destination.stat().st_size > 500:
        return "ALREADY_DOWNLOADED", destination.stat().st_size, ""
    try:
        response = session.get(url, timeout=45, allow_redirects=True)
        response.raise_for_status()
        content = response.content
        # Some investor-relations URLs return an HTML error page instead of a PDF.
        is_pdf = content[:4] == b"%PDF" or "pdf" in response.headers.get("Content-Type", "").lower()
        if not is_pdf or len(content) < 500:
            return "NOT_A_PDF_OR_BLOCKED", len(content), response.url
        destination.write_bytes(content)
        return "DOWNLOADED", len(content), response.url
    except Exception as exc:
        return "FAILED", 0, str(exc)[:500]

def main():
    if not TRACKER.exists():
        raise FileNotFoundError(
            f"Put your Excel workbook here: {TRACKER}\n"
            "The workbook must contain sheets named 'companies' and 'coverage'."
        )

    xls = pd.ExcelFile(TRACKER)
    if not {"companies", "coverage"}.issubset(set(xls.sheet_names)):
        raise ValueError(f"Expected sheets 'companies' and 'coverage'; found {xls.sheet_names}")

    companies = pd.read_excel(TRACKER, sheet_name="companies")
    coverage = pd.read_excel(TRACKER, sheet_name="coverage")
    coverage.columns = [str(c).strip().lower() for c in coverage.columns]

    required = {"ticker", "fy", "q", "transcript_url", "pr_url"}
    missing = required - set(coverage.columns)
    if missing:
        raise ValueError(f"Missing columns in coverage sheet: {sorted(missing)}")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; AcademicResearch/1.0)"})
    manifest = []

    for _, row in coverage.iterrows():
        ticker = safe_name(row.get("ticker", "UNKNOWN"))
        fy = safe_name(row.get("fy", "FY_UNKNOWN"))
        quarter = safe_name(row.get("q", "Q_UNKNOWN"))

        for doc_type, url_col, folder in [
            ("transcript", "transcript_url", RAW_TRANSCRIPTS),
            ("financial_report", "pr_url", RAW_REPORTS),
        ]:
            url = row.get(url_col)
            if pd.isna(url) or not str(url).strip():
                manifest.append({
                    "ticker": ticker, "fy": fy, "quarter": quarter,
                    "document_type": doc_type, "url": "",
                    "status": "NO_LINK", "bytes": 0, "detail": ""
                })
                continue

            url = str(url).strip()
            destination = folder / f"{ticker}_{fy}_{quarter}_{doc_type}.pdf"
            status, size, detail = download(session, url, destination)
            manifest.append({
                "ticker": ticker, "fy": fy, "quarter": quarter,
                "document_type": doc_type, "url": url,
                "status": status, "bytes": size, "detail": detail
            })
            print(f"{ticker} {fy} {quarter} {doc_type}: {status}")
            time.sleep(0.25)

    result = pd.DataFrame(manifest)
    result.to_csv(OUT, index=False)
    print(f"\nSaved: {OUT}")
    print("\nDownload summary:")
    print(result.groupby(["document_type", "status"]).size().to_string())

if __name__ == "__main__":
    main()
