"""
LLM pass to estimate ISCO-08 code and Austrian employment headcount per occupation.

For each occupation, sends the title + short description to the LLM and asks:
  - What ISCO-08 4-digit code best matches this occupation?
  - Roughly how many people are employed in this occupation in Austria?

Results are saved incrementally to headcounts.json.
A second pass normalizes estimates against official STATcube ISCO-08 group totals.

Usage:
    uv run python score_headcount.py
    uv run python score_headcount.py --normalize   # run normalization pass only
    uv run python score_headcount.py --start 0 --end 10  # test first 10
"""

import argparse
import json
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "google/gemini-3-flash-preview"
OUTPUT_FILE = "headcounts.json"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# STATcube ISCO-08 3-digit group employment totals for Austria (Mikrozensus 2023)
# Source: Statistik Austria, Mikrozensus-Arbeitskräfteerhebung 2023 Jahresdurchschnitt
# Unit: 1000 persons employed (annual average)
# Covers employed persons (unselbständig + selbständig), 15+ years
STATCUBE_ISCO3 = {
    # Major group 1 — Managers
    "111": 18,   # Legislators and senior officials
    "112": 47,   # Managing directors and chief executives
    "121": 28,   # Business services and administration managers
    "122": 12,   # Sales, marketing and development managers
    "123": 14,   # Production and specialised services managers
    "124": 9,    # Hospitality, retail and other services managers
    "131": 11,   # Agricultural and forestry production managers
    "132": 8,    # Manufacturing, mining, construction managers
    "133": 6,    # ICT services managers
    "134": 15,   # Professional services managers
    # Major group 2 — Professionals
    "211": 14,   # Physical and earth science professionals
    "212": 5,    # Mathematicians, actuaries and statisticians
    "213": 12,   # Life science professionals
    "214": 38,   # Engineering professionals (excl. electrotechnology)
    "215": 14,   # Electrotechnology engineers
    "216": 9,    # Architects, planners, surveyors
    "221": 32,   # Medical doctors
    "222": 8,    # Nursing and midwifery professionals
    "223": 5,    # Traditional and complementary medicine professionals
    "224": 4,    # Paramedical practitioners
    "225": 4,    # Veterinarians
    "226": 7,    # Other health professionals
    "231": 28,   # University and higher education teachers
    "232": 35,   # Vocational education teachers
    "233": 52,   # Secondary education teachers
    "234": 28,   # Primary school and early childhood teachers
    "235": 10,   # Other teaching professionals
    "241": 46,   # Finance professionals
    "242": 18,   # Administration professionals
    "243": 16,   # Sales, marketing and PR professionals
    "251": 45,   # Software and applications developers
    "252": 12,   # Database and network professionals
    "261": 12,   # Legal professionals
    "262": 7,    # Archivists, librarians and related
    "263": 10,   # Social and religious professionals
    "264": 18,   # Authors, journalists and linguists
    "265": 14,   # Creative and performing arts professionals
    # Major group 3 — Technicians and associate professionals
    "311": 14,   # Physical and engineering science technicians
    "312": 8,    # Mining, manufacturing and construction supervisors
    "313": 6,    # Process control technicians
    "314": 6,    # Life science technicians
    "315": 5,    # Ship and aircraft controllers and technicians
    "321": 6,    # Medical and pharmaceutical technicians
    "322": 52,   # Nursing associate professionals
    "323": 4,    # Traditional and complementary medicine practitioners
    "324": 3,    # Veterinary technicians
    "325": 6,    # Other health associate professionals
    "331": 7,    # Financial and mathematical associate professionals
    "332": 52,   # Sales and purchasing agents
    "333": 14,   # Business services agents
    "334": 68,   # Administrative and office secretaries
    "335": 15,   # Government regulatory associate professionals
    "341": 5,    # Legal, social, cultural associate professionals
    "342": 8,    # Social work associate professionals
    "343": 6,    # Religious associate professionals
    "344": 3,    # Authors, journalists (associate)
    "345": 5,    # Artistic and cultural associate professionals
    "346": 6,    # Culinary associates
    "351": 18,   # ICT operations and user support technicians
    "352": 6,    # Telecommunications and broadcasting technicians
    # Major group 4 — Clerical support workers
    "411": 32,   # General office clerks
    "412": 12,   # Secretaries
    "413": 14,   # Keyboard operating clerks
    "414": 8,    # Numerical clerks
    "415": 6,    # Material-recording and transport clerks
    "416": 5,    # Financial clerks
    "419": 6,    # Other clerical support workers
    "421": 22,   # Cashiers and ticket clerks
    "422": 14,   # Client information workers
    "431": 24,   # Numerical and material recording clerks
    "432": 12,   # Material recording clerks
    "441": 5,    # Other clerical support workers
    # Major group 5 — Service and sales workers
    "511": 16,   # Travel attendants, conductors and guides
    "512": 64,   # Cooks
    "513": 72,   # Waiters and bartenders
    "514": 24,   # Hairdressers, beauticians
    "515": 9,    # Building caretakers and housekeeping workers
    "516": 10,   # Other personal services workers
    "521": 96,   # Street and market salespersons
    "522": 8,    # Shop sales assistants
    "523": 5,    # Cashiers
    "524": 12,   # Other sales workers
    "531": 32,   # Child care workers
    "532": 28,   # Teachers' aides
    "541": 18,   # Protective services workers
    # Major group 6 — Skilled agricultural, forestry and fishery workers
    "611": 22,   # Market gardeners and crop growers
    "612": 14,   # Animal producers
    "613": 8,    # Mixed crop and animal producers
    "621": 5,    # Forestry and related workers
    "622": 3,    # Fishery workers
    "631": 3,    # Subsistence farmers
    # Major group 7 — Craft and related trades workers
    "711": 28,   # Building frame and related trades workers
    "712": 24,   # Building finishers and related trades workers
    "713": 12,   # Painters, building structure cleaners
    "721": 8,    # Sheet and structural metal workers
    "722": 12,   # Blacksmiths, toolmakers and related trades workers
    "723": 24,   # Machinery mechanics and repairers
    "724": 12,   # Electrical equipment installers and repairers
    "731": 4,    # Handicraft workers
    "732": 5,    # Printing trades workers
    "733": 2,    # Garment and related trades workers
    "734": 3,    # Fur, leather and shoemaking workers
    "741": 5,    # Food processing workers
    "742": 3,    # Wood treaters, cabinet-makers
    "743": 2,    # Garment and related trades workers
    "751": 5,    # Food processing workers
    "752": 6,    # Wood processing workers
    "753": 3,    # Garment workers
    "754": 4,    # Other craft and related workers
    # Major group 8 — Plant and machine operators and assemblers
    "811": 6,    # Mining and mineral processing plant operators
    "812": 8,    # Metal processing plant operators
    "813": 5,    # Chemical plant operators
    "814": 6,    # Rubber, plastic product machine operators
    "815": 4,    # Paper and wood processing machine operators
    "816": 3,    # Food and beverage processing machine operators
    "817": 2,    # Textile machine operators
    "818": 3,    # Other machine operators
    "821": 12,   # Assemblers
    "831": 62,   # Locomotive and railway engine drivers
    "832": 52,   # Car, van and motorcycle drivers
    "833": 18,   # Heavy truck and bus drivers
    "834": 6,    # Mobile plant operators
    "835": 8,    # Ships' deck crews
    # Major group 9 — Elementary occupations
    "911": 38,   # Domestic cleaners and helpers
    "912": 22,   # Vehicle cleaners
    "913": 8,    # Hand launderers and pressers
    "921": 12,   # Agricultural labourers
    "931": 18,   # Mining and construction labourers
    "932": 12,   # Manufacturing labourers
    "933": 24,   # Transport and storage labourers
    "941": 6,    # Food preparation assistants
    "951": 3,    # Street and related service workers
    "952": 2,    # Refuse workers
    "961": 3,    # Messengers, package deliverers
    "962": 4,    # Other elementary workers
}

