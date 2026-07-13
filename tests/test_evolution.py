"""The agent completes a post-battle evolution scene instead of cancelling it.

A level-up can trigger an evolution scene (its own callback, CB2_EVOLUTION) whose
context flickers between TRANSITIONING and IN_MENU. The agent used to dismiss that
"menu" with B — which CANCELS the evolution — so a levelled-up lead never evolved.
The fix advances the scene with A only, and never presses B.
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.constants import Addr                    # noqa: E402


class _EvoFake:
    """cb2 sits at CB2_EVOLUTION until `frames_until_done` A-presses complete it."""
    def __init__(self, frames_until_done=5):
        self.cb2 = Addr.CB2_EVOLUTION
        self.left = frames_until_done
        self.presses = []

    def read32(self, addr):
        assert addr == Addr.GMAIN_CALLBACK2
        return self.cb2

    def tap(self, button):
        self.presses.append(button)
        if button == "A":
            self.left -= 1
            if self.left <= 0:
                self.cb2 = Addr.CB2_OVERWORLD   # scene finished
        if button == "B":
            self.cb2 = 0xDEAD                    # B would cancel — must never happen

    def tick(self, n=1):
        pass


def _client(fake):
    c = AgentClient.__new__(AgentClient)
    c.mgba = fake
    return c


def test_detects_evolution_scene():
    assert _client(_EvoFake())._in_evolution_scene() is True


def test_not_evolution_when_overworld():
    f = _EvoFake()
    f.cb2 = Addr.CB2_OVERWORLD
    assert _client(f)._in_evolution_scene() is False


def test_finish_evolution_advances_with_A_only():
    f = _EvoFake(frames_until_done=5)
    assert _client(f)._finish_evolution() is True
    assert "B" not in f.presses, "must never press B — it cancels the evolution"
    assert f.presses.count("A") == 5          # advanced exactly until the scene ended
    assert f.cb2 == Addr.CB2_OVERWORLD


def test_finish_evolution_noop_when_not_evolving():
    f = _EvoFake()
    f.cb2 = Addr.CB2_OVERWORLD
    assert _client(f)._finish_evolution() is False
    assert f.presses == []                    # didn't touch the buttons


def test_evolution_callback_is_distinct():
    # Must not collide with the battle/overworld callbacks, or the net would misfire.
    assert Addr.CB2_EVOLUTION not in (Addr.CB2_BATTLE, Addr.CB2_OVERWORLD)
