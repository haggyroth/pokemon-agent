"""Unit tests for the parts of heal() that don't need the emulator."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import PokemonStatus, GameContext  # noqa: E402


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


class _CtxReader:
    """detect_context() returns `menu_ctx` for the first `menu_steps` calls (the
    lingering post-heal state), then OVERWORLD."""
    def __init__(self, menu_steps, menu_ctx=GameContext.IN_MENU):
        self.menu_steps = menu_steps
        self.menu_ctx = menu_ctx
        self.calls = 0

    def detect_context(self):
        self.calls += 1
        return self.menu_ctx if self.calls <= self.menu_steps else GameContext.OVERWORLD


class _Mgba:
    def __init__(self):
        self.taps = []

    def tap(self, b):
        self.taps.append(b)

    def tick(self, n=1):
        pass


def _ctrl_client(reader, mgba):
    c = AgentClient.__new__(AgentClient)
    c.reader = reader
    c.mgba = mgba
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


def test_advance_to_control_presses_A_until_overworld():
    # heal() ends by calling this so it returns in real OVERWORLD control (the fix for
    # the Poké Center exit stall). It must keep tapping A through the lingering IN_MENU
    # state and stop the moment control returns.
    r = _CtxReader(menu_steps=6)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=24)
    assert ctx == GameContext.OVERWORLD
    assert mg.taps == ["A"] * 6          # pressed exactly until control returned, no more


def test_advance_to_control_stops_on_battle():
    # If a battle starts while advancing, bail immediately (don't mash A into it).
    r = _CtxReader(menu_steps=2, menu_ctx=GameContext.IN_BATTLE)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=24)
    assert ctx == GameContext.IN_BATTLE
    assert mg.taps == []                 # IN_BATTLE on the first check → no presses


def test_advance_to_control_bounded():
    # Never loops forever if control never returns — capped by `tries`.
    r = _CtxReader(menu_steps=999)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=5)
    assert ctx == GameContext.IN_MENU
    assert len(mg.taps) == 5
