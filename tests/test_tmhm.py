"""TM/HM tables, compatibility, forget policy and the teach_move gating (no emulator)."""
import pytest

from game.constants import Addr
from game.state import GameContext, PokemonStatus
from knowledge.leafgreen_data import MOVE_POWER
from knowledge.tmhm import HM_MOVE_NAMES, TMHM, pick_forget, resolve_tmhm
from knowledge.tmhm_learnsets import can_learn


def test_resolve_names_labels_and_numbers():
    assert resolve_tmhm("TM09") == 297 and resolve_tmhm("tm 9") == 297
    assert resolve_tmhm("HM01") == 339 and resolve_tmhm("cut") == 339
    assert resolve_tmhm("Giga Drain") == 307 and resolve_tmhm("tm50") == 338
    assert resolve_tmhm("") is None and resolve_tmhm("hm09") is None and resolve_tmhm("nope") is None


def test_table_is_complete_and_consistent():
    assert len(TMHM) == 58
    assert TMHM[297][:2] == ("TM09", "Bullet Seed") and TMHM[341][1] == "Surf"
    assert HM_MOVE_NAMES == {"Cut", "Fly", "Surf", "Strength", "Flash", "Rock Smash", "Waterfall", "Dive"}


def test_compatibility_from_the_decomp():
    assert can_learn(1, 297) and can_learn(1, 339)            # Bulbasaur: Bullet Seed, Cut
    assert not can_learn(1, 341)                               # ...but not Surf
    assert not can_learn(25, 297)                              # Pikachu can't Bullet Seed
    assert can_learn(99999, 297)                               # unknown species: let the game decide


def test_forget_policy():
    f = lambda cur, new: pick_forget(cur, new, MOVE_POWER)  # noqa: E731
    assert f(["Tackle", "Growl", "Leech Seed", "Vine Whip"], "Giga Drain") == 1          # status first
    assert f(["Cut", "Surf", "Tackle", "Growl"], "Bullet Seed") == 3                      # never an HM move
    assert f(["Cut", "Surf", "Strength", "Fly"], "Giga Drain") is None                     # nothing safe
    assert f(["Cut", "Tackle", "Surf", "Strength"], "Giga Drain") is None                  # last attack kept


def _mon(slot, species, moves=(), hp=10):
    return PokemonStatus(slot=slot, level=5, current_hp=hp, max_hp=10, status="healthy",
                         species_id=species, species_name=f"S{species}",
                         move_names=[*moves, *[""] * (4 - len(moves))], move_ids=[])


def _client(party, tmhm, keys=(Addr.TM_CASE_ITEM,)):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)

    class R:
        def detect_context(self):
            return GameContext.OVERWORLD

        def read_party(self):
            return party

        def read_tmhm_pocket(self):
            return tmhm

        def read_key_items(self):
            return list(keys)
    c.reader = R()
    c._teach_once = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open menus"))
    return c


def test_teach_refuses_without_opening_menus_when_it_can():
    # no TM, no case, not compatible, nothing safe to forget — all decided from memory alone
    assert "don't have TM13" in _client([_mon(0, 1)], [(297, 1)])._teach_move("TM13")
    assert "TM Case" in _client([_mon(0, 1)], [(297, 1)], keys=())._teach_move("TM09")
    out = _client([_mon(0, 25)], [(297, 1)])._teach_move("TM09")
    assert "can't learn" in out
    full_hm = _mon(0, 1, ["Cut", "Surf", "Strength", "Fly"])
    assert "none is safe to forget" in _client([full_hm], [(297, 1)])._teach_move("TM09")
    assert "Don't recognise" in _client([_mon(0, 1)], [])._teach_move("zzz")
