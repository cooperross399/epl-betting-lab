"""A single browser-readable status page for the whole operation.

Reading markdown in a repository is fine for Claude and poor for a person
glancing at their phone. This renders the three routine reports plus the card
into one self-contained HTML file that opens with a double click.

Design constraints, all deliberate:

* **Self-contained.** No external stylesheet, font, script, or image, so it
  works offline and from a `file://` URL.
* **Everything escaped.** Report values are data, not markup. Team names and
  book names go through HTML escaping before they reach the page.
* **No credential can appear.** The page is built only from the routine JSON
  reports, which never contain credential material, and a test asserts a
  key-shaped value planted in a report does not reach the output.
* **Honest when blocked.** A blocked card renders as blocked with its reasons.
  It never renders an empty card as though it were a card with no value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from typing import Any

from epl_betting_lab.config import OUTPUTS_DIR


STATUS_HTML_FILENAME = "status.html"

REPORT_FILES = {
    "model": "epl_model_task.json",
    "card": "epl_card_task.json",
    "settle": "epl_settle_preview_task.json",
    "automated_card": "automated_card.json",
    "comparison": "automated_card_comparison.json",
}


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _text(value: object) -> str:
    """Escape anything destined for the page. Report values are data."""
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _pill(label: str, tone: str) -> str:
    return f'<span class="pill {tone}">{_text(label)}</span>'


def _tone_for_ready(ready: bool) -> str:
    return "ok" if ready else "blocked"


def _market_pills(markets: Sequence[str], tone: str) -> str:
    if not markets:
        return '<span class="muted">none</span>'
    return "".join(_pill(market, tone) for market in markets)


def _picks_table(rows: Sequence[Mapping[str, Any]], empty_note: str) -> str:
    if not rows:
        return f'<p class="muted">{_text(empty_note)}</p>'
    cells = []
    for row in rows:
        prob = row.get("calibrated_model_prob")
        edge = row.get("calibrated_edge")
        units = row.get("suggested_units")
        cells.append(
            "<tr>"
            f"<td>{_text(row.get('home_team'))} v {_text(row.get('away_team'))}</td>"
            f"<td><code>{_text(row.get('market'))}</code></td>"
            f"<td>{_text(row.get('selection'))}</td>"
            f"<td>{_text(row.get('confidence_tier')) or '&mdash;'}</td>"
            f"<td class=\"num\">{f'{float(prob):.1%}' if isinstance(prob, (int, float)) else '&mdash;'}</td>"
            f"<td class=\"num\">{f'{float(edge):+.1%}' if isinstance(edge, (int, float)) else '&mdash;'}</td>"
            f"<td class=\"num\">{_text(row.get('american_odds')) or '&mdash;'}</td>"
            f"<td>{_text(row.get('book')) or '&mdash;'}</td>"
            f"<td class=\"num\">{_text(units) if units not in (None, '') else '&mdash;'}</td>"
            "</tr>"
        )
    return (
        '<div class="scroll"><table>'
        "<thead><tr><th>Match</th><th>Market</th><th>Selection</th><th>Tier</th>"
        "<th>Model</th><th>Edge</th><th>Price</th><th>Book</th><th>Units</th>"
        "</tr></thead><tbody>" + "".join(cells) + "</tbody></table></div>"
    )


def _list_block(items: Sequence[str], empty: str, tone: str = "") -> str:
    if not items:
        return f'<p class="muted">{_text(empty)}</p>'
    css = f' class="{tone}"' if tone else ""
    return "<ul>" + "".join(f"<li{css}>{_text(item)}</li>" for item in items) + "</ul>"


_STYLE = """
:root{--bg:#fbfbfd;--fg:#16181d;--muted:#6b7280;--card:#ffffff;--line:#e5e7eb;
--ok:#0f7b45;--ok-bg:#e6f5ec;--warn:#8a5a00;--warn-bg:#fdf3e0;
--blocked:#a3242c;--blocked-bg:#fbe9ea;--accent:#2b4c7e}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#0f1115;--fg:#e6e8ec;--muted:#9aa3b2;--card:#171a21;--line:#262b35;
--ok:#5cc98d;--ok-bg:#12301f;--warn:#e0b055;--warn-bg:#302612;
--blocked:#f08a90;--blocked-bg:#331a1c;--accent:#8ab0e8}}
:root[data-theme="dark"]{--bg:#0f1115;--fg:#e6e8ec;--muted:#9aa3b2;--card:#171a21;
--line:#262b35;--ok:#5cc98d;--ok-bg:#12301f;--warn:#e0b055;--warn-bg:#302612;
--blocked:#f08a90;--blocked-bg:#331a1c;--accent:#8ab0e8}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1rem 4rem;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1040px;margin:0 auto}
h1{font-size:1.6rem;margin:0 0 .25rem}
h2{font-size:1.15rem;margin:2rem 0 .75rem;padding-bottom:.35rem;
border-bottom:1px solid var(--line)}
h3{font-size:.95rem;margin:1.25rem 0 .5rem;color:var(--muted);
text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--muted);margin:0 0 1.5rem;font-size:.9rem}
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:1rem 1.1rem}
.card .label{color:var(--muted);font-size:.8rem;text-transform:uppercase;
letter-spacing:.06em;margin-bottom:.4rem}
.card .value{font-size:1.35rem;font-weight:600}
.pill{display:inline-block;padding:.15rem .55rem;border-radius:999px;
font-size:.82rem;font-weight:600;margin:0 .3rem .3rem 0}
.pill.ok{background:var(--ok-bg);color:var(--ok)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.blocked{background:var(--blocked-bg);color:var(--blocked)}
.muted{color:var(--muted)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem;min-width:640px}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:.78rem;text-transform:uppercase;
letter-spacing:.05em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
code{background:var(--card);border:1px solid var(--line);border-radius:5px;
padding:.05rem .3rem;font-size:.85em}
ul{margin:.4rem 0;padding-left:1.2rem}
li.blocked{color:var(--blocked)}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:8px;padding:.75rem 1rem;margin:1rem 0;font-size:.9rem}
footer{margin-top:3rem;color:var(--muted);font-size:.82rem}
"""


def build_status_html(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> str:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    reports = {key: _read(outputs / name) for key, name in REPORT_FILES.items()}
    model = reports["model"]
    card = reports["card"]
    settle = reports["settle"]
    generated = reports["automated_card"]

    model_ready = bool(model.get("epl_card_ready", False))
    card_ready = bool(card.get("card_ready", False))
    card_generated = bool(generated.get("card_generated", False))
    manual_required = bool(
        card.get("manual_odds_entry_required", model.get("manual_odds_entry_required", True))
    )

    included = [str(m) for m in (card.get("included_markets") or [])]
    excluded = [str(m) for m in (card.get("excluded_markets") or [])]

    blockers = [str(b) for b in (card.get("blockers") or [])]
    model_blockers = [str(b) for b in (model.get("blockers") or [])]

    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    head = [
        '<div class="wrap">',
        "<h1>EPL Betting Lab &mdash; status</h1>",
        f'<p class="sub">Generated {_text(stamp.strftime("%Y-%m-%d %H:%M UTC"))} '
        "&middot; recommendations only, no bet is ever placed</p>",
        '<div class="grid">',
        f'<div class="card"><div class="label">Model</div>'
        f'<div class="value">{_pill("Ready" if model_ready else "Blocked", _tone_for_ready(model_ready))}</div></div>',
        f'<div class="card"><div class="label">Card</div>'
        f'<div class="value">{_pill("Ready" if card_ready else "Blocked", _tone_for_ready(card_ready))}</div></div>',
        f'<div class="card"><div class="label">Manual odds entry</div>'
        f'<div class="value">{_pill("Not required" if not manual_required else "Required", _tone_for_ready(not manual_required))}</div></div>',
        f'<div class="card"><div class="label">Settlement</div>'
        f'<div class="value">{_pill(str(settle.get("mode") or "Preview only"), "ok")}</div></div>',
        "</div>",
    ]

    markets = [
        "<h2>Markets</h2>",
        "<h3>Included</h3>",
        _market_pills(included, "ok"),
        "<h3>Excluded</h3>",
        _market_pills(excluded, "warn"),
    ]
    for entry in generated.get("excluded_market_details", []) or []:
        if isinstance(entry, Mapping) and not entry.get("usable_for_picks", True):
            markets.append(
                f'<p class="muted"><code>{_text(entry.get("market"))}</code> '
                f"&mdash; {_text(entry.get('reason'))}</p>"
            )
    note = generated.get("exclusion_note") or card.get("excluded_markets_note")
    if note:
        markets.append(f'<div class="note">{_text(note)}</div>')

    if card_ready and card_generated:
        card_section = [
            "<h2>Card</h2>",
            "<h3>Best bets</h3>",
            _picks_table(card.get("best_bets") or [], "No best bets."),
            "<h3>Leans</h3>",
            _picks_table(card.get("leans") or [], "No leans."),
            "<h3>Passes and notable avoids</h3>",
            _picks_table(card.get("passes_or_avoids") or [], "No passes recorded."),
        ]
    else:
        card_section = [
            "<h2>Card</h2>",
            '<div class="note"><strong>No card was produced.</strong> '
            "This is a blocked card, not a card with no value: nothing was "
            "generated, so nothing is being withheld as a judgement.</div>",
            _list_block(blockers or model_blockers, "No blockers recorded.", "blocked"),
        ]

    blockers_section = [
        "<h2>Blockers</h2>",
        _list_block(
            blockers or model_blockers, "None. All tracked gates pass.", "blocked"
        ),
        "<h3>Next action</h3>",
        f'<p>{_text(card.get("next_action") or model.get("next_action") or "")}</p>',
    ]

    comparison = reports["comparison"]
    if comparison.get("comparable"):
        counts = {
            "Added": len(comparison.get("added") or []),
            "Removed": len(comparison.get("removed") or []),
            "Moved section": len(comparison.get("moved_section") or []),
            "Price moved": len(comparison.get("price_changed") or []),
            "Unchanged": comparison.get("unchanged_count", 0),
        }
        change_rows = "".join(
            f'<div class="card"><div class="label">{_text(label)}</div>'
            f'<div class="value">{_text(value)}</div></div>'
            for label, value in counts.items()
        )
        detail: list[str] = []
        for row in (comparison.get("price_changed") or [])[:8]:
            detail.append(
                f"<li>{_text(row.get('label'))}: "
                f"{_text(row.get('from_price'))} &rarr; {_text(row.get('to_price'))}</li>"
            )
        for row in (comparison.get("added") or [])[:8]:
            detail.append(f"<li>added &mdash; {_text(row.get('label'))}</li>")
        for row in (comparison.get("removed") or [])[:8]:
            detail.append(f"<li>removed &mdash; {_text(row.get('label'))}</li>")
        change_section = [
            "<h2>Since the previous card</h2>",
            f'<div class="grid">{change_rows}</div>',
            (
                "<ul>" + "".join(detail) + "</ul>"
                if detail
                else '<p class="muted">No selection or price changed.</p>'
            ),
            '<div class="note">A price that moved is not a pick that was '
            "dropped. The two are counted separately so they cannot be "
            "confused.</div>",
        ]
    else:
        change_section = [
            "<h2>Since the previous card</h2>",
            '<p class="muted">Not enough archived runs to compare yet.</p>',
        ]

    settle_section = [
        "<h2>Settlement preview</h2>",
        '<div class="grid">',
        f'<div class="card"><div class="label">Open bets</div>'
        f'<div class="value">{_text(settle.get("open_bet_count", 0))}</div></div>',
        f'<div class="card"><div class="label">Settled</div>'
        f'<div class="value">{_text(settle.get("settled_bet_count", 0))}</div></div>',
        f'<div class="card"><div class="label">Would settle</div>'
        f'<div class="value">{_text(settle.get("would_settle_count", 0))}</div></div>',
        "</div>",
        f'<div class="note">{_text(settle.get("preview_note") or "Preview only.")}</div>',
    ]

    footer = [
        "<footer>",
        "<p>Built from the routine reports in <code>data/outputs/</code>. "
        "No credential appears on this page. Bets are never placed and "
        "settlement is never applied.</p>",
        "</footer>",
        "</div>",
    ]

    body = "\n".join(
        head
        + markets
        + card_section
        + change_section
        + blockers_section
        + settle_section
        + footer
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>EPL Betting Lab — status</title>"
        f"<style>{_STYLE}</style></head><body>\n{body}\n</body></html>\n"
    )


def save_status_html(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    html = build_status_html(output_dir=outputs, now=now)
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / STATUS_HTML_FILENAME
    path.write_text(html, encoding="utf-8")
    return {"html": str(path), "bytes": len(html.encode("utf-8"))}
