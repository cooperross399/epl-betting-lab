from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.github_runner_inputs import (
    build_github_runner_input_handoff,
    save_github_runner_input_handoff,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
MARKETS = [
    ("1x2", "home", -110),
    ("1x2", "draw", 240),
    ("1x2", "away", 225),
    ("total_2_5", "over", -105),
    ("total_2_5", "under", -115),
    ("btts", "yes", 105),
    ("btts", "no", -125),
]


def _write_inputs(
    root: Path,
    *,
    fixture_dates: tuple[str, ...] = ("2026-08-08",),
    include_markets: tuple[tuple[str, str, int], ...] | None = None,
) -> dict[str, Path]:
    manual = root / "data" / "manual"
    processed = root / "data" / "processed"
    output = root / "data" / "outputs"
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)

    fixtures_rows = []
    odds_rows = []
    markets = list(include_markets) if include_markets is not None else MARKETS
    for index, fixture_date in enumerate(fixture_dates):
        home = f"Home {index + 1}"
        away = f"Away {index + 1}"
        fixtures_rows.append(
            {"date": fixture_date, "home_team": home, "away_team": away}
        )
        for market, selection, american_odds in markets:
            odds_rows.append(
                {
                    "date": fixture_date,
                    "home_team": home,
                    "away_team": away,
                    "market": market,
                    "selection": selection,
                    "american_odds": american_odds,
                    "closing_american_odds": "",
                    "book": "Example Book",
                    "notes": "",
                }
            )

    fixtures = manual / "upcoming_fixtures.csv"
    odds = manual / "current_odds.csv"
    matches = processed / "epl_historical_matches.csv"
    pd.DataFrame(fixtures_rows).to_csv(fixtures, index=False)
    pd.DataFrame(odds_rows).to_csv(odds, index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "home_team": "Home 1",
                "away_team": "Away 1",
                "home_goals": 1,
                "away_goals": 0,
            }
        ]
    ).to_csv(matches, index=False)
    return {
        "current_odds_path": odds,
        "fixtures_path": fixtures,
        "matches_path": matches,
        "output_dir": output,
    }


def _build(root: Path, paths: dict[str, Path], **kwargs) -> dict[str, object]:
    return build_github_runner_input_handoff(
        current_odds_path=paths["current_odds_path"],
        fixtures_path=paths["fixtures_path"],
        matches_path=paths["matches_path"],
        run_at=RUN_AT,
        repository_root=root,
        **kwargs,
    )


def test_runner_handoff_records_valid_committed_inputs_and_allows_card(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)

    result = _build(
        tmp_path,
        paths,
        github_ref="refs/heads/weekly-odds",
        github_sha="abc123",
    )

    assert result["status"] == "Warnings only"
    assert result["card_generation_allowed"] is True
    assert result["current_odds_path"] == "data/manual/current_odds.csv"
    assert result["fixtures_path"] == "data/manual/upcoming_fixtures.csv"
    assert len(str(result["current_odds_checksum_sha256"])) == 64
    assert result["current_odds_checksum_status"] == "Recorded"
    assert result["current_odds_freshness_status"] == "Fresh"
    assert result["fixtures_freshness_status"] == "Fresh"
    assert result["validation_status"] == "Ready"
    assert result["validation_serious_issue_count"] == 0
    assert result["completeness_status"] == "Complete"
    assert result["completion_percentage"] == 1.0
    assert result["github_ref"] == "refs/heads/weekly-odds"
    assert result["github_sha"] == "abc123"


