"""S.S. Anne / Cut + Vermilion Gym switch plumbing (#185 item 5c)."""
from types import SimpleNamespace

import pytest

from game.constants import Addr
from game.memory_reader import LeafGreenReader


def test_trash_can_ids_map_to_the_5x3_grid():
    pytest.importorskip("openai")
    from agent.skills.quests import trash_can_tile
    assert trash_can_tile(1) == (1, 10) and trash_can_tile(5) == (9, 10)
    assert trash_can_tile(6) == (1, 12) and trash_can_tile(12) == (3, 14) and trash_can_tile(15) == (9, 14)
    assert len({trash_can_tile(i) for i in range(1, 16)}) == 15


def test_read_var_decodes_the_temp_vars_from_savebock1():
    sb1 = 0x02025000
    mem = {Addr.SAVEBLOCK1_PTR: sb1, sb1 + Addr.VARS_OFFSET: 12, sb1 + Addr.VARS_OFFSET + 2: 11}

    class _C:
        def read32(self, a): return mem.get(a, 0)
        def read16(self, a): return mem.get(a, 0)
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _C()
    assert (r.read_var(0x4000), r.read_var(0x4001)) == (12, 11)


def _client(**kw):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(**kw)
    return c


def test_get_cut_needs_the_ticket_and_is_idempotent():
    mon = SimpleNamespace(move_ids=[15, 0, 0, 0])
    c = _client(read_party=lambda: [mon], detect_context=lambda: None)
    assert "already knows Cut" in c._get_cut()
    c = _client(read_party=lambda: [SimpleNamespace(move_ids=[33])], detect_context=lambda: None,
                read_flag=lambda n: False, read_key_items=lambda: [])
    assert "get_ss_ticket" in c._get_cut()


def test_unreadable_switch_vars_fall_back_to_a_message():
    c = _client(read_flag=lambda n: False, read_var=lambda n: 0)
    assert "Couldn't read the trash-can switches" in c._solve_vermilion_switches()


def test_locks_already_open_short_circuits():
    c = _client(read_flag=lambda n: True)
    assert "already open" in c._solve_vermilion_switches()


def test_cut_gate_hint_points_at_get_cut():
    from knowledge.gates import MAP_GATES
    assert "get_cut()" in MAP_GATES[(9, 6)][0].hint
