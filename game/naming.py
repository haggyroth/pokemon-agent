"""Drive the Gen III naming screen (Pokémon nickname after a catch; player/rival name).

Layout/behaviour from the pokefirered decomp (src/naming_screen.c) and verified live:
  * pages cycle UPPER -> lower -> SYMBOLS with SELECT; the keyboard starts on UPPER
  * letter pages are 4 rows x 8 cols ("ABCDEF .", "GHIJKL ,", "MNOPQRS", "TUVWXYZ"), then a
    button column (x == column count): PAGE (row 0), BACK/B (rows 1-2), OK (row 3)
  * START jumps the cursor to OK; A on OK confirms; B deletes; Down/Up/Left/Right wrap
  * the typed text is a Gen III byte buffer, so every keypress is CONFIRMED by reading it back
    (no blind button counts): a wrong/dropped press is deleted and retried.
"""
from __future__ import annotations

from game.constants import GEN3_CHARSET, Addr

UPPER, LOWER, SYMBOLS = 0, 1, 2
_PAGES = {
    UPPER: ["ABCDEF .", "GHIJKL ,", "MNOPQRS", "TUVWXYZ"],
    LOWER: ["abcdef .", "ghijkl ,", "mnopqrs", "tuvwxyz"],
    SYMBOLS: ["01234", "56789", "!?"],          # (the ♂ ♀ / - … punctuation keys aren't typeable here)
}
_COLS = {UPPER: 8, LOWER: 8, SYMBOLS: 6}        # keys/row; the button column is at this index
_ENCODE = {v: k for k, v in GEN3_CHARSET.items() if v and len(v) == 1}
MAX_NAME = 10                                   # nickname length (player names are 7)


def key_pos(ch: str):
    """(page, col, row) of the key that types `ch`, or None if it can't be typed."""
    for page, rows in _PAGES.items():
        for y, row in enumerate(rows):
            x = row.find(ch)
            if x >= 0:
                return page, x, y
    return None


def typeable(name: str) -> bool:
    return all(key_pos(c) is not None for c in name)


class NamingDriver:
    def __init__(self, mgba):
        self.m = mgba
        self.page = UPPER

    # ── observation ─────────────────────────────────────────────────────────
    def active(self) -> bool:
        return self.m.read32(Addr.GMAIN_CALLBACK2) == Addr.NAMING_CB2

    def text(self) -> str:
        raw = self.m.read_range(Addr.NAMING_TEXT, MAX_NAME)
        out = []
        for b in raw:
            if b == 0xFF:
                break
            out.append(GEN3_CHARSET.get(b) or "?")
        return "".join(out)

    def _buffer_ok(self) -> bool:
        raw = self.m.read_range(Addr.NAMING_TEXT, MAX_NAME)
        return all(b == 0xFF or b in GEN3_CHARSET for b in raw)

    def cursor(self):
        return (self.m.read16(Addr.NAMING_CURSOR_X), self.m.read16(Addr.NAMING_CURSOR_Y))

    def _press(self, button: str, ticks: int = 12) -> None:
        wait = getattr(self.m, "wait_until_idle", None)
        self.m.tap(button)
        self.m.tick(ticks)
        if wait:
            pass

    # ── primitives ──────────────────────────────────────────────────────────
    def _goto_page(self, page: int) -> bool:
        for _ in range(4):
            if self.page == page:
                return True
            self._press("Select", 20)
            self.page = (self.page + 1) % 3
        return self.page == page

    def _move_to(self, tx: int, ty: int) -> bool:
        """Greedy cursor walk to key (tx, ty), re-reading the live cursor each press."""
        for _ in range(40):
            cx, cy = self.cursor()
            if (cx, cy) == (tx, ty):
                return True
            if cx != tx:
                self._press("Right" if cx < tx else "Left", 8)
            else:
                self._press("Down" if cy < ty else "Up", 8)
        return self.cursor() == (tx, ty)

    def type_char(self, ch: str) -> bool:
        """Type one character, confirming it landed in the buffer; retries/self-corrects."""
        kp = key_pos(ch)
        if kp is None:
            return False
        page, x, y = kp
        for attempt in range(4):
            before = self.text()
            if len(before) >= MAX_NAME:
                return False
            self._goto_page(page)
            if not self._move_to(x, y):
                continue
            self._press("A", 14)
            after = self.text()
            if len(after) == len(before) + 1 and after.endswith(ch):
                return True
            if len(after) > len(before):                 # wrong key landed — delete it
                self._press("B", 14)
            else:                                        # page assumption was off — resync
                self.page = (self.page + 1) % 3
        return False

    def finish(self) -> bool:
        """START jumps to OK; A confirms. True once the keyboard has closed."""
        for _ in range(6):
            if not self.active():
                return True
            self._press("Start", 16)
            self._press("A", 40)
        self.m.tick(60)
        return not self.active()

    # ── skill ───────────────────────────────────────────────────────────────
    def enter_name(self, name: str, max_len: int = MAX_NAME) -> str:
        name = (name or "").strip()[:max_len]
        if not self.active():
            return "The naming screen isn't open."
        if not name:
            return "Give a non-empty name."
        if not typeable(name):
            bad = "".join(sorted({c for c in name if key_pos(c) is None}))
            return f"Can't type {bad!r} — use letters, digits, space, '.', ',', '!' or '?'."
        if not self._buffer_ok():
            return "Couldn't read the name box (unexpected memory layout) — leaving it for B/Start."
        self.page = UPPER
        # Clear anything already typed (a default/previous name).
        for _ in range(MAX_NAME):
            if not self.text():
                break
            self._press("B", 14)
        for ch in name:
            if not self.type_char(ch):
                return f"Typed {self.text()!r} but couldn't enter {ch!r}; stopping before confirming."
        typed = self.text()
        if typed != name:
            return f"Name box reads {typed!r}, wanted {name!r}; not confirming."
        if not self.finish():
            return f"Typed {typed!r} but the screen didn't close — press Start then A."
        return f"Named it {typed!r}."
