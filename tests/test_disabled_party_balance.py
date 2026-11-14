"""Regressions from the 2026-11-13 watched run: Disable loops, Struggle, the party-screen row
mapping, advance_dialog in battle, spurious level-ups from party reordering, and team balance."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.constants import Addr                    # noqa: E402
from game.memory_reader import LeafGreenReader     # noqa: E402
from game.state import GameContext, GameState, PokemonStatus  # noqa: E402
from knowledge.battle import annotate_moves, battle_summary  # noqa: E402
from knowledge.party import lagging_mons, min_level_for     # noqa: E402


def mon(species, level, hp=20, max_hp=20):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=max_hp, status="healthy",
                         species_id=species, species_name=f"S{species}")


# ── team balance ────────────────────────────────────────────────────────────────
def test_min_level_is_85_percent_rounded_up():
    assert min_level_for(18) == 16
    assert min_level_for(13) == 12
    assert min_level_for(5) == 5


def test_lagging_mons_lowest_first_and_ignores_fainted():
    party = [mon(1, 18), mon(2, 5), mon(3, 4), mon(4, 5, hp=0), mon(5, 16)]
    assert [(i, p.level) for i, p in lagging_mons(party)] == [(2, 4), (1, 5)]


def test_a_lone_pokemon_has_nothing_to_balance():
    assert lagging_mons([mon(1, 30)]) == []


# ── Disable / Struggle ──────────────────────────────────────────────────────────
class _BattleFake:
    """Reader + emulator in one: FIGHT menu up, Tackle Disabled."""
    def __init__(self, pp=(30, 40, 10, 0), disabled=(33, 3)):
        self.pp, self.disabled = list(pp), disabled
        self.pressed = []

    def detect_context(self): return GameContext.IN_BATTLE
    def read_party(self):
        return [PokemonStatus(slot=0, level=10, current_hp=18, max_hp=27, status="healthy",
                              species_id=1, species_name="Bulbasaur")]
    def read_active_battle_moves(self):
        return [33, 45, 73, 0], ["Tackle", "Growl", "Leech Seed", ""], list(self.pp)
    def read_disabled_move(self, battler=0): return self.disabled
    def read_active_battle_species(self): return 1
    def read_active_battle_hp(self): return 18
    def read32(self, addr): return Addr.CTRL_CHOOSE_MOVE if addr == Addr.BATTLE_CTRL_FUNC else 0
    def read8(self, addr): return 0
    def write8(self, a, v): pass
    def tick(self, n=1): pass
    def hold(self, b, f): self.pressed.append(b)
    def tap(self, b): self.pressed.append(b)


def _client(fake):
    c = AgentClient.__new__(AgentClient)
    c.reader = c.mgba = fake
    c._learn_armed = False
    c._learn_in_battle = True
    c._offer_resolved = 0
    c._levels_seen = None
    c._offered_move = lambda: 0
    return c


def test_disabled_move_is_refused_without_pressing_anything():
    f = _BattleFake()
    out = _client(f)._use_move("Tackle")
    assert "DISABLED" in out and "Growl" in out
    assert f.pressed == []          # never touched the game


def test_disabled_slot_is_zeroed_in_the_usable_view():
    ids, names, pp, slot, turns = _client(_BattleFake())._active_moves_view()
    assert slot == 0 and pp[0] == 0 and pp[1] == 40 and turns == 3


def test_all_moves_unusable_routes_to_struggle():
    f = _BattleFake(pp=(0, 0, 0, 0), disabled=(0, 0))
    c = _client(f)
    c._struggle = lambda: "STRUGGLED"
    assert c._use_move("Tackle") == "STRUGGLED"
    assert c._use_move("Struggle") == "STRUGGLED"


def test_struggle_is_refused_while_a_move_still_has_pp():
    c = _client(_BattleFake())
    c._struggle = lambda: "STRUGGLED"
    out = c._use_move("Struggle")
    assert "STRUGGLED" not in out and "Growl" in out


def test_disabled_tag_in_the_observation_and_no_best_move_suggestion():
    txt = annotate_moves(["Tackle", "Growl"], "Rattata", [0, 40], disabled_slot=0, disabled_turns=4)
    assert "DISABLED (4 turns)" in txt
    summary = battle_summary(["Tackle", "Growl"], "Rattata", 1.0, [0, 40],
                             disabled_slot=0, disabled_turns=4)
    assert "Best move: Tackle" not in summary


def test_no_usable_move_hint_mentions_struggle():
    summary = battle_summary(["Tackle", ""], "Rattata", 1.0, [0, 0])
    assert "Struggle" in summary


def test_read_disabled_move_decodes_struct_and_timer():
    mem = {Addr.DISABLE_STRUCTS + 4: 33, Addr.DISABLE_STRUCTS + 0xB: 0x54}

    class _C:
        def read16(self, a): return mem.get(a, 0)
        def read8(self, a): return mem.get(a, 0)

    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _C()
    assert r.read_disabled_move(0) == (33, 4)      # low nibble = turns left
    assert r.read_disabled_move(1) == (0, 0)


# ── party screen row mapping ───────────────────────────────────────────────────
def _display_client(party, order, active):
    class _M:
        def read8(self, a):
            i = a - Addr.BATTLE_PARTY_ORDER
            return order[i] if 0 <= i < len(order) else 0
        def read16(self, a): return active if a == Addr.BATTLE_MON0_SPECIES else 0
    c = AgentClient.__new__(AgentClient)
    c.mgba = _M()
    c.reader = SimpleNamespace(read_party=lambda: party)
    return c


def test_display_slot_physical_layout_ignores_battle_order():
    # Forced screen after a faint: gPlayerParty was physically swapped [Pikachu(active), Bulba, ...]
    # while gBattlePartyCurrentOrder still says [1, 0, ...]. Remapping again sent the cursor to the
    # FAINTED mon's row (live: every forced switch to that mon failed).
    party = [mon(25, 5, hp=0), mon(1, 8), mon(10, 5)]
    c = _display_client(party, [0x10, 0x23, 0x45], active=25)
    assert c._battle_display_slot(1) == 1       # Bulbasaur really is row 1


def test_display_slot_uses_battle_order_when_party_not_reordered():
    party = [mon(1, 8), mon(25, 5, hp=0), mon(10, 5)]   # field order, Pikachu (field 1) is active
    c = _display_client(party, [0x10, 0x23, 0x45], active=25)
    assert c._battle_display_slot(0) == 1       # Bulbasaur (field 0) is shown in row 1


# ── advance_dialog in battle ─────────────────────────────────────────────────────
def test_advance_dialog_in_battle_drives_battle_text_instead_of_refusing():
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(detect_context=lambda: GameContext.IN_BATTLE)
    c.mgba = SimpleNamespace(read32=lambda a: 0, read8=lambda a: 0)
    c._battle_settle = lambda: "SETTLED"
    assert c._advance_dialog() == "SETTLED"


# ── level-up arming / state diff ────────────────────────────────────────────────
def test_party_reorder_is_not_a_level_up():
    c = AgentClient.__new__(AgentClient)
    c._learn_armed = False
    c._levels_seen = None
    c._offer_resolved = 0
    c._learn_in_battle = True
    c._offered_move = lambda: 79
    c._delete_box_live = lambda: False
    c._drive_pending_learn = lambda: "DROVE"
    box = {"party": [mon(25, 5), mon(2, 18)]}
    c.reader = SimpleNamespace(read_party=lambda: box["party"],
                               detect_context=lambda: GameContext.IN_BATTLE)
    assert c._maybe_drive_learn() is None
    box["party"] = [mon(2, 18), mon(25, 5)]      # same mons, swapped order
    assert c._maybe_drive_learn() is None
    assert c._learn_armed is False


def _state(party):
    return GameState(context=GameContext.IN_BATTLE, badges=0, badge_bits=0, party=party,
                     party_count=len(party), map_bank=0, map_id=0, player_x=0, player_y=0,
                     screen_fading=False)


def test_diff_pairs_mons_by_identity_after_a_swap():
    r = LeafGreenReader.__new__(LeafGreenReader)
    before = _state([mon(25, 5), mon(2, 18, hp=21, max_hp=55)])
    after = _state([mon(2, 18, hp=21, max_hp=55), mon(25, 5)])
    d = r.diff(before, after)
    assert d.level_changed == [] and not any("leveled" in n for n in d.notes)


def test_diff_still_reports_a_real_level_up():
    r = LeafGreenReader.__new__(LeafGreenReader)
    d = r.diff(_state([mon(2, 17)]), _state([mon(2, 18)]))
    assert d.level_changed == [0]
