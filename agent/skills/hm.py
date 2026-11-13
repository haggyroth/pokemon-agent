"""HM field use: Surf (water), Cut (trees), Rock Smash (rocks), Strength (boulders).

All four are "face the thing, press A, answer YES" in FRLG: the game itself checks that a party
Pokémon knows the move and that the badge is held, and says so if not. The driver does the
approach/facing, answers the prompt (MenuDriver) and CONFIRMS the outcome (surfing flag set /
the object despawned), like every other skill. Teaching an HM (TM Case) and Fly / Flash (party
sub-menus) are not covered here.
"""
from game.constants import Addr
from game.state import GameContext

# name -> (move id, display name)
_HMS = {
    "surf": (57, "Surf"), "cut": (15, "Cut"),
    "rock smash": (249, "Rock Smash"), "rocksmash": (249, "Rock Smash"), "smash": (249, "Rock Smash"),
    "strength": (70, "Strength"),
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
            return (f"No Pokémon in your party knows {label}. Teach it first (HM from the story, "
                    f"taught via the TM Case — not automated yet).")
        return self._surf() if label == "Surf" else self._use_on_object(label)

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
