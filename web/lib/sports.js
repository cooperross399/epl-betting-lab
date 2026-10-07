// One adapter per sport. Each turns that lab's board.json / results.json into the
// view model the shared Board / Results / Graphic pages render. All sport-specific
// vocabulary lives here; the pages know nothing about hockey, football or basketball.
import * as F from "./format.js";

const dash = "—";
const num = (n, d = 1) => (typeof n === "number" ? n.toFixed(d) : dash);
const odds = (n) => (typeof n === "number" ? F.fmtOdds(n) : dash);
const pct = (p) => (typeof p === "number" ? F.pct(p) : dash);
const w = (p) => `${Math.round((p || 0) * 100)}%`;
const hoursOld = (iso) => (iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : Infinity);

// `sample` / `sampleResults` are the OFF-DOMAIN fallback: what the pages fetch
// when site.json is absent, and what the Leans / Empty preview scenarios are
// derived from. They must point at files that exist IN THAT LAB'S REPO. EPL and
// CBB keep theirs under data/sample/; NHL commits its board at the live path.
// Shipped pointing at data/epl/ and data/cbb/, which exist in neither repo, so
// every offline load and both preview scenarios fell through to a 404.
export const SPORTS = {
  nhl: { key: "nhl", name: "NHL", longName: "NHL Projections", host: "https://nhl.maverickhightower.com/", sample: "./data/board.json", sampleResults: "./data/results.json", scoreWord: "goals", timeWord: "Puck drop", staleAfterHours: 30 },
  epl: { key: "epl", name: "EPL", longName: "EPL Projections", host: "https://epl.maverickhightower.com/", sample: "./data/sample/board.json", sampleResults: "./data/sample/results.json", scoreWord: "goals", timeWord: "Kick-off", staleAfterHours: 30 },
  cbb: { key: "cbb", name: "CBB", longName: "CBB Projections", host: "https://cbb.maverickhightower.com/", sample: "./data/sample/board.json", sampleResults: "./data/sample/results.json", scoreWord: "points", timeWord: "Tip", staleAfterHours: 30 },
};
export const ORDER = ["nhl", "epl", "cbb"];
export const SITE = { name: "Maverick Hightower", handle: "@mavhightower", hub: "https://maverickhightower.com/", about: "https://maverickhightower.com/about.html", image: "https://maverickhightower.com/share.png" };

// Which sport this deployment is: site.json on the same host, else the subdomain, else the fallback.
export async function detectSport(fallback) {
  try {
    const r = await fetch("./site.json", { cache: "no-store" });
    if (r.ok) { const j = await r.json(); if (SPORTS[j.sport]) return { sport: j.sport, deployed: true }; }
  } catch (_) { /* not deployed */ }
  const m = /^(nhl|epl|cbb)\./.exec(location.hostname);
  if (m) return { sport: m[1], deployed: true };
  return { sport: SPORTS[fallback] ? fallback : "nhl", deployed: false };
}

export const HOW_TO_READ = [
  ["Projected", "The model's expected score before the game. Not a prediction of the exact final."],
  ["Open / Current", "The market price when the board was first built and at the latest refresh. The small line under a cell shows how it moved across refreshes."],
  ["Fair", "The price the model thinks is break-even for that side. A market price better than fair is where an edge would live."],
  ["Edge", "Model probability minus the probability implied by the market price, after calibration. Small edges are noise; the bars below the picks exist because of that."],
  ["Best bet", "A selection that cleared the card's bars: minimum edge, minimum price, a market the lab has allowlisted. It carries a tier and a stake in units."],
  ["Lean", "The model's side, recorded so it can be judged later, but not staked. Below the bar or in a market that is not yet allowlisted."],
  ["Pass", "The best available market on that game and why it was not taken."],
  ["Record", "Every number in the strip is settled from what was published before the game, never recomputed afterwards. Intervals are 95% confidence; 'no demonstrated edge' means zero sits inside the interval."],
  ["Props", "Player markets, priced the way team markets are: the model's projection for the stat, its probability for the side, the fair price and the edge. The same Best bet / Lean / Pass rules apply, and each market carries a note on what testing has shown so far."],
  ["Live", "Scores, periods and box-score counts come from ESPN while games are on. A pick's live status compares the current score with what the board published; it is not a settlement. Results settle the next morning from the official finals."],
];

const pickView = (p, unit, opts = {}) => {
  if (!p || p.kind === "pass") return { kind: "none", heading: "Model pick", label: opts.noneLabel || "No play", sub: "", extra: "" };
  const price = opts.priceFmt ? opts.priceFmt(p.price) : odds(p.price);
  const edge = typeof p.edgePct === "number" ? `${F.fmtSigned(p.edgePct)}%` : dash;
  const kind = p.kind || "bet";
  return {
    kind, heading: kind === "bet" ? "Best bet" : kind === "lean" ? "Lean" : kind === "pass" ? "Model pick" : "Model pick",
    label: p.label, price, edge,
    sub: `${p.market} · ${price}${p.book ? ` at ${p.book}` : ""}${typeof p.modelProb === "number" ? ` · model ${pct(p.modelProb)}` : ""} · edge ${edge}`,
    extra: kind === "bet" ? [p.tier ? `Tier ${p.tier}` : null, typeof p.units === "number" ? `${p.units} unit${p.units === 1 ? "" : "s"}` : null].filter(Boolean).join(" · ") : kind === "lean" ? "Recorded, not staked" : "",
  };
};

