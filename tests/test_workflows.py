"""The required status check, pinned — parsed and executed, never grepped.

Branch protection on `main` requires two contexts, `Full test suite` and
`Provider Policy PR Gate`. Until this file existed, the only thing in the
repository that read `.github/workflows/tests.yml` was `assert "pytest" in
text` in tests/test_operating_model_docs.py, which the YAML job key `pytest:`
satisfied on its own. Every one of the following left the suite green: rename
the job (the context goes pending forever, or a job in another workflow
takes the name); replace `python -m pytest` with `echo`; put `if: false` or
`continue-on-error: true` on the step; run `pytest -x`, `pytest tests/x.py`,
or bind `PYTEST_ADDOPTS`; wrap it in `if ! pytest; then echo; fi`; add
`paths:` to the trigger so the check never runs on the PR that matters.

A guard that greps for a spelling proves only that the spelling is absent, and
every grep-shaped rule in the sibling labs was defeated by a rewording. So the
rules here read the tree `yaml.safe_load` returns, and where a behaviour can be
OBSERVED it is: each run block in the gate job is written to a sandbox, every
command word in it is replaced by a shell function of known exit status, and
the block is executed under `bash -e` — the shell GitHub runs a `run:` block
with. The verdict is the exit code. That is what catches `set +e`, `|| true`,
`if ! cmd; then echo; fi`, a `trap` that exits zero, and every rewording of
those that has not been thought of yet.

Every rule fails closed: a workflow that cannot be found, cannot be parsed or
declares nothing is a failure, not a quiet pass. Every rule has a synthetic
case that proves it fires — `test_every_rule_has_a_case_that_proves_it_fires`
refuses a rule nobody has watched reject anything.

What this file does NOT do, stated so it is not assumed: the operational
workflows (matchday refresh, closing snapshot, harvest, discovery) use
secrets, `continue-on-error` and `contents: write` on purpose, and their run
blocks swallow failures they have decided to tolerate. Those workflows get the
universal rules only — parse, trigger, shell, pinned Python, and the pytest
rules on any step of theirs that runs the suite. The strict rules and the
executed rules are for the workflow that carries the required check.

Ported from the NCAAF lab's linter with this lab's names and workflows; the
harness is the same mechanism, the rule set is this lab's.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"

#: The context branch protection on `main` requires. Verified against the
#: repository's protection settings on 2026-09-04 (both contexts present);
#: the string here is what a `name:` in tests.yml must equal exactly.
REQUIRED_CHECK = "Full test suite"

#: The provider credential's names. The gate workflow may not bind either.
CREDENTIAL_NAMES = frozenset({"EPL_ODDS_API_KEY", "EPL_ODDS_API_BASE_URL"})

#: `secrets.X`, `secrets['X']`, `secrets["X"]`, `toJSON(secrets)` — the
#: accessor, whatever punctuation follows the word. Read over RAW TEXT,
#: comments included, because a commented-out credential is one uncomment
#: away from a live one.
SECRET_REFERENCE = re.compile(r"(?i)\bsecrets\s*[.\[)]")
GITHUB_EXPRESSION = re.compile(r"(?s)\$\{\{.*?\}\}")
SECRETS_WORD = re.compile(r"(?i)\bsecrets\b")

#: The pytest flags that narrow a run or launder its result.
NARROWING_PYTEST_LONG_FLAGS = frozenset(
    {
        "--exitfirst", "--maxfail", "--keyword", "--markexpr", "--ignore",
        "--ignore-glob", "--deselect", "--config-file", "--confcutdir",
        "--override-ini", "--last-failed", "--failed-first", "--lf", "--ff",
        "--sw", "--stepwise", "--stepwise-skip", "--runxfail", "--co",
        "--collect-only", "--noconftest", "--rootdir",
    }
)
NARROWING_PYTEST_SHORT_FLAGS = frozenset("xkmoc")
PYTEST_ADDOPTS = "PYTEST_ADDOPTS"
#: PYTEST_ADDOPTS narrows with no command line; PYTEST_PLUGINS loads a module
#: that can deselect, skip or fake anything after the guards were counted.
#: Neither may be bound anywhere in a workflow, in any casing.
PYTEST_ENVIRONMENT_NAMES = frozenset({PYTEST_ADDOPTS, "PYTEST_PLUGINS"})
PYTEST_ADDOPTS_PATTERN = re.compile(r"(?i)\bPYTEST_(?:ADDOPTS|PLUGINS)\b")

#: The only `if:` a gate step may carry. `always()` WIDENS when a step runs;
#: every other expression narrows, and a narrowed gate is a gate that does
#: not run.
PERMITTED_CONDITION = "always()"

#: The only shells accepted, as bare keywords. `bash {0}` is bash without the
#: `-e` GitHub's default supplies, and after it every executed verdict here is
#: about a shell the workflow does not run.
SAFE_SHELLS = frozenset({"bash", "sh"})

#: A logical line continues onto the next when it ends this way. `pytest \\`
#: on one line and `-k slow` on the next hid the `-k` from a per-line rule.
CONTINUATION = re.compile(r"(?:\\|\|\||&&|\|)$")

#: `cmd &` and the launchers that background without the operator.
BACKGROUND = re.compile(r"(?<![&>])&(?![&>])")
ASYNC_LAUNCHER = re.compile(r"\b(?:setsid|coproc|nohup)\b")


# --------------------------------------------------------------------------
# Reading the tree.
# --------------------------------------------------------------------------


def workflow_files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.suffix in {".yml", ".yaml"} and path.is_file()
    )


WORKFLOW_FILES = workflow_files_in(WORKFLOWS_DIR)


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(document: Any) -> Any:
    """The `on:` mapping. YAML 1.1 reads bare `on` as the boolean True, and
    every workflow here writes it bare, so both keys are read."""
    if not isinstance(document, dict):
        return None
    if "on" in document:
        return document["on"]
    return document.get(True)


def mappings(node: Any) -> Iterator[dict]:
    """Every mapping in the document, depth first."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from mappings(value)
    elif isinstance(node, list):
        for value in node:
            yield from mappings(value)


def jobs_of(document: Any) -> dict[str, dict]:
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def steps_of(job: dict) -> list[dict]:
    steps = job.get("steps")
    return [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []


def run_blocks(document: Any) -> Iterator[tuple[str, str]]:
    for mapping in mappings(document):
        command = mapping.get("run")
        if isinstance(command, str):
            yield str(mapping.get("name", "<unnamed step>")), command


def commands(block: str) -> list[str]:
    """The LOGICAL lines of a run block. Comments dropped, continuations
    joined — the backslash is dropped because bash drops it, the operators
    kept because they are part of the command."""
    joined: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if joined and CONTINUATION.search(joined[-1]):
            previous = joined[-1]
            if previous.endswith("\\"):
                previous = previous[:-1].rstrip()
            joined[-1] = f"{previous} {line}"
        else:
            joined.append(line)
    return [line[:-1].rstrip() if line.endswith("\\") else line for line in joined]


def without_quoted_spans(line: str) -> str:
    """The line with every quoted span replaced by spaces of the same width,
    so `echo "python -m pytest"` is not a pytest invocation."""
    text: list[str] = []
    index, size = 0, len(line)
    while index < size:
        character = line[index]
        if character == "\\":
            text.append("  ")
            index += 2
            continue
        if character in "'\"":
            cursor = index + 1
            while cursor < size:
                if character == '"' and line[cursor] == "\\":
                    cursor += 2
                    continue
                if line[cursor] == character:
                    break
                cursor += 1
            text.append(" " * (min(cursor, size - 1) - index + 1))
            index = cursor + 1
            continue
        text.append(character)
        index += 1
    return "".join(text)


def _simple_commands(line: str) -> list[list[str]]:
    """Each simple command on a logical line as an argv, split by shlex.

    Split on the top-level operators (`;`, `&&`, `||`, `|`, `&`) and on the
    shell keywords that introduce a command (`if`, `!`, `then`, `do`, ...), so
    that `if ! python -m pytest; then` yields `["python", "-m", "pytest"]`.
    Prefix assignments (`PYTHONPATH=src python ...`) are stepped over.
    """
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        tokens = line.split()
    keywords = {"if", "then", "else", "elif", "fi", "do", "done", "!", "{", "}", "while", "until", "time"}
    argvs: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {";", "&&", "||", "|", "&"} or token.endswith(";"):
            if token.endswith(";") and token not in {";"}:
                current.append(token[:-1])
            if current:
                argvs.append(current)
            current = []
            continue
        if not current and (token in keywords or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token)):
            continue
        current.append(token)
    if current:
        argvs.append(current)
    return argvs


