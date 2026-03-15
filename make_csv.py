"""
Build a CSV summary of all AMS occupations from scraped HTML files.

Extracts from the beruf-detail header span:
  - bereich      (top-level Berufsbereich, e.g. "Soziales, Gesundheit, Schönheitspflege")
  - subbereich   (sub-category text inside the bereich, e.g. "Grafik, Design")
  - ausbildung   (Ausbildungsform, e.g. "Lehre", "Uni/FH/PH")

Extracts from section divs (div#anforderungen, div#beschaeftigung, div#aussichten):
  - outlook_text, outlook_trend
  - employment_sectors

Also extracts:
  - salary_min_eur, salary_max_eur  (KV Brutto entry salary)

Usage:
    uv run python make_csv.py
"""

import csv
import json
import os
import re
from bs4 import BeautifulSoup


# Map of Subbereich → Bereich (built from the AMS Bereiche/Branchen page)
# Keys are the subbereich texts as they appear in the HTML
SUBBEREICH_TO_BEREICH = {
    # Bau, Baunebengewerbe, Holz, Gebäudetechnik (84)
    "Anlern- und Hilfsberufe Bau, Holz": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    "Bautechnik, Hochbau, Tiefbau": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    "Gebäudetechnik": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    "Innenausbau, Raumausstattung": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    "Planungswesen, Architektur": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    "Tischlerei, Holz- und Sägetechnik": "Bau, Baunebengewerbe, Holz, Gebäudetechnik",
    # Bergbau, Rohstoffe, Glas, Keramik, Stein (85)
    "Anlern- und Hilfsberufe Bergbau, Rohstoffe": "Bergbau, Rohstoffe, Glas, Keramik, Stein",
    "Bergbau, Rohstoffe": "Bergbau, Rohstoffe, Glas, Keramik, Stein",
    "Glas": "Bergbau, Rohstoffe, Glas, Keramik, Stein",
    "Keramik, Stein": "Bergbau, Rohstoffe, Glas, Keramik, Stein",
    # Büro, Marketing, Finanz, Recht, Sicherheit (86)
    "Anlern- und Hilfsberufe Büro": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Bank-, Finanz- und Versicherungswesen": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Bundesheer, Öffentliche Sicherheit": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Industrie- und Gewerbekaufleute": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Management, Organisation": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Marketing, Werbung, Public Relations": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Private Sicherheits- und Wachdienste": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Recht": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Sekretariat, Kaufmännische Assistenz": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Wirtschaft und Technik": "Büro, Marketing, Finanz, Recht, Sicherheit",
    "Wirtschaftsberatung, Unternehmensdienstleistungen": "Büro, Marketing, Finanz, Recht, Sicherheit",
    # Chemie, Biotechnologie, Lebensmittel, Kunststoffe (87)
    "Anlern- und Hilfsberufe Lebensmittel, Biotechnologie, Chemie": "Chemie, Biotechnologie, Lebensmittel, Kunststoffe",
    "Biotechnologie, Chemie, Kunststoffproduktion": "Chemie, Biotechnologie, Lebensmittel, Kunststoffe",
    "Lebensmittelherstellung": "Chemie, Biotechnologie, Lebensmittel, Kunststoffe",
    "Chemie, Biotechnologie, Lebensmittel, Kunststoffe": "Chemie, Biotechnologie, Lebensmittel, Kunststoffe",
    # Elektrotechnik, Elektronik, Telekommunikation, IT (88)
    "Anlern- und Hilfsberufe Elektrotechnik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Automatisierungs- und Anlagentechnik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Datenbanken": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "EDV- und Netzwerktechnik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Elektroinstallation, Betriebselektrik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Elektromechanik, Elektromaschinen": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Industrielle Elektronik, Mikroelektronik, Messtechnik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "IT-Analyse und -Organisation": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "IT-Support, -Schulung, -Beratung und -Vertrieb": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Softwaretechnik, Programmierung": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    "Telekommunikation, Nachrichtentechnik": "Elektrotechnik, Elektronik, Telekommunikation, IT",
    # Handel, Logistik, Verkehr (89)
    "Anlern- und Hilfsberufe Handel, Kassa": "Handel, Logistik, Verkehr",
    "Anlern- und Hilfsberufe Logistik, Verkehr": "Handel, Logistik, Verkehr",
    "Einzel-, Groß- und Online-Handel": "Handel, Logistik, Verkehr",
    "Lager, Logistik": "Handel, Logistik, Verkehr",
    "Verkaufsaußendienst, Verkaufsvermittlung": "Handel, Logistik, Verkehr",
    "Verkehr": "Handel, Logistik, Verkehr",
    "Vertrieb, Beratung, Einkauf": "Handel, Logistik, Verkehr",
    # Landwirtschaft, Gartenbau, Forstwirtschaft (90)
    "Anlern- und Hilfsberufe Landwirtschaft": "Landwirtschaft, Gartenbau, Forstwirtschaft",
    "Forstwirtschaft, Jagd, Fischerei": "Landwirtschaft, Gartenbau, Forstwirtschaft",
    "Landbau, Viehwirtschaft, Tierbetreuung": "Landwirtschaft, Gartenbau, Forstwirtschaft",
    "Obst-, Wein- und Gartenbau": "Landwirtschaft, Gartenbau, Forstwirtschaft",
    # Maschinenbau, Kfz, Metall (91)
    "Anlern- und Hilfsberufe Kfz, Metall": "Maschinenbau, Kfz, Metall",
    "Kfz-Bau und Fahrzeugservice": "Maschinenbau, Kfz, Metall",
    "Maschinen- und Anlagenbau": "Maschinenbau, Kfz, Metall",
    "Maschineneinrichtung und -optimierung": "Maschinenbau, Kfz, Metall",
    "Metallbe- und -verarbeitung": "Maschinenbau, Kfz, Metall",
    # Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk (92)
    "Anlern- und Hilfsberufe Kunst, Druck, Papier": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Bildende Kunst, Fotografie": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Darstellende Kunst, Musik": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Druck, Druckvorstufe, Papier": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Grafik, Design": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Kunsthandwerk, Uhren, Schmuck": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Printmedien, Neue Medien": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Rundfunk, Film und Fernsehen": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk": "Medien, Grafik, Design, Druck, Kunst, Kunsthandwerk",
    # Reinigung, Hausbetreuung, Anlern- und Hilfsberufe (93)
    "Allgemeine und sonstige Anlern- und Hilfsberufe": "Reinigung, Hausbetreuung, Anlern- und Hilfsberufe",
    "Hausbetreuung, Liegenschaftsverwaltung": "Reinigung, Hausbetreuung, Anlern- und Hilfsberufe",
    "Reinigung": "Reinigung, Hausbetreuung, Anlern- und Hilfsberufe",
    # Soziales, Gesundheit, Schönheitspflege (94)
    "Ärztliche Berufe": "Soziales, Gesundheit, Schönheitspflege",
    "Gehobene medizinisch-technische Dienste": "Soziales, Gesundheit, Schönheitspflege",
    "Gesundheits- und Krankenpflege, Hebammen": "Soziales, Gesundheit, Schönheitspflege",
    "Gewerbliche und technische Gesundheitsberufe": "Soziales, Gesundheit, Schönheitspflege",
    "Handel mit Gesundheitsprodukten": "Soziales, Gesundheit, Schönheitspflege",
    "Kinderpädagogik und -betreuung": "Soziales, Gesundheit, Schönheitspflege",
    "Medizinische Assistenzberufe, Sanitätsberufe, Massage": "Soziales, Gesundheit, Schönheitspflege",
    "Religiöse Dienste, Seelsorge, Bestattung": "Soziales, Gesundheit, Schönheitspflege",
    "Schönheitspflege, Kosmetik": "Soziales, Gesundheit, Schönheitspflege",
    "Sozial- und Gesundheitsmanagement": "Soziales, Gesundheit, Schönheitspflege",
    "Soziale Betreuung, Beratung, Therapie": "Soziales, Gesundheit, Schönheitspflege",
    "Soziales, Gesundheit, Schönheitspflege": "Soziales, Gesundheit, Schönheitspflege",
    # Textil und Bekleidung, Mode, Leder (95)
    "Anlern- und Hilfsberufe Textil": "Textil und Bekleidung, Mode, Leder",
    "Bekleidung, Textil": "Textil und Bekleidung, Mode, Leder",
    "Ledererzeugung und -verarbeitung": "Textil und Bekleidung, Mode, Leder",
    # Tourismus, Gastgewerbe, Freizeit (96)
    "Anlern- und Hilfsberufe Tourismus, Gastgewerbe, Freizeit": "Tourismus, Gastgewerbe, Freizeit",
    "Hotelempfang, Etage": "Tourismus, Gastgewerbe, Freizeit",
    "Hotelverwaltung, Gaststättenleitung": "Tourismus, Gastgewerbe, Freizeit",
    "Küchen- und Servicefachkräfte": "Tourismus, Gastgewerbe, Freizeit",
    "Reise- und Freizeitgestaltung": "Tourismus, Gastgewerbe, Freizeit",
    "Sport, Sportunterricht": "Tourismus, Gastgewerbe, Freizeit",
    # Umwelt (97)
    "Energietechnik, Erneuerbare Energie": "Umwelt",
    "Umwelt-, Natur- und Landschaftsgestaltung": "Umwelt",
    "Umweltconsulting, -forschung und -pädagogik": "Umwelt",
    "Umwelttechnologie, Nachhaltigkeit": "Umwelt",
    # Wissenschaft, Bildung, Forschung und Entwicklung (98)
    "Forschung und Entwicklung": "Wissenschaft, Bildung, Forschung und Entwicklung",
    "Geistes-, Kultur- und Humanwissenschaften": "Wissenschaft, Bildung, Forschung und Entwicklung",
    "Naturwissenschaften, Lebenswissenschaften": "Wissenschaft, Bildung, Forschung und Entwicklung",
    "Schule, Weiterbildung, Hochschule": "Wissenschaft, Bildung, Forschung und Entwicklung",
    "Sozial-, Wirtschafts- und Rechtswissenschaften": "Wissenschaft, Bildung, Forschung und Entwicklung",
}


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_header(soup):
    """
    Extract bereich, subbereich, ausbildung from the beruf-detail header span.
    The span.beruf-header-bereiche contains the full Berufsbereiche text.
    """
    bereich = ""
    subbereich = ""
    ausbildung = ""

    bd = soup.find("div", class_="beruf-detail")
    if not bd:
        return bereich, subbereich, ausbildung

    # The span.beruf-header-bereiche has the Berufsbereiche text
    span = bd.find("span", class_="beruf-header-bereiche")
    if span:
        text = clean(span.get_text(" "))
        # Extract category (Berufsbereiche: X Ausbildungsform: Y)
        m = re.search(r"Berufsbereiche?:\s*(.+?)(?:Ausbildungsform|$)", text)
        if m:
            subbereich = clean(m.group(1))
            # Map subbereich to top-level bereich
            bereich = SUBBEREICH_TO_BEREICH.get(subbereich, subbereich)

        m2 = re.search(r"Ausbildungsform:\s*(.+?)(?:Einstiegsgehalt|Beruf merken|\*|$)", text)
        if m2:
            # Strip trailing noise like "Infos zur Lehrlingsentschädigung..."
            raw = clean(m2.group(1))
            # Keep only the first word/phrase before any "Infos" text
            ausbildung = re.split(r"\s+Infos", raw)[0].strip()
            # Normalize to clean labels
            if "Lehre" in ausbildung:
                ausbildung = "Lehre"
            elif "Uni" in ausbildung or "FH" in ausbildung:
                ausbildung = "Uni/FH/PH"
            elif "Schule" in ausbildung or "BMS" in ausbildung or "BHS" in ausbildung:
                ausbildung = "Schule"
            elif "Hilfs" in ausbildung or "Anlern" in ausbildung:
                ausbildung = "Hilfs-/Anlernberuf"
            elif "Kurz" in ausbildung or "Spezial" in ausbildung:
                ausbildung = "Kurz-/Spezialausbildung"

    return bereich, subbereich, ausbildung


