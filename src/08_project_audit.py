
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
OUTPUTS = ROOT / "outputs"

OUTPUTS.mkdir(exist_ok=True)

report = []
inventory = []

def log(message=""):
    report.append(str(message))
    print(message)

log("=" * 65)
log("IT CORPORATE ACCOUNTABILITY NLP - PROJECT AUDIT")
log("=" * 65)

# 1. Count raw PDF files
log("\n1. RAW PDF INVENTORY")

for folder_name, folder in [
    ("Transcripts", RAW / "transcripts"),
    ("Financial reports", RAW / "financial_reports")
]:
    files = list(folder.rglob("*.pdf")) if folder.exists() else []
    log(f"{folder_name}: {len(files)} PDF files")

    for file in files:
        inventory.append({
            "category": folder_name,
            "filename": file.name,
            "path": str(file.relative_to(ROOT)),
            "size_kb": round(file.stat().st_size / 1024, 2)
        })

# 2. Inspect processed CSV files
log("\n2. PROCESSED CSV AUDIT")

csv_files = list(PROCESSED.glob("*.csv")) if PROCESSED.exists() else []

for file in sorted(csv_files):
    try:
        df = pd.read_csv(file, low_memory=False)

        duplicate_count = int(df.duplicated().sum())
        empty_rows = int(df.isna().all(axis=1).sum())

        log(f"\nFile: {file.name}")
        log(f"Rows: {len(df)}")
        log(f"Columns: {len(df.columns)}")
        log(f"Duplicates: {duplicate_count}")
        log(f"Completely empty rows: {empty_rows}")
        log(f"Column names: {list(df.columns)}")

        ticker_col = next(
            (c for c in df.columns
             if c.lower() in ["ticker", "company", "company_ticker"]),
            None
        )

        if ticker_col:
            log(f"Unique companies: {df[ticker_col].nunique()}")
            log(f"Company names: {sorted(df[ticker_col].dropna().astype(str).unique())}")

        inventory.append({
            "category": "Processed CSV",
            "filename": file.name,
            "path": str(file.relative_to(ROOT)),
            "size_kb": round(file.stat().st_size / 1024, 2),
            "rows": len(df),
            "columns": len(df.columns),
            "duplicates": duplicate_count
        })

    except Exception as error:
        log(f"Could not read {file.name}: {error}")

# 3. Check important expected files
log("\n3. KEY DATASET CHECK")

expected_files = [
    "transcript_metadata.csv",
    "coverage_by_company.csv",
    "actuals_template.csv",
    "guidance_template.csv",
    "explanations_template.csv",
    "OFSS_quarterly_actuals_extracted.csv",
    "OFSS_management_commentary_extracted.csv",
    "OFSS_document_manifest.csv"
]

for filename in expected_files:
    path = PROCESSED / filename
    status = "FOUND" if path.exists() else "NOT FOUND"
    log(f"{filename}: {status}")

# 4. Save inventory
inventory_df = pd.DataFrame(inventory)
inventory_path = OUTPUTS / "project_audit_inventory.csv"
inventory_df.to_csv(inventory_path, index=False)

# 5. Save text report
report_path = OUTPUTS / "project_audit_report.txt"
report_path.write_text("\n".join(report), encoding="utf-8")

log("\n" + "=" * 65)
log("AUDIT COMPLETED")
log(f"Inventory: {inventory_path}")
log(f"Report: {report_path}")
log("=" * 65)
