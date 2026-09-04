"""Repository hygiene: no credential may reach a tracked file.

These tests run against the files git actually tracks, so they fail the build
if a secret is ever committed — including by a future change that means well.
They deliberately do not read `.env`: the point is to prove nothing *else*
contains a credential, and reading the real key here would be the very leak
being guarded against.

A guard that greps for a spelling proves only that the spelling is absent.
The first version of this module was five such greps, and an audit walked a
synthetic key past every one of them without touching the module:

* any file whose *name* contained "checksum" or "receipt" was skipped from the
  hex scan outright — a by-name exemption that covered twenty-nine tracked
  files, fourteen of them source, and aimed the blind spot at the acceptance
  receipts whose whole job is to record provenance;
* `\\b[0-9a-f]{32}\\b` would not open beside an underscore, because `_` is a
  word character, so `<key>_odds.json` inside a string hid the key; and the
  class was lowercase only, so an uppercased copy of the key was not a key;
* only file *bodies* were read, and only for files that `is_file()` — so a
  key written into a filename was read by nothing, a tracked symlink whose
  target was the key was dropped as "not a file", and a text file wearing a
  `.png` suffix was never opened;
* the assignment scan knew `NAME=value` and nothing else, so the canonical
  Python spelling `os.environ["NAME"] = "<key>"` and the YAML `NAME: <key>`
  were not assignments, and every `.md`, `.rst` and `.txt` was exempt from
  the scan wholesale.

So the rules below are shapes, not spellings, and every one of them is run
over a synthetic corpus in this same module — the regression test for each
bypass writes the file that got through and asserts it no longer does. The
gaps that remain are asserted too, in
`test_the_gaps_this_guard_still_has_are_the_ones_written_down`, because a
guard that names its own limits beats one that overclaims.

There is deliberately NO exemption set. The NCAAF lab needs one, because its
provider cache is full of 32-hex event ids; this lab tracks nothing under
`data/raw/`, and the mechanism that harvested exemptions from filenames was
the self-nomination hole (a decoy `<key>_x.md` at the root exempted the key
everywhere). The day this lab needs to track a provider response, add a
by-value exemption harvested from `data/raw/` bodies only and spent nowhere
outside `data/`; do not bring back a by-name skip.
"""

from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.providers.env_file import ENV_FILENAME, PROVIDER_ENV_ALLOWLIST


#: Obvious placeholders that must never be mistaken for a real credential.
PLACEHOLDERS = {
    "your-secret-key",
    "your-api-key",
    "test-secret-that-must-not-be-written",
    "env-file-secret-that-must-never-be-written",
    "shadow-test-secret-never-write",
    "discovery-secret-must-not-be-written",
    "props-secret-must-not-be-written",
    "already-exported-value",
    "${{",
}

#: A 32-hex-character run is the shape of an Odds API key.
#:
#: The fence is a pair of lookarounds and not `\b`. `\b` will not open between
#: `_` and a hex digit because both are word characters, so one underscore of
#: adjacent context — `<key>_odds.json`, `KEY_<key> = 1` — hid a key from the
#: old matcher. The lookarounds still refuse to fire inside a longer hex run,
#: which is what keeps a SHA-256 quiet without a by-name exemption.
#:
#: `A-F` as well as `a-f`: the provider issues lowercase, and an uppercased
#: copy of a key is the same key. Admitting the uppercase half adds no
#: offender to the tracked corpus.
HEX_KEY = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32}(?![0-9A-Fa-f])")

#: `apiKey=` FOLLOWED BY A VALUE is a leak. The bare token is not: it appears
#: legitimately in the redaction regex that strips credentials and in tests
#: asserting the token is absent. Flagging the bare token would force those
#: defences to be written obscurely, or exempted — both worse than matching
#: precisely. Eight characters is well below any real key length. The spelling
#: is a family (`apiKey`, `apikey`, `api_key`, `api-key`) rather than the one
#: The Odds API happens to use, so a provider rename does not quiet it. The
#: fence in front is what keeps `EPL_ODDS_API_KEY=your-secret-key` in the
#: setup docs from reading as the parameter: the tail of a credential *name*
#: is not a URL parameter, and the assignment scan owns that line.
API_KEY_PARAM = re.compile(
    r"(?<![A-Za-z0-9_])api[_-]?key=[A-Za-z0-9][A-Za-z0-9_-]{7,}", re.IGNORECASE
)

#: Every credential-ish variable name a tracked file may mention but never
#: assign. The allowlist is what `.env` may carry; `ODDS_API_KEY` is the
#: spelling `.env.example` documents; `GH_TOKEN` is what the workflows bind
#: `github.token` to. `test_no_credential_name_in_the_repository_is_unknown_
#: to_this_guard` fails the build if a name of this shape appears in the tree
#: and is missing from here — a scan keyed on names it has not been taught is
#: a scan that goes quiet on a rename.
CREDENTIAL_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys((*PROVIDER_ENV_ALLOWLIST, "ODDS_API_KEY", "GH_TOKEN"))
)

