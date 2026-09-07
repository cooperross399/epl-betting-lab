"""The upcoming slate is fetched, not typed, and never silently erased."""

from __future__ import annotations

from datetime import date

import pytest

from epl_betting_lab.data.fetch_fixtures import (
    FixturesUnavailable,
    NoUpcomingFixtures,
    parse_fixtures,
)


HEADER = b"Div,Date,Time,HomeTeam,AwayTeam,Referee\n"
FEED = HEADER + (
    b"B1,28/08/2026,19:45,Genk,Beveren,\n"
    b"E0,28/08/2026,20:00,Crystal Palace,Man City,A Madley\n"
    b"E0,29/08/2026,12:30,Liverpool,Nott'm Forest,S Barrott\n"
    b"E0,31/08/2026,20:00,Aston Villa,Arsenal,J Gillett\n"
    b"E0,24/08/2026,20:00,Fulham,Chelsea,M Oliver\n"
)


def test_only_the_english_top_flight_is_kept() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert set(fixtures["home_team"]) == {"Crystal Palace", "Liverpool", "Aston Villa"}
    assert "Genk" not in set(fixtures["home_team"])


def test_finished_fixtures_are_dropped() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert "Fulham" not in set(fixtures["home_team"])
    assert fixtures["date"].tolist() == ["2026-08-28", "2026-08-29", "2026-08-31"]


def test_dates_are_read_day_first() -> None:
    """Football-Data writes DD/MM/YYYY.

    Left to infer, pandas reads 03/08/2026 as March and moves the fixture five
    months — into a window nothing will ever select.
    """
    feed = HEADER + b"E0,03/08/2026,15:00,Arsenal,Chelsea,\n"

    fixtures = parse_fixtures(feed, today=date(2026, 8, 1))

    assert fixtures["date"].tolist() == ["2026-08-03"]


def test_the_shape_matches_what_the_card_reads() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert list(fixtures.columns) == ["date", "home_team", "away_team", "notes"]


def test_an_html_redirect_page_is_not_parsed_as_fixtures() -> None:
    """Football-Data answers some requests with a page, not a 404."""
    with pytest.raises(FixturesUnavailable):
        parse_fixtures(b"<html><body>Not here</body></html>", today=date(2026, 8, 28))


def test_a_feed_with_nothing_upcoming_refuses_rather_than_emptying_the_slate() -> None:
    """An empty result written over the file would erase the slate.

    That is the failure this module exists to end, so it is raised rather than
    returned and the caller keeps the previous slate.
    """
    with pytest.raises(NoUpcomingFixtures) as caught:
        parse_fixtures(FEED, today=date(2027, 1, 1))
    # ...but it is a quiet week, not a broken feed: the script must treat it
    # as nothing to do, never as a degradation.
    assert isinstance(caught.value, FixturesUnavailable)


def test_an_empty_week_is_not_a_failure_for_the_script(tmp_path, monkeypatch, capsys):
    import importlib.util, sys
    from pathlib import Path as _P
    from epl_betting_lab.data import fetch_fixtures as mod
    spec = importlib.util.spec_from_file_location("refresh_upcoming_fixtures", _P("scripts/refresh_upcoming_fixtures.py"))
    script = importlib.util.module_from_spec(spec); spec.loader.exec_module(script)

    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-09-04,A,B,\n", encoding="utf-8")
    def quiet(): raise mod.NoUpcomingFixtures("quiet week")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", quiet)
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate)])
    assert script.main() == 0
    assert "stands" in capsys.readouterr().out
    assert slate.read_text(encoding="utf-8").count("\n") == 2


