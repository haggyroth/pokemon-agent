"""Gen III string decoding and state dataclass behavior."""
from game.constants import decode_gen3_string
from game.state import PokemonStatus, StateDiff


def _encode(s: str) -> bytes:
    # Minimal inverse of the charset for the letters we test.
    table = {
        "A": 0xBB, "B": 0xBC, "C": 0xBD, "R": 0xCC, "E": 0xBF, "D": 0xBE,
        " ": 0x00, "a": 0xD5, "b": 0xD6,
    }
    return bytes(table[ch] for ch in s)


def test_decode_gen3_string_basic():
    assert decode_gen3_string(_encode("ABC")) == "ABC"


def test_decode_stops_at_terminator():
    raw = _encode("RED") + bytes([0xFF]) + _encode("ABC")
    assert decode_gen3_string(raw) == "RED"


def test_decode_empty():
    assert decode_gen3_string(bytes([0xFF])) == ""


def test_hp_percent():
    p = PokemonStatus(slot=0, level=5, current_hp=15, max_hp=30, status="healthy",
                      species_id=1, species_name="Bulbasaur",
                      move_ids=[0, 0, 0, 0], move_names=["", "", "", ""], pp=[0, 0, 0, 0])
    assert p.hp_percent == 0.5
    assert not p.is_fainted


def test_fainted():
    p = PokemonStatus(slot=0, level=5, current_hp=0, max_hp=30, status="healthy",
                      species_id=1, species_name="Bulbasaur",
                      move_ids=[0, 0, 0, 0], move_names=["", "", "", ""], pp=[0, 0, 0, 0])
    assert p.is_fainted
    assert p.hp_percent == 0.0


def test_hp_percent_handles_zero_max():
    p = PokemonStatus(slot=0, level=1, current_hp=0, max_hp=0, status="healthy",
                      species_id=0, species_name="?",
                      move_ids=[0, 0, 0, 0], move_names=["", "", "", ""], pp=[0, 0, 0, 0])
    # must not raise ZeroDivisionError
    assert p.hp_percent == 0.0


def test_statediff_empty_by_default():
    assert not StateDiff().anything_changed