def pytest_invocations(block: str) -> list[list[str]]:
    """The argv AFTER `pytest` for every simple command that invokes it: a
    bare `pytest ...` or `python -m pytest ...` (any interpreter spelling).
    A quoted `pytest` inside an `echo` is not an invocation."""
    found: list[list[str]] = []
    for line in commands(block):
        for argv in _simple_commands(line):
            if not argv:
                continue
            if argv[0] == "pytest" or argv[0].endswith("/pytest"):
                found.append(argv[1:])
            elif (
                re.match(r"^(?:.*/)?python[0-9.]*$", argv[0])
                and len(argv) >= 3
                and argv[1] == "-m"
                and argv[2] == "pytest"
            ):
                found.append(argv[3:])
    return found


def compileall_invocations(block: str) -> list[list[str]]:
    found: list[list[str]] = []
    for line in commands(block):
        for argv in _simple_commands(line):
            if (
                len(argv) >= 3
                and re.match(r"^(?:.*/)?python[0-9.]*$", argv[0])
                and argv[1] == "-m"
                and argv[2] == "compileall"
            ):
                found.append(argv[3:])
    return found


def _condition(node: dict) -> str | None:
    """The `if:` as written, unwrapped from `${{ }}`. YAML parses `if: false`
    to the BOOLEAN False, so this stringifies before comparing."""
    if "if" not in node:
        return None
    raw = str(node["if"]).strip()
    if raw.startswith("${{") and raw.endswith("}}"):
        raw = raw[3:-2].strip()
    return raw


# --------------------------------------------------------------------------
# The stub harness: the swallow rule stops reading shell and starts running
# it. Same mechanism as the NCAAF lab; see that module's docstring for the
# measurements behind each choice (flat stubs so an ERR trap is caught, the
# pid test so a substitution's failure is not a false swallow, a marker so a
# preamble that died is not mistaken for an honest failure).
# --------------------------------------------------------------------------

HARNESS_SHELL = shutil.which("bash")

SHELL_KEYWORDS = frozenset(
    {
        "if", "then", "else", "elif", "fi", "for", "while", "until", "do",
        "done", "case", "esac", "in", "function", "select", "time", "coproc",
        "!", "{", "}", "[[", "]]",
    }
)

#: Builtins left real. A function shadows a builtin, so stubbing `true`, `:`
#: or `[` would make `cmd || true` look like a failure path.
SHELL_BUILTINS = frozenset(
    {
        "set", "unset", "exit", "return", "echo", "printf", "test", "[", "]",
        ":", "true", "false", "cd", "pwd", "read", "eval", "exec", "export",
        "local", "shift", "trap", "source", ".", "wait", "break", "continue",
        "declare", "typeset", "let", "mapfile", "readarray", "alias",
        "unalias", "builtin", "command", "hash", "type", "ulimit", "umask",
        "shopt", "popd", "pushd", "dirs", "readonly", "getopts", "kill",
        "jobs", "fg", "bg", "disown", "caller", "enable", "help", "times",
    }
)

STUB_SAFE_NAME = re.compile(r"^[A-Za-z_./][A-Za-z0-9_./+-]*$")
PREFIX_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
COMMAND_NOT_FOUND = re.compile(r"[:\s]([^:\s]+): command not found")
RUNNER_FILE_VARIABLES = ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH")
VARIABLE_WITH_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\s*:?[-=+?]")
VARIABLE_BRACED = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
VARIABLE_BARE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _uncommented(block: str) -> str:
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def _shell_regions(text: str) -> list[str]:
    """The text with `$(...)` and backtick spans lifted out, plus those spans.
    A command inside a substitution still runs, so it still needs a stub."""
    outer: list[str] = []
    inner: list[str] = []
    index, size = 0, len(text)
    while index < size:
        character = text[index]
        if character == "'":
            close = text.find("'", index + 1)
            close = size if close < 0 else close
            outer.append(text[index : close + 1])
            index = close + 1
            continue
        if character == "\\":
            outer.append(text[index : index + 2])
            index += 2
            continue
        if text.startswith("$(", index):
            depth, cursor = 1, index + 2
            while cursor < size and depth:
                if text[cursor] == "'":
                    close = text.find("'", cursor + 1)
                    cursor = (size if close < 0 else close) + 1
                    continue
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == "(":
                    depth += 1
                elif text[cursor] == ")":
                    depth -= 1
                cursor += 1
            inner.append(text[index + 2 : max(cursor - 1, index + 2)])
            outer.append(" ")
            index = cursor
            continue
        if character == "`":
            close = text.find("`", index + 1)
            close = size if close < 0 else close
            inner.append(text[index + 1 : close])
            outer.append(" ")
            index = close + 1
            continue
        outer.append(character)
        index += 1
    regions = ["".join(outer)]
    for span in inner:
        regions.extend(_shell_regions(span))
    return regions


def _scan_command_words(region: str, found: list[str]) -> None:
    current: list[str] = []
    quote: str | None = None
    at_command, skip_next = True, False
    index, size = 0, len(region)

    def flush() -> None:
        nonlocal current, at_command, skip_next
        token = "".join(current)
        current = []
        if not token:
            return
        if skip_next:
            skip_next = False
            return
        if not at_command:
            return
        if token in SHELL_KEYWORDS or PREFIX_ASSIGNMENT.match(token):
            return
        at_command = False
        if token in SHELL_BUILTINS or re.fullmatch(r"[0-9]+", token):
            return
        if "$" in token or "*" in token or "?" in token:
            return
        if token not in found:
            found.append(token)

    while index < size:
        character = region[index]
        if quote is not None:
            if character == quote:
                quote = None
            elif quote == '"' and character == "\\":
                index += 1
            current.append(character)
            index += 1
            continue
        if character in "'\"":
            quote = character
            current.append(character)
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character in "<>":
            flush()
            skip_next = True
            index += 1
            continue
        if character == "\n" or character in ";|&(){}`":
            flush()
            at_command, skip_next = True, False
            index += 1
            continue
        if character.isspace():
            flush()
            index += 1
            continue
        current.append(character)
        index += 1
    flush()


def command_words(block: str) -> list[str]:
    """Every word this block would invoke as a command. Over-collection is
    safe (an unused stub); under-collection is not (a command the sandbox
    cannot control), and `run_block_under_stubs` reports the latter."""
    found: list[str] = []
    for region in _shell_regions(_uncommented(block)):
        _scan_command_words(region, found)
    return found


def referenced_variables(block: str) -> list[str]:
    named = set(VARIABLE_BRACED.findall(block)) | set(VARIABLE_BARE.findall(block))
    return sorted(named - set(VARIABLE_WITH_DEFAULT.findall(block)))


