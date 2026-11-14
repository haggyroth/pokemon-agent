"""Story gates, puzzle-tile data and opened-barrier passability (no emulator)."""
from conftest import FakeClient

from game.constants import Addr
from game.tilemap_reader import TilemapReader
from knowledge.gates import CARD_KEY, MAP_GATES, POKE_FLUTE, SILPH_SCOPE, Req, unmet_gates
from knowledge.puzzle_tiles import PUZZLE_TILES


def _step(dest):
    return ("connection", "North", dest)


def test_unmet_gates_flags_every_gated_entry():
    route = [_step((3, 2)), _step((1, 94, "0")), _step((3, 8))]
    have = {SILPH_SCOPE}                                   # scope yes, surf no
    ok = lambda req: (req.kind == "key_item" and req.value in have)   # noqa: E731
    out = unmet_gates(route, ok)
    assert [(i, r.value) for i, r in out] == [(2, "Surf")]


def test_nothing_unmet_on_an_ungated_route():
    assert unmet_gates([_step((3, 1)), _step((3, 2))], lambda r: False) == []


def test_gate_table_hints_say_where_to_get_it():
    assert all(r.hint for reqs in MAP_GATES.values() for r in reqs)
    assert any(r.value == POKE_FLUTE for reqs in MAP_GATES.values() for r in reqs)


def test_puzzle_tiles_cover_silph_and_mansion():
    kinds = {k for tiles in PUZZLE_TILES.values() for *_xy, k in tiles}
    assert kinds == {"cardkey", "switch"}
    assert (1, 48) in PUZZLE_TILES and (1, 59) in PUZZLE_TILES           # Silph 2F, Mansion 1F
    assert (5, 8, "cardkey") in PUZZLE_TILES[(1, 48)]


def _client(live_rows, rom_rows):
    """Fake map: ROM layout + a padded live EWRAM copy (what the game edits when a barrier opens)."""
    fc = FakeClient()
    layout, rom = 0x08300000, 0x08310000
    h, w = len(rom_rows), len(rom_rows[0])
    fc.set32(Addr.MAP_HEADER, layout)
    fc.set32(layout, w)
    fc.set32(layout + 4, h)
    fc.set32(layout + 0x0C, rom)
    live = 0x02031DFC
    fc.set32(Addr.BACKUP_MAP_LAYOUT, w + 15)
    fc.set32(Addr.BACKUP_MAP_LAYOUT + 4, h + 14)
    fc.set32(Addr.BACKUP_MAP_LAYOUT + 8, live)
    for y in range(h):
        for x in range(w):
            fc.set16(rom + (y * w + x) * 2, rom_rows[y][x])
            fc.set16(live + ((y + 7) * (w + 15) + (x + 7)) * 2, live_rows[y][x])
    return fc


ENTRY = lambda elev, coll, mid=1: (elev << 12) | (coll << 10) | mid   # noqa: E731


def test_opened_barrier_is_walkable_but_plain_void_is_not():
    closed = ENTRY(0, 1, 760)          # barrier: elevation 0, collision 1
    opened = ENTRY(0, 0, 645)          # script-opened: elevation 0, collision 0
    void = ENTRY(0, 0, 473)            # static elevation-0 filler (same in ROM and live)
    floor = ENTRY(3, 0)
    rom = [[floor, closed, void]]
    live = [[floor, opened, void]]
    g, _w, _h = TilemapReader(_client(live, rom)).passable_grid()
    assert g == [[True, True, False]]
    # closed again -> blocked
    g2, _w, _h = TilemapReader(_client(rom, rom)).passable_grid()
    assert g2 == [[True, False, False]]


def test_closed_elev3_barrier_is_a_wall():
    floor, barrier = ENTRY(3, 0), ENTRY(3, 3, 760)
    g, _w, _h = TilemapReader(_client([[floor, barrier]], [[floor, barrier]])).passable_grid()
    assert g == [[True, False]]


def test_req_alt_flag_field():
    r = Req("key_item", CARD_KEY, "hint", alt_flag=0x192)
    assert r.alt_flag == 0x192
