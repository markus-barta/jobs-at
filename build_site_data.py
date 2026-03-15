"""
Build a compact JSON for the website by merging CSV stats with AI exposure scores.

Reads occupations.csv (for stats) and scores.json (for AI exposure).
Writes site/data.json.

Usage:
    uv run python build_site_data.py
"""

import csv
import json
import os


def main():
    # Load AI exposure scores
    with open("scores.json", encoding="utf-8") as f:
        scores_list = json.load(f)
    scores = {s["slug"]: s for s in scores_list}

    # Load CSV stats
    with open("occupations.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Merge
    data = []
    for row in rows:
        slug = row["slug"]
        score = scores.get(slug, {})

        # Parse salary: use midpoint for display, keep min/max
        sal_min = int(row["salary_min_eur"]) if row["salary_min_eur"] else None
        sal_max = int(row["salary_max_eur"]) if row["salary_max_eur"] else None
        sal_mid = round((sal_min + sal_max) / 2) if sal_min and sal_max else (sal_min or sal_max)

        data.append({
            "title": row["title"],
            "slug": slug,
            "category": row["category"],
            "ausbildung": row["ausbildung"],
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_mid": sal_mid,           # used for color/sort in treemap
            "outlook": row["outlook_trend"],  # positive/neutral/negative
            "outlook_text": row["outlook_text"][:200] if row["outlook_text"] else "",
            "sectors": row["employment_sectors"],
            "exposure": score.get("exposure"),
            "rationale": score.get("rationale", ""),
            "url": row["url"],
        })

    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"Wrote {len(data)} occupations to site/data.json")

    # Stats
    with_salary = [d for d in data if d["salary_mid"]]
    with_score = [d for d in data if d["exposure"] is not None]
    if with_salary:
        avg_sal = sum(d["salary_mid"] for d in with_salary) / len(with_salary)
        print(f"Avg entry salary (mid): €{avg_sal:,.0f}/month")
    if with_score:
        avg_exp = sum(d["exposure"] for d in with_score) / len(with_score)
        print(f"Avg AI exposure: {avg_exp:.1f}/10")


if __name__ == "__main__":
    main()