def _quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def stub_preamble(
    words: list[str],
    failing: set[str] | None,
    failure_log: Path,
    any_failure_log: Path,
    unmodelled_log: Path,
    marker: Path,
    environment_log: Path,
) -> str:
    """One shell function per command word, of known exit status.

    Every stub also writes the value of `PYTEST_ADDOPTS` it was invoked with
    into `environment_log`, so a rule can ask what pytest would actually have
    read — whatever spelling put it there. `export PYTEST_ADDOPTS=-x`,
    `eval "export PYTEST_$(echo ADDOPTS)=-x"` and `printf 'PYTEST_%s=-x'
    ADDOPTS >> "$GITHUB_ENV"` are three spellings of the same act, and only
    the first is a token a grep could see.
    """
    assert HARNESS_SHELL, "no bash on PATH: the executed rule cannot run"
    lines = [
        "command_not_found_handle() { printf '%s\\n' \"$1\" >> "
        + _quote(str(unmodelled_log))
        + "; return 127; }",
        "readonly PATH",
    ]
    for word in words:
        status = 1 if (failing is None or word in failing) else 0
        body = ["%s() {" % word]
        if status:
            body.append(
                "  printf '%s\\n' " + _quote(word) + " >> " + _quote(str(any_failure_log))
            )
            body.append(
                '  __SWALLOW_PID="$( exec %s -c \'echo $PPID\' )"' % _quote(HARNESS_SHELL)
            )
            body.append(
                '  if [ "$__SWALLOW_PID" = "$$" ]; then printf \'%s\\n\' '
                + _quote(word)
                + " >> "
                + _quote(str(failure_log))
                + "; fi"
            )
        body.append(
            "  printf '%s\\t%s\\t%s\\n' " + _quote(word)
            + ' "${PYTEST_ADDOPTS-}" "${PYTEST_PLUGINS-}" >> '
            + _quote(str(environment_log))
        )
        body.append("  printf 'stub:%s\\n' " + _quote(word))
        body.append("  return %d" % status)
        body.append("}")
        lines.append("\n".join(body))
    lines.append(": > %s" % _quote(str(marker)))
    return "\n".join(lines) + "\n"


class BlockRun(NamedTuple):
    exit_code: int
    top_level_failures: list[str]
    unmodelled: list[str]
    stderr: str
    any_failures: list[str]
    #: (command word, PYTEST_ADDOPTS, PYTEST_PLUGINS) as that command saw them.
    addopts_seen: list[tuple[str, str, str]]
    #: What the block wrote into $GITHUB_ENV — bindings for every later step.
    github_env: str


def run_block_under_stubs(
    block: str,
    failing: set[str] | None,
    sandbox: Path,
    *,
    present: tuple[str, ...] = (),
) -> BlockRun:
    """Execute one run block with every command replaced by a stub.

    `failing` is the set of command words whose stub returns 1; `None` means
    all of them. Nothing real executes: PATH is an empty directory, the
    working directory is the sandbox, the environment is built from scratch.
    `present` names files or directories (a trailing `/` means directory) to
    create in the sandbox first, so a block that tests for `src/` can be run
    both with and without it.

    A `:` is appended after the block so a block that ends in a failing
    command cannot pass for the wrong reason: once a top-level command has
    failed, this block must not reach its end.
    """
    assert HARNESS_SHELL, "no bash on PATH: the executed rule cannot run"
    sandbox = Path(sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)
    for entry in present:
        target = sandbox / entry.rstrip("/")
        if entry.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
    failure_log = sandbox / "top_level_failures.txt"
    any_failure_log = sandbox / "any_failures.txt"
    unmodelled_log = sandbox / "unmodelled_commands.txt"
    marker = sandbox / "preamble_completed"
    environment_log = sandbox / "environment_seen.txt"
    for log in (failure_log, any_failure_log, unmodelled_log, environment_log):
        log.write_text("", encoding="utf-8")
    if marker.exists():
        marker.unlink()
    empty_path_dir = sandbox / "empty-path"
    empty_path_dir.mkdir(exist_ok=True)

    words = command_words(block)
    unstubbable = [word for word in words if not STUB_SAFE_NAME.match(word)]
    preamble = stub_preamble(
        [word for word in words if STUB_SAFE_NAME.match(word)],
        failing, failure_log, any_failure_log, unmodelled_log, marker, environment_log,
    )
    parsed = subprocess.run([HARNESS_SHELL, "-n"], input=preamble, capture_output=True, text=True)
    if parsed.returncode != 0:
        raise RuntimeError(f"the stub preamble does not parse: {parsed.stderr}")

    script = sandbox / "run_block.sh"
    script.write_text(preamble + block + "\n:\n", encoding="utf-8")
    environment = {
        "PATH": str(empty_path_dir),
        "LC_ALL": "C",
        "HOME": str(sandbox),
        "GITHUB_WORKSPACE": str(sandbox),
        "RUNNER_TEMP": str(sandbox),
    }
    for name in RUNNER_FILE_VARIABLES:
        target = sandbox / name.lower()
        target.write_text("", encoding="utf-8")
        environment[name] = str(target)
    for name in referenced_variables(block):
        environment.setdefault(name, "__harness__")

    completed = subprocess.run(
        [HARNESS_SHELL, "-e", str(script)],
        cwd=sandbox, env=environment, capture_output=True, text=True, timeout=60,
    )
    if not marker.exists():
        raise RuntimeError(
            "the stub preamble did not run to completion, so the exit code "
            f"is not a verdict on the block: {completed.stderr}"
        )
    unmodelled = sorted(
        set(unstubbable)
        | set(unmodelled_log.read_text(encoding="utf-8").split())
        | set(COMMAND_NOT_FOUND.findall(completed.stderr))
    )
    addopts_seen = []
    for line in environment_log.read_text(encoding="utf-8").splitlines():
        fields = (line.split("\t") + ["", ""])[:3]
        addopts_seen.append((fields[0], fields[1], fields[2]))
    return BlockRun(
        completed.returncode,
        failure_log.read_text(encoding="utf-8").split(),
        unmodelled,
        completed.stderr,
        any_failure_log.read_text(encoding="utf-8").split(),
        addopts_seen,
        (sandbox / "github_env").read_text(encoding="utf-8"),
    )


def swallow_findings(block: str, *, present: tuple[str, ...] = ()) -> list[str]:
    """Run the block under every single-failure configuration; report the
    configurations where a command failed and the block still exited 0.
    Every-command-failing alone is not enough: a block stops at its first
    gate and a swallow further down is never reached.

    STRICT, on purpose, because the gate job's blocks are simple: a stub that
    failed ANYWHERE — top level, subshell, pipeline element, command
    substitution, background job — with the block exiting 0 is a finding.
    The NCAAF linter exempts a failure inside `$(...)` so that a summary line
    like `echo "$(head -n 1 f)"` is not a swallow; the gate job here writes
    no such line, and the exemption is exactly the width of `(pytest) ||
    echo` and `pytest | tee`, both of which exit 0 under `bash -e` with the
    suite red. If the gate ever needs a substitution whose failure is
    genuinely immaterial, the answer is `|| exit 1` on it, not a wider rule.
    """
    findings: list[str] = []
    words = command_words(block)
    with tempfile.TemporaryDirectory() as directory:
        sandbox = Path(directory)
        for failing in [None] + [{word} for word in words]:
            result = run_block_under_stubs(block, failing, sandbox, present=present)
            label = "every command failing" if failing is None else (
                "only %s failing" % ", ".join(sorted(failing))
            )
            if result.unmodelled:
                findings.append(
                    f"with {label}, {result.unmodelled} reached the shell with no "
                    "stub behind it, so this block was never modelled."
                )
                continue
            if result.exit_code == 0 and result.any_failures:
                where = (
                    "at the top level"
                    if result.top_level_failures
                    else "in a subshell, pipeline, substitution or background job"
                )
                findings.append(
                    f"with {label}, {sorted(set(result.any_failures))} failed "
                    f"{where} and the block still exited 0. In CI that is a green "
                    "step over a failed command."
                )
    return findings


# --------------------------------------------------------------------------
# The rules. Each takes a directory of workflows (so the synthetic controls
# below can run the real thing over a temp directory) and asserts.
# --------------------------------------------------------------------------


def _documents(directory: Path) -> list[tuple[Path, Any]]:
    files = workflow_files_in(directory)
    assert files, f"{directory} holds no workflow; a linter with nothing to lint is green"
    return [(path, load(path)) for path in files]


def gate_jobs(directory: Path) -> list[tuple[Path, str, dict]]:
    """Every job in `directory` whose `name:` equals REQUIRED_CHECK."""
    found: list[tuple[Path, str, dict]] = []
    for path, document in _documents(directory):
        for job_name, job in jobs_of(document).items():
            if str(job.get("name", "")).strip() == REQUIRED_CHECK:
                found.append((path, job_name, job))
    return found


