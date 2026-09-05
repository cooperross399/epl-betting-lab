"""The hard-rule guards are tracked, non-empty, and cannot be run around.

The audit's cheapest attack on every lab was `git rm` of the guard modules:
the suite went green with BETTER metrics, because nothing in the suite knew
which modules were load-bearing. A guard that can be deleted without a red
build is a guard by convention.

Four mechanisms, because no one of them is sufficient:

* this module asserts each required guard is tracked by git and still defines
  at least five test functions, read with `ast` rather than imported — an
  import would run the module, and a guard that fails to import is a finding
  here, not a crash;
* `tests/conftest.py` compares what each required module contributed to the
  run against the `def test_*` in its file, and exits the session with status
  1 on any shortfall. Per TEST, not per module: `--deselect` of exactly one
  guard test left the first version of that hook green. It also ends a run
  that skipped anything, at collection or at runtime, and a run pytest parsed
  a narrowing option into. None of those touch the file this module reads;
* this module refuses the tracked names that would be imported in place of
  the test runner — `pytest.py`, `coverage.py`, `sitecustomize.py`,
  `usercustomize.py`, and the package directories — on the repository root
  and on every PYTHONPATH entry `tests.yml` declares;
* `scripts/refuse_shadow_modules.py` makes that last assertion again as its
  own workflow step, BEFORE the suite. It has to: a tracked `pytest.py` is
  what stops the suite from starting, and a suite that did not start reports
  nothing. Measured on this branch, with `shadow/pytest.py` tracked and
  `PYTHONPATH: shadow:src`, `python -m pytest -q` exited 0 having collected
  nothing with `PYTHONSAFEPATH=1` set, because that variable drops the
  working directory and not PYTHONPATH.

What none of them covers is written down and executed in
`test_the_gaps_these_guards_still_have_are_the_ones_written_down`.

This module names itself in the list. Deleting it is the first thing an
attacker would try, and the conftest hook is what refuses that: with this
module gone, its path contributes zero items and the session ends red.

No test count is written here, and no wall-clock figure — both move every
time a guard gains a case, and a stale absolute is worse than no number.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = PROJECT_ROOT / "tests" / "conftest.py"

#: The guards. Keep in step with REQUIRED_GUARD_MODULES in tests/conftest.py;
#: `test_the_conftest_manifest_and_this_one_agree` fails the build if not.
REQUIRED_GUARDS: tuple[str, ...] = (
    # No credential in a tracked file, in any spelling or location.
    "tests/test_no_secrets_committed.py",
    # No import of, and no importable, sibling lab.
    "tests/test_no_sibling_lab_import.py",
    # The required status check cannot be renamed, emptied, narrowed,
    # disabled or made to swallow a failure.
    "tests/test_workflows.py",
    # This file.
    "tests/test_the_guards_exist.py",
)

#: Below this many test functions a guard module has been hollowed out, even
#: if the file is still there.
MINIMUM_TESTS_PER_GUARD = 5


def _tracked(relative: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def _test_function_count(path: Path) -> int:
    """Top-level `def test_*` plus `test_*` methods on `Test*` classes.

    A `SyntaxError` is raised, not swallowed: an unparseable guard is a guard
    that contributes nothing, and the failure must name the file.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"{path.name} does not parse: {exc}") from exc
    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                count += 1
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        count += 1
    return count


def _conftest_manifest() -> tuple[str, ...]:
    """REQUIRED_GUARD_MODULES as written in tests/conftest.py, via ast."""
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"), filename=str(CONFTEST))
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "REQUIRED_GUARD_MODULES":
                value = ast.literal_eval(node.value)
                assert isinstance(value, tuple), "the conftest manifest must be a tuple"
                return value
    raise AssertionError("tests/conftest.py no longer defines REQUIRED_GUARD_MODULES")


