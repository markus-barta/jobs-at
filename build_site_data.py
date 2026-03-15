"""
Build a compact JSON for the website by merging CSV stats, AI exposure scores,
and headcount/ISCO data.

Reads:
  - occupations.csv     (stats: salary, bereich, subbereich, ausbildung, outlook)
  - scores.json         (AI exposure 0-10 + rationale)
  - headcounts.json     (ISCO code + normalized headcount estimate)

Writes site/data.json.

Usage:
    uv run python build_site_data.py
"""

import csv
import json
import os


def main():
    # Load AI exposure scores
    scores = {}
    if os.path.exists("scores.json"):
        with open("scores.json", encoding="utf-8") as f:
            for s in json.load(f):
                scores[s["slug"]] = s

    # Load headcounts
    headcounts = {}
    if os.path.exists("headcounts.json"):
        with open("headcounts.json", encoding="utf-8") as f:
            for h in json.load(f):
                headcounts[h["slug"]] = h

    # Load CSV stats
    with open("occupations.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    data = []
    for row in rows:
        slug = row["slug"]
        score = scores.get(slug, {})
        hc = headcounts.get(slug, {})

        sal_min = int(row["salary_min_eur"]) if row.get("salary_min_eur") else None
        sal_max = int(row["salary_max_eur"]) if row.get("salary_max_eur") else None
        sal_mid = round((sal_min + sal_max) / 2) if sal_min and sal_max else (sal_min or sal_max)

        # headcount: use normalized (STATcube-grounded) if available, else raw estimate
        headcount = hc.get("headcount_normalized") or hc.get("headcount_estimate") or None

        data.append({
            "title": row["title"],
            "slug": slug,
            # Grouping
            "bereich": row.get("bereich", ""),
            "subbereich": row.get("subbereich", ""),
            # Education
            "ausbildung": row.get("ausbildung", ""),
            # Salary
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_mid": sal_mid,
            # Outlook
            "outlook": row.get("outlook_trend", "neutral"),
            "outlook_text": (row.get("outlook_text") or "")[:200],
            # Employment
            "headcount": headcount,
            "isco_code": hc.get("isco_code", ""),
            # AI exposure
            "exposure": score.get("exposure"),
            "rationale": score.get("rationale", ""),
            "url": row["url"],
        })

    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Stats
    n = len(data)
    with_bereich = sum(1 for d in data if d["bereich"])
    with_salary = sum(1 for d in data if d["salary_mid"])
    with_score = sum(1 for d in data if d["exposure"] is not None)
    with_hc = sum(1 for d in data if d["headcount"])
    with_edu = sum(1 for d in data if d["ausbildung"])
    with_outlook = sum(1 for d in data if d["outlook"] != "neutral")

    print(f"Wrote {n} occupations to site/data.json")
    print(f"  Bereich:    {with_bereich}/{n} ({100*with_bereich//n}%)")
    print(f"  Ausbildung: {with_edu}/{n} ({100*with_edu//n}%)")
    print(f"  Salary:     {with_salary}/{n} ({100*with_salary//n}%)")
    print(f"  Exposure:   {with_score}/{n} ({100*with_score//n}%)")
    print(f"  Headcount:  {with_hc}/{n} ({100*with_hc//n}%)")
    print(f"  Outlook:    {with_outlook}/{n} non-neutral")

    if with_salary:
        avg_sal = sum(d["salary_mid"] for d in data if d["salary_mid"]) / with_salary
        print(f"  Avg salary: €{avg_sal:,.0f}/month")
    if with_score:
        avg_exp = sum(d["exposure"] for d in data if d["exposure"] is not None) / with_score
        print(f"  Avg exposure: {avg_exp:.1f}/10")
    if with_hc:
        total_hc = sum(d["headcount"] for d in data if d["headcount"])
        print(f"  Total headcount: {total_hc:,}")

    # Bereich breakdown
    bereiche = {}
    for d in data:
        b = d["bereich"] or "(unbekannt)"
        bereiche[b] = bereiche.get(b, 0) + 1
    print(f"\nBereiche ({len(bereiche)}):")
    for b, cnt in sorted(bereiche.items(), key=lambda x: -x[1]):
        print(f"  {cnt:4d}  {b[:60]}")


if __name__ == "__main__":
    main()
