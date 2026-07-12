"""read_party rejects a garbage decode on the battle-load frame (out-of-range species /
move ids) and reuses the last good party, instead of feeding nonsense to use_move (#58)."""
from game.constants import Addr
from game.memory_reader import LeafGreenReader
from game.state import PokemonStatus


def _mon(species_id, move_ids=(33, 0, 0, 0), level=5):
    return PokemonStatus(slot=0, species_id=species_id, species_name=f"#{species_id}",
                         level=level, move_ids=list(move_ids), move_names=["Tackle", "", "", ""],
                         pp=[35, 0, 0, 0], current_hp=20, max_hp=20, status="healthy")


class _Client:
    """One-mon party: slot 0 has level>0 (byte 0x54), the rest are empty (level 0)."""
    def read_range(self, addr, length):
        b = bytearray(length)
        if addr == Addr.PARTY_DATA:          # slot 0 occupied
            b[0x54] = 5
        return bytes(b)                      # other slots: level 0 → skipped


def _reader(decode_queue):
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _Client()
    r._last_good_party = None
    it = iter(decode_queue)
    r._decode_mon = lambda raw, slot: next(it)   # feed controlled decodes
    return r


def test_plausibility_predicate():
    assert LeafGreenReader._mon_plausible(_mon(1)) is True
    assert LeafGreenReader._mon_plausible(_mon(386)) is True
    assert LeafGreenReader._mon_plausible(_mon(34671)) is False        # garbage species
    assert LeafGreenReader._mon_plausible(_mon(1, move_ids=(34639, 0, 0, 0))) is False  # garbage move
    assert LeafGreenReader._mon_plausible(_mon(0)) is False            # empty/invalid


def test_good_read_is_returned_and_cached():
    r = _reader([_mon(1)])
    party = r.read_party()
    assert len(party) == 1 and party[0].species_id == 1
    assert r._last_good_party is party


def test_garbage_read_falls_back_to_last_good():
    r = _reader([_mon(1), _mon(34671, move_ids=(34639, 13699, 0, 0))])
    good = r.read_party()                     # first read: good, cached
    party = r.read_party()                    # second read: garbage → last good
    assert party is good and party[0].species_id == 1


def test_garbage_with_no_prior_good_returns_as_is():
    # First-ever read being garbage (no cache) has nothing better to return.
    r = _reader([_mon(34671)])
    party = r.read_party()
    assert len(party) == 1 and party[0].species_id == 34671
