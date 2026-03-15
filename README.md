# AI Exposure of the Austrian Job Market

Analyzing how susceptible every occupation in the Austrian economy is to AI and automation.

Based on [JoshKale/jobs](https://github.com/JoshKale/jobs) (US version using BLS data), adapted for Austria using Statistik Austria, AMS, and ISCO-08 classifications.

## Plan

### Phase 1: Occupation List (ISCO-08)

Build `occupations.json` -- the master list of Austrian occupations with ISCO codes.

**Sources:**

- **Statistik Austria** employment tables (.ods downloads) -- contain ISCO occupation groups with employment totals (~4.5M employed)
- **STATcube** (free open database) -- Microcensus Labour Force Survey data with ISCO codes, queryable as CSV
- ISCO-08 classification from ILO for the canonical occupation taxonomy

**Output:** `occupations.json` with title (German), ISCO code, category/group, slug

### Phase 2: Occupation Stats

Build `occupations.csv` with structured numbers per occupation.

**Sources:**

- **Statistik Austria / STATcube** -- employment counts by ISCO, broken down by:
  - Gender, age group
  - Education level
  - Sector (ONACE)
  - Region (Bundesland / Bezirk)
- **Register-based Labour Market Statistics** -- wages (gross annual income cross-tabbed with ISCO)
- **Census 2021** (PDF/ODS) -- additional cross-tabs for education x occupation

**Fields:** `isco_code, title, employment_count, median_pay_eur, entry_education, sector, growth_pct, region`

**Key differences from US version:**

- Salaries in EUR (Bruttojahresgehalt), not USD
- ISCO codes instead of SOC codes
- Growth projections may be less granular than BLS (AMS provides general outlook categories)

### Phase 3: Occupation Descriptions

Build rich text descriptions for each occupation (input for AI scoring).

**Sources (layered, best-to-worst):**

1. **AMS Berufslexikon** (berufslexikon.at) -- ~1,800 Austrian job profiles with duties, requirements, salary ranges, outlook. Closest equivalent to BLS OOH. Scrape with Playwright/BeautifulSoup if no bulk download available.
2. **ESCO** (EU skills/occupations framework) -- maps to ISCO, has detailed skills and competences per occupation. Available as bulk download.
3. **ILO ISCO-08** standard texts -- free PDF/CSV downloads with task descriptions per occupation group.

**Output:** `pages/<slug>.md` -- one Markdown file per occupation

### Phase 4: Adapt the Pipeline

Rewrite the scraping/parsing scripts for Austrian data sources.

| Original Script        | Austrian Adaptation                                                                      |
| ---------------------- | ---------------------------------------------------------------------------------------- |
| `parse_occupations.py` | Parse Statistik Austria ISCO list or AMS Berufslexikon index to build `occupations.json` |
| `scrape.py`            | Download AMS Berufslexikon pages (or skip if using ODS/CSV downloads from STATcube)      |
| `parse_detail.py`      | Parse AMS HTML structure (different tags/layout than BLS)                                |
| `make_csv.py`          | Extract Austrian fields from STATcube CSVs / ODS files into `occupations.csv`            |
| `process.py`           | Same role, just wires up new parser                                                      |

**Approach:** Prefer direct downloads (STATcube CSV, Statistik Austria ODS) over scraping where possible. Only scrape AMS Berufslexikon for the job descriptions.

### Phase 5: AI Exposure Scoring

Adapt `score.py` for Austrian occupations.

**Changes:**

- Remove US-centric BLS references from the system prompt
- Keep the 0-10 scoring rubric and calibration logic (it's occupation-generic)
- LLM handles German text fine (Gemini Flash, GPT-4o, etc.)
- Send `pages/<slug>.md` descriptions (same as US version)
- Consider supplementing with ESCO skills data for richer context

**Output:** `scores.json` -- same format as US version

**Note:** AI scores are subjective and model-dependent. Document which model + prompt version was used. Plan to re-run annually with updated data.

### Phase 6: Build Site + Visualization

Adapt `build_site_data.py` and `site/index.html`.

**Changes:**

- EUR instead of USD for salary display
- ISCO categories instead of BLS categories for treemap grouping
- Austrian occupation titles (German)
- Update labels, tooltips, and page title
- Link to Statistik Austria / AMS as source attribution

**Output:** `site/data.json` + updated `site/index.html`, hosted on GitHub Pages

### Phase 7: Regional Filtering (Optional)

Add province-level breakdowns.

**Source:** STATcube allows filtering by Bundesland (Vienna, Styria, etc.) or Bezirk (district).

**Approach:** Either pre-compute separate `data.json` per region, or add a dropdown filter to the frontend that filters the single dataset by region column.

---

## Data Source Summary

| Source            | URL               | What We Get                                                 | Format           |
| ----------------- | ----------------- | ----------------------------------------------------------- | ---------------- |
| Statistik Austria | statistik.at      | Employment by ISCO, wages, education, growth                | ODS/CSV download |
| STATcube          | statcube.at       | Microcensus Labour Force Survey, regional breakdowns        | CSV queries      |
| AMS Berufslexikon | berufslexikon.at  | ~1,800 occupation descriptions, requirements, salary ranges | HTML (scrape)    |
| ESCO              | esco.ec.europa.eu | EU occupation/skills framework mapped to ISCO               | Bulk download    |
| ILO ISCO-08       | ilo.org           | Standard occupation classification with task descriptions   | PDF/CSV          |
| Census 2021       | statistik.at      | Education x occupation cross-tabs by region                 | ODS/PDF          |

## Setup

```bash
uv sync
# Playwright only needed if httpx scraping fails on some pages
uv run playwright install chromium
```

Copy `.env.example` to `.env` and add your OpenRouter API key:

```
OPENROUTER_API_KEY=your_key_here
```

## Pipeline (run in order)

```bash
# 1. Fetch occupation list from AMS Berufslexikon JSON API (~1,700 occupations)
uv run python parse_occupations.py
# → occupations.json

# 2. Scrape AMS detail pages (httpx, ~1,700 pages, ~15 min with 0.5s delay)
uv run python scrape.py
# → html/<slug>.html  (gitignored — large, reproducible)

# 3. Convert HTML → Markdown
uv run python process.py
# → pages/<slug>.md  (gitignored — reproducible)

# 4. Extract structured stats into CSV
uv run python make_csv.py
# → occupations.csv

# 5. Score AI exposure via LLM (OpenRouter API, ~1,700 calls, ~€2-5)
uv run python score.py
# → scores.json  (cached incrementally — resume-safe if interrupted)

# 6. Build site data
uv run python build_site_data.py
# → site/data.json

# 7. Serve locally
cd site && python -m http.server 8000
```

## Docker deployment (csb1 / zukunftschance.ai.barta.cm)

```bash
# Build and run locally (hsb1) first
docker compose up -d --build

# Site available at http://localhost:8081
# Traefik/nginx reverse proxy handles TLS for the public domain
```

The container serves the static `site/` folder via nginx. `site/data.json` is
volume-mounted so data can be updated without rebuilding the image.
uv sync
uv run playwright install chromium

```

Requires an OpenRouter API key in `.env`:

```

OPENROUTER_API_KEY=your_key_here

````

## Usage

```bash
# TODO: Pipeline commands will be updated as scripts are adapted

# Score AI exposure (uses OpenRouter API)
uv run python score.py

# Build website data
uv run python build_site_data.py

# Serve the site locally
cd site && python -m http.server 8000
````
