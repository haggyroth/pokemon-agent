"""switch_pokemon target resolution: species name (exact/partial) or 1-based slot →
0-based party index. Pure logic."""
import importlib.util
from dataclasses import dataclass

import pytest

requires_openai = pytest.mark.skipif(
    importlib.util.find_spec("openai") is None, reason="openai not installed")


@dataclass
class _Mon:
    species_name: str


PARTY = [_Mon("Bulbasaur"), _Mon("Weedle"), _Mon("Pidgey")]


def _resolve(target):
    from agent.lm_studio_client import AgentClient
    return AgentClient._resolve_party_target(target, PARTY)


@requires_openai
def test_exact_species_name():
    assert _resolve("Weedle") == 1
    assert _resolve("bulbasaur") == 0        # case-insensitive


@requires_openai
def test_one_based_slot_number():
    assert _resolve("1") == 0
    assert _resolve("3") == 2


@requires_openai
def test_partial_species_name():
    assert _resolve("pidg") == 2


@requires_openai
def test_unknown_or_out_of_range():
    assert _resolve("Charmander") is None
    assert _resolve("4") is None             # only 3 in party
    assert _resolve("0") is None             # 1-based
