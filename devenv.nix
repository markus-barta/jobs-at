{ pkgs, ... }:

{
  # Load .env automatically (OPENROUTER_API_KEY etc.)
  dotenv.enable = true;

  # uv manages Python itself — no need for devenv's python version pin
  # (which would require the external nixpkgs-python input)
  languages.python = {
    enable = true;
    uv = {
      enable = true;
      sync.enable = true;   # runs `uv sync` on devenv activation
    };
  };

  packages = with pkgs; [
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
    scrape.exec         = "uv run python scrape.py \"$@\"";
    process.exec        = "uv run python process.py \"$@\"";
    make-csv.exec       = "uv run python make_csv.py \"$@\"";
    score.exec          = "uv run python score.py \"$@\"";
    score-headcount.exec= "uv run python score_headcount.py \"$@\"";
    normalize.exec      = "uv run python score_headcount.py --normalize";
    build.exec          = "uv run python build_site_data.py";

    # Deploy: commit data files, push, wait for GHA image build, pull on server
    # Reads DEPLOY_SSH target from .env (e.g. DEPLOY_SSH="user@host -p 2222")
    # and DEPLOY_COMPOSE_DIR (e.g. ~/docker)
    deploy.exec = ''
      set -e
      git add site/data.json occupations.csv scores.json headcounts.json occupations.json
      git commit -m "update Austrian job data $(date +%Y-%m-%d)"
      git push
      echo "Waiting for GitHub Actions to build image..."
      # Wait up to 5s for a run to appear, then watch it; if already done, check latest
      sleep 5
      RUN_ID=$(gh run list --repo markus-barta/jobs-at --workflow docker.yml --limit 1 --json databaseId,status --jq '.[0] | select(.status != "completed") | .databaseId' 2>/dev/null || true)
      if [ -n "$RUN_ID" ]; then
        gh run watch "$RUN_ID" --exit-status
      else
        # Run already completed — verify it succeeded
        CONCLUSION=$(gh run list --repo markus-barta/jobs-at --workflow docker.yml --limit 1 --json conclusion --jq '.[0].conclusion' 2>/dev/null || echo "unknown")
        if [ "$CONCLUSION" = "success" ]; then
          echo "Image already built successfully."
        else
          echo "Last GHA run conclusion: $CONCLUSION — check https://github.com/markus-barta/jobs-at/actions"
          exit 1
        fi
      fi
      if [ -n "$DEPLOY_SSH" ]; then
        echo "Deploying to server..."
        ssh $DEPLOY_SSH "cd ''${DEPLOY_COMPOSE_DIR:-~/docker} && docker compose pull jobs-at && docker compose up -d jobs-at"
        echo "Done."
      else
        echo "DEPLOY_SSH not set in .env — skipping remote deploy."
        echo "Pull manually: docker compose pull jobs-at && docker compose up -d jobs-at"
      fi
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
    echo "  score            — AI exposure scoring via OpenRouter"
    echo "  score-headcount  — ISCO code + headcount estimation via LLM"
    echo "  normalize        — re-run STATcube normalization on headcounts.json"
    echo "  build            — build site/data.json"
    echo "  deploy           — commit + push + deploy to server"
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
