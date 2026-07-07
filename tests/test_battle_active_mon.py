"""Battle-end logging records the fighting mon, not always the lead (#2)."""
from game.state import PokemonStatus, active_party_member, newly_fainted_slots


def mon(slot, species, hp, max_hp=30):
    return PokemonStatus(slot=slot, level=10, current_hp=hp, max_hp=max_hp,
                         status="healthy", species_id=slot + 1, species_name=species,
                         move_ids=[0, 0, 0, 0], move_names=["", "", "", ""], pp=[0, 0, 0, 0])


PARTY = [mon(0, "Bulbasaur", 5), mon(1, "Pidgey", 22), mon(2, "Rattata", 0)]


def test_returns_member_at_slot():
    # The bug: always returning slot 0. Now slot 1 (the switched-in fighter).
    m = active_party_member(PARTY, 1)
    assert m.species_name == "Pidgey"
    assert m.hp_percent == 22 / 30


def test_lead_when_slot_zero():
    assert active_party_member(PARTY, 0).species_name == "Bulbasaur"


def test_out_of_range_falls_back_to_lead():
    assert active_party_member(PARTY, 9).species_name == "Bulbasaur"
    assert active_party_member(PARTY, -1).species_name == "Bulbasaur"


def test_empty_party_is_none():
    assert active_party_member([], 0) is None


def test_fainted_active_mon_reports_zero_hp():
    # Loss case: the last-active mon fainted -> 0% logged, not the lead's HP.
    assert active_party_member(PARTY, 2).hp_percent == 0.0


# ── newly_fainted_slots (party_faint reward, #14) ─────────────────────────────

def test_newly_fainted_detects_alive_to_zero():
    before = [mon(0, "Bulbasaur", 10), mon(1, "Pidgey", 5)]
    after = [mon(0, "Bulbasaur", 0), mon(1, "Pidgey", 5)]
    assert newly_fainted_slots(before, after) == [0]


def test_newly_fainted_ignores_already_fainted():
    before = [mon(0, "Bulbasaur", 0)]
    after = [mon(0, "Bulbasaur", 0)]
    assert newly_fainted_slots(before, after) == []


def test_newly_fainted_multiple():
    before = [mon(0, "A", 3), mon(1, "B", 3)]
    after = [mon(0, "A", 0), mon(1, "B", 0)]
    assert newly_fainted_slots(before, after) == [0, 1]