def parse_salary(soup):
    """Extract KV entry salary. Returns (min_str, max_str) as integer strings."""
    bd = soup.find("div", class_="beruf-detail")
    text = clean(bd.get_text(" ")) if bd else ""

    m = re.search(
        r"Gehalt:\s*(€\s*[\d.,]+[,\-]+(?:\s*bis\s*€\s*[\d.,]+[,\-]+)?)",
        text,
    )
    if not m:
        return "", ""

    salary_str = m.group(1)
    parts = re.split(r"\s*bis\s*", salary_str)
    min_val = _eur_int(re.sub(r"[^\d.,]", "", parts[0]))
    max_val = _eur_int(re.sub(r"[^\d.,]", "", parts[1])) if len(parts) > 1 else min_val
    return min_val, max_val


def _eur_int(s):
    s = re.sub(r"[.,\s\-]+$", "", s)
    s = re.sub(r"\.", "", s)
    s = re.sub(r",\d+$", "", s)
    return s.strip() if re.match(r"^\d+$", s.strip()) else ""


def parse_section_div(soup, div_id):
    """Extract text content from a named div section (div#anforderungen etc.)."""
    div = soup.find("div", id=div_id)
    if not div:
        return ""
    parts = []
    for child in div.children:
        if not hasattr(child, "name") or not child.name:
            continue
        if child.name in ("p", "div"):
            t = clean(child.get_text())
            if t and len(t) > 5 and not t.startswith("*"):
                parts.append(t)
        elif child.name in ("ul", "ol"):
            for li in child.find_all("li"):
                t = clean(li.get_text())
                if t:
                    parts.append(f"- {t}")
    return "\n".join(parts).strip()


