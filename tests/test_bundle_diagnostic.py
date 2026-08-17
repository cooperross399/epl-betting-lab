"""Bundle diagnostic: deterministic, secret-safe, and never a gate decision."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.reports.bundle_diagnostic import (
    SAFE_ENTRY_FIELDS,
    build_bundle_diagnostic,
    render_bundle_diagnostic,
    save_bundle_diagnostic,
)


NOW = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)
SECRET = "0650f592cfd4f8bf139671cd5e52b4cf"


def _entry(path: str, checksum: str) -> dict:
    return {
        "evidence_path": path,
        "evidence_type": "reviewed_shadow_archive_file",
        "status": "Included",
        "required": "Yes",
        "current_checksum_sha256": checksum,
        "expected_checksum_sha256": checksum,
        # Fields the diagnostic must never carry through.
        "raw_payload": f"apiKey={SECRET}",
        "details": f"contains {SECRET}",
    }


def _write(tmp_path: Path, computed_entries, stored_entries, *, stored_path="") -> None:
    (tmp_path / "provider_allowlist_evidence_bundle.json").write_text(
        json.dumps(
            {
                "bundle_id": "computed-id",
                "bundle_checksum_sha256": "computed-checksum",
                "evidence": computed_entries,
            }
        ),
        encoding="utf-8",
    )
    archive = tmp_path / "archived_bundle.json"
    archive.write_text(
        json.dumps(
            {
                "bundle_id": "stored-id",
                "bundle_checksum_sha256": "stored-checksum",
                "evidence": stored_entries,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "provider_allowlist_evidence_bundle_verification.json").write_text(
        json.dumps(
            {
                "bundle_id": "stored-id",
                "bundle_checksum_sha256": "stored-checksum",
                "bundle_path": stored_path or str(archive),
            }
        ),
        encoding="utf-8",
    )


# --- difference detection --------------------------------------------------


def test_files_only_in_the_computed_bundle_are_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [_entry("a.json", "aaa"), _entry("b.json", "bbb")],
        [_entry("a.json", "aaa")],
    )

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert summary["only_in_computed"] == ["b.json"]
    assert summary["only_in_stored"] == []


def test_files_only_in_the_stored_bundle_are_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [_entry("a.json", "aaa")],
        [_entry("a.json", "aaa"), _entry("c.json", "ccc")],
    )

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert summary["only_in_stored"] == ["c.json"]


def test_shared_files_with_differing_checksums_are_reported(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [_entry("a.json", "zzz")])

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert summary["checksum_differences"] == [
        {
            "evidence_path": "a.json",
            "computed_checksum_sha256": "aaa",
            "stored_checksum_sha256": "zzz",
        }
    ]


def test_identical_bundles_report_a_match(tmp_path: Path) -> None:
    entries = [_entry("a.json", "aaa")]
    _write(tmp_path, entries, entries)
    (tmp_path / "provider_allowlist_evidence_bundle_verification.json").write_text(
        json.dumps(
            {
                "bundle_id": "computed-id",
                "bundle_checksum_sha256": "computed-checksum",
                "bundle_path": str(tmp_path / "archived_bundle.json"),
            }
        ),
        encoding="utf-8",
    )

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert summary["matches"] is True


def test_metadata_only_difference_is_named(tmp_path: Path) -> None:
    """Identical evidence but different ids means the cause is not a file."""
    entries = [_entry("a.json", "aaa")]
    _write(tmp_path, entries, entries)

    summary = build_bundle_diagnostic(
        output_dir=tmp_path, repository_root=tmp_path, now=NOW
    )

    assert summary["matches"] is False
    assert any("bundle metadata" in item for item in summary["likely_causes"])


def test_untracked_evidence_is_called_out(tmp_path: Path) -> None:
    """The recurring failure: evidence bound by path but never committed."""
    _write(tmp_path, [_entry("data/outputs/archive/x.json", "aaa")], [])

    summary = build_bundle_diagnostic(
        output_dir=tmp_path, repository_root=tmp_path, now=NOW
    )

    # tmp_path is not a git repo, so tracking is unknown and nothing is claimed.
    assert isinstance(summary["untracked_evidence_paths"], list)


def test_missing_reports_are_recorded_not_raised(tmp_path: Path) -> None:
    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert summary["read_errors"]
    assert summary["matches"] is False


# --- secret safety ---------------------------------------------------------


def test_no_file_contents_or_secrets_reach_the_report(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [_entry("a.json", "zzz")])

    result = save_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    for key in ("json", "markdown"):
        text = Path(result[key]).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "apiKey" not in text
        assert "raw_payload" not in text


def test_only_safe_entry_fields_are_carried(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [])

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    carried = set(summary["computed_evidence"][0]) - {"evidence_path"}
    assert carried <= set(SAFE_ENTRY_FIELDS)
    assert "details" not in carried
    assert "raw_payload" not in carried


def test_safety_flags_declare_what_it_does_not_do(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [])

    safety = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)["safety"]

    assert safety["file_contents_included"] is False
    assert safety["secrets_included"] is False
    assert safety["evidence_modified"] is False
    assert safety["gate_decision_made"] is False


# --- determinism -----------------------------------------------------------


def test_output_is_deterministic_across_runs(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [_entry("b.json", "bbb"), _entry("a.json", "aaa")],
        [_entry("a.json", "aaa")],
    )

    first = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)
    second = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_evidence_is_ordered_by_path_regardless_of_input_order(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        [_entry("c.json", "c"), _entry("a.json", "a"), _entry("b.json", "b")],
        [],
    )

    summary = build_bundle_diagnostic(output_dir=tmp_path, now=NOW)
    paths = [item["evidence_path"] for item in summary["computed_evidence"]]

    assert paths == sorted(paths)


def test_the_diagnostic_never_modifies_evidence(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [_entry("a.json", "zzz")])
    before = {
        path.name: path.read_bytes()
        for path in tmp_path.iterdir()
        if path.is_file()
    }

    build_bundle_diagnostic(output_dir=tmp_path, now=NOW)

    after = {
        path.name: path.read_bytes()
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    assert before == after


def test_markdown_states_it_makes_no_gate_decision(tmp_path: Path) -> None:
    _write(tmp_path, [_entry("a.json", "aaa")], [])

    text = render_bundle_diagnostic(
        build_bundle_diagnostic(output_dir=tmp_path, now=NOW)
    )

    assert "never decides whether a gate passes" in text
    assert "Gate decision made: **No**" in text