@pytest.mark.parametrize("guard", REQUIRED_GUARDS)
def test_every_required_guard_is_tracked_by_git(guard: str) -> None:
    assert _tracked(guard), (
        f"{guard} is not tracked by git. Deleting or renaming a hard-rule "
        "guard is not a smaller green suite; it is a red one."
    )


@pytest.mark.parametrize("guard", REQUIRED_GUARDS)
def test_every_required_guard_still_defines_tests(guard: str) -> None:
    path = PROJECT_ROOT / guard
    assert path.is_file(), f"{guard} is missing from the working tree"

    count = _test_function_count(path)

    assert count >= MINIMUM_TESTS_PER_GUARD, (
        f"{guard} defines {count} test function(s); a guard hollowed out "
        f"below {MINIMUM_TESTS_PER_GUARD} is a guard in name only."
    )


def test_this_module_is_in_its_own_manifest() -> None:
    assert "tests/test_the_guards_exist.py" in REQUIRED_GUARDS


def test_the_conftest_manifest_and_this_one_agree() -> None:
    """Two lists that can drift apart are one list plus a hole."""
    assert _tracked("tests/conftest.py")
    assert _conftest_manifest() == REQUIRED_GUARDS


def _calls_in(function: ast.FunctionDef, tree: ast.Module, depth: int = 0) -> list[ast.Call]:
    """Every call in `function`, following calls to module-level helpers."""
    found: list[ast.Call] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        found.append(node)
        if isinstance(node.func, ast.Name) and depth < 3:
            for other in tree.body:
                if isinstance(other, ast.FunctionDef) and other.name == node.func.id:
                    found.extend(_calls_in(other, tree, depth + 1))
    return found


@pytest.mark.parametrize("hook", ["pytest_collection_modifyitems", "pytest_collection_finish"])
def test_the_conftest_hooks_are_the_ones_that_end_the_session(hook: str) -> None:
    """Both hooks must reach `pytest.exit` with a non-zero status, read from
    the source: a hook rewritten to `warnings.warn` would still be a hook.
    `pytest_collection_finish` is the one that sees the list the run loop
    will execute, after every plugin's deselection."""
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"), filename=str(CONFTEST))
    hooks = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == hook
    ]
    assert len(hooks) == 1, f"tests/conftest.py must define {hook} once"

    exits = [
        node for node in _calls_in(hooks[0], tree)
        if isinstance(node.func, ast.Attribute)
        and node.func.attr == "exit"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    ]
    assert exits, f"{hook} no longer reaches pytest.exit"
    statuses = [
        keyword.value.value
        for call in exits
        for keyword in call.keywords
        if keyword.arg == "returncode" and isinstance(keyword.value, ast.Constant)
    ]
    assert statuses and all(isinstance(s, int) and s != 0 for s in statuses), (
        "pytest.exit must carry a non-zero returncode; exit status 0 is a pass"
    )


def test_the_skip_hooks_are_the_ones_that_end_the_session() -> None:
    """A hook rewritten to `warnings.warn` would still be a hook, so both skip
    hooks are read out of the source: `pytest_collectreport` (the one that
    sees a module that skipped itself) and `pytest_runtest_logreport` must
    each record into the same list, and `pytest_sessionfinish` must assign a
    non-zero `session.exitstatus` — that is the value `wrap_session` returns
    after the hook, and so the process exit code."""
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"), filename=str(CONFTEST))
    defined = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for hook in ("pytest_collectreport", "pytest_runtest_logreport", "pytest_sessionfinish"):
        assert hook in defined, f"tests/conftest.py no longer defines {hook}"

    for hook in ("pytest_collectreport", "pytest_runtest_logreport"):
        appends = [
            node for node in ast.walk(defined[hook])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
        ]
        assert appends, f"{hook} records nothing"

    assignments = [
        node for node in ast.walk(defined["pytest_sessionfinish"])
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "exitstatus"
            for target in node.targets
        )
    ]
    assert assignments, "pytest_sessionfinish no longer sets session.exitstatus"
    statuses = [
        node.value.value for node in assignments
        if isinstance(node.value, ast.Constant)
    ]
    assert statuses and all(isinstance(s, int) and s != 0 for s in statuses), (
        f"pytest_sessionfinish must set a non-zero exit status; got {statuses}"
    )