def parse_outlook(soup):
    """Extract Berufsaussichten text and derive a trend label."""
    text = parse_section_div(soup, "aussichten")
    if not text:
        # Fallback: look for h2 Berufsaussichten
        for h2 in soup.find_all("h2"):
            if "aussicht" in h2.get_text().lower():
                parts = []
                for sib in h2.find_next_siblings():
                    if sib.name == "h2":
                        break
                    if sib.name in ("p", "div"):
                        t = clean(sib.get_text())
                        if t and len(t) > 10:
                            parts.append(t)
                    if len(parts) >= 3:
                        break
                text = " ".join(parts)
                break

    if not text:
        return "", "neutral"

    positive_kw = ["steigt", "wächst", "zunimmt", "steigende", "wachsend", "gute",
                   "sehr gute", "stark gefragt", "gefragt", "positiv", "zunehmen",
                   "mehr", "ansteig", "boomen", "boom", "rosig", "günstig"]
    negative_kw = ["sinkt", "rückgang", "abnimmt", "abnehmend", "schlechte",
                   "schwierig", "rückläufig", "gesättig", "übersättig", "wenig",
                   "keine", "kaum"]
    text_lower = text.lower()
    pos = sum(1 for kw in positive_kw if kw in text_lower)
    neg = sum(1 for kw in negative_kw if kw in text_lower)

    trend = "positive" if pos > neg else ("negative" if neg > pos else "neutral")
    return text[:400], trend


