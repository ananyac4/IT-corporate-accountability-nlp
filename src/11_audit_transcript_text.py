
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEXT_DIR = ROOT / "data" / "processed" / "transcripts_text"
MANIFEST = ROOT / "data" / "processed" / "extraction_manifest.csv"

print("=" * 70)
print("TRANSCRIPT TEXT QUALITY AUDIT")
print("=" * 70)

manifest = pd.read_csv(MANIFEST)
results = []

for _, row in manifest.iterrows():
    relative_path = str(row["text_file"]).replace("\\", "/")
    file_path = ROOT / relative_path

    record = {
        "ticker": row["ticker"],
        "fy": row["fy"],
        "quarter": row["quarter"],
        "filename": row["filename"],
        "file_exists": file_path.exists(),
        "characters": 0,
        "words": 0,
        "empty": True,
        "read_error": ""
    }

    if file_path.exists():
        try:
            content = file_path.read_text(
                encoding="utf-8",
                errors="replace"
            )
            record["characters"] = len(content)
            record["words"] = len(content.split())
            record["empty"] = len(content.strip()) == 0
        except Exception as exc:
            record["read_error"] = str(exc)

    results.append(record)

audit = pd.DataFrame(results)

print("\n1. OVERALL COUNTS")
print("Manifest records:", len(audit))
print("Files existing:", audit["file_exists"].sum())
print("Missing files:", (~audit["file_exists"]).sum())
print("Empty files:", audit["empty"].sum())
print("Read errors:", (audit["read_error"] != "").sum())

print("\n2. TEXT LENGTH SUMMARY")
print(audit["characters"].describe().to_string())

print("\n3. COMPANY COVERAGE")
summary = audit.groupby("ticker").agg(
    quarters=("filename", "count"),
    existing_files=("file_exists", "sum"),
    total_words=("words", "sum"),
    average_characters=("characters", "mean")
).reset_index()

print(summary.to_string(index=False))

print("\n4. LOWEST TEXT LENGTH FILES")
print(
    audit.sort_values("characters")[
        ["ticker", "fy", "quarter", "filename", "characters", "words"]
    ].head(20).to_string(index=False)
)

print("\n5. FILES REQUIRING REVIEW")
review = audit[
    (~audit["file_exists"]) |
    audit["empty"] |
    (audit["read_error"] != "") |
    (audit["characters"] < 1000)
]

print("Files requiring review:", len(review))

output = ROOT / "outputs"
output.mkdir(exist_ok=True)

audit.to_csv(output / "transcript_text_audit.csv", index=False)
summary.to_csv(output / "transcript_company_coverage.csv", index=False)
review.to_csv(output / "transcript_text_review.csv", index=False)

print("\nReports saved in outputs/")
print(" - transcript_text_audit.csv")
print(" - transcript_company_coverage.csv")
print(" - transcript_text_review.csv")
print("\nAudit complete. No original files modified.")
