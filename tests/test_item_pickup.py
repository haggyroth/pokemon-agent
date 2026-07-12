"""Ground-item pickup: parsing item balls out of gObjectEvents and the facing
helper. Pure logic with a fake memory client (no ROM/LLM) — this is where an
address/offset regression would bite, so it's worth pinning."""
import importlib.util

import pytest

from game.constants import Addr
from game.memory_reader import LeafGreenReader


class _FakeClient:
    """Minimal object-event memory: `objs[slot]` = (active, gfx, gx, gy) or None.
    Encodes the FRLG ObjectEvent layout the reader decodes (active bit0 @+0x00,
    graphicsId @+0x05, currentCoords @+0x10/+0x12 as grid coord + 7)."""
    def __init__(self, objs):
        self.objs = objs

    def _slot(self, addr):
        rel = addr - Addr.OBJECT_EVENTS
        return rel // Addr.OBJECT_EVENT_STRIDE, rel % Addr.OBJECT_EVENT_STRIDE

    def read8(self, addr):
        slot, off = self._slot(addr)
        o = self.objs[slot] if slot < len(self.objs) else None
        if not o:
            return 0
        active, gfx, _gx, _gy = o
        if off == 0x00:
            return 1 if active else 0
        if off == Addr.OBJECT_GFX_OFFSET:
            return gfx
        return 0

    def read16(self, addr):
        slot, off = self._slot(addr)
        _active, _gfx, gx, gy = self.objs[slot]
        if off == 0x10:
            return (gx + Addr.OBJECT_COORD_OFFSET) & 0xFFFF
        if off == 0x12:
            return (gy + Addr.OBJECT_COORD_OFFSET) & 0xFFFF
        return 0


def _reader(objs):
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _FakeClient(objs)
    return r


BALL = Addr.OBJ_GFX_ITEM_BALL   # 92


def test_finds_item_ball_and_reports_grid_coord():
    # slot 0 = player (gfx not a ball), slot 1 = an item ball at grid (12, 9).
    objs = [(True, 1, 5, 5), (True, BALL, 12, 9)]
    assert _reader(objs).read_item_ball_tiles() == [(12, 9)]


def test_ignores_npcs_and_inactive_slots():
    objs = [
        (True, 1, 5, 5),        # player-ish NPC gfx
        (True, 7, 3, 3),        # an NPC
        (False, BALL, 8, 8),    # a collected/inactive ball → not spawned
        (True, BALL, 2, 4),     # a real visible ball
    ]
    assert _reader(objs).read_item_ball_tiles() == [(2, 4)]


def test_no_balls_returns_empty():
    assert _reader([(True, 1, 5, 5), (True, 9, 6, 6)]).read_item_ball_tiles() == []


def test_multiple_balls():
    objs = [(True, 1, 5, 5), (True, BALL, 1, 1), (True, BALL, 20, 14)]
    assert set(_reader(objs).read_item_ball_tiles()) == {(1, 1), (20, 14)}


# ── facing helper (pure) ──────────────────────────────────────────────────────
requires_openai = pytest.mark.skipif(
    importlib.util.find_spec("openai") is None, reason="openai not installed")


@requires_openai
@pytest.mark.parametrize("px,py,tx,ty,expected", [
    (5, 5, 6, 5, "Right"),
    (5, 5, 4, 5, "Left"),
    (5, 5, 5, 6, "Down"),
    (5, 5, 5, 4, "Up"),
    (5, 5, 7, 5, None),     # not adjacent
    (5, 5, 6, 6, None),     # diagonal
])
def test_facing_dir(px, py, tx, ty, expected):
    from agent.lm_studio_client import AgentClient
    assert AgentClient._facing_dir(px, py, tx, ty) == expected
