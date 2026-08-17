#!/usr/bin/env python
"""Diagnose a computed-vs-stored provider evidence bundle mismatch.

Diagnostic only. Reports paths, checksums, and counts so a CI failure can be
explained instead of guessed at. Never includes file contents, never modifies
evidence, never relaxes a check, and never decides whether a gate passes.

Exit code is always 0: this explains a failure, it does not add one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.bundle_diagnostic import save_bundle_diagnostic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="Repository root used to resolve evidence paths and git tracking.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Provider Evidence Bundle Diagnostic")
    print(
        "Diagnostic only: paths, checksums, and counts. No file contents, no "
        "secrets, no evidence changes, no gate decision."
    )

    result = save_bundle_diagnostic(
        output_dir=args.output_dir, repository_root=args.repository_root
    )
    summary = result["summary"]

    print(f"Bundles match: {'Yes' if summary['matches'] else 'No'}")
    print(f"Computed bundle id: {summary['computed_bundle_id'] or 'none'}")
    print(f"Stored bundle id:   {summary['stored_bundle_id'] or 'none'}")
    print(f"Computed checksum:  {summary['computed_bundle_checksum_sha256'] or 'none'}")
    print(f"Stored checksum:    {summary['stored_bundle_checksum_sha256'] or 'none'}")
    print(f"Stored bundle path: {summary['stored_bundle_path'] or 'none'}")
    print(
        "Stored bundle tracked by git: "
        f"{'No' if summary['stored_bundle_is_untracked'] else 'Yes'}"
    )
    print(
        f"Evidence entries: computed {summary['computed_evidence_count']}, "
        f"stored {summary['stored_evidence_count']}"
    )

    for cause in summary["likely_causes"]:
        print(f"LIKELY CAUSE: {cause}")
    for path in summary["untracked_evidence_paths"]:
        print(f"UNTRACKED EVIDENCE: {path}")
    for path in summary["only_in_computed"]:
        print(f"ONLY IN COMPUTED: {path}")
    for path in summary["only_in_stored"]:
        print(f"ONLY IN STORED: {path}")
    for item in summary["checksum_differences"]:
        print(
            f"CHECKSUM DIFFERS: {item['evidence_path']} "
            f"computed={item['computed_checksum_sha256'][:16]} "
            f"stored={item['stored_checksum_sha256'][:16]}"
        )
    for error in summary["read_errors"]:
        print(f"READ ERROR: {error}")

    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
