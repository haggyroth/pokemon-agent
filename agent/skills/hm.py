"""HM field use: Surf (water), Cut (trees), Rock Smash (rocks), Strength (boulders).

All four are "face the thing, press A, answer YES" in FRLG: the game itself checks that a party
Pokémon knows the move and that the badge is held, and says so if not. The driver does the
approach/facing, answers the prompt (MenuDriver) and CONFIRMS the outcome (surfing flag set /
the object despawned), like every other skill. Teaching an HM is teach_move (agent/skills/tmhm.py); Fly / Flash (party
sub-menus) are not covered here.
"""
from game.constants import Addr
from game.state import GameContext

MOVE_LABEL = {148: 'Flash', 19: 'Fly'}

# name -> (move id, display name)
_HMS = {
    "surf": (57, "Surf"), "cut": (15, "Cut"),
    "rock smash": (249, "Rock Smash"), "rocksmash": (249, "Rock Smash"), "smash": (249, "Rock Smash"),
    "strength": (70, "Strength"),
    "flash": (148, "Flash"), "fly": (19, "Fly"),
}
# Moves that appear in the party sub-menu, in the game's own order (party_menu.h sFieldMoves).
_FIELD_MOVE_IDS = (148, 15, 19, 70, 57, 249, 127, 100, 91, 208, 135, 230)
# Fly destinations: name -> ((map bank, id), region-map grid cell (x, y), world-map flag).
FLY_SPOTS = {
    "pallet town": ((3, 0), (4, 11), 0x890), "viridian city": ((3, 1), (4, 8), 0x891),
    "pewter city": ((3, 2), (4, 4), 0x892), "cerulean city": ((3, 3), (14, 3), 0x893),
    "lavender town": ((3, 4), (18, 6), 0x894), "vermilion city": ((3, 5), (14, 9), 0x895),
    "celadon city": ((3, 6), (11, 6), 0x896), "fuchsia city": ((3, 7), (12, 12), 0x897),
    "cinnabar island": ((3, 8), (4, 14), 0x898), "indigo plateau": ((3, 9), (2, 3), 0x899),
    "saffron city": ((3, 10), (14, 6), 0x89A),
}
_OBJECT_GFX = {"Cut": Addr.OBJ_GFX_CUT_TREE, "Rock Smash": Addr.OBJ_GFX_ROCK_SMASH,
               "Strength": Addr.OBJ_GFX_BOULDER}


