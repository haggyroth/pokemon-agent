"""Team-building: go_to stops on a wild NEW species (so the model can catch a roster
instead of auto-fleeing everything). Pins the pure decision — small team, a real named
species not already owned — including the garbage-read guard (#58)."""
import importlib.util
from dataclasses import dataclass

import pytest

requires_openai = pytest.mark.skipif(
    importlib.util.find_spec("openai") is None, reason="openai not installed")


@dataclass
class _Mon:
    species_id: int
    species_name: str = "X"


def _decide(party, enemy):
    from agent.lm_studio_client import AgentClient
    return AgentClient._is_new_team_species(party, enemy)


@requires_openai
def test_offers_a_new_species_for_a_small_team():
    party = [_Mon(1, "Bulbasaur")]
    assert _decide(party, _Mon(19, "Rattata")) is True


@requires_openai
def test_skips_a_species_already_on_the_team():
    party = [_Mon(1, "Bulbasaur"), _Mon(19, "Rattata")]
    assert _decide(party, _Mon(19, "Rattata")) is False


@requires_openai
def test_skips_once_team_is_full_enough():
    party = [_Mon(1), _Mon(19), _Mon(16), _Mon(10)]     # 4 already
    assert _decide(party, _Mon(21, "Spearow")) is False


@requires_openai
def test_ignores_garbage_battle_load_read():
    # The enemy struct reads junk on the battle-load frame (#58): a huge id / a "#"
    # placeholder name must NOT be offered as a catchable species.
    party = [_Mon(1, "Bulbasaur")]
    assert _decide(party, _Mon(62171, "#62171")) is False
    assert _decide(party, _Mon(0, "")) is False
    assert _decide(party, None) is False
