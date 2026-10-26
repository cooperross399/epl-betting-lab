#!/usr/bin/env bash
set -u
H='Origin: https://www.premierleague.com'
echo "===== football-data fixtures.csv referee column"
curl -sS -m 30 https://www.football-data.co.uk/fixtures.csv | python -c "
import csv,sys,io
rows=list(csv.DictReader(io.StringIO(sys.stdin.read().lstrip('﻿'))))
print(list(rows[0].keys())[:14] if rows else 'empty')
for r in rows:
    if r.get('Div')=='E0': print(r.get('Date'), r.get('HomeTeam'), r.get('AwayTeam'), repr(r.get('Referee')))
"
echo "===== pulselive comp seasons"
curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/competitions/1/compseasons?page=0&pageSize=3" | python -c "import json,sys; d=json.load(sys.stdin); print([(c['id'],c['label']) for c in d['content']])"
CS=$(curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/competitions/1/compseasons?page=0&pageSize=1" | python -c "import json,sys; print(int(json.load(sys.stdin)['content'][0]['id']))")
echo "current compSeason $CS"
for status in U C; do
  echo "--- status $status"
  curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures?comps=1&compSeasons=$CS&page=0&pageSize=12&sort=$([ $status = U ] && echo asc || echo desc)&statuses=$status" | python -c "
import json,sys
d=json.load(sys.stdin)
for f in d['content']:
    t=[x['team']['name'] for x in f['teams']]
    print(int(f['id']), f.get('kickoff',{}).get('label'), t, json.dumps(f.get('matchOfficials'))[:300])
"
done
echo "--- single fixture, last completed"
ID=$(curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures?comps=1&compSeasons=$CS&page=0&pageSize=1&sort=desc&statuses=C" | python -c "import json,sys; print(int(json.load(sys.stdin)['content'][0]['id']))")
curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures/$ID" | python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.keys())); print(json.dumps(d.get('matchOfficials'))[:800])"
echo "--- single fixture, next upcoming"
ID=$(curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures?comps=1&compSeasons=$CS&page=0&pageSize=1&sort=asc&statuses=U" | python -c "import json,sys; print(int(json.load(sys.stdin)['content'][0]['id']))")
curl -sS -m 30 -H "$H" "https://footballapi.pulselive.com/football/fixtures/$ID" | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('matchOfficials'))[:800])"
