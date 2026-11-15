"""
Extract searchable text from downloaded transcript PDFs.
Outputs one TXT per PDF and a combined transcript_text.csv.
"""
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "raw" / "transcripts"
TEXT_DIR = ROOT / "data" / "processed" / "transcripts_text"
MANIFEST = ROOT / "data" / "processed" / "extraction_manifest.csv"
COMBINED = ROOT / "data" / "processed" / "transcripts_text.csv"

TEXT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    pdfs = sorted(INPUT.glob("*.pdf"))
    rows = []

    if not pdfs:
        print(f"No transcript PDFs found in {INPUT}")
        return

    for pdf in pdfs:
        status, text, error = "OK", "", ""
        try:
            with pdfplumber.open(pdf) as doc:
                text = "\n".join((page.extract_text() or "") for page in doc.pages)
            if len(text.strip()) < 200:
                status = "LOW_OR_EMPTY_TEXT"
        except Exception as exc:
            status, error = "EXTRACTION_FAILED", str(exc)[:500]

        txt_path = TEXT_DIR / f"{pdf.stem}.txt"
        txt_path.write_text(text, encoding="utf-8")
        parts = pdf.stem.split("_")
        rows.append({
            "filename": pdf.name,
            "ticker": parts[0] if len(parts) > 0 else "",
            "fy": parts[1] if len(parts) > 1 else "",
            "quarter": parts[2] if len(parts) > 2 else "",
            "text_file": str(txt_path.relative_to(ROOT)),
            "character_count": len(text),
            "status": status,
            "error": error,
            "text": text
        })
        print(f"{pdf.name}: {status} ({len(text)} chars)")

    pd.DataFrame(rows).to_csv(MANIFEST, index=False)
    pd.DataFrame(rows).drop(columns=["error"]).to_csv(COMBINED, index=False)
    print(f"\nSaved extraction manifest: {MANIFEST}")
    print(f"Saved combined text: {COMBINED}")

if __name__ == "__main__":
    main()
