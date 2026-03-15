# KI-Exposition des österreichischen Arbeitsmarkts

**AI Exposure of the Austrian Job Market** — an interactive treemap showing how susceptible every occupation in Austria is to AI and automation.

Based on [JoshKale/jobs](https://github.com/JoshKale/jobs) (US/BLS version), adapted for Austria with richer data sourcing and a two-pass LLM pipeline.

**Live:** [zukunftschance.ai.barta.cm](https://zukunftschance.ai.barta.cm)

---

## What it shows

- **1,752 Austrian occupations** from the [AMS Berufslexikon](https://www.berufslexikon.at/)
- **Tile area** proportional to estimated employment (people working in that occupation in Austria)
- **Tile color** = AI exposure score (green = low, red = high)
- **Grouped by 15 Bereiche** (AMS sector taxonomy) with cascading Subbereich + education filters
- **Tooltip**: entry salary (KV Brutto), estimated headcount, ISCO-08 code, education type, job outlook, AI rationale

---

## Data pipeline

Five steps, two LLM passes:

### 1. Occupation list — `parse_occupations.py`

Fetches all 1,752 occupation URLs from the [AMS sitemap](https://www.berufslexikon.at/sitemap/sitemap.xml).

> The AMS Berufslexikon uses a server-side DataTables JSON API that always returns exactly 25 records regardless of pagination parameters — the sitemap was the only reliable way to get the full list.

**Output:** `occupations.json`

### 2. Scrape — `scrape.py`

Downloads every occupation's detail page from berufslexikon.at using `httpx` (no browser needed — AMS does not block bots). ~15–20 min at 0.5s delay.

**Output:** `html/<slug>.html` (gitignored, ~400MB total)

### 3. Parse — `process.py` + `parse_detail.py`

Converts raw HTML to clean Markdown. Extracts:

- **Title** (second `<h1>` on page — first is the site header)
- **Berufsbereich + Subbereich** from `span.beruf-header-bereiche`
- **Ausbildungsform** (education type: Lehre / Schule / Uni/FH/PH / Hilfs / Kurz)
- **Tätigkeitsmerkmale** (job duties) from `<h2>` section
- **Anforderungen** (requirements) from `div#anforderungen`
- **Beschäftigungsmöglichkeiten** (employment sectors) from `div#beschaeftigung`
- **Berufsaussichten** (outlook) from `div#aussichten`
- **Einstiegsgehalt** (KV entry salary, EUR/month) from the header block

**Output:** `pages/<slug>.md` (gitignored, reproducible)

### 4. Extract stats — `make_csv.py`

Parses all HTML files again for structured fields. Includes the full `SUBBEREICH_TO_BEREICH` mapping (91 sub-categories → 15 top-level Bereiche) hard-coded from the AMS taxonomy. Derives an outlook trend label (positive/neutral/negative) from keyword analysis of the Berufsaussichten text.

**Output:** `occupations.csv`

### 5a. AI exposure scoring — `score.py`

Sends each occupation's Markdown description to an LLM (Gemini via OpenRouter) with a German-language scoring rubric. Returns a 0–10 **KI-Exposition** score and a 2–3 sentence rationale.

Calibration anchors:
| Score | Bedeutung | Beispiele |
|-------|-----------|-----------|
| 0–1 | Minimal | Dachdecker/in, Reinigungskraft |
| 2–3 | Gering | Elektriker/in, Feuerwehrmann/-frau |
| 4–5 | Moderat | Krankenpfleger/in, Polizist/in |
| 6–7 | Hoch | Lehrer/in, Buchhalter/in |
| 8–9 | Sehr hoch | Softwareentwickler/in, Übersetzer/in |
| 10 | Maximal | Dateneingabe, Telemarketing |

Incremental checkpointing — safe to interrupt and resume.

**Output:** `scores.json`

### 5b. Headcount + ISCO estimation — `score_headcount.py`

A second LLM pass that asks for each occupation:

- **ISCO-08 4-digit code** (standard international occupation classification)
- **Estimated headcount** in Austria (how many people work in this specific occupation)

The raw LLM estimates are then **normalized against official Statistik Austria data**: ISCO-08 3-digit group totals from the Mikrozensus-Arbeitskräfteerhebung 2023 are embedded in the script. Within each ISCO group, individual job estimates are scaled proportionally so the group total matches the official figure. This keeps the relative sizing from the LLM but grounds absolute numbers in real employment data.

> **Why not just use official data directly?** The AMS Berufslexikon operates at ~1,752 individual job titles, while Statistik Austria / STATcube publishes at ISCO-08 3-digit group level (~130 groups). There is no official crosswalk between AMS job titles and ISCO codes at this level of granularity — LLM mapping + normalization is the most practical approach.

**Output:** `headcounts.json`

### 6. Build site data — `build_site_data.py`

Merges `occupations.csv` + `scores.json` + `headcounts.json` into a single compact JSON for the frontend.

**Output:** `site/data.json`

---

## Data sources

| Source                        | URL                                               | What we use                                                                 |
| ----------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------- |
| AMS Berufslexikon             | [berufslexikon.at](https://www.berufslexikon.at/) | 1,752 occupation profiles: duties, requirements, salary, outlook, education |
| Statistik Austria Mikrozensus | [statistik.at](https://www.statistik.at/)         | ISCO-08 3-digit group employment totals (2023) for normalization            |
| OpenRouter / Gemini           | [openrouter.ai](https://openrouter.ai/)           | AI exposure scoring + ISCO mapping + headcount estimation                   |

---

## Setup

The dev environment uses [devenv](https://devenv.sh) + [direnv](https://direnv.net/). When you `cd` into the project, the shell activates automatically and `uv sync` runs.

```bash
# First time only — devenv builds the Nix shell (~2 min)
cd jobs-at
# direnv activates, uv sync runs

# Add your OpenRouter API key
cp .env.example .env
# edit .env: OPENROUTER_API_KEY=sk-or-v1-...
```

Available commands after activation:

| Command           | What it does                                  |
| ----------------- | --------------------------------------------- |
| `scrape`          | Download AMS pages (~15–20 min)               |
| `process`         | Convert HTML → Markdown                       |
| `make-csv`        | Extract structured stats                      |
| `score`           | AI exposure scoring (~30–60 min, ~€2–5)       |
| `score-headcount` | ISCO + headcount estimation (~20–30 min, ~€3) |
| `normalize`       | Re-run STATcube normalization only            |
| `build`           | Build `site/data.json`                        |
| `serve`           | Serve site locally at :8000                   |
| `deploy`          | Commit data, push, deploy                     |
| `pipeline`        | Run full pipeline in one go                   |

---

## Running the pipeline

```bash
# Steps 1–2 only needed once (or to refresh)
uv run python parse_occupations.py   # fetch occupation list
scrape                               # ~15–20 min
process                              # ~5 min

# Re-run these whenever refreshing data
make-csv                             # ~2 min
score                                # ~30–60 min, needs OPENROUTER_API_KEY
score-headcount                      # ~20–30 min, needs OPENROUTER_API_KEY
build                                # <1 min

# Test locally
serve                                # → http://localhost:8000

# Deploy
deploy
```

`score` and `score-headcount` are both **incremental** — they save after every occupation and skip already-processed ones. Safe to interrupt and resume.

---

## Deployment

Push to `main` → GitHub Actions builds `ghcr.io/markus-barta/jobs-at:latest` → pull on your server.

```bash
# GitHub Actions handles image build automatically on push
# Manual deploy:
deploy   # commits site/data.json, pushes, watches GHA, pulls on server
```

The container is a minimal nginx:alpine serving the static `site/` folder. `site/data.json` is volume-mounted so data updates don't require an image rebuild.

See `Dockerfile`, `nginx.conf`, and `docker-compose.yml` for the container setup.

---

## Visualization

The site is a pure canvas treemap with no external JS dependencies.

- **Tile area** = estimated headcount (normalized against Statistik Austria ISCO group totals)
- **Tile color** = KI-Exposition score on a green → red gradient
- **Grouping** = 15 AMS Bereiche as outer groups (colored borders + labels)
- **Filters** = Bereich → Subbereich → Ausbildung (cascading dropdowns)
- **Language** = DE/EN toggle
- **Click** = opens the AMS Berufslexikon page for that occupation

---

## Caveats

- **AI scores are model-dependent** — Gemini's scores will differ from GPT-4o's. The prompt calibration anchors help but can't eliminate subjectivity. Document the model version used when publishing.
- **Headcounts are estimates** — LLM estimates normalized against ISCO-3 group totals are much better than raw LLM output, but still approximate. Treat as order-of-magnitude, not exact figures.
- **Outlook is heuristic** — derived from keyword analysis of the Berufsaussichten text, not official projections. AMS does not publish quantitative growth forecasts at the individual occupation level.
- **Annual refresh recommended** — AMS updates job profiles and salaries regularly. Re-run the full pipeline once a year.
