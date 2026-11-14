"""Catch policy: don't take on grinding debt for weak/low-level species (#185 item 4)."""
from types import SimpleNamespace as P

from knowledge.catch_policy import evaluate
from knowledge.species_data import SPECIES_DATA

BULBASAUR, IVYSAUR, CATERPIE, PIDGEY, PIKACHU, KAKUNA, GEODUDE, ZUBAT, MAGIKARP, ABRA = 1, 2, 10, 16, 25, 14, 74, 41, 129, 63


def party(*mons):
    return [P(species_id=i, species_name=n, level=lv) for i, n, lv in mons]


def test_generated_table_has_sane_values():
    bst, types, line = SPECIES_DATA[PIKACHU]
    assert bst == 300 and types == ("ELE",) and line >= bst
    assert SPECIES_DATA[CATERPIE][0] < 250 and SPECIES_DATA[MAGIKARP][2] > 500


def test_near_level_species_with_a_new_type_is_worth_it():
    v = evaluate(party((BULBASAUR, "Bulbasaur", 8)), PIKACHU, 5)
    assert v.catch and v.debt <= 3


def test_big_level_gap_is_refused_even_for_a_decent_species():
    # the run-#2 mistakes: L5 Kakuna / L7 Zubat / L6 Geodude behind a (now) L40 lead
    team = party((IVYSAUR, "Ivysaur", 40))
    for sid, lvl in ((KAKUNA, 5), (ZUBAT, 7), (GEODUDE, 6), (MAGIKARP, 5)):
        v = evaluate(team, sid, lvl)
        assert not v.catch and "levels under your balance floor" in v.reason, (sid, v)


def test_premium_line_is_accepted_when_the_gap_is_small():
    team = party((IVYSAUR, "Ivysaur", 19))
    assert evaluate(team, GEODUDE, 12).catch          # debt 3 → fine
    assert evaluate(team, ABRA, 10).catch             # premium line, debt 5


def test_already_owned_and_full_party_are_refused():
    team = party((BULBASAUR, "Bulbasaur", 8))
    assert "already have" in evaluate(team, BULBASAUR, 8).reason
    full = party(*[(i, f"M{i}", 10) for i in range(1, 7)])
    assert "party is full" in evaluate(full, PIKACHU, 10).reason


def test_unknown_species_is_refused():
    assert not evaluate(party((BULBASAUR, "Bulbasaur", 8)), 99999, 5).catch


def test_go_to_only_stops_on_worthwhile_species():
    import pytest
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    team = party((IVYSAUR, "Ivysaur", 19))
    weak = P(species_id=KAKUNA, species_name="Kakuna", level=5)
    ok = P(species_id=GEODUDE, species_name="Geodude", level=17)
    assert AgentClient._is_new_team_species(team, weak) is False
    assert AgentClient._is_new_team_species(team, ok) is True


# ── party composition: upgrades and a bigger debt allowance (the team stalled at 4 weak members) ──
def test_a_stronger_line_than_the_weakest_member_is_an_upgrade_even_far_behind():
    team = party((IVYSAUR, "Ivysaur", 30), (CATERPIE, "Caterpie", 10), (PIDGEY, "Pidgey", 12))
    v = evaluate(team, ABRA, 14)                 # Alakazam line vs the Caterpie line; debt 9 (floor 23)
    assert v.catch and v.debt >= 5


def test_full_party_catches_an_upgrade_into_the_box_with_a_pc_swap_hint():
    full = party((IVYSAUR, "Ivysaur", 30), (CATERPIE, "Caterpie", 12), (PIDGEY, "Pidgey", 12),
                 (CATERPIE + 1, "Metapod", 12), (CATERPIE + 2, "Butterfree", 12), (13, "Weedle", 12))
    v = evaluate(full, ABRA, 18)
    assert v.catch and "pc_swap" in v.reason


def test_a_weak_line_only_adding_a_type_still_needs_a_small_gap():
    team = party((IVYSAUR, "Ivysaur", 19))
    assert not evaluate(team, KAKUNA, 5).catch   # debt 7 > TYPE_DEBT