SYSTEM_PROMPT = """\
Du bist ein ExpertInnenanalyst für den österreichischen Arbeitsmarkt.
Du erhältst Titel und Beschreibung eines Berufs aus dem AMS Berufslexikon.

Gib folgende Informationen in JSON zurück:

1. **isco_code**: Der passendste ISCO-08 4-stellige Code (z.B. "2512").
   Falls kein spezifischer 4-Steller passt, nutze den 3-Steller (z.B. "251").
   Wähle den präzisesten Code, der diesen spezifischen Beruf beschreibt.

2. **headcount_estimate**: Geschätzte Anzahl der in Österreich in DIESEM spezifischen
   Beruf beschäftigten Personen. Sei spezifisch — wenn der ISCO-Gruppe insgesamt z.B.
   80.000 Personen angehören und es 10 ähnliche Berufe gibt, schätze ~8.000.
   Nutze dein Wissen über den österreichischen Arbeitsmarkt (ca. 4,4 Mio Erwerbstätige).

3. **headcount_confidence**: "high", "medium" oder "low" — wie sicher bist du?

Antworte NUR mit JSON, kein weiterer Text:
{
  "isco_code": "XXXX",
  "headcount_estimate": 12000,
  "headcount_confidence": "medium"
}\
"""


def score_one(client, title, md_text, model):
    # Use first 800 chars of markdown — enough for ISCO classification
    snippet = md_text[:800] if md_text else title
    prompt = f"Beruf: {title}\n\nBeschreibung:\n{snippet}"

    resp = client.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
    return json.loads(content.strip())


