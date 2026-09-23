"""Two rules about the scoreboard fetch, both learned from a red deploy.

On 2026-09-23 the first publish carrying `settle_results.py` failed outright.
`site.api.espn.com` answered 403, the exception went unhandled, and the step
died -- so the whole board, which had already been built successfully one line
above, was never deployed. Yesterday's settlement took today's board with it.

Two separate things were wrong and each is pinned here.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"

#: The sport this repository settles. `main` requires it and validates it
#: against the ESPN table, so it cannot be a placeholder.
SPORT = "epl"


def _module():
    spec = importlib.util.spec_from_file_location("settle_results", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_settlement_fetch_sends_no_custom_user_agent() -> None:
    """The polite thing is the thing that breaks it.

    This is the OPPOSITE of the rule the NHL lab pins for api-web.nhle.com,
    which refuses urllib's default and accepts any string. site.api.espn.com
    sits behind a WAF that does the reverse: `Python-urllib/3.x` gets 200, and
    a descriptive agent gets 403 Access Denied -- as does a Chrome string, so
    this is not about looking like a browser. Measured three trials, both
    sports, 2026-09-23.

    Left to a comment this gets "fixed" by the next person adding a courteous
    agent, which is how it shipped in the first place.
    """
    module = _module()
    captured: dict = {}

    class _Resp:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def _urlopen(request: object, timeout: float = 0) -> object:
        captured["agent"] = request.get_header("User-agent")
        return _Resp()

    original, original_load = module.urllib.request.urlopen, module.json.load
    module.urllib.request.urlopen = _urlopen
    module.json.load = lambda handle: {}
    try:
        module.fetch("https://site.api.espn.com/apis/site/v2/sports/x/scoreboard")
    finally:
        module.urllib.request.urlopen = original
        module.json.load = original_load

    agent = str(captured.get("agent") or "")
    assert "maverick" not in agent.lower(), (
        "the settlement fetch sends a descriptive User-Agent again; "
        "site.api.espn.com answers that with 403 Access Denied"
    )
    assert "mozilla" not in agent.lower(), (
        "a browser User-Agent is refused by the same WAF, and is not what this "
        "needs -- urllib's own default is what the host accepts"
    )


def test_a_scoreboard_outage_does_not_take_the_board_down(tmp_path) -> None:
    """The board is built before this runs and must survive it.

    Asserts the exit code, because that is what the workflow step reads, and
    asserts the notice reaches results.json, because a settlement that quietly
    stops looks exactly like a day with no games -- and this page's whole claim
    is that the record is settled from what was published.
    """
    module = _module()
    history = tmp_path / "history"
    history.mkdir()
    (history / "2026-09-22.json").write_text(
        json.dumps({"season": "2026-27", "teams": {}, "games": []}), encoding="utf-8"
    )

    def _boom(url: str):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    module.fetch = _boom
    code = module.main(["--data", str(tmp_path), "--sport", SPORT, "--date", "2026-09-22"])

    assert code == 0, "a scoreboard outage failed the step, and with it the deploy"
    written = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert "could not be settled" in written["notice"]
    assert "403" in written["notice"], "the notice must name what actually happened"

