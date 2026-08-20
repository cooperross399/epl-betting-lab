"""Per-market eligibility for the API-first card workflow.

The old workflow was all-or-nothing: one missing BTTS price blocked the entire
card, which forced manual odds entry. That is the wrong shape. A provider can
be completely trustworthy for 1X2 and simply not offer BTTS.

This module decides eligibility **per market** so the card can run on the
markets the provider actually covers while naming the rest explicitly.

Four states, and the distinction between them matters:

``eligible``
    Provider returned every required selection for every fixture in the
    selected window, and mapping/validation/freshness all pass. Usable.
``incomplete``
    Provider returned this market for some fixtures but not all. Not usable as
    a whole; the covered fixtures are reported but the market is excluded.
``unavailable``
    Provider returned no rows at all for this market (BTTS today). Not a
    price of zero, not a "no value" verdict — simply absent.
``disabled``
    Deliberately excluded from automated picks regardless of availability.

An excluded market is **never** a pass, a lean, or a no-value call. Nothing here
invents a price: absence stays absence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import pandas as pd

from epl_betting_lab.selected_slate import filter_to_selected_window


#: Required selections per supported market.
MARKET_SELECTIONS: dict[str, tuple[str, ...]] = {
    "1x2": ("home", "draw", "away"),
    "total_2_5": ("over", "under"),
    "btts": ("yes", "no"),
    # Both read off the same 1X2 distribution, so they need no new model and
    # cannot disagree with the 1X2 rows on the same card. See
    # strategies/derived_result.py for why draw-no-bet is conditional and why
    # these behave as underdog markets under the configured juice limit.
    "double_chance": ("home_or_draw", "draw_or_away", "home_or_away"),
    "draw_no_bet": ("home", "away"),
    # Corner markets, fitted on columns Football-Data already ships in the same
    # file as the scorelines. See models/poisson_counts.py.
    #
    # Card markets are modelled too and deliberately not listed here: a live
    # probe found no book offering cards in the `us` region, which is where
    # every account is. A price that cannot be taken is not a price. The model
    # stays so the market can be added the day one appears.
    #
    # Team totals are likewise absent, for a different reason: the book sets a
    # different line per team on the same fixture — Arsenal at 2.5 and Coventry
    # at 0.5 in the same market — so a fixed line in the market name can never
    # match. Supporting them needs line-aware selections, not another entry.
    "corners_1x2": ("home", "draw", "away"),
    "corners_total_9_5": ("over", "under"),
    "corners_total_10_5": ("over", "under"),
}

#: Markets intentionally excluded from automated picks regardless of coverage.
#:
#: BTTS was previously disabled here because the featured endpoint returns no
#: BTTS rows. Market discovery showed that was an endpoint limitation, not a
#: provider one: the per-event endpoint supplies BTTS for every Week 1 fixture,
#: and `--include-event-markets` now ingests it. BTTS is therefore no longer
#: disabled — it is judged on coverage like any other market.
DEFAULT_DISABLED_MARKETS: tuple[str, ...] = ()

#: Standing notes about why a market is excluded, beyond what this run's
#: coverage numbers show. Coverage says a market is incomplete; it cannot say
#: why, and a future session seeing "8 of 10 fixtures" would reasonably wonder
#: whether another region fixes it. This records that the question was asked
#: and answered, so the investigation is not repeated to a different conclusion.
MARKET_EXCLUSION_NOTES: dict[str, str] = {
    "total_2_5": (
        "Reopened 2026-08-19. The 2026-08-17 exclusion said the complete 2.5 "
        "line existed only at William Hill, Betsson and Nordic Bet, where "
        "there is no account. That was true of the bulk `totals` market, which "
        "is the only one that had been examined. It was never true of "
        "`alternate_totals`: BetRivers and FanDuel each carry 2.5 on all ten "
        "fixtures, and both already price rows on the card. The line was "
        "reachable the whole time, in a market nobody had looked at. The "
        "market is now sourced from there and awaits policy approval like any "
        "other."
    ),
}

ELIGIBLE = "eligible"
INCOMPLETE = "incomplete"
UNAVAILABLE = "unavailable"
DISABLED = "disabled"

MARKET_STATUSES = (ELIGIBLE, INCOMPLETE, UNAVAILABLE, DISABLED)


@dataclass(frozen=True)
class MarketEligibility:
    """Eligibility of one market, with the reason it is not usable if it isn't."""

    market: str
    status: str
    reason: str
    fixtures_expected: int = 0
    fixtures_covered: int = 0
    missing_fixtures: tuple[str, ...] = ()
    row_count: int = 0
    bookmaker_count: int = 0

    @property
    def usable(self) -> bool:
        return self.status == ELIGIBLE

    def as_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "status": self.status,
            "reason": self.reason,
            "usable_for_picks": self.usable,
            "fixtures_expected": self.fixtures_expected,
            "fixtures_covered": self.fixtures_covered,
            "missing_fixtures": list(self.missing_fixtures),
            "row_count": self.row_count,
            "bookmaker_count": self.bookmaker_count,
            "fabricated": False,
        }