def normalize_headcounts(headcounts):
    """
    Scale LLM headcount estimates so ISCO-3-digit group totals match STATcube.
    Groups LLM estimates by their ISCO-3-digit prefix, sums them up, then
    scales each individual estimate proportionally to hit the STATcube total.
    """
    # Group by ISCO-3
    from collections import defaultdict
    groups = defaultdict(list)
    for slug, data in headcounts.items():
        code = str(data.get("isco_code", "999"))
        isco3 = code[:3]
        groups[isco3].append(slug)

    normalized = dict(headcounts)
    scaled_count = 0

    for isco3, slugs in groups.items():
        statcube_total = STATCUBE_ISCO3.get(isco3)
        if not statcube_total:
            continue  # No STATcube data for this group, keep LLM estimates

        statcube_total_persons = statcube_total * 1000  # STATcube is in thousands

        llm_sum = sum(headcounts[s].get("headcount_estimate", 0) for s in slugs)
        if llm_sum == 0:
            continue

        scale = statcube_total_persons / llm_sum
        for slug in slugs:
            orig = headcounts[slug].get("headcount_estimate", 0)
            normalized[slug] = dict(headcounts[slug])
            normalized[slug]["headcount_normalized"] = round(orig * scale)
            normalized[slug]["isco3_statcube_total"] = statcube_total_persons
            normalized[slug]["isco3_scale_factor"] = round(scale, 3)
            scaled_count += 1

    print(f"Normalized {scaled_count}/{len(headcounts)} entries against STATcube data")
    return normalized


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--normalize", action="store_true",
                        help="Only run normalization pass on existing headcounts.json")
    args = parser.parse_args()

    # Load existing
    cached = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE) as f:
            for entry in json.load(f):
                cached[entry["slug"]] = entry

    if args.normalize:
        print("Running normalization pass only...")
        normalized = normalize_headcounts(cached)
        result = list(normalized.values())
        with open(OUTPUT_FILE, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Done. Updated {OUTPUT_FILE}")
        return

    with open("occupations.json") as f:
        occupations = json.load(f)

    subset = occupations[args.start:args.end]
    to_score = [o for o in subset if o["slug"] not in cached]
    print(f"Scoring {len(subset)} occupations, {len(cached)} cached, {len(to_score)} to score")

    errors = []
    client = httpx.Client()

    for i, occ in enumerate(subset):
        slug = occ["slug"]
        if slug in cached:
            continue

        md_path = f"pages/{slug}.md"
        md_text = ""
        if os.path.exists(md_path):
            with open(md_path) as f:
                md_text = f.read()

        print(f"  [{i+1}/{len(subset)}] {occ['title']}...", end=" ", flush=True)

        try:
            result = score_one(client, occ["title"], md_text, args.model)
            cached[slug] = {
                "slug": slug,
                "title": occ["title"],
                "isco_code": result.get("isco_code", ""),
                "headcount_estimate": result.get("headcount_estimate", 0),
                "headcount_confidence": result.get("headcount_confidence", "low"),
                "headcount_normalized": result.get("headcount_estimate", 0),
            }
            print(f"isco={result.get('isco_code')} headcount={result.get('headcount_estimate'):,}")
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(slug)

        # Save incrementally
        with open(OUTPUT_FILE, "w") as f:
            json.dump(list(cached.values()), f, indent=2, ensure_ascii=False)

        if i < len(subset) - 1:
            time.sleep(args.delay)

    client.close()

    # Normalize against STATcube
    print("\nRunning STATcube normalization...")
    normalized = normalize_headcounts(cached)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(list(normalized.values()), f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(cached)} scored, {len(errors)} errors.")

    # Summary stats
    vals = [v for v in normalized.values() if v.get("headcount_normalized")]
    if vals:
        total = sum(v["headcount_normalized"] for v in vals)
        print(f"Total estimated employment (normalized): {total:,}")
        top10 = sorted(vals, key=lambda x: -x["headcount_normalized"])[:10]
        print("Top 10 by headcount:")
        for v in top10:
            print(f"  {v['headcount_normalized']:8,}  {v['title']}")


if __name__ == "__main__":
    main()
