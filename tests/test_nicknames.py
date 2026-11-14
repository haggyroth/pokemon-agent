"""Nicknames are the model's to invent; the code only keeps them typeable and non-bland."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402
from knowledge.nicknames import critique, sanitize  # noqa: E402


def test_sanitize_folds_accents_and_drops_untypeable_chars():
    assert sanitize("Pokémon’s") == "Pokemons"
    assert sanitize("Mr. Zap!") == "Mr. Zap!"
    assert sanitize("Wing-Ding") == "Wing Ding"
    assert sanitize("  ") == ""
    assert len(sanitize("A very long nickname")) <= 10


@pytest.mark.parametrize("name", ["Kakuna1", "Geodude 2", "kakuna", "K"])
def test_bland_names_are_criticised(name):
    assert critique(name, "Kakuna", []) or critique(name, "Geodude", [])


def test_species_name_with_number_is_just_the_species():
    assert "species name" in critique("Zubat 2", "Zubat", [])


def test_duplicate_and_too_long_are_flagged_but_creative_names_pass():
    assert "already on your team" in critique("rocky", "Geodude", ["ROCKY"])
    assert "limit is 10" in critique("Sir Wiggles", "Caterpie", [])
    assert critique("Wing Ding", "Zubat", ["BULBASAUR"]) is None
    assert critique("Mr. Zap!", "Pikachu", []) is None


class _F:
    def __init__(self):
        self.bag_opened = False

    def detect_context(self): return GameContext.IN_BATTLE
    def read32(self, a): return 0
    def read_enemy_lead(self): return SimpleNamespace(species_name="Zubat")
    def read_party(self):
        return [PokemonStatus(slot=0, level=9, current_hp=5, max_hp=9, status="healthy",
                              species_id=1, species_name="Bulbasaur", nickname="Sprout")]


def _client(f):
    c = AgentClient.__new__(AgentClient)
    c.reader = c.mgba = f
    c._ball_count = lambda: 5

    def opened():
        f.bag_opened = True
        return False
    c._open_battle_bag = opened
    return c


def test_bland_nickname_is_refused_once_without_throwing_a_ball():
    f = _F()
    c = _client(f)
    out = c._catch("Zubat")
    assert out.startswith("No ball thrown") and "species name" in out and not f.bag_opened
    c._catch("Zubat")                       # second try is accepted (never loops)
    assert f.bag_opened


def test_creative_nickname_goes_straight_through():
    f = _F()
    _client(f)._catch("Batty Boop")
    assert f.bag_opened
