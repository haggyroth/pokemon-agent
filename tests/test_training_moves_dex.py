"""Training lead trick, trapped awareness, Pokédex objective (PR from the 2026-11-14 observations)."""
from types import SimpleNamespace

import pytest

from game.state import GameContext, PokemonStatus
from knowledge.catch_policy import evaluate
from knowledge.readiness import assess

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def mon(species=1, level=10, hp=40, name="Bulbasaur"):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=40, status="healthy", species_id=species,
                         species_name=name, move_names=["Tackle"], pp=[30])


# ── Pokédex secondary objective ───────────────────────────────────────────────────
def test_a_full_party_still_catches_a_brand_new_dex_entry():
    full = [mon(i, 30, name=f"M{i}") for i in range(1, 7)]
    assert evaluate(full, 16, 5, dex_owned=False).catch
    assert not evaluate(full, 16, 5, dex_owned=True).catch
    assert not evaluate(full, 16, 5).catch                       # unknown: the old rule


def test_readiness_mentions_the_dex_only_when_nothing_is_urgent():
    team = [mon(i, 30, name=f"M{i}") for i in range(1, 5)]
    texts = [n.text for n in assess(team, 9, 5, 0, ["Brock", "Misty", "Lt. Surge", "Erika"], dex=(20, 40))]
    assert any("Pokédex 20/151" in t for t in texts)
    hurt = [mon(1, 30, hp=3)] + team[1:]
    assert not any("Pokédex" in n.text for n in assess(hurt, 9, 5, 0, [], dex=(20, 40)))


# ── trapped awareness ───────────────────────────────────────────────────────────────
def _trapped_client(trapped, forced=False):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(is_trapped=lambda b=0: trapped,
                               read_battle_volatiles=lambda b=0: {"wrapped": 3} if trapped else {},
                               detect_context=lambda: GameContext.IN_BATTLE,
                               read_party=lambda: [mon(1), mon(2, name="B")])
    c.mgba = SimpleNamespace(read32=lambda a: 0, read16=lambda a: 0, read8=lambda a: 0)
    return c


def test_flee_and_switch_refuse_while_trapped_with_an_explanation():
    c = _trapped_client(True)
    assert "can't run" in c._flee_battle() and "Wrap" in c._flee_battle()
    assert "can't switch" in c._switch_pokemon("2")


def test_not_trapped_means_no_refusal_message():
    c = _trapped_client(False)
    assert c._battle_trapped() is False


def test_volatile_decoding():
    from game.memory_reader import LeafGreenReader
    from game.constants import Addr
    mem = {Addr.BATTLE_MON0_SPECIES + Addr.BATTLE_MON_STATUS2: (3 << 13) | (1 << 26) | (1 << 31)}
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = SimpleNamespace(read32=lambda a: mem.get(a, 0))
    v = r.read_battle_volatiles(0)
    assert v["wrapped"] == 3 and v["escape_prevention"] and v["tormented"]
    assert r.is_trapped(0)
    assert r.read_battle_volatiles(1) == {}


# ── training: the trainee leads ─────────────────────────────────────────────────────
def test_lead_trainee_moves_the_trainee_to_slot_one_and_remembers_to_restore():
    ace, trainee = mon(2, 40, name="Venusaur"), mon(25, 12, name="Pikachu")
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_party=lambda: [ace, trainee])
    calls = []
    c._set_lead = lambda who: calls.append(who) or "Swapped slots 1 and 2. Party order: ..."
    c._training_swapped = False
    assert c._lead_trainee(trainee) is True and calls == ["2"] and c._training_swapped
    calls.clear()
    assert c._lead_trainee(ace) is True and calls == []         # already in front: nothing to do


def test_restore_ace_lead_puts_the_highest_level_back_in_front():
    from types import SimpleNamespace as NS
    party = [mon(25, 12, name="Pikachu"), mon(2, 40, name="Venusaur"), mon(10, 8, hp=0, name="Caterpie")]
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: party, detect_context=lambda: GameContext.OVERWORLD)
    calls = []

    def set_lead(who):
        i = int(who) - 1
        calls.append(who)
        party[0], party[i] = party[i], party[0]            # the swap happens, so the retry loop stops
    c._set_lead = set_lead
    c._restore_ace_lead()
    assert calls == ["2"] and party[0].species_name == "Venusaur"


def test_balance_gap_is_seven_levels():
    from knowledge.party import min_level_for
    assert min_level_for(40) == 33


