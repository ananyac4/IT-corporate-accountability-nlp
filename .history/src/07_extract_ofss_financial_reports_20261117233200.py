"""
07_extract_ofss_financial_reports.py

Extracts quarterly financial actuals and management commentary from OFSS
quarterly financial-results PDFs. These are NOT earnings-call transcripts.

Input:
  data/raw/financial_reports/OFSS/*.pdf

Outputs:
  data/processed/OFSS_quarterly_actuals.csv
  data/processed/OFSS_management_commentary.csv
  data/processed/OFSS_document_manifest.csv

Units:
  Financial statement values are reported in INR million in the tables.
  The script preserves that unit; do not mix with INR crore without conversion.
"""

from pathlib import Path
import re
import fitz
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "raw" / "financial_reports" / "OFSS"
OUT_DIR = ROOT / "data" / "processed"

# Optional filename hints. The document itself is used to identify the quarter.
FILENAME_HINTS = {
    "OFSS_FY26_Q1_financial_report.pdf": ("FY2026", "Q1"),
    "OFSS_FY26_Q2_financial_report.pdf": ("FY2026", "Q2"),
    "OFSS_FY26_Q3_financial_report.pdf": ("FY2026", "Q3"),
    "OFSS_FY26_Q4_financial_report.pdf": ("FY2026", "Q4"),
    "OFSS_FY27_Q1_financial_report.pdf": ("FY2027", "Q1"),
}

NUM = r"\(?-?\d[\d,]*(?:\.\d+)?\)?%?"

def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()

def numeric_tokens(s):
    return re.findall(NUM, s)

def to_number(token):
    if not token:
        return None
    token = token.replace(",", "").replace("%", "")
    neg = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    try:
        val = float(token)
        return -val if neg else val
    except ValueError:
        return None

def get_row_value(text, label, section_start=None, section_end=None):
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    if section_start:
        start = next((i for i,x in enumerate(lines) if section_start.lower() in x.lower()), 0)
        lines = lines[start:]
    # Find the target row and collect values until the next table label.
    target = next((i for i,x in enumerate(lines) if x.lower() == label.lower()), None)
    if target is None:
        target = next((i for i,x in enumerate(lines) if x.lower().startswith(label.lower())), None)
    if target is None:
        return []
    stop_labels = [
        "Products", "Services", "Total Revenues", "SEGMENT RESULTS",
        "Unallocable expenses", "OPERATING INCOME", "Interest and other income",
        "INCOME BEFORE", "Provision for taxes", "NET INCOME",
        "Earnings per share", "Basic", "Diluted", "REVENUES BY GEOGRAPHY"
    ]
    vals = []
    for line in lines[target + 1:]:
        if section_end and section_end.lower() in line.lower():
            break
        if line.lower() in [x.lower() for x in stop_labels] and line.lower() != label.lower():
            break
        vals.extend([to_number(v) for v in numeric_tokens(line) if to_number(v) is not None])
        if len(vals) >= 5:
            break
    return vals

def identify_period(filename, pages_text):
    fy, q = FILENAME_HINTS.get(filename, (None, None))
    alltext = "\n".join(pages_text)
    m = re.search(r"Q([1-4])\s+FY\s+20(\d{2})[-– ]?(\d{2})", alltext, re.I)
    if m:
        q = "Q" + m.group(1)
        fy = "FY20" + m.group(3)
    if not fy or not q:
        # filename fallback
        m = re.search(r"FY(\d{2})_Q([1-4])", filename, re.I)
        if m:
            fy, q = "FY20" + m.group(1), "Q" + m.group(2)
    return fy, q

def extract_management_quotes(pages_text):
    records = []
    for page_no, page_text in enumerate(pages_text[:3], start=1):
        # Preserve the source wording and surrounding attribution. These releases
        # sometimes split one speaker's remarks across multiple quoted spans.
        if "said " in page_text.lower() or "said," in page_text.lower():
            records.append({
                "ticker": "OFSS",
                "speaker": "",
                "designation_as_printed": "",
                "page": page_no,
                "statement": norm(page_text),
                "source_type": "QUARTERLY_FINANCIAL_RESULTS_RELEASE",
                "transcript_equivalent": "NO",
                "review_status": "MANUALLY_SEGMENT_AND_ATTRIBUTE"
            })
    return records