def test_the_only_conftest_is_the_one_that_counts(pytestconfig: pytest.Config) -> None:
    """A second conftest, or an ini `addopts`, is a second place a run can be
    narrowed or a guard deselected from. Nothing here needs either."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").split("\0")
    conftests = sorted(name for name in tracked if Path(name).name == "conftest.py")

    assert conftests == ["tests/conftest.py"], conftests
    assert not pytestconfig.getini("addopts"), pytestconfig.getini("addopts")


def test_no_pytest_plugin_is_registered_from_inside_the_repository() -> None:
    """A plugin loaded into the session can deselect a guard after it was
    counted, or report it passed without running it — `pytest_runtest_
    protocol` can write any outcome it likes, and that was run rather than
    supposed. The workflow linter refuses `-p <plugin>`, `PYTEST_PLUGINS`
    and a second conftest; this refuses the routes that need no command line
    at all: a `pytest11` entry point in pyproject.toml, which `pip install
    -e .` in CI would auto-load, a `pytest_plugins` declaration in the one
    conftest, and an ini file this repository does not otherwise have. A
    plugin installed from requirements.txt is the route that remains, and it
    is a reviewed line in a reviewed file."""
    import tomllib

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entry_points = pyproject.get("project", {}).get("entry-points", {})
    assert "pytest11" not in entry_points, entry_points["pytest11"]
    assert "pytest" not in pyproject.get("tool", {}), (
        "a [tool.pytest] section is a second place to narrow the run from; "
        "if one is ever needed, teach this test what it may contain"
    )

    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"), filename=str(CONFTEST))
    declared = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "pytest_plugins"
    ]
    assert not declared, "tests/conftest.py declares pytest_plugins"

    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").split("\0")
    ini_files = sorted(
        name for name in tracked if Path(name).name in {"pytest.ini", "tox.ini", "setup.cfg"}
    )
    assert ini_files == [], ini_files


def _run_pytest(*arguments: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"
    }
    environment["PYTHONPATH"] = "src"
    environment.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--collect-only", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )


#: Two guard modules named on the command line, so the subprocess collects
#: only them and stays fast. Both are inside the selection, so both are
#: enforced, exactly as every module is when CI runs with no positional.
_TWO_GUARDS = ("tests/test_no_secrets_committed.py", "tests/test_the_guards_exist.py")


def test_a_deselected_guard_ends_the_session_red() -> None:
    """Observed, not reasoned about: `--deselect` of a whole guard module."""
    result = _run_pytest(*_TWO_GUARDS, "--deselect", "tests/test_no_secrets_committed.py")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_no_secrets_committed.py" in result.stdout
    assert "contributed no test" in result.stdout


def test_a_keyword_that_matches_nothing_in_a_guard_ends_the_session_red() -> None:
    result = _run_pytest(*_TWO_GUARDS, "-k", "the_guards_exist")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_no_secrets_committed.py" in result.stdout


def test_pytest_addopts_cannot_carry_the_narrowing_in() -> None:
    """The variable is enforced whatever it holds — it is where a narrowing
    hides from a reader of the workflow file."""
    result = _run_pytest(*_TWO_GUARDS, env_extra={"PYTEST_ADDOPTS": "-k the_guards_exist"})

    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_no_secrets_committed.py" in result.stdout


def test_the_positive_control_collects_both_guards_and_exits_clean() -> None:
    """Without this, the red runs above could be red for a YAML typo."""
    result = _run_pytest(*_TWO_GUARDS)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "contributed no test" not in result.stdout


def test_a_developer_running_one_unrelated_module_is_left_alone() -> None:
    """The one exemption, stated so it cannot be widened by accident: a
    positional selection on the command line that contains no guard module
    enforces no guard module. In CI there is no positional — the workflow
    linter refuses one — so this exemption never applies there."""
    result = _run_pytest("tests/test_value.py")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "contributed no test" not in result.stdout


# --------------------------------------------------------------------------
# The suite that runs is the suite that was installed.
#
# `python -m pytest` puts the working directory ahead of site-packages, and
# the workflow adds `src` to PYTHONPATH ahead of it too. So a tracked file
# with the right name never has to touch the workflow to replace the suite:
# measured on 8a50474, a two-line `pytest.py` in the repository root made
# `python -m pytest -q` print one line and exit 0 with every guard green.
# `sitecustomize.py` is worse: the interpreter imports it before pytest
# starts, so it can set PYTEST_ADDOPTS from inside the tree.
#
# Two mechanisms again: this refuses the tracked NAMES, and the workflow
# linter requires PYTHONSAFEPATH on every pytest step, which drops the
# working directory whatever the file is called.
# --------------------------------------------------------------------------

#: Names Python would import in preference to the installed package.
SHADOWING_BASENAMES = frozenset(
    {"pytest.py", "coverage.py", "sitecustomize.py", "usercustomize.py"}
)

#: Directory names that shadow the same imports as a package rather than a
#: module.
SHADOWING_DIRECTORY_NAMES = frozenset({"pytest", "_pytest", "coverage"})

WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"
GATE_WORKFLOW = WORKFLOWS_DIR / "tests.yml"


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def _declared_pythonpath_entries() -> list[str]:
    """Every `PYTHONPATH` the gate workflow binds, split on `:`.

    Read with yaml.safe_load from every mapping in the file, because the
    variable can be bound at workflow, job or step level and all three reach
    the suite step the same way.
    """
    import yaml

    document = yaml.safe_load(GATE_WORKFLOW.read_text(encoding="utf-8"))
    entries: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            environment = node.get("env")
            if isinstance(environment, dict):
                for key, value in environment.items():
                    if str(key).strip().upper() == "PYTHONPATH":
                        entries.extend(
                            part for part in str(value).split(":") if part.strip()
                        )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    # De-duplicated, order preserved: the same entry declared by two steps is
    # one import root, and the rules below are about roots.
    return list(dict.fromkeys(entries))


def test_no_tracked_file_can_shadow_pytest_or_run_before_it() -> None:
    """`git ls-files`, not the working tree: an untracked scratch file on a
    laptop is nobody's business, and a tracked one is in CI's checkout."""
    tracked = _tracked_files()
    assert tracked, "git ls-files returned nothing; a guard with no corpus is green"

    offenders = sorted(
        name for name in tracked if Path(name).name in SHADOWING_BASENAMES
    )

    assert not offenders, (
        f"tracked file(s) that Python would import in place of the real "
        f"module: {offenders}. `python -m pytest` searches the working "
        "directory first, and sitecustomize.py runs before the interpreter "
        "reaches pytest at all."
    )


def test_no_tracked_package_shadows_pytest_on_a_path_the_workflow_declares() -> None:
    """A directory shadows the same import a module does.

    The roots checked are the repository root — the working directory of
    every run block — and every entry the gate workflow puts on PYTHONPATH,
    read from tests.yml rather than assumed to be `src`.
    """
    tracked = _tracked_files()
    assert tracked, "git ls-files returned nothing"
    roots = [""] + [entry.strip("/") for entry in _declared_pythonpath_entries()]
    assert roots, "no root to check"

    offenders: list[str] = []
    for name in tracked:
        parts = Path(name).parts
        for root in roots:
            prefix = tuple(part for part in root.split("/") if part)
            if parts[: len(prefix)] != prefix:
                continue
            remainder = parts[len(prefix):]
            if len(remainder) >= 2 and remainder[0] in SHADOWING_DIRECTORY_NAMES:
                offenders.append(name)

    assert not offenders, (
        f"tracked file(s) inside a package that shadows pytest or coverage on "
        f"a path the workflow declares ({roots}): {sorted(set(offenders))}"
    )


def test_the_gate_workflow_declares_a_pythonpath_this_guard_could_read() -> None:
    """Absence is never a pass: if the parse stops finding PYTHONPATH, the
    rule above is checking the repository root only and saying nothing about
    it. This is the assertion that turns that silence red."""
    entries = _declared_pythonpath_entries()

    assert entries == ["src"], entries


# --------------------------------------------------------------------------
# The conftest's own behaviour, observed in a synthetic tree.
#
# A synthetic tree rather than the real one, because these need a guard
# module to be mutilated and the real guards cannot be. The tree holds a
# copy of tests/conftest.py and a stub at each required guard path, so the
# hook enforces exactly what it enforces in this repository.
# --------------------------------------------------------------------------

STUB_GUARD = '''\
def test_first() -> None:
    assert True


def test_second() -> None:
    assert True
'''


def _synthetic_tree(root: Path) -> Path:
    """A minimal repository the real conftest can run in."""
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(
        CONFTEST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    for module in REQUIRED_GUARDS:
        (root / module).write_text(STUB_GUARD, encoding="utf-8")
    return root


def _run_in(tree: Path, *arguments: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"
    }
    environment.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arguments],
        cwd=tree, env=environment, capture_output=True, text=True, timeout=300,
    )


def test_the_synthetic_tree_is_green_before_it_is_mutilated(tmp_path: Path) -> None:
    """The positive control. Without it every red below could be red for a
    reason that has nothing to do with the mutation."""
    result = _run_in(_synthetic_tree(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "8 passed" in result.stdout, result.stdout


@pytest.mark.parametrize(
    "shape",
    [
        'import pytest\npytest.skip("no data on this runner", allow_module_level=True)\n',
        'import pytest\npytest.importorskip("a_dependency_that_is_not_installed")\n',
    ],
)
def test_a_collection_phase_skip_ends_the_session_red(tmp_path: Path, shape: str) -> None:
    """`pytest_runtest_logreport` never sees these: a module that skips itself
    is resolved during COLLECTION and arrives as a CollectReport. That is what
    made a permanent skip on absent data invisible — measured on 8a50474,
    either shape on a real test module gave `180 passed, 1 skipped` and exit
    0."""
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(
        shape + "\n\ndef test_something() -> None:\n    assert True\n", encoding="utf-8"
    )

    result = _run_in(tree)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 skipped" in result.stdout, result.stdout
    assert "A skip is not a pass" in result.stdout, result.stdout


def test_a_runtime_skip_ends_the_session_red(tmp_path: Path) -> None:
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(
        "import pytest\n\n\ndef test_waits_for_data() -> None:\n"
        '    pytest.skip("the dataset is gitignored")\n',
        encoding="utf-8",
    )

    result = _run_in(tree)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "A skip is not a pass" in result.stdout, result.stdout


def test_a_skipif_marker_that_is_true_ends_the_session_red(tmp_path: Path) -> None:
    """A marker is the third shape, and it is the one that reads as harmless
    in review."""
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(
        "import pytest\n\n\n@pytest.mark.skipif(True, reason='no data')\n"
        "def test_waits_for_data() -> None:\n    assert True\n",
        encoding="utf-8",
    )

    result = _run_in(tree)

    assert result.returncode == 1, result.stdout + result.stderr


def test_deselecting_one_test_from_a_guard_ends_the_session_red(tmp_path: Path) -> None:
    """The floor is per TEST. A module floor let this through: the module
    still contributed an item, so it was still counted as present."""
    tree = _synthetic_tree(tmp_path)

    result = _run_in(
        tree, "--deselect", "tests/test_workflows.py::test_second"
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "did not reach this run" in result.stdout, result.stdout
    assert "test_second" in result.stdout, result.stdout


def test_pytest_addopts_deselecting_one_guard_test_ends_the_session_red(tmp_path: Path) -> None:
    """The same edit with no command line to read."""
    tree = _synthetic_tree(tmp_path)

    result = _run_in(
        tree, env_extra={"PYTEST_ADDOPTS": "--deselect tests/test_workflows.py::test_second"}
    )

    assert result.returncode == 1, result.stdout + result.stderr


def test_an_ini_addopts_that_narrows_ends_the_session_red(tmp_path: Path) -> None:
    """`-c other.ini` and an `addopts` line are the routes with no flag on the
    command line. The conftest reads `getini`, which is what pytest actually
    resolved."""
    tree = _synthetic_tree(tmp_path)
    (tree / "pytest.ini").write_text(
        "[pytest]\naddopts = --deselect tests/test_workflows.py::test_second\n",
        encoding="utf-8",
    )

    result = _run_in(tree)

    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize(
    "narrowing",
    [("-k", "test_first"), ("-m", "not slow"), ("--ignore", "tests/test_ordinary.py")],
)
def test_a_narrowing_option_is_read_from_the_parsed_config(
    tmp_path: Path, narrowing: tuple[str, str]
) -> None:
    """Observed, not grepped: what pytest PARSED, whichever way it arrived.
    `--ignore` of an unrelated module leaves every guard test collected and is
    still refused, because the next `--ignore` names a guard."""
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(STUB_GUARD, encoding="utf-8")

    result = _run_in(tree, *narrowing)

    assert result.returncode == 1, result.stdout + result.stderr


def test_a_developer_selecting_one_unrelated_module_may_still_narrow_it(tmp_path: Path) -> None:
    """The exemption, stated so it cannot be widened by accident and so its
    width is not guessed at: a positional selection holding no guard module
    enforces no guard module, and the narrowing check is silent there too.
    In CI there is no positional — the workflow linter refuses one."""
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(STUB_GUARD, encoding="utf-8")

    result = _run_in(tree, "tests/test_ordinary.py", "-k", "test_first")

    assert result.returncode == 0, result.stdout + result.stderr


def test_an_option_value_that_names_a_file_is_not_a_developer_selection(tmp_path: Path) -> None:
    """The exemption is for a POSITIONAL argument, and it is read from the
    positional destination pytest parsed.

    Reading it by walking the raw argv and keeping every word that names an
    existing file made the exemption reachable by anyone: measured on
    8a50474, `pytest --collect-only --ignore tests/test_books.py -k "not
    no_secrets_committed"` exited 0 with none of the secrets guard's tests
    collected, because `--ignore`'s value was mistaken for the selection.
    """
    tree = _synthetic_tree(tmp_path)
    (tree / "tests" / "test_ordinary.py").write_text(STUB_GUARD, encoding="utf-8")

    result = _run_in(
        tree, "--ignore", "tests/test_ordinary.py", "-k", "not test_workflows"
    )

    assert result.returncode == 1, result.stdout + result.stderr


# --------------------------------------------------------------------------
# The step that makes the same assertion in time to matter.
# --------------------------------------------------------------------------

SHADOW_SCRIPT = PROJECT_ROOT / "scripts" / "refuse_shadow_modules.py"


def _gate_document() -> dict:
    import yaml

    return yaml.safe_load(GATE_WORKFLOW.read_text(encoding="utf-8"))


def _gate_steps() -> list[dict]:
    document = _gate_document()
    steps: list[dict] = []
    for job in (document.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                steps.append(step)
    return steps


def test_the_workflow_refuses_a_shadow_before_it_runs_the_suite() -> None:
    """The assertions above cannot run when the shadow is doing its job: a
    tracked pytest.py is what stops the suite from starting, and a suite that
    did not start reports nothing. Measured on this branch, with a tracked
    `shadow/pytest.py` and `PYTHONPATH: shadow:src`: `python -m pytest -q`
    exited 0 having collected nothing, PYTHONSAFEPATH=1 included, because
    PYTHONSAFEPATH drops the working directory and not PYTHONPATH. So the
    check also runs as its own step, before the suite, in the workflow.
    """
    assert _tracked("scripts/refuse_shadow_modules.py")
    steps = _gate_steps()
    running = [
        index for index, step in enumerate(steps)
        if isinstance(step.get("run"), str)
        and "refuse_shadow_modules.py" in step["run"]
    ]
    assert len(running) == 1, (
        "exactly one step in tests.yml must run scripts/refuse_shadow_modules.py"
    )
    suite = [
        index for index, step in enumerate(steps)
        if isinstance(step.get("run"), str) and "pytest" in step["run"]
    ]
    assert suite, "no step in tests.yml runs pytest"
    assert running[0] < min(suite), (
        "the shadow check runs after the suite it protects, which is after the "
        "shadow has already replaced the suite"
    )


def test_the_shadow_check_and_the_suite_see_the_same_import_roots() -> None:
    """Two PYTHONPATH declarations that can drift apart are one declaration
    plus a hole: the check would be looking at roots the suite does not use,
    or missing one it does."""
    steps = _gate_steps()
    checking = [
        step for step in steps
        if isinstance(step.get("run"), str)
        and "refuse_shadow_modules.py" in step["run"]
    ]
    suite = [
        step for step in steps
        if isinstance(step.get("run"), str) and "pytest" in step["run"]
    ]
    assert checking and suite

    def pythonpath(step: dict) -> object:
        environment = step.get("env")
        return environment.get("PYTHONPATH") if isinstance(environment, dict) else None

    assert pythonpath(checking[0]) == pythonpath(suite[0]) == "src"


def test_the_shadow_check_refuses_each_shadowing_shape(tmp_path: Path) -> None:
    """The script, run against a synthetic git repository, one shape at a
    time. Red for each; green for the same tree without it."""
    import subprocess as sp

    def build(extra: str | None) -> Path:
        tree = tmp_path / (extra or "clean").replace("/", "_")
        (tree / "src" / "epl_betting_lab").mkdir(parents=True)
        (tree / "src" / "epl_betting_lab" / "__init__.py").write_text("", encoding="utf-8")
        if extra:
            target = tree / extra
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# shadow\n", encoding="utf-8")
        sp.run(["git", "init", "-q"], cwd=tree, check=True)
        sp.run(["git", "add", "-A"], cwd=tree, check=True)
        return tree

    def verdict(tree: Path) -> sp.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = "src"
        return sp.run(
            [sys.executable, str(SHADOW_SCRIPT)],
            cwd=tree, env=environment, capture_output=True, text=True, timeout=60,
        )

    clean = verdict(build(None))
    assert clean.returncode == 0, clean.stdout + clean.stderr

    for shape in (
        "pytest.py",
        "coverage.py",
        "sitecustomize.py",
        "usercustomize.py",
        "src/pytest.py",
        "src/sitecustomize.py",
        "pytest/__init__.py",
        "src/coverage/__init__.py",
        "src/_pytest/__init__.py",
    ):
        result = verdict(build(shape))
        assert result.returncode == 1, f"{shape} was not refused: {result.stdout}"
        assert shape in result.stdout, result.stdout


def test_the_shadow_check_fails_closed_on_an_empty_corpus(tmp_path: Path) -> None:
    """`git ls-files` returning nothing must be red, not a clean bill."""
    import subprocess as sp

    tree = tmp_path / "empty"
    tree.mkdir()
    sp.run(["git", "init", "-q"], cwd=tree, check=True)

    result = sp.run(
        [sys.executable, str(SHADOW_SCRIPT)],
        cwd=tree, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "no file" in result.stdout, result.stdout


# --------------------------------------------------------------------------
# What still gets through, asserted rather than remembered.
# --------------------------------------------------------------------------


def test_the_gaps_these_guards_still_have_are_the_ones_written_down(
    tmp_path: Path,
) -> None:
    """Each route below was written, run against this branch, and observed to
    pass. They are recorded rather than quietly left open.

    **This asserts nothing is allowed.** Every gate above still demands its
    empty list. This is a ledger of coverage: the correct response to any line
    is to close it and delete the line, and a failure here means someone
    closed one.

    Executed below, so the ledger cannot rot:

    * `collect_ignore` in tests/conftest.py drops whole modules with no skip
      report, no deselection and no narrowing option for the conftest to read.
      Measured in a clone of this branch: 2062 collected became 2050, exit 0.
      What stops it is that tests/conftest.py is one tracked, reviewed file
      that four guards assert the contents of.
    * A guard test whose BODY is replaced by `pass` still contributes an item
      under its own name, so the per-test floor counts it. The floor knows
      that a test ran, not that it asserted anything.
    * `--collect-only` collects everything and executes nothing, and exits 0.
      The workflow whitelist refuses it on the suite line, so this is a gap on
      a laptop and not in CI.

    Not executed here, and stated instead, with why:

    * A commit that deletes all four guard modules AND tests/conftest.py in
      one change is green: each guard vouches for the manifest and the
      manifest for each guard, but nothing outside the suite vouches for the
      suite. Branch protection and a reviewer are that backstop.
    * A pytest plugin added to requirements.txt is loaded before the guards
      are counted and can report any outcome it likes from
      `pytest_runtest_protocol`. It is a reviewed line in a reviewed file.
    * Branch protection itself is a repository setting. Nothing here reads
      it; `REQUIRED_CHECK` is a value verified against the settings by hand on
      2026-09-04, and a change there is invisible to every test in this repo.
    * `concurrency: cancel-in-progress: true` on the gate workflow is not
      refused. It was tried: a cancelled check is not reported as a passing
      one, so it makes the check noisy rather than falsely green.
    * PYTHONSAFEPATH drops the working directory and NOT the PYTHONPATH
      entries. The shadow rules know four basenames and three directory
      names; a tracked module under any other importable name on a declared
      root would still be imported ahead of the installed distribution.
    """
    # Sibling directories, never nested: a tree inside another tree is
    # collected by it, and the verdict would be about both.
    plain = _synthetic_tree(tmp_path / "plain")
    (plain / "tests" / "test_ordinary.py").write_text(STUB_GUARD, encoding="utf-8")

    still_open: dict[str, subprocess.CompletedProcess[str]] = {}

    ignored = _synthetic_tree(tmp_path / "ignored")
    (ignored / "tests" / "test_ordinary.py").write_text(STUB_GUARD, encoding="utf-8")
    with (ignored / "tests" / "conftest.py").open("a", encoding="utf-8") as handle:
        handle.write('\n\ncollect_ignore = ["test_ordinary.py"]\n')
    still_open["collect_ignore drops a module"] = _run_in(ignored)

    emptied = _synthetic_tree(tmp_path / "emptied")
    (emptied / "tests" / "test_workflows.py").write_text(
        "def test_first() -> None:\n    pass\n\n\ndef test_second() -> None:\n    pass\n",
        encoding="utf-8",
    )
    still_open["a guard test emptied to pass"] = _run_in(emptied)

    still_open["--collect-only runs nothing"] = _run_in(plain, "--collect-only")

    unclosed = {
        name: result.returncode for name, result in still_open.items()
    }

    assert unclosed == {
        "collect_ignore drops a module": 0,
        "a guard test emptied to pass": 0,
        "--collect-only runs nothing": 0,
    }, (
        "a route recorded as still open no longer is. That is good news: "
        f"close it properly and delete its line here. {unclosed}"
    )
