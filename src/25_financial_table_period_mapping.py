"""SCRIPT 25 V4: HIGH-PRECISION FINANCIAL HIGHLIGHT CANDIDATE EXTRACTION

Extracts explicit financial highlight statements conservatively.
It does not claim independent verification. It excludes obvious non-financial
numbers (deal wins, client counts, headcount, order book, etc.), keeps currency
and scale explicit, and preserves source evidence.

Run from project root:
    python src/25_financial_table_period_mapping.py
"""
from pathlib import Path
import re
import hashlib
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data/processed/financial_report_page_text.csv"
OUT = ROOT / "data/processed/financial_actuals_period_mapped.csv"
REV = ROOT / "data/processed/financial_actuals_period_mapping_review.csv"
SUM = ROOT / "outputs/financial_actuals_period_mapping_summary.txt"

# Match only explicit financial metric labels. More specific labels come first.
METRIC_PATTERNS = [
    ("EBITDA_MARGIN", r"\b(?:adjusted\s+|adj\.?\s*)?EBITDA\s+margin\b"),
    ("EBIT_MARGIN", r"\bEBIT\s+margin\b"),
    ("PAT_MARGIN", r"\b(?:PAT|net\s+profit|net\s+income)\s+margin\b"),
    ("OPERATING_MARGIN", r"\boperating\s+margin\b"),
    ("REVENUE_GROWTH", r"\b(?:revenue|revenues)\s+(?:growth|grew|up)\b"),
    ("REVENUE", r"\b(?:revenue\s+from\s+operations|revenue|revenues)\b"),
    ("EBITDA", r"\b(?:adjusted\s+|adj\.?\s*)?EBITDA\b"),
    ("EBIT", r"\bEBIT\b"),
    ("PAT_NET_PROFIT", r"\b(?:PAT|profit\s+after\s+tax|net\s+income|net\s+profit)\b"),
    ("PBT", r"\b(?:PBT|profit\s+before\s+tax)\b"),
    ("OPERATING_CASH_FLOW", r"\b(?:operating\s+cash\s+flow|cash\s+flow\s+from\s+operations|cash\s+generated\s+from\s+operations)\b"),
]

NUM = re.compile(r"(?<![A-Za-z])\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?\)?|(?<![A-Za-z])\(?-?\d+(?:\.\d+)?%?\)?")
CURRENCY_TOKEN = re.compile(r"₹|\bINR\b|\$|\bUSD\b|€|\bEUR\b|£|\bGBP\b", re.I)
BAD_CONTEXT = re.compile(
    r"\b(TCV|deal\s+wins?|order\s*book|client(?:s)?|customer(?:s)?|"
    r"headcount|employees?|professionals|attrition|DSO|EPS|"
    r"market\s+cap|bookings?|large\s+deals?|new\s+logos?|"
    r"cash\s*&?\s*cash\s+equivalents?|annualized\s+revenue\s+run\s+rate)\b",
    re.I,
)
# Revenue from Top 5/10/20 clients and revenue by segment are not total revenue.
NON_TOTAL_REVENUE = re.compile(
    r"\b(revenue|revenues)\s+(?:from|by|of)\s+(?:top\s+\d+|"
    r"(?:the\s+)?(?:americas|europe|asia|bfs[i]?|manufacturing|"
    r"services?|software|geograph(?:y|ies)|industry|verticals?|"
    r"offerings?|segments?))\b",
    re.I,
)
PERCENT_METRICS = {"EBITDA_MARGIN", "EBIT_MARGIN", "PAT_MARGIN", "OPERATING_MARGIN", "REVENUE_GROWTH"}
MONETARY_METRICS = {"REVENUE", "EBITDA", "EBIT", "PAT_NET_PROFIT", "PBT", "OPERATING_CASH_FLOW"}

def clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()

def parse_num(token):
    negative = token.startswith("(") and token.endswith(")")
    value = float(token.strip("()").replace(",", "").replace("%", ""))
    return -value if negative else value

def split_clauses(text):
    # Keep short clauses; split flattened PDF text at separators and sentence boundaries.
    raw = re.split(r"[\n\r]+|[|•▪➢●]+|(?<=[.;])\s+(?=[A-Z₹$])", text)
    clauses = []
    for item in raw:
        item = re.sub(r"\s+", " ", item).strip(" \t|")
        if item:
            clauses.append(item)
    # Further split flattened bullet-like content at clear metric starts.
    result = []
    for clause in clauses:
        starts = list(re.finditer(
            r"\b(?:Revenue\s+from\s+operations|Revenue|Revenues|EBITDA\s+Margin|"
            r"EBIT\s+Margin|PAT\s+Margin|Operating\s+Margin|EBITDA|EBIT|"
            r"PAT|Net\s+Income|Net\s+Profit|Profit\s+after\s+tax|PBT)\b",
            clause, re.I
        ))
        if len(starts) <= 1:
            result.append(clause)
        else:
            for i, m in enumerate(starts):
                end = starts[i+1].start() if i+1 < len(starts) else len(clause)
                part = clause[m.start():end].strip(" ,;|")
                if part:
                    result.append(part)
    return result

