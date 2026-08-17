#!/usr/bin/env python
"""Create the provider human acceptance receipt from a GitHub PR approval.

The human act is a GitHub review or comment authored by an allowed reviewer and
containing the approval block. This command only verifies that approval and
transcribes it into the receipt the Provider Policy PR Gate requires. It cannot
author the approval: the reviewer identity comes from GitHub's API.

Fails closed on a missing phrase, an unexpected author, the wrong PR, the wrong
provider, an unapproved market, evidence that changed after approval, a review
of a superseded commit, or an approval older than the freshness window.

Never prints or writes a credential, places a bet, applies settlement, or
enables cron.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epl_betting_lab.reports.github_approval import (
    APPROVAL_PHRASE,
    DEFAULT_MAX_APPROVAL_AGE_HOURS,
    EXPECTED_PROVIDER,
    GitHubApprovalError,
    approval_template,
    fetch_pr_activity,
    verify_github_approval,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    ProviderHumanAcceptanceReceiptError,
    build_provider_human_acceptance_receipt,
    save_provider_human_acceptance_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True, help="Pull request number.")
    parser.add_argument(
        "--repository",
        default="",
        help="owner/name. Defaults to the current repository via gh.",
    )
    parser.add_argument("--provider", default="odds_api", help="Registered provider.")
    parser.add_argument(
        "--provider-name",
        default=EXPECTED_PROVIDER,
        help=f"Provider name in the approval. Default: {EXPECTED_PROVIDER}.",
    )
    parser.add_argument(
        "--markets",
        default="1x2,btts",
        help="Comma-separated market scope the approval must grant.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_APPROVAL_AGE_HOURS,
        help="Reject approvals older than this.",
    )
    parser.add_argument(
        "--activity-json",
        type=Path,
        help="Read PR activity from a file instead of calling GitHub (offline).",
    )
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--write-receipt",
        action="store_true",
        help="Write the receipt. Without this the command only verifies.",
    )
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="Print the exact approval text to paste into GitHub, then exit.",
    )
    return parser.parse_args()


def _repository(explicit: str) -> str:
    if explicit:
        return explicit
    import subprocess

    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def main() -> int:
    args = parse_args()
    markets = [item.strip() for item in args.markets.split(",") if item.strip()]

    if args.print_template:
        print(approval_template(args.pr, provider_name=args.provider_name, markets=markets))
        return 0

    print("EPL Betting Lab - Receipt from GitHub Approval")
    print(
        "The approval is a GitHub review or comment by an allowed reviewer. "
        "This command verifies it and cannot author it."
    )

    if args.activity_json:
        try:
            activity = json.loads(args.activity_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"BLOCKED: activity file unreadable: {type(exc).__name__}.")
            return 2
    else:
        repository = _repository(args.repository)
        if not repository:
            print("BLOCKED: could not determine the repository. Pass --repository.")
            return 2
        try:
            activity = fetch_pr_activity(args.pr, repository=repository)
        except GitHubApprovalError as exc:
            print(f"BLOCKED: {exc}")
            return 2

    try:
        approval = verify_github_approval(
            activity,
            pr_number=args.pr,
            provider_name=args.provider_name,
            expected_markets=markets,
            output_dir=args.output_dir,
            max_age_hours=args.max_age_hours,
        )
    except GitHubApprovalError as exc:
        print(f"BLOCKED: {exc}")
        print()
        print("Paste this into a PR review or comment to approve:")
        print("---")
        print(approval_template(args.pr, provider_name=args.provider_name, markets=markets))
        print("---")
        return 2

    print(f"Approval found: {approval['source_kind']} by {approval['reviewer_github_login']}")
    print(f"Approved at: {approval['approved_at']} ({approval['approval_age_hours']}h ago)")
    print(f"PR: #{approval['pr_number']}  provider: {approval['provider_name']}")
    print(f"Approved markets: {approval['approved_markets']}")
    print(f"Excluded markets: {approval['excluded_markets']}")
    print(f"Evidence artifacts bound: {len(approval['evidence_checksums_sha256'])}")

    notes = (
        f"Approved in GitHub UI on PR #{approval['pr_number']} by "
        f"{approval['reviewer_github_login']} via {approval['source_kind']} "
        f"at {approval['approved_at']}. Markets: "
        f"{', '.join(approval['approved_markets'])}. Excluded: "
        f"{', '.join(approval['excluded_markets'])}."
    )

    try:
        receipt = build_provider_human_acceptance_receipt(
            args.provider,
            approval["reviewer_github_login"],
            approval["decision"],
            notes=notes,
            output_dir=args.output_dir,
        )
    except ProviderHumanAcceptanceReceiptError as exc:
        print(f"BLOCKED: receipt could not be built: {exc}")
        return 2

    # Bind the GitHub approval into the receipt so the audit trail records where
    # the human act happened, not merely that one was claimed.
    receipt = dict(receipt)
    receipt["github_approval"] = approval

    if not args.write_receipt:
        print()
        print("Verification only. Re-run with --write-receipt to write it.")
        return 0

    result = save_provider_human_acceptance_receipt(receipt, args.output_dir)
    print(f"Receipt ID: {receipt.get('receipt_id', '')}")
    for key in ("latest_json_path", "latest_markdown_path", "archive_directory"):
        value = (result.get("receipt_storage") or {}).get(key) if isinstance(
            result.get("receipt_storage"), dict
        ) else None
        if value:
            print(f"{key}: {value}")
    print("No secrets were printed or written. No bet, settlement, or cron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
