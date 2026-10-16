#!/usr/bin/env bash
# Smoke-test the deployed ELC-compatible API.
# Usage:  bash test_elc_api.sh
# Optional: BASE=https://your-service.onrender.com/api_v1 bash test_elc_api.sh

set -euo pipefail

BASE="${BASE:-https://elc-api-i83q.onrender.com/api_v1}"

echo "Testing ELC API at: $BASE"
echo

echo "=== index ==="
curl -sS --max-time 120 "$BASE/" | python3 -m json.tool

echo
echo "=== occurrences (canis dirus, limit 3) ==="
curl -sS --max-time 120 "$BASE/occ?taxon=canis+dirus&limit=3&ageunits=ma" | python3 -m json.tool

echo
echo "=== taxonomy ==="
curl -sS --max-time 120 "$BASE/tax?taxon=canis+dirus" | python3 -m json.tool

echo
echo "=== timebound (pleistocene) ==="
curl -sS --max-time 120 "$BASE/misc/timebound?agerange=pleistocene&ageunits=ma" | python3 -m json.tool

echo
echo "OK — smoke test finished."
