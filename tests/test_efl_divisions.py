"""The EFL divisions are modelled beside the Premier League, never inside it.

Football-Data publishes E1, E2 and E3 in the same shape as E0, which makes
adding them look like a one-line change. The thing that stops it being one is
that a team rating means something only against the pool it was fitted on: four
English divisions share almost no opponents, so a pooled dataset would put a
League Two side's rating on the same scale as a Premier League side's and
nothing downstream would report the error. The card would look entirely normal.

Every test here pins one half of that: the divisions stay in separate files, and
the builder refuses to write one division's matches into another's dataset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epl_betting_lab.config import DIVISION_NAMES, EFL_DIVISIONS, LEAGUE_CODE
from epl_betting_lab.data import fetch_football_data as fetcher


def _csv(div: str) -> bytes:
    return (
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC\n"
        + f"{div},16/08/2025,Home FC,Away FC,2,1,H,5,4\n".encode()
    )


def _stub_fetch(monkeypatch, div_of_file: str) -> None:
    """Serve `div_of_file` rows no matter which division is asked for."""

    def _fetch(season: str, league: str = LEAGUE_CODE, raw_dir: Path | None = None) -> Path:
        path = fetcher.RAW_DIR / f"football_data_{league}_{season}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_csv(div_of_file))
        return path

    monkeypatch.setattr(fetcher, "fetch_season", _fetch)


class TestTheDivisionsAreNamedOnce:
    def test_the_efl_is_every_english_division_below_the_premier_league(self) -> None:
        assert set(EFL_DIVISIONS) == set(DIVISION_NAMES) - {LEAGUE_CODE}

    def test_the_premier_league_is_not_in_the_efl(self) -> None:
        """It is the one division that is not in the EFL, and a card that
        quietly included it under an EFL heading would be wrong about which
        competition it was advising on."""
        assert LEAGUE_CODE not in EFL_DIVISIONS


class TestEachDivisionGetsItsOwnFile:
    def test_the_premier_league_keeps_the_path_every_reader_already_names(self) -> None:
        assert fetcher.processed_path_for(LEAGUE_CODE).name == "epl_historical_matches.csv"

    def test_no_two_divisions_share_a_file(self) -> None:
        """Sharing one would not raise anything. The second build would simply
        overwrite the first, and the model would be fitted on whichever
        division happened to run last."""
        paths = [fetcher.processed_path_for(d) for d in DIVISION_NAMES]
        assert len(set(paths)) == len(paths)

    @pytest.mark.parametrize("division", EFL_DIVISIONS)
    def test_an_efl_division_is_written_beside_the_premier_league_not_over_it(
        self, division: str
    ) -> None:
        assert fetcher.processed_path_for(division) != fetcher.processed_path_for(LEAGUE_CODE)
        assert division in fetcher.processed_path_for(division).name


class TestTheBuilderRefusesToPoolDivisions:
    def _build(self, monkeypatch, tmp_path, *, asked_for: str, served: str):
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", tmp_path / "processed")
        _stub_fetch(monkeypatch, div_of_file=served)
        return fetcher.fetch_and_build_dataset(["2526"], force=True, league=asked_for)

    def test_championship_rows_cannot_become_the_premier_league_dataset(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The failure this exists for: a fetch that went to the wrong URL, or
        a stale raw file picked up, trains the model on the wrong league while
        looking completely ordinary."""
        with pytest.raises(RuntimeError, match="no common scale"):
            self._build(monkeypatch, tmp_path, asked_for="E0", served="E1")

    def test_premier_league_rows_cannot_become_the_championship_dataset(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        with pytest.raises(RuntimeError, match="no common scale"):
            self._build(monkeypatch, tmp_path, asked_for="E1", served="E0")

    @pytest.mark.parametrize("division", ("E0",) + EFL_DIVISIONS)
    def test_the_guard_is_not_simply_refusing_everything(
        self, monkeypatch, tmp_path: Path, division: str
    ) -> None:
        """A guard that rejects the matching case too would pass both tests
        above while making the feature unusable — and four vacuous guards have
        been found in this project already."""
        frame = self._build(monkeypatch, tmp_path, asked_for=division, served=division)
        assert len(frame) == 1
        assert fetcher.processed_path_for(division).exists()


class TestTheColumnsTheEflMarketsNeed:
    @pytest.mark.parametrize(
        "column,why",
        [
            ("HC", "corners_1x2 and both corner totals settle on HC/AC"),
            ("AC", "corners_1x2 and both corner totals settle on HC/AC"),
            ("AvgCH", "closing odds are the only per-bet feedback inside a season"),
            ("B365C>2.5", "the totals market's closing price"),
        ],
    )
    def test_it_is_kept_when_the_csv_has_it(self, column: str, why: str) -> None:
        """Verified present and fully populated for E1/E2/E3 in every season
        from 2021/22 onward. If the keep-list ever drops one of these, the EFL
        markets stop being settleable and the report would say the data was
        missing rather than that the loader threw it away."""
        source = Path(fetcher.__file__).read_text(encoding="utf-8")
        desired = source.split("desired = [", 1)[1].split("]", 1)[0]
        assert f'"{column}"' in desired, why
