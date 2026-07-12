"""overworld_pp_summary: the lead's move-PP readout + low-attacking-PP warning shown
in the overworld obs. Pure logic. This is the fix for the agent running its damaging
moves dry across a trainer gauntlet (it was blind to PP outside battle)."""
from knowledge.battle import overworld_pp_summary


def test_lists_each_move_with_pp():
    line, warn = overworld_pp_summary(
        ["Tackle", "Growl", "Leech Seed", "Vine Whip"], [30, 40, 10, 20])
    assert line == "Lead moves: Tackle PP:30, Growl PP:40, Leech Seed PP:10, Vine Whip PP:20"
    assert warn is None            # plenty of attacking PP (Tackle 30 + Vine Whip 20)


def test_warns_when_attacking_pp_low():
    # Only Tackle + Vine Whip are attacking; Growl/Leech Seed are status and don't count.
    line, warn = overworld_pp_summary(
        ["Tackle", "Growl", "Leech Seed", "Vine Whip"], [2, 40, 10, 1])
    assert "Vine Whip PP:1" in line
    assert warn is not None and "LOW PP" in warn and "3 PP left" in warn


def test_status_only_moveset_warns_at_zero_attacking_pp():
    # A mon with only status moves has 0 attacking PP → always warns.
    line, warn = overworld_pp_summary(["Growl", "Leech Seed"], [40, 10])
    assert warn is not None and "0 PP left" in warn


def test_empty_moveset():
    assert overworld_pp_summary(["", "", "", ""], [0, 0, 0, 0]) == ("", None)


def test_threshold_boundary():
    # atk_pp exactly at the threshold (5) warns; just above (6) does not.
    _, at = overworld_pp_summary(["Tackle"], [5])
    _, above = overworld_pp_summary(["Tackle"], [6])
    assert at is not None and above is None
