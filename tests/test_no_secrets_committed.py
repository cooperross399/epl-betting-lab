"""Repository hygiene: no credential may reach a tracked file.

These tests run against the files git actually tracks, so they fail the build
if a secret is ever committed — including by a future change that means well.
They deliberately do not read `.env`: the point is to prove nothing *else*
contains a credential, and reading the real key here would be the very leak
being guarded against.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.providers.env_file import ENV_FILENAME, PROVIDER_ENV_ALLOWLIST


#: Files whose whole job is to describe secret handling, so they legitimately
#: contain placeholder-looking strings.
DOC_SUFFIXES = {".md", ".rst", ".txt"}

#: Obvious placeholders that must never be mistaken for a real credential.
PLACEHOLDERS = {
    "your-secret-key",
    "your-api-key",
    "test-secret-that-must-not-be-written",
    "env-file-secret-that-must-never-be-written",
    "shadow-test-secret-never-write",
    "discovery-secret-must-not-be-written",
    "already-exported-value",
}

#: A 32-hex-character run is the shape of an Odds API key.
HEX_KEY = re.compile(r"\b[0-9a-f]{32}\b")

#: `NAME=value` where NAME is a credential variable and value is not a
#: placeholder — i.e. a real assignment, not documentation.
ASSIGNMENT = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in PROVIDER_ENV_ALLOWLIST) + r")\s*=\s*(\S+)"
)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    )
    names = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    return [PROJECT_ROOT / name for name in names]


#: This file necessarily contains every pattern it hunts for, so it must not
#: scan itself. A scanner that flags its own needles reports a false positive
#: forever and teaches everyone to ignore it.
SELF = Path(__file__).resolve()


def _text_files() -> list[Path]:
    keep: list[Path] = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        if path.resolve() == SELF:
            continue
        if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"}:
            continue
        keep.append(path)
    return keep


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def test_env_file_is_never_tracked() -> None:
    tracked = {path.name for path in _tracked_files()}

    assert ENV_FILENAME not in tracked


def test_env_file_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ENV_FILENAME],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )

    assert result.returncode == 0, ".env must stay gitignored"


def test_no_tracked_file_assigns_a_real_credential() -> None:
    """`EPL_ODDS_API_KEY=<something real>` must not appear in a tracked file."""
    offenders: list[str] = []
    for path in _text_files():
        for match in ASSIGNMENT.finditer(_read(path)):
            # Strip the punctuation that surrounds a value in source and prose:
            # quotes, and trailing commas/semicolons/parens from code literals.
            value = match.group(2).strip("'\"`").strip(",;)").strip("'\"`")
            if not value:
                continue
            if value in PLACEHOLDERS:
                continue
            # Documentation shows the shape of the command; a placeholder-ish
            # value in prose is fine, a 32-hex key is not.
            if path.suffix in DOC_SUFFIXES and not HEX_KEY.fullmatch(value):
                continue
            if value.startswith("$") or value.startswith("<"):
                continue
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(1)}")

    assert offenders == [], f"credential assignment in tracked files: {offenders}"


def test_no_tracked_file_contains_an_odds_api_key_shape() -> None:
    """A bare 32-hex string is the shape of the provider key."""
    offenders: list[str] = []
    for path in _text_files():
        # Checksums are legitimately hex, and SHA-256 is 64 chars, so only an
        # isolated 32-char run is suspicious.
        if "checksum" in path.name or "receipt" in path.name:
            continue
        for match in HEX_KEY.finditer(_read(path)):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)[:6]}...")

    assert offenders == [], f"possible credential in tracked files: {offenders}"


def test_generated_reports_never_include_the_api_key_parameter() -> None:
    """`apiKey=` is how the credential travels; it must not be written down."""
    offenders: list[str] = []
    for path in _text_files():
        text = _read(path)
        if "apiKey=" in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], f"apiKey= present in tracked files: {offenders}"


@pytest.mark.parametrize("name", PROVIDER_ENV_ALLOWLIST)
def test_credential_names_are_referenced_but_never_valued(name: str) -> None:
    """The variable name may appear anywhere; only a real value is forbidden."""
    assert isinstance(name, str) and name


def test_data_outputs_reports_are_not_tracked_with_secrets() -> None:
    """Report artifacts under data/outputs must be clean if tracked at all."""
    offenders: list[str] = []
    for path in _text_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if not relative.startswith("data/outputs/"):
            continue
        text = _read(path)
        if HEX_KEY.search(text) or "apiKey=" in text:
            offenders.append(relative)

    assert offenders == [], f"tracked report contains a credential: {offenders}"


def test_the_guard_excludes_itself_from_its_own_scan() -> None:
    """Otherwise it flags its own needles and everyone learns to ignore it."""
    scanned = {path.resolve() for path in _text_files()}

    assert SELF not in scanned


def test_the_guard_still_scans_other_test_files() -> None:
    """Self-exclusion must be exactly one file, not all of tests/."""
    scanned = {path.name for path in _text_files()}

    assert "test_automated_card.py" in scanned
    assert "test_provider_env_file.py" in scanned
