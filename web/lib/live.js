// Live scores for the NHL board, read from ESPN's public site API, which answers
// cross-origin requests from a browser. api-web.nhle.com sends no CORS header and
// fails from a page; it stays server-side (build_site_json settles from it).
// Nothing here is a pick. It reads scores and box-score counts and compares them
// with what board.json already published.

export const ESPN = {
  scoreboard: (ymd) => `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=${ymd}`,
  summary: (id) => `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event=${id}`,
};

// ESPN abbreviation -> board abbreviation. Codes not listed are taken as identical.
// A game whose codes and start time do not land on a board game stays unmatched
// and is shown as unmatched, never attached to the nearest guess.
export const ESPN_TO_BOARD = { TB: "TBL", NJ: "NJD", SJ: "SJS", LA: "LAK", UTAH: "UTA", UTA: "UTA", VEG: "VGK", WAS: "WSH", MON: "MTL", NAS: "NSH", CLB: "CBJ" };
export const toBoard = (a) => (a && ESPN_TO_BOARD[a]) || a || "?";
export const MATCH_WINDOW_HOURS = 3;

const ORD = ["", "1st", "2nd", "3rd"];
// Regular season: period 4 is overtime, 5 the shootout. A playoff period 5 is 2OT.
export const periodName = (p, regular = true) => ORD[p] || (p === 4 ? "OT" : p > 4 ? (regular ? "SO" : `${p - 3}OT`) : "");

export const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
  .replace(/[^a-z ]/g, "").replace(/\b(jr|sr|ii|iii)\b/g, "").replace(/\s+/g, " ").trim();
const toNum = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };

export async function getJSON(url, ms = 10e3) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { cache: "no-store", signal: ctl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally { clearTimeout(t); }
}

export function parseScoreboard(json) {
  return ((json && json.events) || []).map((ev) => {
    const c = (ev.competitions || [])[0] || {};
    const st = c.status || ev.status || {}, type = st.type || {};
    const side = (ha) => {
      const x = (c.competitors || []).find((k) => k.homeAway === ha) || {}, t = x.team || {};
      return { espn: t.abbreviation || "?", abbr: toBoard(t.abbreviation), score: x.score != null && x.score !== "" ? Number(x.score) : null };
    };
    return { id: String(ev.id), startUtc: c.date || ev.date, state: type.state || "pre", detail: type.shortDetail || type.detail || "",
      period: st.period || 0, clock: st.displayClock || "", away: side("away"), home: side("home") };
  });
}

export function stateLabel(e) {
  if (e.state === "pre") return { top: "", sub: "", tone: "pre" };
  if (e.state === "post") return { top: /final/i.test(e.detail) ? e.detail.replace(/\s+/g, " ") : "Final", sub: "", tone: "post" };
  const p = periodName(e.period);
  return { top: e.clock && e.clock !== "0:00" ? `${p} ${e.clock}` : `End ${p}`, sub: "Live", tone: "in" };
}

// 25 s while a game is on; up to 5 min while games are only scheduled (sooner
// when one is about to start); stop once every game is final.
export function scoreboardDelay(events, now = Date.now()) {
  if (!events || !events.length) return null;
  if (events.some((e) => e.state === "in")) return 25e3;
  const pre = events.filter((e) => e.state === "pre");
  if (!pre.length) return null;
  const until = Math.min(...pre.map((e) => Date.parse(e.startUtc) || Infinity)) - now;
  if (until <= 0) return 60e3;
  return Math.max(15e3, Math.min(300e3, until + 20e3));
}