def the_gate(directory: Path) -> tuple[Path, str, dict]:
    found = gate_jobs(directory)
    assert len(found) == 1, (
        f"exactly one job must carry `name: {REQUIRED_CHECK}` — the context branch "
        f"protection requires — and {len(found)} do: "
        f"{[(p.name, j) for p, j, _ in found]}. Zero means the check goes pending "
        "forever; two means a job that runs nothing can report the name."
    )
    return found[0]


def suite_steps(job: dict) -> list[dict]:
    return [step for step in steps_of(job) if isinstance(step.get("run"), str) and pytest_invocations(step["run"])]


def check_every_workflow_parses_and_declares_a_trigger(directory: Path) -> None:
    for path, document in _documents(directory):
        assert isinstance(document, dict), f"{path.name}: not a mapping"
        assert triggers(document) is not None, f"{path.name}: declares no `on:` trigger"
        assert jobs_of(document), f"{path.name}: declares no job"


def check_no_workflow_overrides_the_shell(directory: Path) -> None:
    """A step-level `shell:` or a `defaults.run.shell` at job or workflow
    level must be the bare keyword `bash` or `sh`. `bash {0}` is the default
    shell minus its `-e`, and it is the least conspicuous way to disarm every
    executed verdict here."""
    for path, document in _documents(directory):
        for mapping in mappings(document):
            if "shell" not in mapping:
                continue
            declared = mapping["shell"]
            assert isinstance(declared, str) and declared in SAFE_SHELLS, (
                f"{path.name}: `shell: {declared!r}`. Only {sorted(SAFE_SHELLS)} are "
                "accepted, as bare keywords; a value with an argument is a custom "
                "command line and `bash {0}` drops errexit."
            )


def check_python_version_is_pinned_to_an_exact_minor(directory: Path) -> None:
    for path, document in _documents(directory):
        for mapping in mappings(document):
            if "python-version" not in mapping:
                continue
            version = str(mapping["python-version"]).strip()
            assert re.fullmatch(r"3\.[0-9]+", version), (
                f"{path.name}: python-version {version!r} is not an exact minor; "
                "'3.x' or '3' moves the lab onto an untested interpreter silently."
            )


def check_no_pytest_step_anywhere_is_narrowed_or_disabled(directory: Path) -> None:
    """Every step in every workflow that runs pytest runs the whole suite and
    cannot be switched off. The pytest rules are universal: a narrowed run in
    the manual Thursday workflow is a false report about that run too."""
    for path, document in _documents(directory):
        for mapping in mappings(document):
            environment = mapping.get("env")
            if isinstance(environment, dict):
                bound = [k for k in environment if str(k).strip().upper() in PYTEST_ENVIRONMENT_NAMES]
                assert not bound, (
                    f"{path.name}: an `env:` binds {bound}. pytest reads PYTEST_ADDOPTS "
                    "as if the flags had been typed, and PYTEST_PLUGINS as a module to "
                    "load before the guards are counted."
                )
        for name, block in run_blocks(document):
            for line in commands(block):
                # The raw line, quotes included: `echo "PYTEST_ADDOPTS=-x" >>
                # "$GITHUB_ENV"` narrows every later step from inside a string.
                assert not PYTEST_ADDOPTS_PATTERN.search(line), (
                    f"{path.name}: step {name!r} sets {PYTEST_ADDOPTS} from the shell: {line!r}"
                )
        for job_name, job in jobs_of(document).items():
            for step in suite_steps(job):
                name = str(step.get("name", "<unnamed step>"))
                for arguments in pytest_invocations(step["run"]):
                    plugin_values = {
                        index + 1 for index, flag in enumerate(arguments) if flag == "-p"
                    }
                    for index, argument in enumerate(arguments):
                        if index in plugin_values:
                            # `-p no:cacheprovider` disables a plugin; `-p anything_else`
                            # LOADS one, and a loaded plugin can deselect the guards
                            # after they were counted.
                            assert argument.startswith("no:"), (
                                f"{path.name}: step {name!r} loads a pytest plugin with "
                                f"-p {argument}; a plugin can deselect or fake any test."
                            )
                            continue
                        assert argument.startswith("-"), (
                            f"{path.name}: step {name!r} passes the positional "
                            f"{argument!r} to pytest. A path or node id selects a "
                            "subset exactly as --ignore does."
                        )
                        if argument.startswith("--"):
                            flag = argument.split("=", 1)[0]
                            assert flag not in NARROWING_PYTEST_LONG_FLAGS, (
                                f"{path.name}: step {name!r} narrows the suite with {flag}"
                            )
                        elif argument != "-":
                            cluster = set(argument[1:].split("=", 1)[0])
                            narrowing = cluster & NARROWING_PYTEST_SHORT_FLAGS
                            assert not narrowing, (
                                f"{path.name}: step {name!r} narrows the suite with "
                                f"{argument} (-{''.join(sorted(narrowing))})"
                            )
                    assert arguments[-1:] != ["-p"], (
                        f"{path.name}: step {name!r} ends its pytest line with a bare -p"
                    )
                assert "working-directory" not in step, (
                    f"{path.name}: the pytest step {name!r} sets working-directory; "
                    "the suite runs from the repository root or not at all."
                )
                assert not step.get("continue-on-error"), (
                    f"{path.name}: the pytest step {name!r} carries continue-on-error"
                )
                condition = _condition(step)
                assert condition in (None, PERMITTED_CONDITION), (
                    f"{path.name}: the pytest step {name!r} carries `if: {condition}`; "
                    "any expression that can evaluate false is a gate that can be off."
                )


def check_exactly_one_job_carries_the_required_check_name(directory: Path) -> None:
    path, _, _ = the_gate(directory)
    assert path.name == "tests.yml", (
        f"the job named {REQUIRED_CHECK!r} lives in {path.name}, not tests.yml"
    )


def check_the_gate_runs_the_whole_suite(directory: Path) -> None:
    path, job_name, job = the_gate(directory)
    steps = suite_steps(job)
    assert steps, (
        f"{path.name}: job {job_name!r} has no step that INVOKES pytest as a "
        "command (`python -m pytest` or `pytest`). An `echo` that mentions pytest "
        "is not an invocation."
    )
    for step in steps:
        for arguments in pytest_invocations(step["run"]):
            plugin_values = {index + 1 for index, flag in enumerate(arguments) if flag == "-p"}
            positionals = [
                argument for index, argument in enumerate(arguments)
                if index not in plugin_values and not argument.startswith("-")
            ]
            assert not positionals, (
                f"{path.name}: pytest is given a positional argument: {positionals}"
            )


def check_the_gate_cannot_be_switched_off(directory: Path) -> None:
    """No `if:` (but `always()`), no continue-on-error, no `shell:`, no
    `defaults.run.shell` — on the gate job, on its suite steps, and on the
    workflow. A job-level condition switches every step off at once."""
    path, job_name, job = the_gate(directory)
    document = load(path)
    job_condition = _condition(job)
    assert job_condition is None, (
        f"{path.name}: job {job_name!r} carries `if: {job_condition}`"
    )
    assert not job.get("continue-on-error"), f"{path.name}: job {job_name!r} continues on error"
    for owner, node in (("the workflow", document), (f"job {job_name!r}", job)):
        defaults = node.get("defaults") if isinstance(node, dict) else None
        run_defaults = defaults.get("run") if isinstance(defaults, dict) else None
        assert not (isinstance(run_defaults, dict) and "shell" in run_defaults), (
            f"{path.name}: {owner} sets defaults.run.shell"
        )
    for step in steps_of(job):
        name = str(step.get("name", "<unnamed step>"))
        assert not step.get("continue-on-error"), f"{path.name}: step {name!r} continues on error"
        assert "shell" not in step, f"{path.name}: step {name!r} overrides the shell"
        condition = _condition(step)
        assert condition in (None, PERMITTED_CONDITION), (
            f"{path.name}: step {name!r} carries `if: {condition}`; only "
            f"`{PERMITTED_CONDITION}` widens when a step runs."
        )


