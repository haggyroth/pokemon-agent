"""The move-learn driver must not re-decline a LINGERING offer every turn (#… stall).

gMoveToLearn and learnMoveState both linger after a move is declined, so
_delete_box_live() reads a phantom box on every subsequent turn. Before the fix that
made use_move return "declined X" instead of attacking for a whole trainer gauntlet
(the second_badge eval stalled ~83 min on Route 3). The _offer_resolved guard refuses
to re-drive an offer id we've already handled until it actually clears.
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402


class _Lead:
    def __init__(self, level): self.level = level


class _Reader:
    def __init__(self, level=15): self._level = level
    def read_party(self): return [_Lead(self._level)]


def _client(level=15):
    c = AgentClient.__new__(AgentClient)
    c._learn_armed = False
    c._lead_level_seen = None
    c._offer_resolved = 0
    c.reader = _Reader(level)
    c.drives = 0
    # A real box is "live" the whole time (learnMoveState lingers) — the exact trap.
    c._delete_box_live = lambda: True
    def _drive():
        c.drives += 1
        return "declined Sleep Powder"
    c._drive_pending_learn = _drive
    return c


def test_declines_a_new_offer_once_then_stops():
    c = _client()
    c._offered_move = lambda: 79          # Sleep Powder, lingers at this id

    # First turn: a genuine offer → drive it once.
    assert c._maybe_drive_learn() == "declined Sleep Powder"
    assert c.drives == 1

    # Next turns: the SAME offer still lingers (box live), but we must NOT re-drive it —
    # use_move needs to fall through and actually attack.
    for _ in range(10):
        assert c._maybe_drive_learn() is None
    assert c.drives == 1                  # driven exactly once, not eleven times


def test_a_genuinely_new_offer_still_drives():
    c = _client()
    cur = {"v": 79}                       # Sleep Powder, then later a new move
    c._offered_move = lambda: cur["v"]

    cur["v"] = 79
    assert c._maybe_drive_learn() == "declined Sleep Powder"   # drive #1
    assert c._maybe_drive_learn() is None                       # lingering → skip
    cur["v"] = 73                                                # a different move offered
    assert c._maybe_drive_learn() == "declined Sleep Powder"   # drive #2 (new id)
    assert c.drives == 2


def test_cleared_offer_resets_the_guard():
    c = _client()
    cur = {"v": 79}
    c._offered_move = lambda: cur["v"]
    assert c._maybe_drive_learn() == "declined Sleep Powder"
    cur["v"] = 0                          # offer cleared (battle moved on)
    assert c._maybe_drive_learn() is None
    assert c._offer_resolved == 0         # guard reset
    cur["v"] = 79                          # same move offered again in a LATER battle
    assert c._maybe_drive_learn() == "declined Sleep Powder"   # drives again
    assert c.drives == 2
