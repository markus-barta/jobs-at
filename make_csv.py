"""
Build a CSV summary of all AMS occupations from scraped HTML files.

Extracts:
  - title, category (Berufsbereich), ausbildung (education type)
  - salary_min_eur, salary_max_eur (KV Brutto entry salary range)
  - outlook_text (Berufsaussichten qualitative description)
  - outlook_trend (positive/neutral/negative — heuristic from outlook text)
  - employment_sectors (from Beschäftigungsmöglichkeiten)
  - ams_id, slug, url

Usage:
    uv run python make_csv.py
"""

import csv
import json
import os
import re
from bs4 import BeautifulSoup


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_salary(soup: BeautifulSoup) -> tuple[str, str]:
    """
    Extract KV entry salary range.
    Typical formats:
      "€ 2.460,- bis € 2.800,-"
      "€ 1.800,-"
      "€ 2.500,- bis € 3.200,- *"
    Returns (min_eur, max_eur) as plain integers (e.g. "2460", "2800").
    """
    # Search all text on the page
    full_text = soup.get_text(" ")

    # Find the salary block — appears after "Gehalt:" or "Einstiegsgehalt"
    m = re.search(
        r"(?:Gehalt:|Einstiegsgehalt lt\. KV:)\s*(€\s*[\d.,]+(?:\s*bis\s*€\s*[\d.,]+)?)",
        full_text,
    )
    if not m:
        # Looser search for any EUR range
        m = re.search(r"€\s*([\d.,]+)[,-]+\s*bis\s*€\s*([\d.,]+)[,-]+", full_text)
        if m:
            return _eur_int(m.group(1)), _eur_int(m.group(2))
        return "", ""

    salary_str = m.group(1)
    # Split on "bis"
    parts = re.split(r"\s*bis\s*", salary_str)
    min_val = _eur_int(re.sub(r"[^\d.,]", "", parts[0]))
    max_val = _eur_int(re.sub(r"[^\d.,]", "", parts[1])) if len(parts) > 1 else min_val
    return min_val, max_val


def _eur_int(s: str) -> str:
    """Convert '2.460,-' or '2460' to '2460'."""
    s = re.sub(r"[.,\s\-]+$", "", s)   # strip trailing punctuation
    s = re.sub(r"\.", "", s)            # remove thousand separator
    s = re.sub(r",\d+$", "", s)        # remove decimal part
    return s.strip() if re.match(r"^\d+$", s.strip()) else ""


def parse_outlook(soup: BeautifulSoup) -> tuple[str, str]:
    """
    Extract Berufsaussichten text and derive a trend label.
    Returns (outlook_text, trend) where trend in {positive, neutral, negative}.
    """
    anchor = soup.find("a", {"name": "aussichten"}) or soup.find(id="aussichten")
    if not anchor:
        return "", "neutral"

    paragraphs = []
    for sib in anchor.find_next_siblings():
        if sib.name in ("h2", "h3"):
            break
        if sib.name == "a" and sib.get("name") and sib.get("name") != "aussichten":
            break
        if sib.name == "p":
            t = clean(sib.get_text())
            if t:
                paragraphs.append(t)

    outlook_text = " ".join(paragraphs[:2])  # first two paragraphs

    # Heuristic: detect trend keywords
    positive_kw = [
        "steigt", "wächst", "zunimmt", "steigende", "wachsend", "gute",
        "sehr gute", "stark gefragt", "gefrag", "positiv", "zunehmen",
        "mehr", "ansteig", "boomen", "boom",
    ]
    negative_kw = [
        "sinkt", "rückgang", "abnimmt", "abnehmend", "schlechte",
        "schwierig", "rückläufig", "gesättig", "übersättig", "wenig",
    ]
    text_lower = outlook_text.lower()
    pos_score = sum(1 for kw in positive_kw if kw in text_lower)
    neg_score = sum(1 for kw in negative_kw if kw in text_lower)

    if pos_score > neg_score:
        trend = "positive"
    elif neg_score > pos_score:
        trend = "negative"
    else:
        trend = "neutral"

    return outlook_text[:500], trend


def parse_employment_sectors(soup: BeautifulSoup) -> str:
    """Extract a short list of employment sectors from Beschäftigungsmöglichkeiten."""
    anchor = soup.find("a", {"name": "beschaeftigung"}) or soup.find(id="beschaeftigung")
    if not anchor:
        return ""

    items = []
    for sib in anchor.find_next_siblings():
        if sib.name in ("h2", "h3"):
            break
        if sib.name == "a" and sib.get("name") and sib.get("name") != "beschaeftigung":
            break
        if sib.name in ("ul", "ol"):
            for li in sib.find_all("li"):
                t = clean(li.get_text())
                if t:
                    items.append(t)
            break  # only first list

    return "; ".join(items[:8])


def extract_occupation(html_path: str, occ_meta: dict) -> dict:
    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    salary_min, salary_max = parse_salary(soup)
    outlook_text, outlook_trend = parse_outlook(soup)
    sectors = parse_employment_sectors(soup)

    return {
        "title": occ_meta["title"],
        "category": occ_meta["category"],
        "ausbildung": occ_meta["ausbildung"],
        "ams_id": occ_meta["id"],
        "slug": occ_meta["slug"],
        "url": occ_meta["url"],
        "salary_min_eur": salary_min,
        "salary_max_eur": salary_max,
        "outlook_text": outlook_text,
        "outlook_trend": outlook_trend,
        "employment_sectors": sectors,
    }


def main():
    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    fieldnames = [
        "title", "category", "ausbildung", "ams_id", "slug",
        "salary_min_eur", "salary_max_eur",
        "outlook_text", "outlook_trend",
        "employment_sectors",
        "url",
    ]

    rows = []
    missing = 0
    errors = 0

    for occ in occupations:
        html_path = f"html/{occ['slug']}.html"
        if not os.path.exists(html_path):
            missing += 1
            continue
        try:
            row = extract_occupation(html_path, occ)
            rows.append(row)
        except Exception as e:
            print(f"  ERROR {occ['slug']}: {e}")
            errors += 1

    with open("occupations.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to occupations.csv")
    print(f"Missing HTML: {missing}, Errors: {errors}")

    # Quick sanity check
    sample = [r for r in rows if r["salary_min_eur"]][:5]
    print(f"\nSample rows (with salary):")
    for r in sample:
        print(f"  {r['title']}: €{r['salary_min_eur']}-{r['salary_max_eur']}/mo, outlook: {r['outlook_trend']}")

    # Trend breakdown
    trends: dict[str, int] = {}
    for r in rows:
        t = r["outlook_trend"]
        trends[t] = trends.get(t, 0) + 1
    print(f"\nOutlook trend distribution: {trends}")


if __name__ == "__main__":
    main()
