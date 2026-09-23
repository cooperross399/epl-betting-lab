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
];

const pickView = (p, unit, opts = {}) => {
  if (!p) return { kind: "none", heading: "Model pick", label: opts.noneLabel || "No market clears the edge bar", sub: "", extra: "" };
  const price = opts.priceFmt ? opts.priceFmt(p.price) : odds(p.price);
  const edge = typeof p.edgePct === "number" ? `${F.fmtSigned(p.edgePct)}%` : dash;
  const kind = p.kind || "bet";
  return {
    kind, heading: kind === "bet" ? "Best bet" : kind === "lean" ? "Lean" : kind === "pass" ? "Model pick" : "Model pick",
    label: p.label, price, edge,
    sub: `${p.market} · ${price}${p.book ? ` at ${p.book}` : ""}${typeof p.modelProb === "number" ? ` · model ${pct(p.modelProb)}` : ""} · edge ${edge}`,
    extra: kind === "bet" ? [p.tier ? `Tier ${p.tier}` : null, typeof p.units === "number" ? `${p.units} units · $${(p.units * unit).toFixed(2)}` : null].filter(Boolean).join(" · ") : kind === "lean" ? "Lean · recorded, not staked" : "",
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
    const p = g.pick ? { kind: "bet", ...g.pick } : null;
    if (p && !g.started) bets++;
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
      cells, pick: pickView(p, unit, { noneLabel: pre ? "Exhibition · model abstains"
        : (data.allowlistedMarkets || []).length ? "No market clears the edge bar"
        : "No market is allowlisted for selection" }),
      score: modelled ? `${num(g.away.projGoals)} – ${num(g.home.projGoals)}` : dash,
    });
  }
  const r = data.record || {}, fw = r.forward;
  const strip = [
    { label: "Straight up", value: F.recStr(r.straightUp || { w: 0, l: 0 }), sub: `${F.winRate((r.straightUp || {}).w || 0, (r.straightUp || {}).l || 0)} of games`, fine: "" },
    { label: "Puck line", value: F.recStr(r.puckLine || { w: 0, l: 0, p: 0 }), sub: "against the spread", fine: "" },
    { label: "Totals", value: F.recStr(r.totals || { w: 0, l: 0, p: 0 }), sub: "over / under", fine: "" },
    // No unsealed branch, on purpose, for the fifth time -- it arrived again
    // when this rendering moved out of the page and into this module, where
    // the guard that greps the page could not see it. `load_record` always
    // returns sealed:true and never emits the return fields, so
    // the branch is unreachable today and a live route back to publishing the
    // return tomorrow. NHL's pooled forward return IS the test decided
    // 2027-04-25 (docs/when_this_ends.md).
    //
    // `rows` is build_forward_report's len(ledger): every frozen opinion,
    // settled or not. It is not called "settled".
    //
    // The sibling adapters below DO publish their records, and must: EPL's
    // card is allowlisted and CBB's measurement is historical. Neither is a
    // pre-registered forward test. Pinned by
    // tests/test_site_publishes_no_forward_return.py.
    { label: "Forward ledger · sealed", value: fw && fw.rows ? String(fw.rows) : dash,
      sub: !fw ? "No forward ledger yet"
        : fw.rows ? `opinions frozen across ${fw.markets} market${fw.markets === 1 ? "" : "s"} · return decided ${F.fmtDateOnly(fw.decisionDate)}, not before`
        : `Nothing frozen yet · return decided ${F.fmtDateOnly(fw.decisionDate)}, not before`,
      fine: "" },
  ];
  return { ...common(data, sport), kicker: `${data.season} NHL · ${data.boardDate ? F.fmtDateOnly(data.boardDate) : ""}`, title: ["Tonight's", "Board."],
    blurb: "Model-projected scores, win probabilities and market context for every game on tonight's slate.", strip, groups: [...byDay.values()].map((d) => ({ ...d, countLabel: `${d.games.length} game${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} games · ${bets} best bets · ${leans} leans · a unit is $${unit}`, unit };
}

function nhlResults(data) {
  const sport = SPORTS.nhl, T = data.teams || {}, s = data.summary || {};
  const games = (data.games || []).map((g) => {
    const winner = g.away.final > g.home.final ? g.away.abbr : g.home.abbr, suHit = winner === g.projWinner, tot = g.away.final + g.home.final;
    const side = (x) => ({ ...sideBase(T, x), proj: num(x.projGoals), final: x.final, scoreColor: x.abbr === winner ? "#14151a" : "#9a9ca6" });
    return { sides: [side(g.away), side(g.home)], finishLabel: g.finish && g.finish !== "REG" ? ` · ${g.finish}` : "",
      cells: [cell("Straight up", [["Projected", g.projWinner], ["Result", suHit ? "Hit" : "Miss", true]]), cell("Total", [["Line / proj", `${num(g.total.line)} / ${num(g.total.proj)}`], ["Landed", `${tot} · ${g.total.result === "over" ? "Over" : g.total.result === "under" ? "Under" : "Push"}`, true]])],
      ...resultPick(g.pick) };
  });
  return { ...common(data, sport), kicker: `${data.season} NHL · ${data.resultsDate ? F.fmtDateOnly(data.resultsDate) : ""}`, dateShort: data.resultsDate ? F.fmtDateOnly(data.resultsDate) : "",
    strip: [{ label: "Straight up", value: F.recStr(s.straightUp || { w: 0, l: 0 }) }, { label: "Model picks", value: F.recStr(s.picks || { w: 0, l: 0, p: 0 }) }, { label: "Totals", value: F.recStr(s.totals || { w: 0, l: 0, p: 0 }) }],
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
        cell("Match result · fair", [["Home", odds(fair.home)], ["Draw", odds(fair.draw)], ["Away", odds(fair.away)]], null, "not on the card"),
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
    { label: "Time to an answer", value: `~${(r.betsToAnswer ?? 1500).toLocaleString()}`, sub: "settled bets to separate a real 5% edge from zero", fine: "" },
  ];
  return { ...common(data, sport), kicker: `${data.season} Premier League · ${data.windowLabel || ""}`, title: ["This week's", "Board."],
    blurb: "Model-projected goals, outcome probabilities and market context for every fixture in this card's window. Match result is not on the card; its fair price is shown for reference only.",
    strip, groups: [...byDay.values()].map((d) => ({ ...d, countLabel: `${d.games.length} fixture${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} fixtures · ${bets} best bets · ${leans} leans · a unit is $${unit}`, unit };
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
    strip: [{ label: "Model picks", value: F.recStr(s.picks || { w: 0, l: 0, p: 0 }) }, { label: "Favoured side", value: F.recStr(s.result || { w: 0, l: 0 }) }, { label: "Total 2.5 leans", value: F.recStr(s.totals || { w: 0, l: 0 }) }],
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
  strip.push({ label: "Time to an answer", value: (r.opinionsSoFar ?? 0).toLocaleString(), sub: `of ${(r.opinionsNeeded ?? 10000).toLocaleString()} settled opinions before the stopping rule speaks`, fine: typeof r.clvPoints === "number" ? `CLV ${F.fmtSigned(r.clvPoints, 2)} pts` : "" });
  return { ...common(data, sport), kicker: `${data.season} Men's College Basketball · ${data.slateDate ? F.fmtDateOnly(data.slateDate) : ""}${data.cardSlot ? ` · ${data.cardSlot} card` : ""}`, title: ["Tonight's", "Board."],
    blurb: "Model-projected scores, win probabilities and market context for every carded game on tonight's slate.",
    strip, groups: order.filter((k) => bySlot.has(k)).map((k) => bySlot.get(k)).map((d) => ({ ...d, countLabel: `${d.games.length} game${d.games.length === 1 ? "" : "s"}` })),
    summary: `Showing ${(data.games || []).length} games · ${bets} best bets · ${leans} leans · a unit is $${unit}`, unit };
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
    strip: [{ label: "Straight up", value: F.recStr(s.straightUp || { w: 0, l: 0 }) }, { label: "Model picks", value: F.recStr(s.picks || { w: 0, l: 0, p: 0 }) }, { label: "Against the spread", value: F.recStr(s.ats || { w: 0, l: 0, p: 0 }) }],
    games, count: games.length, isEmpty: games.length === 0, notice: data.notice || "No games were settled for this date.", vsLabel: "Projected score vs final" };
}

function resultPick(p) {
  if (!p) return { hasPick: false, pick: { label: "", market: "", result: "", color: "#14151a", bg: "#f4f2ee" } };
  const r = p.result;
  return { hasPick: true, pick: { label: p.label, market: `${p.market}${typeof p.price === "number" ? ` · ${F.fmtOdds(p.price)}` : ""}`, result: r === "win" ? "Win" : r === "loss" ? "Loss" : r === "void" ? "Void" : "Push", color: r === "win" ? "#f4f2ee" : r === "loss" ? "#b0341f" : "#14151a", bg: r === "win" ? "#2c7a5a" : "#f4f2ee" } };
}

export const ADAPTERS = { nhl: { board: nhlBoard, results: nhlResults }, epl: { board: eplBoard, results: eplResults }, cbb: { board: cbbBoard, results: cbbResults } };

// One line for the home page.
export function hubLine(sport, board, results) {
  const s = SPORTS[sport];
  if (!board) return { sport: s, headline: "Feed unreachable", detail: "", stale: true };
  const vm = ADAPTERS[sport].board(board);
  const games = vm.groups.reduce((n, g) => n + g.games.length, 0);
  const bets = vm.groups.reduce((n, g) => n + g.games.filter((x) => x.pick.kind === "bet" && !x.started).length, 0);
  const when = sport === "epl" ? "this window" : "tonight";
  let headline = games ? `${games} ${sport === "epl" ? "fixtures" : "games"} ${when} · ${bets ? `${bets} best bet${bets === 1 ? "" : "s"}` : "no best bets"}` : `No ${sport === "epl" ? "fixtures" : "games"} ${when}`;
  if (board.phase === "preseason") headline = `${games} exhibition games · model abstains`;
  let detail = "";
  if (results && results.games && results.games.length) {
    const p = (results.summary || {}).picks;
    detail = p ? `Yesterday's picks ${F.recStr(p)}` : `${results.games.length} settled yesterday`;
  } else if (results && results.notice) detail = results.notice.split(". ")[0] + ".";
  return { sport: s, headline, detail, stale: vm.stale, updated: vm.updated };
}
