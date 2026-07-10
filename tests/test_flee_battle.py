"""Unit tests for flee_battle's guard logic (no emulator)."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext                # noqa: E402
from game.constants import Addr                    # noqa: E402


class _Fake:
    def __init__(self, ctx, flags=0):
        self.ctx = ctx
        self.flags = flags

    def detect_context(self):
        return self.ctx

    def read32(self, addr):
        return self.flags if addr == Addr.BATTLE_TYPE_FLAGS else 0


def _client(ctx, flags=0):
    f = _Fake(ctx, flags)
    c = AgentClient.__new__(AgentClient)
    c.reader = f
    c.mgba = f
    return c


def test_flee_refuses_when_not_in_battle():
    assert "Not in a battle" in _client(GameContext.OVERWORLD)._flee_battle()


def test_flee_refuses_trainer_battle():
    msg = _client(GameContext.IN_BATTLE, flags=Addr.BATTLE_TYPE_TRAINER)._flee_battle()
    assert "trainer battle" in msg.lower()


def test_action_cursor_constants():
    # RUN is index 3 in the FIGHT/BAG/POKEMON/RUN grid; cursor is the u8 adjacent
    # to the move cursor.
    assert Addr.ACTION_RUN == 3
    assert Addr.ACTION_CURSOR == 0x02023FF8
    assert Addr.CTRL_CHOOSE_ACTION == 0x08030611