def _script():
    import importlib.util
    from pathlib import Path as _P
    spec = importlib.util.spec_from_file_location("refresh_upcoming_fixtures", _P("scripts/refresh_upcoming_fixtures.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_a_quiet_feed_falls_back_to_the_provider_slate_so_the_card_is_not_blocked(tmp_path, monkeypatch):
    """On 2026-09-01 the feed was empty and a fresh runner kept the committed
    slate — weeks old — so every odds row failed `fixture_not_found` and no
    card was built. The provider's staged fixtures were on hand the whole time."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2020-01-01,Old,Match\n2099-09-04,Arsenal,Chelsea\n2099-09-05,Leeds,Hull\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-08-21,Stale,Slate,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.NoUpcomingFixtures("quiet")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged)])

    assert script.main() == 0
    written = slate.read_text(encoding="utf-8")
    assert "Arsenal,Chelsea" in written and "Leeds,Hull" in written
    assert "Stale" not in written and "Old,Match" not in written
    assert "from provider staging" in written


def test_without_any_staged_fixtures_the_previous_slate_stands(tmp_path, monkeypatch):
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-09-04,A,B,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.NoUpcomingFixtures("quiet")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(tmp_path / "missing.csv")])
    assert script.main() == 0
    assert "2026-09-04,A,B" in slate.read_text(encoding="utf-8")



def test_an_outage_falls_back_to_the_provider_slate_but_stays_degraded(tmp_path, monkeypatch):
    """On 2026-09-07 Football-Data answered 503 on both endpoints. The fallback
    added after 2026-09-01 was wired to the quiet-week branch only, so the
    outage walked straight past ten correct staged fixtures and the card was
    blocked with 160 `fixture_not_found` rows.

    Rescuing the slate must not also hide the outage: the exit code stays
    non-zero so the run summary keeps reporting a degraded run."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2020-01-01,Old,Match\n2099-09-04,Arsenal,Chelsea\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-08-21,Stale,Slate,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.FixturesUnavailable("503")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged)])

    assert script.main() == script.EXIT_RESCUED_FROM_STAGING, "an outage is a degradation even when the slate is rescued"
    assert script.EXIT_RESCUED_FROM_STAGING != 0
    written = slate.read_text(encoding="utf-8")
    assert "Arsenal,Chelsea" in written
    assert "Stale" not in written and "Old,Match" not in written


def test_a_slate_rescued_from_an_outage_says_so_and_not_that_the_feed_was_empty(tmp_path, monkeypatch):
    """Two failures now reach the staging fallback. A slate that names the
    wrong one misreports its own provenance."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2099-09-04,Arsenal,Chelsea\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.FixturesUnavailable("503")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged)])

    assert script.main() == script.EXIT_RESCUED_FROM_STAGING
    written = slate.read_text(encoding="utf-8")
    assert "from provider staging: Football-Data was unreachable" in written
    assert "listed no upcoming fixture" not in written


def test_a_quiet_week_still_reports_the_feed_listed_nothing(tmp_path, monkeypatch):
    """The default reason must not have drifted onto the outage wording."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2099-09-04,Arsenal,Chelsea\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.NoUpcomingFixtures("quiet")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged)])

    assert script.main() == 0
    assert "from provider staging: Football-Data listed no upcoming fixture" in slate.read_text(encoding="utf-8")


def test_an_outage_with_no_staging_behaves_exactly_as_before(tmp_path, monkeypatch, capsys):
    """The first invocation on a fresh runner: staging does not exist yet
    because no quota has been spent. The fallback must do nothing at all."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-09-04,A,B,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.FixturesUnavailable("503")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(tmp_path / "missing.csv")])

    assert script.main() == 1
    assert "was left in place" in capsys.readouterr().out
    assert slate.read_text(encoding="utf-8") == "date,home_team,away_team,notes\n2026-09-04,A,B,\n"


def test_an_outage_whose_staging_holds_nothing_upcoming_leaves_the_slate(tmp_path, monkeypatch):
    """Staging exists but every fixture in it has already been played — the
    same fact as no staging at all, and it must not overwrite the slate."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2020-01-01,Old,Match\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-09-04,A,B,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.FixturesUnavailable("503")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged)])

    assert script.main() == 1
    assert slate.read_text(encoding="utf-8") == "date,home_team,away_team,notes\n2026-09-04,A,B,\n"


def test_a_dry_run_during_an_outage_writes_nothing(tmp_path, monkeypatch, capsys):
    """The rescue path is a second write path, so it needs the dry-run guard
    the shared one has, or `--dry-run` quietly stops being a dry run."""
    import sys
    from epl_betting_lab.data import fetch_fixtures as mod
    script = _script()
    staged = tmp_path / "upcoming_fixtures_staging.csv"
    staged.write_text("date,home_team,away_team\n2099-09-04,Arsenal,Chelsea\n", encoding="utf-8")
    slate = tmp_path / "upcoming_fixtures.csv"
    slate.write_text("date,home_team,away_team,notes\n2026-09-04,A,B,\n", encoding="utf-8")
    monkeypatch.setattr(script, "fetch_upcoming_fixtures", lambda: (_ for _ in ()).throw(mod.FixturesUnavailable("503")))
    monkeypatch.setattr(sys, "argv", ["refresh", "--path", str(slate), "--staging-fixtures", str(staged), "--dry-run"])

    assert script.main() == script.EXIT_RESCUED_FROM_STAGING
    assert "Dry run" in capsys.readouterr().out
    assert slate.read_text(encoding="utf-8") == "date,home_team,away_team,notes\n2026-09-04,A,B,\n"


def test_a_rescued_slate_and_a_stale_one_do_not_share_an_exit_code():
    """Both are degraded, but the run summary has to say which fixtures the
    card ended up about, and the workflow reads that from the code alone."""
    script = _script()
    assert script.EXIT_RESCUED_FROM_STAGING not in (0, 1), (
        "0 would hide the outage; 1 is the code for a slate that was NOT rescued"
    )
    assert script.EXIT_RESCUED_FROM_STAGING != 2, "argparse exits 2 on a usage error"
