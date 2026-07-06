"""Reward tracker: shaped vs sparse and annealing."""
from agent.reward import RewardTracker


def test_shaped_accumulates():
    r = RewardTracker(shaped=True)
    assert r.reward("new_badge") == 5.0
    assert r.reward("level_up") == 0.5
    assert r.total == 5.5
    assert len(r.history) == 2


def test_unknown_event_is_zero():
    r = RewardTracker(shaped=True)
    assert r.reward("does_not_exist") == 0.0
    assert r.total == 0.0


def test_sparse_zeroes_out_shaping_events():
    r = RewardTracker(shaped=False)
    assert r.reward("level_up") == 0.0      # not in sparse table
    assert r.reward("new_town") == 0.0
    assert r.reward("gym_leader_win") == 10.0


def test_sparse_champion_is_worth_more():
    shaped = RewardTracker(shaped=True)
    sparse = RewardTracker(shaped=False)
    assert sparse.reward("champion_win") == 100.0
    assert shaped.reward("champion_win") == 50.0


def test_anneal_switches_table_midstream():
    r = RewardTracker(shaped=True)
    r.reward("level_up")                     # +0.5 while shaped
    r.anneal_to_sparse()
    assert r.shaped is False
    assert r.reward("level_up") == 0.0       # now ignored
    assert r.total == 0.5
