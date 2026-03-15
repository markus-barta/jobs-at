"""
Fetch the full AMS Berufslexikon occupation list from the sitemap.

The sitemap at berufslexikon.at/sitemap/sitemap.xml contains all ~1,750
occupation URLs in a clean, complete list with no pagination or session tricks.
We parse it, then enrich each entry with category/education data from a
quick API call for the first page.

Usage:
    uv run python parse_occupations.py
    uv run python parse_occupations.py --limit 50   # for testing

Output: occupations.json
"""

import argparse
import json
import re
import time
import httpx

SITEMAP_URL = "https://www.berufslexikon.at/sitemap/sitemap.xml"
API_URL = "https://www.berufslexikon.at/searchjsonsolr/"

# Map AMS education type keys to readable labels
AUSBILDUNG_MAP = {
    "lehre": "Lehre (Apprenticeship)",
    "schule": "Schule (Vocational School)",
    "uni": "Uni/FH/PH (University)",
    "hilfsberufe": "Hilfs-/Anlernberuf (Helper/Semi-skilled)",
    "kurzausbildungen": "Kurz-/Spezialausbildung (Short Course)",
}


def fetch_sitemap_urls(client):
    """Return all occupation URLs from the sitemap."""
    resp = client.get(SITEMAP_URL, timeout=15)
    resp.raise_for_status()
    urls = re.findall(
        r"<loc>(https://www\.berufslexikon\.at/berufe/[^<]+)</loc>",
        resp.text,
    )
    # Filter out the bare /berufe/ index page
    return [u for u in urls if re.search(r"/berufe/\d+", u)]


def url_to_record(url):
    """Build a basic occupation record from a sitemap URL."""
    m = re.search(r"/berufe/(\d+)-([^/]+)/?$", url)
    if not m:
        return None
    beruf_id = m.group(1)
    url_slug = m.group(2)
    # Decode the display title from the URL slug:
    # ~ → / (e.g. "Bankkaufmann~Bankkauffrau" → "Bankkaufmann/-frau")
    title = url_slug.replace("~", "/").replace("-", " ").replace("  ", " ")
    slug = f"{beruf_id}-{url_slug}"
    return {
        "id": beruf_id,
        "title": title,
        "url": url,
        "category": "",
        "ausbildung": "",
        "slug": slug,
    }


def parse_ausbildung(lexikonspan):
    """Derive education type from lexikonspan field (list or string)."""
    items = lexikonspan if isinstance(lexikonspan, list) else [lexikonspan]
    for item in items:
        for key in AUSBILDUNG_MAP:
            if key in str(item):
                return AUSBILDUNG_MAP[key]
    return "Sonstige"


def fetch_api_metadata(client, limit=None):
    """
    Fetch occupation metadata (title, category, education) from the JSON API.
    The API always returns 25 records per call and ignores pagination params,
    so we collect as many unique records as we can from a single call.
    Returns dict keyed by beruf id.
    """
    headers = {
        "Accept": "application/json, text/javascript, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.berufslexikon.at/berufe/",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.berufslexikon.at",
    }
    params = {
        "json": "true", "draw": "1", "start": "0",
        "length": "25", "order[0][column]": "2", "order[0][dir]": "asc",
        "q": "", "q_method": "", "q_alle": "", "q_lehre": "", "q_schule": "",
        "q_uni": "", "q_sonstige1": "", "q_sonstige2": "", "job": "",
        "subbereich": "", "bereich": "", "filter_kat": "",
        "filter_reset": "false", "letter": "",
    }
    resp = client.post(API_URL, data=params, headers=headers, timeout=15)
    if resp.status_code != 200:
        return {}
    rows = resp.json().get("data", [])
    meta = {}
    for row in rows:
        rid = str(row.get("id", ""))
        bereiche_raw = row.get("bereiche", "") or ""
        link_match = re.search(r">([^<]+)</a>", bereiche_raw)
        category = link_match.group(1).strip() if link_match else re.sub(r"<[^>]+>", "", bereiche_raw).strip()
        meta[rid] = {
            "category": category,
            "ausbildung": parse_ausbildung(row.get("lexikonspan", "")),
            "title": re.sub(r"<[^>]+>", "", row.get("title", "")).strip(),
        }
    return meta


def main():
    parser = argparse.ArgumentParser(description="Fetch AMS Berufslexikon occupation list")
    parser.add_argument("--limit", type=int, default=None, help="Max occupations (for testing)")
    args = parser.parse_args()

    with httpx.Client(timeout=15) as client:
        print("Fetching sitemap...")
        urls = fetch_sitemap_urls(client)
        print(f"  Found {len(urls)} occupation URLs in sitemap")

        if args.limit:
            urls = urls[:args.limit]

        # Get metadata from API for the first 25 records
        print("Fetching metadata from JSON API...")
        meta = fetch_api_metadata(client)
        print(f"  Got metadata for {len(meta)} occupations from API")

    # Build occupation records
    occupations = []
    for url in urls:
        rec = url_to_record(url)
        if not rec:
            continue
        # Enrich with API metadata if available
        m = meta.get(rec["id"], {})
        if m.get("title"):
            rec["title"] = m["title"]
        if m.get("category"):
            rec["category"] = m["category"]
        if m.get("ausbildung"):
            rec["ausbildung"] = m["ausbildung"]
        occupations.append(rec)

    # Deduplicate by slug
    seen = set()
    unique = []
    for occ in occupations:
        if occ["slug"] not in seen:
            seen.add(occ["slug"])
            unique.append(occ)

    unique.sort(key=lambda x: x["title"].lower())

    with open("occupations.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(unique)} occupations to occupations.json")
    print(f"Note: category/education only populated for {len(meta)} entries from API.")
    print("These fields will be filled in from scraped HTML by make_csv.py.")

    # Category breakdown (only what we got from API)
    cats = {}
    for occ in unique:
        cat = occ["category"] or "(to be scraped)"
        cats[cat] = cats.get(cat, 0) + 1
    print("\nTop categories:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1])[:12]:
        print(f"  {count:4d}  {cat}")


if __name__ == "__main__":
    main()
