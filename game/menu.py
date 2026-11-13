"""Deterministic menu / sub-menu / dialogue driving (no LLM, no I/O besides the emulator).

Same pattern as the shop/battle skills: observe state, act toward a target, confirm the
OUTCOME rather than the button. Inputs are dropped during fades and text printing, so
nothing here presses a fixed button count blind.

What is directly observable (live-verified, see constants.Addr):
  * Start menu — row cursor + the row→action table      (START_MENU_*)
  * Small menus — Yes/No, Save prompt, context menus     (MENU_CURSOR, probed for liveness)
  * Dialogue    — script engine byte + game context
Full-screen list menus (Bag / Party / Pokédex) keep their cursor in heap memory, so
open_menu() opens them and the caller navigates with the D-pad + screen.
"""
from __future__ import annotations

from game.constants import Addr
from game.state import GameContext

# sStartMenuOrder action ids (pokefirered start_menu.c STARTMENU_*)
START_MENU_NAMES = {
    0: "Pokedex", 1: "Pokemon", 2: "Bag", 3: "Player", 4: "Save",
    5: "Option", 6: "Exit", 7: "Retire", 8: "Player",
}
_ALIASES = {
    "pokédex": "Pokedex", "dex": "Pokedex", "pokemon": "Pokemon", "pokémon": "Pokemon",
    "party": "Pokemon", "team": "Pokemon", "bag": "Bag", "items": "Bag",
    "player": "Player", "trainer card": "Player", "trainer": "Player", "card": "Player",
    "save": "Save", "option": "Option", "options": "Option", "settings": "Option",
    "exit": "Exit", "close": "Exit",
}


def canonical_menu_name(name: str) -> str | None:
    n = (name or "").strip().lower()
    if n in _ALIASES:
        return _ALIASES[n]
    for v in set(START_MENU_NAMES.values()):
        if v.lower() == n:
            return v
    return None


def forced_party_screen(mgba, reader) -> bool:
    """True while the game is forcing a Pokémon choice after your active mon fainted: the party
    screen is up mid-battle (gBattleOutcome still 0, an active battler whose HP is 0). B cannot
    cancel it — you must pick a healthy mon. A stale battle struct on the FIELD party menu is
    excluded: after any finished battle gBattleOutcome is non-zero."""
    if mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_PARTY_MENU:
        return False
    if mgba.read8(Addr.BATTLE_OUTCOME) != 0:
        return False
    return reader.read_active_battle_species() != 0 and reader.read_active_battle_hp() == 0


def _healthy_roster(reader) -> str:
    party = reader.read_party()
    alive = [f"{i + 1}:{p.species_name} (HP {p.current_hp}/{p.max_hp})"
             for i, p in enumerate(party) if p.current_hp > 0 and p.species_name]
    return ", ".join(alive) or "none"


