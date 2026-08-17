"""Prove the provider credential authenticates, without revealing it.

Answering "does the key work?" normally tempts someone to print it, echo it into
a log, or diff it against an expected value. None of that is necessary: the
provider itself will say whether the credential is accepted.

This module asks the sports-list endpoint, which costs no quota, and reports
only the outcome — authenticated or not, the HTTP status, and the safe usage
headers. The credential is never returned, printed, logged, written, or
compared against anything. The only fact derived from it is its length, which is
reported as a bare integer so an operator can tell "empty" from "present"
without learning a character of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

import requests

from epl_betting_lab.providers.odds_api_staging_provider import (
    ALLOWED_API_HOSTS,
    API_KEY_ENV,
    DEFAULT_API_BASE_URL,
    SAFE_RESPONSE_HEADERS,
)


#: Free endpoint: listing sports costs no quota.
SPORTS_PATH = "/v4/sports"

#: Anything matching these is scrubbed before a message is returned.
_REDACTIONS = (
    re.compile(r"(apiKey=)[^&\s\"']+", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{32}\b", re.IGNORECASE),
)


def redact(text: object) -> str:
    """Remove anything credential-shaped from a message before it is shown."""
    value = "" if text is None else str(text)
    value = _REDACTIONS[0].sub(r"\1[redacted]", value)
    return _REDACTIONS[1].sub("[redacted]", value)


def check_provider_credential(
    environment: Mapping[str, str],
    *,
    base_url: str = DEFAULT_API_BASE_URL,
    requester: Any = None,
    timeout_seconds: float = 20.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ask the provider whether the credential is accepted.

    Returns a report containing no credential material. Network and parsing
    failures are reported as outcomes rather than raised, so a caller never has
    to catch an exception whose message might quote the request URL.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    api_key = str(environment.get(API_KEY_ENV, "") or "").strip()

    report: dict[str, Any] = {
        "report": "Provider Credential Check",
        "checked_at": moment.isoformat(timespec="seconds"),
        "credential_variable": API_KEY_ENV,
        "credential_present": bool(api_key),
        "credential_length": len(api_key),
        "endpoint": f"{base_url.rstrip('/')}{SPORTS_PATH}",
        "quota_cost": 0,
        "authenticated": False,
        "status_code": None,
        "outcome": "",
        "usage_headers": {},
        "safety": {
            "credential_printed": False,
            "credential_written": False,
            "credential_compared": False,
            "quota_consumed": False,
        },
    }

    if not api_key:
        report["outcome"] = (
            f"`{API_KEY_ENV}` is not set in this environment. Set it as a GitHub "
            "Actions secret for CI, or in a gitignored local `.env`."
        )
        return report

    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_API_HOSTS:
        report["outcome"] = "Refusing to send the credential to an unapproved host."
        return report

    request = requester or requests.get
    try:
        response = request(
            report["endpoint"],
            params={"apiKey": api_key},
            timeout=timeout_seconds,
        )
    except Exception as exc:  # message may quote the URL, so scrub it
        report["outcome"] = redact(
            f"The provider could not be reached ({type(exc).__name__})."
        )
        return report

    status = getattr(response, "status_code", None)
    report["status_code"] = status
    headers = getattr(response, "headers", {}) or {}
    report["usage_headers"] = {
        name: redact(headers.get(name, ""))
        for name in SAFE_RESPONSE_HEADERS
        if headers.get(name) is not None
    }

    if status == 200:
        report["authenticated"] = True
        report["outcome"] = "The provider accepted the credential."
    elif status in {401, 403}:
        report["outcome"] = (
            f"The provider rejected the credential (HTTP {status}). If the key "
            "was recently rotated, update the secret or `.env`."
        )
    else:
        report["outcome"] = redact(
            f"Unexpected provider response (HTTP {status or 'unknown'})."
        )
    return report


def render_credential_check(report: Mapping[str, Any]) -> list[str]:
    """Lines safe to print or write to a CI log."""
    lines = [
        f"Credential variable: {report['credential_variable']}",
        f"Credential present: {'Yes' if report['credential_present'] else 'No'}",
        f"Credential length: {report['credential_length']}",
        f"Endpoint: {report['endpoint']} (quota cost {report['quota_cost']})",
        f"Authenticated: {'Yes' if report['authenticated'] else 'No'}",
        f"HTTP status: {report['status_code'] if report['status_code'] is not None else 'n/a'}",
        f"Outcome: {report['outcome']}",
    ]
    for name, value in sorted(report["usage_headers"].items()):
        lines.append(f"Usage header {name}: {value}")
    lines.append(
        "Safety: the credential was not printed, written, logged, or compared."
    )
    return lines
