from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping


SOURCE_ODDS_FILENAME = "source_current_odds.csv"
SOURCE_FIXTURES_FILENAME = "source_upcoming_fixtures.csv"
STAGING_ODDS_FILENAME = "current_odds_staging.csv"
STAGING_FIXTURES_FILENAME = "upcoming_fixtures_staging.csv"
PROVENANCE_FILENAME = "staging_provenance.json"


class ProviderAdapterError(RuntimeError):
    """Base error for provider setup, response, and staging failures."""


class UnknownProviderError(ProviderAdapterError):
    """Raised when the requested provider is not registered."""


class MissingProviderCredentialsError(ProviderAdapterError):
    """Raised when live mode is requested without environment credentials."""


class ProviderUnavailableError(ProviderAdapterError):
    """Raised when a configured provider cannot be reached safely."""


class MalformedProviderResponseError(ProviderAdapterError):
    """Raised when a provider response cannot be trusted or normalized."""


class EmptyProviderResponseError(ProviderAdapterError):
    """Raised when a provider returns no usable fixtures or odds."""


@dataclass(frozen=True)
class ProviderRunRequest:
    """Safe, provider-independent controls for one staging run."""

    dry_run: bool = True
    overwrite_staging: bool = False
    repository_root: Path | None = None
    run_at: datetime | None = None
    generated_by: str = "scripts/run_provider_staging.py"
    notes: str = "Provider staging adapter run."


class BaseStagingProvider(ABC):
    """Interface for adapters that prepare evidence for staging validation."""

    provider_key: str
    provider_name: str
    provider_type: str

    @property
    def credential_environment_variables(self) -> tuple[str, ...]:
        return ()

    @abstractmethod
    def run(self, request: ProviderRunRequest) -> dict[str, object]:
        """Prepare staging evidence without validating or promoting it."""

    def public_configuration(self) -> Mapping[str, object]:
        """Return non-secret adapter metadata suitable for reports and logs."""
        return {
            "provider_key": self.provider_key,
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "credential_environment_variables": list(
                self.credential_environment_variables
            ),
        }


def sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_repository_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return str(path)


def path_contains_symlink(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.absolute().relative_to(repository_root)
    except ValueError:
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def validate_output_path(
    path: Path,
    *,
    repository_root: Path,
    allowed_parent: Path,
    suffixes: tuple[str, ...],
) -> tuple[Path, str, list[str]]:
    """Resolve a generated output and keep it inside its reviewed data folder."""
    candidate = path if path.is_absolute() else repository_root / path
    blockers: list[str] = []
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        return candidate, str(candidate), [f"Output path could not be resolved: {exc}"]

    display_path = display_repository_path(resolved, repository_root)
    try:
        resolved.relative_to(repository_root)
        resolved.relative_to(allowed_parent.resolve())
    except ValueError:
        blockers.append(
            f"Provider output must stay inside "
            f"`{display_repository_path(allowed_parent.resolve(), repository_root)}`."
        )
    if resolved.suffix.lower() not in suffixes:
        allowed = ", ".join(suffixes)
        blockers.append(f"Provider output must use one of these suffixes: {allowed}.")
    if path_contains_symlink(candidate.absolute(), repository_root):
        blockers.append(f"Provider output cannot use a symbolic link: `{display_path}`.")
    if resolved.exists() and not resolved.is_file():
        blockers.append(f"Provider output is not a regular file: `{display_path}`.")
    return resolved, display_path, blockers


def _temporary_file(target: Path, content: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def atomic_write_bundle(
    payloads: Mapping[Path, bytes],
    *,
    overwrite: bool,
) -> None:
    """Write a provider bundle with collision protection and atomic file moves."""
    collisions = [target for target in payloads if target.exists()]
    if collisions and not overwrite:
        names = ", ".join(target.name for target in collisions)
        raise FileExistsError(
            f"Provider outputs already exist: {names}. Review them before using "
            "`--overwrite-staging`."
        )

    temporary_paths: dict[Path, Path | None] = {}
    newly_created: list[Path] = []
    try:
        for target, content in payloads.items():
            temporary_paths[target] = _temporary_file(target, content)

        if overwrite:
            for target, temporary_path in temporary_paths.items():
                if temporary_path is None:
                    continue
                os.replace(temporary_path, target)
                temporary_paths[target] = None
        else:
            try:
                for target, temporary_path in temporary_paths.items():
                    if temporary_path is None:
                        continue
                    os.link(temporary_path, target)
                    newly_created.append(target)
            except OSError:
                for target in newly_created:
                    target.unlink(missing_ok=True)
                raise
    finally:
        for temporary_path in temporary_paths.values():
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def atomic_write_report(path: Path, content: bytes) -> None:
    """Replace one generated report without exposing a partial file."""
    temporary_path = _temporary_file(path, content)
    try:
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
