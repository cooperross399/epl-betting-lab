#!/usr/bin/env bash
set -u
git fetch -q origin odds-history
python scripts/fetch_data.py >/dev/null || echo "fetch_data failed"
python scripts/fetch_understat_xg.py >/dev/null || echo "understat failed"
echo "===== R1b"; python research/r1b_derived_on_xg.py 2>&1 | grep -v Warning || echo "r1b failed"
echo "===== officials probe"
H='Origin: https://www.premierleague.com'
for id in 129006; do
  curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures/$id" | python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.keys())); print(json.dumps(d.get('matchOfficials'))[:800])"
done
curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures?comps=1&compSeasons=841&page=0&pageSize=2&sort=desc&statuses=C" | python -c "import json,sys; d=json.load(sys.stdin); f=d['content'][0]; print(f['id'], sorted(f.keys())); print(json.dumps(f.get('matchOfficials'))[:600])"
