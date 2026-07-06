"""Gen III substructure decryption + status decoding."""
import pytest

from game.memory_reader import (
    decrypt_substructs, parse_species, parse_moves, decode_status, SUBSTRUCT_ORDER,
)
from conftest import build_party_mon


@pytest.mark.parametrize("pid", [0, 1, 23, 24, 0xABCDEF12, 0x00030201])
def test_decrypt_roundtrip_species_and_moves(pid):
    ot_id = 0x11223344
    mon = build_party_mon(pid, ot_id, level=10, cur_hp=20, max_hp=30,
                          species=0x0199, moves=(33, 45, 22, 14), pp=(35, 20, 10, 5))
    sub = decrypt_substructs(mon)
    assert parse_species(sub) == 0x0199
    move_ids, pp = parse_moves(sub)
    assert move_ids == [33, 45, 22, 14]
    assert pp == [35, 20, 10, 5]


def test_substruct_order_table_is_permutations():
    assert len(SUBSTRUCT_ORDER) == 24
    for order in SUBSTRUCT_ORDER:
        assert sorted(order) == ["A", "E", "G", "M"]


def test_key_is_pid_xor_otid():
    # Two PIDs sharing pid % 24 but different keys must still decode correctly.
    a = build_party_mon(24, 0xDEADBEEF, level=5, cur_hp=1, max_hp=1, species=7)
    b = build_party_mon(0, 0x00000000, level=5, cur_hp=1, max_hp=1, species=7)
    assert parse_species(decrypt_substructs(a)) == 7
    assert parse_species(decrypt_substructs(b)) == 7


@pytest.mark.parametrize("word,expected", [
    (0, "healthy"),
    (1, "asleep (1 turns)"),
    (3, "asleep (3 turns)"),
    (1 << 3, "poisoned"),
    (1 << 4, "burned"),
    (1 << 5, "frozen"),
    (1 << 6, "paralyzed"),
    (1 << 7, "badly_poisoned"),
])
def test_decode_status(word, expected):
    assert decode_status(word) == expected


def test_sleep_takes_priority_over_higher_bits():
    # Low 3 bits (sleep counter) set alongside a higher status bit → sleep wins.
    assert decode_status(0b0000_0010) == "asleep (2 turns)"
