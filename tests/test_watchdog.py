"""Frame budgets / no-progress detection for tool calls (the 26-minute train_party spin)."""
import pytest

from game.watchdog import FrameWatchdog, SkillBudgetExceeded


def run(wd, frames, step=100):
    for _ in range(frames // step):
        wd.advance(step)


def test_hard_cap_trips():
    wd = FrameWatchdog(max_frames=1000, stall_frames=10**9)
    with pytest.raises(SkillBudgetExceeded) as e:
        run(wd, 2000)
    assert not e.value.stalled and "limit" in e.value.reason


def test_unchanging_signature_trips_the_stall_detector():
    wd = FrameWatchdog(max_frames=10**9, stall_frames=3000, probe=lambda: ("same",), check_every=500)
    with pytest.raises(SkillBudgetExceeded) as e:
        run(wd, 10_000)
    assert e.value.stalled and "no progress" in e.value.reason


def test_changing_signature_never_trips():
    n = {"i": 0}

    def probe():
        n["i"] += 1
        return n["i"]
    wd = FrameWatchdog(max_frames=10**9, stall_frames=3000, probe=probe, check_every=500)
    run(wd, 50_000)                                   # keeps making progress → no exception


def test_progress_resets_the_stall_clock():
    sigs = iter(["a"] * 4 + ["b"] + ["b"] * 100)
    wd = FrameWatchdog(max_frames=10**9, stall_frames=2500, probe=lambda: next(sigs), check_every=500)
    with pytest.raises(SkillBudgetExceeded):
        run(wd, 20_000)
    assert wd.frames > 2500 + 500                     # the 'a'→'b' change bought extra time


def test_broken_probe_never_trips_by_itself():
    def boom():
        raise RuntimeError("unreadable")
    wd = FrameWatchdog(max_frames=10**9, stall_frames=1000, probe=boom, check_every=200)
    run(wd, 5000)                                      # no stall verdict from an unreadable probe


def test_trips_once_then_disarms_so_cleanup_can_run():
    wd = FrameWatchdog(max_frames=100, stall_frames=10**9)
    with pytest.raises(SkillBudgetExceeded):
        wd.advance(500)
    wd.advance(10_000)                                # no second raise


def test_skill_code_cannot_swallow_it():
    wd = FrameWatchdog(max_frames=100, stall_frames=10**9)
    with pytest.raises(SkillBudgetExceeded):
        try:
            wd.advance(500)
        except Exception:
            pytest.fail("SkillBudgetExceeded must not be an Exception")


def test_exempt_and_default_budgets():
    from agent.budgets import budget_for
    assert budget_for("press_button") is None and budget_for("wait_frames") is None
    assert budget_for("grind")[0] > budget_for("use_move")[0]
    assert budget_for("some_new_tool") is not None