#: The shape of a credential variable name, used to find names this guard has
#: not been taught. The suffix is an alternation because `_API_KEY` alone is
#: one spelling.
CREDENTIAL_NAME_SHAPE = re.compile(
    r"\b[A-Z][A-Z0-9_]*_(?:API_KEY|APIKEY|API_TOKEN|TOKEN|SECRET|PASSWORD)\b"
)

#: Punctuation that may sit between a credential name and the operator that
#: gives it a value: the closing half of a quote, a subscript, a code span, an
#: emphasis marker, or an HTML tag. `os.environ["NAME"] = "..."`,
#: `` `NAME` = ... ``, `{"NAME": "..."}`, `**NAME**: ...`, `<code>NAME</code>:`.
#: A shape rather than a list of six characters, because a list is a
#: spelling: any character that is neither alphanumeric, a newline, nor one of
#: the operators this module reads back. Bounded at eight so it cannot walk
#: across a line to an operator that belongs to something else.
_CLOSERS = r"(?:</?[A-Za-z][A-Za-z0-9]*[^<>\n]{0,64}>|[^0-9A-Za-z\n=:,|]){0,8}"

#: A horizontal blank, agreeing with `\S` about what a blank is. `[ \t]*` is
#: ASCII and `\S` is Unicode-aware, so a U+00A0 after the operator fell in the
#: gap between the two classes and opened no match at all. `[^\S\r\n]*` is
#: every character `\S` refuses, minus the line breaks — the two classes now
#: partition the input. Newline stays excluded on purpose: it is what keeps
#: `.env.example`'s bare `NAME=` on one line from pairing with the next.
_BLANK = r"[^\S\r\n]*"

#: How much of the line after the operator is handed to the value tests. A
#: zero-width lookahead so the match ends at the operator (a consumed value
#: would swallow a nested `${NAME:-<key>}`), and bounded so a generated
#: one-line file cannot make the scan quadratic.
_REST_OF_LINE = r"(?=(.{0,512}))"

_NAMES = "|".join(re.escape(name) for name in CREDENTIAL_NAMES)

#: `NAME=value` and its family. The operator is `[:?+]?=` — `:=` (Make, Go),
#: `?=` (Make) and `+=` are assignments a machine reads back. `_CLOSERS` is
#: what admits `os.environ["NAME"] = ...`; `_BLANK` is what closes the
#: Unicode gap; the fence is `(?<![A-Za-z0-9])` rather than `\b` so the
#: Markdown emphasis spelling `_NAME_` is reachable. Case-insensitive because
#: a credential under a lowercased name is the same credential.
ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9])(" + _NAMES + r")" + _CLOSERS + _BLANK
    + r"[:?+]?=" + _BLANK + _REST_OF_LINE,
    re.IGNORECASE,
)

#: The same idea for the separators `=` cannot cover: YAML's `NAME: value`,
#: the comma of `{"NAME", value}`, and the pipe of a Markdown table row. Each
#: of these also separates a name from ordinary prose ("`EPL_ODDS_API_KEY`:
#: the GitHub secret"), so under these the value must independently look like
#: a credential — see `_looks_like_a_credential_value`.
SEPARATED = re.compile(
    r"(?<![A-Za-z0-9])(" + _NAMES + r")" + _CLOSERS + _BLANK
    + r"[:,|]" + _BLANK + _REST_OF_LINE,
    re.IGNORECASE,
)

#: Does this token look like a credential *value* rather than a word of prose?
#: One unbroken run of name-safe characters, twelve or longer, carrying at
#: least one digit, and not itself an identifier in shouting case. Each clause
#: pays for itself against real prose in this repository: the length rejects
#: "required"; the class rejects a path or a URL; the digit rejects
#: "not-configured"; the shouting-case clause rejects `DEFAULT_API_BASE_URL`
#: and `SECRET`, which sit after a comma or a colon in real source here.
CREDENTIAL_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{11,}")
SHOUTING_CASE = re.compile(r"[A-Z0-9_]+")

#: A URL is a location, not a credential. `EPL_ODDS_API_BASE_URL=https://…`
#: is a legitimate line in the setup docs. A key *inside* a URL is still
#: caught, by `API_KEY_PARAM` and `HEX_KEY`, which read every body regardless.
URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

#: Unicode categories that occupy no space and belong to no credential:
#: format marks (U+200B, U+FEFF, U+00AD) and controls. `\S` starts on them, so
#: they ride into the value token rather than being consumed as spacing;
#: `_unwrap` deletes them by category rather than by a list of codepoints.
INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc"})


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