def check_the_gate_trigger_is_unfiltered(directory: Path) -> None:
    """A `paths:`, `paths-ignore:`, `branches:` or `types:` filter on
    `pull_request` makes a required check pending — never failed — on the PR
    it does not fire for, and a change that breaks a guard rarely touches the
    guard's own file."""
    path, _, _ = the_gate(directory)
    on = triggers(load(path))
    if isinstance(on, str):
        on = {on: None}
    if isinstance(on, list):
        on = {str(event): None for event in on}
    assert isinstance(on, dict) and "pull_request" in on, (
        f"{path.name}: the gate workflow does not trigger on pull_request"
    )
    filters = on["pull_request"]
    assert not filters, (
        f"{path.name}: pull_request carries {sorted(filters)}; the required check "
        "must fire on every pull request without a filter."
    )


def check_the_gate_workflow_holds_no_credential(directory: Path) -> None:
    """The suite must pass with no credential: that is the proof no test
    depends on a live provider. Read over RAW TEXT, comments included."""
    path, _, _ = the_gate(directory)
    text = path.read_text(encoding="utf-8")
    assert not SECRET_REFERENCE.search(text), f"{path.name}: accesses the secrets context"
    for expression in GITHUB_EXPRESSION.findall(text):
        assert not SECRETS_WORD.search(expression), (
            f"{path.name}: interpolates the secrets context: {expression!r}"
        )
    document = load(path)
    for mapping in mappings(document):
        environment = mapping.get("env")
        if isinstance(environment, dict):
            bound = sorted(set(map(str, environment)) & CREDENTIAL_NAMES)
            assert not bound, f"{path.name}: an `env:` binds {bound}"
    permissions = document.get("permissions") if isinstance(document, dict) else None
    assert isinstance(permissions, dict) and permissions.get("contents") == "read", (
        f"{path.name}: permissions must be declared and contents: read"
    )
    assert all(value == "read" for value in permissions.values()), (
        f"{path.name}: a write permission on the gate workflow: {permissions}"
    )


def check_no_run_block_in_the_gate_swallows_a_failure(directory: Path) -> None:
    """THE EXECUTED RULE. Every run block in the gate job, run under stubs."""
    path, job_name, job = the_gate(directory)
    present = _workspace_entries(job)
    findings: list[str] = []
    for step in steps_of(job):
        block = step.get("run")
        if not isinstance(block, str):
            continue
        name = str(step.get("name", "<unnamed step>"))
        for finding in swallow_findings(block, present=present):
            findings.append(f"{path.name}: step {name!r}: {finding}")
    assert not findings, "\n".join(findings)


def check_a_failing_suite_fails_the_gate_step(directory: Path) -> None:
    """Sharper than the swallow rule: with ONLY the command that carries
    pytest failing, the suite step must exit non-zero — that is the exit code
    branch protection reads, observed rather than inferred."""
    path, _, job = the_gate(directory)
    present = _workspace_entries(job)
    steps = suite_steps(job)
    assert steps, f"{path.name}: no pytest step to execute"
    with tempfile.TemporaryDirectory() as directory_name:
        sandbox = Path(directory_name)
        for step in steps:
            block = step["run"]
            carriers = [
                word for word in command_words(block)
                if word == "pytest" or re.match(r"^(?:.*/)?python[0-9.]*$", word)
            ]
            assert carriers, f"{path.name}: the pytest step has no command word carrying pytest"
            for carrier in carriers:
                result = run_block_under_stubs(block, {carrier}, sandbox, present=present)
                assert not result.unmodelled, f"{path.name}: unmodelled {result.unmodelled}"
                assert result.exit_code != 0, (
                    f"{path.name}: step {step.get('name')!r} exited 0 with {carrier} "
                    "failing. A red suite is a green check."
                )


def check_pytest_addopts_is_empty_when_pytest_runs(directory: Path) -> None:
    """OBSERVED, not grepped: run every block in the gate job with every stub
    succeeding and read the `PYTEST_ADDOPTS` each command was invoked with,
    and what each block wrote into `$GITHUB_ENV`. A name assembled at runtime
    — `eval "export PYTEST_$(echo ADDOPTS)=-x"`, `printf 'PYTEST_%s=-x'
    ADDOPTS >> "$GITHUB_ENV"` — has no token for the text rule to find, and
    the variable is exactly as set when pytest reads it."""
    path, job_name, job = the_gate(directory)
    present = _workspace_entries(job)
    with tempfile.TemporaryDirectory() as directory_name:
        for index, step in enumerate(steps_of(job)):
            block = step.get("run")
            if not isinstance(block, str):
                continue
            name = str(step.get("name", "<unnamed step>"))
            result = run_block_under_stubs(block, set(), Path(directory_name) / str(index), present=present)
            assert not result.unmodelled, f"{path.name}: step {name!r}: unmodelled {result.unmodelled}"
            bound = [
                (word, addopts, plugins)
                for word, addopts, plugins in result.addopts_seen
                if addopts or plugins
            ]
            assert not bound, (
                f"{path.name}: step {name!r} invoked {bound[0][0]} with "
                f"PYTEST_ADDOPTS={bound[0][1]!r} PYTEST_PLUGINS={bound[0][2]!r} in "
                "its environment. pytest reads the first as if the flags had been "
                "typed and the second as a module to load, whatever spelling set them."
            )
            assert not PYTEST_ADDOPTS_PATTERN.search(result.github_env), (
                f"{path.name}: step {name!r} wrote PYTEST_ADDOPTS or PYTEST_PLUGINS into "
                f"$GITHUB_ENV, which binds it for every later step: {result.github_env!r}"
            )
            assert not result.github_env.strip(), (
                f"{path.name}: step {name!r} writes into $GITHUB_ENV; the gate job "
                f"has no reason to rebind anything for a later step: {result.github_env!r}"
            )


def _workspace_entries(job: dict) -> tuple[str, ...]:
    """What the compile step expects on disk, so its existence assertions
    pass in the sandbox and the executed rules get past them to the command
    they are judging. Directories end in `/`."""
    entries: list[str] = []
    for step in steps_of(job):
        block = step.get("run")
        if not isinstance(block, str):
            continue
        for arguments in compileall_invocations(block):
            for argument in arguments:
                if argument.startswith("-"):
                    continue
                entries.append(argument if "." in Path(argument).name else argument.rstrip("/") + "/")
    return tuple(dict.fromkeys(entries))


def check_the_compile_step_fails_on_a_missing_path(directory: Path) -> None:
    """`python -m compileall -q src` prints "Can't list 'src'" and EXITS 0
    when the path names nothing (run on 3.12.13, not recalled). So the step
    must assert each target exists first, and pass `-f` so a stale
    `__pycache__` cannot mask a source that no longer parses. Both halves are
    observed: the block is run with every stub succeeding in a sandbox that
    lacks one target at a time, and must exit non-zero each time."""
    path, _, job = the_gate(directory)
    blocks = [
        (str(step.get("name", "<unnamed step>")), step["run"])
        for step in steps_of(job)
        if isinstance(step.get("run"), str) and compileall_invocations(step["run"])
    ]
    assert blocks, f"{path.name}: the gate job has no compileall step"
    entries = _workspace_entries(job)
    assert entries, f"{path.name}: compileall is given no path"
    with tempfile.TemporaryDirectory() as directory_name:
        sandbox_root = Path(directory_name)
        for name, block in blocks:
            for arguments in compileall_invocations(block):
                assert "-f" in arguments, (
                    f"{path.name}: step {name!r} runs compileall without -f"
                )
            for index, missing in enumerate(entries):
                sandbox = sandbox_root / f"without-{index}"
                sandbox.mkdir()
                others = tuple(entry for entry in entries if entry != missing)
                result = run_block_under_stubs(block, set(), sandbox, present=others)
                assert not result.unmodelled, f"{path.name}: unmodelled {result.unmodelled}"
                assert result.exit_code != 0, (
                    f"{path.name}: step {name!r} exited 0 with {missing!r} absent. "
                    "compileall on a missing path is a green report about no files."
                )
            complete = sandbox_root / "complete"
            complete.mkdir()
            result = run_block_under_stubs(block, set(), complete, present=entries)
            assert result.exit_code == 0 and not result.unmodelled, (
                f"{path.name}: step {name!r} does not pass with every path present "
                f"and every command succeeding: {result}"
            )


