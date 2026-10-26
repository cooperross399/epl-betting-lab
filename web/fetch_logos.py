#!/usr/bin/env python3
"""Fill `web/logos/<ABBR>.png` with a 500-px crest for every club the board builder knows.

    PYTHONPATH=src python web/fetch_logos.py

Run by hand, once, and the PNGs are committed; nothing in a workflow calls it.
Stdlib only, keyless, spends no credit, fetches no odds. Idempotent: a logo
already on disk is never fetched again, so a re-run only fills gaps.

"Every club the builder knows" is every abbreviation in `build_board_json.TEAMS`
— the twenty 2026-27 clubs and the three relegated ones the settled record
still names. ESPN's names reach the board's abbreviations through the
builder's own `fd_name` -> `TEAMS`, the same path the board itself takes, so
the two cannot map a club differently. That mapping asks the lab's reviewed
alias table (`epl_betting_lab.providers.team_names`), hence `PYTHONPATH=src`;
without it ESPN's spellings ("AFC Bournemouth", "Tottenham Hotspur") would not
map and this refuses to run rather than fall through to a search for clubs
ESPN does carry.

Sources, per club, first that answers 200 with a real PNG (> 2 KB, valid
signature, IHDR and image data that inflates):

  1. ESPN's teams endpoints, the host the live scoreboard already reads:
     `logos[0].href` off `soccer/eng.1/teams`, then `soccer/eng.2/teams` for a
     club the Premier League list no longer carries (the relegated three).
     Read off the endpoint rather than guessed from team codes.
  2. Wikimedia Commons search, for a club neither ESPN list carries: the first
     SVG/PNG file result and its 500-px thumbnail. Sent with a descriptive
     User-Agent as Wikimedia's policy asks, with a back-off on HTTP 429.
  3. Nothing. The page then shows the coloured abbreviation.

Text/metadata chunks (tEXt, iTXt, zTXt, eXIf, tIME) are dropped before a
file is saved: ESPN's carry XMP ids shaped like an API key, which the repo's
secrets guard rightly refuses in any tracked file. Pixels are untouched.

`web/logos/SOURCES.md` lists every file and the URL it came from. The logos
are the leagues' and clubs' trademarks, shown for identification only.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_builder():
    """The builder's own module, by path, so nothing is added to sys.path."""
    spec = importlib.util.spec_from_file_location("build_board_json_for_logos", HERE / "build_board_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()

LOGOS = HERE / "logos"
SOURCES = LOGOS / "SOURCES.md"
SIZE = 500
MIN_BYTES = 2048


#: Committed and published at this size (2026-10-26): a 500-px crest drawn in
#: a small circle cost about 1.5 MB on a full board. A download is still
#: checked at its source size above, then shrunk before it is written.
PUBLISHED_PX = 128
PUBLISHED_MIN_BYTES = 1024


def shrink(data: bytes) -> bytes:
    """The logo fitted inside a transparent PUBLISHED_PX square, centred and
    optimised. Needs Pillow (`pip install pillow`); only this hand-run fetch
    does, so nothing the workflows or the suite import requires it."""
    import io

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - a hand-run step
        raise SystemExit("web/fetch_logos.py needs Pillow to shrink logos: pip install pillow") from exc
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    image.thumbnail((PUBLISHED_PX, PUBLISHED_PX), Image.LANCZOS)
    canvas = Image.new("RGBA", (PUBLISHED_PX, PUBLISHED_PX))
    canvas.paste(image, ((PUBLISHED_PX - image.width) // 2, (PUBLISHED_PX - image.height) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


ESPN_TEAMS = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams",
    "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.2/teams",
)
COMMONS = "https://commons.wikimedia.org/w/api.php"
#: Wikimedia asks every client to identify itself with a way to reach its
#: operator. ESPN gets urllib's default agent, which it is known to accept.
WIKI_AGENT = "epl-betting-lab-logos/1.0 (https://github.com/cooperross399/epl-betting-lab; logo fetch for identification)"
NOTICE = ("The logos are the leagues' and clubs' trademarks, shown for "
          "identification only.")


def get(url: str, agent: str | None = None, tries: int = 3) -> bytes:
    headers = {"User-Agent": agent} if agent else {}
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed hosts
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt + 1 < tries:
                wait = exc.headers.get("Retry-After", "") if exc.headers else ""
                time.sleep(min(int(wait), 60) if wait.isdigit() else 10 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def png_problem(data: bytes, min_bytes: int = MIN_BYTES) -> str | None:
    """Why `data` is not a usable PNG, or None when it is."""
    if len(data) <= min_bytes:
        return f"{len(data)} bytes"
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return "not a PNG signature"
    pos, idat, seen_ihdr = 8, b"", False
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            return "truncated chunk"
        if struct.unpack(">I", crc)[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            return f"bad CRC on {kind!r}"
        if not seen_ihdr:
            if kind != b"IHDR" or length != 13:
                return "first chunk is not IHDR"
            width, height = struct.unpack(">II", body[:8])
            if not (0 < width <= 4096 and 0 < height <= 4096):
                return f"implausible size {width}x{height}"
            seen_ihdr = True
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    else:
        return "no IEND"
    try:
        if not zlib.decompress(idat):
            return "empty image data"
    except zlib.error as exc:
        return f"image data does not inflate ({exc})"
    return None


#: Ancillary chunks that carry text, not pixels. ESPN's files embed an XMP
#: packet whose `xmp.iid`/`xmp.did` values are 32-hex runs — the exact shape
#: tests/test_no_secrets_committed.py refuses in any tracked file, with no
#: exemption for what a file is called. They are dropped before saving; the
#: image (IHDR, PLTE, tRNS, iCCP, IDAT ...) is kept byte for byte.
TEXT_CHUNKS = (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME")


def strip_text(data: bytes) -> bytes:
    """`data` without its text/metadata chunks. Assumes `png_problem(data)` is None."""
    out, pos = [data[:8]], 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if kind not in TEXT_CHUNKS:
            out.append(data[pos:end])
        pos = end
        if kind == b"IEND":
            break
    return b"".join(out)


def png_size(data: bytes) -> tuple[int, int]:
    return struct.unpack(">II", data[16:24])


def fetch_png(abbr: str, url: str, agent: str | None = None) -> bytes | None:
    """The file at `url` when it is a usable PNG, else None (and why, printed)."""
    try:
        data = get(url, agent)
    except (urllib.error.URLError, OSError) as exc:
        print(f"{abbr}: {url}: {exc}")
        return None
    problem = png_problem(data)
    if problem:
        print(f"{abbr}: {url}: {problem}")
        return None
    data = strip_text(data)
    problem = png_problem(data)
    if problem:
        print(f"{abbr}: {url}: {problem} once its text chunks were removed")
        return None
    return data


def espn_hrefs() -> dict[str, str]:
    """Board abbreviation -> ESPN logo URL, Premier League list first."""
    out: dict[str, str] = {}
    for url in ESPN_TEAMS:
        try:
            payload = json.loads(get(url))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"ESPN teams list unreadable: {url}: {exc}")
            continue
        for league in (payload.get("sports") or [{}])[0].get("leagues") or []:
            for item in league.get("teams") or []:
                team = item.get("team") or {}
                fd = builder.fd_name(team.get("displayName", ""))
                if fd not in builder.TEAMS:
                    continue
                href = ((team.get("logos") or [{}])[0] or {}).get("href")
                abbr = builder.TEAMS[fd][0]
                if href and abbr not in out:
                    out[abbr] = href
    return out


def commons_thumb(fd: str) -> str | None:
    query = urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": f"{fd} logo",
        "gsrnamespace": 6, "prop": "imageinfo", "iiprop": "url",
        "iiurlwidth": SIZE, "format": "json",
    })
    payload = json.loads(get(f"{COMMONS}?{query}", WIKI_AGENT))
    pages = sorted(((payload.get("query") or {}).get("pages") or {}).values(),
                   key=lambda p: p.get("index", 0))
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        # Commons now appends `?utm_source=...` to both URLs; judge the path.
        path = urllib.parse.urlsplit(str(info.get("url", ""))).path.lower()
        if path.endswith((".svg", ".png")) and info.get("thumburl"):
            return info["thumburl"]
    return None


def read_sources() -> dict[str, str]:
    """What an earlier run recorded, so a skipped file keeps its line."""
    out: dict[str, str] = {}
    try:
        lines = SOURCES.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0].endswith(".png`"):
            out[cells[0].strip("`")] = cells[1]
    return out


def write_sources(sources: dict[str, str]) -> None:
    rows = "\n".join(f"| `{name}` | {sources[name]} |" for name in sorted(sources))
    SOURCES.write_text(
        "# Team logos\n\n"
        "Written by `web/fetch_logos.py`. One file per club the board builder knows\n"
        "(`web/build_board_json.py` `TEAMS`), at 500 px. Each file is the source's\n"
        "PNG with its text/metadata chunks removed; the image data is unchanged.\n\n"
        f"{NOTICE}\n\n"
        "| File | Source |\n|---|---|\n"
        f"{rows}\n",
        encoding="utf-8",
    )


def main() -> int:
    if builder._normalize_team_name("Arsenal") is None:
        print("The lab's team-name table is not importable; run with PYTHONPATH=src.")
        return 2
    LOGOS.mkdir(exist_ok=True)
    sources = read_sources()
    wanted = {abbr: fd for fd, (abbr, *_rest) in builder.TEAMS.items()}
    todo = [abbr for abbr in sorted(wanted) if not (LOGOS / f"{abbr}.png").exists()]
    for abbr in sorted(set(wanted) - set(todo)):
        sources.setdefault(f"{abbr}.png", "(already on disk; source not recorded)")
    espn = espn_hrefs() if todo else {}
    missing = []
    for abbr in todo:
        url = espn.get(abbr)
        data = fetch_png(abbr, url) if url else None
        if data is None:
            # ESPN does not carry the club, or its file was not a usable PNG.
            try:
                url = commons_thumb(wanted[abbr])
            except (urllib.error.URLError, OSError, ValueError) as exc:
                print(f"{abbr}: Wikimedia search failed: {exc}")
                url = None
            data = fetch_png(abbr, url, WIKI_AGENT) if url else None
        if data is None:
            missing.append(abbr)
            continue
        data = shrink(data)
        (LOGOS / f"{abbr}.png").write_bytes(data)
        sources[f"{abbr}.png"] = url
        w, h = png_size(data)
        print(f"{abbr}: {w}x{h}, {len(data)} bytes from {url}")
    write_sources(sources)
    have = len(wanted) - len(missing)
    print(f"{have} of {len(wanted)} clubs have a logo"
          + (f"; none found for {', '.join(missing)} (the page shows the abbreviation)." if missing else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
