#!/usr/bin/env bash
# Run after: gh auth login   (choose GitHub.com > HTTPS > "Login with a web browser" device code; scopes repo,workflow)
set -e; cd "$(dirname "$0")"
gh repo create mf-dashboard --public --source=. --push
U=$(gh api user -q .login)
gh api -X POST repos/$U/mf-dashboard/pages -f build_type=workflow >/dev/null || true
gh workflow run refresh.yml; sleep 90
echo "URL: https://$U.github.io/mf-dashboard/"; curl -s https://$U.github.io/mf-dashboard/data.json | head -c 300