def extract_pdf(path):
    doc = fitz.open(path)
    pages = [p.get_text("text") or "" for p in doc]
    fy, quarter = identify_period(path.name, pages)

    # Select the standalone quarterly table, not the YTD or full-year table.
    candidates = []
    for page_no, text in enumerate(pages, start=1):
        if "CONSOLIDATED STATEMENTS OF OPERATIONS" in text:
            low = text.lower()
            score = 0
            if "three month ended" in low: score += 5
            if quarter and re.search(rf"\b{quarter}\b", text, re.I): score += 3
            if "year to date" in low or "half year ended" in low or "nine month ended" in low or "year ended" in low:
                score -= 5
            candidates.append((score, page_no, text))
    if not candidates:
        table_text = ""
        table_page = None
    else:
        candidates.sort(reverse=True, key=lambda x: x[0])
        _, table_page, table_text = candidates[0]

    # Extract values from the first REVENUES section only for product/service rows.
    product = get_row_value(table_text, "Products", "REVENUES", "SEGMENT RESULTS")
    services = get_row_value(table_text, "Services", "REVENUES", "SEGMENT RESULTS")
    total_rev = get_row_value(table_text, "Total Revenues")
    op_income = get_row_value(table_text, "OPERATING INCOME")
    net_income = get_row_value(table_text, "NET INCOME")

    # Row layout is current value, current margin, prior value, prior margin, growth.
    row = {
        "ticker": "OFSS", "financial_year": fy, "quarter": quarter,
        "source_file": path.name, "source_page": table_page,
        "source_type": "QUARTERLY_FINANCIAL_RESULTS_RELEASE",
        "revenue_unit": "INR million",
        "products_revenue_inr_mn": product[0] if len(product)>0 else None,
        "services_revenue_inr_mn": services[0] if len(services)>0 else None,
        "total_revenue_inr_mn": total_rev[0] if len(total_rev)>0 else None,
        "total_revenue_yoy_pct": total_rev[4] if len(total_rev)>4 else None,
        "operating_income_inr_mn": op_income[0] if len(op_income)>0 else None,
        "operating_margin_pct": op_income[1] if len(op_income)>1 else None,
        "operating_income_yoy_pct": op_income[4] if len(op_income)>4 else None,
        "net_income_inr_mn": net_income[0] if len(net_income)>0 else None,
        "net_margin_pct": net_income[1] if len(net_income)>1 else None,
        "net_income_yoy_pct": net_income[4] if len(net_income)>4 else None,
        "extraction_status": "EXTRACTED" if total_rev and op_income and net_income else "REVIEW_REQUIRED"
    }
    commentary = extract_management_quotes(pages)
    manifest = {
        "ticker": "OFSS", "source_file": path.name, "pages": len(doc),
        "financial_year": fy, "quarter": quarter,
        "quarterly_table_page": table_page,
        "management_commentary_blocks": len(commentary),
        "financial_extraction_status": row["extraction_status"]
    }
    return row, commentary, manifest

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Create {INPUT_DIR} and copy the OFSS quarterly financial-report PDFs into it."
        )
    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {INPUT_DIR}")

    actuals, commentary, manifests = [], [], []
    for pdf in pdfs:
        try:
            a, c, m = extract_pdf(pdf)
            actuals.append(a)
            commentary.extend(c)
            manifests.append(m)
        except Exception as exc:
            manifests.append({
                "ticker": "OFSS", "source_file": pdf.name,
                "financial_extraction_status": "FAILED",
                "error": str(exc)
            })

    pd.DataFrame(actuals).to_csv(OUT_DIR / "OFSS_quarterly_actuals.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(commentary).to_csv(OUT_DIR / "OFSS_management_commentary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(manifests).to_csv(OUT_DIR / "OFSS_document_manifest.csv", index=False, encoding="utf-8-sig")

    print(f"PDFs processed: {len(pdfs)}")
    print(f"Quarterly actual rows: {len(actuals)}")
    print(f"Management commentary blocks: {len(commentary)}")
    print("Outputs saved in data/processed/.")
    print("Validate extracted values against the source PDF before final analysis.")
    print("These releases are not full earnings-call transcripts.")

if __name__ == "__main__":
    main()