# ── training: tag-switch, never back to the trainee ───────────────────────────────────
class _TrainBattle:
    """Just enough of a battle for AgentClient._train_fight: scripted party/foe, a log of switches and moves."""

    def __init__(self, party, foe_level, active, turns_to_win=3):
        self.party, self.foe_level, self.active_idx, self.turns = party, foe_level, active, turns_to_win
        self.log = []

    def client(self):
        c = AgentClient.__new__(AgentClient)
        b = self
        c.reader = SimpleNamespace(
            detect_context=lambda: GameContext.IN_BATTLE if b.turns > 0 else GameContext.OVERWORLD,
            read_party=lambda: b.party,
            read_enemy_lead=lambda: SimpleNamespace(level=b.foe_level, max_hp=30, current_hp=30, species_name="Foe"),
            read_active_battle_species=lambda: b.party[b.active_idx].species_id)
        c._battle_settle = lambda *a, **k: ""
        c._send_next_mon = lambda: None
        c._maybe_drive_learn = lambda: None
        c._maybe_heal_mid_fight = lambda used: False
        c._active_moves_view = lambda: ([1], ["Tackle"], [20], None, 0)
        c._battle_types = lambda: ((), ())
        c._settle_evolution = lambda: None
        c._no_attack_turn = lambda: None

        def switch(t):
            b.log.append(("switch", b.party[int(t) - 1].species_name))
            b.active_idx = int(t) - 1
            return "Switched in"

        def use(mv):
            b.log.append(("move", b.party[b.active_idx].species_name))
            b.turns -= 1
        c._switch_pokemon, c._use_move = switch, use
        c._best_damaging_move = staticmethod(lambda *a: "Tackle")
        return c


def test_train_fight_tags_the_trainee_out_once_and_never_swaps_it_back():
    # The live bug: trainee leads, tough foe → ace switched in, then the loop switched the TRAINEE back
    # (fed to the foe for no XP). Expect exactly one switch: trainee → ace, then the ace finishes.
    party = [mon(10, 6, name="Caterpie"), mon(1, 40, name="Bulbasaur"), mon(25, 5, name="Pikachu")]
    b = _TrainBattle(party, foe_level=20, active=0)
    c = b.client()
    c._train_fight((party[0].species_id, party[0].max_hp))
    assert b.log[0] == ("switch", "Bulbasaur")
    assert [e for e in b.log if e[0] == "switch"] == [("switch", "Bulbasaur")]
    assert all(e == ("move", "Bulbasaur") for e in b.log[1:])


def test_train_fight_lets_the_trainee_fight_an_easy_foe_alone():
    party = [mon(10, 6, name="Caterpie"), mon(1, 40, name="Bulbasaur")]
    b = _TrainBattle(party, foe_level=6, active=0)
    b.client()._train_fight((party[0].species_id, party[0].max_hp))
    assert [e for e in b.log if e[0] == "switch"] == [] and {e[1] for e in b.log} == {"Caterpie"}


def test_train_fight_brings_a_benched_trainee_in_then_tags_it_out():
    party = [mon(1, 40, name="Bulbasaur"), mon(10, 8, name="Caterpie")]
    b = _TrainBattle(party, foe_level=15, active=0)          # travel fight: the ace is out front
    b.client()._train_fight((party[1].species_id, party[1].max_hp))
    assert [e for e in b.log if e[0] == "switch"] == [("switch", "Caterpie"), ("switch", "Bulbasaur")]


def test_train_fight_skips_a_risky_swap_in_for_a_hurt_trainee():
    party = [mon(1, 40, name="Bulbasaur"), mon(10, 8, hp=15, name="Caterpie")]
    b = _TrainBattle(party, foe_level=15, active=0)
    b.client()._train_fight((party[1].species_id, party[1].max_hp))
    assert [e for e in b.log if e[0] == "switch"] == []        # the ace just fights; no free hit on the trainee


def test_xp_share_hint():
    from knowledge.battle import xp_share_hint
    party = [mon(10, 6, name="Caterpie"), mon(1, 40, name="Bulbasaur")]
    assert "switch_pokemon('Bulbasaur')" in xp_share_hint(party, party[0].species_id, 20)
    assert "set_lead('Caterpie')" in xp_share_hint(party, party[1].species_id, 20)
    assert xp_share_hint([mon(1, 40, name="A"), mon(2, 36, name="B")], 1) == ""
