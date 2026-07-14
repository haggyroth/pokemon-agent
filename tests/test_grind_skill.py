"""Unit tests for grind()'s move-selection logic (no emulator)."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402


def _mon(moves, pp):
    # _best_damaging_move now takes parallel (move_names, pp) lists (the ACTIVE battler's,
    # read from gBattleMons[0]); this shim keeps the tests reading naturally.
    return (list(moves), list(pp))


def test_best_move_picks_highest_power():
    # Bulbasaur: Tackle(35) is the only damaging move vs Growl/Leech Seed (status).
    mon = _mon(["Tackle", "Growl", "Leech Seed", ""], [35, 40, 10, 0])
    assert AgentClient._best_damaging_move(*mon) == "Tackle"


def test_best_move_prefers_stronger_of_two():
    mon = _mon(["Tackle", "Vine Whip", "Razor Leaf", ""], [35, 25, 25, 0])
    assert AgentClient._best_damaging_move(*mon) == "Razor Leaf"   # 55 > 35


def test_best_move_skips_out_of_pp():
    mon = _mon(["Razor Leaf", "Tackle", "", ""], [0, 35, 0, 0])   # Razor Leaf no PP
    assert AgentClient._best_damaging_move(*mon) == "Tackle"


def test_best_move_falls_back_to_any_move_with_pp():
    # Only status moves have PP (all 0 listed power) → return the first with PP.
    mon = _mon(["Growl", "Leech Seed", "", ""], [40, 10, 0, 0])
    assert AgentClient._best_damaging_move(*mon) in ("Growl", "Leech Seed")


def test_best_move_none_when_all_out_of_pp():
    mon = _mon(["Tackle", "Growl", "", ""], [0, 0, 0, 0])
    assert AgentClient._best_damaging_move(*mon) is None
