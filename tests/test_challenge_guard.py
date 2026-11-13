"""challenge_leader warns once when the party is under-levelled for the gym ace."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient  # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402


class _Reader:
    def __init__(self, level):
        self.level = level

    def read_current_map(self):
        return (6, 2)                     # Pewter Gym

    def detect_context(self):
        return GameContext.OVERWORLD

    def read_party(self):
        return [PokemonStatus(slot=0, level=self.level, current_hp=30, max_hp=30,
                              status="healthy")]


def _client(level):
    c = AgentClient.__new__(AgentClient)
    c.reader = _Reader(level)
    c.walked = False
    c._walk_to = lambda *a: setattr(c, "walked", True)
    return c


def test_underleveled_warns_first_then_proceeds():
    c = _client(10)
    out = c._challenge_leader()
    assert "ace is L14" in out and not c.walked
    c.mgba = type("M", (), {"tap": lambda *a: None, "tick": lambda *a: None})()
    c._advance_to_control = lambda: None
    c._challenge_leader()
    assert c.walked                         # second call goes ahead


def test_strong_enough_does_not_warn():
    c = _client(13)
    c.mgba = type("M", (), {"tap": lambda *a: None, "tick": lambda *a: None})()
    c._advance_to_control = lambda: None
    c._challenge_leader()
    assert c.walked
