"""PC boxes: memory decoding, growth levels, skill guards (the UI itself is covered by the live tests)."""
from types import SimpleNamespace

import pytest

from game.constants import Addr
from game.memory_reader import SUBSTRUCT_ORDER, LeafGreenReader
from knowledge.growth import exp_for_level, level_from_exp


def test_growth_levels_match_the_decomp_formulas():
    assert level_from_exp(1, 4575) == 19 and level_from_exp(1, 555) == 9       # Bulbasaur: medium slow
    assert level_from_exp(25, 135) == 5                                           # Pikachu: medium fast
    assert exp_for_level(0, 10) == 1000 and exp_for_level(4, 10) == 800 and exp_for_level(5, 10) == 1250
    assert level_from_exp(1, 0) == 1 and level_from_exp(1, 10**9) == 100


def _boxmon(species, exp, nick=b"\xc3\xcc\xff"):
    """An 80-byte BoxPokemon: personality/OT, nickname, encrypted substructs (G = species+exp)."""
    pid, ot = 0x11223344, 0x55667788
    key = pid ^ ot
    sub = {k: bytearray(12) for k in "GAEM"}
    sub["G"][0:2] = species.to_bytes(2, "little")
    sub["G"][4:8] = exp.to_bytes(4, "little")
    sub["A"][0:2] = (33).to_bytes(2, "little")                                    # Tackle
    order = SUBSTRUCT_ORDER[pid % 24]
    blob = bytearray()
    for letter in order:
        blob += sub[letter]
    for i in range(0, 48, 4):
        w = int.from_bytes(blob[i:i + 4], "little") ^ key
        blob[i:i + 4] = w.to_bytes(4, "little")
    raw = bytearray(80)
    raw[0:4], raw[4:8] = pid.to_bytes(4, "little"), ot.to_bytes(4, "little")
    raw[8:8 + len(nick)] = nick
    raw[32:80] = blob
    return bytes(raw)


def _reader(boxes):
    base = 0x02029000
    mem = {Addr.POKEMON_STORAGE_PTR: base, base: 1}
    ram = bytearray(14 * 30 * 80)
    for (b, s), data in boxes.items():
        off = (b * 30 + s) * 80
        ram[off:off + 80] = data

    class _C:
        def read32(self, a): return mem.get(a, 0)
        def read8(self, a): return mem.get(a, 0)
        def read_range(self, a, n):
            off = a - (base + 4)
            return bytes(ram[off:off + n])
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _C()
    return r


def test_box_mons_decode_species_level_and_skip_empty_slots():
    r = _reader({(0, 0): _boxmon(25, 135), (1, 14): _boxmon(1, 4575)})
    boxes = r.read_boxes()
    assert [(m["box"], m["slot"], m["species_name"], m["level"]) for m in boxes] == \
        [(0, 0, "Pikachu", 5), (1, 14, "Bulbasaur", 19)]
    assert boxes[0]["move_names"] == ["Tackle"]
    assert r.read_current_box() == 1
    assert r.read_box_mon(3, 3) is None


def _client(party, boxes=()):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_party=lambda: party, read_boxes=lambda: list(boxes))
    c._open_pc = lambda mode=1: "SHOULD NOT OPEN"
    return c


def mon(name, hp=20, nick=""):
    return SimpleNamespace(species_name=name, nickname=nick, current_hp=hp, max_hp=20)


def test_deposit_refuses_the_last_pokemon_and_the_last_able_one():
    assert "only Pokémon" in _client([mon("A")])._pc_deposit("1")
    out = _client([mon("A"), mon("B", hp=0)])._pc_deposit("A")
    assert "only Pokémon able to battle" in out
    assert "Couldn't find" in _client([mon("A"), mon("B")])._pc_deposit("Mew")


def test_withdraw_needs_a_match_and_a_free_slot():
    assert "No Pokémon matching" in _client([mon("A")], [])._pc_withdraw("pikachu")
    box = [{"box": 0, "slot": 3, "species_name": "Pikachu", "nickname": "Zap", "level": 9}]
    assert "party is full" in _client([mon(str(i)) for i in range(6)], box)._pc_withdraw("zap")


def test_swap_validates_the_boxed_pokemon_before_depositing_anything():
    c = _client([mon("A"), mon("B")], [])
    c._pc_deposit = lambda who: (_ for _ in ()).throw(AssertionError("must not deposit"))
    assert "nothing was deposited" in c._pc_swap("A", "nobody")


def test_pc_listing_reads_nicely():
    box = [{"box": 0, "slot": 3, "species_name": "Pikachu", "nickname": "Zap", "level": 9},
           {"box": 1, "slot": 0, "species_name": "Geodude", "nickname": "", "level": 12}]
    out = _client([mon("A")], box)._pc_boxes()
    assert "Box 1: [3] Zap (Pikachu L9)" in out and "Box 2: [0] Geodude (Geodude L12)" in out
