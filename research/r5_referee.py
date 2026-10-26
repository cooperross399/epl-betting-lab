"""Does knowing the referee improve a held-out card forecast?

Walk-forward over every Football-Data season on file. Baseline: each match's
expected bookings from both teams' prior card rates (exponentially weighted,
shrunk to the league). With referee: that times the referee's prior
cards-over-expected ratio, shrunk toward 1 with K pseudo-matches. Scored on
the last two seasons only, as Poisson log likelihood and over 3.5 / 4.5 log loss.
"""
import glob, math
import numpy as np, pandas as pd

frames = []
for path in sorted(glob.glob("data/raw/football_data_E0_*.csv")):
    df = pd.read_csv(path, encoding="latin-1")
    df["season"] = path.rsplit("_", 1)[1][:4]
    frames.append(df)
d = pd.concat(frames, ignore_index=True).dropna(subset=["HomeTeam", "AwayTeam", "HY", "AY", "Referee"])
d["date"] = pd.to_datetime(d["Date"], dayfirst=True)
d = d.sort_values("date").reset_index(drop=True)
d["cards"] = d.HY + d.AY + d.HR.fillna(0) + d.AR.fillna(0)
print("matches", len(d), "seasons", sorted(d.season.unique()), "referees", d.Referee.nunique())
seasons = sorted(d.season.unique()); test = set(seasons[-2:])
HL = 365.0
def pois_ll(k, lam): return k * math.log(lam) - lam - math.lgamma(k + 1)
def p_over(line, lam): return 1 - sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(int(line) + 1))
team_hist = {}; ref_hist = {}
res = {K: [] for K in (5, 10, 20, 40)}; base = []
for i, r in d.iterrows():
    past = d.iloc[max(0, i - 760):i]
    if len(past) >= 300:
        lg = past.cards.mean()
        def rate(t):
            h = team_hist.get(t, [])
            if len(h) < 3: return 1.0
            w = np.array([0.5 ** ((r.date - dd).days / HL) for dd, _ in h]); v = np.array([x for _, x in h])
            n = w.sum(); return ((w * v).sum() + 5 * 1.0) / (n + 5)
        lam = lg * rate(r.HomeTeam) * rate(r.AwayTeam)
        rh = ref_hist.get(r.Referee, [])
        if r.season in test:
            base.append((r.cards, lam))
            for K in res:
                num = sum(c for c, l in rh); den = sum(l for c, l in rh)
                f = (num + K * 1.0 * 1) / (den + K) if den else 1.0
                # ratio shrunk: (sum cards + K*mean) / (sum expected + K*mean) with mean 1 per unit
                f = (num + K * lg) / (den + K * lg) if rh else 1.0
                res[K].append((r.cards, lam * f))
        ref_hist.setdefault(r.Referee, []).append((r.cards, lam))
        ratio_t = r.cards / lg
    else:
        ratio_t = r.cards / max(d.iloc[:i + 1].cards.mean(), 1)
    for t in (r.HomeTeam, r.AwayTeam):
        team_hist.setdefault(t, []).append((r.date, math.sqrt(max(r.cards, 0.25) / max(d.iloc[max(0,i-760):i+1].cards.mean(), 1))))
def score(rows, name):
    ll = np.mean([pois_ll(k, l) for k, l in rows])
    out = []
    for line in (3.5, 4.5):
        y = np.array([k > line for k, _ in rows], float); p = np.clip([p_over(line, l) for _, l in rows], 1e-6, 1 - 1e-6)
        out.append(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    print(f"{name:22s} n {len(rows)} poisson ll {ll:.4f}  logloss o3.5 {out[0]:.4f}  o4.5 {out[1]:.4f}")
score(base, "teams only")
for K, rows in res.items(): score(rows, f"teams x referee K={K}")
# spread of referee factors at the end
lg = d.cards.tail(760).mean()
f = {ref: (sum(c for c, _ in h) + 20 * lg) / (sum(l for _, l in h) + 20 * lg) for ref, h in ref_hist.items() if len(h) >= 20}
s = pd.Series(f).sort_values(); print("referee factor (K=20, 20+ matches):", s.round(2).head(4).to_dict(), "...", s.round(2).tail(4).to_dict())
