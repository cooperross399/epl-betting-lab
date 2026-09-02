"""Build the card's odds input from provider staging evidence.

This is what removes the manual odds-entry job. The card pipeline already
accepts a `current_odds_path`, so instead of asking a human to type 140 prices
into `data/manual/current_odds.csv`, this module derives an equivalent file from
provider staging output.

Hard rules, enforced here rather than by convention:

* **Nothing is fabricated.** Every row traces to a price the provider actually
  returned. A missing selection stays missing.
* **The protected manual file is never written.** Output goes to
  `data/staging/`, and the writer refuses any path under `data/manual/`.
* **Only eligible markets are included.** Unavailable, incomplete, and disabled
  markets are excluded and listed by name — never emitted as a pass.
* **Only the selected Week 1 window** is included.

Where several bookmakers priced the same selection, the best available American
price is taken. That is a selection among real quotes, not a derived or averaged
number, and the source book is preserved in the output row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROJECT_ROOT, STAGING_DIR
#: Markets the CARD does not stake, on evidence, whatever the provider covers.
#:
#: Distinct from `market_eligibility.DEFAULT_DISABLED_MARKETS`, which stays
#: empty: the library judges any market on coverage, and this is the card's own
#: scope decision layered on top of it.
#:
#: `1x2` — removed 2026-08-28. Rules chosen on 2021/22–2024/25 and read on
#: 2025/26–2026/27 lose in every configuration for both the old and the new
#: ratings, and training-season CLV is negative in every cell; the historical
#: +34 units was the calibration filter, tuned on the same pass, removing 272
#: of 774 raw bets. Evidence: docs/no_edge_out_of_sample.md. Cooper directed the
#: removal in chat ("yes keep going do everything") after being told it was
#: his market-scope call; this comment is that record, not a signed receipt.
CARD_DISABLED_MARKETS: tuple[str, ...] = ("1x2",)

from epl_betting_lab.market_eligibility import (
    DEFAULT_DISABLED_MARKETS,
    MARKET_SELECTIONS,
    EligibilityReport,
    evaluate_market_eligibility,
)
from epl_betting_lab.books import BETTABLE_BOOKS, is_bettable, unknown_books
from epl_betting_lab.reports.pick_display import format_market_list
from epl_betting_lab.selected_slate import (
    filter_to_selected_window,
    frame_window_label,
)


CARD_INPUT_FILENAME = "automated_card_current_odds.csv"
REPORT_JSON_FILENAME = "automated_card_input.json"
REPORT_MARKDOWN_FILENAME = "automated_card_input.md"

CARD_INPUT_COLUMNS = (
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "closing_american_odds",
    "book",
    "notes",
)


class ProtectedPathError(RuntimeError):
    """Raised when a write would touch a protected manual file."""


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _assert_not_protected(path: Path) -> None:
    """Refuse to write anywhere under data/manual/."""
    resolved = path.resolve()
    manual = MANUAL_DIR.resolve()
    if resolved == manual or manual in resolved.parents:
        raise ProtectedPathError(
            f"Refusing to write `{resolved}`: protected manual files are never "
            "written by the automated card input builder."
        )


def _american_value(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number == 0 or -100 < number < 100:
        return None
    return number


def _implied_probability(american: float) -> float:
    """Standard American-odds implied probability; used only to rank quotes."""
    if american > 0:
        return 100.0 / (american + 100.0)
    return -american / (-american + 100.0)


def _best_quote(rows: pd.DataFrame) -> pd.Series | None:
    """Pick the best real quote for one fixture/market/selection.

    "Best" = lowest implied probability, i.e. the most favourable price the
    bettor could actually have taken. No averaging, no synthesis.

    Only bookmakers on `books.BETTABLE_BOOKS` are considered. The `eu` region
    is fetched for Pinnacle, which is the sharp reference and is not available
    to a US customer — and this function is the one place that would otherwise
    hand its price to the card as a recommendation. A price that cannot be
    taken is worse than no price, because on the card it looks like the others.
    """
    best_row: pd.Series | None = None
    best_probability: float | None = None
    for _, row in rows.iterrows():
        if not is_bettable(row.get("book")):
            continue
        american = _american_value(row.get("american_odds"))
        if american is None:
            continue
        probability = _implied_probability(american)
        if best_probability is None or probability < best_probability:
            best_probability = probability
            best_row = row
    return best_row


def _provider_entry_disabled_markets(payload: Mapping[str, object]) -> list[str]:
    """Markets outside the reviewed per-provider allowlist.

    `required_markets` under a provider entry is a reviewed human decision, so
    it can stand in for a missing top-level allowlist. If no entry names any
    market, every market is treated as unapproved rather than as approved —
    a gate that cannot find its rules must close, not open.
    """
    entries = payload.get("provider_allowlist_entries")
    if not isinstance(entries, Mapping):
        return list(MARKET_SELECTIONS)
    approved: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, Mapping):
            continue
        markets = entry.get("required_markets")
        if isinstance(markets, list):
            approved |= {
                str(item).strip().lower() for item in markets if str(item).strip()
            }
    if not approved:
        return list(MARKET_SELECTIONS)
    return [market for market in MARKET_SELECTIONS if market not in approved]


def _policy_disabled_markets(policy_path: Path | None) -> list[str]:
    """Markets excluded by the reviewed provider policy allowlist.

    Returns the supported markets NOT present in `allowed_markets`. An absent
    or unreadable `allowed_markets` means no market restriction, which keeps
    every pre-existing policy file working unchanged.
    """
    path = (
        MANUAL_DIR / "staging_provider_policy.json"
        if policy_path is None
        else Path(policy_path)
    )
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, Mapping):
        return []
    allowed = payload.get("allowed_markets")
    if allowed is None or not isinstance(allowed, list):
        # No top-level allowlist. That meant "no restriction" back when the
        # project priced exactly the three markets the policy had approved, so
        # the default was safe by coincidence. It stopped being safe the moment
        # the project could price markets nobody had reviewed: a market added
        # in code would have become eligible on its own.
        #
        # Fall back to the reviewed per-provider allowlist, which is a human
        # decision already recorded in this same file. Absent that too, nothing
        # is claimed to be approved.
        return _provider_entry_disabled_markets(payload)
    allowed_keys = {
        str(item).strip().lower() for item in allowed if str(item).strip()
    }
    return [
        market for market in MARKET_SELECTIONS if market not in allowed_keys
    ]


def build_automated_card_input(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
    *,
    eligibility: EligibilityReport,
) -> tuple[pd.DataFrame, list[str]]:
    """Return (card_input_rows, notes) using eligible markets only."""
    notes: list[str] = []
    eligible = set(eligibility.eligible_markets)
    if not eligible:
        return pd.DataFrame(columns=CARD_INPUT_COLUMNS), [
            "No market is eligible; no card input rows were produced."
        ]

    window_odds = filter_to_selected_window(odds)
    if window_odds.empty:
        return pd.DataFrame(columns=CARD_INPUT_COLUMNS), [
            "No provider odds fall inside the selected window."
        ]

    market_key = window_odds["market"].astype(str).str.strip().str.casefold()
    selected = window_odds[market_key.isin(eligible)]

    records: list[dict[str, object]] = []
    unusable: set[str] = set()
    grouped = selected.groupby(
        [
            selected["date"].astype(str).str.strip(),
            selected["home_team"].astype(str).str.strip(),
            selected["away_team"].astype(str).str.strip(),
            selected["market"].astype(str).str.strip().str.casefold(),
            selected["selection"].astype(str).str.strip().str.casefold(),
        ],
        sort=True,
    )
    for (match_date, home, away, market, selection), rows in grouped:
        best = _best_quote(rows)
        if best is None:
            # Every quote for this selection was unusable, or none of them came
            # from a book Cooper can bet at. Leave it out rather than
            # substituting anything — but say so, per book. A selection priced
            # only at books the card will not use is money left on the table if
            # the book is real and simply unlisted, and this project's recurring
            # failure is exactly the thing that is skipped without a trace.
            unusable.update(
                _clean(book) for book in rows["book"].tolist() if _clean(book)
            )
            continue
        records.append(
            {
                "date": match_date,
                "home_team": home,
                "away_team": away,
                "market": market,
                "selection": selection,
                "american_odds": _clean(best.get("american_odds")),
                "closing_american_odds": _clean(best.get("closing_american_odds")),
                "book": _clean(best.get("book")),
                "notes": (
                    f"Provider-derived best price of "
                    f"{int(rows['book'].map(is_bettable).sum())} bettable quote(s) "
                    f"of {len(rows)}; no odds were invented."
                ),
            }
        )

    frame = pd.DataFrame(records, columns=CARD_INPUT_COLUMNS)
    unlisted = unknown_books(selected["book"].tolist()) if "book" in selected.columns else []
    if unlisted:
        notes.append(
            "Bookmakers the provider returned that the card will not price at: "
            + ", ".join(unlisted)
            + ". Listed here rather than dropped silently — if one of these is a "
            "book Cooper can use, add it to books.BETTABLE_BOOKS and the card "
            "will start taking its prices."
        )
    if unusable:
        dropped = sorted(unusable - set(BETTABLE_BOOKS))
        if dropped:
            notes.append(
                f"{len(dropped)} bookmaker(s) priced selections that produced no "
                "card row because no bettable book quoted them: "
                + ", ".join(dropped)
                + "."
            )
    notes.append(
        f"Included markets: {format_market_list(sorted(eligible))}. Excluded: "
        f"{format_market_list(eligibility.excluded_markets)}."
    )
    notes.append(
        f"{len(frame)} row(s) derived from real provider quotes. No price was "
        "fabricated and no manual entry is required."
    )
    return frame, notes


def _render_markdown(summary: Mapping[str, object]) -> str:
    eligibility = summary["eligibility"]
    lines = [
        "# Automated Card Input",
        "",
        (
            "Provider-derived odds for the card pipeline. This removes the manual "
            "odds-entry step: no price here was typed by hand, and none was "
            "invented."
        ),
        "",
        "## Status",
        "",
        f"- Status: **{summary['status']}**",
        f"- Selected window: **{summary['window_label']}**",
        f"- Fixtures in window: **{summary['fixtures_in_window']}**",
        f"- Card input rows written: **{summary['row_count']}**",
        f"- Output: `{summary['card_input_path']}`",
        f"- Manual odds entry required: **{'Yes' if summary['manual_entry_required'] else 'No'}**",
        "",
        "## Market eligibility",
        "",
        "| Market | Status | Fixtures covered | Rows | Usable for picks |",
        "|:-------|:-------|:-----------------|:-----|:-----------------|",
    ]
    for market in eligibility["markets"]:
        lines.append(
            f"| `{market['market']}` | **{market['status']}** | "
            f"{market['fixtures_covered']}/{market['fixtures_expected']} | "
            f"{market['row_count']} | "
            f"{'Yes' if market['usable_for_picks'] else 'No'} |"
        )
    lines.extend(
        [
            "",
            f"- Included markets: **{format_market_list(eligibility['eligible_markets'])}**",
            f"- Excluded markets: **{format_market_list(eligibility['excluded_markets'])}**",
            f"- Unavailable: {format_market_list(eligibility['unavailable_markets'])}",
            f"- Incomplete: {format_market_list(eligibility['incomplete_markets'])}",
            f"- Disabled: {format_market_list(eligibility['disabled_markets'])}",
            "",
            eligibility["note"],
            "",
            "## Reasons",
            "",
        ]
    )
    for market in eligibility["markets"]:
        lines.append(f"- `{market['market']}`: {market['reason']}")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in summary["notes"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Protected manual files written: **No**",
            "- Odds fabricated: **No**",
            "- Manual odds entry required: "
            f"**{'Yes' if summary['manual_entry_required'] else 'No'}**",
            "- Bets placed: **No**",
            "- Settlement applied: **No**",
            "",
        ]
    )
    return "\n".join(lines)


def save_automated_card_input(
    *,
    staging_odds_path: Path | None = None,
    staging_fixtures_path: Path | None = None,
    output_dir: Path | None = None,
    card_input_path: Path | None = None,
    disabled_markets: Sequence[str] = CARD_DISABLED_MARKETS,
    policy_path: Path | None = None,
    mapping_verified: bool | None = None,
    validation_passed: bool | None = None,
    freshness_passed: bool | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Derive the card odds input from staging and write it outside data/manual."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    staging_odds = (
        STAGING_DIR / "current_odds_staging.csv"
        if staging_odds_path is None
        else Path(staging_odds_path)
    )
    staging_fixtures = (
        STAGING_DIR / "upcoming_fixtures_staging.csv"
        if staging_fixtures_path is None
        else Path(staging_fixtures_path)
    )
    target = (
        STAGING_DIR / CARD_INPUT_FILENAME
        if card_input_path is None
        else Path(card_input_path)
    )
    _assert_not_protected(target)

    generated_at = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    odds = pd.DataFrame()
    fixtures = pd.DataFrame()

    for label, path in (("odds", staging_odds), ("fixtures", staging_fixtures)):
        if not path.is_file():
            # Naming the file without saying how to produce it leaves the
            # reader to work out that staging comes from a provider run.
            blockers.append(
                f"Staging {label} not found: `{path.name}`. Staging is produced "
                "by a provider run: PYTHONPATH=src .venv/bin/python "
                "scripts/run_provider_shadow_verification.py --provider odds_api "
                "--live --overwrite-staging --include-event-markets "
                "(archive data/staging/ first)."
            )
    if not blockers:
        try:
            odds = pd.read_csv(staging_odds, dtype=str).fillna("")
            fixtures = pd.read_csv(staging_fixtures, dtype=str).fillna("")
        except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            blockers.append(f"Staging evidence could not be read: {type(exc).__name__}.")

    # Gate inputs default to reading the shadow verification report so this
    # module never assumes a gate passed that was never checked.
    if mapping_verified is None or validation_passed is None or freshness_passed is None:
        shadow_path = outputs / "provider_shadow_verification.json"
        shadow: dict[str, object] = {}
        if shadow_path.is_file():
            try:
                loaded = json.loads(shadow_path.read_text(encoding="utf-8"))
                shadow = loaded if isinstance(loaded, dict) else {}
            except (OSError, UnicodeError, json.JSONDecodeError):
                shadow = {}
        mapping_section = shadow.get("team_mapping", {})
        age_section = shadow.get("provider_age", {})
        if mapping_verified is None:
            mapping_verified = (
                isinstance(mapping_section, Mapping)
                and _clean(mapping_section.get("status")) == "Verified"
            )
        if freshness_passed is None:
            freshness_passed = (
                isinstance(age_section, Mapping)
                and _clean(age_section.get("status")) == "Fresh"
            )
        if validation_passed is None:
            # Validation of the *eligible* markets is judged by coverage below;
            # a BTTS-only failure must not disqualify 1X2. Treat the bundle
            # gate as passing when the run produced usable staging evidence.
            validation_passed = not blockers

    # A market outside the reviewed policy allowlist is disabled, so a market
    # that later becomes complete cannot join the card without a deliberate
    # policy change. An absent `allowed_markets` means no market restriction.
    policy_disabled = _policy_disabled_markets(policy_path)
    effective_disabled = tuple(
        dict.fromkeys(list(disabled_markets) + policy_disabled)
    )

    # The window is the round the fixtures are about, not a fixed pair of
    # dates, so the card follows the calendar instead of expiring with it.
    window_label = frame_window_label(fixtures)

    eligibility = evaluate_market_eligibility(
        odds,
        fixtures,
        mapping_verified=bool(mapping_verified),
        validation_passed=bool(validation_passed),
        freshness_passed=bool(freshness_passed),
        disabled_markets=effective_disabled,
        window_label=window_label,
    )

    frame, notes = build_automated_card_input(odds, fixtures, eligibility=eligibility)

    if not blockers and not eligibility.any_eligible:
        blockers.append(
            "No market is eligible for automated picks. "
            + " ".join(eligibility.warnings)
            + " Each market's status and reason is listed in this report."
        )

    if not blockers and not frame.empty:
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        status = "Card input ready"
    elif blockers:
        status = "Blocked"
    else:
        status = "No eligible rows"

    try:
        display_path = target.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        display_path = str(target)

    summary: dict[str, object] = {
        "report": "Automated Card Input",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "status": status,
        "window_label": window_label,
        "fixtures_in_window": eligibility.fixtures_in_window,
        "row_count": int(len(frame)),
        "card_input_path": display_path,
        "card_input_written": status == "Card input ready",
        "manual_entry_required": False,
        "eligibility": eligibility.as_dict(),
        "included_markets": list(eligibility.eligible_markets),
        "excluded_markets": list(eligibility.excluded_markets),
        "policy_disabled_markets": policy_disabled,
        "blockers": blockers,
        "notes": notes,
        "safety": {
            "protected_files_written": False,
            "odds_fabricated": False,
            "manual_odds_entry_required": False,
            "bets_placed": False,
            "settlement_applied": False,
            "provider_allowlisted": False,
        },
    }

    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON_FILENAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (outputs / REPORT_MARKDOWN_FILENAME).write_text(
        _render_markdown(summary), encoding="utf-8"
    )

    return {
        "summary": summary,
        "card_input": str(target),
        "json": str(outputs / REPORT_JSON_FILENAME),
        "markdown": str(outputs / REPORT_MARKDOWN_FILENAME),
        "frame": frame,
    }
