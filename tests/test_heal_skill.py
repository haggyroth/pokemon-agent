"""Unit tests for the parts of heal() that don't need the emulator."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import PokemonStatus              # noqa: E402


def _mon(cur, mx):
    return PokemonStatus(slot=0, level=10, current_hp=cur, max_hp=mx, status="healthy")


class _Reader:
    def __init__(self, party):
        self._party = party

    def read_party(self):
        return self._party


def _client(party):
    c = AgentClient.__new__(AgentClient)
    c.reader = _Reader(party)
    return c


def test_party_full_hp_true_when_all_full():
    assert _client([_mon(27, 27), _mon(20, 20)])._party_full_hp() is True


def test_party_full_hp_false_when_any_hurt():
    assert _client([_mon(27, 27), _mon(5, 20)])._party_full_hp() is False


def test_party_full_hp_false_when_empty():
    assert _client([])._party_full_hp() is False


def test_heal_noops_when_already_full():
    # Full party → heal() returns immediately without any navigation.
    msg = _client([_mon(27, 27)])._heal()
    assert "already at full HP" in msg


def test_nurse_tile_is_below_the_counter():
    # Regression for the counter geometry: talk from (7,4), not the counter (7,3).
    assert AgentClient._NURSE_TILE == (7, 4)