const spark = (series) => {
  if (!Array.isArray(series) || series.length < 2) return null;
  const v = series.map((s) => (typeof s === "number" ? s : s.v)).filter((x) => typeof x === "number");
  if (v.length < 2) return null;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1, W = 72, H = 18;
  const points = v.map((y, i) => `${((i / (v.length - 1)) * W).toFixed(1)},${(H - 2 - ((y - min) / span) * (H - 4)).toFixed(1)}`).join(" ");
  const d = v[v.length - 1] - v[0];
  return { points, from: v[0], to: v[v.length - 1], note: d === 0 ? "flat" : `${d > 0 ? "▲" : "▼"} ${Math.abs(d) % 1 === 0 ? Math.abs(d) : Math.abs(d).toFixed(1)} over ${v.length} refreshes` };
};
const cell = (title, rows, series, note) => ({ title, rows: rows.map(([label, value, bold]) => ({ label, value, bold: !!bold })), spark: spark(series), note: note || "" });

const common = (data, sport) => {
  const age = hoursOld(data.generatedAt);
  return {
    sport, season: data.season || "", updated: data.generatedAt ? F.fmtUpdated(data.generatedAt) : dash, tz: F.tzName(),
    stale: age > sport.staleAfterHours, staleLabel: age === Infinity ? "No build time" : `Feed stale · ${Math.round(age)} h old`,
    notice: data.notice || "", archived: data.__archived || null,
  };
};

const sideBase = (T, s, role) => {
  const t = T[s.abbr] || {};
  return { abbr: s.abbr, name: t.short || t.name || s.abbr, record: s.record || "", color: t.color || "#14151a", fg: t.fg || "#fff", role, win: typeof s.winProb === "number" ? `${F.pct(s.winProb)} win` : "", flag: s.b2b ? "B2B" : "", note: s.goalie ? `${s.goalie.name}${s.goalie.status === "confirmed" ? " ✓" : " (proj.)"}` : "" };
};