CHECKS: dict[str, Callable[[Path], None]] = {
    "every_workflow_parses_and_declares_a_trigger": check_every_workflow_parses_and_declares_a_trigger,
    "no_workflow_overrides_the_shell": check_no_workflow_overrides_the_shell,
    "python_version_is_pinned_to_an_exact_minor": check_python_version_is_pinned_to_an_exact_minor,
    "no_pytest_step_anywhere_is_narrowed_or_disabled": check_no_pytest_step_anywhere_is_narrowed_or_disabled,
    "exactly_one_job_carries_the_required_check_name": check_exactly_one_job_carries_the_required_check_name,
    "the_gate_runs_the_whole_suite": check_the_gate_runs_the_whole_suite,
    "the_gate_cannot_be_switched_off": check_the_gate_cannot_be_switched_off,
    "the_gate_trigger_is_unfiltered": check_the_gate_trigger_is_unfiltered,
    "the_gate_workflow_holds_no_credential": check_the_gate_workflow_holds_no_credential,
    "no_run_block_in_the_gate_swallows_a_failure": check_no_run_block_in_the_gate_swallows_a_failure,
    "a_failing_suite_fails_the_gate_step": check_a_failing_suite_fails_the_gate_step,
    "the_compile_step_fails_on_a_missing_path": check_the_compile_step_fails_on_a_missing_path,
    "pytest_addopts_is_empty_when_pytest_runs": check_pytest_addopts_is_empty_when_pytest_runs,
}


# --------------------------------------------------------------------------
# The rules, applied to the real .github/workflows/*.yml.
# --------------------------------------------------------------------------


def test_the_workflow_directory_is_not_empty() -> None:
    assert WORKFLOW_FILES, "no workflow found; a linter with nothing to lint is green"
    assert any(path.name == "tests.yml" for path in WORKFLOW_FILES)


def test_the_executed_rules_have_a_shell_to_run_in() -> None:
    assert HARNESS_SHELL, "no bash on PATH: absence is never a pass"


@pytest.mark.parametrize("rule", sorted(CHECKS), ids=sorted(CHECKS))
def test_the_real_workflows_pass_every_rule(rule: str) -> None:
    CHECKS[rule](WORKFLOWS_DIR)


def test_the_real_gate_is_the_required_check_context() -> None:
    """The name is a contract with branch protection, pinned as a value."""
    path, job_name, job = the_gate(WORKFLOWS_DIR)

    assert (path.name, job_name, job["name"]) == ("tests.yml", "pytest", REQUIRED_CHECK)


def test_the_real_pytest_invocation_survives_the_line_joining() -> None:
    """The real suite line, as `commands` reads it, is a pytest invocation
    with no positional — proof the line-joiner is not hiding the line the
    narrowing rule needs to see."""
    _, _, job = the_gate(WORKFLOWS_DIR)
    invocations = [
        arguments
        for step in suite_steps(job)
        for arguments in pytest_invocations(step["run"])
    ]

    assert invocations, "no pytest invocation found in the gate job"
    assert invocations == [["-q"]], invocations


def test_every_real_run_block_in_the_gate_is_actually_executed() -> None:
    """The swallow rule runs every block with a command in it, and the
    harness models every command word: nothing reaches the shell unstubbed."""
    _, _, job = the_gate(WORKFLOWS_DIR)
    present = _workspace_entries(job)
    executed = 0
    with tempfile.TemporaryDirectory() as directory:
        for step in steps_of(job):
            block = step.get("run")
            if not isinstance(block, str) or not command_words(block):
                continue
            result = run_block_under_stubs(block, None, Path(directory), present=present)
            assert not result.unmodelled, result
            executed += 1

    assert executed >= 3, executed


def test_nothing_real_runs_under_the_stub_harness(tmp_path: Path) -> None:
    """`python` in a block must be the stub, not an interpreter."""
    probe = tmp_path / "probe.txt"
    block = f"python -c 'open({str(probe)!r}, \"w\").write(\"ran\")'\n"

    result = run_block_under_stubs(block, set(), tmp_path / "sandbox")

    assert result.exit_code == 0
    assert not probe.exists()


# --------------------------------------------------------------------------
# Synthetic controls: a good workflow passes every rule, and every rule has a
# mutation that makes it fire.
# --------------------------------------------------------------------------

GOOD_WORKFLOW = """\
name: Tests
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  pytest:
    name: Full test suite
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Compile every module
        run: |
          for d in src scripts; do
            [ -d "$d" ] || { echo "::error::$d is missing"; exit 1; }
          done
          [ -f app.py ] || { echo "::error::app.py is missing"; exit 1; }
          python -m compileall -q -f src scripts app.py
      - name: Run the full test suite
        env:
          PYTHONPATH: src
        run: |
          python -m pytest -q
      - name: Confirm no odds were fetched
        if: always()
        run: |
          echo "This job installs the project and runs unit tests only."
"""

JOB_NAME_LINE = "    name: Full test suite\n"
SUITE_LINE = "          python -m pytest -q\n"
SUITE_STEP_HEADER = "      - name: Run the full test suite\n"
COMPILE_LINE = "          python -m compileall -q -f src scripts app.py\n"
PULL_REQUEST_LINE = "  pull_request:\n"
PERMISSIONS_BLOCK = "permissions:\n  contents: read\n"
PYTHON_LINE = '          python-version: "3.11"\n'


def mutate(anchor: str, replacement: str) -> str:
    """GOOD_WORKFLOW with exactly one substitution, or a loud failure: a
    mutation whose anchor drifted would feed the linter the good text."""
    assert anchor in GOOD_WORKFLOW, f"anchor no longer in GOOD_WORKFLOW: {anchor!r}"
    return GOOD_WORKFLOW.replace(anchor, replacement, 1)


def workflow_dir(tmp_path: Path, text: str, name: str = "tests.yml") -> Path:
    directory = tmp_path / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")
    return directory


def assert_rejects(check: Callable[[Path], None], directory: Path) -> None:
    with pytest.raises(AssertionError):
        check(directory)


@pytest.mark.parametrize("rule", sorted(CHECKS), ids=sorted(CHECKS))
def test_the_control_workflow_passes_every_rule(tmp_path: Path, rule: str) -> None:
    CHECKS[rule](workflow_dir(tmp_path, GOOD_WORKFLOW))


def test_every_rule_has_a_case_that_proves_it_fires() -> None:
    proofs = {
        "every_workflow_parses_and_declares_a_trigger": "test_a_workflow_with_no_trigger_is_rejected",
        "no_workflow_overrides_the_shell": "test_a_custom_shell_is_rejected",
        "python_version_is_pinned_to_an_exact_minor": "test_an_unpinned_python_version_is_rejected",
        "no_pytest_step_anywhere_is_narrowed_or_disabled": "test_a_narrowing_pytest_flag_is_rejected",
        "exactly_one_job_carries_the_required_check_name": "test_a_renamed_gate_job_is_rejected",
        "the_gate_runs_the_whole_suite": "test_an_echo_in_place_of_pytest_is_rejected",
        "the_gate_cannot_be_switched_off": "test_a_condition_on_the_gate_is_rejected",
        "the_gate_trigger_is_unfiltered": "test_a_filtered_pull_request_trigger_is_rejected",
        "the_gate_workflow_holds_no_credential": "test_a_secret_in_the_gate_workflow_is_rejected",
        "no_run_block_in_the_gate_swallows_a_failure": "test_a_swallowed_failure_is_rejected",
        "a_failing_suite_fails_the_gate_step": "test_a_suite_whose_failure_does_not_reach_the_exit_code_is_rejected",
        "the_compile_step_fails_on_a_missing_path": "test_a_compile_step_that_tolerates_a_missing_path_is_rejected",
        "pytest_addopts_is_empty_when_pytest_runs": "test_a_runtime_assembled_pytest_addopts_is_rejected",
    }
    unproven = sorted(set(CHECKS) - set(proofs))
    assert not unproven, f"rules with no synthetic case proving they fire: {unproven}"
    missing = sorted(name for name in proofs.values() if name not in globals())
    assert not missing, f"named proofs that do not exist in this module: {missing}"


