"""
Parse an AMS Berufslexikon detail page into clean Markdown.

AMS page structure (berufslexikon.at/berufe/{id}-{slug}/):
  - div.beruf-detail: main content container
    - h1 (second one on page): occupation title
    - "Berufsbereiche:" text: category
    - "Ausbildungsform:" text: education type
    - "Einstiegsgehalt lt. KV: Gehalt: € X,- bis € Y,-": salary
    - h2 "Tätigkeitsmerkmale": job duties
    - a[name=anforderungen] / h2 "Anforderungen": requirements
    - a[name=beschaeftigung]: employment sectors
    - a[name=aussichten]: job outlook
    - a[name=ausbildung]: education details

Usage (standalone):
    uv run python parse_detail.py html/3049-3D-DesignerIn.html
"""

import os
import re
import sys
from bs4 import BeautifulSoup


def clean(text):
    """Normalize whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def get_beruf_detail(soup):
    """
    Return the container holding the main occupation content.
    On AMS pages, the beruf-detail div only holds the header (title/salary/category).
    The actual content sections (h2s + content) are in the broader page body,
    so we return the full body and rely on section-specific extractors.
    """
    return soup.body


def parse_salary(detail_div):
    """Extract the KV entry salary from the detail block."""
    text = detail_div.get_text(" ") if detail_div else ""
    m = re.search(
        r"Gehalt:\s*(€\s*[\d.,]+[,\-]+(?:\s*bis\s*€\s*[\d.,]+[,\-]+)?)",
        text,
    )
    if m:
        return m.group(1).strip().rstrip("*").strip()
    return ""


def parse_meta(detail_div):
    """Extract category and education type from the header block."""
    category = ""
    ausbildung = ""
    if not detail_div:
        return category, ausbildung
    # Use collapsed whitespace for reliable regex matching
    text = re.sub(r"\s+", " ", detail_div.get_text(" "))
    m = re.search(r"Berufsbereiche?:\s*(.+?)(?:Ausbildungsform|Einstiegsgehalt|Beruf merken)", text)
    if m:
        category = clean(m.group(1))
    m2 = re.search(r"Ausbildungsform:\s*(.+?)(?:Einstiegsgehalt|Beruf merken|\*)", text)
    if m2:
        ausbildung = clean(m2.group(1))
    return category, ausbildung


def extract_section_after_h2(detail_div, heading_text):
    """Extract content after an h2 with matching text (searches full soup if needed)."""
    # Search in the given div, or fall back to searching the full page
    search_root = detail_div if detail_div else None
    h2_found = None
    if search_root:
        for h2 in search_root.find_all("h2"):
            if heading_text.lower() in h2.get_text().lower():
                h2_found = h2
                break
    if not h2_found:
        return ""

    parts = []
    for sib in h2_found.find_next_siblings():
        if sib.name == "h2":
            break
        if sib.name in ("p", "div"):
            t = clean(sib.get_text())
            if t and not t.startswith("*") and "Hinweis:" not in t and len(t) > 5:
                parts.append(t)
        elif sib.name in ("ul", "ol"):
            for li in sib.find_all("li"):
                t = clean(li.get_text())
                if t:
                    parts.append(f"- {t}")
        elif sib.name == "h3":
            t = clean(sib.get_text())
            if t:
                parts.append(f"\n### {t}")
    return "\n".join(parts).strip()


def extract_section_after_anchor(detail_div, anchor_name):
    """Extract content after a named anchor or matching heading."""
    anchor = detail_div.find("a", {"name": anchor_name})
    if not anchor:
        text_map = {
            "anforderungen": "Anforderungen",
            "beschaeftigung": "Beschäftigungsmöglichkeiten",
            "aussichten": "Berufsaussichten",
            "ausbildung": "Ausbildung",
        }
        heading = text_map.get(anchor_name, "")
        if heading:
            return extract_section_after_h2(detail_div, heading)
        return ""

    parts = []
    for sib in anchor.find_next_siblings():
        tag = getattr(sib, "name", None)
        if tag is None:
            continue
        if tag == "a" and sib.get("name") and sib.get("name") != anchor_name:
            break
        if tag == "div" and "similarberufe" in " ".join(sib.get("class", [])):
            break
        if tag == "p":
            t = clean(sib.get_text())
            if t and not t.startswith("*") and "Hinweis:" not in t and "Gehaltsangaben" not in t:
                parts.append(t)
        elif tag in ("ul", "ol"):
            for li in sib.find_all("li", recursive=False):
                t = clean(li.get_text())
                if t:
                    parts.append(f"- {t}")
        elif tag == "h3":
            t = clean(sib.get_text())
            if t:
                parts.append(f"\n### {t}")

    return "\n".join(parts).strip()


def parse_ams_page(html_path):
    """Parse an AMS Berufslexikon HTML file into Markdown."""
    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    md = []

    # The small beruf-detail div holds header info (title, salary, category)
    header_div = soup.find("div", class_="beruf-detail")
    # The full body is used for content sections
    beruf_div = get_beruf_detail(soup)

    # --- Title: find h1 inside beruf-detail header, or second h1 on page ---
    title = ""
    if header_div:
        h1 = header_div.find("h1")
        if h1:
            title = clean(h1.get_text())
    if not title:
        all_h1 = soup.find_all("h1")
        if len(all_h1) > 1:
            title = clean(all_h1[1].get_text())
        elif all_h1:
            title = clean(all_h1[0].get_text())
    if not title:
        title = os.path.basename(html_path).replace(".html", "")

    md.append(f"# {title}")
    md.append("")

    # --- Source URL ---
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        url = canonical["href"]
        if "/berufe/" in url:
            md.append(f"**Quelle:** {url}")
            md.append("")

    # --- Category + Education (from header div) ---
    category, ausbildung = parse_meta(header_div)
    if category or ausbildung:
        md.append("## Kurzübersicht")
        md.append("")
        if category:
            md.append(f"- **Berufsbereich:** {category}")
        if ausbildung:
            md.append(f"- **Ausbildungsform:** {ausbildung}")
        md.append("")

    # --- Salary (from header div) ---
    salary = parse_salary(header_div)
    if salary:
        md.append(f"**Einstiegsgehalt (KV Brutto):** {salary}")
        md.append("")

    # --- Tätigkeitsmerkmale ---
    if beruf_div:
        duties = extract_section_after_h2(beruf_div, "Tätigkeitsmerkmale")
        if duties:
            md.append("## Tätigkeitsmerkmale")
            md.append("")
            md.append(duties)
            md.append("")

    # --- Anforderungen ---
    if beruf_div:
        req = extract_section_after_anchor(beruf_div, "anforderungen")
        if req:
            md.append("## Anforderungen")
            md.append("")
            md.append(req)
            md.append("")

    # --- Beschäftigungsmöglichkeiten ---
    if beruf_div:
        emp = extract_section_after_anchor(beruf_div, "beschaeftigung")
        if emp:
            md.append("## Beschäftigungsmöglichkeiten")
            md.append("")
            md.append(emp)
            md.append("")

    # --- Berufsaussichten ---
    if beruf_div:
        outlook = extract_section_after_anchor(beruf_div, "aussichten")
        if outlook:
            md.append("## Berufsaussichten")
            md.append("")
            md.append(outlook)
            md.append("")

    # --- Ausbildung (truncated) ---
    if beruf_div:
        edu = extract_section_after_anchor(beruf_div, "ausbildung")
        if edu:
            md.append("## Ausbildung")
            md.append("")
            lines = edu.split("\n")
            trimmed = [l for l in lines if not re.match(r"^\d{4}\s", l)]
            md.append("\n".join(trimmed[:30]))
            md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    html_path = sys.argv[1] if len(sys.argv) > 1 else "html/3049-3D-DesignerIn.html"
    result = parse_ams_page(html_path)
    out_path = html_path.replace("html/", "pages/").replace(".html", ".md")
    os.makedirs("pages", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"Written to {out_path}")
    print()
    print(result)
