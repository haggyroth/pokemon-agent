"""_has_control confirms REAL overworld control vs. the quest-log recap (#79).

The recap masquerades as OVERWORLD but ignores the D-pad; real control moves the
player. Driven against a fake that either responds to input or doesn't.
"""
import pytest

pytest.importorskip("openai")

import main  # noqa: E402
from game.state import GameContext  # noqa: E402

_D = {"Down": (0, 1), "Up": (0, -1), "Left": (-1, 0), "Right": (1, 0)}


class Fake:
    """Serves as both mgba and reader, modelling the Gen III turn-vs-step rule:
    a tap in a direction you're not facing only TURNS (no move); a tap in the
    facing direction STEPS if that direction is walkable. `movable` = directions
    that are walkable (empty = recap/no control — the D-pad does nothing)."""
    def __init__(self, ctx, movable, pos=(5, 5), facing="Down"):
        self.ctx = ctx
        self.movable = set(movable)
        self.pos = pos
        self.facing = facing

    def detect_context(self):
        return self.ctx

    def read_player_pos(self):
        return self.pos

    def tap(self, mv):
        if self.ctx != GameContext.OVERWORLD:
            return                              # recap/menu: input does nothing
        if mv != self.facing:
            self.facing = mv                    # first press turns to face mv
            return
        if mv in self.movable:                  # facing it now → step
            dx, dy = _D[mv]
            self.pos = (self.pos[0] + dx, self.pos[1] + dy)

    def tick(self, *a):
        pass


def test_control_confirmed_despite_turn_then_step():
    # Player faces Up; the Down test must press twice (turn, then step) to detect
    # movement — the whole point of the fix.
    f = Fake(GameContext.OVERWORLD, {"Down", "Up", "Left", "Right"}, facing="Up")
    assert main._has_control(f, f) is True
    assert f.pos == (5, 5)                       # restored by the two back presses


def test_no_control_in_recap_ignoring_input():
    f = Fake(GameContext.OVERWORLD, set())       # nothing walkable / D-pad dead
    assert main._has_control(f, f) is False


def test_no_control_when_not_overworld():
    f = Fake(GameContext.IN_MENU, {"Down", "Up", "Left", "Right"})
    assert main._has_control(f, f) is False


def test_control_confirmed_even_if_only_one_axis_open():
    # Walled on three sides but one direction steps → still real control.
    f = Fake(GameContext.OVERWORLD, {"Left"}, facing="Down")
    assert main._has_control(f, f) is True
