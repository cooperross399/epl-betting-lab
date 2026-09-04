"""The hard-rule guards are tracked, non-empty, and cannot be run around.

The audit's cheapest attack on every lab was `git rm` of the guard modules:
the suite went green with BETTER metrics, because nothing in the suite knew
which modules were load-bearing. A guard that can be deleted without a red
build is a guard by convention.

Two mechanisms, because either alone is insufficient:

* this module asserts each required guard is tracked by git and still defines
  at least five test functions, read with `ast` rather than imported — an
  import would run the module, and a guard that fails to import is a finding
  here, not a crash;
* `tests/conftest.py` counts what each required module contributed to the
  run and exits the session with status 1 if any contributed nothing. That is
  what catches a rename, `-k`, `-m`, `--deselect`, `--ignore` and
  `PYTEST_ADDOPTS`, none of which touch the file this module reads.

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
