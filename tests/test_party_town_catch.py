"""Party reordering, first-visit town healing, auto-catch in the grind loop, trainer-loss memory."""
from types import SimpleNamespace

import pytest

from game.state import GameContext, PokemonStatus
from knowledge.nicknames import auto_name, critique, sanitize

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def mon(species=1, level=10, nick="", hp=20):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=20, status="healthy", species_id=species,
                         species_name=f"S{species}", nickname=nick, move_names=["Tackle"], pp=[30])


# ── autopilot nicknames ─────────────────────────────────────────────────────────
def test_auto_names_are_typeable_varied_and_never_the_species():
    seen = set()
    for sp in ("Zubat", "Pidgey", "Tauros", "Mew"):
        n = auto_name(sp, taken=list(seen))
        assert n == sanitize(n) and len(n) <= 10 and critique(n, sp, seen) is None
        seen.add(n)
    assert len(seen) == 4


def test_auto_name_skips_a_taken_pun():
    assert auto_name("Zubat", ["Batty"]) != "Batty"


# ── reorder_party guards ────────────────────────────────────────────────────────
def _client(**kw):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(**kw)
    return c


def test_reorder_refuses_in_battle_and_bad_names():
    c = _client(detect_context=lambda: GameContext.IN_BATTLE)
    assert "switch_pokemon" in c._reorder_party("1", "2")
    c = _client(detect_context=lambda: GameContext.OVERWORLD, read_party=lambda: [mon(1), mon(2)])
    assert "Couldn't find" in c._reorder_party("Mew", "1")
    assert "same Pokémon" in c._reorder_party("1", "1")


def test_set_lead_rules():
    c = _client(read_party=lambda: [mon(1, nick="Sprout"), mon(2, hp=0), mon(3)])
    assert "already your lead" in c._set_lead("1")
    assert "fainted" in c._set_lead("2")


# ── first-visit town heal ───────────────────────────────────────────────────────
def _town_client(visited=None):
    c = AgentClient.__new__(AgentClient)
    c.ltm = SimpleNamespace(data={"pc_visited": list(visited or [])}, save=lambda: None)
    c.reader = SimpleNamespace(detect_context=lambda: GameContext.OVERWORLD)
    c.calls = []
    c._heal = lambda force=False: c.calls.append(force) or "Healed the party to full HP at the Pokémon Center."
    return c


def test_new_town_is_visited_once():
    c = _town_client()
    c._maybe_visit_new_town((3, 3), "Vermilion City")
    c._maybe_visit_new_town((3, 3), "Vermilion City")
    assert c.calls == [True] and c.ltm.data["pc_visited"] == ["3,3"]


def test_no_visit_for_routes_pallet_or_when_heading_to_a_center():
    c = _town_client()
    c._maybe_visit_new_town((3, 43), "Cerulean City")          # a route
    c._maybe_visit_new_town((3, 0), "Pewter City")             # Pallet has no Center
    c._maybe_visit_new_town((3, 3), "Pokemon Center")          # already going to one (no recursion)
    assert c.calls == []


def test_a_failed_visit_is_retried_next_time():
    c = _town_client()
    c._heal = lambda force=False: "A battle started while healing — handle it, then heal again."
    c._maybe_visit_new_town((3, 3), "x")
    assert c.ltm.data["pc_visited"] == []


# ── auto-catch gating ────────────────────────────────────────────────────────────
def test_grind_catch_declines_without_balls_or_with_a_full_party():
    foe = SimpleNamespace(species_id=16, species_name="Pidgey", level=5, max_hp=20, current_hp=20)
    c = _client(read_party=lambda: [mon(1)], read_enemy_lead=lambda: foe)
    c._ball_count = lambda: 0
    assert c._grind_try_catch() is None
    c = _client(read_party=lambda: [mon(i) for i in range(1, 7)], read_enemy_lead=lambda: foe)
    c._ball_count = lambda: 5
    assert c._grind_try_catch() is None


def test_grind_catch_declines_a_species_the_policy_rejects():
    foe = SimpleNamespace(species_id=14, species_name="Kakuna", level=5, max_hp=20, current_hp=20)
    c = _client(read_party=lambda: [mon(2, level=30)], read_enemy_lead=lambda: foe)   # L5 vs L30 team
    c._ball_count = lambda: 5
    assert c._grind_try_catch() is None
