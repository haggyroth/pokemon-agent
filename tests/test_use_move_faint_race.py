"""use_move reports truthfully when the active mon faints before the move resolves (#68).

A faster foe can KO our mon the same turn we pick a move: our PP never drops, so the
naive success check would mash A through the forced send-out prompt (blindly confirming
a switch) and return a misleading "Could not use…". The resolution loop must instead
notice the ACTIVE battler (gBattleMons[0]) fainted (hp==0) or changed identity (species)
and hand back a truthful, actionable observation.
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402
from game.constants import Addr                    # noqa: E402


class _FaintFake:
    """The FIGHT menu is up; the instant the move is committed (hold A), the ACTIVE
    battler reads as fainted with its PP unchanged — the exact race the fix must catch.
    Models gBattleMons[0] via the read_active_battle_* reader methods use_move now uses."""
    def __init__(self, *, post_species=1, post_hp=0):
        self.committed = False
        self.post_species = post_species
        self.post_hp = post_hp

    # reader side
    def detect_context(self):
        return GameContext.IN_BATTLE

    def read_party(self):
        # Only used for the "no active Pokémon" sanity check at the top.
        return [PokemonStatus(slot=0, level=10, current_hp=18, max_hp=27, status="healthy",
                              species_id=1, species_name="Bulbasaur")]

    def read_active_battle_moves(self):
        # PP never drops — the mon fainted before its move fired.
        return [33, 45, 0, 0], ["Tackle", "Growl", "", ""], [15, 15, 0, 0]

    def read_active_battle_species(self):
        return self.post_species if self.committed else 1

    def read_active_battle_hp(self):
        return self.post_hp if self.committed else 18

    # mgba side
    def read32(self, addr):
        return Addr.CTRL_CHOOSE_MOVE if addr == Addr.BATTLE_CTRL_FUNC else 0

    def read8(self, addr):
        return 0                       # BATTLE_OUTCOME == 0 → battle not over

    def write8(self, addr, val):
        pass

    def hold(self, button, frames):
        self.committed = True          # committing the move is when the KO lands

    def tick(self, n=1):
        pass


def _client(fake):
    c = AgentClient.__new__(AgentClient)
    c.reader = fake
    c.mgba = fake
    c._maybe_drive_learn = lambda: None   # no level-up prompt in this scenario
    return c


def test_use_move_reports_active_mon_faint():
    c = _client(_FaintFake(post_hp=0))
    msg = c._use_move("Tackle")
    assert "fainted" in msg.lower()
    assert "switch_pokemon" in msg
    assert "could not use" not in msg.lower()   # not the misleading flail message


def test_use_move_reports_identity_swap():
    # Even if HP reads nonzero, an active-species change means the mon we commanded is no
    # longer out (a forced switch already sent the next one) — still not a landed move.
    c = _client(_FaintFake(post_species=99, post_hp=18))
    msg = c._use_move("Tackle")
    assert "fainted" in msg.lower() or "switch_pokemon" in msg
    assert "could not use" not in msg.lower()


class _ActiveMonFake:
    """The ACTIVE battler is a Pidgey with only two moves (Gust, Sand-Attack); the LEAD
    (party[0]) is an Ivysaur with four. use_move must validate/index against the ACTIVE
    mon (gBattleMons[0]) — else it targets an empty slot / rejects the real moves."""
    def __init__(self):
        self.cursor = None
        self.pp = [35, 15, 0, 0]

    def detect_context(self):
        return GameContext.IN_BATTLE

    def read_party(self):
        return [PokemonStatus(slot=0, level=20, current_hp=50, max_hp=50, status="healthy",
                              species_id=2, species_name="Ivysaur",
                              move_names=["Vine Whip", "Tackle", "Growl", "Leech Seed"],
                              pp=[10, 20, 30, 10])]

    def read_active_battle_moves(self):
        return [16, 28, 0, 0], ["Gust", "Sand-Attack", "", ""], list(self.pp)

    def read_active_battle_species(self):
        return 16          # Pidgey

    def read_active_battle_hp(self):
        return 20

    def read32(self, addr):
        return Addr.CTRL_CHOOSE_MOVE if addr == Addr.BATTLE_CTRL_FUNC else 0

    def read8(self, addr):
        return 0

    def write8(self, addr, val):
        if addr == Addr.MOVE_CURSOR:
            self.cursor = val

    def hold(self, button, frames):
        if self.cursor is not None:      # committing the chosen slot drops its PP
            self.pp[self.cursor] -= 1

    def tick(self, n=1):
        pass


def test_use_move_indexes_active_mon_not_lead():
    # Gust is the ACTIVE Pidgey's move (slot 0); use_move must target slot 0 and land it,
    # never the lead Ivysaur's slots.
    f = _ActiveMonFake()
    msg = _client(f)._use_move("Gust")
    assert "Used Gust" in msg
    assert f.cursor == 0                # committed the active mon's slot, not an empty one


def test_use_move_rejects_a_move_only_the_lead_knows():
    # Vine Whip is the LEAD's move but NOT the active Pidgey's — must be rejected, proving
    # validation is against the active battler (the empty-slot bug the user hit).
    msg = _client(_ActiveMonFake())._use_move("Vine Whip")
    assert "not a known move" in msg.lower()
    assert "Gust" in msg               # lists the ACTIVE mon's real moves


def test_use_move_rejects_empty_move_name():
    # An empty name must not match an empty move slot.
    msg = _client(_ActiveMonFake())._use_move("")
    assert "not a known move" in msg.lower()