@dataclass(frozen=True)
class EligibilityReport:
    """Whole-slate eligibility outcome."""

    markets: tuple[MarketEligibility, ...]
    gate_failures: tuple[str, ...] = ()
    fixtures_in_window: int = 0
    window_label: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def eligible_markets(self) -> tuple[str, ...]:
        return tuple(m.market for m in self.markets if m.status == ELIGIBLE)

    @property
    def excluded_markets(self) -> tuple[str, ...]:
        return tuple(m.market for m in self.markets if m.status != ELIGIBLE)

    @property
    def any_eligible(self) -> bool:
        return bool(self.eligible_markets)

    def by_status(self, status: str) -> tuple[str, ...]:
        return tuple(m.market for m in self.markets if m.status == status)

    def as_dict(self) -> dict[str, object]:
        return {
            "window_label": self.window_label,
            "fixtures_in_window": self.fixtures_in_window,
            "gate_failures": list(self.gate_failures),
            "eligible_markets": list(self.eligible_markets),
            "excluded_markets": list(self.excluded_markets),
            "unavailable_markets": list(self.by_status(UNAVAILABLE)),
            "incomplete_markets": list(self.by_status(INCOMPLETE)),
            "disabled_markets": list(self.by_status(DISABLED)),
            "any_market_eligible": self.any_eligible,
            "markets": [m.as_dict() for m in self.markets],
            "warnings": list(self.warnings),
            "note": (
                "Excluded markets are unavailable, incomplete, or deliberately "
                "disabled. They are never reported as passes or no-value calls, "
                "and no missing price was invented."
            ),
        }


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _fixture_label(row: Mapping[str, object]) -> str:
    return (
        f"{_clean(row.get('date'))}: {_clean(row.get('home_team'))} vs "
        f"{_clean(row.get('away_team'))}"
    )


