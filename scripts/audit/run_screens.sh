#!/bin/sh
# Screen-size audit in the Playwright Docker image.
# Usage: scripts/audit/run_screens.sh [WEB_URL]   (default http://host.docker.internal:5173)
# Output: audit-output/screens/*.png, report.json, summary.txt. Optional env: PAGES="#/overview,#/holdings", OUT=dir
set -e
cd "$(dirname "$0")/../.."
docker run --rm --ipc=host -v "$PWD":/work -w /work \
  -e WEB_URL="${1:-http://host.docker.internal:5173}" -e OUT="${OUT:-audit-output/screens}" -e PAGES \
  mcr.microsoft.com/playwright:v1.48.2-noble \
  sh -c 'mkdir -p /pw && cd /pw && npm init -y >/dev/null && npm i --no-audit --no-fund playwright@1.48.2 >/dev/null && cp /work/scripts/audit/screens.mjs . && cd /work && node /pw/screens.mjs'
