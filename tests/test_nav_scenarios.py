"""Tier-1 deterministic nav-skill scenarios (ROM-gated; skip without hardware).

These exercise the navigation SKILL directly — no LLM in the loop — so a failure
is unambiguously a pathfinding/routing bug, not a reasoning one. They need the
native binding, the ROM, and the standard battery save, so they SKIP cleanly in
CI (which has none of those) and run locally.

The Route 2 → Pewter case is the reproduction of #59; it's marked xfail so it
documents the open bug and flips to an unexpected-pass the day routing learns to
warp through Viridian Forest instead of walking to the sealed north edge.
"""
import os
import pytest

pytest.importorskip("openai")   # AgentClient/main import openai

# The native binding must be built, or there's no emulator to drive.
pytest.importorskip("game._mgba_native")

import main  # noqa: E402
from evals import scenarios  # noqa: E402
from game.state import GameContext  # noqa: E402

SAVE = scenarios.DEFAULT_SAVE
_HAVE_SAVE = os.path.isfile(SAVE)

# These boot a real emulator and drive it for many seconds, and they're
# non-deterministic (wild encounters), so they must NOT run in the fast default
# suite even when the hardware is present. Opt in explicitly:
#   RUN_NAV_EVALS=1 pytest tests/test_nav_scenarios.py
_OPT_IN = os.getenv("RUN_NAV_EVALS") == "1"

pytestmark = [
    pytest.mark.skipif(not _OPT_IN,
                       reason="set RUN_NAV_EVALS=1 to run the ROM-gated nav skill tests"),
    pytest.mark.skipif(not _HAVE_SAVE, reason=f"standard save not present at {SAVE}"),
]


@pytest.fixture(scope="module")
def runtime():
    rt = main.build_runtime(start_save=SAVE, start_state="", verbose=False,
                            fresh_session=False)
    if rt is None:
        pytest.skip("emulator/ROM not available")
    return rt


def _drive_go_to(rt, destination, tries=6):
    """Call the nav skill repeatedly (resuming past wild battles by fleeing/using
    a move is out of scope here — we just re-issue go_to a few times) and return
    the final (map, message)."""
    msg = ""
    for _ in range(tries):
        msg = rt.client._go_to(destination)
        cur = rt.reader.read_current_map()
        if rt.reader.detect_context() == GameContext.IN_BATTLE:
            # A wild battle interrupted nav; this test doesn't fight — bail out.
            pytest.skip("wild battle interrupted the nav skill (needs battle handling)")
        if "Arrived" in msg:
            return cur, msg
    return rt.reader.read_current_map(), msg


def test_go_to_viridian_from_pallet(runtime):
    # Baseline: Pallet → Viridian City is a straight shot north up Route 1.
    cur, msg = _drive_go_to(runtime, "Viridian City")
    assert cur == (3, 1), f"expected Viridian City (3,1), got {cur} — {msg}"


@pytest.mark.xfail(reason="the no-LLM drive helper can't fight/flee the forest's "
                          "wild battles, so it usually skips; the full LLM eval "
                          "(python -m evals -s reach_pewter) is what confirms Pewter "
                          "is reachable end-to-end (it XPASSed)",
                   strict=False)
def test_go_to_pewter_crosses_viridian_forest(runtime):
    cur, _msg = _drive_go_to(runtime, "Pewter City", tries=10)
    assert cur == (3, 2), "reached Pewter City"
