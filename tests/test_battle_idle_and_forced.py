"""Battle-driver gap fixes from the overnight log: idle presses in battle, the forced
replacement screen after a faint, and mid-fight Potions."""
import pytest

from game.constants import Addr
from game.menu import forced_party_screen
from knowledge.battle import battle_idle_nudge


def test_nudge_after_three_idle_actions():
    hist = ["use_move", "press:A", "wait_frames", "read_game_state"]
    out = battle_idle_nudge(hist, "Vine Whip")
    assert "use_move('Vine Whip')" in out and "IDLE" in out


def test_no_nudge_when_a_battle_skill_is_recent():
    assert battle_idle_nudge(["press:A", "use_move", "press:A"], "Tackle") == ""
    assert battle_idle_nudge(["press:A", "press:A"], "Tackle") == ""          # too short


class _Emu:
    def __init__(self, cb2, outcome, species, hp):
        self.v = {Addr.GMAIN_CALLBACK2: cb2, Addr.BATTLE_OUTCOME: outcome}
        self.species, self.hp = species, hp

    def read32(self, a):
        return self.v.get(a, 0)

    def read8(self, a):
        return self.v.get(a, 0)


class _Reader:
    def __init__(self, species, hp):
        self.s, self.h = species, hp

    def read_active_battle_species(self):
        return self.s

    def read_active_battle_hp(self):
        return self.h


def test_forced_party_screen_detection():
    reader = _Reader(25, 0)
    assert forced_party_screen(_Emu(Addr.CB2_PARTY_MENU, 0, 25, 0), reader)
    # field party menu after a finished battle (outcome != 0, stale struct) is NOT forced
    assert not forced_party_screen(_Emu(Addr.CB2_PARTY_MENU, 1, 25, 0), reader)
    # voluntary switch screen mid-battle: active mon still alive
    assert not forced_party_screen(_Emu(Addr.CB2_PARTY_MENU, 0, 25, 7), _Reader(25, 7))
    assert not forced_party_screen(_Emu(0x08011101, 0, 25, 0), reader)        # not the party screen


def test_best_potion_policy_constants():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    assert AgentClient._POTION_HP_FLOOR < 0.5 and AgentClient._POTIONS_PER_BATTLE >= 1
    assert [i for i, _ in AgentClient._POTIONS] == [13, 22, 21]


def test_mid_fight_potion_policy():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient

    class M:
        def read16(self, a):
            return 40 if a == Addr.BATTLE_MON0_SPECIES + 0x2C else 0

    class R:
        def __init__(self, hp, items):
            self.hp, self.items = hp, items

        def read_active_battle_hp(self):
            return self.hp

        def read_active_battle_species(self):
            return 1

        def read_party(self):
            from game.state import PokemonStatus
            return [PokemonStatus(slot=0, level=5, current_hp=self.hp, max_hp=40, status="healthy",
                                  species_id=1)]

        def read_items_pocket(self):
            return self.items

    def client(hp, items):
        c = AgentClient.__new__(AgentClient)
        c.mgba, c.reader = M(), R(hp, items)
        c.drunk = []
        c._use_item = lambda name: (c.drunk.append(name) or f"Used {name} — healed")
        return c

    c = client(10, [(13, 3)])                       # 10/40 = 25% < 35%
    assert c._maybe_heal_mid_fight([]) and c.drunk == ["Potion"]
    assert not client(30, [(13, 3)])._maybe_heal_mid_fight([])        # healthy enough
    assert not client(10, [(14, 2)])._maybe_heal_mid_fight([])        # no healing item
    assert not client(10, [(13, 3)])._maybe_heal_mid_fight(["Potion"] * 3)   # per-battle cap
    assert client(10, [(22, 1), (13, 1)])._maybe_heal_mid_fight([])   # prefers cheapest first


def test_stale_battle_hp_does_not_trigger_a_potion():
    """Battle struct says low, party data says full -> do NOT open the bag (it strands the party screen)."""
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient

    class M:
        def read16(self, a):
            return 40

    class R:
        def read_active_battle_hp(self):
            return 5

        def read_active_battle_species(self):
            return 1

        def read_party(self):
            from game.state import PokemonStatus
            return [PokemonStatus(slot=0, level=5, current_hp=40, max_hp=40, status="healthy", species_id=1)]

        def read_items_pocket(self):
            return [(13, 3)]
    c = AgentClient.__new__(AgentClient)
    c.mgba, c.reader = M(), R()
    c._use_item = lambda n: (_ for _ in ()).throw(AssertionError("must not use an item"))
    assert c._maybe_heal_mid_fight([]) is False


def test_battle_advance_points_the_action_cursor_at_fight():
    """The action menu remembers its cursor: after a Bag/Potion turn it sits on BAG, so the next A
    reopened the Bag and stalled every following fight (regression from mid-fight Potions)."""
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    writes, presses = [], []

    class M:
        def read32(self, a):
            return 0x08011101          # battle callback: not a full-screen menu

        def write8(self, a, v):
            writes.append((a, v))
    c = AgentClient.__new__(AgentClient)
    c.mgba = M()
    c._battle_press = lambda b: presses.append(b)
    c._battle_advance()
    assert writes == [(Addr.ACTION_CURSOR, 0)] and presses == ["A"]

    class Menu(M):
        def read32(self, a):
            return Addr.BAG_CB2        # a full-screen menu is up: back out with B, never A
    writes.clear(); presses.clear()
    c.mgba = Menu()
    c._battle_advance()
    assert presses == ["B"] and writes == []