// One fetch loop: pauses while the tab is hidden, refreshes once on return,
// backs off on errors (15 s doubling to 5 min) and keeps the last good data.
export class Poller {
  constructor({ fetcher, delayFor, onChange }) {
    Object.assign(this, { fetcher, delayFor, onChange, timer: null, busy: false, stopped: false, failures: 0, data: undefined, at: null, error: null, nextAt: null });
    this.onVis = () => {
      if (document.hidden) return this.clear();
      if (this.at && this.nextAt == null && !this.error) return; // finished: nothing left to refresh
      this.tick();
    };
  }
  start() { document.addEventListener("visibilitychange", this.onVis); this.tick(); return this; }
  stop() { this.stopped = true; this.clear(); document.removeEventListener("visibilitychange", this.onVis); }
  clear() { clearTimeout(this.timer); this.timer = null; }
  async tick() {
    if (this.stopped || this.busy || document.hidden) return;
    this.clear(); this.busy = true;
    try { this.data = await this.fetcher(); this.at = Date.now(); this.error = null; this.failures = 0; }
    catch (e) { this.error = e; this.failures += 1; }
    this.busy = false;
    if (this.stopped) return;
    const d = this.error ? Math.min(300e3, 15e3 * 2 ** (this.failures - 1)) : this.delayFor(this.data);
    this.nextAt = d == null ? null : Date.now() + d;
    this.onChange({ data: this.data, at: this.at, error: this.error ? this.error.message || String(this.error) : null, failures: this.failures, nextAt: this.nextAt });
    if (d != null && !document.hidden) this.timer = setTimeout(() => this.tick(), d);
  }
}

// Board game <- ESPN event: same away and home code after mapping, start within
// MATCH_WINDOW_HOURS. Anything else is unmatched, with the reason.
export function matchEvents(events, games) {
  const byGame = {}, unmatched = [], codes = new Set((games || []).flatMap((g) => [g.away.abbr, g.home.abbr]));
  for (const e of events || []) {
    const t = Date.parse(e.startUtc);
    const g = (games || []).find((x) => !byGame[x.id] && x.away.abbr === e.away.abbr && x.home.abbr === e.home.abbr && Math.abs(Date.parse(x.startUtc) - t) <= MATCH_WINDOW_HOURS * 36e5);
    if (g) { byGame[g.id] = e; continue; }
    const unknown = [e.away, e.home].filter((s) => !codes.has(s.abbr)).map((s) => s.espn);
    unmatched.push({ ...e, why: unknown.length === 2 ? "neither team on this board" : unknown.length ? `no board code for ${unknown[0]}` : "start time differs from the board" });
  }
  return { byGame, unmatched };
}

// Live status of the board's team pick against the current score. Needs
// pick.side ("away" | "home" | "over" | "under") and, for totals, pick.line.
export function pickStatus(pick, e) {
  if (!pick || !e || e.state === "pre" || e.away.score == null || e.home.score == null) return null;
  const a = e.away.score, h = e.home.score, fin = e.state === "post", end = fin ? " · final, settles on Results" : "";
  if (pick.side === "home" || pick.side === "away") {
    if (!/moneyline|^ml$/i.test(pick.market || "")) return { word: "not tracked", tone: "mute", detail: "live status covers moneyline and totals" };
    const d = pick.side === "home" ? h - a : a - h;
    if (d === 0) return { word: "tied", tone: "flat", detail: `${a}–${h}${end}` };
    return d > 0 ? { word: fin ? "won" : "winning", tone: "win", detail: `${fin ? "by" : "leads by"} ${d}${end}` }
      : { word: fin ? "lost" : "losing", tone: "lose", detail: `${fin ? "by" : "trails by"} ${-d}${end}` };
  }
  if ((pick.side === "over" || pick.side === "under") && typeof pick.line === "number") {
    const tot = a + h, over = pick.side === "over";
    if (tot === pick.line) return { word: "push", tone: "flat", detail: `${tot} goals on a ${pick.line} line${end}` };
    const ahead = over ? tot > pick.line : tot < pick.line;
    const need = over && !ahead && !fin ? ` · needs ${Math.floor(pick.line) + 1 - tot} more` : "";
    return { word: ahead ? (fin ? "won" : "winning") : fin ? "lost" : "losing", tone: ahead ? "win" : "lose", detail: `${tot} goals, line ${pick.line}${need}${end}` };
  }
  return { word: "unavailable", tone: "mute", detail: "this pick carries no side to track" };
}