def _is_this_file(path: Path) -> bool:
    """`path` is this module, resolving symlinks — and never raises.

    `Path.resolve()` raises on a symlink loop. A path that cannot be resolved
    is *not* this file, so it stays in the corpus and gets scanned: absence of
    an answer is never an exemption.
    """
    try:
        return path.resolve() == SELF
    except (OSError, RuntimeError):
        return False


def _link_target(path: Path) -> str:
    """What a tracked symlink carries, which is neither its name nor a body.

    git stores a symlink as a blob whose content is the target string, so
    `ln -s <key> docs/provider_key` commits the credential in plaintext. The
    old body scan dropped it on `is_file()` and the old name scan did not
    exist. Returns `""` for anything that is not a link so callers can
    concatenate it unconditionally.
    """
    try:
        if not path.is_symlink():
            return ""
        return os.readlink(path)
    except OSError:
        return ""


def _scannable(paths: Iterable[Path]) -> list[Path]:
    """Every tracked path except this module. No suffix rule.

    A symlink is kept even when it dangles: its body reads as empty and its
    target is scanned beside its name. A `.png` is kept too — the suffix is
    chosen by whoever adds the file, and a text body wearing a binary suffix
    was one of the audit's bypasses. Nothing binary is tracked today; a real
    binary that happened to decode to 32 hex characters would be a build
    someone looks at, which is the right side of that trade.
    """
    return [path for path in paths if not _is_this_file(path)]


def _text_files() -> list[Path]:
    return _scannable(_tracked_files())