def parse_employment_sectors(soup):
    """Extract employment sectors from div#beschaeftigung."""
    text = parse_section_div(soup, "beschaeftigung")
    if not text:
        return ""
    # Return first 300 chars of the section
    return text[:300]


def extract_occupation(html_path, occ_meta):
    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    bereich, subbereich, ausbildung = parse_header(soup)
    salary_min, salary_max = parse_salary(soup)
    outlook_text, outlook_trend = parse_outlook(soup)
    sectors = parse_employment_sectors(soup)

    return {
        "title": occ_meta["title"],
        "bereich": bereich,
        "subbereich": subbereich,
        "ausbildung": ausbildung,
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
        "title", "bereich", "subbereich", "ausbildung", "ams_id", "slug",
        "salary_min_eur", "salary_max_eur",
        "outlook_text", "outlook_trend",
        "employment_sectors", "url",
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

    # Stats
    with_bereich = sum(1 for r in rows if r["bereich"])
    with_salary = sum(1 for r in rows if r["salary_min_eur"])
    with_outlook = sum(1 for r in rows if r["outlook_text"])
    with_edu = sum(1 for r in rows if r["ausbildung"])
    print(f"\nField coverage:")
    print(f"  Bereich:    {with_bereich}/{len(rows)} ({100*with_bereich//len(rows)}%)")
    print(f"  Ausbildung: {with_edu}/{len(rows)} ({100*with_edu//len(rows)}%)")
    print(f"  Salary:     {with_salary}/{len(rows)} ({100*with_salary//len(rows)}%)")
    print(f"  Outlook:    {with_outlook}/{len(rows)} ({100*with_outlook//len(rows)}%)")

    trends = {}
    for r in rows:
        t = r["outlook_trend"]
        trends[t] = trends.get(t, 0) + 1
    print(f"  Outlook distribution: {trends}")

    bereiche = {}
    for r in rows:
        b = r["bereich"] or "(unbekannt)"
        bereiche[b] = bereiche.get(b, 0) + 1
    print(f"\nBereiche ({len(bereiche)}):")
    for b, n in sorted(bereiche.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {b[:60]}")


if __name__ == "__main__":
    main()
