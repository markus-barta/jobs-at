{ pkgs, ... }:

{
  # Load .env automatically (OPENROUTER_API_KEY etc.)
  dotenv.enable = true;

  languages.python = {
    enable = true;
    version = "3.13";
    uv = {
      enable = true;
      sync.enable = true;   # runs `uv sync` on devenv activation
    };
  };

  packages = with pkgs; [
    uv
    httpie   # handy for quick API testing
    jq
  ];

  scripts = {
    # Full pipeline in one go
    pipeline.exec = ''
      set -e
      echo "==> 1/6 parse_occupations"
      uv run python parse_occupations.py
      echo "==> 2/6 scrape"
      uv run python scrape.py
      echo "==> 3/6 process"
      uv run python process.py
      echo "==> 4/6 make_csv"
      uv run python make_csv.py
      echo "==> 5/6 score  (LLM calls — takes a while)"
      uv run python score.py
      echo "==> 6/6 build_site_data"
      uv run python build_site_data.py
      echo "Done! site/data.json is ready."
    '';

    # Individual steps
    scrape.exec    = "uv run python scrape.py \"$@\"";
    process.exec   = "uv run python process.py \"$@\"";
    make-csv.exec  = "uv run python make_csv.py \"$@\"";
    score.exec     = "uv run python score.py \"$@\"";
    build.exec     = "uv run python build_site_data.py";

    # Deploy: commit data.json + push + pull on csb1
    deploy.exec = ''
      set -e
      git add site/data.json occupations.csv scores.json occupations.json
      git commit -m "update Austrian job data $(date +%Y-%m-%d)"
      git push
      echo "Waiting for GitHub Actions to build image..."
      gh run watch --exit-status
      echo "Deploying to csb1..."
      ssh mba@cs1.barta.cm -p 2222 "cd ~/docker && docker compose pull jobs-at && docker compose up -d jobs-at"
      echo "Live at https://zukunftschance.ai.barta.cm"
    '';

    # Serve site locally
    serve.exec = "cd site && python -m http.server 8000";
  };

  enterShell = ''
    echo ""
    echo "jobs-at dev environment"
    echo "  pipeline   — run full data pipeline (scrape → score → build)"
    echo "  scrape     — fetch AMS Berufslexikon pages"
    echo "  process    — convert HTML → Markdown"
    echo "  make-csv   — extract salary/outlook stats"
    echo "  score      — AI exposure scoring via OpenRouter"
    echo "  build      — build site/data.json"
    echo "  deploy     — commit + push + deploy to csb1"
    echo "  serve      — serve site locally at :8000"
    echo ""
    if [ -z "$OPENROUTER_API_KEY" ]; then
      echo "  ⚠  OPENROUTER_API_KEY not set — add it to .env"
    else
      echo "  ✓  OPENROUTER_API_KEY loaded"
    fi
    echo ""
  '';
}
