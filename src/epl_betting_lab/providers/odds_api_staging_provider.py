from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse

import pandas as pd
import requests

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT, STAGING_DIR
from epl_betting_lab.providers.base import (
    BaseStagingProvider,
    EmptyProviderResponseError,
    MalformedProviderResponseError,
    MissingProviderCredentialsError,
    PROVENANCE_FILENAME,
    ProviderAdapterError,
    ProviderRunRequest,
    ProviderUnavailableError,
    SOURCE_FIXTURES_FILENAME,
    SOURCE_ODDS_FILENAME,
    STAGING_FIXTURES_FILENAME,
    STAGING_ODDS_FILENAME,
    atomic_write_bundle,
    atomic_write_report,
    display_repository_path,
    file_sha256,
    path_contains_symlink,
    sha256_bytes,
    validate_output_path,
)


from epl_betting_lab.providers.team_names import normalize_team_name


API_KEY_ENV = "EPL_ODDS_API_KEY"
API_BASE_URL_ENV = "EPL_ODDS_API_BASE_URL"
DEFAULT_API_BASE_URL = "https://api.the-odds-api.com"
ALLOWED_API_HOSTS = {
    "api.the-odds-api.com",
    "ipv6-api.the-odds-api.com",
}
DEFAULT_SPORT_KEY = "soccer_epl"
DEFAULT_REGIONS = "us"
PROVIDER_KEY = "odds_api"
PROVIDER_NAME = "the_odds_api"
PROVIDER_TYPE = "odds_api"
REPORT_JSON_FILENAME = "odds_api_staging_provider_report.json"
REPORT_MARKDOWN_FILENAME = "odds_api_staging_provider_report.md"
PROVENANCE_SCHEMA_VERSION = 1

