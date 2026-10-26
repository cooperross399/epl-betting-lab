#!/usr/bin/env python
"""Read and write a price feed on the `price-feed` branch as one file per day.

On 2026-10-26 `price_feed.csv` was 52,491,855 bytes on the branch and growing
about 1.9 MB a day. GitHub refuses a push carrying a file over 100 MB, so
within weeks every push would have been rejected and live closing-line value
would have stopped recording. Compressing the one file would have fitted and
cost more: git cannot delta one gzip stream against the next, so every push
would add a whole new compressed copy to the history. Split by the day each
price was observed, a push rewrites today's file and every earlier day stays
the blob it already was.

The branch holds `price_feed/2026-10-26.csv` and so on, each with the header.
Locally nothing changes: a step restores one `data/processed/price_feed.csv`
and every reader reads that.

    show REF NAME   print feed NAME (e.g. price_feed.csv) as one CSV, from its
                    day files if REF has them, else from the single file an
                    older tip carries. Exits 1, printing nothing, if REF holds
                    neither.
    entry PATH      split the local feed at PATH into day files, write them
                    and their tree into the object store, and print the
                    `git mktree` line naming that tree.

Standard library only: the board's workflow runs it too.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

#: A row whose `observed_at` does not start with a date still has to be kept.
UNDATED = "undated"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _git(*args: str, data: bytes | None = None) -> bytes:
    done = subprocess.run(["git", *args], input=data, capture_output=True, check=False)
    if done.returncode != 0:
        raise LookupError(done.stderr.decode(errors="replace").strip())
    return done.stdout


def shard_dir(name: str) -> str:
    """`price_feed.csv` lives in `price_feed/`."""
    return Path(name).stem


def _lines(data: bytes) -> list[bytes]:
    lines = data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        lines[-1] += b"\n"
    return lines


def show(ref: str, name: str) -> bytes:
    directory = shard_dir(name)
    try:
        listing = _git("ls-tree", "--name-only", f"{ref}:{directory}")
    except LookupError:
        listing = b""
    shards = sorted(n for n in listing.decode().splitlines() if n.endswith(".csv"))
    if not shards:
        # An older tip, or the extra feed's retired name: one plain file.
        return _git("cat-file", "blob", f"{ref}:{name}")
    out: list[bytes] = []
    for shard in shards:
        lines = _lines(_git("cat-file", "blob", f"{ref}:{directory}/{shard}"))
        out.extend(lines if not out else lines[1:])
    return b"".join(out)


def split(data: bytes) -> dict[str, bytes]:
    """Day -> that day's file, header included. Row order within a day is kept."""
    lines = _lines(data)
    if len(lines) < 2:
        return {}
    header, days = lines[0], {}
    # Found by name: the extra competitions' feed puts two columns before it.
    columns = next(csv.reader([header.decode()]))
    at = columns.index("observed_at") if "observed_at" in columns else 0
    for line in lines[1:]:
        fields = next(csv.reader([line.decode(errors="replace")]), [])
        match = _DAY.match(fields[at]) if len(fields) > at else None
        days.setdefault(match.group(0) if match else UNDATED, []).append(line)
    return {day: header + b"".join(rows) for day, rows in sorted(days.items())}


def entry(path: Path) -> str:
    shards = split(path.read_bytes())
    if not shards:
        raise LookupError(f"{path} holds no observations")
    listing = []
    for day, body in shards.items():
        blob = _git("hash-object", "-w", "--stdin", data=body).decode().strip()
        listing.append(f"100644 blob {blob}\t{day}.csv\n")
    tree = _git("mktree", data="".join(listing).encode()).decode().strip()
    return f"040000 tree {tree}\t{shard_dir(path.name)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    shown = commands.add_parser("show")
    shown.add_argument("ref")
    shown.add_argument("name")
    entered = commands.add_parser("entry")
    entered.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            sys.stdout.buffer.write(show(args.ref, args.name))
        else:
            print(entry(args.path))
    except (LookupError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
