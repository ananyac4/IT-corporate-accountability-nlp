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
        raise FileNotFoundError(f"Missing {path}")
    return pd.read_csv(path)

def text_key(s):
    return s.astype("string").fillna("").str.strip()

def num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)

def forecast_accountability():
    g = read_csv("guidance_template.csv")
    a = read_csv("actuals_template.csv")
    g.columns = g.columns.str.lower().str.strip()
    a.columns = a.columns.str.lower().str.strip()
    for d in (g, a):
        if "ticker" not in d: d["ticker"] = ""
        d["ticker"] = text_key(d["ticker"]).str.upper()
    if "target_quarter" not in g: g["target_quarter"] = ""
    if "quarter_key" not in a: a["quarter_key"] = ""
    g["target_quarter"] = text_key(g["target_quarter"])
    a["quarter_key"] = text_key(a["quarter_key"])

    # Merge only rows with an explicitly entered target quarter.
    filled = g[g["target_quarter"] != ""].copy()
    blank = g[g["target_quarter"] == ""].copy()
    merged = filled.merge(
        a, left_on=["ticker", "target_quarter"],
        right_on=["ticker", "quarter_key"], how="left",
        suffixes=("_guidance", "_actual")
    )
    for col in a.columns:
        if col not in blank.columns:
            blank[col] = np.nan
    cols = list(dict.fromkeys(list(merged.columns) + list(blank.columns)))
    result = pd.concat([merged.reindex(columns=cols), blank.reindex(columns=cols)], ignore_index=True)

    actual, low, high, target = (
        num(result, "revenue_growth_cc_pct"), num(result, "low_pct"),
        num(result, "high_pct"), num(result, "target_pct")
    )
    result["actual_revenue_growth_cc_pct"] = actual
    result["guidance_midpoint_pct"] = np.where(low.notna() & high.notna(), (low + high) / 2, target)
    result["outcome"] = ""
    is_range = actual.notna() & low.notna() & high.notna()
    is_target = actual.notna() & target.notna()
    result.loc[is_range & (actual < low), "outcome"] = "BELOW_GUIDANCE"
    result.loc[is_range & (actual > high), "outcome"] = "ABOVE_GUIDANCE"
    result.loc[is_range & actual.between(low, high), "outcome"] = "WITHIN_GUIDANCE"
    result.loc[is_target & (actual < target), "outcome"] = "BELOW_TARGET"
    result.loc[is_target & (actual >= target), "outcome"] = "AT_OR_ABOVE_TARGET"
    result["absolute_deviation_from_midpoint_pp"] = (actual - result["guidance_midpoint_pct"]).abs()
    result.to_csv(OUT / "forecast_accountability.csv", index=False)

    valid = result[result["outcome"] != ""]
    if not valid.empty:
        ax = valid["outcome"].value_counts().plot(kind="bar", figsize=(9, 5), title="Management guidance outcomes")
        ax.set_ylabel("Observations")
        plt.tight_layout()
        plt.savefig(FIG / "guidance_outcomes.png", dpi=160)
        plt.close()
    else:
        print("No forecast outcomes yet. Fill target_quarter, guidance values and matching actuals.")
    print(f"Forecast rows saved: {len(result)}")

def communication_change():
    path = DATA / "transcripts_text.csv"
    if not path.exists():
        print("Skipping communication analysis: transcripts_text.csv not found.")
        return
    df = pd.read_csv(path)
    if "text" not in df:
        print("Skipping communication analysis: no text column.")
        return
    certain = re.compile(r"\b(will|confident|expect|committed|remain|achieve|target)\b", re.I)
    uncertain = re.compile(r"\b(may|might|uncertain|challenging|subject to|could|depending)\b", re.I)
    rows = []
    for _, r in df.iterrows():
        txt = "" if pd.isna(r.get("text")) else str(r["text"])
        words = re.findall(r"\b[\w'-]+\b", txt)
        c, u = len(certain.findall(txt)), len(uncertain.findall(txt))
        rows.append({"ticker": r.get("ticker", ""), "quarter_key": f"{r.get('fy','')}_{r.get('quarter','')}",
                     "filename": r.get("filename", ""), "word_count": len(words),
                     "numeric_token_count": len(re.findall(r"\b\d+(?:\.\d+)?%?\b", txt)),
                     "certainty_term_count": c, "uncertainty_term_count": u,
                     "certainty_per_1000_words": 1000*c/max(len(words),1),
                     "uncertainty_per_1000_words": 1000*u/max(len(words),1)})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "communication_change.csv", index=False)
    if not out.empty:
        grouped = out.groupby("quarter_key", as_index=False)[["certainty_per_1000_words","uncertainty_per_1000_words"]].mean()
        ax = grouped.plot(x="quarter_key", y=["certainty_per_1000_words","uncertainty_per_1000_words"],
                          figsize=(12,5), marker="o", title="Communication-language indicators")
        ax.set_ylabel("Terms per 1,000 words")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.savefig(FIG / "communication_change.png", dpi=160)
        plt.close()
    print(f"Communication rows saved: {len(out)}")

def explanation_persistence():
    path = DATA / "explanations_template.csv"
    if not path.exists():
        print("Skipping explanation persistence: template not found.")
        return
    df = pd.read_csv(path)
    required = {"ticker","quarter_key","explanation_text"}
    if not required.issubset(df.columns):
        print(f"Skipping explanation persistence: need columns {sorted(required)}.")
        return
    df = df.dropna(subset=["explanation_text"]).copy()
    df["explanation_text"] = df["explanation_text"].astype(str).str.strip()
    df = df[df["explanation_text"].str.len() > 20]
    if len(df) < 2:
        print("Skipping explanation persistence: annotate at least two explanations.")
        return
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1)
    sim = cosine_similarity(vec.fit_transform(df["explanation_text"]))
    rows = []
    for i in range(len(df)):
        for j in range(i+1, len(df)):
            if str(df.iloc[i]["ticker"]) == str(df.iloc[j]["ticker"]) and str(df.iloc[i]["quarter_key"]) != str(df.iloc[j]["quarter_key"]):
                rows.append({"ticker": df.iloc[i]["ticker"], "quarter_1": df.iloc[i]["quarter_key"],
                             "quarter_2": df.iloc[j]["quarter_key"], "similarity": float(sim[i,j]),
                             "text_1": df.iloc[i]["explanation_text"], "text_2": df.iloc[j]["explanation_text"]})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "explanation_persistence.csv", index=False)
    if not out.empty:
        out[out["similarity"] >= 0.45].to_csv(OUT / "potential_repeated_explanations_review.csv", index=False)
    print(f"Explanation-pair rows saved: {len(out)}")

def coverage_report():
    path = DATA / "download_manifest.csv"
    if path.exists():
        df = pd.read_csv(path)
        if {"ticker","document_type","status"}.issubset(df.columns):
            df.groupby(["ticker","document_type","status"]).size().unstack(fill_value=0).to_csv(OUT / "download_coverage_summary.csv")

def main():
    forecast_accountability()
    communication_change()
    explanation_persistence()
    coverage_report()
    print(f"Outputs saved under {OUT}")
    print("Similarity and dictionary counts are exploratory indicators; manually validate before reporting.")

if __name__ == "__main__":
    main()