class HMMixin:

    def _party_knows(self, move_id: int) -> bool:
        try:
            return any(move_id in (p.move_ids or []) for p in self.reader.read_party())
        except Exception:
            return False

    def _answer_field_yes(self) -> bool:
        """Answer the field Yes/No ('Would you like to use X?') with YES, then clear the text."""
        for _ in range(8):
            if self._menus.choice_live():
                self._menus.answer_prompt("yes")
                self._advance_to_control(tries=30)
                return True
            self.mgba.tap("A")
            self.mgba.tick(20)
        return False

    def _use_hm(self, name: str) -> str:
        key = str(name).strip().lower()
        if key not in _HMS:
            return (f"'{name}' isn't supported. Field HMs here: Surf, Cut, Rock Smash, Strength "
                    f"(Flash/Fly use the party menu and aren't automated yet).")
        move_id, label = _HMS[key]
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Only usable while walking around the overworld."
        if not self._party_knows(move_id):
            return (f"No Pokémon in your party knows {label}. Teach it with teach_move("
                    f"'{label}') (needs the HM item and the TM Case).")
        if label == "Flash":
            return self._flash()
        if label == "Fly":
            return "Use fly_to('<town>') — Fly needs a destination."
        return self._surf() if label == "Surf" else self._use_on_object(label)

    # ── party sub-menu field moves (Flash, Fly) ─────────────────────────────
    def _party_field_move(self, move_id: int, who: str = "") -> str | None:
        """Start -> Pokémon -> a mon that knows `move_id` -> its sub-menu entry for the move -> A.
        The sub-menu is [SUMMARY, <field moves in move-slot order>, SWITCH, ITEM, CANCEL], so the entry
        index is computed, then reached by the live cursor. Returns an error string or None."""
        party = self.reader.read_party()
        slots = [i for i, p in enumerate(party) if move_id in (p.move_ids or [])]
        if who:
            t = self._resolve_party_target(who, party)
            slots = [t] if t is not None and t in slots else []
        if not slots:
            return f"No Pokémon in your party knows {MOVE_LABEL.get(move_id, move_id)}."
        slot = slots[0]
        res = self._menus.open_menu("Pokemon")
        if "screen open" not in res:
            return f"Couldn't open the party screen ({res})"
        self.mgba.tick(40)
        for _ in range(10):
            cur = self.mgba.read8(Addr.PARTY_FIELD_SLOT)
            if cur == slot:
                break
            self.mgba.tap("Down" if cur < slot else "Up")
            self.mgba.tick(14)
        if self.mgba.read8(Addr.PARTY_FIELD_SLOT) != slot:
            self._menus.close_menus()
            return "Couldn't move the party cursor."
        self.mgba.tap("A")
        self.mgba.tick(50)
        moves = list(party[slot].move_ids)
        idx = 1 + sum(1 for m in moves[:moves.index(move_id)] if m in _FIELD_MOVE_IDS)
        for _ in range(12):
            cur = self.mgba.read8(Addr.MENU_CURSOR)
            if cur == idx:
                break
            self.mgba.tap("Down" if cur < idx else "Up")
            self.mgba.tick(14)
        if self.mgba.read8(Addr.MENU_CURSOR) != idx:
            self._menus.close_menus()
            return "Couldn't reach the move in the Pokémon's menu."
        self.mgba.tap("A")
        self.mgba.tick(60)
        return None

    def _flash(self) -> str:
        if self.reader.read_flag(Addr.FLAG_SYS_FLASH_ACTIVE):
            return "Flash is already lighting the cave."
        err = self._party_field_move(148)
        if err:
            return err
        lit = self.reader.read_flag(Addr.FLAG_SYS_FLASH_ACTIVE)
        for _ in range(30):                          # the light-up fade/animation takes a moment
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tick(20)
            self._advance_to_control(tries=2)
        if not lit:
            self._menus.close_menus()
        if lit:
            return "Used Flash — the cave is lit up."
        return "Flash had no effect here (it only works in a dark cave like Rock Tunnel)."

    def _fly_to(self, town: str) -> str:
        key = str(town).strip().lower()
        key = key if key in FLY_SPOTS else next((k for k in FLY_SPOTS if key and key in k), "")
        if not key:
            return f"Can't fly to {town!r}. Choose from: {', '.join(k.title() for k in FLY_SPOTS)}."
        (dbank, did), (cx, cy), flag = FLY_SPOTS[key]
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Fly only from the overworld."
        if not self.reader.read_flag(flag):
            return f"You haven't visited {key.title()} yet — Fly only goes to towns you've been to."
        if self.reader.read_current_map() == (dbank, did):
            return f"Already in {key.title()}."
        err = self._party_field_move(19)
        if err:
            return err
        for _ in range(40):                          # the map screen fades in
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.REGIONMAP_CB2:
                break
            self.mgba.tick(15)
        if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.REGIONMAP_CB2:
            self._menus.close_menus()
            return "Fly couldn't be used here (indoors / not allowed) — go outside first."
        self.mgba.tick(40)
        # Clamp to the top-left corner, read its pixel origin, then step to the target cell.
        for _ in range(23):
            self.mgba.hold("Left", 2); self.mgba.tick(8)
        for _ in range(15):
            self.mgba.hold("Up", 2); self.mgba.tick(8)
        px0 = self.mgba.read16(Addr.FLYMAP_CURSOR_X) & 0x1FF
        py0 = self.mgba.read16(Addr.FLYMAP_CURSOR_Y) & 0xFF
        for _ in range(80):
            cell = (((self.mgba.read16(Addr.FLYMAP_CURSOR_X) & 0x1FF) - px0) // 8,
                    ((self.mgba.read16(Addr.FLYMAP_CURSOR_Y) & 0xFF) - py0) // 8)
            if cell == (cx, cy):
                break
            btn = "Right" if cell[0] < cx else "Left" if cell[0] > cx else "Down" if cell[1] < cy else "Up"
            self.mgba.hold(btn, 2)
            self.mgba.tick(12)
        if cell != (cx, cy):
            self._menus.close_menus()
            return f"Couldn't steer the map cursor to {key.title()} (ended at {cell})."
        self.mgba.tap("A")
        for _ in range(60):                          # fade out, warp, fade in
            self.mgba.tick(15)
            if self.reader.read_current_map() == (dbank, did) and self.mgba.read32(
                    Addr.GMAIN_CALLBACK2) == Addr.CB2_OVERWORLD:
                break
        self._advance_to_control(tries=20)
        if self.reader.read_current_map() == (dbank, did):
            return f"Flew to {key.title()}."
        self._menus.close_menus()
        return f"Selected {key.title()} but didn't arrive (map {self.reader.read_current_map()})."

    # ── Surf ────────────────────────────────────────────────────────────────
    def _surf(self) -> str:
        if self._surfing():
            return "Already surfing."
        t = self.tilemap
        t.refresh()
        grid, w, h = t.passable_grid()
        if grid is None:
            return "Can't read the map right now."
        px, py = self.reader.read_player_pos()
        spots = []                                   # (shore tile, face dir toward water)
        for y in range(h):
            for x in range(w):
                if not grid[y][x]:
                    continue
                for face, (dx, dy) in (("Down", (0, 1)), ("Up", (0, -1)),
                                       ("Right", (1, 0)), ("Left", (-1, 0))):
                    ti = t.read_tile(x + dx, y + dy)
                    if ti is not None and ti.is_water and t.metatile_behavior(x + dx, y + dy) != 0x13:
                        spots.append((abs(x - px) + abs(y - py), (x, y), face))
                        break
        for _d, (sx, sy), face in sorted(spots)[:6]:
            self._walk_to(sx, sy)
            if self.reader.read_player_pos() != (sx, sy):
                continue
            for _ in range(3):
                self.mgba.tap(face)                  # turn to the water (the first press only turns)
                self.mgba.tick(8)
                self.mgba.tap("A")
                self.mgba.tick(40)
                if self._answer_field_yes():
                    break
            if self._surfing():
                return (f"Surfing! You can now cross water with walk_to / go_to_map "
                        f"(from {(sx, sy)}). Stepping onto land ends it.")
        return "Couldn't start Surf — no reachable shore with water to face (or the prompt didn't appear)."

    # ── Cut / Rock Smash / Strength ─────────────────────────────────────────
    def _use_on_object(self, label: str) -> str:
        gfx = _OBJECT_GFX[label]
        for _ in range(4):
            self.tilemap.refresh()
            _g, gw, gh = self.tilemap.passable_grid()
            # Objects of the NEIGHBOURING map are loaded too (their coords fall outside this map's
            # grid) — they can't be reached from here, so only consider ones on this map.
            objs = [o for o in self.reader.read_objects_by_gfx([gfx])
                    if 0 <= o[0] < gw and 0 <= o[1] < gh]
            if not objs:
                return (f"No {'tree' if label == 'Cut' else 'rock' if label == 'Rock Smash' else 'boulder'} "
                        f"in view to use {label} on.")
            px, py = self.reader.read_player_pos()
            ox, oy = min(objs, key=lambda o: abs(o[0] - px) + abs(o[1] - py))
            if not self._approach_adjacent(ox, oy):
                return f"Couldn't reach the {label} target at ({ox},{oy})."
            px, py = self.reader.read_player_pos()
            face = self._facing_dir(px, py, ox, oy)
            if not face:
                continue
            for _ in range(3):
                self.mgba.tap(face)
                self.mgba.tick(8)
                self.mgba.tap("A")
                self.mgba.tick(40)
                if self._answer_field_yes():
                    break
            self._advance_to_control(tries=20)
            if label == "Strength":
                return "Used Strength — boulders can be pushed now (walk into them)."
            if (ox, oy) not in self.reader.read_objects_by_gfx([gfx]):
                return f"Used {label}: cleared the obstacle at ({ox},{oy})."
        return f"Tried {label} but the obstacle is still there."
