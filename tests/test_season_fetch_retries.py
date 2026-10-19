"""A slow or flaky Football-Data answer is asked again before the run gives up.

On 2026-10-19 the 08:26 UTC Matchday Refresh lost the E0 fetch to one 30-second
timeout and fitted the model on the previous day's file, and the 12:41 run lost
La Liga the same way, which took the whole Champions League section off the
card. Each was one request, asked once.
"""

from __future__ import annotations

import pytest
import requests

from epl_betting_lab.data import fetch_football_data as fetcher

RESULTS_CSV = (
    b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    b"E0,18/10/2026,Arsenal,Chelsea,2,1,H\n"
)


class _Response:
    def __init__(self, status: int, content: bytes = RESULTS_CSV) -> None:
        self.status_code = status
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(fetcher.time, "sleep", slept.append)
    return slept


def _sequence(monkeypatch, answers):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(fetcher.requests, "get", fake_get)
    return calls


def test_a_timeout_is_retried(monkeypatch, tmp_path) -> None:
    calls = _sequence(monkeypatch, [requests.Timeout("read timed out"), _Response(200)])
    path = fetcher.fetch_season("2627", "E0", raw_dir=tmp_path)
    assert len(calls) == 2
    assert path.read_bytes() == RESULTS_CSV


def test_a_server_error_is_retried(monkeypatch, tmp_path) -> None:
    calls = _sequence(monkeypatch, [_Response(503, b""), _Response(200)])
    fetcher.fetch_season("2627", "E0", raw_dir=tmp_path)
    assert len(calls) == 2


def test_it_gives_up_after_a_bounded_number_of_tries(monkeypatch, tmp_path, _no_sleep) -> None:
    calls = _sequence(monkeypatch, [requests.ConnectionError("reset")])
    with pytest.raises(requests.ConnectionError):
        fetcher.fetch_season("2627", "E0", raw_dir=tmp_path)
    assert len(calls) == fetcher.FETCH_ATTEMPTS
    assert len(_no_sleep) == fetcher.FETCH_ATTEMPTS - 1


def test_a_missing_season_is_not_retried(monkeypatch, tmp_path) -> None:
    """A redirect page is an answer, not a failure: asking again changes nothing."""
    calls = _sequence(monkeypatch, [_Response(300, b"<html>300</html>")])
    with pytest.raises(fetcher.SeasonNotPublished):
        fetcher.fetch_season("2627", "E0", raw_dir=tmp_path)
    assert len(calls) == 1


def test_a_client_error_is_not_retried(monkeypatch, tmp_path) -> None:
    calls = _sequence(monkeypatch, [_Response(404, b"")])
    with pytest.raises(requests.HTTPError):
        fetcher.fetch_season("2627", "E0", raw_dir=tmp_path)
    assert len(calls) == 1
