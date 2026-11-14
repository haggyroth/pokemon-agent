"""The 2026-11-13 zero-PP loop: with attacks out of PP the grind spammed Growl/Harden forever."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.constants import Addr                    # noqa: E402
from game.state import PokemonStatus  # noqa: E402
from knowledge.battle import annotate_moves, battle_summary   # noqa: E402
from knowledge.party import attack_pp, can_attack, party_needs_restock   # noqa: E402


def mon(species, level, moves, pp, hp=20, max_hp=20):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=max_hp, status="healthy",
                         species_id=species, species_name=f"S{species}",
                         move_names=list(moves), pp=list(pp))


# ── pure rules ──────────────────────────────────────────────────────────────────
def test_status_moves_never_count_as_attack_pp():
    m = mon(1, 19, ["Tackle", "Growl", "Leech Seed", "Vine Whip"], [0, 40, 10, 0])
    assert attack_pp(m) == 0 and not can_attack(m)
    assert can_attack(mon(1, 19, ["Tackle", "Growl"], [3, 40]))


def test_kakuna_style_mon_cannot_attack():
    assert not can_attack(mon(14, 5, ["Harden", "String Shot"], [30, 40]))


def test_restock_when_best_attacker_is_out_of_attack_pp():
    spent = mon(1, 19, ["Tackle", "Growl"], [0, 40])
    weak = mon(2, 5, ["Harden"], [30])
    assert "attacking PP" in party_needs_restock([spent, weak])


def test_restock_when_nearly_out_and_not_when_fine():
    assert "nearly out" in party_needs_restock([mon(1, 19, ["Tackle"], [2]), mon(2, 5, ["Tackle"], [35])])
    assert party_needs_restock([mon(1, 19, ["Tackle"], [20]), mon(2, 5, ["Tackle"], [35])]) == ""


def test_restock_when_everyone_hurt():
    assert party_needs_restock([mon(1, 19, ["Tackle"], [20], hp=2), mon(2, 5, ["Tackle"], [20], hp=1)])


# ── observation text ───────────────────────────────────────────────────────────
def test_status_moves_are_labelled_no_damage_not_super_effective():
    txt = annotate_moves(["Leech Seed", "Growl"], "Geodude", [10, 40])
    assert "SUPER" not in txt and txt.count("NO damage") == 2


def test_summary_warns_when_only_status_moves_have_pp():
    out = battle_summary(["Tackle", "Growl"], "Rattata", 1.0, [0, 40], backup_hint="Switch to Pikachu.")
    assert "NO ATTACKING MOVE WITH PP" in out and "Switch to Pikachu." in out


def test_summary_quiet_when_an_attack_has_pp():
    out = battle_summary(["Tackle", "Growl"], "Rattata", 1.0, [30, 40])
    assert "NO ATTACKING MOVE" not in out


# ── _no_attack_turn ────────────────────────────────────────────────────────────
class _F:
    def __init__(self, names, pp, trainer=False):
        self.names, self.pp, self.trainer = names, pp, trainer

    def read_active_battle_moves(self): return [1] * 4, list(self.names), list(self.pp)
    def read_active_battle_species(self): return 1
    def read_party(self):
        return [mon(1, 19, self.names, self.pp), mon(25, 12, ["Thunder Shock"], [30], hp=15),
                mon(14, 5, ["Harden"], [30])]
    def read32(self, a): return 0x08 if a == Addr.BATTLE_TYPE_FLAGS and self.trainer else 0


def _client(f, calls):
    c = AgentClient.__new__(AgentClient)
    c.reader = c.mgba = f
    c._active_moves_view = lambda: (f.read_active_battle_moves()[0], f.names, f.pp, None, 0)
    c._struggle = lambda: calls.append("struggle") or "S"
    c._switch_pokemon = lambda t: calls.append(("switch", t)) or "W"
    c._flee_battle = lambda: calls.append("flee") or "F"
    c._use_move = lambda m: calls.append(("move", m)) or "M"
    return c


def test_all_pp_gone_means_struggle():
    calls = []
    _client(_F(["Tackle", "Growl"], [0, 0]), calls)._no_attack_turn()
    assert calls == ["struggle"]


def test_status_only_lead_switches_to_a_teammate_that_can_attack():
    calls = []
    _client(_F(["Tackle", "Growl"], [0, 40]), calls)._no_attack_turn()
    assert calls == [("switch", "2")]        # Pikachu (Kakuna can't attack; Bulbasaur is the active one)


def test_wild_battle_with_nobody_left_flees_instead_of_spamming():
    calls = []
    f = _F(["Tackle", "Growl"], [0, 40])
    f.read_party = lambda: [mon(1, 19, f.names, f.pp), mon(14, 5, ["Harden"], [30])]
    _client(f, calls)._no_attack_turn()
    assert calls == ["flee"]


def test_trainer_battle_with_nobody_left_uses_a_move_not_flee():
    calls = []
    f = _F(["Growl", "Tackle"], [40, 0], trainer=True)
    f.read_party = lambda: [mon(1, 19, f.names, f.pp)]
    _client(f, calls)._no_attack_turn()
    assert calls == [("move", "Growl")]


def test_repeated_status_move_gets_a_warning():
    c = AgentClient.__new__(AgentClient)
    assert c._status_streak_note("Growl") == ""
    assert "2× in a row" in c._status_streak_note("Growl")
    assert c._status_streak_note("Tackle") == ""        # a damaging move resets it
    assert c._status_streak_note("Growl") == ""


# ── heal() must work when only PP is gone ──────────────────────────────────────
def test_heal_gate_sees_an_out_of_pp_team_at_full_hp():
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_party=lambda: [mon(1, 19, ["Tackle", "Growl"], [0, 40])])
    assert c._party_needs_heal() is True
    c.reader = SimpleNamespace(read_party=lambda: [mon(1, 19, ["Tackle", "Growl"], [20, 40])])
    assert c._party_needs_heal() is False
