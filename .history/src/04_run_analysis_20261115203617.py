"""
Run the initial all-company analyses after manually filling templates.
Supported numeric guidance: low/high range or target values.
Actual revenue growth must use constant-currency (CC) growth where available.
"""
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
OUT.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)

def read_csv(name):
    path = DATA / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run src/03_create_templates.py first.")
    return pd.read_csv(path)

def numeric(series):
    return pd.to_numeric(series, errors="coerce")

def forecast_accountability():
    g = read_csv("guidance_template.csv")
    a = read_csv("actuals_template.csv")
    g.columns = g.columns.str.lower()
    a.columns = a.columns.str.lower()
    merged = g.merge(a, left_on=["ticker", "target_quarter"],
                     right_on=["ticker", "quarter_key"], how="left",
                     suffixes=("_guidance", "_actual"))

    actual = numeric(merged.get("revenue_growth_cc_pct"))
    low = numeric(merged.get("low_pct"))
    high = numeric(merged.get("high_pct"))
    target = numeric(merged.get("target_pct"))

    result = merged.copy()
    result["actual_revenue_growth_cc_pct"] = actual
    result["guidance_midpoint_pct"] = np.where(
        low.notna() & high.notna(), (low + high) / 2, target
    )
    result["outcome"] = ""
    range_ok = actual.notna() & low.notna() & high.notna()
    target_ok = actual.notna() & target.notna()
    result.loc[range_ok & (actual < low), "outcome"] = "BELOW_GUIDANCE"
    result.loc[range_ok & (actual > high), "outcome"] = "ABOVE_GUIDANCE"
    result.loc[range_ok & (actual >= low) & (actual <= high), "outcome"] = "WITHIN_GUIDANCE"
    result.loc[target_ok & (actual < target), "outcome"] = "BELOW_TARGET"
    result.loc[target_ok & (actual >= target), "outcome"] = "AT_OR_ABOVE_TARGET"
    result["absolute_deviation_from_midpoint_pp"] = (
        actual - result["guidance_midpoint_pct"]
    ).abs()
    result.to_csv(OUT / "forecast_accountability.csv", index=False)

    valid = result[result["outcome"] != ""]
    if not valid.empty:
        counts = valid["outcome"].value_counts()
        ax = counts.plot(kind="bar", figsize=(9, 5), title="Management guidance outcomes")
        ax.set_ylabel("Number of observations")
        plt.tight_layout()
        plt.savefig(FIG / "guidance_outcomes.png", dpi=160)
        plt.close()

def communication_change():
    transcripts_path = DATA / "transcripts_text.csv"
    if not transcripts_path.exists():
        print("Skipping communication analysis: transcripts_text.csv not found.")
        return

    df = pd.read_csv(transcripts_path)
    if "text" not in df.columns:
        print("Skipping communication analysis: no 'text' column.")
        return

    certainty = re.compile(r"\b(will|confident|expect|committed|remain|achieve|target)\b", re.I)
    uncertainty = re.compile(r"\b(may|might|uncertain|challenging|subject to|could|depending)\b", re.I)
    rows = []
    for _, r in df.iterrows():
        text = str(r.get("text", ""))
        words = re.findall(r"\b[\w'-]+\b", text)
        rows.append({
            "ticker": r.get("ticker", ""),
            "quarter_key": f"{r.get('fy', '')}_{r.get('quarter', '')}",
            "filename": r.get("filename", ""),
            "word_count": len(words),
            "numeric_token_count": len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text)),
            "certainty_term_count": len(certainty.findall(text)),
            "uncertainty_term_count": len(uncertainty.findall(text)),
            "certainty_per_1000_words": 1000 * len(certainty.findall(text)) / max(len(words), 1),
            "uncertainty_per_1000_words": 1000 * len(uncertainty.findall(text)) / max(len(words), 1),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "communication_change.csv", index=False)
    if not out.empty:
        grouped = out.groupby("quarter_key", as_index=False)[
            ["certainty_per_1000_words", "uncertainty_per_1000_words"]
        ].mean()
        ax = grouped.plot(x="quarter_key", y=[
            "certainty_per_1000_words", "uncertainty_per_1000_words"
        ], figsize=(12, 5), marker="o", title="Communication-language indicators")
        ax.set_ylabel("Terms per 1,000 words")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.savefig(FIG / "communication_change.png", dpi=160)
        plt.close()

def explanation_persistence():
    path = DATA / "explanations_template.csv"
    if not path.exists():
        print("Skipping explanation persistence: explanations_template.csv not found.")
        return
    df = pd.read_csv(path).dropna(subset=["explanation_text"])
    df["explanation_text"] = df["explanation_text"].astype(str).str.strip()
    df = df[df["explanation_text"].str.len() > 20].copy()
    if len(df) < 2:
        print("Skipping explanation persistence: annotate at least two explanation rows.")
        return

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(df["explanation_text"])
    sim = cosine_similarity(matrix)
    records = []
    for i in range(len(df)):
        for j in range(i + 1, len(df)):
            if df.iloc[i]["ticker"] == df.iloc[j]["ticker"] and \
               df.iloc[i]["quarter_key"] != df.iloc[j]["quarter_key"]:
                records.append({
                    "ticker": df.iloc[i]["ticker"],
                    "quarter_1": df.iloc[i]["quarter_key"],
                    "quarter_2": df.iloc[j]["quarter_key"],
                    "similarity": float(sim[i, j]),
                    "text_1": df.iloc[i]["explanation_text"],
                    "text_2": df.iloc[j]["explanation_text"],
                })
    result = pd.DataFrame(records)
    result.to_csv(OUT / "explanation_persistence.csv", index=False)
    if not result.empty:
        repeated = result[result["similarity"] >= 0.45]
        repeated.to_csv(OUT / "potential_repeated_explanations_review.csv", index=False)

def coverage_report():
    manifest_path = DATA / "download_manifest.csv"
    if manifest_path.exists():
        m = pd.read_csv(manifest_path)
        summary = m.groupby(["ticker", "document_type", "status"]).size().unstack(fill_value=0)
        summary.to_csv(OUT / "download_coverage_summary.csv")

def main():
    forecast_accountability()
    communication_change()
    explanation_persistence()
    coverage_report()
    print(f"Analysis outputs saved under: {OUT}")
    print("Similarity scores and dictionary counts are screening indicators; manually validate before reporting.")

if __name__ == "__main__":
    main()
