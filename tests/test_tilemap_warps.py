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


def test_read_connections_parses_edges():
    fc = FakeClient()
    conns = 0x08350000
    arr   = 0x08350100
    fc.set32(Addr.MAP_HEADER + 0x0C, conns)     # gMapHeader +0x0C -> MapConnections
    fc.set32(conns + 0, 2)                        # count
    fc.set32(conns + 4, arr)                      # array ptr
    # MapConnection (12b): direction(u8@0), offset(s32@4), mapGroup(u8@8), mapNum(u8@9)
    fc.set8(arr + 0, 2); fc.set32(arr + 4, 0);  fc.set8(arr + 8, 3);  fc.set8(arr + 9, 19)   # North -> Route 1
    fc.set8(arr + 12, 1); fc.set32(arr + 16, 0); fc.set8(arr + 20, 3); fc.set8(arr + 21, 39)  # South -> Route 21
    got = TilemapReader(fc).read_connections()
    assert got == [
        {"direction": "North", "offset": 0, "map_bank": 3, "map_id": 19},
        {"direction": "South", "offset": 0, "map_bank": 3, "map_id": 39},
    ]


def test_read_connections_empty_on_bad_ptr():
    fc = FakeClient()
    fc.set32(Addr.MAP_HEADER + 0x0C, 0)
    assert TilemapReader(fc).read_connections() == []
