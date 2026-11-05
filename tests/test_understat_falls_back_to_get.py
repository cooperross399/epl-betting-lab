"""Understat answers 405 to POST on its data endpoints; the requester must
ask again by GET rather than report the season unreadable."""

from __future__ import annotations

import sys
import types

import pytest

from epl_betting_lab.providers import understat_players


class _Response:
    def __init__(self, status: int, payload: object = None) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


def _fake_requests(monkeypatch, post_status: int, get_status: int, calls: list[str]) -> None:
    module = types.ModuleType("requests")

    def post(url, headers=None, timeout=None):
        calls.append("post")
        return _Response(post_status, {"via": "post"})

    def get(url, headers=None, timeout=None):
        calls.append("get")
        assert headers and headers.get("X-Requested-With") == "XMLHttpRequest"
        return _Response(get_status, {"via": "get"})

    module.post = post
    module.get = get
    monkeypatch.setitem(sys.modules, "requests", module)


def test_a_405_on_post_is_asked_again_by_get(monkeypatch):
    calls: list[str] = []
    _fake_requests(monkeypatch, 405, 200, calls)
    assert understat_players._default_requester("https://understat.com/getLeagueData/EPL/2026") == {"via": "get"}
    assert calls == ["post", "get"]


def test_a_working_post_never_asks_by_get(monkeypatch):
    calls: list[str] = []
    _fake_requests(monkeypatch, 200, 200, calls)
    assert understat_players._default_requester("https://understat.com/x") == {"via": "post"}
    assert calls == ["post"]


def test_other_refusals_still_raise(monkeypatch):
    calls: list[str] = []
    _fake_requests(monkeypatch, 403, 200, calls)
    with pytest.raises(understat_players.UnderstatError, match="403"):
        understat_players._default_requester("https://understat.com/x")
    assert calls == ["post"]


def test_get_refusing_too_still_raises(monkeypatch):
    calls: list[str] = []
    _fake_requests(monkeypatch, 405, 404, calls)
    with pytest.raises(understat_players.UnderstatError, match="404"):
        understat_players._default_requester("https://understat.com/x")
