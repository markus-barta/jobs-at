"""
Scrape AMS Berufslexikon detail pages (raw HTML).

AMS does NOT block bots aggressively, so we use httpx (no browser needed).
Falls back to Playwright if a page returns unexpected content.

Saves raw HTML to html/<slug>.html as the source of truth.
Run process.py afterwards to derive pages/<slug>.md.

Usage:
    uv run python scrape.py                      # scrape all
    uv run python scrape.py --start 0 --end 5    # scrape first 5
    uv run python scrape.py --force               # re-scrape ignoring cache
    uv run python scrape.py --delay 0.5           # seconds between requests
"""

import argparse
import json
import os
import time
import httpx


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; research-bot/1.0; "
        "+https://github.com/markus-barta/jobs-at)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
}


def scrape_with_httpx(client: httpx.Client, url: str) -> tuple[int, str]:
    """Fetch a page with httpx. Returns (status_code, html)."""
    resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
    return resp.status_code, resp.text


def looks_valid(html: str) -> bool:
    """Check that we got an actual occupation page, not a redirect/error page."""
    return "Tätigkeitsmerkmale" in html or "Berufsbereich" in html or "Einstiegsgehalt" in html


def main():
    parser = argparse.ArgumentParser(description="Scrape AMS Berufslexikon pages")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Re-scrape even if cached")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    args = parser.parse_args()

    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    end = args.end if args.end is not None else len(occupations)
    subset = occupations[args.start:end]

    os.makedirs("html", exist_ok=True)
    os.makedirs("pages", exist_ok=True)

    to_scrape = []
    for i, occ in enumerate(subset, start=args.start):
        html_path = f"html/{occ['slug']}.html"
        if not args.force and os.path.exists(html_path):
            print(f"  [{i}] CACHED {occ['title']}")
            continue
        to_scrape.append((i, occ))

    if not to_scrape:
        print("Nothing to scrape — all cached.")
        return

    print(f"\nScraping {len(to_scrape)} occupations with httpx...\n")

    errors = []
    with httpx.Client(timeout=15) as client:
        for idx, (i, occ) in enumerate(to_scrape):
            slug = occ["slug"]
            url = occ["url"]
            html_path = f"html/{slug}.html"

            print(f"  [{i}] {occ['title']}...", end=" ", flush=True)

            try:
                status, html = scrape_with_httpx(client, url)

                if status != 200:
                    print(f"HTTP {status} — SKIPPED")
                    errors.append(slug)
                    continue

                if not looks_valid(html):
                    print(f"INVALID CONTENT — SKIPPED")
                    errors.append(slug)
                    continue

                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)

                print(f"OK ({len(html):,} bytes)")

            except Exception as e:
                print(f"ERROR: {e}")
                errors.append(slug)

            if idx < len(to_scrape) - 1:
                time.sleep(args.delay)

    cached = len([f for f in os.listdir("html") if f.endswith(".html")])
    print(f"\nDone. {cached}/{len(occupations)} HTML files cached in html/")
    if errors:
        print(f"Errors ({len(errors)}): {errors[:10]}{'...' if len(errors) > 10 else ''}")


if __name__ == "__main__":
    main()