// Prop market -> ESPN box-score column, by key with the column label as fallback.
// null: ESPN's box score has no equivalent, and the page says so instead of guessing.
// The key names are the single place to correct if ESPN renames a column.
export const PROP_STATS = {
  // ESPN's "SOG" column is SHOOTOUT goals (key shootoutGoals), not shots on
  // goal; shots on goal is key shotsTotal, label "S". Checked on real box
  // scores 2026-10-07. Never fall back to the "SOG" label.
  shots_on_goal: { group: "skater", read: [["shotsTotal", "S"], ["shotsOnGoal", null]] },
  goals: { group: "skater", read: [["goals", "G"]] },
  assists: { group: "skater", read: [["assists", "A"]] },
  points: { group: "skater", sum: ["goals", "assists"] },
  blocked_shots: { group: "skater", read: [["blockedShots", "BS"]] },
  hits: { group: "skater", read: [["hits", "HT"]] },
  faceoffs_won: { group: "skater", read: [["faceoffsWon", "FW"]] },
  goalie_saves: { group: "goalie", read: [["saves", "SV"]] },
  goals_against: { group: "goalie", read: [["goalsAgainst", "GA"]] },
  power_play_points: null,
  time_on_ice: null,
};

export function parseSummary(json) {
  const bx = (json && json.boxscore) || {}, players = [], teams = {};
  for (const tb of bx.players || []) {
    const team = toBoard((tb.team || {}).abbreviation);
    for (const grp of tb.statistics || []) {
      const group = /goal/i.test(grp.name || "") ? "goalie" : "skater", keys = grp.keys || [], labels = grp.labels || [];
      for (const a of grp.athletes || []) {
        const vals = a.stats || [], stats = {}, byLabel = {}, ath = a.athlete || {};
        keys.forEach((k, i) => { stats[k] = toNum(vals[i]); });
        labels.forEach((l, i) => { byLabel[l] = toNum(vals[i]); });
        players.push({ id: String(ath.id || ""), name: ath.displayName || "", norm: norm(ath.displayName), team, group, stats, byLabel });
      }
    }
  }
  for (const t of bx.teams || []) {
    const s = {};
    for (const x of t.statistics || []) s[x.name] = toNum(x.displayValue);
    teams[toBoard((t.team || {}).abbreviation)] = s;
  }
  return { players, teams };
}

const readOne = (spec, p) => {
  for (const [k, l] of spec.read || []) {
    if (p.stats[k] != null) return p.stats[k];
    if (l && p.byLabel[l] != null) return p.byLabel[l];
  }
  return null;
};
export function liveStat(row, box) {
  const spec = Object.hasOwn(PROP_STATS, row.market) ? PROP_STATS[row.market] : null;
  if (!spec) return { ok: false, why: "Live stat unavailable for this market" };
  const n = norm(row.player);
  const p = (row.espnId && box.players.find((x) => x.id === String(row.espnId)))
    || box.players.find((x) => x.norm === n && x.team === row.team) || box.players.find((x) => x.norm === n);
  if (!p) return { ok: false, why: "Live stat unavailable · not in the box score yet" };
  let v;
  if (spec.sum) { const parts = spec.sum.map((m) => readOne(PROP_STATS[m], p)); v = parts.some((x) => x == null) ? null : parts.reduce((s, x) => s + x, 0); }
  else v = readOne(spec, p);
  return v == null ? { ok: false, why: "Live stat unavailable · no such column in the box score" } : { ok: true, value: v };
}

