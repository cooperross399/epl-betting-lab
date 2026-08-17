"""Tests for gitignored `.env` loading of provider credentials.

These tests exist to prove the loader cannot leak a credential: not through the
returned object, not through terminal output, and not through any file written
during a provider run.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from epl_betting_lab.providers.env_file import (
    ENV_FILENAME,
    PROVIDER_ENV_ALLOWLIST,
    ProviderEnvLoadResult,
    env_file_path,
    load_provider_env,
)
from epl_betting_lab.providers.odds_api_staging_provider import (
    API_KEY_ENV,
    OddsApiStagingProvider,
)
from epl_betting_lab.providers.base import ProviderRunRequest

from datetime import datetime, timezone


SECRET = "env-file-secret-that-must-never-be-written"
RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _write_env(root: Path, body: str, mode: int = 0o600) -> Path:
    path = root / ENV_FILENAME
    path.write_text(body, encoding="utf-8")
    path.chmod(mode)
    return path


def test_missing_env_file_is_a_safe_no_op(tmp_path: Path) -> None:
    environment: dict[str, str] = {}
    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert result.file_present is False
    assert result.loaded_names == ()
    assert environment == {}
    assert "not found" in result.summary_line()


def test_allowlisted_credential_is_loaded_when_absent(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    environment: dict[str, str] = {}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert result.loaded_names == (API_KEY_ENV,)
    assert environment[API_KEY_ENV] == SECRET


def test_exported_environment_value_always_wins(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    environment = {API_KEY_ENV: "already-exported-value"}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert environment[API_KEY_ENV] == "already-exported-value"
    assert result.loaded_names == ()
    assert result.already_set_names == (API_KEY_ENV,)


def test_non_provider_names_are_never_applied(tmp_path: Path) -> None:
    _write_env(
        tmp_path,
        f"{API_KEY_ENV}={SECRET}\nPATH=/attacker/bin\nAWS_SECRET_ACCESS_KEY=nope\n",
    )
    environment: dict[str, str] = {}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert set(environment) == {API_KEY_ENV}
    assert "PATH" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert result.ignored_names == ("AWS_SECRET_ACCESS_KEY", "PATH")


def test_allowlist_stays_minimal() -> None:
    # A widening of this list must be a deliberate, reviewed change.
    assert PROVIDER_ENV_ALLOWLIST == (
        "EPL_ODDS_API_KEY",
        "EPL_ODDS_API_BASE_URL",
    )


def test_blank_value_does_not_overwrite_or_register(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}=\n")
    environment: dict[str, str] = {}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert environment == {}
    assert result.loaded_names == ()


def test_world_readable_env_file_warns_without_revealing_value(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n", mode=0o644)
    environment: dict[str, str] = {}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    assert any("chmod 600" in warning for warning in result.warnings)
    assert all(SECRET not in warning for warning in result.warnings)


def test_result_object_never_carries_the_secret(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    environment: dict[str, str] = {}

    result = load_provider_env(repository_root=tmp_path, environment=environment)

    # Every representation an operator or log could capture must be clean.
    assert SECRET not in repr(result)
    assert SECRET not in str(result)
    assert SECRET not in result.summary_line()
    assert SECRET not in json.dumps(asdict(result), default=str)
    assert SECRET not in "".join(result.warnings)


def test_summary_line_reports_names_only(tmp_path: Path) -> None:
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    environment: dict[str, str] = {}

    line = load_provider_env(
        repository_root=tmp_path, environment=environment
    ).summary_line()

    assert API_KEY_ENV in line
    assert "values hidden" in line
    assert SECRET not in line


def test_env_file_path_points_at_repository_root(tmp_path: Path) -> None:
    assert env_file_path(tmp_path) == tmp_path / ENV_FILENAME


def test_unreadable_env_file_does_not_raise(tmp_path: Path) -> None:
    path = _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    path.chmod(0o000)
    try:
        result = load_provider_env(repository_root=tmp_path, environment={})
    finally:
        path.chmod(0o600)

    assert result.file_present is True
    assert SECRET not in "".join(result.warnings)


def test_env_sourced_secret_is_not_written_by_a_provider_dry_run(
    tmp_path: Path, capsys
) -> None:
    """End-to-end: a credential loaded from `.env` reaches the provider but
    never reaches stdout or any file the provider writes."""
    _write_env(tmp_path, f"{API_KEY_ENV}={SECRET}\n")
    environment: dict[str, str] = {}

    load_result = load_provider_env(repository_root=tmp_path, environment=environment)
    assert load_result.loaded_names == (API_KEY_ENV,)

    calls: list[object] = []

    def _never_called(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("dry run must not make a network request")

    provider = OddsApiStagingProvider(
        environment=environment,
        requester=_never_called,
    )
    # The credential really is visible to the provider...
    assert provider.api_key == SECRET

    provider.run(
        ProviderRunRequest(
            dry_run=True,
            repository_root=tmp_path,
            run_at=RUN_AT,
            generated_by="test suite",
            notes="Env-file dry run.",
        )
    )

    assert calls == []
    print(load_result.summary_line())
    assert SECRET not in capsys.readouterr().out

    # ...but appears in none of the files produced by the run.
    written = [p for p in tmp_path.rglob("*") if p.is_file() and p.name != ENV_FILENAME]
    assert written, "dry run should still write report evidence"
    for path in written:
        assert SECRET not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_result_defaults_are_immutable_and_empty() -> None:
    result = ProviderEnvLoadResult(path=Path("/tmp/.env"))

    assert result.loaded_names == ()
    assert result.warnings == ()
    assert result.file_present is False