def test_a_workflow_with_no_trigger_is_rejected(tmp_path: Path) -> None:
    text = GOOD_WORKFLOW.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", "")
    assert text != GOOD_WORKFLOW
    assert_rejects(check_every_workflow_parses_and_declares_a_trigger, workflow_dir(tmp_path, text))
    for bad in ("- not: a workflow\n", "just a string\n", ""):
        assert_rejects(check_every_workflow_parses_and_declares_a_trigger, workflow_dir(tmp_path, bad))


@pytest.mark.parametrize(
    "shell", ["bash {0}", "/bin/bash {0}", "bash -c {0}", "pwsh", "python", "bash "],
)
def test_a_custom_shell_is_rejected(tmp_path: Path, shell: str) -> None:
    step = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + f"        shell: {shell!r}\n")
    assert_rejects(check_no_workflow_overrides_the_shell, workflow_dir(tmp_path, step))
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, step))
    job_default = mutate(
        "    runs-on: ubuntu-latest\n",
        f"    runs-on: ubuntu-latest\n    defaults:\n      run:\n        shell: {shell!r}\n",
    )
    assert_rejects(check_no_workflow_overrides_the_shell, workflow_dir(tmp_path, job_default))
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, job_default))
    workflow_default = mutate(
        PERMISSIONS_BLOCK, PERMISSIONS_BLOCK + f"defaults:\n  run:\n    shell: {shell!r}\n"
    )
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, workflow_default))


def test_a_bare_bash_shell_is_accepted(tmp_path: Path) -> None:
    """The one shell value the manual Thursday workflow actually uses."""
    step = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        shell: bash\n")
    check_no_workflow_overrides_the_shell(workflow_dir(tmp_path, step))


@pytest.mark.parametrize("version", ["3.x", "3", "latest", "'3.11.*'"])
def test_an_unpinned_python_version_is_rejected(tmp_path: Path, version: str) -> None:
    assert_rejects(
        check_python_version_is_pinned_to_an_exact_minor,
        workflow_dir(tmp_path, mutate(PYTHON_LINE, f"          python-version: {version}\n")),
    )


@pytest.mark.parametrize(
    "suite_line",
    [
        "python -m pytest -q -x",
        "python -m pytest -qx",
        "python -m pytest --exitfirst",
        "python -m pytest --maxfail=1",
        "python -m pytest -k 'not secrets'",
        "python -m pytest -m 'not slow'",
        "python -m pytest --ignore=tests/test_no_secrets_committed.py",
        "python -m pytest --deselect tests/test_no_secrets_committed.py",
        "python -m pytest -c other.ini",
        "python -m pytest --config-file other.ini",
        "python -m pytest --confcutdir=src",
        "python -m pytest -o addopts=-x",
        "python -m pytest --override-ini=addopts=-x",
        "python -m pytest --runxfail",
        "python -m pytest tests/test_value.py",
        "python -m pytest tests",
        "python -m pytest -q \\\n            -k fast",
        "pytest -x",
        "python3 -m pytest -x",
    ],
)
def test_a_narrowing_pytest_flag_is_rejected(tmp_path: Path, suite_line: str) -> None:
    directory = workflow_dir(tmp_path, mutate(SUITE_LINE, f"          {suite_line}\n"))
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, directory)


def test_pytest_addopts_is_rejected_at_every_level(tmp_path: Path) -> None:
    step_env = mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          PYTEST_ADDOPTS: -x\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, step_env))
    job_env = mutate("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    env:\n      pytest_addopts: -k fast\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, job_env))
    workflow_env = mutate(PERMISSIONS_BLOCK, PERMISSIONS_BLOCK + "env:\n  PYTEST_ADDOPTS: --maxfail=1\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, workflow_env))
    exported = mutate(SUITE_LINE, "          export PYTEST_ADDOPTS=-x\n" + SUITE_LINE)
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, exported))
    github_env = mutate(SUITE_LINE, '          echo "PYTEST_ADDOPTS=-x" >> "$GITHUB_ENV"\n' + SUITE_LINE)
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, github_env))


def test_a_plugin_load_or_a_working_directory_on_the_suite_is_rejected(tmp_path: Path) -> None:
    plugin_env = mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          PYTEST_PLUGINS: dropguards\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, plugin_env))
    plugin_flag = mutate(SUITE_LINE, "          python -m pytest -q -p dropguards\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, plugin_flag))
    disabled_plugin = mutate(SUITE_LINE, "          python -m pytest -q -p no:cacheprovider\n")
    check_no_pytest_step_anywhere_is_narrowed_or_disabled(workflow_dir(tmp_path, disabled_plugin))
    moved = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        working-directory: docs\n")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, moved))


def test_a_narrowed_pytest_step_in_another_workflow_is_rejected(tmp_path: Path) -> None:
    """The pytest rules are universal, not gate-only."""
    directory = workflow_dir(tmp_path, GOOD_WORKFLOW)
    other = GOOD_WORKFLOW.replace(JOB_NAME_LINE, "    name: Manual\n").replace(SUITE_LINE, "          python -m pytest -x\n")
    (directory / "manual.yml").write_text(other, encoding="utf-8")
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, directory)


def test_a_renamed_gate_job_is_rejected(tmp_path: Path) -> None:
    renamed = mutate(JOB_NAME_LINE, "    name: Full test suite (fast)\n")
    assert_rejects(check_exactly_one_job_carries_the_required_check_name, workflow_dir(tmp_path, renamed))
    removed = mutate(JOB_NAME_LINE, "")
    assert_rejects(check_exactly_one_job_carries_the_required_check_name, workflow_dir(tmp_path, removed))
    # Two jobs with the name: a second job that runs nothing could report it.
    directory = workflow_dir(tmp_path, GOOD_WORKFLOW)
    (directory / "other.yml").write_text(
        GOOD_WORKFLOW.replace(SUITE_LINE, "          echo skipped\n"), encoding="utf-8"
    )
    assert_rejects(check_exactly_one_job_carries_the_required_check_name, directory)
    # The name in a workflow other than tests.yml.
    moved = workflow_dir(tmp_path / "moved", GOOD_WORKFLOW, name="ci.yml")
    assert_rejects(check_exactly_one_job_carries_the_required_check_name, moved)


@pytest.mark.parametrize(
    "suite_line",
    [
        'echo "python -m pytest -q"',
        "echo python -m pytest -q",
        "true",
        "python -m compileall -q src",
        "python -c 'import pytest'",
    ],
)
def test_an_echo_in_place_of_pytest_is_rejected(tmp_path: Path, suite_line: str) -> None:
    directory = workflow_dir(tmp_path, mutate(SUITE_LINE, f"          {suite_line}\n"))
    assert_rejects(check_the_gate_runs_the_whole_suite, directory)


def test_a_pytest_invocation_inside_a_condition_is_still_seen() -> None:
    """`if ! python -m pytest; then` invokes pytest; the swallow rule is what
    rejects it, and this is what stops it being rejected for the wrong
    reason (no invocation found)."""
    assert pytest_invocations("if ! python -m pytest -q; then\n  echo failed\nfi\n") == [["-q"]]
    assert pytest_invocations('echo "python -m pytest -q"') == []


@pytest.mark.parametrize(
    "condition",
    ["false", "${{ false }}", "github.event_name == 'schedule'", "${{ !cancelled() && false }}", "success()"],
)
def test_a_condition_on_the_gate_is_rejected(tmp_path: Path, condition: str) -> None:
    step = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + f"        if: {condition}\n")
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, step))
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, step))
    job = mutate("    runs-on: ubuntu-latest\n", f"    runs-on: ubuntu-latest\n    if: {condition}\n")
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, job))


def test_always_is_the_one_condition_accepted(tmp_path: Path) -> None:
    step = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        if: always()\n")
    check_the_gate_cannot_be_switched_off(workflow_dir(tmp_path, step))