def metric_for(clause):
    for name, pattern in METRIC_PATTERNS:
        m = re.search(pattern, clause, re.I)
        if m:
            return name, m
    return None, None

def detect_currency(text):
    # Prefer explicit currency marker in the same short clause.
    if "₹" in text or re.search(r"\bINR\b", text, re.I): return "INR"
    if "$" in text or re.search(r"\bUSD\b", text, re.I): return "USD"
    if "€" in text or re.search(r"\bEUR\b", text, re.I): return "EUR"
    if "£" in text or re.search(r"\bGBP\b", text, re.I): return "GBP"
    return "UNKNOWN"

def detect_scale(text):
    t = text.lower()
    if re.search(r"\b(billion|bn)\b", t): return "BILLION"
    if re.search(r"\b(million|mn)\b", t): return "MILLION"
    if re.search(r"\b(crore|cr)\b", t): return "CRORE"
    if re.search(r"\b(thousand|000s?)\b", t): return "THOUSAND"
    # A lone M immediately after a value is a common Indian-report shorthand.
    if re.search(r"\b\d+(?:,\d{3})*(?:\.\d+)?\s*M\b", text): return "MILLION"
    return "UNSPECIFIED"

def metric_value(clause, metric, match):
    # Reject known non-financial contexts before parsing any numbers.
    if BAD_CONTEXT.search(clause):
        return None, "NON_FINANCIAL_CONTEXT"
    if metric == "REVENUE" and NON_TOTAL_REVENUE.search(clause):
        return None, "SEGMENT_OR_CLIENT_REVENUE_NOT_TOTAL"
    tail = clause[match.end():]
    # Require value to follow a clear amount introducer or be the immediate first number.
    # Do not take client counts/years or arbitrary numbers from long prose.
    if metric in PERCENT_METRICS:
        if metric == "REVENUE_GROWTH":
            # Only take the percentage explicitly associated with revenue growth/up.
            p = re.search(r"\b(?:growth|grew|up)\b[^%]{0,45}(-?\d+(?:\.\d+)?)\s*%", tail, re.I)
            if not p:
                p = re.search(r"(-?\d+(?:\.\d+)?)\s*%\s*(?:YoY|QoQ|year[- ]on[- ]year|quarter[- ]on[- ]quarter)", tail, re.I)
            if not p:
                return None, "NO_EXPLICIT_REVENUE_GROWTH_PERCENT"
            return float(p.group(1)), ""
        p = re.search(r"(-?\d+(?:\.\d+)?)\s*%", tail[:100])
        if not p:
            return None, "NO_EXPLICIT_MARGIN_PERCENT"
        return float(p.group(1)), ""
    # Monetary metric: demand a currency marker and amount close to metric label.
    currency = detect_currency(clause)
    if currency == "UNKNOWN":
        return None, "NO_EXPLICIT_CURRENCY"
    # Prefer values after 'at', 'of', ':' or 'was'; avoid values from unrelated clauses.
    p = re.search(
        r"(?:\bat\b|\bof\b|:|was|were)\s*[$₹€£]?\s*\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\b(?:at|of)\s*[$₹€£]?\s*\(?-?\d+(?:\.\d+)?\)?",
        tail[:100], re.I
    )
    if not p:
        # If the amount directly follows the label, accept only when the clause is short.
        p = re.match(r"\s*[$₹€£]?\s*\(?-?\d[\d,]*(?:\.\d+)?\)?", tail)
    if not p:
        return None, "NO_CLEAR_AMOUNT_AFTER_METRIC"
    nums = NUM.findall(p.group(0))
    if not nums:
        return None, "AMOUNT_PARSE_FAILED"
    try:
        return parse_num(nums[-1]), ""
    except Exception:
        return None, "AMOUNT_PARSE_FAILED"