ODDS_COLUMNS = (
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
FIXTURE_COLUMNS = (
    "date",
    "home_team",
    "away_team",
    "provider_event_id",
    "commence_time",
    "notes",
)
SAFE_RESPONSE_HEADERS = (
    "x-requests-remaining",
    "x-requests-used",
    "x-requests-last",
)


Requester = Callable[..., object]


def _default_requester(url: str, **kwargs: object) -> object:
    return requests.get(url, **kwargs)


def _csv_bytes(frame: pd.DataFrame, columns: tuple[str, ...]) -> bytes:
    ordered = frame.reindex(columns=columns).fillna("")
    return ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _required_text(value: object, *, label: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise MalformedProviderResponseError(
            f"Provider response is missing required `{label}` data."
        )
    return text


def _american_price(value: object) -> int | float:
    if isinstance(value, bool):
        raise MalformedProviderResponseError(
            "Provider response contains a non-numeric American price."
        )
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise MalformedProviderResponseError(
            "Provider response contains a non-numeric American price."
        ) from exc
    if not math.isfinite(price) or -100 < price < 100:
        raise MalformedProviderResponseError(
            "Provider response contains an invalid American price."
        )
    return int(price) if price.is_integer() else price


def _normalize_provider_events(
    events: object,
    *,
    generated_at: datetime,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict[str, int]]:
    if not isinstance(events, list):
        raise MalformedProviderResponseError(
            "Provider response must be a JSON list of EPL events."
        )
    if not events:
        raise EmptyProviderResponseError(
            "The provider returned no EPL fixtures. Try again when markets are posted."
        )

    fixture_rows: list[dict[str, object]] = []
    odds_rows: list[dict[str, object]] = []
    fixture_keys: set[tuple[str, str, str]] = set()
    odds_keys: set[tuple[str, str, str, str, str, str]] = set()
    market_counts = {"1x2": 0, "total_2_5": 0, "btts": 0}

    for event_index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise MalformedProviderResponseError(
                f"Provider event {event_index} is not a JSON object."
            )
        event_id = _required_text(event.get("id"), label="event id")
        commence_time = _required_text(
            event.get("commence_time"), label="commence_time"
        )
        parsed_time = pd.to_datetime(commence_time, errors="coerce", utc=True)
        if pd.isna(parsed_time):
            raise MalformedProviderResponseError(
                f"Provider event `{event_id}` has an invalid commence_time."
            )
        provider_home_team = _required_text(event.get("home_team"), label="home_team")
        provider_away_team = _required_text(event.get("away_team"), label="away_team")
        if provider_home_team.casefold() == provider_away_team.casefold():
            raise MalformedProviderResponseError(
                f"Provider event `{event_id}` uses the same home and away team."
            )
        # Staging rows carry canonical project names so they line up with
        # upcoming_fixtures.csv. The raw provider names are kept for matching
        # h2h outcome labels, which the provider emits in its own vocabulary.
        home_team = normalize_team_name(provider_home_team)
        away_team = normalize_team_name(provider_away_team)
        if home_team.casefold() == away_team.casefold():
            raise MalformedProviderResponseError(
                f"Provider event `{event_id}` maps home and away onto the same "
                "project team name."
            )
        match_date = parsed_time.strftime("%Y-%m-%d")
        fixture_key = (
            match_date,
            home_team.casefold(),
            away_team.casefold(),
        )
        if fixture_key in fixture_keys:
            raise MalformedProviderResponseError(
                f"Provider response repeats event `{event_id}`."
            )
        fixture_keys.add(fixture_key)
        fixture_rows.append(
            {
                "date": match_date,
                "home_team": home_team,
                "away_team": away_team,
                "provider_event_id": event_id,
                "commence_time": commence_time,
                "notes": f"{PROVIDER_NAME} event {event_id}",
            }
        )

        bookmakers = event.get("bookmakers", [])
        if not isinstance(bookmakers, list):
            raise MalformedProviderResponseError(
                f"Provider event `{event_id}` has malformed bookmakers data."
            )
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, dict):
                raise MalformedProviderResponseError(
                    f"Provider event `{event_id}` has a malformed bookmaker."
                )
            book_key = _required_text(bookmaker.get("key"), label="bookmaker key")
            book_name = _required_text(
                bookmaker.get("title") or book_key, label="bookmaker name"
            )
            markets = bookmaker.get("markets", [])
            if not isinstance(markets, list):
                raise MalformedProviderResponseError(
                    f"Provider bookmaker `{book_name}` has malformed markets data."
                )
            for market in markets:
                if not isinstance(market, dict):
                    raise MalformedProviderResponseError(
                        f"Provider bookmaker `{book_name}` has a malformed market."
                    )
                market_key = str(market.get("key", "")).strip().lower()
                if market_key not in {"h2h", "totals", "btts"}:
                    continue
                outcomes = market.get("outcomes", [])
                if not isinstance(outcomes, list):
                    raise MalformedProviderResponseError(
                        f"Provider market `{market_key}` has malformed outcomes."
                    )
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        raise MalformedProviderResponseError(
                            f"Provider market `{market_key}` has a malformed outcome."
                        )
                    outcome_name = _required_text(
                        outcome.get("name"), label="outcome name"
                    )
                    normalized_market = ""
                    selection = ""
                    if market_key == "h2h":
                        # Compare on both the raw provider label and the mapped
                        # project name so a reviewed alias resolves the outcome.
                        outcome_keys = {
                            outcome_name.casefold(),
                            normalize_team_name(outcome_name).casefold(),
                        }
                        if outcome_keys & {
                            provider_home_team.casefold(),
                            home_team.casefold(),
                        }:
                            selection = "home"
                        elif outcome_keys & {
                            provider_away_team.casefold(),
                            away_team.casefold(),
                        }:
                            selection = "away"
                        elif outcome_name.casefold() in {"draw", "tie"}:
                            selection = "draw"
                        else:
                            raise MalformedProviderResponseError(
                                f"Unrecognized h2h outcome `{outcome_name}` for "
                                f"provider event `{event_id}`."
                            )
                        normalized_market = "1x2"
                    elif market_key == "totals":
                        try:
                            point = float(outcome.get("point"))
                        except (TypeError, ValueError):
                            continue
                        if not math.isclose(point, 2.5):
                            continue
                        lowered = outcome_name.casefold()
                        if lowered not in {"over", "under"}:
                            raise MalformedProviderResponseError(
                                f"Unrecognized totals outcome `{outcome_name}`."
                            )
                        normalized_market = "total_2_5"
                        selection = lowered
                    else:
                        lowered = outcome_name.casefold()
                        if lowered not in {"yes", "no"}:
                            raise MalformedProviderResponseError(
                                f"Unrecognized BTTS outcome `{outcome_name}`."
                            )
                        normalized_market = "btts"
                        selection = lowered

                    price = _american_price(outcome.get("price"))
                    odds_key = (
                        match_date,
                        home_team.casefold(),
                        away_team.casefold(),
                        normalized_market,
                        selection,
                        book_name.casefold(),
                    )
                    if odds_key in odds_keys:
                        raise MalformedProviderResponseError(
                            "Provider response repeats an odds row for the same "
                            "fixture, market, selection, and book."
                        )
                    odds_keys.add(odds_key)
                    odds_rows.append(
                        {
                            "date": match_date,
                            "home_team": home_team,
                            "away_team": away_team,
                            "market": normalized_market,
                            "selection": selection,
                            "american_odds": price,
                            "closing_american_odds": "",
                            "book": book_name,
                            "notes": (
                                f"{PROVIDER_NAME} event {event_id}; bookmaker "
                                f"{book_key}; fetched "
                                f"{generated_at.isoformat(timespec='seconds')}"
                            ),
                        }
                    )
                    market_counts[normalized_market] += 1

    if not odds_rows:
        raise EmptyProviderResponseError(
            "The provider returned fixtures but no supported 1X2, 2.5 totals, "
            "or BTTS prices. No staging files were written."
        )

    fixtures = pd.DataFrame(fixture_rows, columns=FIXTURE_COLUMNS).sort_values(
        ["date", "home_team", "away_team"], ignore_index=True
    )
    odds = pd.DataFrame(odds_rows, columns=ODDS_COLUMNS).sort_values(
        ["date", "home_team", "away_team", "book", "market", "selection"],
        ignore_index=True,
    )
    warnings = []
    for market, label in (
        ("1x2", "1X2"),
        ("total_2_5", "2.5 totals"),
        ("btts", "BTTS"),
    ):
        if market_counts[market] == 0:
            warnings.append(
                f"The provider returned no {label} rows. Staging completeness "
                "validation may block this bundle; no prices were guessed."
            )
    return odds, fixtures, warnings, market_counts


class OddsApiStagingProvider(BaseStagingProvider):
    """Offline-first EPL adapter skeleton for The Odds API v4 response shape."""

    provider_key = PROVIDER_KEY
    provider_name = PROVIDER_NAME
    provider_type = PROVIDER_TYPE

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        requester: Requester | None = None,
        sport_key: str = DEFAULT_SPORT_KEY,
        regions: str = DEFAULT_REGIONS,
        bookmakers: str = "",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.requester = requester or _default_requester
        self.sport_key = sport_key.strip() or DEFAULT_SPORT_KEY
        self.regions = regions.strip() or DEFAULT_REGIONS
        self.bookmakers = bookmakers.strip()
        self.timeout_seconds = timeout_seconds

    @property
    def credential_environment_variables(self) -> tuple[str, ...]:
        return (API_KEY_ENV,)

    @property
    def api_key(self) -> str:
        return self.environment.get(API_KEY_ENV, "").strip()

    @property
    def base_url(self) -> str:
        return (
            self.environment.get(API_BASE_URL_ENV, DEFAULT_API_BASE_URL).strip()
            or DEFAULT_API_BASE_URL
        ).rstrip("/")

    @property
    def source_url(self) -> str:
        return f"{self.base_url}/v4/sports/{self.sport_key}/odds"

    def public_configuration(self) -> Mapping[str, object]:
        config = dict(super().public_configuration())
        config.update(
            {
                "source_url": self.source_url,
                "sport_key": self.sport_key,
                "regions": self.regions,
                "bookmakers": self.bookmakers or "provider region default",
                "featured_markets_requested": ["h2h", "totals"],
            }
        )
        return config

    def _validate_configuration(self) -> None:
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_API_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderAdapterError(
                f"{API_BASE_URL_ENV} must use an approved The Odds API HTTPS host."
            )
        if not re.fullmatch(r"[a-z0-9_]+", self.sport_key):
            raise ProviderAdapterError("Provider sport key contains unsafe characters.")
        for label, value in (("regions", self.regions), ("bookmakers", self.bookmakers)):
            if value and not re.fullmatch(r"[a-z0-9_,]+", value):
                raise ProviderAdapterError(
                    f"Provider {label} must contain only lowercase keys and commas."
                )
        if self.timeout_seconds <= 0:
            raise ProviderAdapterError("Provider timeout must be positive.")

    def _fetch_events(self) -> tuple[list[object], bytes, dict[str, str]]:
        if not self.api_key:
            raise MissingProviderCredentialsError(
                f"Live mode requires `{API_KEY_ENV}` from the environment, a "
                "gitignored local `.env`, or a GitHub Secret. Never pass the key "
                "as a command argument or commit it."
            )
        params = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": "h2h,totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if self.bookmakers:
            params["bookmakers"] = self.bookmakers
        try:
            response = self.requester(
                self.source_url,
                params=params,
                timeout=self.timeout_seconds,
            )
        except (requests.RequestException, OSError, TimeoutError) as exc:
            raise ProviderUnavailableError(
                f"The odds provider could not be reached ({type(exc).__name__}). "
                "No staging files were written."
            ) from exc

        status_code = getattr(response, "status_code", None)
        if status_code != 200:
            raise ProviderUnavailableError(
                f"The odds provider returned HTTP {status_code or 'unknown'}. "
                "No staging files were written."
            )
        raw_content = getattr(response, "content", b"")
        try:
            if raw_content:
                if not isinstance(raw_content, (bytes, bytearray)):
                    raise TypeError("response content is not bytes")
                payload = json.loads(bytes(raw_content).decode("utf-8-sig"))
            else:
                payload = response.json()
        except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
            raise MalformedProviderResponseError(
                "The odds provider returned unreadable JSON. No staging files "
                "were written."
            ) from exc
        if not isinstance(payload, list):
            raise MalformedProviderResponseError(
                "The odds provider JSON root is not an event list."
            )
        if not raw_content:
            raw_content = (
                json.dumps(payload, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
        headers = getattr(response, "headers", {})
        safe_headers = {
            name: str(headers.get(name, ""))
            for name in SAFE_RESPONSE_HEADERS
            if headers.get(name) is not None
        }
        return payload, bytes(raw_content), safe_headers

    def _directories(self, request: ProviderRunRequest) -> tuple[Path, Path, Path]:
        root = (request.repository_root or PROJECT_ROOT).resolve()
        staging = (root / "data" / "staging").resolve()
        outputs = (root / "data" / "outputs").resolve()
        for label, path in (("data/staging", staging), ("data/outputs", outputs)):
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ProviderAdapterError(
                    f"Provider {label} must stay inside the repository."
                ) from exc
            if path_contains_symlink(path, root):
                raise ProviderAdapterError(
                    f"Provider `{label}` cannot use a symbolic link."
                )
        if request.repository_root is None and (
            staging != STAGING_DIR.resolve() or outputs != OUTPUTS_DIR.resolve()
        ):
            raise ProviderAdapterError(
                "Provider outputs must stay in the project data directories."
            )
        return root, staging, outputs

    def _report_paths(self, output_dir: Path) -> tuple[Path, Path]:
        return (
            output_dir / REPORT_JSON_FILENAME,
            output_dir / REPORT_MARKDOWN_FILENAME,
        )

    def _save_reports(self, summary: dict[str, object], output_dir: Path) -> None:
        json_path, markdown_path = self._report_paths(output_dir)
        atomic_write_report(
            json_path,
            (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        atomic_write_report(
            markdown_path,
            self._render_report(summary).encode("utf-8"),
        )

    def _render_report(self, summary: dict[str, object]) -> str:
        blockers = [f"- {item}" for item in summary["blockers"]] or ["- None."]
        warnings = [f"- {item}" for item in summary["warnings"]] or ["- None."]
        lines = [
            "# Odds API Staging Provider Run",
            "",
            (
                "This adapter prepares provider evidence and staging files only. "
                "It does not validate the bundle, promote files, generate model "
                "recommendations, fabricate odds, or place bets."
            ),
            "",
            "## Result",
            "",
            f"- Status: **{summary['status']}**",
            f"- Mode: **{summary['mode']}**",
            f"- Provider: **{summary['provider_name']}** ({summary['provider_type']})",
            f"- Generated at: {summary['generated_at']}",
            f"- Generated by: {summary['generated_by']}",
            f"- Credential status: **{summary['credential_status']}**",
            f"- Source: {summary['source_url']}",
            f"- Network request made: **{'Yes' if summary['network_request_made'] else 'No'}**",
            f"- Next step: {summary['next_step']}",
            "",
            "## Output counts",
            "",
            f"- Fixtures: {summary['fixture_count']}",
            f"- Odds rows: {summary['odds_row_count']}",
            f"- 1X2 rows: {summary['market_counts']['1x2']}",
            f"- Total 2.5 rows: {summary['market_counts']['total_2_5']}",
            f"- BTTS rows: {summary['market_counts']['btts']}",
            "",
            "## Raw evidence",
            "",
            f"- Path: {summary['raw_source_path'] or 'not written'}",
            f"- SHA-256: {summary['raw_source_checksum_sha256'] or 'not available'}",
            "",
            "## Blockers",
            "",
            *blockers,
            "",
            "## Warnings",
            "",
            *warnings,
            "",
            "## Safety boundary",
            "",
            "- The API key is read only from `EPL_ODDS_API_KEY`.",
            "- The key is never written to reports, provenance, raw files, or console output.",
            "- Dashboard actions do not run this provider or expose credentials.",
            "- Staging validation remains a separate required command.",
            (
                "- The default provider policy must be deliberately reviewed "
                "before allowing this provider."
            ),
            "- Cron remains disabled.",
        ]
        if summary["status"] == "Dry run ready":
            lines.extend(
                [
                    "",
                    "## Live run after configuration review",
                    "",
                    "```bash",
                    "export EPL_ODDS_API_KEY='your-secret-key'",
                    "python scripts/run_provider_staging.py --provider odds_api --live",
                    "```",
                    "",
                    "Do not paste the key into a command argument or commit it.",
                ]
            )
        elif summary["status"] == "Completed":
            lines.extend(
                [
                    "",
                    "## Validate next",
                    "",
                    "```bash",
                    "python scripts/validate_staging_inputs.py",
                    "```",
                    "",
                    "Only a later `Ready for handoff` receipt may be trusted.",
                ]
            )
        return "\n".join(lines)

    def _summary(
        self,
        request: ProviderRunRequest,
        *,
        generated_at: datetime,
    ) -> dict[str, object]:
        credential_status = (
            "Configured"
            if self.api_key
            else "Missing (required only for explicit live mode)"
        )
        return {
            "status": "Dry run ready" if request.dry_run else "Blocked",
            "mode": "Dry run" if request.dry_run else "Live provider fetch",
            "provider_key": self.provider_key,
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "generated_by": request.generated_by.strip(),
            "notes": request.notes.strip(),
            "credential_environment_variable": API_KEY_ENV,
            "credential_status": credential_status,
            "source_url": self.source_url,
            "sport_key": self.sport_key,
            "regions": self.regions,
            "bookmakers": self.bookmakers,
            "featured_markets_requested": ["h2h", "totals"],
            "network_request_made": False,
            "overwrite_staging": request.overwrite_staging,
            "fixture_count": 0,
            "odds_row_count": 0,
            "market_counts": {"1x2": 0, "total_2_5": 0, "btts": 0},
            "raw_source_path": "",
            "raw_source_checksum_sha256": "",
            "source_files": {},
            "staging_files": {},
            "provider_response_headers": {},
            "files_written": [],
            "blockers": [],
            "warnings": [],
            "next_step": (
                f"Set `{API_KEY_ENV}` in the environment, review provider policy, "
                "then rerun with `--live`."
            ),
            "staging_validation_run": False,
            "manual_files_edited": False,
            "staging_promoted": False,
            "secrets_written_or_printed": False,
            "cron_enabled": False,
            "bets_placed": False,
        }

    def run(self, request: ProviderRunRequest) -> dict[str, object]:
        generated_at = request.run_at or datetime.now().astimezone()
        root, staging_dir, output_dir = self._directories(request)
        summary = self._summary(request, generated_at=generated_at)
        json_report, markdown_report = self._report_paths(output_dir)
        result: dict[str, object] = {
            "summary": summary,
            "report_json": json_report,
            "report_markdown": markdown_report,
            "staging_odds": staging_dir / STAGING_ODDS_FILENAME,
            "staging_fixtures": staging_dir / STAGING_FIXTURES_FILENAME,
            "provenance": staging_dir / PROVENANCE_FILENAME,
        }

        try:
            self._validate_configuration()
            if generated_at.tzinfo is None:
                raise ProviderAdapterError(
                    "Provider run timestamp must include a timezone."
                )
            if not request.generated_by.strip():
                raise ProviderAdapterError("generated_by cannot be blank.")
            if self.api_key and (
                self.api_key in request.generated_by or self.api_key in request.notes
            ):
                if self.api_key in request.generated_by:
                    summary["generated_by"] = "[redacted unsafe value]"
                if self.api_key in request.notes:
                    summary["notes"] = "[redacted unsafe value]"
                raise ProviderAdapterError(
                    "Provider notes/generator text appears to contain the API "
                    "credential. Remove it before rerunning."
                )
        except ProviderAdapterError as exc:
            summary["status"] = "Blocked"
            summary["blockers"] = [str(exc)]
            summary["next_step"] = "Fix the provider configuration, then rerun dry-run."
            self._save_reports(summary, output_dir)
            return result

        stable_targets = {
            "source odds": staging_dir / SOURCE_ODDS_FILENAME,
            "source fixtures": staging_dir / SOURCE_FIXTURES_FILENAME,
            "staging odds": staging_dir / STAGING_ODDS_FILENAME,
            "staging fixtures": staging_dir / STAGING_FIXTURES_FILENAME,
            "provenance": staging_dir / PROVENANCE_FILENAME,
        }
        path_blockers: list[str] = []
        for label, target in stable_targets.items():
            _, _, blockers = validate_output_path(
                target,
                repository_root=root,
                allowed_parent=staging_dir,
                suffixes=(".csv", ".json"),
            )
            path_blockers.extend(f"{label}: {item}" for item in blockers)
            if target.exists() and not request.overwrite_staging:
                path_blockers.append(
                    f"Provider output already exists: "
                    f"`{display_repository_path(target, root)}`. Review it first; "
                    "use `--overwrite-staging` only for intentional replacement."
                )
        if path_blockers:
            summary["status"] = "Blocked"
            summary["blockers"] = list(dict.fromkeys(path_blockers))
            summary["next_step"] = (
                "Review existing staging evidence. Use `--overwrite-staging` only "
                "when replacing the complete bundle is intentional."
            )
            self._save_reports(summary, output_dir)
            return result

        if request.dry_run:
            if not self.api_key:
                summary["warnings"] = [
                    f"`{API_KEY_ENV}` is not configured. Dry-run made no network "
                    "request; live mode will block until the secret is available."
                ]
            self._save_reports(summary, output_dir)
            return result

        try:
            if not self.api_key:
                raise MissingProviderCredentialsError(
                    f"Live mode requires `{API_KEY_ENV}` from the environment, a "
                    "gitignored local `.env`, or a GitHub Secret. Never pass the "
                    "key as a command argument or commit it."
                )
            summary["network_request_made"] = True
            events, raw_content, response_headers = self._fetch_events()
            if self.api_key.encode("utf-8") in raw_content:
                raise MalformedProviderResponseError(
                    "The provider response appears to echo the API credential. "
                    "No raw or staging files were written."
                )
            raw_checksum = sha256_bytes(raw_content)
            run_slug = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            raw_target = (
                staging_dir
                / "raw"
                / f"{run_slug}_{raw_checksum[:12]}_odds_api_response.json"
            )
            _, raw_display, raw_blockers = validate_output_path(
                raw_target,
                repository_root=root,
                allowed_parent=staging_dir / "raw",
                suffixes=(".json",),
            )
            if raw_blockers:
                raise ProviderAdapterError(" ".join(raw_blockers))
            odds, fixtures, warnings, market_counts = _normalize_provider_events(
                events,
                generated_at=generated_at,
            )
            odds_bytes = _csv_bytes(odds, ODDS_COLUMNS)
            fixtures_bytes = _csv_bytes(fixtures, FIXTURE_COLUMNS)
            odds_checksum = sha256_bytes(odds_bytes)
            fixtures_checksum = sha256_bytes(fixtures_bytes)
            source_odds = stable_targets["source odds"]
            source_fixtures = stable_targets["source fixtures"]
            staging_odds = stable_targets["staging odds"]
            staging_fixtures = stable_targets["staging fixtures"]
            provenance_target = stable_targets["provenance"]
            provenance = {
                "schema_version": PROVENANCE_SCHEMA_VERSION,
                "provider_name": self.provider_name,
                "provider_type": self.provider_type,
                "source_file_path": display_repository_path(source_odds, root),
                "source_checksum_sha256": odds_checksum,
                "source_url": self.source_url,
                "raw_source_checksum_sha256": raw_checksum,
                "raw_source_files": {
                    "odds_api_response": {
                        "path": raw_display,
                        "checksum_sha256": raw_checksum,
                        "size_bytes": len(raw_content),
                    }
                },
                "source_files": {
                    "current_odds": {
                        "path": display_repository_path(source_odds, root),
                        "checksum_sha256": odds_checksum,
                        "row_count": int(len(odds)),
                    },
                    "upcoming_fixtures": {
                        "path": display_repository_path(source_fixtures, root),
                        "checksum_sha256": fixtures_checksum,
                        "row_count": int(len(fixtures)),
                    },
                },
                "staging_files": {
                    "current_odds": {
                        "path": display_repository_path(staging_odds, root),
                        "checksum_sha256": odds_checksum,
                        "row_count": int(len(odds)),
                    },
                    "upcoming_fixtures": {
                        "path": display_repository_path(staging_fixtures, root),
                        "checksum_sha256": fixtures_checksum,
                        "row_count": int(len(fixtures)),
                    },
                },
                "generated_by": request.generated_by.strip(),
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "notes": request.notes.strip(),
            }
            provenance_bytes = (
                json.dumps(provenance, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            payloads = {
                source_odds: odds_bytes,
                source_fixtures: fixtures_bytes,
                staging_odds: odds_bytes,
                staging_fixtures: fixtures_bytes,
                provenance_target: provenance_bytes,
                raw_target: raw_content,
            }
            atomic_write_bundle(payloads, overwrite=request.overwrite_staging)
            mismatches = [
                display_repository_path(path, root)
                for path, content in payloads.items()
                if file_sha256(path) != sha256_bytes(content)
            ]
            if mismatches:
                raise ProviderAdapterError(
                    "Provider output checksum verification failed for: "
                    + ", ".join(mismatches)
                )
        except ProviderAdapterError as exc:
            summary["status"] = "Blocked"
            summary["blockers"] = [str(exc)]
            summary["next_step"] = (
                "Review the provider configuration/response, then rerun dry-run. "
                "No model or manual files were changed."
            )
            self._save_reports(summary, output_dir)
            return result
        except OSError as exc:
            summary["status"] = "Failed"
            summary["blockers"] = [
                f"Provider evidence could not be written safely ({type(exc).__name__})."
            ]
            summary["next_step"] = (
                "Inspect staging permissions and existing files, then rerun dry-run."
            )
            self._save_reports(summary, output_dir)
            return result

        summary.update(
            {
                "status": "Completed",
                "fixture_count": int(len(fixtures)),
                "odds_row_count": int(len(odds)),
                "market_counts": market_counts,
                "raw_source_path": raw_display,
                "raw_source_checksum_sha256": raw_checksum,
                "source_files": {
                    "current_odds": display_repository_path(source_odds, root),
                    "upcoming_fixtures": display_repository_path(
                        source_fixtures, root
                    ),
                },
                "staging_files": {
                    "current_odds": display_repository_path(staging_odds, root),
                    "upcoming_fixtures": display_repository_path(
                        staging_fixtures, root
                    ),
                    "provenance": display_repository_path(provenance_target, root),
                },
                "provider_response_headers": response_headers,
                "files_written": [
                    display_repository_path(path, root) for path in payloads
                ],
                "warnings": warnings
                + [
                    "Staging validation was not run automatically. The checked-in "
                    "provider policy must explicitly allow `the_odds_api` before "
                    "this bundle can become Ready for handoff."
                ],
                "next_step": (
                    "Run `python scripts/validate_staging_inputs.py`. Trust the "
                    "bundle only if that separate report says `Ready for handoff`."
                ),
            }
        )
        self._save_reports(summary, output_dir)
        return result