// ---------- NHL ----------
function nhlBoard(data) {
  const sport = SPORTS.nhl, T = data.teams || {}, LH = data.lineHistory || {}, unit = data.unitDollars ?? 25, pre = data.phase === "preseason";
  let bets = 0, leans = 0;
  const byDay = new Map();
  for (const g of data.games || []) {
    const key = F.localDayKey(g.startUtc);
    if (!byDay.has(key)) byDay.set(key, { label: F.fmtDayLong(g.startUtc), games: [] });
    const modelled = typeof g.home.projGoals === "number";
    const h = LH[g.id] || {}, a = g.away.abbr, hm = g.home.abbr;
    const ml = g.moneyline || {}, pl = g.puckLine || {}, tot = g.total || {}, reg = g.regulation || {};
    const cells = modelled ? [
      cell("Moneyline", [["Open", ml.open ? F.favLine(ml.open, a, hm) : dash], ["Current", ml.current ? F.favLine(ml.current, a, hm) : dash], ["Fair", ml.fair ? F.favLine(ml.fair, a, hm) : dash, true]], h.ml_home),
      cell("Puck line", [["Line", pl.favorite ? `${pl.favorite} ${F.fmtLine(pl.line)}` : dash], ["Price", odds(pl.price)], ["Cover", pct(pl.coverProb), true]], h.pl_price),
      cell("Total", [["Open / Current", `${num(tot.open)} / ${num(tot.current)}`], ["Over / Under", `${odds(tot.overPrice)} / ${odds(tot.underPrice)}`], ["Proj", `${num(tot.proj)} · O ${pct(tot.overProb)}`, true]], h.total),
      cell("Regulation", [[a, `${pct(reg.away)} · ${odds(reg.prices && reg.prices.away)}`], ["Draw", `${pct(reg.draw)} · ${odds(reg.prices && reg.prices.draw)}`], [hm, `${pct(reg.home)} · ${odds(reg.prices && reg.prices.home)}`]]),
    ] : [];
    // The builder names each pick's kind; a pick frozen before it did reads
    // as a bet. This counted every pick as a best bet, and the builder set
    // no kind, so a lean was headed "Best bet" and counted in the strip.
    // Pinned by tests/test_a_lean_is_never_published_as_a_best_bet.py.
    const p = g.pick ? { kind: "bet", ...g.pick } : null;
    if (p && p.kind === "bet" && !g.started) bets++;
    if (p && p.kind === "lean" && !g.started) leans++;
    byDay.get(key).games.push({
      id: g.id, time: F.fmtTime(g.startUtc), tv: g.tv || "", venue: g.venue || "", city: g.city || "", started: !!g.started, opacity: g.started ? "0.55" : "1",
      sides: [{ ...sideBase(T, g.away, "Away"), proj: num(g.away.projGoals) }, { ...sideBase(T, g.home, "Home"), proj: num(g.home.projGoals) }],
      bar: modelled ? [{ width: w(g.away.winProb), color: T[a] ? T[a].color : "#14151a" }] : [], barTail: modelled ? (T[hm] ? T[hm].color : "#6b6e7a") : "transparent", barNote: "",
      // Which gate stopped it depends on the policy, so the board tells the
      // page rather than the page assuming. With nothing allowlisted,
      // eligibility is decided before edge and the card never reaches the
      // bar, so naming the bar would report a model judgement where a
      // permission gate is what happened. With markets allowlisted the bar is
      // exactly what stopped it, and naming the allowlist would be the same
      // error pointing the other way. Reverted by four drops now, the last
      // one by hard-coding the bar arm here. Pinned by
      // tests/test_site_publishes_no_forward_return.py.
      //
      // Neither gate applies to a game the board holds no price for
      // (`priced: false`): nothing was assessed, so naming the bar or the
      // allowlist reports a judgement nobody made. Until 2026-09-29 (PR
      // #275) Publish Site restored no staged prices, so without this arm
      // every regular-season game read "No market clears the edge bar"
      // while the card held a best bet; a run whose prices do not arrive
      // still lands here.
      // Pinned by tests/test_site_never_calls_an_unpriced_game_a_pass.py.
      //
      // Nor does either apply to a game that is not a regular-season game,
      // on a night that also holds one: build_site_json publishes it as
      // schedule only (no projection, no price), and "Not priced" would say
      // a price failed to arrive for a game nobody looked for one on.
      cells, pick: pickView(p, unit, { noneLabel: pre || g.gameType === 1 ? "Exhibition · model abstains"
        : typeof g.gameType === "number" && g.gameType !== 2 ? "Not a regular-season game · model abstains"
        : g.priced === false ? "Not priced · no market price reached this board"
        : (data.allowlistedMarkets || []).length ? "No market clears the edge bar"
        : "No market is allowlisted for selection" }),
      score: modelled ? `${num(g.away.projGoals)} – ${num(g.home.projGoals)}` : dash,
    });
  }
  const r = data.record || {}, season = r.season || {};
  // The season's record, summed by build_site_json from every frozen board
  // it settled (season_record). Shown only when the board carries one: an
  // absent record is a dash that says why, never 0–0, because 0–0 is what
  // this strip printed for weeks while nothing tallied anything. Pinned by
  // tests/test_site_invents_no_season_record.py.
  //
  // The forward ledger is not on this strip (owner's call, 2026-10-05). Its
  // size stays in board.json; its return stays sealed until 2027-04-25
  // (docs/when_this_ends.md) and must never be added here. Pinned by
  // tests/test_site_publishes_no_forward_return.py.
  const kept = (rec) => rec && typeof rec === "object";
  const untallied = "No night settled yet · each night is on Results";
  const nights = typeof season.nights === "number" ? `${season.nights} night${season.nights === 1 ? "" : "s"}` : "";
  const missed = season.missingNights ? ` · ${season.missingNights} not yet settled` : "";
  const strip = [
    { label: "Best bets · season", value: kept(r.picks) ? F.recStr(r.picks) : dash, sub: kept(r.picks) ? `${F.winRate(r.picks.w || 0, r.picks.l || 0)} · ${nights}${missed}` : untallied, fine: "" },
    { label: "Straight up · season", value: kept(r.straightUp) ? F.recStr(r.straightUp) : dash, sub: kept(r.straightUp) ? `${F.winRate(r.straightUp.w || 0, r.straightUp.l || 0)} of games` : untallied, fine: "" },
    { label: "Totals · season", value: kept(r.totals) ? F.recStr(r.totals) : dash, sub: kept(r.totals) ? "model side of the line" : untallied, fine: "" },
    { label: "Leans · season", value: kept(r.leans) ? F.recStr(r.leans) : dash, sub: kept(r.leans) ? "recorded, not staked" : untallied, fine: "" },
  ];
  return { ...common(data, sport), kicker: `${data.season} NHL · ${data.boardDate ? F.fmtDateOnly(data.boardDate) : ""}`, title: ["Tonight's", "Board."],
    blurb: "Projected scores, win probabilities and market prices for tonight's slate.", strip, groups: [...byDay.values()].map((d) => ({ ...d, countLabel: `${d.games.length} game${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} games · ${bets} best bets · ${leans} leans`, unit };
}

// A settled game whose board carried no pick. The builder used to hand such
// a game the pick {market: "—", label: "No play", price: 0, result: "push"},
// and resultPick rendered it under "Model pick" as "No play · — · −0 ·
// Push". Until 2026-09-29 (PR #275) Publish Site restored no staged
// prices, so every game on an unpriced board became a model pass graded as
// a push, at a price of −0 that nobody quoted: 5 of 5 on the real
// 2026-09-29 slate, and still the fate of any run whose prices do not
// arrive. The
// row now carries `priced`. A pass is read only off `priced: true`; any
// other row is not a judgement the model made. Neither kind is graded,
// and neither shows a price. Pinned by
// tests/test_results_never_grade_an_unpriced_game.py.
function nhlNoPick(g) {
  const [label, market] = g.priced === true
    ? ["No play", "priced, nothing selected · not graded"]
    : ["Not priced", "no market price reached this board · not graded"];
  return { hasPick: true, pick: { label, market, result: dash, color: "#6b6e7a", bg: "#f4f2ee" } };
}

// A settled lean says so. The builder keeps it out of the Model picks
// record (it was recorded, not staked), and the row it is judged on must
// not read like a best bet's. Pinned by
// tests/test_a_lean_is_never_published_as_a_best_bet.py.
function nhlResultPick(p) {
  const r = resultPick(p);
  return p.kind === "lean" ? { ...r, pick: { ...r.pick, market: `Lean · ${r.pick.market} · not in the record` } } : r;
}

function nhlResults(data) {
  const sport = SPORTS.nhl, T = data.teams || {}, s = data.summary || {};
  const games = (data.games || []).map((g) => {
    const winner = g.away.final > g.home.final ? g.away.abbr : g.home.abbr, suHit = winner === g.projWinner, tot = g.away.final + g.home.final;
    const side = (x) => ({ ...sideBase(T, x), proj: num(x.projGoals), final: x.final, scoreColor: x.abbr === winner ? "#14151a" : "#9a9ca6" });
    // A game whose board carried no total line settles with no `total`.
    // This read g.total.line unguarded, so the morning after an unpriced
    // board -- every game, under Publish Site -- the adapter threw and the
    // Results page rendered nothing. Pinned by
    // tests/test_site_never_calls_an_unpriced_game_a_pass.py.
    const t = g.total;
    return { sides: [side(g.away), side(g.home)], finishLabel: g.finish && g.finish !== "REG" ? ` · ${g.finish}` : "",
      cells: [cell("Straight up", [["Projected", g.projWinner], ["Result", suHit ? "Hit" : "Miss", true]]), cell("Total", t ? [["Line / proj", `${num(t.line)} / ${num(t.proj)}`], ["Landed", `${tot} · ${t.result === "over" ? "Over" : t.result === "under" ? "Under" : "Push"}`, true]] : [["Line / proj", dash], ["Landed", `${tot} · no line`, true]])],
      ...(g.pick ? nhlResultPick(g.pick) : nhlNoPick(g)) };
  });
  return { ...common(data, sport), kicker: `${data.season} NHL · ${data.resultsDate ? F.fmtDateOnly(data.resultsDate) : ""}`, dateShort: data.resultsDate ? F.fmtDateOnly(data.resultsDate) : "",
    strip: [{ label: "Straight up", value: F.recStr(s.straightUp || { w: 0, l: 0 }) }, picksCell(s), { label: "Totals", value: F.recStr(s.totals || { w: 0, l: 0, p: 0 }) },
      // The season's best bets beside the night's, when the file carries a
      // season that has settled at least one night.
      ...(data.seasonRecord && data.seasonRecord.nights && data.seasonRecord.picks ? [{ label: "Best bets · season", value: F.recStr(data.seasonRecord.picks) }] : [])],
    games, count: games.length, isEmpty: games.length === 0, notice: data.notice || "No games were settled for this date.", vsLabel: "Projected score vs final" };
}

// ---------- EPL ----------
const MK = { total_2_5: "Total 2.5", btts: "Both teams to score", double_chance: "Double chance", draw_no_bet: "Draw no bet", corners_1x2: "Corners 1x2", corners_total_9_5: "Corners 9.5", corners_total_10_5: "Corners 10.5", "1x2": "Match result" };
function eplBoard(data) {
  const sport = SPORTS.epl, T = data.teams || {}, LH = data.lineHistory || {}, unit = data.unitDollars ?? 25;
  let bets = 0, leans = 0;
  const byDay = new Map();
  for (const g of data.games || []) {
    const key = F.localDayKey(g.kickoff);
    if (!byDay.has(key)) byDay.set(key, { label: F.fmtDayLong(g.kickoff), games: [] });
    const h = LH[g.id] || {}, fair = (g.result && g.result.fair) || {}, tot = g.total || {}, bt = g.btts || {}, dnb = g.drawNoBet || {};
    const p = g.pick ? { ...g.pick, market: MK[g.pick.market] || g.pick.market } : null;
    if (p && p.kind === "bet" && !g.started) bets++;
    if (p && p.kind === "lean" && !g.started) leans++;
    byDay.get(key).games.push({
      id: g.id, time: F.fmtTime(g.kickoff), tv: g.tv || "", venue: g.venue || "", city: g.city || "", started: !!g.started, opacity: g.started ? "0.55" : "1",
      sides: [{ ...sideBase(T, g.home, "Home"), proj: num(g.home.projGoals) }, { ...sideBase(T, g.away, "Away"), proj: num(g.away.projGoals) }],
      bar: [{ width: w(g.home.winProb), color: T[g.home.abbr] ? T[g.home.abbr].color : "#14151a" }, { width: w(g.drawProb), color: "#c9c7c0" }], barTail: T[g.away.abbr] ? T[g.away.abbr].color : "#6b6e7a", barNote: typeof g.drawProb === "number" ? `Draw ${pct(g.drawProb)}` : "",
      cells: [
        cell("Match result · fair", [["Home", odds(fair.home)], ["Draw", odds(fair.draw)], ["Away", odds(fair.away)]], null, "reference only"),
        cell("Total 2.5", [["Over", odds(tot.over)], ["Under", odds(tot.under)], ["Model over", pct(tot.overProb), true]], h.total_over),
        cell("Both teams to score", [["Yes", odds(bt.yes)], ["No", odds(bt.no)], ["Model yes", pct(bt.yesProb), true]], h.btts_yes),
        cell("Draw no bet", [["Home", odds(dnb.home)], ["Away", odds(dnb.away)], ["Model home", pct(dnb.homeProb), true]], h.dnb_home),
      ],
      pick: pickView(p, unit), score: `${num(g.home.projGoals)} – ${num(g.away.projGoals)}`,
    });
  }
  const r = data.record || {};
  const strip = [
    { label: "Settled selections", value: String(r.settled ?? 0), sub: `${r.won ?? 0} won · ${r.pending ?? 0} pending · ${r.void ?? 0} void`, fine: "" },
    { label: "Profit on turnover", value: typeof r.roiPct === "number" ? `${F.fmtSigned(r.roiPct)}%` : dash, sub: `${typeof r.profitUnits === "number" ? F.fmtSigned(r.profitUnits, 2) : dash} units on ${typeof r.stakedUnits === "number" ? r.stakedUnits.toFixed(2) : dash} staked`, fine: "no demonstrated edge" },
    { label: "Awaiting results feed", value: String(r.awaitingResults ?? 0), sub: "played, not yet settled", fine: "" },
    { label: "Time to an answer", value: `~${(r.betsToAnswer ?? 1500).toLocaleString()}`, sub: "settled bets needed", fine: "" },
  ];
  return { ...common(data, sport), kicker: `${data.season} Premier League · ${data.windowLabel || ""}`, title: ["This week's", "Board."],
    blurb: "Projected goals, outcome probabilities and market prices for this card's fixtures.",
    strip, groups: [...byDay.values()].map((d) => ({ ...d, countLabel: `${d.games.length} fixture${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} fixtures · ${bets} best bets · ${leans} leans`, unit };
}
function eplResults(data) {
  const sport = SPORTS.epl, T = data.teams || {}, s = data.summary || {};
  const games = (data.games || []).map((g) => {
    const out = g.home.final > g.away.final ? "home" : g.home.final < g.away.final ? "away" : "draw", tot = g.home.final + g.away.final, m = g.markets || {};
    const side = (x, role) => ({ ...sideBase(T, x, role), proj: num(x.projGoals), final: x.final, scoreColor: out === "draw" || (out === "home") === (role === "Home") ? "#14151a" : "#9a9ca6" });
    return { sides: [side(g.home, "Home"), side(g.away, "Away")], finishLabel: "",
      cells: [cell("Match result", [["Model favoured", g.projResult === "home" ? "Home" : g.projResult === "away" ? "Away" : "Draw"], ["Result", out === g.projResult ? "Hit" : "Miss", true]]),
        cell("Total 2.5", [["Model", pct(m.total && m.total.overProb)], ["Landed", `${tot} · ${tot > 2.5 ? "Over" : "Under"}`, true]]),
        cell("Both teams to score", [["Model yes", pct(m.btts && m.btts.yesProb)], ["Landed", g.home.final > 0 && g.away.final > 0 ? "Yes" : "No", true]])],
      ...resultPick(g.pick) };
  });
  return { ...common(data, sport), kicker: `${data.season} Premier League · ${data.resultsDate ? F.fmtDateOnly(data.resultsDate) : ""}`, dateShort: data.windowLabel || (data.resultsDate ? F.fmtDateOnly(data.resultsDate) : ""),
    strip: [picksCell(s), { label: "Favoured side", value: F.recStr(s.result || { w: 0, l: 0 }) }, { label: "Total 2.5 leans", value: F.recStr(s.totals || { w: 0, l: 0 }) }],
    games, count: games.length, isEmpty: games.length === 0, notice: data.notice || "No fixtures were settled for this window.", vsLabel: "Projected goals vs final" };
}

// ---------- CBB ----------
function cbbBoard(data) {
  const sport = SPORTS.cbb, T = data.teams || {}, LH = data.lineHistory || {}, unit = data.unitDollars ?? 25;
  const labels = { morning: "Morning card", evening: "Evening card" }, order = ["morning", "evening"];
  let bets = 0, leans = 0;
  const bySlot = new Map();
  for (const g of data.games || []) {
    const k = g.cardSlot || "morning";
    if (!bySlot.has(k)) bySlot.set(k, { label: labels[k] || k, games: [] });
    const h = LH[g.id] || {}, a = g.away.abbr, hm = g.home.abbr, ml = g.moneyline || {}, sp = g.spread || {}, tot = g.total || {};
    const p = g.pick || null;
    if (p && p.kind === "bet" && !g.started) bets++;
    if (p && p.kind === "lean" && !g.started) leans++;
    const spStr = (n) => (typeof n === "number" ? `${hm} ${F.fmtLine(n)}` : dash);
    bySlot.get(k).games.push({
      id: g.id, time: F.fmtTime(g.tip), tv: g.tv || "", venue: g.venue || "", city: g.city || "", started: !!g.started, opacity: g.started ? "0.55" : "1",
      sides: [{ ...sideBase(T, g.away, "Away"), proj: num(g.away.projPts) }, { ...sideBase(T, g.home, g.neutral ? "Home (neutral)" : "Home"), proj: num(g.home.projPts) }],
      bar: typeof g.away.winProb === "number" ? [{ width: w(g.away.winProb), color: T[a] ? T[a].color : "#14151a" }] : [], barTail: typeof g.away.winProb === "number" ? (T[hm] ? T[hm].color : "#6b6e7a") : "transparent", barNote: "",
      cells: [
        cell("Moneyline", [["Open", ml.open ? F.favLine(ml.open, a, hm) : dash], ["Current", ml.current ? F.favLine(ml.current, a, hm) : dash], ["Fair", ml.fair ? F.favLine(ml.fair, a, hm) : dash, true]], h.ml_home),
        cell("Spread", [["Open", spStr(sp.open)], ["Current", `${spStr(sp.current)}${typeof sp.homePrice === "number" ? ` · ${odds(sp.homePrice)}` : ""}`], ["Proj", spStr(sp.proj), true]], h.spread),
        cell("Total", [["Open", num(tot.open)], ["Current", `${num(tot.current)}${typeof tot.overPrice === "number" ? ` · O ${odds(tot.overPrice)}` : ""}`], ["Proj", num(tot.proj), true]], h.total),
      ],
      pick: pickView(p, unit), score: `${num(g.away.projPts)} – ${num(g.home.projPts)}`,
    });
  }
  const r = data.record || {}, ms = r.markets || [];
  const strip = ms.slice(0, 3).map((m) => ({ label: `${m.label} · ROI`, value: `${F.fmtSigned(m.roiPct)}%`, sub: `${m.bets} bets · 95% ${F.fmtSigned(m.ciLowPct)}% to ${F.fmtSigned(m.ciHighPct)}%`, fine: m.verdict || "no demonstrated edge" }));
  while (strip.length < 3) strip.push({ label: "ROI", value: dash, sub: "No settled opinions yet", fine: "" });
  strip.push({ label: "Time to an answer", value: (r.opinionsSoFar ?? 0).toLocaleString(), sub: `of ${(r.opinionsNeeded ?? 10000).toLocaleString()} settled opinions needed`, fine: typeof r.clvPoints === "number" ? `CLV ${F.fmtSigned(r.clvPoints, 2)} pts` : "" });
  return { ...common(data, sport), kicker: `${data.season} Men's College Basketball · ${data.slateDate ? F.fmtDateOnly(data.slateDate) : ""}${data.cardSlot ? ` · ${data.cardSlot} card` : ""}`, title: ["Tonight's", "Board."],
    blurb: "Projected scores, win probabilities and market prices for tonight's carded games.",
    strip, groups: order.filter((k) => bySlot.has(k)).map((k) => bySlot.get(k)).map((d) => ({ ...d, countLabel: `${d.games.length} game${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} games · ${bets} best bets · ${leans} leans`, unit };
}
function cbbResults(data) {
  const sport = SPORTS.cbb, T = data.teams || {}, s = data.summary || {};
  const games = (data.games || []).map((g) => {
    const winner = g.away.final > g.home.final ? g.away.abbr : g.home.abbr, tot = g.away.final + g.home.final, m = g.markets || {}, margin = g.home.final - g.away.final;
    const side = (x, role) => ({ ...sideBase(T, x, role), proj: num(x.projPts), final: x.final, scoreColor: x.abbr === winner ? "#14151a" : "#9a9ca6" });
    const ats = m.spread && typeof m.spread.line === "number" ? (margin + m.spread.line > 0 ? `${g.home.abbr} covers` : margin + m.spread.line < 0 ? `${g.away.abbr} covers` : "Push") : dash;
    return { sides: [side(g.away, "Away"), side(g.home, "Home")], finishLabel: g.finish && g.finish !== "REG" ? ` · ${g.finish}` : "",
      cells: [cell("Straight up", [["Projected", g.projWinner || dash], ["Result", winner === g.projWinner ? "Hit" : "Miss", true]]),
        cell("Spread", [["Line / proj", m.spread ? `${F.fmtLine(m.spread.line)} / ${typeof m.spread.proj === "number" ? F.fmtLine(m.spread.proj) : dash}` : dash], ["Landed", ats, true]]),
        cell("Total", [["Line / proj", m.total ? `${num(m.total.line)} / ${num(m.total.proj)}` : dash], ["Landed", m.total ? `${tot} · ${tot > m.total.line ? "Over" : tot < m.total.line ? "Under" : "Push"}` : String(tot), true]])],
      ...resultPick(g.pick) };
  });
  return { ...common(data, sport), kicker: `${data.season} Men's College Basketball · ${data.resultsDate ? F.fmtDateOnly(data.resultsDate) : ""}`, dateShort: data.resultsDate ? F.fmtDateOnly(data.resultsDate) : "",
    strip: [{ label: "Straight up", value: F.recStr(s.straightUp || { w: 0, l: 0 }) }, picksCell(s), { label: "Against the spread", value: F.recStr(s.ats || { w: 0, l: 0, p: 0 }) }],
    games, count: games.length, isEmpty: games.length === 0, notice: data.notice || "No games were settled for this date.", vsLabel: "Projected score vs final" };
}

// Only "push" is a Push. This mapped every result it did not recognise --
// null, a missing key, any other word -- to "Push", so a pick the settler
// could not answer for was published as a returned stake. Anything that is
// not a grade is "Not graded", in the colours an unpriced game uses. Pinned
// by tests/test_an_ungraded_pick_is_never_a_push.py.
const GRADES = { win: "Win", loss: "Loss", void: "Void", push: "Push" };
function resultPick(p) {
  if (!p) return { hasPick: false, pick: { label: "", market: "", result: "", color: "#14151a", bg: "#f4f2ee" } };
  const r = p.result, word = Object.hasOwn(GRADES, r) ? GRADES[r] : "Not graded";
  return { hasPick: true, pick: { label: p.label, market: `${p.market}${typeof p.price === "number" ? ` · ${F.fmtOdds(p.price)}` : ""}`, result: word, color: r === "win" ? "#f4f2ee" : r === "loss" ? "#b0341f" : word === "Not graded" ? "#6b6e7a" : "#14151a", bg: r === "win" ? "#2c7a5a" : "#f4f2ee" } };
}

// The Model picks cell of a Results strip. The record is graded picks only,
// so a page whose every pick went ungraded read "0–0–0" exactly like a page
// with nothing to grade; the cell now names the ungraded count when there is
// one. Pinned by tests/test_an_ungraded_pick_is_never_a_push.py.
function picksCell(s) {
  const n = typeof s.ungraded === "number" && s.ungraded > 0 ? s.ungraded : 0;
  return { label: n ? `Model picks · ${n} ungraded` : "Model picks", value: F.recStr(s.picks || { w: 0, l: 0, p: 0 }) };
}

// ---------- NHL player props ----------
// The props block of board.json / results.json. Kind, tier, units and edge are the
// pipeline's; nothing here decides a pick. Pinned by the same rule as team picks:
// a lean is never shown as a best bet, and a starter who is not confirmed is never
// staked (the pipeline writes such a goalie prop as a pass; the page greys it).
export const PROP_MARKETS = {
  shots_on_goal: { title: "Shots on goal", one: "shot", many: "shots" },
  points: { title: "Points", one: "point", many: "points" },
  goals: { title: "Goals", one: "goal", many: "goals" },
  assists: { title: "Assists", one: "assist", many: "assists" },
  blocked_shots: { title: "Blocked shots", one: "blocked shot", many: "blocked shots" },
  hits: { title: "Hits", one: "hit", many: "hits" },
  faceoffs_won: { title: "Faceoffs won", one: "faceoff won", many: "faceoffs won" },
  power_play_points: { title: "Power-play points", one: "power-play point", many: "power-play points" },
  goalie_saves: { title: "Goalie saves", one: "save", many: "saves" },
  goals_against: { title: "Goals against", one: "goal against", many: "goals against" },
};
export const PROPS_DISCLOSURE = "The model has no demonstrated edge in any market. Picks are recorded so they can be graded, not because they are known winners.";
const propMarket = (k) => PROP_MARKETS[k] || { title: String(k || "").replace(/_/g, " "), one: String(k || "").replace(/_/g, " "), many: String(k || "").replace(/_/g, " ") };
const propLabel = (r, m) => `${r.side === "under" ? "Under" : "Over"} ${typeof r.line === "number" ? r.line : dash} ${r.line === 1 ? m.one : m.many}`;
const PROP_RANK = { bet: 0, lean: 1, pass: 2 };
const money = (x) => `$${x % 1 ? x.toFixed(2) : x.toFixed(0)}`;
const unitsWord = (u) => `${u} unit${u === 1 ? "" : "s"}`;

function nhlProps(data) {
  const P = data.props, T = data.teams || {}, unit = data.unitDollars ?? 25, pre = data.phase === "preseason";
  const games = Object.fromEntries((data.games || []).map((g) => [g.id, g]));
  const none = { bets: 0, leans: 0, total: 0 };
  if (!P || typeof P !== "object") return { status: "missing", rows: [], counts: none, note: "", disclosure: PROPS_DISCLOSURE,
    empty: { tag: "No props", title: "Props are not on this board", body: "This board was built before the pipeline published player props." } };
  const status = ["ok", "no_lines", "abstain"].includes(P.status) ? P.status : "ok", notes = P.marketNotes || {};
  const rows = (status === "ok" ? P.rows || [] : []).map((r) => {
    const m = propMarket(r.market), t = T[r.team] || {}, g = games[r.gameId];
    const kind = PROP_RANK[r.kind] != null ? r.kind : "pass", unconfirmed = r.starterConfirmed === false, u = typeof r.units === "number" ? r.units : null;
    const where = g ? (g.home.abbr === r.team ? `vs ${r.opp}` : `@ ${r.opp}`) : r.opp ? `vs ${r.opp}` : "";
    return {
      key: `${r.gameId}|${r.playerId || r.player}|${r.market}|${r.line}|${r.side}`,
      gameId: r.gameId, player: r.player, playerId: r.playerId, espnId: r.espnId, team: r.team, opp: r.opp, position: r.position || "",
      teamName: t.short || t.name || r.team, color: t.color || "#14151a", fg: t.fg || "#fff", meta: [r.position, where].filter(Boolean).join(" · "),
      market: r.market, marketTitle: m.title, unitOne: m.one, unitMany: m.many, line: r.line, side: r.side, label: propLabel(r, m),
      priceLine: `${odds(r.price)}${r.book ? ` at ${r.book}` : ""}`, proj: typeof r.projection === "number" ? r.projection.toFixed(r.projection < 1 ? 2 : 1) : dash,
      prob: pct(r.modelProb), fair: odds(r.fairPrice), edge: typeof r.edgePct === "number" ? `${F.fmtSigned(r.edgePct)}%` : dash, edgeNum: typeof r.edgePct === "number" ? r.edgePct : -Infinity,
      kind, kindLabel: kind === "bet" ? "Best bet" : kind === "lean" ? "Lean" : "Pass",
      stake: kind === "bet" && u != null && !unconfirmed ? [r.tier ? `Tier ${r.tier}` : null, unitsWord(u), money(u * unit)].filter(Boolean).join(" · ")
        : kind === "lean" ? `Recorded, not staked${r.allowlisted === false ? " · market not allowlisted" : ""}` : "",
      note: notes[r.market] || "", unconfirmed, goalieNote: unconfirmed ? "Starter not confirmed — not priced as a bet" : "",
    };
  }).sort((a, b) => PROP_RANK[a.kind] - PROP_RANK[b.kind] || b.edgeNum - a.edgeNum);
  let empty = null;
  if (status === "no_lines") empty = { tag: "No lines", title: "Lines not posted yet", body: P.note || "No book had posted player props when this board was built. The next refresh looks again." };
  else if (status === "abstain") empty = { tag: "Abstains", title: pre ? "Model abstains — preseason" : "Model abstains", body: P.note || "The props model prices regular-season games only." };
  else if (!rows.length) empty = { tag: "No props", title: "No props priced tonight", body: P.note || "The props block arrived with no rows." };
  const bets = rows.filter((r) => r.kind === "bet").length, leans = rows.filter((r) => r.kind === "lean").length;
  return { status, rows, empty, note: status === "ok" ? P.note || "" : "", disclosure: PROPS_DISCLOSURE, counts: { bets, leans, total: rows.length },
    summary: `${rows.length} priced · ${bets} best bet${bets === 1 ? "" : "s"} · ${leans} lean${leans === 1 ? "" : "s"}` };
}

function nhlPropResults(data) {
  const P = data.props, T = data.teams || {};
  if (!P || typeof P !== "object") return { status: "missing", rows: [], strip: [], summaryLine: "",
    empty: { tag: "No props", title: "No props on this page", body: "These results were settled before the pipeline published player props." } };
  const status = ["ok", "no_lines", "abstain"].includes(P.status) ? P.status : "ok";
  const rows = (status === "ok" ? P.rows || [] : []).map((r) => {
    const m = propMarket(r.market), t = T[r.team] || {}, label = propLabel(r, m), kind = PROP_RANK[r.kind] != null ? r.kind : "pass";
    const res = r.result, word = Object.hasOwn(GRADES, res) ? GRADES[res] : "Not graded", has = typeof r.actual === "number";
    const outcome = res === "void" ? (has ? `finished with ${r.actual} · void` : "did not play · void")
      : has ? `finished with ${r.actual}${res === "win" ? " ✓" : res === "loss" ? " ✗" : res === "push" ? " · push" : ""}` : "no final stat yet";
    return { key: `${r.gameId}|${r.playerId || r.player}|${r.market}`, player: r.player, team: r.team, color: t.color || "#14151a", fg: t.fg || "#fff",
      meta: [r.position, r.opp ? `vs ${r.opp}` : ""].filter(Boolean).join(" · "), line: `${label} — ${outcome}`, kind, rank: PROP_RANK[kind],
      kindWord: kind === "bet" ? ["Best bet", r.tier ? `Tier ${r.tier}` : null, typeof r.units === "number" ? unitsWord(r.units) : null].filter(Boolean).join(" · ") : `${kind === "lean" ? "Lean" : "Pass"} · not in the record`,
      priceLine: `${odds(r.price)}${r.book ? ` at ${r.book}` : ""}`, result: word,
      color2: res === "win" ? "#f4f2ee" : res === "loss" ? "#b0341f" : word === "Not graded" ? "#6b6e7a" : "#14151a", bg: res === "win" ? "#2c7a5a" : "#f4f2ee",
      units: kind === "bet" && typeof r.profitUnits === "number" ? `${F.fmtSigned(r.profitUnits, 2)} u` : "" };
  }).sort((a, b) => a.rank - b.rank);
  const s = P.summary, se = P.season, u = (x) => (typeof x === "number" ? `${F.fmtSigned(x, 2)} units` : dash);
  const strip = [
    { label: "Props · best bets", value: s ? F.recStr(s) : dash, sub: s ? `${u(s.units)}${s.ungraded ? ` · ${s.ungraded} ungraded` : ""}` : "Nothing graded" },
    { label: "Props · season", value: se && se.nights ? F.recStr(se) : dash, sub: se && se.nights ? `${u(se.units)} · ${se.nights} night${se.nights === 1 ? "" : "s"}` : "No night settled yet" },
  ];
  let empty = null;
  if (status === "no_lines") empty = { tag: "No lines", title: "No props were published for this date", body: P.note || "No book had posted player props when the board was built." };
  else if (status === "abstain") empty = { tag: "Abstained", title: data.phase === "preseason" ? "Model abstained — preseason" : "Model abstained", body: P.note || "The props model prices regular-season games only." };
  else if (!rows.length) empty = { tag: "No props", title: "No props were recorded for this date", body: P.note || "The props block arrived with no rows." };
  const bets = rows.filter((r) => r.kind === "bet").length, leans = rows.filter((r) => r.kind === "lean").length;
  return { status, rows, strip, empty, summaryLine: rows.length ? `${bets} best bet${bets === 1 ? "" : "s"} · ${leans} lean${leans === 1 ? "" : "s"} settled` : "" };
}

export const ADAPTERS = { nhl: { board: nhlBoard, results: nhlResults, props: nhlProps, propResults: nhlPropResults }, epl: { board: eplBoard, results: eplResults }, cbb: { board: cbbBoard, results: cbbResults } };

// One line for the home page.
export function hubLine(sport, board, results) {
  const s = SPORTS[sport];
  if (!board) return { sport: s, headline: "Feed unreachable", detail: "", stale: true };
  const vm = ADAPTERS[sport].board(board);
  const games = vm.groups.reduce((n, g) => n + g.games.length, 0);
  const bets = vm.groups.reduce((n, g) => n + g.games.filter((x) => x.pick.kind === "bet" && !x.started).length, 0);
  const when = sport === "epl" ? "this window" : "tonight";
  let headline = games ? `${games} ${sport === "epl" ? "fixtures" : "games"} ${when} · ${bets ? `${bets} best bet${bets === 1 ? "" : "s"}` : "no best bets"}` : `No ${sport === "epl" ? "fixtures" : "games"} ${when}`;
  if (board.phase === "preseason") headline = `${games} exhibition games · no projections`;
  let detail = "";
  if (results && results.games && results.games.length) {
    const p = (results.summary || {}).picks;
    detail = p ? `Yesterday's picks ${F.recStr(p)}` : `${results.games.length} settled yesterday`;
  // First sentence only, with any trailing period stripped before one is
  // added back: a notice whose first sentence IS the whole notice already
  // ends in "." and printed "…settles them.." on the hub.
  } else if (results && results.notice) detail = results.notice.split(". ")[0].replace(/\.*$/, "") + ".";
  return { sport: s, headline, detail, stale: vm.stale, updated: vm.updated };
}
