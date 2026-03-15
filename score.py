"""
Score each occupation's AI exposure using an LLM via OpenRouter.

Reads Markdown descriptions from pages/, sends each to an LLM with a scoring
rubric, and collects structured scores. Results are cached incrementally to
scores.json so the script can be resumed if interrupted.

Usage:
    uv run python score.py
    uv run python score.py --model google/gemini-2.5-flash-preview
    uv run python score.py --start 0 --end 10   # test on first 10
    uv run python score.py --force               # re-score all
"""

import argparse
import json
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "google/gemini-2.5-flash"
OUTPUT_FILE = "scores.json"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
Du bist ein ExpertInnenanalyst, der bewertet, wie stark verschiedene Berufe \
durch KI (Künstliche Intelligenz) und Automatisierung betroffen sein werden. \
Du erhältst eine detaillierte Beschreibung eines Berufs.

Bewerte die **KI-Exposition** des Berufs auf einer Skala von 0 bis 10.

KI-Exposition misst: Wie stark wird KI diesen Beruf verändern? Berücksichtige \
sowohl direkte Effekte (KI übernimmt Aufgaben, die derzeit Menschen erledigen) \
als auch indirekte Effekte (KI macht einzelne Arbeitskräfte so produktiv, \
dass weniger gebraucht werden).

Ein wesentliches Signal ist, ob das Arbeitsprodukt grundsätzlich digital ist. \
Wenn der Beruf vollständig von zuhause am Computer ausgeübt werden kann — \
Schreiben, Programmieren, Analysieren, Kommunizieren — ist die KI-Exposition \
inhärent hoch (7+), da KI-Fähigkeiten in digitalen Bereichen rasant \
zunehmen. Jobs, die physische Anwesenheit, manuelle Fähigkeiten oder \
Echtzeit-Interaktion mit Menschen erfordern, haben dagegen natürliche Barrieren.

Verwende diese Ankerpunkte zur Kalibrierung:

- **0–1: Minimale Exposition.** Die Arbeit ist fast ausschließlich körperlich \
oder erfordert menschliche Anwesenheit in unvorhersehbaren Umgebungen. KI hat \
praktisch keinen Einfluss. \
Beispiele: Dachdecker/in, Reinigungskraft, Bauarbeiter/in.

- **2–3: Geringe Exposition.** Überwiegend körperliche oder zwischenmenschliche \
Arbeit. KI kann bei peripheren Aufgaben (Terminplanung, Dokumentation) helfen, \
berührt aber nicht den Kernberuf. \
Beispiele: Elektriker/in, Klempner/in, Feuerwehrmann/-frau, Zahntechniker/in.

- **4–5: Moderate Exposition.** Mix aus körperlicher/zwischenmenschlicher und \
Wissensarbeit. KI kann bei der Informationsverarbeitung helfen, ein wesentlicher \
Anteil der Arbeit erfordert aber noch menschliche Präsenz. \
Beispiele: Krankenpfleger/in, Polizist/in, Tierarzt/-ärztin.

- **6–7: Hohe Exposition.** Überwiegend Wissensarbeit mit einigen Anforderungen \
an menschliches Urteilsvermögen, Beziehungen oder physische Präsenz. \
KI-Tools sind bereits nützlich. \
Beispiele: Lehrer/in, Manager/in, Buchhalter/in, Journalist/in.

- **8–9: Sehr hohe Exposition.** Der Beruf wird fast ausschließlich am Computer \
ausgeübt. Alle Kernaufgaben — Schreiben, Programmieren, Analysieren, Gestalten, \
Kommunizieren — liegen in Bereichen, in denen KI rasch voranschreitet. \
Beispiele: Softwareentwickler/in, Grafikdesigner/in, Übersetzer/in, \
Datenanalyst/in, Juristischer Assistent/in, Texter/in.

- **10: Maximale Exposition.** Reine Informationsverarbeitung, vollständig \
digital, kein physischer Anteil. KI kann heute schon den Großteil übernehmen. \
Beispiele: Dateneingabe, Telemarketing.

Antworte NUR mit einem JSON-Objekt in genau diesem Format, kein weiterer Text:
{
  "exposure": <0-10>,
  "rationale": "<2-3 Sätze, die die entscheidenden Faktoren erklären>"
}\
"""


def score_occupation(client: httpx.Client, text: str, model: str) -> dict:
    """Send one occupation to the LLM and parse the structured response."""
    response = client.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--force", action="store_true", help="Re-score even if already cached")
    args = parser.parse_args()

    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    subset = occupations[args.start:args.end]

    # Load existing scores
    scores: dict[str, dict] = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["slug"]] = entry

    print(f"Scoring {len(subset)} occupations with {args.model}")
    print(f"Already cached: {len(scores)}")

    errors = []
    client = httpx.Client()

    for i, occ in enumerate(subset):
        slug = occ["slug"]

        if slug in scores:
            continue

        md_path = f"pages/{slug}.md"
        if not os.path.exists(md_path):
            print(f"  [{i+1}] SKIP {slug} (no markdown)")
            continue

        with open(md_path, encoding="utf-8") as f:
            text = f.read()

        print(f"  [{i+1}/{len(subset)}] {occ['title']}...", end=" ", flush=True)

        try:
            result = score_occupation(client, text, args.model)
            scores[slug] = {
                "slug": slug,
                "title": occ["title"],
                **result,
            }
            print(f"exposure={result['exposure']}")
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(slug)

        # Save after each one (incremental checkpoint)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(list(scores.values()), f, indent=2, ensure_ascii=False)

        if i < len(subset) - 1:
            time.sleep(args.delay)

    client.close()

    print(f"\nDone. Scored {len(scores)} occupations, {len(errors)} errors.")
    if errors:
        print(f"Errors: {errors}")

    # Summary stats
    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        avg = sum(s["exposure"] for s in vals) / len(vals)
        by_score: dict[int, int] = {}
        for s in vals:
            bucket = s["exposure"]
            by_score[bucket] = by_score.get(bucket, 0) + 1
        print(f"\nDurchschnittliche KI-Exposition über {len(vals)} Berufe: {avg:.1f}")
        print("Verteilung:")
        for k in sorted(by_score):
            print(f"  {k}: {'█' * by_score[k]} ({by_score[k]})")


if __name__ == "__main__":
    main()
