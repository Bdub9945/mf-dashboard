# Multifamily Pulse (standalone)
Static dashboard (index.html + data.json). Hosted on GitHub Pages; `.github/workflows/refresh.yml` runs `scripts/build.py` hourly (cron :07), commits data.json + usage/usage.jsonl, and deploys Pages.
- Edit sources, keywords, and social lists in `config.json`.
- Usage log: `usage/usage.jsonl` (one line per run: fetch count, failures, bytes, paid_api_calls=0, cost_usd=0).
- No secrets in the repo. Optional scratchpad sync uses a fine-grained token the user enters in the browser; it stays in localStorage and writes notes.md to a `notes` branch.
- Not affiliated with any employer system; public sources only.