class MenuDriver:
    def __init__(self, mgba, reader):
        self.mgba = mgba
        self.reader = reader

    # ── observation ──────────────────────────────────────────────────────────
    def ctx(self) -> GameContext:
        return self.reader.detect_context()

    def start_menu_items(self) -> list[str]:
        n = self.mgba.read8(Addr.START_MENU_COUNT)
        if not 0 < n <= 9:
            return []
        order = self.mgba.read_range(Addr.START_MENU_ORDER, n)
        return [START_MENU_NAMES.get(a, f"#{a}") for a in order]

    def start_cursor(self) -> int:
        return self.mgba.read8(Addr.START_MENU_CURSOR)

    def menu_cursor(self) -> int:
        return self.mgba.read8(Addr.MENU_CURSOR)

    def on_field_overlay(self) -> bool:
        """The field callback is running with a menu overlay on top (Start menu,
        Save/Yes-No prompt, context box) — as opposed to a full-screen menu screen."""
        return (self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_OVERWORLD
                and self.ctx() == GameContext.IN_MENU)

    def choice_live(self) -> bool:
        """True iff a cursor menu (Yes/No, context menu, Start menu) is taking input
        right now. Interactivity probe: nudge Down; a live menu moves its cursor, a text
        box / fade ignores it. Undone with Up. NEVER call on the free-roam overworld
        (Down would walk the player) — guarded."""
        if self.ctx() in (GameContext.OVERWORLD, GameContext.IN_BATTLE):
            return False
        before = self.menu_cursor()
        self.mgba.tap("Down"); self.mgba.tick(10)
        moved = self.menu_cursor() != before
        if moved:
            self.mgba.tap("Up"); self.mgba.tick(10)
        else:
            # At the last row Down is clamped: try Up instead to detect liveness.
            self.mgba.tap("Up"); self.mgba.tick(10)
            moved = self.menu_cursor() != before
            if moved:
                self.mgba.tap("Down"); self.mgba.tick(10)
        return moved

    def describe(self) -> str:
        """One-line menu/dialogue hint for the observation ('' on the free field)."""
        c = self.ctx()
        if c == GameContext.OVERWORLD:
            return ""
        if forced_party_screen(self.mgba, self.reader):
            return (f"FORCED switch: your Pokémon fainted — B can't cancel. Call "
                    f"switch_pokemon('<name or slot>'). Healthy: {_healthy_roster(self.reader)}.")
        if c == GameContext.DIALOG_OPEN:
            return "Dialogue box open — call advance_dialog()."
        if c == GameContext.IN_MENU and self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.NAMING_CB2:
            return "Naming screen open — call enter_name('<name>') (letters/digits)."
        if c == GameContext.IN_MENU:
            if self.on_field_overlay():
                items = self.start_menu_items()
                return (f"A field menu/prompt is open (Start-menu row "
                        f"{self.start_cursor()}/{items}; small-menu cursor "
                        f"{self.menu_cursor()}). Use open_menu / answer_prompt / "
                        f"close_menus.")
            return "A full-screen menu (Bag/Party/…) is open — D-pad+A, or close_menus()."
        return ""

    # ── primitives ───────────────────────────────────────────────────────────
    def _wait_overlay(self, ticks: int = 40) -> None:
        self.mgba.tick(ticks)

    def open_start_menu(self) -> bool:
        for _ in range(6):
            c = self.ctx()
            if c == GameContext.OVERWORLD:
                self.mgba.tap("Start"); self._wait_overlay()
            elif c == GameContext.IN_MENU and self.on_field_overlay() \
                    and self.start_menu_items() and self._start_menu_showing():
                return True
            else:
                self.close_menus()
        return self.on_field_overlay() and self._start_menu_showing()

    def _start_menu_showing(self) -> bool:
        """Start-menu overlay (vs. a Save/Yes-No box drawn over it): the start cursor
        and the generic menu cursor agree while the Start menu owns the input."""
        return self.menu_cursor() == self.start_cursor()

    def _move_start_cursor(self, target: int) -> bool:
        n = len(self.start_menu_items())
        for _ in range(n * 2 + 4):
            cur = self.start_cursor()
            if cur == target:
                return True
            self.mgba.tap("Down" if cur < target else "Up"); self.mgba.tick(12)
        return self.start_cursor() == target

    # ── skills ───────────────────────────────────────────────────────────────
    def open_menu(self, name: str) -> str:
        canon = canonical_menu_name(name)
        if canon is None:
            return (f"Unknown menu {name!r}. Start-menu entries: "
                    f"{', '.join(dict.fromkeys(START_MENU_NAMES.values()))}.")
        if self.ctx() == GameContext.IN_BATTLE:
            return "Can't open the Start menu in battle (use use_item / switch_pokemon)."
        if not self.open_start_menu():
            return "Couldn't open the Start menu (a dialogue or fade is blocking). Try advance_dialog()."
        items = self.start_menu_items()
        if canon == "Player":
            targets = [i for i, n in enumerate(items) if n == "Player"]
        else:
            targets = [i for i, n in enumerate(items) if n == canon]
        if not targets:
            return f"{canon} isn't on the Start menu right now ({items})."
        if not self._move_start_cursor(targets[0]):
            return f"Couldn't move the Start-menu cursor to {canon}."
        if canon == "Exit":
            return self.close_menus()
        self.mgba.tap("A"); self.mgba.tick(60)
        for _ in range(10):
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_OVERWORLD:
                break                   # full-screen menu took over
            if canon == "Save" and self.ctx() == GameContext.IN_MENU and not self._start_menu_showing():
                break
            self.mgba.tick(20)
        if canon == "Save":
            return ("Save prompt is up. advance_dialog() through the text, then "
                    "answer_prompt('yes') to save or 'no' to cancel.")
        if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_OVERWORLD:
            return f"Selected {canon} but no screen opened; state={self.ctx().name}."
        return (f"{canon} screen open. Navigate with Up/Down/A; B steps back; "
                f"close_menus() returns to the field.")

    def answer_prompt(self, answer: str) -> str:
        """Answer a Yes/No box. Waits (bounded) for it to take input first."""
        want_yes = str(answer).strip().lower() in ("yes", "y", "true", "1", "ok", "confirm")
        for _ in range(8):
            if self.ctx() == GameContext.OVERWORLD:
                return "No prompt is open."
            if self.choice_live():
                break
            self.mgba.tap("A") if self.ctx() == GameContext.DIALOG_OPEN else None
            self.mgba.tick(25)
        else:
            return "No Yes/No prompt is taking input. Try advance_dialog() first."
        if not want_yes:
            self.mgba.tap("B"); self.mgba.tick(40)
            return f"Answered NO. state={self.ctx().name}"
        for _ in range(4):
            if self.menu_cursor() == 0:
                break
            self.mgba.tap("Up"); self.mgba.tick(10)
        if self.menu_cursor() != 0:
            return "Couldn't put the cursor on YES; nothing pressed."
        self.mgba.tap("A"); self.mgba.tick(40)
        return f"Answered YES. state={self.ctx().name}"

    def advance_dialog(self, max_presses: int = 40) -> str:
        """Press A through dialogue until it ends or a choice/menu needs a decision."""
        pressed = 0
        for _ in range(max_presses):
            c = self.ctx()
            if c == GameContext.OVERWORLD:
                return f"Dialogue finished ({pressed} presses); back on the field."
            if c == GameContext.IN_BATTLE:
                return "A battle started — use battle tools."
            if c == GameContext.IN_MENU and self.choice_live():
                return (f"A choice/menu is waiting (cursor {self.menu_cursor()}). "
                        f"answer_prompt('yes'/'no') for Yes/No, or navigate it.")
            self.mgba.tap("A"); pressed += 1
            self.mgba.tick(25)
        return f"Dialogue still open after {pressed} presses (state={self.ctx().name})."

    def close_menus(self, max_presses: int = 14) -> str:
        """Back out of every menu/prompt/dialogue to the free field with B."""
        if forced_party_screen(self.mgba, self.reader):
            return (f"Can't close this: your Pokémon fainted and the game FORCES a replacement "
                    f"(B does nothing). Call switch_pokemon('<name or slot>'). "
                    f"Healthy: {_healthy_roster(self.reader)}.")
        stable = 0
        for i in range(max_presses):
            c = self.ctx()
            if c == GameContext.IN_BATTLE:
                return "In battle — not a menu."
            if c == GameContext.OVERWORLD:
                stable += 1
                if stable >= 2:
                    return "Back on the field."
                self.mgba.tick(15)
                continue
            stable = 0
            self.mgba.tap("B"); self.mgba.tick(30)
        return f"Still in {self.ctx().name} after {max_presses} B presses."
