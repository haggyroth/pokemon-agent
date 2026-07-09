"""walk_to must route AROUND obstacles the tilemap can't see (#59 forest stall).

The ROM passability grid can't see everything that stops a step (solid object
events, ledges, cut trees). When a tap fails to move the player, walk_to marks
that tile blocked and replans around it instead of retrying the identical path.
These tests drive _walk_to against a simulated world (no emulator/LLM).
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext                # noqa: E402

_DELTA = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


class FakeWorld:
    """Doubles as mgba + reader + tilemap. `grid[y][x]` is tilemap-passable;
    `mystery` tiles look passable but silently block the step (the hidden
    obstacle). Taps update the simulated player position."""
    def __init__(self, grid, start, mystery=(), model_turning=False):
        self.grid = grid
        self.h, self.w = len(grid), len(grid[0])
        self.pos = start
        self.mystery = set(mystery)
        self.map = (1, 0)
        self.model_turning = model_turning   # Gen III turn-then-step
        self.facing = "Down"

    # reader interface
    def read_player_pos(self):
        return self.pos

    def read_current_map(self):
        return self.map

    def detect_context(self):
        return GameContext.OVERWORLD

    # tilemap interface
    def refresh(self):
        return True

    def passable_grid(self):
        return [row[:] for row in self.grid], self.w, self.h

    def read_warps(self):
        return []

    # mgba interface
    def tap(self, mv):
        if self.model_turning and mv != self.facing:
            self.facing = mv             # first press only turns
            return
        self.facing = mv
        dx, dy = _DELTA.get(mv, (0, 0))
        nx, ny = self.pos[0] + dx, self.pos[1] + dy
        if (0 <= nx < self.w and 0 <= ny < self.h
                and self.grid[ny][nx] and (nx, ny) not in self.mystery):
            self.pos = (nx, ny)

    def tick(self, *a):
        pass

    def read8(self, *a):     # _npc_tiles: all object-event slots inactive
        return 0

    def read16(self, *a):
        return 0


def _client(world):
    c = AgentClient.__new__(AgentClient)
    c.mgba = world
    c.reader = world
    c.tilemap = world
    return c


def _open(w, h):
    return [[True] * w for _ in range(h)]


def test_walk_to_straight_path_no_obstacle():
    world = FakeWorld(_open(5, 5), start=(0, 0))
    msg = _client(world)._walk_to(4, 4)
    assert world.pos == (4, 4), msg
    assert "Arrived" in msg


def test_walk_to_completes_path_with_turns_no_false_block():
    # With the Gen III turn-then-step rule modelled, an L-shaped path changes
    # direction; walk_to must press twice at each corner and NOT mistake the turn
    # for a blocked tile (the forest/gate stall regression).
    world = FakeWorld(_open(4, 4), start=(0, 0), model_turning=True)
    msg = _client(world)._walk_to(3, 3)
    assert world.pos == (3, 3), msg
    assert "Arrived" in msg


def test_walk_to_routes_around_hidden_obstacle():
    # Open 5x5, but a hidden obstacle sits on the straight-down path at (0,2).
    # walk_to must detour (via column x=1) and still reach the goal.
    world = FakeWorld(_open(5, 5), start=(0, 0), mystery={(0, 2)})
    msg = _client(world)._walk_to(0, 4)
    assert world.pos == (0, 4), msg
    assert "Arrived" in msg


def test_walk_to_gives_up_when_truly_blocked_without_hanging():
    # 1-wide corridor (only x=0 passable) with a hidden obstacle at (0,2) and no
    # detour. walk_to must terminate with a stopped/no-path message, not loop.
    grid = [[x == 0 for x in range(3)] for _ in range(5)]   # only column 0 open
    world = FakeWorld(grid, start=(0, 0), mystery={(0, 2)})
    msg = _client(world)._walk_to(0, 4)
    assert world.pos != (0, 4)
    assert ("Stopped" in msg) or ("No walkable path" in msg)
    assert world.pos[1] <= 2      # got no further than the obstacle
