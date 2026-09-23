export const fmtOdds = (n) => (n > 0 ? `+${n}` : `−${Math.abs(n)}`);
export const fmtSigned = (n, d = 1) => (n > 0 ? `+${n.toFixed(d)}` : n < 0 ? `−${Math.abs(n).toFixed(d)}` : n.toFixed(d));
export const pct = (p) => `${Math.round(p * 100)}%`;
export const fmtLine = (n) => (n < 0 ? `−${Math.abs(n).toFixed(1)}` : `+${n.toFixed(1)}`);

const tf = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const tz = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" });
export const fmtTime = (iso) => tf.format(new Date(iso));
export const tzName = () => {
  const part = tz.formatToParts(new Date()).find((p) => p.type === "timeZoneName");
  return part ? part.value : "";
};
export const localDayKey = (iso) => {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const fmtDayLong = (iso) =>
  new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" }).format(new Date(iso));
export const fmtDateOnly = (ymd) => {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(y, m - 1, d));
};
export const fmtUpdated = (iso) =>
  new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(iso));

export const winRate = (w, l, p = 0) => {
  const n = w + l + p;
  return n ? `${((w / n) * 100).toFixed(1)}%` : "—";
};
export const recStr = (r) => (r.p != null ? `${r.w}–${r.l}–${r.p}` : `${r.w}–${r.l}`);

// The market favorite as "ABBR −150", matching the CFB page's open/current convention.
export const favLine = (ml, away, home) =>
  ml.home <= ml.away ? `${home} ${fmtOdds(ml.home)}` : `${away} ${fmtOdds(ml.away)}`;
