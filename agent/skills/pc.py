"""Pokémon storage (PC boxes): open the PC in a Pokémon Center, deposit / withdraw through the storage screen,
log off. Boxes are READ from memory (gPokemonStoragePtr); every change is DRIVEN through the real menus and
verified against memory afterwards.

Live-found addresses (this ROM): gPokemonStoragePtr = 0x03005010 (→ PokemonStorage: currentBox u8, then 14
boxes × 30 BoxPokemon × 80 bytes), storage-screen cursor area 0x02039820 (0 box grid, 1 party panel, 2 box title,
3 top buttons) and cursor position 0x02039821 (grid 0-29 = col + 6·row; buttons 0 = PARTY POKéMON, 1 = CLOSE BOX;
party panel = slot).
"""
from game.constants import Addr
from game.state import GameContext

STORAGE_CB2 = 0x0808CD99                 # gMain.callback2 while the storage screen is up
AREA_ADDR, POS_ADDR = 0x02039820, 0x02039821
AREA_GRID, AREA_PARTY, AREA_TITLE, AREA_BUTTONS = 0, 1, 2, 3
PC_TILE_BEHAVIOR = 0x83                  # MB_PC


class PCMixin:
    # ── reading ──────────────────────────────────────────────────────────────
    def _storage_base(self) -> int:
        ptr = self.mgba.read32(Addr.POKEMON_STORAGE_PTR)
        return ptr if 0x02000000 <= ptr < 0x02040000 else 0

    # ── driving ──────────────────────────────────────────────────────────────
    def _pc_tile(self):
        self.tilemap.refresh()
        w, h = 40, 40
        for y in range(h):
            for x in range(w):
                if self.tilemap.metatile_behavior(x, y) == PC_TILE_BEHAVIOR:
                    return x, y
        return None

    def _in_storage(self) -> bool:
        return self.mgba.read32(Addr.GMAIN_CALLBACK2) == STORAGE_CB2

    def _storage_cursor(self) -> tuple[int, int]:
        return self.mgba.read8(AREA_ADDR), self.mgba.read8(POS_ADDR)

    def _mcur(self) -> int:
        return self.mgba.read8(Addr.MENU_CURSOR)

    def _press(self, button: str, ticks: int = 50) -> None:
        self.mgba.hold(button, 8)
        self.mgba.tick(ticks)

    def _open_pc(self, mode: int = 1) -> str | None:
        """Walk to the Center's PC and open SOMEONE'S PC → the storage screen in `mode` (0 WITHDRAW, 1 DEPOSIT,
        2 MOVE). The PC has two list menus: 'Which PC?' (first entry = SOMEONE'S PC) and the storage system menu
        (WITHDRAW / DEPOSIT / MOVE POKéMON / MOVE ITEMS / SEE YA!). Text in between is advanced with A. None on
        success, else an error message."""
        from knowledge.map_graph import MAP_KIND
        if self._in_storage():
            return None
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Open the PC from the overworld inside a Pokémon Center."
        if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
            res = self._go_to("Pokemon Center")
            if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
                return f"Not at a Pokémon Center yet: {res}"
        pc = self._pc_tile()
        if pc is None:
            return "Couldn't find the PC in this Pokémon Center."
        px, py = pc
        self._walk_to(px, py + 1)
        if self.reader.read_player_pos() != (px, py + 1):
            return f"Couldn't reach the PC at ({px},{py})."
        self.mgba.tap("Up")
        self.mgba.tick(8)
        menus_seen, was_live = 0, False
        for _ in range(60):
            if self._in_storage():
                break
            live = self._menus.choice_live()
            if live and not was_live:
                menus_seen += 1
                if menus_seen == 2:                         # the storage-system menu: pick the mode
                    for _k in range(6):
                        if self._mcur() == mode:
                            break
                        self._press("Down" if self._mcur() < mode else "Up", 30)
                    if self._mcur() != mode:
                        return "Couldn't steer the PC menu to the requested mode."
            was_live = live
            self.mgba.hold("A", 8)
            self.mgba.tick(70)
        self.mgba.tick(90)
        return None if self._in_storage() else "The PC didn't open the storage screen."

    def _pc_close(self) -> None:
        """Leave the storage screen and log off: B → 'Continue BOX operations?' → B (leaves) → the 'Which PC?' menu →
        B (LOG OFF) → back to the overworld."""
        for _ in range(8):
            if not self._in_storage():
                break
            self._press("B", 80)
        for _ in range(6):
            if self.reader.detect_context() == GameContext.OVERWORLD and not self._menus.choice_live():
                break
            self._press("B", 60)
        self._advance_to_control(tries=20)

    # ── cursor helpers (storage screen) ───────────────────────────────────────────
    def _grid_goto(self, pos: int) -> bool:
        """Move the box-grid cursor to slot `pos` (0-29 = col + 6·row), verifying every step."""
        for _ in range(4):                                    # get into the grid
            if self._storage_cursor()[0] == AREA_GRID:
                break
            self._press("Down", 50)
        if self._storage_cursor()[0] != AREA_GRID:
            return False
        for _ in range(40):
            area, cur = self._storage_cursor()
            if area != AREA_GRID:
                return False
            if cur == pos:
                return True
            cc, cr, tc, tr = cur % 6, cur // 6, pos % 6, pos // 6
            if cr != tr:
                self._press("Down" if cr < tr else "Up", 40)
            else:
                self._press("Right" if cc < tc else "Left", 40)
        return self._storage_cursor() == (AREA_GRID, pos)

    def _goto_box(self, box: int) -> bool:
        """Change the displayed box (cursor on the box-title row, Left/Right) until currentBox == box."""
        cur = self.reader.read_current_box()
        if cur is None:
            return False
        if cur == box:
            return True
        for _ in range(4):
            if self._storage_cursor()[0] == AREA_TITLE:
                break
            self._press("Up", 50)
        if self._storage_cursor()[0] != AREA_TITLE:
            return False
        for _ in range(16):
            cur = self.reader.read_current_box()
            if cur == box:
                return True
            fwd = (box - cur) % 14
            self._press("Right" if fwd <= 7 else "Left", 50)
        return self.reader.read_current_box() == box

    # ── the skills ───────────────────────────────────────────────────────────────────
    def _pc_boxes(self) -> str:
        boxes = self.reader.read_boxes()
        if not boxes:
            return "Your PC boxes are empty."
        by_box: dict = {}
        for m in boxes:
            by_box.setdefault(m["box"], []).append(m)
        lines = []
        for b in sorted(by_box):
            items = ", ".join(f"[{m['slot']}] {m['nickname'] or m['species_name']} ({m['species_name']} L{m['level']})"
                              for m in by_box[b])
            lines.append(f"Box {b + 1}: {items}")
        return "\n".join(lines)

    def _pc_deposit(self, who: str) -> str:
        party = self.reader.read_party()
        i = self._resolve_party_target(str(who), party)
        if i is None:
            return f"Couldn't find {who!r} in your party: {', '.join(p.species_name for p in party)}."
        mon = party[i]
        name = mon.nickname or mon.species_name
        if len(party) < 2:
            return "That's your only Pokémon — the PC won't take your last one."
        if not any(j != i and p.current_hp > 0 for j, p in enumerate(party)):
            return f"{name} is your only Pokémon able to battle — the PC refuses to take it. Heal the others first."
        err = self._open_pc(mode=1)
        if err:
            return err
        try:
            for _ in range(8):
                if self._storage_cursor() == (AREA_PARTY, i):
                    break
                self._press("Down" if self._storage_cursor()[1] < i else "Up", 50)
            if self._storage_cursor() != (AREA_PARTY, i):
                return "Couldn't place the cursor on that party member."
            self._press("A", 70)                              # context menu: STORE first
            self._press("A", 100)                             # → "Deposit in which BOX?"
            self._press("A", 130)                             # confirm the current box
            for _ in range(12):
                if len(self.reader.read_party()) == len(party) - 1:
                    break
                self.mgba.tick(30)
        finally:
            self._pc_close()
        if len(self.reader.read_party()) != len(party) - 1:
            return f"The deposit of {name} didn't go through — try pc_deposit again."
        return f"Deposited {name} into the PC. Party now: {self._party_names()}."

    def _pc_withdraw(self, who: str) -> str:
        boxes = self.reader.read_boxes()
        key = str(who).strip().lower()
        pick = None
        if ":" in key and key.replace(":", "").replace(" ", "").isdigit():
            b, sl = (int(x) for x in key.split(":"))
            pick = next((m for m in boxes if m["box"] == b - 1 and m["slot"] == sl), None)
        else:
            cands = [m for m in boxes if key in (m["nickname"].lower(), m["species_name"].lower())] or \
                    [m for m in boxes if key and (key in m["nickname"].lower() or key in m["species_name"].lower())]
            pick = max(cands, key=lambda m: m["level"], default=None)
        if pick is None:
            return f"No Pokémon matching {who!r} in the PC. {self._pc_boxes()}"
        party = self.reader.read_party()
        if len(party) >= 6:
            return "Your party is full (6) — pc_deposit one first, or use pc_swap."
        name = pick["nickname"] or pick["species_name"]
        err = self._open_pc(mode=0)
        if err:
            return err
        try:
            if not self._goto_box(pick["box"]):
                return "Couldn't switch to that box."
            if not self._grid_goto(pick["slot"]):
                return "Couldn't place the cursor on that slot."
            self._press("A", 70)                              # context menu: WITHDRAW first
            self._press("A", 130)
            for _ in range(12):
                if len(self.reader.read_party()) == len(party) + 1:
                    break
                self.mgba.tick(30)
        finally:
            self._pc_close()
        if len(self.reader.read_party()) != len(party) + 1:
            return f"The withdrawal of {name} didn't go through — try pc_withdraw again."
        return f"Withdrew {name} (L{pick['level']}) from Box {pick['box'] + 1}. Party now: {self._party_names()}."

    def _pc_swap(self, party_mon: str, box_mon: str) -> str:
        """Put a party member into the PC and take a boxed one out in its place. The boxed Pokémon is validated
        first so a typo can't leave the party short a member."""
        key = str(box_mon).strip().lower()
        known = self.reader.read_boxes()
        if not any(key in (m["nickname"].lower(), m["species_name"].lower())
                   or key in m["nickname"].lower() or key in m["species_name"].lower()
                   or key == f"{m['box'] + 1}:{m['slot']}" for m in known):
            return f"No Pokémon matching {box_mon!r} in the PC, so nothing was deposited. {self._pc_boxes()}"
        out = self._pc_deposit(party_mon)
        if not out.startswith("Deposited"):
            return out
        res = self._pc_withdraw(box_mon)
        return out + " " + res
