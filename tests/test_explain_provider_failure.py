"""Saying why the provider step stopped.

It exits non-zero for two unrelated reasons: the fetch failed, or the fetch
worked and something downstream refused the bundle. Reporting the first for the
second sent a reader looking for a network problem that was not there — a run
stopped by the Thursday cutoff announced that prices could not be refreshed
while 330 rows of freshly fetched prices sat in the bundle.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT


def _module():
    spec = importlib.util.spec_from_file_location(
        "_explain", PROJECT_ROOT / "scripts" / "explain_provider_failure.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, payload: dict) -> None:
    (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")


class TestExplain:
    def test_no_reports_at_all_falls_back(self, tmp_path: Path) -> None:
        """A run already going wrong must still be able to explain itself."""
        assert "could not be refreshed" in _module().explain(tmp_path)

    def test_a_provider_blocker_is_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "provider_shadow_verification.json",
               {"blockers": ["Receipt after the Thursday cutoff."]})

        out = _module().explain(tmp_path)

        assert "The provider run was refused" in out
        assert "Thursday cutoff" in out

    def test_a_validation_blocker_is_reported_when_the_provider_is_happy(
        self, tmp_path: Path
    ) -> None:
        """The gate that most often refuses a bundle the provider accepted."""
        _write(tmp_path, "provider_shadow_verification.json", {"blockers": []})
        _write(tmp_path, "staging_input_validation.json",
               {"handoff_gate": {"blockers": ["Not handoff eligible."]}})

        out = _module().explain(tmp_path)

        assert "Not handoff eligible." in out

    def test_blockers_nested_anywhere_are_found(self, tmp_path: Path) -> None:
        """Each report keeps them somewhere different."""
        _write(tmp_path, "provider_shadow_verification.json",
               {"provider_policy": {"blockers": ["Provider not allowlisted."]}})

        assert "Provider not allowlisted." in _module().explain(tmp_path)

    def test_structured_issues_are_read_too(self, tmp_path: Path) -> None:
        _write(tmp_path, "provider_shadow_verification.json",
               {"serious_issues": [{"detail": "Receipt too old."}]})

        assert "Receipt too old." in _module().explain(tmp_path)

    def test_repeats_are_not_printed_twice(self, tmp_path: Path) -> None:
        """Reports repeat themselves across sections."""
        _write(tmp_path, "provider_shadow_verification.json",
               {"blockers": ["Same."], "provider_policy": {"blockers": ["Same."]}})

        assert _module().explain(tmp_path).count("Same.") == 1

    def test_it_stays_to_one_line(self, tmp_path: Path) -> None:
        """It is appended to a degradation record that is read as a list."""
        _write(tmp_path, "provider_shadow_verification.json",
               {"blockers": [f"Blocker {i}." for i in range(9)]})

        assert "\n" not in _module().explain(tmp_path)

    def test_empty_blocker_lists_do_not_claim_a_refusal(self, tmp_path: Path) -> None:
        _write(tmp_path, "provider_shadow_verification.json", {"blockers": []})
        _write(tmp_path, "staging_input_validation.json", {"blockers": []})

        assert "could not be refreshed" in _module().explain(tmp_path)

    def test_unreadable_json_does_not_raise(self, tmp_path: Path) -> None:
        (tmp_path / "provider_shadow_verification.json").write_text(
            "{not json", encoding="utf-8"
        )

        assert "could not be refreshed" in _module().explain(tmp_path)


class TestTheWorkflowUsesIt:
    def test_the_degradation_record_calls_the_script(self) -> None:
        text = (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

        assert "explain_provider_failure.py" in text
        assert ">> run_degraded.txt" in text


class TestDecliningIsNotFailing:
    """The Thursday cutoff refuses receipts made after 10:00 New York.

    Scheduled runs are all before it, so only a run started by hand outside the
    window meets it — and that is the policy doing its job. Reported as a
    failure it produced a week of red runs and alarming mail, and a health
    check reasonably concluded the pipeline was broken.
    """

    def test_the_cutoff_refusal_is_expected(self) -> None:
        module = _module()

        assert module.is_expected(
            "The provider run was refused: The staging receipt was generated "
            "after the Thursday automation cutoff of 10:00 America/New_York."
        )

    def test_a_real_fetch_failure_is_not_expected(self) -> None:
        assert not _module().is_expected(_module().FALLBACK)

    def test_another_refusal_is_not_expected(self) -> None:
        """A provider that is not allowlisted is a real problem."""
        assert not _module().is_expected(
            "The provider run was refused: Provider is not allowlisted."
        )

    def test_a_validation_refusal_is_not_expected(self) -> None:
        assert not _module().is_expected(
            "The provider run was refused: Not handoff eligible."
        )

    def test_the_exit_code_marks_an_expected_refusal(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        _write(tmp_path, "provider_shadow_verification.json", {
            "blockers": ["The staging receipt was generated after the Thursday "
                         "automation cutoff of 10:00 America/New_York."]})
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "explain_provider_failure.py"),
             "--output-dir", str(tmp_path), "--expected-exit", "3"],
            capture_output=True, text=True,
        )

        assert result.returncode == 3
        assert "Thursday automation cutoff" in result.stdout

    def test_a_real_failure_exits_zero(self, tmp_path: Path) -> None:
        """Zero here means "not an expected refusal", not "everything is fine"."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "explain_provider_failure.py"),
             "--output-dir", str(tmp_path), "--expected-exit", "3"],
            capture_output=True, text=True,
        )

        assert result.returncode == 0

    def test_the_workflow_finishes_green_on_an_expected_refusal(self) -> None:
        text = (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

        assert "expected_refusal=true" in text
        assert "as expected outside the Thursday window" in text

    def test_any_other_degradation_still_goes_red(self) -> None:
        text = (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

        assert "This run was degraded" in text
        assert "exit 1" in text