// Progress toward the line: an over needs floor(line)+1; an under loses there.
export function propProgress(row, v, e) {
  const target = Math.floor(row.line) + 1, over = row.side !== "under", fin = e.state === "post";
  const reached = v >= target, push = Number.isInteger(row.line) && v === row.line;
  let tone = "flat";
  if (fin) tone = push ? "flat" : (over ? reached : !reached) ? "win" : "lose";
  else if (reached) tone = over ? "win" : "lose";
  return { target, pct: Math.min(100, Math.round((v / target) * 100)), tone, fin, push, period: fin ? "" : stateLabel(e).top,
    mark: fin ? (push ? "· push" : tone === "win" ? "✓" : "✗") : "" };
}

// ---------- EPL and CBB (additive; nothing above changes for NHL) ----------
// The same scoreboard reader for the other two boards. Each sport names its ESPN
// path, the codes where ESPN and the board differ, and how a period reads. A game
// matches on both teams (code after mapping, else the team's name) plus a start
// within the window; anything else stays unmatched and is shown that way.
const ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports";
export const LIVE_SPORTS = {
  nhl: { path: "hockey/nhl", codes: ESPN_TO_BOARD, windowHours: MATCH_WINDOW_HOURS, extra: "" },
  epl: { path: "soccer/eng.1", codes: { MNC: "MCI", MAN: "MUN", NOT: "NFO", NFF: "NFO", WHM: "WHU", SPU: "TOT" }, windowHours: 3, extra: "" },
  cbb: { path: "basketball/mens-college-basketball", codes: { CONN: "UCONN", VILL: "NOVA", KAN: "KU", KY: "UK", GONZ: "GONZ", IAST: "ISU", MSU: "MSU", NDAME: "ND", CREIGH: "CREI" }, windowHours: 3, extra: "&groups=50&limit=500" },
};
const ymdOf = (iso) => new Date(iso).toISOString().slice(0, 10).replace(/-/g, "");
// One request for the board's dates: a single day, or a range for a window (EPL).
// The range starts a day early because ESPN files a late-UTC start under the US day.
export function scoreboardUrlFor(sport, startIsos) {
  const L = LIVE_SPORTS[sport] || LIVE_SPORTS.nhl, ts = (startIsos || []).map((x) => Date.parse(x)).filter(Number.isFinite);
  if (!ts.length) return null;
  const lo = Math.min(...ts) - 864e5, hi = Math.max(...ts);
  const a = ymdOf(lo), b = ymdOf(hi);
  return `${ESPN_BASE}/${L.path}/scoreboard?dates=${a === b ? a : `${a}-${b}`}${L.extra}`;
}
export function parseScoreboardFor(sport, json) {
  const L = LIVE_SPORTS[sport] || LIVE_SPORTS.nhl, map = (x) => (x && L.codes[x]) || x || "?";
  return ((json && json.events) || []).map((ev) => {
    const c = (ev.competitions || [])[0] || {};
    const st = c.status || ev.status || {}, type = st.type || {};
    const side = (ha) => {
      const x = (c.competitors || []).find((k) => k.homeAway === ha) || {}, t = x.team || {};
      return { espn: t.abbreviation || "?", abbr: map(t.abbreviation), names: [t.displayName, t.shortDisplayName, t.location, t.name].filter(Boolean).map(norm),
        score: x.score != null && x.score !== "" ? Number(x.score) : null };
    };
    return { id: String(ev.id), startUtc: c.date || ev.date, state: type.state || "pre", detail: type.shortDetail || type.detail || "",
      period: st.period || 0, clock: st.displayClock || "", away: side("away"), home: side("home") };
  });
}
export function stateLabelFor(sport, e) {
  if (sport === "nhl" || !LIVE_SPORTS[sport]) return stateLabel(e);
  if (e.state === "pre") return { top: "", sub: "", tone: "pre" };
  if (e.state === "post") return { top: sport === "epl" ? "FT" : /OT/.test(e.detail) ? e.detail.replace(/^Final\s*\/?\s*/i, "Final ") : "Final", sub: "", tone: "post" };
  if (sport === "epl") return { top: /HT|half/i.test(e.detail) ? "HT" : e.clock || e.detail, sub: "Live", tone: "in" };
  const p = e.period <= 2 ? (e.period === 1 ? "1st" : "2nd") : e.period === 3 ? "OT" : `${e.period - 2}OT`;
  return { top: /halftime/i.test(e.detail) ? "Half" : e.clock && e.clock !== "0:00" ? `${p} ${e.clock}` : `End ${p}`, sub: "Live", tone: "in" };
}
// games: [{id, startUtc, away:{abbr}, home:{abbr}}]; teams: the board's teams lookup.
export function matchEventsFor(sport, events, games, teams) {
  if (sport === "nhl") return matchEvents(events, games);
  const L = LIVE_SPORTS[sport] || LIVE_SPORTS.nhl, T = teams || {}, byGame = {}, unmatched = [];
  const keys = (abbr) => { const t = T[abbr] || {}; return [t.name, t.short].filter(Boolean).map(norm); };
  const same = (side, abbr) => side.abbr === abbr || keys(abbr).some((k) => k && side.names.includes(k));
  for (const e of events || []) {
    const t = Date.parse(e.startUtc);
    const g = (games || []).find((x) => !byGame[x.id] && same(e.away, x.away.abbr) && same(e.home, x.home.abbr) && Math.abs(Date.parse(x.startUtc) - t) <= L.windowHours * 36e5);
    if (g) { byGame[g.id] = e; continue; }
    const known = (side) => (games || []).some((x) => same(side, x.away.abbr) || same(side, x.home.abbr));
    const unknown = [e.away, e.home].filter((s) => !known(s)).map((s) => s.espn);
    if (unknown.length === 2) continue; // a game this board never carried: not a mapping gap
    unmatched.push({ ...e, why: unknown.length ? `no board code for ${unknown[0]}` : "start time differs from the board" });
  }
  return { byGame, unmatched };
}
// Live status for EPL and CBB picks. Needs pick.side and, where a line applies,
// pick.line; without them the page shows no live status rather than a guess.
export function pickStatusFor(sport, pick, e) {
  if (sport === "nhl") return pickStatus(pick, e);
  if (!pick || !e || e.state === "pre" || e.away.score == null || e.home.score == null || !pick.side) return null;
  const a = e.away.score, h = e.home.score, fin = e.state === "post", m = String(pick.market || "").toLowerCase();
  const sc = sport === "epl" ? `${h}–${a}` : `${a}–${h}`;
  const out = (d, push) => (d === 0 ? { word: push ? "push" : "level", tone: "flat", detail: sc } : d > 0 ? { word: fin ? "won" : "winning", tone: "win", detail: sc } : { word: fin ? "lost" : "losing", tone: "lose", detail: sc });
  const mine = pick.side === "home" ? h - a : a - h;
  if (pick.side === "over" || pick.side === "under") {
    if (typeof pick.line !== "number" || /corner|card/.test(m)) return null;
    const tot = a + h; return out(pick.side === "over" ? tot - pick.line : pick.line - tot, true);
  }
  if (pick.side === "yes" || pick.side === "no") {
    if (!/btts|both/.test(m)) return null;
    const both = a > 0 && h > 0; return pick.side === "yes" ? (both ? out(1) : out(fin ? -1 : 0)) : both ? out(-1) : out(fin ? 1 : 0);
  }
  if (pick.side === "draw") return a === h ? out(1) : out(-1);
  if (pick.side !== "home" && pick.side !== "away") return null;
  if (/spread|handicap/.test(m)) return typeof pick.line === "number" ? out(mine + pick.line, true) : null;
  if (/draw.?no.?bet|dnb/.test(m)) return out(mine, true);
  if (/moneyline|^ml$|match result|1x2/.test(m)) return mine === 0 && sport === "epl" ? out(-1) : out(mine);
  return null;
}