def main():
    if not IN.exists():
        sys.exit(f"Missing input: {IN}")
    # Avoid mixed-dtype fillna warning and preserve metadata values.
    d = pd.read_csv(IN, low_memory=False, dtype=str).fillna("")
    required = ["ticker", "filename_quarter", "verified_quarter", "filename", "page_number", "page_text"]
    missing = [c for c in required if c not in d.columns]
    if missing:
        sys.exit(f"Required page metadata missing: {missing}; found {d.columns.tolist()}")

    mapped, review = [], []
    nonempty_pages = 0
    mismatch_files = d[["ticker", "filename", "filename_quarter", "verified_quarter"]].drop_duplicates()
    mismatch_files = mismatch_files[
        (mismatch_files.verified_quarter != "") &
        (mismatch_files.filename_quarter != "") &
        (mismatch_files.filename_quarter != mismatch_files.verified_quarter)
    ]
    for r in d.itertuples(index=False):
        ticker = clean(r.ticker).upper()
        filename = clean(r.filename)
        filename_q = clean(r.filename_quarter)
        verified_q = clean(r.verified_quarter)
        report_q = verified_q or filename_q
        page = clean(r.page_number)
        page_text = clean(r.page_text)
        if not page_text:
            continue
        nonempty_pages += 1
        if not re.fullmatch(r"FY\d{2}_Q[1-4]", report_q):
            continue

        page_candidates = 0
        seen = set()
        for clause in split_clauses(page_text):
            metric, match = metric_for(clause)
            if not metric:
                continue
            value, reason = metric_value(clause, metric, match)
            if reason:
                # Keep review rows only for clauses that look like actual metric statements.
                if reason not in {"NON_FINANCIAL_CONTEXT", "SEGMENT_OR_CLIENT_REVENUE_NOT_TOTAL"}:
                    review.append({
                        "ticker": ticker, "report_quarter_key": report_q,
                        "source_filename": filename, "source_pdf_page": page,
                        "metric_category": metric, "evidence_text": clause[:1200],
                        "candidate_values": ";".join(NUM.findall(clause)),
                        "review_reason": reason, "filename_quarter": filename_q,
                        "verified_quarter": verified_q,
                    })
                continue
            unit = "PERCENT" if metric in PERCENT_METRICS else detect_currency(clause)
            scale = "NOT_APPLICABLE" if unit == "PERCENT" else detect_scale(clause)
            growth_type = ""
            if metric == "REVENUE_GROWTH":
                if re.search(r"\bQoQ\b|quarter[- ]on[- ]quarter", clause, re.I): growth_type = "QOQ"
                elif re.search(r"\bYoY\b|year[- ]on[- ]year", clause, re.I): growth_type = "YOY"
                else: growth_type = "UNSPECIFIED_GROWTH_BASIS"
            # Avoid duplicate identical clauses within the same page.
            key = (metric, value, unit, clause.lower())
            if key in seen:
                continue
            seen.add(key)
            page_candidates += 1
            rid = hashlib.sha1(
                f"{ticker}|{filename}|{page}|{metric}|{value}|{clause}".encode("utf-8", "ignore")
            ).hexdigest()[:16]
            mapped.append({
                "record_id": rid, "ticker": ticker, "report_quarter_key": report_q,
                "source_filename": filename, "source_pdf_page": page,
                "source_line_number": "", "metric_category": metric,
                "evidence_text": clause, "detected_page_periods": "",
                "unit": unit, "unit_scale": scale,
                "period_basis": "QUARTER_HIGHLIGHT_CANDIDATE",
                "growth_type": growth_type, "observation_quarter_key": report_q,
                "value": value, "mapping_confidence": "MEDIUM",
                "mapping_status": "REPORT_QUARTER_HIGHLIGHT_CANDIDATE",
                "review_reason": "VERIFY_SOURCE_BASIS_AND_VALUE",
                "filename_quarter": filename_q, "verified_quarter": verified_q,
                "consolidated_basis": "NOT_DETERMINED",
                "adjustment_basis": "NOT_DETERMINED",
            })

        # Keep a page-level review marker if financial content exists but no candidate was extracted.
        if page_candidates == 0 and re.search(
            r"\brevenue\b|\bEBITDA\b|\bEBIT\b|\bPAT\b|net income|net profit", page_text, re.I
        ):
            review.append({
                "ticker": ticker, "report_quarter_key": report_q,
                "source_filename": filename, "source_pdf_page": page,
                "metric_category": "UNMAPPED_FINANCIAL_CONTENT",
                "evidence_text": re.sub(r"\s+", " ", page_text)[:1200],
                "candidate_values": "", "review_reason": "TABLE_OR_NARRATIVE_NEEDS_CONTEXTUAL_MAPPING",
                "filename_quarter": filename_q, "verified_quarter": verified_q,
            })

    m, rv = pd.DataFrame(mapped), pd.DataFrame(review)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    SUM.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(OUT, index=False, encoding="utf-8-sig")
    rv.to_csv(REV, index=False, encoding="utf-8-sig")
    metric_counts = m.metric_category.value_counts().to_dict() if not m.empty else {}
    lines = [
        "SCRIPT 25 V4: HIGH-PRECISION FINANCIAL HIGHLIGHT CANDIDATE EXTRACTION",
        "=" * 76, f"Input page rows: {len(d):,}", f"Pages with text: {nonempty_pages:,}",
        f"Filename/verified-quarter mismatches: {len(mismatch_files):,}",
        "Period rule: verified_quarter when present; otherwise filename_quarter.",
        f"Extracted candidates: {len(m):,}", f"Contextual review rows: {len(rv):,}",
        f"Companies represented: {m.ticker.nunique() if not m.empty else 0}",
        f"Report quarters represented: {m.observation_quarter_key.nunique() if not m.empty else 0}",
        "Metric counts:"
    ]
    lines += [f"  {k}: {v:,}" for k, v in sorted(metric_counts.items())]
    lines += [
        "", "LIMITATIONS:",
        "- All output rows are candidates, not independently verified actuals.",
        "- Obvious TCV, deal, client-count, headcount and segment-revenue contexts are excluded.",
        "- Multi-column table alignment is not inferred.",
        "- Currency, scale, consolidated/standalone and adjusted/reported basis require validation.",
        f"Mapped output: {OUT.relative_to(ROOT)}", f"Review output: {REV.relative_to(ROOT)}"
    ]
    SUM.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
