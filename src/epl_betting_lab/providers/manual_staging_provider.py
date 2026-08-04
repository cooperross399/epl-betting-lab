from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT, STAGING_DIR


SOURCE_ODDS_FILENAME = "source_current_odds.csv"
SOURCE_FIXTURES_FILENAME = "source_upcoming_fixtures.csv"
STAGING_ODDS_FILENAME = "current_odds_staging.csv"
STAGING_FIXTURES_FILENAME = "upcoming_fixtures_staging.csv"
PROVENANCE_FILENAME = "staging_provenance.json"
REPORT_JSON_FILENAME = "manual_staging_provider_report.json"
REPORT_MARKDOWN_FILENAME = "manual_staging_provider_report.md"
PROVENANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SourceInspection:
    label: str
    path: Path
    display_path: str
    path_safe: bool
    exists: bool
    readable: bool
    row_count: int
    size_bytes: int
    checksum_sha256: str
    blockers: tuple[str, ...]
    content: bytes


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return str(path)


def _contains_symlink(path: Path, repository_root: Path) -> bool:
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


def _checksum(content: bytes) -> str:
    return sha256(content).hexdigest()


def _file_checksum(path: Path) -> str:
    try:
        return _checksum(path.read_bytes()) if path.is_file() else ""
    except OSError:
        return ""


def _inspect_source(
    requested_path: Path,
    *,
    label: str,
    repository_root: Path,
    staging_dir: Path,
    reserved_outputs: set[Path],
) -> SourceInspection:
    candidate = (
        requested_path
        if requested_path.is_absolute()
        else repository_root / requested_path
    )
    try:
        path = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        return SourceInspection(
            label=label,
            path=candidate,
            display_path=str(candidate),
            path_safe=False,
            exists=False,
            readable=False,
            row_count=0,
            size_bytes=0,
            checksum_sha256="",
            blockers=(f"{label} path could not be resolved safely: {exc}",),
            content=b"",
        )

    display_path = _display_path(path, repository_root)
    blockers: list[str] = []
    if ".." in requested_path.parts:
        blockers.append(f"{label} cannot contain path traversal (`..`).")
    try:
        path.relative_to(staging_dir)
    except ValueError:
        blockers.append(f"{label} must stay inside `data/staging`.")
    if path.suffix.lower() != ".csv":
        blockers.append(f"{label} must use a `.csv` file path.")
    if _contains_symlink(candidate, repository_root):
        blockers.append(f"{label} cannot use a symbolic link.")
    if path in reserved_outputs:
        blockers.append(
            f"{label} cannot be one of the adapter's staging output files."
        )

    path_safe = not blockers
    exists = path.exists() if path_safe else False
    readable = False
    row_count = 0
    content = b""
    checksum = ""
    size_bytes = 0
    if path_safe and not exists:
        blockers.append(f"{label} is missing: `{display_path}`.")
    elif path_safe and not path.is_file():
        blockers.append(f"{label} is not a regular file: `{display_path}`.")
    elif path_safe:
        try:
            content = path.read_bytes()
            size_bytes = len(content)
            checksum = _checksum(content)
            if not content:
                blockers.append(f"{label} is empty: `{display_path}`.")
            else:
                frame = pd.read_csv(
                    BytesIO(content),
                    dtype=str,
                    keep_default_na=False,
                )
                readable = True
                row_count = int(len(frame))
                if frame.empty:
                    blockers.append(
                        f"{label} has headers but no data rows: `{display_path}`."
                    )
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            blockers.append(f"{label} could not be read as CSV: {exc}")

    return SourceInspection(
        label=label,
        path=path,
        display_path=display_path,
        path_safe=path_safe,
        exists=exists,
        readable=readable,
        row_count=row_count,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        blockers=tuple(dict.fromkeys(blockers)),
        content=content,
    )


