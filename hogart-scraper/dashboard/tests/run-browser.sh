#!/bin/bash
set -euo pipefail
cd /home/kocher.av/hogart-scraper
source_dir=${DASHBOARD_SOURCE:-/home/kocher.av/hogart-scraper/dashboard}
scratch=$(mktemp -d /tmp/deal-dashboard-test.XXXXXX)
DASHBOARD_DB="$scratch/test.sqlite3" DASHBOARD_PORT=8097 DASHBOARD_ORIGIN=http://127.0.0.1:8097 python3 "$source_dir/server.py" > "$scratch/server.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; rm -f /tmp/deal-dashboard-test-auth.json; rm -rf "$scratch"' EXIT
python3 "$source_dir/tests/make_auth.py"
for attempt in {1..30}; do
 if curl -fsS http://127.0.0.1:8097/deal-dashboard/health >/dev/null 2>&1; then break; fi
 sleep 0.2
done
export NODE_PATH=/home/kocher.av/hogart-scraper/node_modules
node "$source_dir/tests/browser.cjs"
node "$source_dir/tests/workspace-browser.cjs"

# Give auth-focused scenarios a fresh rate-limit window in the isolated server.
kill "$server_pid"
wait "$server_pid" 2>/dev/null || true
DASHBOARD_DB="$scratch/test.sqlite3" DASHBOARD_PORT=8097 DASHBOARD_ORIGIN=http://127.0.0.1:8097 python3 "$source_dir/server.py" >> "$scratch/server.log" 2>&1 &
server_pid=$!
for attempt in {1..30}; do
 if curl -fsS http://127.0.0.1:8097/deal-dashboard/health >/dev/null 2>&1; then break; fi
 sleep 0.2
done
python3 "$source_dir/tests/make_auth.py"
node "$source_dir/tests/reopen-browser.cjs"
