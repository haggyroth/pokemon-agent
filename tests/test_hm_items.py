"""Field item use, HM drivers and surf-aware tiles — the pure/fake-memory parts."""
import pytest
from conftest import FakeClient

from game.constants import Addr
from game.state import PokemonStatus
from game.tilemap_reader import TilemapReader
from knowledge.map_regions import CONN_RANGES

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def _grid_client(rows):
    fc = FakeClient()
    layout, mp = 0x08300000, 0x08310000
    fc.set32(Addr.MAP_HEADER, layout)
    h, w = len(rows), len(rows[0])
    fc.set32(layout, w)
    fc.set32(layout + 4, h)
    fc.set32(layout + 0x0C, mp)
    for y, row in enumerate(rows):
        for x, elev in enumerate(row):
            fc.set16(mp + (y * w + x) * 2, elev << 12)
    return fc


def test_passable_grid_water_only_when_surfing():
    t = TilemapReader(_grid_client([[3, 1, 3], [0, 1, 3]]))
    g, w, h = t.passable_grid()
    assert g == [[True, False, True], [False, False, True]]
    gs, _w, _h = t.passable_grid(surf=True)
    assert gs == [[True, True, True], [False, True, True]]          # walls stay walls


def _mon(slot, hp, mx, status="healthy", moves=()):
    return PokemonStatus(slot=slot, level=5, current_hp=hp, max_hp=mx, status=status,
                         species_name=f"MON{slot}", move_ids=list(moves))


def _client(party):
    c = AgentClient.__new__(AgentClient)

    class R:
        def read_party(self):
            return party
    c.reader = R()
    return c


def test_field_item_auto_target_picks_who_needs_it():
    party = [_mon(0, 30, 30), _mon(1, 5, 20), _mon(2, 10, 20, "poisoned"), _mon(3, 0, 20)]
    c = _client(party)
    assert c._pick_field_target(13, party, "") == 1        # Potion -> lowest HP% alive
    assert c._pick_field_target(24, party, "") == 3        # Revive -> the fainted one
    assert c._pick_field_target(14, party, "") == 2        # Antidote -> the poisoned one
    assert c._pick_field_target(18, party, "") is None     # Paralyze Heal -> nobody paralysed
    assert c._pick_field_target(13, party, "mon2") == 2    # explicit target wins
    full = [_mon(0, 30, 30)]
    assert _client(full)._pick_field_target(13, full, "") is None   # nobody hurt


def test_hm_needs_a_party_member_who_knows_it():
    c = _client([_mon(0, 10, 10, moves=[33])])
    assert c._party_knows(57) is False
    assert _client([_mon(0, 10, 10, moves=[33, 57])])._party_knows(57) is True


def test_conn_ranges_are_generated_for_overworld_edges():
    lo, hi = CONN_RANGES[((3, 0), "North", (3, 19))]       # Pallet -> Route 1
    assert 0 <= lo <= hi
