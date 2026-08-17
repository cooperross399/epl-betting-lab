"""Load provider credentials from a gitignored local `.env` file.

This module exists so a local operator can keep `EPL_ODDS_API_KEY` out of shell
history without weakening the existing credential rules. It is deliberately
narrow:

* Only the provider credential names in :data:`PROVIDER_ENV_ALLOWLIST` are read.
  Anything else in `.env` is ignored, so a stale or careless file cannot change
  unrelated process configuration.
* A real environment variable always wins. `.env` only fills gaps, so exported
  secrets and GitHub Secrets keep their precedence.
* No credential value is ever returned, printed, logged, or written to a report.
  Callers receive variable *names* only.

Provider entry points call :func:`load_provider_env`. Nothing else does.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from epl_betting_lab.config import PROJECT_ROOT


ENV_FILENAME = ".env"

# Only provider credentials may travel through `.env`. Keep this list minimal:
# every addition widens what an untrusted file can influence.
PROVIDER_ENV_ALLOWLIST: tuple[str, ...] = (
    "EPL_ODDS_API_KEY",
    "EPL_ODDS_API_BASE_URL",
)


@dataclass(frozen=True)
class ProviderEnvLoadResult:
    """Non-secret summary of a `.env` load.

    Only variable names are recorded. Values are never stored on this object so
    it stays safe to print, log, or embed in a provenance report.
    """

    path: Path
    file_present: bool = False
    loaded_names: tuple[str, ...] = ()
    already_set_names: tuple[str, ...] = ()
    ignored_names: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def summary_line(self) -> str:
        """One non-secret line suitable for terminal output."""
        if not self.file_present:
            return f"Local `{ENV_FILENAME}`: not found (using exported environment only)."
        if self.loaded_names:
            names = ", ".join(self.loaded_names)
            return f"Local `{ENV_FILENAME}`: loaded {names} (values hidden)."
        if self.already_set_names:
            names = ", ".join(self.already_set_names)
            return (
                f"Local `{ENV_FILENAME}`: {names} already set in the environment; "
                "the exported value was kept."
            )
        return f"Local `{ENV_FILENAME}`: no provider credentials found."


def env_file_path(repository_root: Path | None = None) -> Path:
    """Return the expected `.env` location without reading it."""
    root = PROJECT_ROOT if repository_root is None else Path(repository_root)
    return root / ENV_FILENAME


def _permission_warnings(path: Path) -> tuple[str, ...]:
    """Warn when `.env` is readable beyond its owner. Never reads the contents."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return ()
    if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        return (
            f"`{ENV_FILENAME}` is readable or writable beyond its owner. "
            f"Run `chmod 600 {ENV_FILENAME}` to restrict it.",
        )
    return ()


def load_provider_env(
    *,
    repository_root: Path | None = None,
    environment: dict[str, str] | None = None,
) -> ProviderEnvLoadResult:
    """Fill missing provider credentials from a gitignored `.env` file.

    Existing environment values are never overwritten and non-allowlisted names
    are never applied. Returns a non-secret summary containing names only.
    """
    path = env_file_path(repository_root)
    target = os.environ if environment is None else environment

    if not path.is_file():
        return ProviderEnvLoadResult(path=path, file_present=False)

    warnings = _permission_warnings(path)

    try:
        parsed = dotenv_values(path)
    except OSError as exc:  # unreadable file should not break a dry run
        return ProviderEnvLoadResult(
            path=path,
            file_present=True,
            warnings=warnings + (f"`{ENV_FILENAME}` could not be read: {exc.strerror}.",),
        )

    loaded: list[str] = []
    already_set: list[str] = []
    ignored: list[str] = []

    for name, value in parsed.items():
        if name not in PROVIDER_ENV_ALLOWLIST:
            ignored.append(name)
            continue
        if value is None or not value.strip():
            continue
        if target.get(name, "").strip():
            already_set.append(name)
            continue
        target[name] = value
        loaded.append(name)

    if ignored:
        warnings = warnings + (
            f"`{ENV_FILENAME}` contains non-provider entries that were ignored: "
            f"{', '.join(sorted(ignored))}.",
        )

    return ProviderEnvLoadResult(
        path=path,
        file_present=True,
        loaded_names=tuple(loaded),
        already_set_names=tuple(already_set),
        ignored_names=tuple(sorted(ignored)),
        warnings=warnings,
    )