def test_continue_on_error_is_rejected(tmp_path: Path) -> None:
    step = mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        continue-on-error: true\n")
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, step))
    assert_rejects(check_no_pytest_step_anywhere_is_narrowed_or_disabled, workflow_dir(tmp_path, step))
    job = mutate("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    continue-on-error: true\n")
    assert_rejects(check_the_gate_cannot_be_switched_off, workflow_dir(tmp_path, job))


@pytest.mark.parametrize(
    "filters",
    [
        "    paths: ['src/**']\n",
        "    paths-ignore: ['docs/**']\n",
        "    branches: [main]\n",
        "    branches-ignore: [main]\n",
        "    types: [opened]\n",
    ],
)
def test_a_filtered_pull_request_trigger_is_rejected(tmp_path: Path, filters: str) -> None:
    directory = workflow_dir(tmp_path, mutate(PULL_REQUEST_LINE, PULL_REQUEST_LINE + filters))
    assert_rejects(check_the_gate_trigger_is_unfiltered, directory)


def test_a_missing_pull_request_trigger_is_rejected(tmp_path: Path) -> None:
    directory = workflow_dir(tmp_path, mutate(PULL_REQUEST_LINE, ""))
    assert_rejects(check_the_gate_trigger_is_unfiltered, directory)


@pytest.mark.parametrize(
    "mutation",
    [
        ("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          EPL_ODDS_API_KEY: ${{ secrets.EPL_ODDS_API_KEY }}\n"),
        ("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          KEY: ${{ secrets['EPL_ODDS_API_KEY'] }}\n"),
        ("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          ALL: ${{ toJSON(secrets) }}\n"),
        ("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          EPL_ODDS_API_KEY: literal\n"),
        ("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          # EPL_ODDS_API_KEY: ${{ secrets.EPL_ODDS_API_KEY }}\n"),
        (PERMISSIONS_BLOCK, "permissions:\n  contents: write\n"),
        (PERMISSIONS_BLOCK, "permissions:\n  contents: read\n  issues: write\n"),
        (PERMISSIONS_BLOCK, ""),
    ],
)
def test_a_secret_in_the_gate_workflow_is_rejected(tmp_path: Path, mutation: tuple[str, str]) -> None:
    anchor, replacement = mutation
    assert_rejects(check_the_gate_workflow_holds_no_credential, workflow_dir(tmp_path, mutate(anchor, replacement)))


@pytest.mark.parametrize(
    "suite_block",
    [
        "python -m pytest -q || true",
        "python -m pytest -q || :",
        "python -m pytest -q || echo 'tests failed'",
        "python -m pytest -q || { echo failed; exit 0; }",
        "if ! python -m pytest -q; then\n            echo failed\n          fi",
        "set +e\n          python -m pytest -q\n          echo done",
        "set +e; python -m pytest -q; set -e",
        "trap 'exit 0' ERR\n          python -m pytest -q",
        "python -m pytest -q &\n          wait",
        "python -m pytest -q | tee log.txt",
        "python -m pytest -q || /bin/true",
        "(python -m pytest -q) || echo failed",
        "python -m pytest -q > /dev/null 2>&1 || echo 'see log'",
    ],
)
def test_a_swallowed_failure_is_rejected(tmp_path: Path, suite_block: str) -> None:
    """Every one of these exits 0 under `bash -e` with pytest failing —
    observed by running it, which is the only reading that survives the next
    rewording."""
    text = mutate(SUITE_LINE, f"          {suite_block}\n")
    directory = workflow_dir(tmp_path, text)
    assert_rejects(check_no_run_block_in_the_gate_swallows_a_failure, directory)


def test_a_suite_whose_failure_does_not_reach_the_exit_code_is_rejected(tmp_path: Path) -> None:
    for suite_block in (
        "if ! python -m pytest -q; then\n            echo failed\n          fi",
        "set +e\n          python -m pytest -q",
        "python -m pytest -q || true",
    ):
        directory = workflow_dir(tmp_path, mutate(SUITE_LINE, f"          {suite_block}\n"))
        assert_rejects(check_a_failing_suite_fails_the_gate_step, directory)


def test_the_house_failure_path_is_accepted(tmp_path: Path) -> None:
    """`cmd || { echo; exit 1; }` is a failure path, not a swallow."""
    text = mutate(SUITE_LINE, "          python -m pytest -q || { echo '::error::suite failed'; exit 1; }\n")
    check_no_run_block_in_the_gate_swallows_a_failure(workflow_dir(tmp_path, text))
    check_a_failing_suite_fails_the_gate_step(workflow_dir(tmp_path, text))


@pytest.mark.parametrize(
    "compile_block",
    [
        "python -m compileall -q -f src scripts app.py",
        "python -m compileall -q src scripts app.py",
        "for d in src scripts; do\n            [ -d \"$d\" ] || { echo missing; exit 1; }\n          done\n          python -m compileall -q src scripts app.py",
        "for d in src; do\n            [ -d \"$d\" ] || { echo missing; exit 1; }\n          done\n          python -m compileall -q -f src scripts app.py",
        "for d in src scripts; do\n            [ -d \"$d\" ] || echo \"$d missing\"\n          done\n          python -m compileall -q -f src scripts app.py",
    ],
)
def test_a_compile_step_that_tolerates_a_missing_path_is_rejected(tmp_path: Path, compile_block: str) -> None:
    anchor = (
        "          for d in src scripts; do\n"
        '            [ -d "$d" ] || { echo "::error::$d is missing"; exit 1; }\n'
        "          done\n"
        '          [ -f app.py ] || { echo "::error::app.py is missing"; exit 1; }\n'
        + COMPILE_LINE
    )
    directory = workflow_dir(tmp_path, mutate(anchor, f"          {compile_block}\n"))
    assert_rejects(check_the_compile_step_fails_on_a_missing_path, directory)


@pytest.mark.parametrize(
    "spelling",
    [
        "export PYTEST_ADDOPTS=-x",
        "eval \"export PYTEST_$(echo ADDOPTS)=-x\"",
        "printf 'PYTEST_%s=-x\\n' ADDOPTS >> \"$GITHUB_ENV\"",
        "declare -x \"PYTEST_ADD${EMPTY:-}OPTS=-k fast\"",
        "echo 'SOMETHING=1' >> \"$GITHUB_ENV\"",
        "export PYTEST_PLUGINS=dropguards",
        "eval \"export PYTEST_$(echo PLUGINS)=dropguards\"",
    ],
)
def test_a_runtime_assembled_pytest_addopts_is_rejected(tmp_path: Path, spelling: str) -> None:
    """The first spelling carries the token; the rest do not, and only an
    executed rule sees them."""
    text = mutate(SUITE_LINE, f"          {spelling}\n" + SUITE_LINE)
    assert_rejects(check_pytest_addopts_is_empty_when_pytest_runs, workflow_dir(tmp_path, text))


def test_the_harness_reports_the_environment_a_command_ran_with(tmp_path: Path) -> None:
    result = run_block_under_stubs(
        "eval \"export PYTEST_$(echo ADDOPTS)=-x\"\npython -m pytest -q\n", set(), tmp_path
    )

    assert ("python", "-x", "") in result.addopts_seen
    assert result.exit_code == 0


def test_the_guard_manifest_and_its_hook_are_in_place() -> None:
    """Each hard-rule guard vouches for the manifest that vouches for it."""
    for relative in ("tests/test_the_guards_exist.py", "tests/conftest.py"):
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=PROJECT_ROOT, capture_output=True,
        )
        assert result.returncode == 0, f"{relative} is not tracked"
    manifest = (PROJECT_ROOT / "tests" / "test_the_guards_exist.py").read_text(encoding="utf-8")
    assert "tests/test_workflows.py" in manifest
    hook = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in hook
    assert "tests/test_workflows.py" in hook


def test_compileall_really_exits_zero_on_a_missing_path(tmp_path: Path) -> None:
    """The premise of the compile rule, run rather than recalled."""
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(tmp_path / "does-not-exist")],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result
