#!/usr/bin/env bash
set -u
python scripts/fetch_data.py || echo "fetch_data failed"
python scripts/supplement_results_from_espn.py || true
python scripts/fetch_understat_xg.py || echo "understat failed"
echo "===== R5 referee"; python research/r5_referee.py || echo "r5 failed"
echo "===== R5 appointments probe"
curl -sS -m 30 -H "Origin: https://www.premierleague.com" "https://footballapi.pulselive.com/football/fixtures?comps=1&page=0&pageSize=3&sort=asc&statuses=U&altIds=true" | head -c 1500; echo
curl -sS -m 30 "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v2/matches?competition=8&season=2026&pageSize=3" | head -c 1500; echo
echo "===== R1 out of sample"; python scripts/run_out_of_sample.py || echo "r1 failed"
for f in data/outputs/out_of_sample_*.md; do echo "----- $f"; cat "$f"; done
