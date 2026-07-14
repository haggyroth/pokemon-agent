"""Unit tests for flee_battle + travel-battle guard logic (no emulator)."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402
from game.constants import Addr                    # noqa: E402


class _Fake:
    def __init__(self, ctx, flags=0, outcome=0, party=None):
        self.ctx = ctx
        self.flags = flags
        self.outcome = outcome
        self._party = party if party is not None else []

    def detect_context(self):
        return self.ctx

    def read32(self, addr):
        return self.flags if addr == Addr.BATTLE_TYPE_FLAGS else 0

    def read8(self, addr):
        return self.outcome if addr == Addr.BATTLE_OUTCOME else 0

    def read_party(self):
        return self._party


def _client(ctx, flags=0, outcome=0, party=None):
    f = _Fake(ctx, flags, outcome, party)
    c = AgentClient.__new__(AgentClient)
    c.reader = f
    c.mgba = f
    return c


def _mon(cur, mx=50):
    return PokemonStatus(slot=0, level=18, current_hp=cur, max_hp=mx, status="healthy")


def test_flee_refuses_when_not_in_battle():
    assert "Not in a battle" in _client(GameContext.OVERWORLD)._flee_battle()


def test_flee_refuses_trainer_battle():
    msg = _client(GameContext.IN_BATTLE, flags=Addr.BATTLE_TYPE_TRAINER)._flee_battle()
    assert "trainer battle" in msg.lower()


# ── Travel trainer battles are now AUTO-FOUGHT; _auto_fight is stubbed so the tests
#    drive the post-fight state the decision logic reads (outcome / context / party HP).

def _trainer_client(*, outcome, ctx_after, party):
    c = _client(ctx_after, flags=Addr.BATTLE_TYPE_TRAINER, outcome=outcome, party=party)
    c._auto_fight = lambda: None      # don't drive a real battle in a unit test
    return c


def test_travel_trainer_win_continues_travel():
    # Clean win (outcome WON, back in overworld, lead healthy) → keep travelling (None).
    c = _trainer_client(outcome=Addr.B_OUTCOME_WON, ctx_after=GameContext.OVERWORLD,
                        party=[_mon(45)])
    assert c._handle_travel_battle("Cerulean City") is None


def test_travel_trainer_loss_bails():
    c = _trainer_client(outcome=Addr.B_OUTCOME_LOST, ctx_after=GameContext.TRANSITIONING,
                        party=[_mon(0), _mon(0)])
    msg = c._handle_travel_battle("Cerulean City")
    assert msg is not None and "lost" in msg.lower() and "heal" in msg.lower()


def test_travel_trainer_all_fainted_bails_even_without_outcome():
    # Blackout race: outcome not yet set but the whole party is down → still a loss.
    c = _trainer_client(outcome=0, ctx_after=GameContext.TRANSITIONING,
                        party=[_mon(0), _mon(0)])
    assert "lost" in c._handle_travel_battle("Cerulean City").lower()


def test_travel_trainer_unfinished_hands_back():
    # Still IN_BATTLE after a full auto pass (tough trainer / forced switch) → take over.
    c = _trainer_client(outcome=0, ctx_after=GameContext.IN_BATTLE, party=[_mon(20)])
    msg = c._handle_travel_battle("Cerulean City")
    assert msg is not None and "autopilot" in msg.lower()


def test_travel_trainer_win_but_low_hp_bails_to_heal():
    c = _trainer_client(outcome=Addr.B_OUTCOME_WON, ctx_after=GameContext.OVERWORLD,
                        party=[_mon(5)])          # 5/50 = 10% < TRAVEL_HP_FLOOR
    msg = c._handle_travel_battle("Cerulean City")
    assert msg is not None and "low" in msg.lower() and "heal" in msg.lower()


def test_action_cursor_constants():
    # RUN is index 3 in the FIGHT/BAG/POKEMON/RUN grid; cursor is the u8 adjacent
    # to the move cursor.
    assert Addr.ACTION_RUN == 3
    assert Addr.ACTION_CURSOR == 0x02023FF8
    assert Addr.CTRL_CHOOSE_ACTION == 0x08030611