def _source_summary(source: SourceInspection) -> dict[str, object]:
    return {
        "path": source.display_path,
        "path_safe": source.path_safe,
        "exists": source.exists,
        "readable": source.readable,
        "row_count": source.row_count,
        "size_bytes": source.size_bytes,
        "checksum_sha256": source.checksum_sha256,
        "blockers": list(source.blockers),
    }


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


def _write_bundle(
    payloads: dict[Path, bytes],
    *,
    overwrite: bool,
) -> None:
    temporary_paths: dict[Path, Path | None] = {}
    newly_created: list[Path] = []
    try:
        for target, content in payloads.items():
            temporary_paths[target] = _temporary_file(target, content)

        if not overwrite:
            collisions = [target for target in payloads if target.exists()]
            if collisions:
                names = ", ".join(target.name for target in collisions)
                raise FileExistsError(
                    f"Staging output appeared before write: {names}. Rerun preview."
                )
            try:
                for target, temporary_path in temporary_paths.items():
                    os.link(temporary_path, target)
                    newly_created.append(target)
            except OSError:
                for target in newly_created:
                    target.unlink(missing_ok=True)
                raise
        else:
            for target, temporary_path in temporary_paths.items():
                if temporary_path is None:
                    continue
                os.replace(temporary_path, target)
                temporary_paths[target] = None
    finally:
        for temporary_path in temporary_paths.values():
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def _write_report_file(path: Path, content: bytes) -> None:
    temporary_path = _temporary_file(path, content)
    try:
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _render_report(summary: dict[str, object]) -> str:
    source_rows = []
    for label, source in summary["source_files"].items():
        source_rows.append(
            {
                "source": label,
                "path": source["path"],
                "rows": source["row_count"],
                "readable": source["readable"],
                "sha256": source["checksum_sha256"] or "not available",
            }
        )
    staging_rows = []
    for label, staging_file in summary["staging_files"].items():
        staging_rows.append(
            {
                "output": label,
                "path": staging_file["path"],
                "rows": staging_file.get("row_count", ""),
                "state": (
                    "Written" if staging_file.get("written") else "Not written"
                ),
                "sha256": staging_file.get("checksum_sha256", "")
                or "not available",
            }
        )
    blockers = list(summary["blockers"])
    lines = [
        "# Manual Staging Provider Run",
        "",
        (
            "This controlled adapter copies prepared source CSVs into staging and "
            "writes provenance. It does not validate betting data, edit production "
            "or manual files, fabricate odds, place bets, promote files, or enable cron."
        ),
        "",
        "## Result",
        "",
        f"- Status: **{summary['status']}**",
        f"- Generated at: {summary['generated_at']}",
        (
            f"- Provider: **{summary['provider_name']}** "
            f"({summary['provider_type']})"
        ),
        f"- Generated by: {summary['generated_by']}",
        f"- Mode: **{'Dry run' if summary['dry_run'] else 'Write staging'}**",
        (
            "- Existing staging overwrite requested: "
            f"**{'Yes' if summary['overwrite_staging'] else 'No'}**"
        ),
        f"- Next step: {summary['next_step']}",
        "",
        "## Prepared sources",
        "",
        pd.DataFrame(source_rows).to_markdown(index=False),
        "",
        "## Staging outputs",
        "",
        pd.DataFrame(staging_rows).to_markdown(index=False),
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in blockers] or ["- None."])
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "- Only files under `data/staging/` were eligible for adapter writes.",
            "- `data/manual/` and model code were not changed.",
            "- No odds were generated or inferred.",
            "- Staging validation was not bypassed or run automatically.",
            "- Cron remains disabled.",
        ]
    )
    if summary["status"] == "Completed":
        lines.extend(
            [
                "",
                "## Validate next",
                "",
                "```bash",
                "python scripts/validate_staging_inputs.py",
                "```",
                "",
                (
                    "Only a later `Ready for handoff` staging validation receipt "
                    "makes these files eligible for the manual GitHub workflow."
                ),
            ]
        )
    elif summary["status"] == "Dry run ready":
        lines.extend(
            [
                "",
                "## Write only after review",
                "",
                "```bash",
                "python scripts/run_provider_staging.py --provider manual --live",
                "```",
                "",
                "The live command still refuses existing staging outputs unless "
                "`--overwrite-staging` is explicitly supplied.",
            ]
        )
    return "\n".join(lines)