def test_runner_handoff_blocks_any_odds_rows_tied_to_past_matches(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(
        tmp_path,
        fixture_dates=("2026-08-05", "2026-08-08"),
    )

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["card_generation_allowed"] is False
    assert result["current_odds_past_rows"] == 7
    assert result["current_odds_today_or_future_rows"] == 7
    assert any("tied to past matches" in item for item in result["blockers"])


def test_runner_handoff_blocks_past_fixture_rows(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        fixture_dates=("2026-08-05", "2026-08-08"),
    )

    result = _build(tmp_path, paths)

    assert result["fixtures_past_rows"] == 1
    assert result["card_generation_allowed"] is False
    assert any("past match row" in item for item in result["blockers"])


def test_runner_handoff_blocks_incomplete_expected_market_rows(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(
        tmp_path,
        include_markets=tuple(MARKETS[:3]),
    )

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["completeness_status"] == "Blocked"
    assert result["completion_percentage"] < 1.0
    assert result["incomplete_match_count"] == 1
    assert result["card_generation_allowed"] is False


def test_runner_handoff_blocks_missing_current_odds_file(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    paths["current_odds_path"].unlink()

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["current_odds_checksum_status"] == "Not available"
    assert result["validation_status"] == "Not checked"
    assert result["card_generation_allowed"] is False
    assert any("is missing" in item for item in result["blockers"])


def test_runner_handoff_blocks_malformed_odds_dates(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    odds = pd.read_csv(paths["current_odds_path"])
    odds["date"] = "2026-99-99"
    odds.to_csv(paths["current_odds_path"], index=False)

    with pytest.warns(UserWarning, match="Could not infer format"):
        result = _build(tmp_path, paths)

    assert result["current_odds_freshness_status"] == "Not checked"
    assert result["current_odds_invalid_date_rows"] == 7
    assert result["card_generation_allowed"] is False
    assert any("malformed" in item for item in result["blockers"])


def test_runner_handoff_blocks_paths_outside_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    paths = _write_inputs(root)
    outside = tmp_path / "outside_current_odds.csv"
    outside.write_text(
        paths["current_odds_path"].read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["current_odds_path"] = outside

    result = _build(root, paths)

    assert result["current_odds_path_policy_valid"] is False
    assert result["card_generation_allowed"] is False
    assert any("inside" in item for item in result["blockers"])


def test_runner_handoff_blocks_symbolic_link_inputs(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    link = paths["current_odds_path"].with_name("linked_current_odds.csv")
    link.symlink_to(paths["current_odds_path"])
    paths["current_odds_path"] = link

    result = _build(tmp_path, paths)

    assert result["current_odds_path_policy_valid"] is False
    assert result["card_generation_allowed"] is False
    assert any("symbolic link" in item for item in result["blockers"])


def test_runner_handoff_blocks_optional_checksum_mismatch(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    result = _build(
        tmp_path,
        paths,
        expected_current_odds_sha256="0" * 64,
    )

    assert result["current_odds_checksum_status"] == "Mismatch"
    assert result["card_generation_allowed"] is False
    assert any("checksum does not match" in item for item in result["blockers"])


def test_runner_handoff_verifies_matching_optional_checksums(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    odds_checksum = hashlib.sha256(paths["current_odds_path"].read_bytes()).hexdigest()
    fixtures_checksum = hashlib.sha256(paths["fixtures_path"].read_bytes()).hexdigest()

    result = _build(
        tmp_path,
        paths,
        expected_current_odds_sha256=odds_checksum,
        expected_fixtures_sha256=fixtures_checksum,
    )

    assert result["current_odds_checksum_status"] == "Verified"
    assert result["fixtures_checksum_status"] == "Verified"
    assert result["card_generation_allowed"] is True


def test_runner_handoff_writes_json_and_beginner_markdown(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    saved = save_github_runner_input_handoff(
        output_dir=paths["output_dir"],
        current_odds_path=paths["current_odds_path"],
        fixtures_path=paths["fixtures_path"],
        matches_path=paths["matches_path"],
        run_at=RUN_AT,
        repository_root=tmp_path,
    )

    payload = json.loads(Path(saved["json"]).read_text(encoding="utf-8"))
    markdown = Path(saved["markdown"]).read_text(encoding="utf-8")
    assert payload["current_odds_path"] == "data/manual/current_odds.csv"
    assert payload["card_generation_allowed"] is True
    assert "Input proof" in markdown
    assert "SHA-256" in markdown
    assert "Never fill missing odds with guesses" not in markdown
    assert "does not create sportsbook prices" in markdown
