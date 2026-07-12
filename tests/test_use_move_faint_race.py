"""use_move reports truthfully when the lead faints before the move resolves (#68).

A faster foe can KO our lead the same turn we pick a move: our PP never drops, so the
naive success check would mash A through the forced send-out prompt (blindly confirming
a switch) and return a misleading "Could not use…". The resolution loop must instead
notice party[0] fainted (current_hp==0) or changed identity (species_id) and hand back a
truthful, actionable observation.
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402
from game.constants import Addr                    # noqa: E402


def _lead(hp, species=1, pp=(15, 15, 15, 15)):
    return PokemonStatus(slot=0, level=10, current_hp=hp, max_hp=27, status="healthy",
                         species_id=species, species_name="Bulbasaur",
                         move_names=["Tackle", "Growl", "", ""], pp=list(pp))


class _FaintFake:
    """Move menu is up; the instant the move is committed (hold A), the lead reads as
    fainted with its PP unchanged — the exact race the fix must catch."""
    def __init__(self, *, post_species=1):
        self.committed = False
        self.post_species = post_species

    # reader side
    def detect_context(self):
        return GameContext.IN_BATTLE

    def read_party(self):
        if self.committed:
            return [_lead(0, species=self.post_species), _lead(20, species=16)]
        return [_lead(18), _lead(20, species=16)]

    # mgba side
    def read32(self, addr):
        return Addr.CTRL_CHOOSE_MOVE if addr == Addr.BATTLE_CTRL_FUNC else 0

    def read8(self, addr):
        return 0                       # BATTLE_OUTCOME == 0 → battle not over

    def read16(self, addr):
        return 0

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


def test_use_move_reports_lead_faint():
    c = _client(_FaintFake())
    msg = c._use_move("Tackle")
    assert "fainted" in msg.lower()
    assert "switch_pokemon" in msg
    assert "could not use" not in msg.lower()   # not the misleading flail message


def test_use_move_reports_identity_swap():
    # Even if HP reads nonzero, a slot-0 identity change (species_id) means the mon we
    # commanded is no longer there — still not a landed move.
    class _SwapFake(_FaintFake):
        def read_party(self):
            if self.committed:
                return [_lead(18, species=99), _lead(20, species=16)]  # different species, alive
            return [_lead(18, species=1), _lead(20, species=16)]
    msg = _client(_SwapFake())._use_move("Tackle")
    assert "fainted" in msg.lower() or "switch_pokemon" in msg
    assert "could not use" not in msg.lower()
