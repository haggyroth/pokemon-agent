"""TilemapReader.read_warps against a fake memory."""
from game.constants import Addr
from game.tilemap_reader import TilemapReader
from conftest import FakeClient


def test_read_warps_parses_warp_events():
    fc = FakeClient()
    events = 0x02036000
    warps  = 0x08370000
    # gMapHeader: +0x04 = mapEvents ptr
    fc.set32(Addr.MAP_HEADER + 0x04, events)
    # MapEvents: +0x01 warpCount, +0x08 warps ptr
    fc.set8(events + 0x01, 3)
    fc.set32(events + 0x08, warps)
    # three WarpEvents (8 bytes each): x(s16), y(s16), elevation, warpId, mapNum, mapGroup
    for i, (x, y) in enumerate([(4, 8), (5, 8), (3, 8)]):
        fc.set16(warps + i * 8 + 0, x)
        fc.set16(warps + i * 8 + 2, y)
    assert TilemapReader(fc).read_warps() == [(4, 8), (5, 8), (3, 8)]


def test_read_warps_returns_empty_on_bad_events_ptr():
    fc = FakeClient()
    fc.set32(Addr.MAP_HEADER + 0x04, 0)  # null/invalid events pointer
    assert TilemapReader(fc).read_warps() == []
