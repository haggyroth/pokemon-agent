"""switch_pokemon maps a field slot to the in-battle party menu's DISPLAY slot (#120).

The in-battle party menu lists mons in battle order (gBattlePartyCurrentOrder, packed
nibbles). It's identity at battle start but a switch permutes it, so a field slot and its
on-screen slot diverge — the reason a 2nd switch used to land on the active mon and get
rejected as "already in battle".
"""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.constants import Addr                    # noqa: E402


class _OrderFake:
    """Serves the 3 packed order bytes at Addr.BATTLE_PARTY_ORDER."""
    def __init__(self, order_bytes):
        self.order = order_bytes

    def read8(self, addr):
        return self.order[addr - Addr.BATTLE_PARTY_ORDER]


def _client(order_bytes):
    c = AgentClient.__new__(AgentClient)
    c.mgba = _OrderFake(order_bytes)
    return c


def test_identity_order_is_passthrough():
    # [01 23 45]: display slot i -> party id i (battle start, no switch yet).
    c = _client([0x01, 0x23, 0x45])
    assert [c._battle_display_slot(f) for f in range(6)] == [0, 1, 2, 3, 4, 5]


def test_permuted_after_switch_maps_field_to_display():
    # After swapping slots 0 and 1: [10 23 45]. Field slot 0 now shows at display slot 1
    # (and vice versa) — the exact case where a naive field-slot cursor hit the active mon.
    c = _client([0x10, 0x23, 0x45])
    assert c._battle_display_slot(0) == 1
    assert c._battle_display_slot(1) == 0
    assert c._battle_display_slot(2) == 2      # untouched slots stay put


def test_nibble_order_matches_GetPartyIdFromBattleSlot():
    # Even display slot reads the HIGH nibble, odd reads the LOW nibble (decomp
    # GetPartyIdFromBattleSlot). [63 __ __]: display0 -> id6, display1 -> id3.
    c = _client([0x63, 0x00, 0x00])
    assert c._battle_display_slot(6) == 0
    assert c._battle_display_slot(3) == 1


def test_falls_back_to_identity_when_unmapped():
    # No display slot maps to field id 5 in this 2-mon order — fall back to the field slot.
    c = _client([0x10, 0x00, 0x00])
    assert c._battle_display_slot(5) == 5
