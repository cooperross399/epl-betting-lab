"""The credential check must prove authentication without revealing anything."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epl_betting_lab.providers.credential_check import (
    SPORTS_PATH,
    check_provider_credential,
    redact,
    render_credential_check,
)
from epl_betting_lab.providers.odds_api_staging_provider import API_KEY_ENV


NOW = datetime(2026, 8, 17, 21, 0, tzinfo=timezone.utc)
# The redaction tests need a value that *looks* like a credential, but a
# 32-hex literal in a tracked file is exactly what the secrets guard flags -
# and rightly so, since it cannot tell a synthetic one from a real one.
# Building it at runtime keeps the guard strict and this file honest.
FAKE_KEY = "abcdef01" * 4


class _Response:
    def __init__(self, status: int = 200, headers: dict | None = None) -> None:
        self.status_code = status
        self.headers = headers or {
            "x-requests-remaining": "340",
            "x-requests-used": "160",
        }


def _check(status: int = 200, **kwargs):
    calls: list[dict] = []

    def requester(url: str, **request_kwargs):
        calls.append({"url": url, **request_kwargs})
        return _Response(status)

    report = check_provider_credential(
        {API_KEY_ENV: FAKE_KEY}, requester=requester, now=NOW, **kwargs
    )
    return report, calls


# --- outcome ---------------------------------------------------------------


def test_accepted_credential_reports_authenticated() -> None:
    report, _ = _check(200)

    assert report["authenticated"] is True
    assert report["status_code"] == 200
    assert "accepted" in report["outcome"]


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credential_reports_not_authenticated(status: int) -> None:
    report, _ = _check(status)

    assert report["authenticated"] is False
    assert "rejected" in report["outcome"]
    assert "rotated" in report["outcome"]


def test_missing_credential_is_reported_not_raised() -> None:
    report = check_provider_credential({}, now=NOW)

    assert report["credential_present"] is False
    assert report["credential_length"] == 0
    assert report["authenticated"] is False
    assert API_KEY_ENV in report["outcome"]


def test_unapproved_host_is_refused_before_sending() -> None:
    calls: list[dict] = []

    report = check_provider_credential(
        {API_KEY_ENV: FAKE_KEY},
        base_url="https://evil.example.com",
        requester=lambda url, **kwargs: calls.append(kwargs),
        now=NOW,
    )

    assert calls == []
    assert report["authenticated"] is False
    assert "unapproved host" in report["outcome"]


def test_network_failure_is_an_outcome_not_an_exception() -> None:
    def boom(url: str, **kwargs):
        raise OSError(f"connection failed for {url}?apiKey={FAKE_KEY}")

    report = check_provider_credential(
        {API_KEY_ENV: FAKE_KEY}, requester=boom, now=NOW
    )

    assert report["authenticated"] is False
    assert FAKE_KEY not in report["outcome"]


# --- it must not leak ------------------------------------------------------


def test_the_report_never_contains_the_credential() -> None:
    import json

    report, _ = _check(200)

    assert FAKE_KEY not in json.dumps(report, default=str)


def test_printed_lines_never_contain_the_credential() -> None:
    report, _ = _check(200)

    text = "\n".join(render_credential_check(report))

    assert FAKE_KEY not in text
    assert "apiKey=" not in text


def test_only_the_length_is_derived_from_the_credential() -> None:
    report, _ = _check(200)

    assert report["credential_length"] == len(FAKE_KEY)
    assert report["safety"]["credential_printed"] is False
    assert report["safety"]["credential_written"] is False
    assert report["safety"]["credential_compared"] is False


def test_rejected_status_message_never_quotes_the_credential() -> None:
    report, _ = _check(401)

    assert FAKE_KEY not in report["outcome"]


def test_unexpected_status_message_is_redacted() -> None:
    report, _ = _check(500)

    assert FAKE_KEY not in report["outcome"]
    assert report["authenticated"] is False


def test_usage_headers_are_redacted_even_if_they_echo_a_key() -> None:
    def requester(url: str, **kwargs):
        return _Response(
            200,
            headers={
                "x-requests-remaining": "340",
                "x-requests-used": f"apiKey={FAKE_KEY}",
            },
        )

    report = check_provider_credential(
        {API_KEY_ENV: FAKE_KEY}, requester=requester, now=NOW
    )

    assert FAKE_KEY not in str(report["usage_headers"])


def test_redact_removes_key_shaped_values_and_query_parameters() -> None:
    assert FAKE_KEY not in redact(f"apiKey={FAKE_KEY}&regions=us")
    assert FAKE_KEY not in redact(f"bare {FAKE_KEY} in text")
    assert "[redacted]" in redact(f"apiKey={FAKE_KEY}")


# --- request shape ---------------------------------------------------------


def test_it_calls_the_free_sports_endpoint() -> None:
    report, calls = _check(200)

    assert calls[0]["url"].endswith(SPORTS_PATH)
    assert report["quota_cost"] == 0
    assert report["safety"]["quota_consumed"] is False


def test_the_credential_is_sent_as_a_parameter_not_in_the_url() -> None:
    _, calls = _check(200)

    assert FAKE_KEY not in calls[0]["url"]
    assert calls[0]["params"]["apiKey"] == FAKE_KEY


def test_it_requests_no_odds() -> None:
    """A credential check must not pull prices as a side effect."""
    _, calls = _check(200)

    assert "markets" not in calls[0]["params"]
    # The host is api.the-odds-api.com, so check the path rather than the host.
    assert "/odds" not in calls[0]["url"]


# --- workflow ---------------------------------------------------------------


def _workflow() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "provider-credential-check.yml"
    )
    return path.read_text(encoding="utf-8")


def test_workflow_passes_the_secret_as_an_environment_variable() -> None:
    text = _workflow()

    assert "EPL_ODDS_API_KEY: ${{ secrets.EPL_ODDS_API_KEY }}" in text


def test_workflow_has_no_schedule_or_cron_trigger() -> None:
    text = _workflow()

    assert "cron" not in text
    assert "schedule:" not in text
    assert "workflow_dispatch" in text


def test_workflow_never_echoes_the_credential() -> None:
    text = _workflow()

    assert "echo $EPL_ODDS_API_KEY" not in text
    assert "echo ${EPL_ODDS_API_KEY}" not in text
    assert "print(os.environ[" not in text


# --- what the key is entitled to price -------------------------------------
#
# Adding a competition means writing a sport key into the collector, and a
# wrong key does not raise: the provider returns nothing for it and the feed
# stays empty, quietly, until somebody notices months later. The sports list
# was already being fetched here and discarded, so reporting it costs no quota
# and no extra call.


class _SportsResponse(_Response):
    def __init__(self, body, status: int = 200) -> None:
        super().__init__(status)
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _check_with_body(body, status: int = 200):
    return check_provider_credential(
        {API_KEY_ENV: FAKE_KEY},
        requester=lambda url, **kw: _SportsResponse(body, status),
        now=NOW,
    )


SPORTS_BODY = [
    {"key": "soccer_epl", "title": "Premier League", "active": True},
    {"key": "soccer_uefa_nations_league", "title": "UEFA Nations League", "active": False},
    {"key": "basketball_nba", "title": "NBA", "active": True},
]


def test_the_soccer_competitions_are_reported() -> None:
    report = _check_with_body(SPORTS_BODY)

    keys = [entry["key"] for entry in report["soccer_sports"]]
    assert keys == ["soccer_epl", "soccer_uefa_nations_league"]
    assert report["soccer_sports"][1]["active"] is False


def test_other_sports_are_not_reported() -> None:
    """This project prices football. A basketball key in the list is noise in
    the one report someone reads to find out what a competition is called."""
    report = _check_with_body(SPORTS_BODY)

    assert all(entry["key"].startswith("soccer") for entry in report["soccer_sports"])


def test_the_listing_appears_in_the_printed_lines() -> None:
    lines = render_credential_check(_check_with_body(SPORTS_BODY))
    text = "\n".join(lines)

    assert "soccer_uefa_nations_league" in text
    assert "UEFA Nations League" in text
    assert "out of season" in text, (
        "a competition between tournaments still has a key worth knowing, and "
        "reporting it without saying it is dormant reads as a broken feed"
    )


def test_the_listing_never_carries_the_credential() -> None:
    """The one rule this module exists to keep."""
    report = _check_with_body(SPORTS_BODY)

    assert FAKE_KEY not in json.dumps(report)
    assert FAKE_KEY not in "\n".join(render_credential_check(report))


@pytest.mark.parametrize(
    "body",
    [
        ValueError("not json"),
        {"message": "an object, not a list"},
        ["a bare string", 7, None],
        [],
    ],
    ids=["unparseable", "not-a-list", "junk-entries", "empty"],
)
def test_a_body_that_is_not_a_sports_list_does_not_break_the_check(body) -> None:
    """Diagnostics riding along on a credential check must never be the reason
    the credential check fails. The question being answered is "does the key
    work", and it still has an answer when the body is unexpected."""
    report = _check_with_body(body)

    assert report["authenticated"] is True
    assert report["soccer_sports"] == []


def test_a_rejected_credential_claims_no_competitions() -> None:
    """A 401 body is an error document. Reading competitions out of it would
    report an entitlement the key does not have."""
    report = _check_with_body(SPORTS_BODY, status=401)

    assert report["authenticated"] is False
    assert not report.get("soccer_sports")