def _read(path: Path) -> str:
    """The body as text, plus a NUL-stripped reading when there are NULs.

    A UTF-16 file decodes under `errors="ignore"` into `K\\x00E\\x00Y…`, and
    every matcher here wants an unbroken run. Removing the NULs recovers the
    ASCII; appending rather than replacing keeps the ordinary reading intact.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if "\x00" in text:
        return text + "\n" + text.replace("\x00", "")
    return text


def _hex_key_offenders(paths: Iterable[Path], root: Path) -> list[str]:
    """Every 32-hex run in `paths` — in the path, the link target, or the
    body. Only six characters of a finding are reported: enough to locate it,
    not enough to publish it.

    The corpus is an argument so the regression tests below can run this
    exact code over a synthetic file instead of asserting about it from a
    distance. There is no `allowed` set — see the module docstring.
    """
    offenders: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        found = [match.group(0) for match in HEX_KEY.finditer(relative)]
        found += [match.group(0) for match in HEX_KEY.finditer(_link_target(path))]
        found += [match.group(0) for match in HEX_KEY.finditer(_read(path))]
        for value in found:
            offenders.append(f"{relative}: {value[:6]}...")
    return offenders


def _unwrap(raw: str) -> str:
    """Strip the punctuation that surrounds a value in source and prose.

    Invisible characters go first, by category. Then a string-literal prefix
    (`f"{SECRET}"` is quoting, not value), then quotes, then the closing halves
    of a call, dict or list, then quotes again, then a trailing escape such as
    the `\\n` of `printf 'NAME=value\\n'`, and the leading `-` of a shell
    default so `${NAME:-<key>}` reads as the assignment it is.
    """
    visible = "".join(
        character
        for character in raw
        if unicodedata.category(character) not in INVISIBLE_CATEGORIES
    )
    without_prefix = re.sub(r"^[fFrRbBuU]{1,2}(?=[\"'])", "", visible)
    value = without_prefix.strip("'\"`").strip(",;)}]").strip("'\"`")
    value = re.sub(r"(?:\\[nrt])+$", "", value)
    return value.lstrip("-")


def _unbracket(value: str) -> str:
    return value.strip("<>{} ")


def _looks_like_a_credential_value(value: str) -> bool:
    if not CREDENTIAL_VALUE.fullmatch(value):
        return False
    if SHOUTING_CASE.fullmatch(value):
        return False
    return any(character.isdigit() for character in value)


def _is_a_reference(value: str) -> bool:
    """`$VAR`, `${{ secrets.X }}`, `<placeholder>`, an f-string `{SECRET}`.

    `$` is unconditional: a `$`-prefixed token is an expansion whatever
    follows. The bracket forms are not — `NAME: <sk-live-…>` is the leak
    wearing the placeholder's clothes — so what is inside has to fail the
    value test, which `<your-key>` does and a real credential does not.
    """
    if value[0] == "$":
        return True
    if value[0] in "<{":
        return not _looks_like_a_credential_value(_unbracket(value))
    return False


def _assignment_offenders(paths: Iterable[Path], root: Path) -> list[str]:
    """Every `CREDENTIAL_NAME <given> <real value>` in `paths`, by file and name.

    Two families, because they need different evidence. `=` is an assignment
    wherever it appears, so its first token is a finding unless it is a
    placeholder, a reference, a URL, or a fragment of source that still
    carries a quote after unwrapping (`("NAME=", "api_key=")` in a test is
    the shape that forced the last rule). `:`, `,` and `|` also occur in
    prose, so every token under them must independently look like a
    credential value — and so must every token after the first under `=`,
    which is what keeps the sentence following `export NAME=<placeholder>`
    from being reported.

    Every whitespace-separated token on the rest of the line is evaluated and
    an empty one advances rather than ending the line, so a key in the third
    cell of a table row, or after `""` in Python, is still reached. The link
    target is appended to the body so `ln -s 'NAME=<key>' note` is read.
    """
    offenders: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text = _read(path)
        target = _link_target(path)
        if target:
            text = f"{text}\n{target}"
        for pattern, value_must_look_real in ((ASSIGNMENT, False), (SEPARATED, True)):
            for match in pattern.finditer(text):
                tokens = [
                    unwrapped
                    for unwrapped in (
                        _unwrap(token) for token in match.group(2).split()
                    )
                    if unwrapped
                ]
                for index, value in enumerate(tokens):
                    must_look_real = value_must_look_real or index > 0
                    if value in PLACEHOLDERS:
                        continue
                    if _is_a_reference(value):
                        continue
                    if URL.match(value):
                        continue
                    if not must_look_real and any(q in value for q in "'\"`"):
                        continue
                    if must_look_real and not _looks_like_a_credential_value(
                        _unbracket(value)
                    ):
                        continue
                    finding = f"{relative}: {match.group(1).upper()}"
                    if finding not in offenders:
                        offenders.append(finding)
                    break
    return offenders


def _api_key_param_offenders(paths: Iterable[Path], root: Path) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text = _read(path) + "\n" + _link_target(path)
        for match in API_KEY_PARAM.finditer(text):
            offenders.append(f"{relative}: {match.group(0)[:10]}...")
    return offenders


# --------------------------------------------------------------------------
# The gates, over the real tracked corpus.
# --------------------------------------------------------------------------


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


def test_the_corpus_is_not_empty() -> None:
    """A guard with nothing to scan reports green. Absence is never a pass."""
    corpus = _text_files()

    assert len(corpus) > 100, len(corpus)
    assert any(path.name == "CLAUDE.md" for path in corpus)


def test_no_tracked_file_assigns_a_real_credential() -> None:
    """`EPL_ODDS_API_KEY=<something real>`, in any spelling, in any file."""
    offenders = _assignment_offenders(_text_files(), PROJECT_ROOT)

    assert offenders == [], f"credential assignment in tracked files: {offenders}"


def test_no_tracked_file_contains_an_odds_api_key_shape() -> None:
    """A 32-hex run is the shape of the provider key — in a body, a path, or
    a symlink target. No file is exempt for what it is called."""
    offenders = _hex_key_offenders(_text_files(), PROJECT_ROOT)

    assert offenders == [], f"possible credential in tracked files: {offenders}"


def test_generated_reports_never_include_the_api_key_parameter() -> None:
    """`apiKey=<value>` is how the credential travels; it must not be written."""
    offenders = _api_key_param_offenders(_text_files(), PROJECT_ROOT)

    assert offenders == [], f"apiKey= with a value in tracked files: {offenders}"


def test_no_credential_name_in_the_repository_is_unknown_to_this_guard() -> None:
    """A name of credential shape that this module was not taught is a name
    the assignment scan cannot see being assigned."""
    unknown: set[str] = set()
    for path in _text_files():
        for match in CREDENTIAL_NAME_SHAPE.finditer(_read(path)):
            if match.group(0) not in CREDENTIAL_NAMES:
                unknown.add(f"{path.relative_to(PROJECT_ROOT).as_posix()}: {match.group(0)}")

    assert not unknown, (
        "credential-shaped names this guard does not know; add them to "
        f"CREDENTIAL_NAMES so their assignment is scanned: {sorted(unknown)}"
    )


def test_data_outputs_reports_are_not_tracked_with_secrets() -> None:
    """Report artifacts under data/outputs must be clean if tracked at all."""
    reports = [
        path for path in _text_files()
        if path.relative_to(PROJECT_ROOT).as_posix().startswith("data/outputs/")
    ]

    assert reports, "no tracked report under data/outputs/ — the scope is empty"
    assert _hex_key_offenders(reports, PROJECT_ROOT) == []
    assert _api_key_param_offenders(reports, PROJECT_ROOT) == []


@pytest.mark.parametrize("name", PROVIDER_ENV_ALLOWLIST)
def test_credential_names_are_referenced_but_never_valued(name: str) -> None:
    """The variable name may appear anywhere; only a real value is forbidden."""
    assert isinstance(name, str) and name
    assert name in CREDENTIAL_NAMES


def test_the_guard_excludes_itself_from_its_own_scan() -> None:
    """Otherwise it flags its own needles and everyone learns to ignore it."""
    scanned = {path.resolve() for path in _text_files()}

    assert SELF not in scanned


#: The only key-shaped strings this module may contain: the synthetic needle
#: and the positive-control strings. Anything else hex-shaped in this file is
#: a finding, which closes the "paste it into the guard" route.
OWN_NEEDLES = frozenset({"0123456789abcdef0123456789abcdef", "abcdef0123456789abcdef0123456789"})
OWN_PARAMETER_CONTROLS = frozenset(
    {"apiKey=012...", "apiKey=abc...", "api_key=sk...", "APIKEY=012..."}
)


def test_this_module_carries_only_its_own_needles() -> None:
    """Self-exclusion is not a hole: the scanners run over this file too, and
    allow exactly the needles this file declares."""
    hex_runs = {
        match.group(0) for match in HEX_KEY.finditer(_read(SELF))
    } | {match.group(0) for match in HEX_KEY.finditer(SELF.name)}
    assert hex_runs <= OWN_NEEDLES, hex_runs - OWN_NEEDLES

    assert _assignment_offenders([SELF], SELF.parent) == []

    parameters = {
        finding.split(": ", 1)[1]
        for finding in _api_key_param_offenders([SELF], SELF.parent)
    }
    assert parameters <= OWN_PARAMETER_CONTROLS, parameters - OWN_PARAMETER_CONTROLS


def test_the_guard_manifest_and_its_hook_are_in_place() -> None:
    """Each hard-rule guard vouches for the manifest that vouches for it.

    tests/test_the_guards_exist.py names this module and tests/conftest.py
    ends a run in which it contributed nothing. Deleting those two together
    would have left this module standing with nothing to say it was required.
    """
    for relative in ("tests/test_the_guards_exist.py", "tests/conftest.py"):
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )
        assert result.returncode == 0, f"{relative} is not tracked"
    manifest = (PROJECT_ROOT / "tests" / "test_the_guards_exist.py").read_text(encoding="utf-8")
    assert "tests/test_no_secrets_committed.py" in manifest
    hook = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in hook
    assert "tests/test_no_secrets_committed.py" in hook


def test_the_guard_still_scans_other_test_files() -> None:
    """Self-exclusion must be exactly one file, not all of tests/."""
    scanned = {path.name for path in _text_files()}

    assert "test_automated_card.py" in scanned
    assert "test_provider_env_file.py" in scanned


# --------------------------------------------------------------------------
# Positive controls: the matchers still fire on the real thing.
# --------------------------------------------------------------------------


def test_the_api_key_parameter_check_still_catches_a_real_leak() -> None:
    assert API_KEY_PARAM.search("https://x/v4/odds?apiKey=0123456789abcdef&r=us")
    assert API_KEY_PARAM.search("apiKey=abcdef0123456789abcdef0123456789")
    assert API_KEY_PARAM.search("api_key=sk-live-4f19c0d27ba6e83d")
    assert API_KEY_PARAM.search("APIKEY=0123456789abcdef")
    # ...and stays quiet on the defences that mention the token.
    assert not API_KEY_PARAM.search('re.compile(r"(apiKey=)[^&s]+")')
    assert not API_KEY_PARAM.search('assert "apiKey=" not in text')
    assert not API_KEY_PARAM.search("apiKey=[redacted]")


def test_the_key_shape_check_still_catches_a_real_leak() -> None:
    key = "0123456789abcdef0123456789abcdef"

    assert HEX_KEY.search(f'KEY = "{key}"')
    assert HEX_KEY.search(f"?apiKey={key}&regions=us")
    # A SHA-256 is a longer hex run and is not a key.
    assert not HEX_KEY.search(key + key)


# --------------------------------------------------------------------------
# One regression test per bypass the audit reproduced. Each writes the file
# that got through and runs the real scanner over it.
# --------------------------------------------------------------------------

KEY = "0123456789abcdef0123456789abcdef"
VALUE = "sk-live-4f19c0d27ba6e83d"
NAME = "EPL_ODDS_API_KEY"


def test_a_file_is_never_exempt_from_the_hex_scan_for_what_it_is_called(
    tmp_path: Path,
) -> None:
    """Bypass (a): the by-name skip. A file called `receipt.json` or
    `checksums.md` carrying a key was not scanned at all."""
    for filename in ("provider_human_acceptance_receipt.json", "checksums.md"):
        (tmp_path / filename).write_text(f'{{"id": "{KEY}"}}\n', encoding="utf-8")
    paths = sorted(tmp_path.iterdir())

    assert _hex_key_offenders(paths, tmp_path) == [
        f"checksums.md: {KEY[:6]}...",
        f"provider_human_acceptance_receipt.json: {KEY[:6]}...",
    ]


def test_the_key_shape_matcher_is_not_stopped_by_a_word_character(
    tmp_path: Path,
) -> None:
    """Bypass (b): `\\b` closed beside an underscore, and the class was
    lowercase only."""
    cases = {
        "underscore.py": f'CACHE = "{KEY}_odds.json"',
        "prefixed.py": f"KEY_{KEY} = 1",
        "upper.py": f'KEY = "{KEY.upper()}"',
        "mixed.py": f'KEY = "{KEY[:16].upper()}{KEY[16:]}"',
    }
    for filename, body in cases.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    paths = [tmp_path / filename for filename in sorted(cases)]

    assert [finding.split(":")[0] for finding in _hex_key_offenders(paths, tmp_path)] == sorted(cases)


def test_a_hex_run_in_a_filename_is_a_finding_wherever_the_name_sits(
    tmp_path: Path,
) -> None:
    """Bypass (c), first half: a filename needs no decoding, and used to be
    read by nothing. A binary suffix does not save it either."""
    (tmp_path / "docs").mkdir()
    named = tmp_path / "docs" / f"{KEY}.md"
    named.write_text("nothing in the body\n", encoding="utf-8")
    picture = tmp_path / f"{KEY}.png"
    picture.write_bytes(b"\x89PNG\r\n\x1a\n")

    assert _hex_key_offenders([named, picture], tmp_path) == [
        f"docs/{KEY}.md: {KEY[:6]}...",
        f"{KEY}.png: {KEY[:6]}...",
    ]


def test_a_tracked_symlink_carries_its_target_into_the_scans(
    tmp_path: Path,
) -> None:
    """Bypass (c), second half: `is_file()` is False for a dangling link, so
    the old corpus dropped it, and nothing read the target."""
    hex_link = tmp_path / "provider_key"
    hex_link.symlink_to(KEY)
    assignment_link = tmp_path / "note"
    assignment_link.symlink_to(f"{NAME}={VALUE}")
    param_link = tmp_path / "url"
    param_link.symlink_to(f"https://x/v4/odds?apiKey={KEY}")

    corpus = _scannable([hex_link, assignment_link, param_link])
    assert corpus == [hex_link, assignment_link, param_link]
    assert _hex_key_offenders(corpus, tmp_path) == [
        f"provider_key: {KEY[:6]}...",
        f"url: {KEY[:6]}...",
    ]
    assert _assignment_offenders(corpus, tmp_path) == [f"note: {NAME}"]
    assert _api_key_param_offenders(corpus, tmp_path) == [f"url: apiKey=012..."]


def test_a_text_body_wearing_a_binary_suffix_is_still_read(tmp_path: Path) -> None:
    """Bypass (c), third half: the old corpus dropped `.png` by suffix, so a
    text file named `cover.png` was never opened."""
    disguised = tmp_path / "cover.png"
    disguised.write_text(f'KEY = "{KEY}"\n{NAME} = "{VALUE}"\n', encoding="utf-8")

    assert _scannable([disguised]) == [disguised]
    assert _hex_key_offenders([disguised], tmp_path) == [f"cover.png: {KEY[:6]}..."]
    assert _assignment_offenders([disguised], tmp_path) == [f"cover.png: {NAME}"]


def test_a_decoy_filename_cannot_nominate_an_exemption(tmp_path: Path) -> None:
    """Bypass (d): in the sibling labs, a stem harvest over every tracked file
    let `<key>_x.md` at the repo root exempt the key everywhere. This lab has
    no exemption set at all, so the decoy is a finding and so is the key it
    was trying to cover for."""
    decoy = tmp_path / f"{KEY}_x.md"
    decoy.write_text("decoy\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    source = tmp_path / "scripts" / "fetch.py"
    source.write_text(f'KEY = "{KEY}"\n', encoding="utf-8")

    assert _hex_key_offenders([decoy, source], tmp_path) == [
        f"{KEY}_x.md: {KEY[:6]}...",
        f"scripts/fetch.py: {KEY[:6]}...",
    ]
    assert "_exempt" not in globals() and "EXEMPT_SCOPE" not in globals()


def test_the_canonical_python_assignment_is_a_finding(tmp_path: Path) -> None:
    """Bypass (e), first half: `os.environ["NAME"] = "<key>"` has a quote and a
    bracket between the name and the `=`, and the old scan required them to
    touch."""
    cases = {
        "environ.py": f'os.environ["{NAME}"] = "{VALUE}"',
        "spaced.py": f'os.environ[ "{NAME}" ] = "{VALUE}"',
        "setdefault.py": f'os.environ.setdefault("{NAME}", "{VALUE}")',
        "walrus.go": f"{NAME} := {VALUE}",
        "make.mk": f"{NAME} ?= {VALUE}",
        "append.mk": f"{NAME} += {VALUE}",
        "nbsp.md": f"export {NAME}=\u00a0{VALUE}",
        "emphasis.md": f"**{NAME}**: {VALUE}",
        "code.html": f"<code>{NAME}</code> = {VALUE}",
        "lower.sh": f"export {NAME.lower()}={VALUE}",
        "empty_first.py": f'os.environ["{NAME}"] = "" "{VALUE}"',
    }
    for filename, body in cases.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    paths = [tmp_path / filename for filename in sorted(cases)]

    assert _assignment_offenders(paths, tmp_path) == [
        f"{filename}: {NAME}" for filename in sorted(cases)
    ]


def test_a_yaml_assignment_is_a_finding_and_prose_is_not(tmp_path: Path) -> None:
    """Bypass (e), second half: `NAME: <key>` is how a workflow `env:` and a
    compose file spell an assignment. The value test is what lets the prose
    this repository actually writes pass."""
    leaks = {
        "env.yml": f"  {NAME}: {VALUE}",
        "quoted.yml": f'  {NAME}: "{VALUE}"',
        "dict.py": f'{{"{NAME}": "{VALUE}"}}',
        "table.md": f"| `{NAME}` | live | {VALUE} |",
        "bracketed.yml": f"  {NAME}: <{VALUE}>",
    }
    prose = {
        "reference.yml": f"  {NAME}: ${{{{ secrets.{NAME} }}}}",
        "docs.md": f"`{NAME}`: the name of the GitHub secret, never its value",
        "table_prose.md": f"| Production credential | GitHub secret `{NAME}` |",
        "json.json": f'  "credential_environment_variable": "{NAME}",',
        "constant.py": f'os.environ.get("{NAME}", DEFAULT_API_BASE_URL)',
        "url.md": f"EPL_ODDS_API_BASE_URL=https://api.the-odds-api.com/v4",
        "printf.md": f"printf '{NAME}=your-secret-key\\n' > .env",
        "needles.py": f'for needle in ("apiKey", "{NAME}=", "api_key="):',
        "placeholder.yml": f"  {NAME}: <your-key>",
        "fstring.py": f'{NAME}={{SECRET}}',
    }
    for filename, body in {**leaks, **prose}.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")

    assert _assignment_offenders(
        [tmp_path / filename for filename in sorted(leaks)], tmp_path
    ) == [f"{filename}: {NAME}" for filename in sorted(leaks)]
    assert _assignment_offenders(
        [tmp_path / filename for filename in sorted(prose)], tmp_path
    ) == []


def test_documentation_files_are_not_exempt_from_the_assignment_scan(
    tmp_path: Path,
) -> None:
    """Bypass (e), third half: every `.md`, `.rst` and `.txt` used to skip the
    assignment scan unless the value was hex. A key of any other shape in a
    runbook was not a finding."""
    for suffix in (".md", ".rst", ".txt"):
        (tmp_path / f"runbook{suffix}").write_text(
            f"export {NAME}={VALUE}\n", encoding="utf-8"
        )
    paths = sorted(tmp_path.iterdir())

    assert _assignment_offenders(paths, tmp_path) == [
        f"{path.name}: {NAME}" for path in paths
    ]


def test_a_credential_in_a_utf16_body_is_a_finding(tmp_path: Path) -> None:
    body = tmp_path / "notes.txt"
    body.write_text(f'KEY = "{KEY}"\n{NAME}={VALUE}\n', encoding="utf-16")

    assert _hex_key_offenders([body], tmp_path) == [f"notes.txt: {KEY[:6]}..."]
    assert _assignment_offenders([body], tmp_path) == [f"notes.txt: {NAME}"]


def test_the_gaps_this_guard_still_has_are_the_ones_written_down(
    tmp_path: Path,
) -> None:
    """The rewordings that still get past this module, asserted not remembered.

    Each line below is an attack that was written, run, and observed to pass.
    They are recorded rather than quietly left open. **This asserts nothing is
    allowed**: every gate above still demands an empty offender list. It is a
    ledger of coverage, and the correct response to any line is to close it
    and delete the line — a failure here means someone closed a gap.

    * Hex glued to another hex character. `<key>00` is a run longer than 32
      and the matcher refuses to fire inside one; that refusal is what keeps a
      SHA-256 quiet without a by-name exemption.
    * A key split across a concatenation. Nothing here parses source.
    * An encoded body — base64, hex-of-hex, ROT13. Nothing here decodes; the
      UTF-16 case is covered because that was a decoding this module was
      getting wrong, not an encoding it would have to undo.
    * A value on the line after its name. The blank classes stop at a newline
      on purpose, which is what keeps `.env.example`'s bare `NAME=` green.
    * A name assembled at runtime from pieces, or a separator this module does
      not know — a tab, a prose arrow.
    * An invisible character Unicode files as a *letter* — U+3164 HANGUL
      FILLER — glued to the front of a value under `:`/`,`/`|`. `_BLANK` does
      not consume it (not whitespace) and `INVISIBLE_CATEGORIES` does not
      strip it (category `Lo`), so the token fails the value test. Under `=`
      the same file IS a finding, and that half is asserted below.
    * A value under `:`/`,`/`|` shorter than twelve characters, all letters,
      or carrying a `.` or `/`. Those are the value test's edges; dropping
      the digit clause flags ordinary English instead.
    * A first token under `=` that still carries a quote in its interior
      after unwrapping (`NAME=<key>":x`), dismissed as a fragment of source
      because `("NAME=", "api_key="):` in a test is that shape. A trailing
      quote alone is stripped and IS a finding, asserted below. The hex shape
      is still caught either way; a non-hex key written that way is not.
    * A key embedded in a URL assigned to a credential name. The URL is
      dismissed by the assignment scan; the `apiKey=` and hex scans still read
      the same line, so only a non-hex key under a parameter this module does
      not know gets through.
    * A literal nested inside a shell expansion: `${NAME:=${OTHER:-<key>}}`.
      `$` is dismissed unconditionally and `OTHER` is not a credential name.
    * More than eight characters of markup between the name and the operator,
      a Markdown link `[NAME](#x): <key>`, or an HTML entity `NAME&nbsp;=`.
    * This module's own body, excluded from the tracked-corpus scans so it
      does not flag its own needles — but NOT unscanned: `test_this_module_
      carries_only_its_own_needles` runs every scanner over this file and
      allows exactly the needles listed there. What still gets through here
      is what gets through anywhere: a non-hex key under a name this module
      does not know.
    """
    gaps = {
        "padded.py": f'KEY = "{KEY}00"',
        "split.py": f'KEY = "{KEY[:16]}" "{KEY[16:]}"',
        "encoded.py": 'KEY = "MDEyMzQ1Njc4OWFiY2RlZg=="',
        "next_line.env": f"{NAME}=\n{VALUE}",
        "built.py": f'os.environ["EPL_ODDS_" "API_KEY"] = "{VALUE}"',
        "arrow.md": f"{NAME} -> {VALUE}",
        "column.tsv": f"{NAME}\t{VALUE}",
        "filler.md": f"{NAME}:\u3164{VALUE}",
        "short.yml": f"{NAME}: abc123def45",
        "letters.yml": f"{NAME}: purelettersecretvalue",
        "dotted.yml": f"{NAME}: ab12.cd34.ef56",
        "quote_inside.sh": f'{NAME}={VALUE}":x',
        "in_url.md": f"{NAME}=https://x/v4/odds?token={VALUE}",
        "nested.sh": ': "${' + NAME + ':=${OTHER:-' + VALUE + '}}"',
        "closers.md": f"{NAME}]]]]]]]]]]: {VALUE}",
        "link.md": f"[{NAME}](#the-secret): {VALUE}",
        "entity.md": f"{NAME}&nbsp;= {VALUE}",
    }
    for filename, body in gaps.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    paths = [tmp_path / filename for filename in sorted(gaps)]

    assert _hex_key_offenders(paths, tmp_path) == []
    assert _assignment_offenders(paths, tmp_path) == []
    assert _api_key_param_offenders(paths, tmp_path) == []

    # ...and the halves of those gaps that are NOT open, so that narrowing one
    # of them back fails here rather than passing quietly.
    caught = {
        "filler_equals.md": f"{NAME}=\u3164{VALUE}",
        "past_equals_real.sh": f"{NAME}=$UNUSED {VALUE}",
        "eight_closers.md": f"{NAME}]]]]]]]]: {VALUE}",
        "stray_quote.sh": f'{NAME}={VALUE}"',
        "in_url_hex.md": f"{NAME}=https://x/v4/odds?apiKey={KEY}",
    }
    for filename, body in caught.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    caught_paths = [tmp_path / filename for filename in sorted(caught)]

    assert _assignment_offenders(caught_paths, tmp_path) == [
        f"{filename}: {NAME}"
        for filename in sorted(caught)
        if filename != "in_url_hex.md"
    ]
    assert _hex_key_offenders(caught_paths, tmp_path) == [f"in_url_hex.md: {KEY[:6]}..."]
    assert _api_key_param_offenders(caught_paths, tmp_path) == [
        "in_url_hex.md: apiKey=012..."
    ]