def _fixture_ids(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
    if frame.empty:
        return set()
    return {
        (
            _clean(row.get("date")),
            _clean(row.get("home_team")).casefold(),
            _clean(row.get("away_team")).casefold(),
        )
        for _, row in frame.iterrows()
        if _clean(row.get("date")) and _clean(row.get("home_team"))
    }


def evaluate_market_eligibility(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
    *,
    mapping_verified: bool,
    validation_passed: bool,
    freshness_passed: bool,
    disabled_markets: Sequence[str] = DEFAULT_DISABLED_MARKETS,
    markets: Iterable[str] | None = None,
    window_label: str = "",
    restrict_to_window: bool = True,
) -> EligibilityReport:
    """Decide, per market, whether the automated card may use it.

    `odds` and `fixtures` are provider-derived frames. Gate failures
    (mapping/validation/freshness) disqualify every market at once, because
    those describe the bundle rather than a single market.
    """
    considered = tuple(markets) if markets is not None else tuple(MARKET_SELECTIONS)
    disabled = {m.strip().casefold() for m in disabled_markets}

    window_fixtures = (
        filter_to_selected_window(fixtures) if restrict_to_window else fixtures
    )
    window_odds = filter_to_selected_window(odds) if restrict_to_window else odds

    expected_ids = _fixture_ids(window_fixtures)
    labels = {
        (
            _clean(row.get("date")),
            _clean(row.get("home_team")).casefold(),
            _clean(row.get("away_team")).casefold(),
        ): _fixture_label(row)
        for _, row in window_fixtures.iterrows()
    }

    gate_failures: list[str] = []
    if not mapping_verified:
        gate_failures.append("Team mapping is not verified.")
    if not validation_passed:
        gate_failures.append("Staging validation did not pass.")
    if not freshness_passed:
        gate_failures.append("Provider run freshness did not pass.")

    results: list[MarketEligibility] = []
    for market in considered:
        selections = MARKET_SELECTIONS.get(market, ())
        if market in window_odds.get("market", pd.Series(dtype=str)).astype(str).str.strip().str.casefold().values:
            market_rows = window_odds[
                window_odds["market"].astype(str).str.strip().str.casefold() == market
            ]
        else:
            market_rows = window_odds.iloc[0:0]

        row_count = int(len(market_rows))
        book_count = (
            int(market_rows["book"].nunique()) if "book" in market_rows.columns else 0
        )

        # A fixture is covered only when every required selection is present.
        covered_ids: set[tuple[str, str, str]] = set()
        if row_count and selections:
            for fixture_id in expected_ids:
                subset = market_rows[
                    (market_rows["date"].astype(str).str.strip() == fixture_id[0])
                    & (
                        market_rows["home_team"].astype(str).str.strip().str.casefold()
                        == fixture_id[1]
                    )
                    & (
                        market_rows["away_team"].astype(str).str.strip().str.casefold()
                        == fixture_id[2]
                    )
                ]
                present = {
                    _clean(value).casefold()
                    for value in subset.get("selection", pd.Series(dtype=str))
                }
                if set(selections).issubset(present):
                    covered_ids.add(fixture_id)

        missing_ids = sorted(expected_ids - covered_ids)
        missing_labels = tuple(labels.get(item, str(item)) for item in missing_ids)

        if market in disabled:
            status = DISABLED
            reason = (
                f"`{market}` is deliberately disabled for automated picks. "
                "It is excluded, not treated as a pass or a no-value call."
            )
        elif row_count == 0:
            status = UNAVAILABLE
            reason = (
                f"The provider returned no `{market}` rows. The market is "
                "unavailable; no price was invented and none is required "
                "manually."
            )
        elif gate_failures:
            status = INCOMPLETE
            reason = "Bundle-level gate failed: " + " ".join(gate_failures)
        elif not expected_ids:
            status = INCOMPLETE
            reason = "No fixtures were found inside the selected window."
        elif missing_ids:
            status = INCOMPLETE
            reason = (
                f"`{market}` covers {len(covered_ids)} of {len(expected_ids)} "
                "fixtures in the selected window. The market is excluded rather "
                "than partially used."
            )
        else:
            status = ELIGIBLE
            reason = (
                f"`{market}` covers all {len(expected_ids)} fixtures in the "
                "selected window with passing mapping, validation, and freshness."
            )

        standing_note = MARKET_EXCLUSION_NOTES.get(market, "")
        if standing_note and status != ELIGIBLE:
            reason = f"{reason} {standing_note}"

        results.append(
            MarketEligibility(
                market=market,
                status=status,
                reason=reason,
                fixtures_expected=len(expected_ids),
                fixtures_covered=len(covered_ids),
                missing_fixtures=missing_labels,
                row_count=row_count,
                bookmaker_count=book_count,
            )
        )

    warnings: list[str] = []
    unavailable = [m.market for m in results if m.status == UNAVAILABLE]
    if unavailable:
        warnings.append(
            "Unavailable market(s): "
            + ", ".join(unavailable)
            + ". Excluded from automated picks; no manual entry required and no "
            "price fabricated."
        )
    incomplete = [m.market for m in results if m.status == INCOMPLETE]
    if incomplete:
        warnings.append(
            "Incomplete market(s): "
            + ", ".join(incomplete)
            + ". Excluded from automated picks rather than used for a subset of "
            "fixtures."
        )

    return EligibilityReport(
        markets=tuple(results),
        gate_failures=tuple(gate_failures),
        fixtures_in_window=len(expected_ids),
        window_label=window_label,
        warnings=tuple(warnings),
    )
