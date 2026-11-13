"""Hardware-free tests for game.menu.MenuDriver using a tiny scripted fake emulator.

The fake models the two things the driver depends on: a Start menu (row cursor +
action table) over the field, and a Yes/No box whose cursor clamps at the ends.
"""
from game.constants import Addr
from game.menu import MenuDriver, canonical_menu_name
from game.state import GameContext


class FakeEmu:
    """mode: 'field' | 'start' | 'yesno' | 'full' (full-screen menu)."""

    ORDER = [0, 1, 2, 3, 4, 5, 6]          # Pokedex..Exit

    def __init__(self):
        self.mode = "field"
        self.start = 0
        self.yn = 0

    # reader surface
    def detect_context(self):
        return GameContext.OVERWORLD if self.mode == "field" else GameContext.IN_MENU

    # emulator surface
    def read8(self, a):
        return {Addr.START_MENU_COUNT: len(self.ORDER),
                Addr.START_MENU_CURSOR: self.start,
                Addr.MENU_CURSOR: self.yn if self.mode == "yesno" else self.start}.get(a, 0)

    def read32(self, a):
        if a == Addr.GMAIN_CALLBACK2:
            return Addr.CB2_OVERWORLD if self.mode in ("field", "start", "yesno") else 0x08107EB9
        return 0

    def read_range(self, a, n):
        return bytes(self.ORDER[:n]) if a == Addr.START_MENU_ORDER else bytes(n)

    def tick(self, n=1):
        pass

    def tap(self, b):
        if self.mode == "field" and b == "Start":
            self.mode = "start"
        elif self.mode == "start":
            if b == "Down":
                self.start = min(self.start + 1, len(self.ORDER) - 1)
            elif b == "Up":
                self.start = max(self.start - 1, 0)
            elif b == "B":
                self.mode = "field"
            elif b == "A":
                a = self.ORDER[self.start]
                self.mode = {4: "yesno", 6: "field"}.get(a, "full")
                self.yn = 0
        elif self.mode == "yesno":
            if b == "Down":
                self.yn = min(self.yn + 1, 1)
            elif b == "Up":
                self.yn = max(self.yn - 1, 0)
            elif b == "B":
                self.mode = "start"
            elif b == "A":
                self.mode = "field" if self.yn == 0 else "start"
        elif self.mode == "full" and b == "B":
            self.mode = "start"


def _driver():
    e = FakeEmu()
    return e, MenuDriver(e, e)


def test_names():
    assert canonical_menu_name("trainer card") == "Player"
    assert canonical_menu_name("Party") == "Pokemon"
    assert canonical_menu_name("nonsense") is None


def test_open_each_full_screen_menu():
    e, d = _driver()
    for name in ("Pokemon", "Bag", "Option", "Player", "Pokedex"):
        out = d.open_menu(name)
        assert e.mode == "full", (name, out)
        assert d.close_menus() == "Back on the field."


def test_cursor_moves_up_and_down():
    e, d = _driver()
    d.open_menu("Option")                  # row 5
    assert e.start == 5
    e.mode = "start"
    d.open_menu("Pokedex")                 # back up to row 0
    assert e.start == 0


def test_save_then_yes_and_no():
    e, d = _driver()
    assert "Save prompt" in d.open_menu("Save")
    assert e.mode == "yesno"
    assert d.answer_prompt("no").startswith("Answered NO")
    assert e.mode == "start"
    d.open_menu("Save")
    e.yn = 1                               # cursor parked on NO
    assert d.answer_prompt("yes").startswith("Answered YES")
    assert e.mode == "field"


def test_exit_closes_menu():
    e, d = _driver()
    d.open_menu("Exit")
    assert e.mode == "field"


def test_unknown_menu_and_prompt_without_box():
    e, d = _driver()
    assert "Unknown menu" in d.open_menu("foo")
    assert d.answer_prompt("yes") == "No prompt is open."


def test_choice_live_restores_cursor():
    e, d = _driver()
    e.mode = "yesno"
    e.yn = 1                               # clamped end: must still detect + restore
    assert d.choice_live() is True
    assert e.yn == 1
    e.yn = 0
    assert d.choice_live() is True
    assert e.yn == 0
