# Multifamily Pulse (standalone)
Static dashboard (index.html + data.json). Hosted on GitHub Pages; `.github/workflows/refresh.yml` runs `scripts/build.py` hourly (cron :07), commits data.json + usage/usage.jsonl, and deploys Pages.
- Edit sources, keywords, and social lists in `config.json`.
- Usage log: `usage/usage.jsonl` (one line per run: fetch count, failures, bytes, paid_api_calls=0, cost_usd=0).
- No secrets in the repo. Optional scratchpad sync uses a fine-grained token the user enters in the browser; it stays in localStorage and writes notes.md to a `notes` branch.
- Not affiliated with any employer system; public sources only.
- Market numbers: Census CPS/HVS (annual state rental vacancy), Census BPS (monthly state permits), Zillow ZORI (metro rents). No FRED (CSV graph endpoint is blocked from Actions).
- Account Watch (tab next to Competitors): accounts live in `config.json` → `accounts` (name, url, news_query, optional `match` = phrase a Google News headline must contain). `scripts/accounts.py` checks each homepage, auto-discovers an RSS feed or news/press/blog page, and runs one Google News RSS query per account. Polite: 4 concurrent requests max, 15s timeout, identifying User-Agent, Google News calls serialized with a delay, and a full pass only every 6h (or when the account config changes). Items are classified by keyword (Acquisition, Hire/Leadership, Merger, Development, Other). Per-site status (reachable / no news page / unreachable / no url) is stored in `data.json` → `account_watch`.