def run_manual_staging_provider(
    *,
    odds_source_path: Path | None = None,
    fixtures_source_path: Path | None = None,
    provider_name: str = "manual_reviewed",
    generated_by: str = "scripts/run_manual_staging_provider.py",
    notes: str = "Controlled manual staging provider run.",
    dry_run: bool = False,
    overwrite_staging: bool = False,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    """Copy prepared CSVs into staging without touching production/manual data."""
    root = (repository_root or PROJECT_ROOT).resolve()
    staging_candidate = root / "data" / "staging"
    output_candidate = root / "data" / "outputs"
    if _contains_symlink(staging_candidate, root):
        raise ValueError("The project `data/staging` directory cannot be a symbolic link.")
    if _contains_symlink(output_candidate, root):
        raise ValueError("The project `data/outputs` directory cannot be a symbolic link.")
    staging_dir = staging_candidate.resolve()
    output_dir = output_candidate.resolve()
    try:
        staging_dir.relative_to(root)
        output_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Provider adapter outputs must stay inside the repository."
        ) from exc
    if repository_root is None and (
        staging_dir != STAGING_DIR.resolve()
        or output_dir != OUTPUTS_DIR.resolve()
    ):
        raise ValueError("Provider adapter outputs must stay in project data directories.")

    generated_at = run_at or datetime.now().astimezone()
    blockers: list[str] = []
    if generated_at.tzinfo is None:
        blockers.append("Provider run timestamp must include a timezone.")
    provider_name = provider_name.strip()
    generated_by = generated_by.strip()
    if not provider_name:
        blockers.append("provider_name cannot be blank.")
    if not generated_by:
        blockers.append("generated_by cannot be blank.")
    odds_target = staging_dir / STAGING_ODDS_FILENAME
    fixtures_target = staging_dir / STAGING_FIXTURES_FILENAME
    provenance_target = staging_dir / PROVENANCE_FILENAME
    reserved_outputs = {
        odds_target.resolve(strict=False),
        fixtures_target.resolve(strict=False),
        provenance_target.resolve(strict=False),
    }
    odds_source = _inspect_source(
        odds_source_path or staging_dir / SOURCE_ODDS_FILENAME,
        label="Current odds source",
        repository_root=root,
        staging_dir=staging_dir,
        reserved_outputs=reserved_outputs,
    )
    fixtures_source = _inspect_source(
        fixtures_source_path or staging_dir / SOURCE_FIXTURES_FILENAME,
        label="Upcoming fixtures source",
        repository_root=root,
        staging_dir=staging_dir,
        reserved_outputs=reserved_outputs,
    )
    blockers.extend(odds_source.blockers)
    blockers.extend(fixtures_source.blockers)

    staging_targets = (odds_target, fixtures_target, provenance_target)
    for target in staging_targets:
        if target.is_symlink():
            blockers.append(f"Staging output cannot be a symbolic link: `{target.name}`.")
        elif target.exists() and not target.is_file():
            blockers.append(f"Staging output is not a regular file: `{target.name}`.")
        elif target.exists() and not overwrite_staging:
            blockers.append(
                f"Staging output already exists: `{target.name}`. Review it first, "
                "then use `--overwrite-staging` only when replacement is intentional."
            )

    source_files = {
        "current_odds": _source_summary(odds_source),
        "upcoming_fixtures": _source_summary(fixtures_source),
    }
    timestamp = generated_at.isoformat(timespec="seconds")
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "provider_name": provider_name,
        "provider_type": "manual_upload",
        "source_file_path": odds_source.display_path,
        "source_checksum_sha256": odds_source.checksum_sha256,
        "source_files": {
            "current_odds": {
                "path": odds_source.display_path,
                "checksum_sha256": odds_source.checksum_sha256,
                "row_count": odds_source.row_count,
            },
            "upcoming_fixtures": {
                "path": fixtures_source.display_path,
                "checksum_sha256": fixtures_source.checksum_sha256,
                "row_count": fixtures_source.row_count,
            },
        },
        "staging_files": {
            "current_odds": {
                "path": _display_path(odds_target, root),
                "checksum_sha256": odds_source.checksum_sha256,
                "row_count": odds_source.row_count,
            },
            "upcoming_fixtures": {
                "path": _display_path(fixtures_target, root),
                "checksum_sha256": fixtures_source.checksum_sha256,
                "row_count": fixtures_source.row_count,
            },
        },
        "generated_by": generated_by,
        "generated_at": timestamp,
        "notes": notes.strip(),
    }
    provenance_bytes = (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

    status = "Blocked" if blockers else ("Dry run ready" if dry_run else "Completed")
    files_written: list[str] = []
    if not blockers and not dry_run:
        payloads = {
            odds_target: odds_source.content,
            fixtures_target: fixtures_source.content,
            provenance_target: provenance_bytes,
        }
        try:
            _write_bundle(payloads, overwrite=overwrite_staging)
            files_written = [_display_path(path, root) for path in payloads]
        except OSError as exc:
            status = "Failed"
            blockers.append(f"Staging bundle could not be written safely: {exc}")

    staging_files = {
        "current_odds": {
            "path": _display_path(odds_target, root),
            "row_count": odds_source.row_count,
            "written": _display_path(odds_target, root) in files_written,
            "checksum_sha256": _file_checksum(odds_target),
        },
        "upcoming_fixtures": {
            "path": _display_path(fixtures_target, root),
            "row_count": fixtures_source.row_count,
            "written": _display_path(fixtures_target, root) in files_written,
            "checksum_sha256": _file_checksum(fixtures_target),
        },
        "provenance": {
            "path": _display_path(provenance_target, root),
            "row_count": "",
            "written": _display_path(provenance_target, root) in files_written,
            "checksum_sha256": _file_checksum(provenance_target),
        },
    }
    if status == "Completed" and (
        staging_files["current_odds"]["checksum_sha256"]
        != odds_source.checksum_sha256
        or staging_files["upcoming_fixtures"]["checksum_sha256"]
        != fixtures_source.checksum_sha256
    ):
        status = "Failed"
        blockers.append("A staging output checksum did not match its source file.")

    if status == "Completed":
        next_step = (
            "Run `python scripts/validate_staging_inputs.py`, review the report, "
            "and use only a `Ready for handoff` receipt."
        )
    elif status == "Dry run ready":
        next_step = (
            "Review this preview, then run `python scripts/run_provider_staging.py "
            "--provider manual --live` to write staging intentionally."
        )
    elif any("already exists" in item for item in blockers):
        next_step = (
            "Review the existing staging files. Rerun with `--overwrite-staging` "
            "only if replacing all three staging outputs is intentional."
        )
    else:
        next_step = "Fix the listed source/path issues, then rerun the adapter."

    summary: dict[str, object] = {
        "status": status,
        "generated_at": timestamp,
        "provider_name": provider_name,
        "provider_type": "manual_upload",
        "generated_by": generated_by,
        "notes": notes.strip(),
        "dry_run": dry_run,
        "overwrite_staging": overwrite_staging,
        "source_files": source_files,
        "staging_files": staging_files,
        "files_written": files_written,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": [],
        "next_step": next_step,
        "staging_validation_run": False,
        "manual_files_edited": False,
        "cron_enabled": False,
        "bets_placed": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / REPORT_JSON_FILENAME
    markdown_path = output_dir / REPORT_MARKDOWN_FILENAME
    _write_report_file(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    _write_report_file(markdown_path, _render_report(summary).encode("utf-8"))
    return {
        "summary": summary,
        "report_json": json_path,
        "report_markdown": markdown_path,
        "staging_odds": odds_target,
        "staging_fixtures": fixtures_target,
        "provenance": provenance_target,
    }
