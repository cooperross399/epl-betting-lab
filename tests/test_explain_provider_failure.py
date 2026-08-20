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

        assert "explain_provider_failure.py >> run_degraded.txt" in text
