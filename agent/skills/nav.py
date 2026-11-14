"""Navigation skills: A* walk_to, cross-map go_to / go_to_map routing,
warp crossing, the travel-battle handler, and the gym-leader challenge.
Deterministic code driving the emulator; the LLM only picks the intent.
See agent.lm_studio_client.AgentClient (which inherits NavMixin)."""

from rich.console import Console

from knowledge.navigation import MAP_NAMES

console = Console()


class NavMixin:
    # go_to stall detection: consecutive travel calls that end at the same map
    # without arriving. The "call go_to again" resume message loops the agent
    # forever when the path is story-gated (e.g. the Pewter guard shuffles it back,
    # which reads as progress), so after a few we return actionable guidance.
    _go_to_last_end = None
    _go_to_stalls = 0
    # Team-building: while travelling with a small team, go_to stops ONCE on a wild
    # new-species encounter so the model can catch it (instead of auto-fleeing past
    # everything). This flag makes that offer once-per-battle so re-issuing go_to
    # skips it rather than re-offering forever. Reset when back in the overworld.
    _travel_catch_offered = False


    def _surfing(self) -> bool:
        fn = getattr(self.reader, "is_surfing", None)
        return bool(fn()) if fn else False

    def _npc_tiles(self) -> set:
        """Grid coords of on-screen NPCs (loaded object events, excluding the
        player and invisible ones) so walk_to can path around them. Only nearby
        NPCs are loaded; far ones aren't in gObjectEvents."""
        from game.constants import Addr
        tiles = set()
        try:
            for i in range(Addr.OBJECT_EVENT_COUNT):
                b = Addr.OBJECT_EVENTS + i * Addr.OBJECT_EVENT_STRIDE
                flags0 = self.mgba.read8(b)
                if not (flags0 & 1):            # not active
                    continue
                if self.mgba.read8(b + 2) & 1:  # isPlayer
                    continue
                if (self.mgba.read8(b + 1) >> 5) & 1:  # invisible
                    continue
                x = self.mgba.read16(b + 0x10)
                y = self.mgba.read16(b + 0x12)
                x = x - 65536 if x >= 32768 else x
                y = y - 65536 if y >= 32768 else y
                tiles.add((x - Addr.OBJECT_COORD_OFFSET, y - Addr.OBJECT_COORD_OFFSET))
        except Exception as e:
            # Don't let a read hiccup crash pathfinding, but surface it — an empty
            # NPC set silently degrades walk_to into pathing THROUGH NPCs, which
            # otherwise masquerades as a mysterious "blocked" stall (#73).
            console.log(f"[dim]NPC read failed ({e}); pathing without NPC avoidance[/]")
        return tiles

    _MOVE_DELTA = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}

    def _press_on_tile(self, stand: tuple, face: str, yesno: bool = False) -> bool:
        """Walk to `stand`, face `face`, press A, then clear the result (a 'press the switch?' YES/NO,
        or just text)."""
        from game.state import GameContext
        self._in_puzzle = True                   # the walk to the tile must not start another puzzle
        try:
            for _ in range(6):                   # wild battles interrupt long walks: finish + resume
                self._walk_to(*stand)
                if self.reader.read_player_pos() == stand:
                    break
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    self._handle_travel_battle("the puzzle tile")
        finally:
            self._in_puzzle = False
        if self.reader.read_player_pos() != stand:
            return False
        self.mgba.tap(face)
        self.mgba.tick(8)
        self.mgba.tap("A")
        self.mgba.tick(30)
        if yesno or self._menus.choice_live():
            for _ in range(4):
                if self._menus.choice_live():
                    self._menus.answer_prompt("yes")
                    break
                self.mgba.tap("A")
                self.mgba.tick(20)
        self._advance_to_control(tries=20)
        return True

    def _solve_puzzle_tiles(self, start, goal, grid, w, h, npcs, blocked) -> bool:
        """The route exists only if a puzzle tile is used: a Silph Co. card-key door (face it + A; needs
        the Card Key) or a Pokémon Mansion statue switch (A -> YES flips every barrier). Tile positions
        come from the decomp (knowledge/puzzle_tiles.py); the live (EWRAM) map then shows the result.
        Returns True if it acted (caller replans)."""
        from game.pathfinding import find_path
        from knowledge.puzzle_tiles import PUZZLE_TILES
        tiles = PUZZLE_TILES.get(self.reader.read_current_map())
        if not tiles:
            return False
        step = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}

        def passable(extra):
            return lambda x, y: (x, y) == goal or (
                (grid[y][x] or (x, y) in extra) and (x, y) not in npcs and (x, y) not in blocked)

        doors = {(x, y) for x, y, k in tiles if k == "cardkey"}
        if doors:
            clusters, seen = [], set()
            for d in doors:
                if d in seen:
                    continue
                comp, stack = set(), [d]
                while stack:
                    t = stack.pop()
                    if t in comp or t not in doors:
                        continue
                    comp.add(t)
                    stack += [(t[0] + dx, t[1] + dy) for dx, dy in step.values()]
                seen |= comp
                clusters.append(comp)
            best = None
            for cl in clusters:
                pth = find_path(start, goal, passable(cl), w, h)
                if pth and (best is None or len(pth) < len(best[0])):
                    best = (pth, cl)
            if best:
                pth, cl = best
                x, y = start
                for mv in pth:
                    dx, dy = step[mv]
                    if (x + dx, y + dy) in cl:
                        return self._press_on_tile((x, y), mv)
                    x, y = x + dx, y + dy
        switches = sorted(((x, y) for x, y, k in tiles if k == "switch"),
                          key=lambda t: abs(t[0] - start[0]) + abs(t[1] - start[1]))
        for sx, sy in switches:
            for face, (dx, dy) in (("Up", (0, 1)), ("Down", (0, -1)), ("Left", (1, 0)), ("Right", (-1, 0))):
                nx, ny = sx + dx, sy + dy              # stand below the statue and face Up, etc.
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] and (
                        (nx, ny) == tuple(start) or find_path(start, (nx, ny), passable(()), w, h)):
                    return self._press_on_tile((nx, ny), face, yesno=True)
        return False

    def _engage_blocking_npc(self, start, goal, grid, w, h, npcs, blocked) -> bool:
        """The route to `goal` exists only THROUGH an NPC. Walk to the tile in front of
        the first NPC on that route, face it and press A (a trainer fights, a plain NPC
        talks / steps aside), then clear the resulting battle/dialogue. Returns True if
        it acted (caller replans), False if there's no such NPC-only route."""
        from game.pathfinding import find_path
        from game.state import GameContext
        # Which single NPC is the real chokepoint? Clear each in turn and keep the ones whose
        # removal opens a route (a 2-wide corridor needs two NPCs, but removing either frees
        # it) — choosing the shortest such route, so we don't pick an NPC that merely stands
        # on the straight-line path while a way round it exists.
        best = None
        for n in npcs:
            pth = find_path(start, goal,
                            lambda x, y, n=n: (x, y) == goal or (
                                grid[y][x] and (x, y) not in blocked
                                and ((x, y) not in npcs or (x, y) == n)),
                            w, h)
            if pth and (best is None or len(pth) < len(best[0])):
                best = (pth, n)
        if best is None:
            return False
        path, npc = best
        step = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}
        x, y = start
        for mv in path:
            dx, dy = step[mv]
            if (x + dx, y + dy) == npc:
                break
            x, y = x + dx, y + dy
        else:
            return False
        stand = (x, y)                       # tile in front of the NPC
        face = mv
        if stand != start:
            self._walk_to(*stand)
            if self.reader.read_player_pos() != stand:
                return False
        for _ in range(3):
            self.mgba.tap(face); self.mgba.tick(6)
            self.mgba.tap("A"); self.mgba.tick(20)
            if self.reader.detect_context() in (GameContext.IN_BATTLE, GameContext.DIALOG_OPEN):
                break
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            self._auto_fight()
        self._advance_to_control(tries=30)
        return True

    def _walk_to(self, tx: int, ty: int) -> str:
        """Deterministically walk the player to tile (tx, ty) on the current map
        via A* over the tilemap. Replans if a step is unexpectedly blocked and
        stops if the map changes (walked onto a warp/edge).

        Blocked-tile learning: the ROM tile passability can't see everything that
        stops a step — a solid object event, a ledge (one-way), a cut tree, an NPC
        that just moved. When a tap doesn't change our position, we mark the tile
        we tried to enter as blocked and replan AROUND it, instead of re-planning
        the identical path and stalling (the Viridian Forest / ledge stall)."""
        from game.pathfinding import find_path
        from game.state import GameContext
        # A lingering post-battle / dialog / heal-fade state (DIALOG_OPEN / TRANSITIONING
        # / IN_MENU) absorbs the D-pad, so A* taps can't move the player and walk_to
        # stalls in place — the Poké Center exit and Mt. Moon post-trainer-battle stalls
        # (a beaten trainer's "…I lost!" line, or a warp fade, left control un-returned).
        # Regain real overworld control first: A advances dialog/text and waits out a fade.
        if self.reader.detect_context() not in (GameContext.OVERWORLD, GameContext.IN_BATTLE):
            if self._advance_to_control(tries=12) == GameContext.IN_BATTLE:
                return f"A battle started before walking (at {self.reader.read_player_pos()})."
        start_map = self.reader.read_current_map()
        warps = set(self.tilemap.read_warps())
        blocked: set[tuple[int, int]] = set()   # tiles a step failed to enter
        saw_path = False                        # ever found a route this call?
        npc_tried = False                       # already engaged a blocking NPC this call
        surf_tried = False                      # already tried to start Surfing this call
        puzzle_tries = 0                        # card-key door / mansion switch uses this call
        for _attempt in range(16):
            self.tilemap.refresh()
            grid, w, h = self.tilemap.passable_grid(surf=self._surfing())
            if grid is None:
                self.mgba.tick(15)              # map still loading — settle & retry
                continue
            px, py = self.reader.read_player_pos()
            # Just after a warp the new map hasn't finished loading, so refresh()
            # can still hold the PREVIOUS map's grid — on which the player's real
            # position is out of bounds. Don't pathfind on a stale grid (that made
            # walk_to give up with a bogus "no path" the instant it entered a new
            # area, e.g. warping into Viridian Forest); let it settle and re-read.
            if not (0 <= px < w and 0 <= py < h):
                self.mgba.tick(15)
                continue
            if (px, py) == (tx, ty):
                # On a door/stairs tile, stepping onto it isn't enough — you have to
                # step through (usually Down, the exit direction). Nudge each way, but
                # WAIT for the warp: it starts a screen fade and the map changes ~30
                # frames later, so checking immediately abandons an in-progress warp
                # (which left the agent needing a second go_to to leave a Poké Center).
                if (tx, ty) in warps:
                    for mv in ("Down", "Left", "Right", "Up"):
                        self.mgba.tap(mv)
                        warped = False
                        for _ in range(12):
                            self.mgba.tick(6)
                            if self.reader.read_current_map() != start_map:
                                nb, ni = self.reader.read_current_map()
                                return (f"Exited through ({tx},{ty}) to map {nb}/{ni} "
                                        f"at {self.reader.read_player_pos()}.")
                            if self.reader.read_player_pos() != (tx, ty):
                                warped = True   # nudged off the warp — wrong direction
                                break
                        if warped:
                            break   # got nudged off; replan back onto the warp
                    else:
                        return f"Arrived at ({tx},{ty})."
                    continue   # got nudged off the warp; replan back onto it
                return f"Arrived at ({tx},{ty})."
            # Passable if floor, minus tiles occupied by loaded NPCs (route around
            # them). The goal itself is always allowed: door/stairs warp tiles sit
            # on "wall" tiles but are steppable-onto from a passable neighbour.
            npcs = self._npc_tiles()   # refresh each attempt — NPCs move
            from knowledge.puzzle_tiles import PUZZLE_TILES as _PT
            on_puzzle_map = start_map in _PT       # barrier maps: a wall goal is really blocked
            def _passable(x, y):
                if (x, y) == (tx, ty):
                    # A goal wall that is NOT a door/warp is genuinely blocked (e.g. a closed barrier):
                    # report "no path" so the puzzle/NPC solvers can act, instead of bumping it forever.
                    return bool(grid[y][x]) or (tx, ty) in warps or not on_puzzle_map
                return grid[y][x] and (x, y) not in npcs and (x, y) not in blocked
            # One-way ledges: A* may hop a ledge in its facing direction (Route 1's
            # downhill trap). Exclude any ledge a prior jump failed on (marked
            # blocked) so a mistimed hop replans instead of retrying forever.
            def _ledge(x, y):
                if (x, y) in blocked:
                    return None
                return self.tilemap.ledge_dir(x, y)
            path = find_path((px, py), (tx, ty), _passable, w, h, ledge=_ledge)
            if path is None:
                # Could be a genuinely blocked target, or a transient (an NPC on
                # the only corridor, a not-yet-settled map). Settle and retry a few
                # times rather than bailing on the first None; report "no path" only
                # if we never found one across the whole attempt budget.
                # If the ONLY thing in the way is an NPC standing in a chokepoint (a
                # trainer in Mt. Moon's 2-wide B2F corridor), go talk to it / fight it
                # rather than reporting the target unreachable forever.
                if (not self._surfing() and not surf_tried and self._party_knows(57)):
                    surf_tried = True
                    sg, _w, _h = self.tilemap.passable_grid(surf=True)
                    if sg is not None and find_path((px, py), (tx, ty), lambda x, y: sg[y][x], w, h):
                        res = self._use_hm("surf")        # only water in the way and we can Surf
                        if self._surfing():
                            continue
                        return res
                if puzzle_tries < 1 and not getattr(self, "_in_puzzle", False) and self._solve_puzzle_tiles(
                        (px, py), (tx, ty), grid, w, h, npcs, blocked):
                    puzzle_tries += 1
                    continue
                if npcs and not npc_tried and self._engage_blocking_npc(
                        (px, py), (tx, ty), grid, w, h, npcs, blocked):
                    npc_tried = True
                    continue
                self.mgba.tick(8)
                continue
            saw_path = True
            for mv in path:
                before = self.reader.read_player_pos()
                # Gen III turn-vs-step: the FIRST press of a direction you aren't
                # facing only TURNS the character (no tile change); the second
                # steps. So press up to twice before deciding the tile is blocked —
                # otherwise every corner in the path reads as an obstacle.
                for _ in range(2):
                    self.mgba.tap(mv)
                    if self.reader.read_current_map() != start_map:
                        nb, ni = self.reader.read_current_map()
                        return f"Entered a new map ({nb}/{ni}) at ({self.reader.read_player_pos()})."
                    # A wild encounter or NPC/script can interrupt mid-walk — stop
                    # and hand control back rather than mashing into a battle/dialog.
                    ctx = self.reader.detect_context()
                    if ctx == GameContext.IN_BATTLE:
                        return f"A wild battle started while walking (at {self.reader.read_player_pos()})."
                    if ctx == GameContext.DIALOG_OPEN:
                        return f"A dialog opened while walking (at {self.reader.read_player_pos()})."
                    if self.reader.read_player_pos() != before:
                        break   # stepped
                if self.reader.read_player_pos() == before:
                    # Two presses and still on the same tile → genuinely blocked
                    # (not just a turn): an obstacle the tilemap can't see (object
                    # event, ledge, cut tree). Mark it so the replan routes around
                    # it instead of retrying the identical path and stalling.
                    dx, dy = self._MOVE_DELTA.get(mv, (0, 0))
                    blocked.add((before[0] + dx, before[1] + dy))
                    break   # replan with the obstacle excluded
            else:
                continue    # full path walked without a block; loop re-checks arrival
        px, py = self.reader.read_player_pos()
        if (px, py) == (tx, ty):
            return f"Arrived at ({tx},{ty})."   # e.g. a warp target we couldn't step through
        if not saw_path:
            return (f"No walkable path from ({px},{py}) to ({tx},{ty}) — "
                    f"the target may be blocked or off this map.")
        return f"Stopped at ({px},{py}) while heading to ({tx},{ty})."

    @staticmethod
    def _facing_dir(px: int, py: int, tx: int, ty: int) -> str | None:
        """Button that turns the player from (px,py) to face the adjacent tile
        (tx,ty). None if not orthogonally adjacent."""
        if (tx, ty) == (px + 1, py): return "Right"
        if (tx, ty) == (px - 1, py): return "Left"
        if (tx, ty) == (px, py + 1): return "Down"
        if (tx, ty) == (px, py - 1): return "Up"
        return None

    def _approach_adjacent(self, tx: int, ty: int) -> bool:
        """Walk to a walkable tile orthogonally adjacent to (tx,ty) — used to stand
        next to a solid object (item ball) so we can face it and press A. Already-
        adjacent is success. Tries the nearest reachable neighbour. Returns whether
        we ended up adjacent."""
        grid, w, h = self.tilemap.passable_grid()
        if not grid:
            return False
        px, py = self.reader.read_player_pos()
        neighbours = [(tx, ty - 1), (tx, ty + 1), (tx - 1, ty), (tx + 1, ty)]
        if (px, py) in neighbours:
            return True
        cand = [(nx, ny) for nx, ny in neighbours
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx]]
        cand.sort(key=lambda t: abs(t[0] - px) + abs(t[1] - py))
        for nx, ny in cand:
            self._walk_to(nx, ny)
            if self.reader.read_player_pos() == (nx, ny):
                return True
        return False

    _EDGE = {  # direction -> (border-cell generator, step button)
        "North": ("top",    "Up"),
        "South": ("bottom", "Down"),
        "West":  ("left",   "Left"),
        "East":  ("right",  "Right"),
    }

    _DIR_ALIAS = {"n": "North", "s": "South", "e": "East", "w": "West",
                  "north": "North", "south": "South", "east": "East", "west": "West",
                  "up": "North", "down": "South", "left": "West", "right": "East"}

    @staticmethod
    def _waypoint_kind(dest: str):
        """Fuzzy-match a destination string to a waypoint kind, or None. Substring
        based so 'Viridian Pokemart', 'Poke Mart', 'Pewter City Gym' all resolve."""
        if any(k in dest for k in ("pokemon center", "poke center", "pokecenter")) \
           or dest in ("pc", "center", "heal", "healing"):
            return "pokecenter"
        if "mart" in dest or dest in ("shop", "store"):
            return "mart"
        if "gym" in dest:
            return "gym"
        return None

    def _resolve_destination(self, destination: str):
        """Resolve a go_to destination string to (target_map, name). Accepts a map
        name (exact/partial) or a waypoint (pokemon center / mart / gym, matched
        fuzzily), routing waypoints to the nearest such map from the current spot."""
        from knowledge.map_graph import nearest_of_kind, node_for
        # normalise: lowercase, strip, drop accents (é→e) so "Poké Mart" matches.
        dest = str(destination).strip().lower().replace("é", "e").replace("è", "e")
        # Region-qualify the start so routing off a split map (Route 2) is correct.
        bank, mid = self.reader.read_current_map()
        px, py = self.reader.read_player_pos()
        cur = node_for(bank, mid, px, py)
        kind = self._waypoint_kind(dest)
        if kind == "gym":
            # Story-aware: the "gym" waypoint means the NEXT gym you owe, not the
            # nearest one. Nearest routed the agent back into a just-beaten gym, or
            # to Viridian's gym (locked until 7 badges), instead of onward (#92).
            return self._resolve_next_gym()
        if kind:
            found = nearest_of_kind(cur, kind)
            if not found:
                return None, f"No {dest} reachable from here."
            target_map = found[0]
            return target_map, MAP_NAMES.get(target_map, dest.title())
        matches = [(k, v) for k, v in MAP_NAMES.items()
                   if v.lower() == dest or dest in v.lower()]
        if not matches:
            return None, f"Unknown destination '{destination}'."
        exact = [(k, v) for k, v in matches if v.lower() == dest]
        target_map, target_name = (exact or matches)[0]
        return target_map, target_name

    def _resolve_next_gym(self):
        """Resolve the 'gym' waypoint to the next gym the agent still owes — the
        first GYMS entry whose Leader isn't in gyms_beaten — routing to that gym's
        interior map. Story order (Brock→Misty→…→Giovanni) means Viridian's
        gym (locked until 7 badges) is never picked until it's actually next."""
        from knowledge.leafgreen_data import GYMS, GYM_MAP_LEADER
        beaten = set(self.ltm.data.get("gyms_beaten", []))
        nxt = next((g for g in GYMS if g["leader"] not in beaten), None)
        if nxt is None:
            return None, "All 8 Gym Leaders beaten — head to the Pokémon League (Route 22/23)."
        gym_map = next((m for m, leader in GYM_MAP_LEADER.items()
                        if leader == nxt["leader"]), None)
        if gym_map is None:
            return None, f"Don't know the map for {nxt['leader']}'s gym yet."
        return gym_map, f"{nxt['city']} Gym ({nxt['leader']})"

    # Below this lead-HP fraction, go_to stops travelling after a battle so the
    # model can heal() before walking into more wild grass (avoids a spiral to a
    # blackout, which would warp the player all the way back to a Pokémon Center).
    _TRAVEL_HP_FLOOR = 0.30

    @staticmethod
    def _is_new_team_species(party, enemy) -> bool:
        """Whether a travel wild-battle is worth stopping on to catch: the team is
        still small (<4), the wild mon is a REAL named species (not a battle-load
        garbage read, #58), it's a species not already on the team, and the catch policy
        (knowledge.catch_policy) says it's worth the training. Ball-count and
        the once-per-battle flag are checked by the caller."""
        if enemy is None or not getattr(enemy, "species_id", 0):
            return False
        name = getattr(enemy, "species_name", "") or ""
        if not name or name.startswith("#"):
            return False
        if len(party) >= 4:
            return False
        if enemy.species_id in {p.species_id for p in party}:
            return False
        lvl = getattr(enemy, "level", 0)
        if lvl:    # catch policy: don't stop for a catch that would only add grinding debt
            from knowledge.catch_policy import evaluate
            return evaluate(party, enemy.species_id, lvl).catch
        return True

    def _handle_travel_battle(self, target_name: str):
        """A battle interrupted travel. Trainer → auto-fight it (can't flee) so a
        trainer-dense dungeon is ONE go_to call, not dozens of LLM round-trips; wild →
        auto-flee and keep going (return None), unless the escape fails or HP is low.
        Returns a message to stop go_to, or None to continue travelling."""
        from game.constants import Addr
        from game.state import GameContext
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            # Auto-fight the (usually weak) travel trainer with best-move logic. Hand
            # back to the model for anything that needs judgement — a loss, a fight that
            # didn't finish on autopilot (tough trainer / a forced switch after a faint),
            # or a scraped-through win that left the lead low.
            self._auto_fight()
            outcome = self.mgba.read8(Addr.BATTLE_OUTCOME)
            party = self.reader.read_party()
            if outcome in (Addr.B_OUTCOME_LOST, Addr.B_OUTCOME_DREW) or (
                    party and all(p.current_hp == 0 for p in party)):
                # Remember WHERE we lost: a mandatory trainer on the way (the rival at Cerulean's north exit,
                # Route 22) beats an under-levelled team every time, and a retry loop of
                # lose → Pokémon Center → walk back → lose again helps nobody.
                here = getattr(self.reader, "read_current_map", lambda: (0, 0))()
                losses = self.__dict__.setdefault("_trainer_losses", {})
                losses[here] = losses.get(here, 0) + 1
                if losses[here] >= 2:
                    return (f"Lost to a trainer near {MAP_NAMES.get(here, here)} {losses[here]} times — you're "
                            f"not strong enough for the way to {target_name} yet. Do NOT retry: heal(), then "
                            "grind() to level up on a different route (or switch in a stronger Pokémon), and "
                            "come back.")
                return (f"Lost a trainer battle en route to {target_name} — heal (and "
                        f"revive any fainted mon), then go_to({target_name!r}) again.")
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                # Still fighting after a full auto pass — take over for the hard call.
                return (f"A tough trainer battle en route to {target_name} isn't resolving "
                        f"on autopilot — take over with use_move / switch_pokemon / "
                        f"use_item, then go_to({target_name!r}) again.")
            if party and party[0].max_hp and party[0].hp_percent < self._TRAVEL_HP_FLOOR:
                return (f"Beat a trainer en route to {target_name}, but your lead's HP is "
                        f"low ({party[0].hp_percent:.0%}) — call heal(), then "
                        f"go_to({target_name!r}) again.")
            return None   # won cleanly — keep travelling
        # Team-building: with a small team and Poké Balls, don't auto-flee a NEW species
        # (one not already on the team) — stop ONCE so the model can catch it and build a
        # roster. A lone/pair Pokémon can't sustain dungeons or the Elite Four. The
        # offer is once-per-battle (flag reset in the overworld), so re-issuing go_to
        # skips it and flees instead of looping.
        party = self.reader.read_party()
        if not self._travel_catch_offered and len(party) < 4 and self._ball_count() > 0:
            # The enemy struct reads garbage on the battle-load frame (#58), so settle
            # until it's a real, named species before deciding — otherwise we'd offer on
            # junk or flee the real mon before offering.
            enemy = self.reader.read_enemy_lead()
            for _ in range(5):
                if enemy and enemy.species_name and not enemy.species_name.startswith("#"):
                    break
                self.mgba.tick(6)
                enemy = self.reader.read_enemy_lead()
            if self._is_new_team_species(party, enemy):
                self._travel_catch_offered = True
                return (f"A wild {enemy.species_name} appeared en route to {target_name} "
                        f"— a NEW species for your {len(party)}-Pokémon team. To add it, "
                        f"weaken it with use_move then catch(); or call "
                        f"go_to({target_name!r}) again to skip it and keep travelling.")
        # XP on the way: when the team still has levelling to do (a lagging member, or the best Pokémon is
        # under the next gym's target) and it is healthy, fight a few of the ordinary wild battles instead of
        # running from every one — travelling shouldn't quietly replace levelling up.
        if self._travel_wants_xp():
            self._travel_fights = getattr(self, "_travel_fights", 0) + 1
            lag = self._lagging_mons()
            if lag:
                self._train_fight((lag[0][1].species_id, lag[0][1].max_hp))
            else:
                self._auto_fight()
            return None
        flee = self._flee_battle()
        if "Got away" not in flee:
            return (f"A wild battle started en route to {target_name} and the escape "
                    f"failed — fight it with use_move, then go_to({target_name!r}) again.")
        party = self.reader.read_party()
        if party and party[0].max_hp and party[0].hp_percent < self._TRAVEL_HP_FLOOR:
            return (f"Fled a wild battle en route to {target_name}, but your lead's HP "
                    f"is low ({party[0].hp_percent:.0%}) — call heal(), then "
                    f"go_to({target_name!r}) again.")
        return None   # escaped; keep travelling

    def _advance_to_control(self, tries: int = 10):
        """Press A to advance a dialog / menu / trainer-engagement into either
        overworld control or a battle. Dungeons are full of trainers whose spotting
        animation reads as IN_MENU (menu flag + fade on the field callback); without
        this, walk_to/go_to can't act and the agent is pinned. Returns the context."""
        from game.state import GameContext
        for _ in range(tries):
            ctx = self.reader.detect_context()
            if ctx in (GameContext.OVERWORLD, GameContext.IN_BATTLE):
                return ctx
            sender = getattr(self, "_send_next_mon", None)
            if sender is not None:
                try:
                    if sender():               # forced replacement after a faint: B can't cancel it
                        continue
                except Exception:
                    pass
            # A stray full-screen menu (Bag / party / summary / TM Case / map): A would USE or
            # SELECT things in it (that is how a left-open Bag drank potions in a loop) — back out.
            from game.constants import Addr
            rd = getattr(self.mgba, "read32", None)
            in_screen = bool(rd) and rd(Addr.GMAIN_CALLBACK2) in Addr.FULLSCREEN_MENU_CB2
            self.mgba.tap("B" if in_screen else "A")
            self.mgba.tick(30 if in_screen else 10)    # menu inputs drop mid-fade: give B time
        return self.reader.detect_context()

    def _register_go_to_stall(self, target_name: str, end_map) -> str | None:
        """Track consecutive go_to calls that end at the SAME map without reaching the
        target. A genuinely-progressing journey ends somewhere new (or arrives) each
        call; ending at the same map repeatedly means the path is gated (an unbeaten
        local Gym, a story event, or a missing HM). Since the resumable "call go_to
        again" message otherwise loops the agent forever — the Pewter guard shuffling
        it back to the gym reads as movement, i.e. "progress" — after 3 stalls we
        return actionable guidance instead. Returns that guidance, or None to let the
        caller send its normal resume message."""
        key = (target_name, end_map)
        if key == self._go_to_last_end:
            self._go_to_stalls += 1
        else:
            self._go_to_last_end = key
            self._go_to_stalls = 1
        if self._go_to_stalls < 3:
            return None
        self._go_to_stalls = 0            # fresh 3-strike window after we've advised
        self._go_to_last_end = None
        here = MAP_NAMES.get(end_map, "here")
        from knowledge.map_graph import DUNGEON_MAPS
        if end_map in DUNGEON_MAPS:
            # A cave maze, not a gated road — don't send the "you need an HM" message that
            # made the agent backtrack out of Mt. Moon. Tell it to keep pushing through.
            return (f"You're still inside {here} — a cave maze, NOT a gated road (no HM "
                    f"needed). Keep pushing to the far-side exit: call go_to again toward "
                    f"your destination, use_move to beat any trainer blocking the path, and "
                    f"heal() only if HP is low. Don't backtrack out the way you came in.")
        from knowledge.leafgreen_data import GYMS
        beaten = set(self.ltm.data.get("gyms_beaten", []))
        nxt = next((g for g in GYMS if g["leader"] not in beaten), None)
        if nxt and (nxt["city"] in here or here in nxt["city"]):
            return (f"Blocked: you've circled back to {here} 3× trying to reach "
                    f"{target_name}. Kanto keeps a city's road onward shut until its "
                    f"Gym Leader is beaten, and you still owe {nxt['leader']} here. Stop "
                    f"retrying that route — challenge the gym: go_to('Gym'), then "
                    f"challenge_leader().")
        return (f"Blocked reaching {target_name}: you've ended at {here} 3× with no "
                f"progress, so the way on is gated — likely a story event to finish "
                f"here or an HM you don't have yet (Cut/Surf/Strength). Do something "
                f"else (explore {here}, review objectives, or heal) rather than "
                f"repeating this route.")

    def _gate_ok(self, req) -> bool:
        """Does the player currently meet a knowledge.gates.Req?"""
        from knowledge.gates import HM_BADGE
        try:
            if req.alt_flag is not None and self.reader.read_flag(req.alt_flag):
                return True
            if req.kind == "key_item":
                return int(req.value) in self.reader.read_key_items()
            if req.kind == "badges":
                return self.reader.read_badges()[0] >= int(req.value)
            if req.kind == "hm":
                move_id, bit = HM_BADGE[req.value]
                return self._party_knows(move_id) and bool(self.reader.read_badges()[1] >> bit & 1)
        except Exception:
            return True                       # never block travel on a read hiccup
        return True

    def _respect_gates(self, cur_node, target_map, route, avoid):
        """If `route` enters a map whose story requirement isn't met (Silph Scope, Poké Flute, Tea, Surf,
        Strength, badges), look for a route that avoids it; else return (route, hint) so go_to explains
        what to get first instead of walking into a locked road. Returns (route, None) when fine."""
        from knowledge.gates import unmet_gates
        from knowledge.map_graph import route_to
        blocked = set(avoid)
        banned_maps: set = set()
        first_hint = None
        for _ in range(6):
            unmet = unmet_gates(route, self._gate_ok)
            if not unmet:
                return route, None
            idx, req = unmet[0]
            first_hint = first_hint or req.hint          # explain the SHORTEST route's gate, not a detour's
            prev = cur_node if idx == 0 else route[idx - 1][2]
            blocked.add((prev, route[idx][0], route[idx][1]))
            # Ban the WHOLE gated map: a gated city has several doors (Saffron's four gatehouses, each
            # with two mat tiles) and blocking one edge at a time ran out of retries on the same gate.
            banned_maps.add(tuple(route[idx][2][:2]))
            alt = route_to(cur_node, target_map, avoid_edges=blocked, avoid_maps=banned_maps)
            if not alt:
                return route, first_hint
            route = alt
        return route, first_hint

    # Towns with their own Pokémon Center (Pallet has none). Healing at a town's Center the first time we
    # arrive also makes it the blackout respawn point, so a loss never sends us back across the map.
    _PC_TOWNS = frozenset({(3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (3, 10)})

    def _maybe_visit_new_town(self, town, destination: str) -> None:
        """First arrival in a town with a Center: walk in and talk to Nurse Joy (heals HP+PP and sets the
        respawn point), then carry on. Skipped while already heading to a Center (no recursion)."""
        from game.state import GameContext
        town = tuple(town[:2])
        if town not in self._PC_TOWNS or "pokemon center" in str(destination).lower() \
                or getattr(self, "_in_town_visit", False):
            return
        seen = self.ltm.data.setdefault("pc_visited", [])
        key = f"{town[0]},{town[1]}"
        if key in seen:
            return
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return
        self._in_town_visit = True
        try:
            res = self._heal(force=True)
            if res.startswith(("Healed", "Party is already")):
                seen.append(key)             # only count it once we actually reached the nurse
                try:
                    self.ltm.save()
                except Exception:
                    pass
        finally:
            self._in_town_visit = False

    # Maps you can't walk to from Cerulean (see the guard in _go_to): the whole west side of Kanto start.
    _WEST_OF_ROUTE4 = frozenset({(3, 0), (3, 1), (3, 2), (3, 19), (3, 20), (3, 21), (1, 0), (1, 1), (1, 2), (1, 3)})

    _TRAVEL_FIGHTS_MAX = 4        # wild fights per go_to call taken for XP; the rest are fled

    def _travel_wants_xp(self) -> bool:
        if getattr(self, "_travel_fights", 0) >= self._TRAVEL_FIGHTS_MAX:
            return False
        try:
            party = self.reader.read_party()
            if not party or party[0].max_hp == 0 or party[0].current_hp / party[0].max_hp < 0.6:
                return False
            if any(n.level == "must" for n in self._readiness()):
                return False                      # hurt / out of PP: get away and heal instead
            foe = self.reader.read_enemy_lead()
            top = max(p.level for p in party)
            if foe and foe.level and foe.level > top + 3:
                return False                      # too dangerous for the XP
            return any(n.code in ("train", "level") for n in self._readiness())
        except Exception:
            return False

    def _readiness(self):
        """knowledge.readiness needs for the current party/bag/money/gym progress ([] on any read hiccup)."""
        from knowledge.readiness import assess
        try:
            bag = self.reader.read_bag()
            balls = sum(bag.get(b, 0) for b in (1, 2, 3, 4))
            pots = sum(q for iid, q in self.reader.read_items_pocket() if iid in (13, 22, 21))
            return assess(self.reader.read_party(), balls, pots, self.reader.read_money(),
                          self.ltm.data.get("gyms_beaten", []))
        except Exception:
            return []

    def _go_to_tool(self, destination: str, force: bool = False) -> str:
        """The model-facing go_to: travel only. It will NOT start a trip while the party is hurt or out of
        attack PP (heal first — a blackout or a wasted wild-battle spiral costs far more than the detour),
        and it reminds the model of the other fundamentals (restock, catch, train, level for the gym) so the
        convenient travel tool doesn't quietly replace them. `force` overrides the pre-flight check."""
        from game.state import GameContext
        from knowledge.readiness import blocking
        dest = str(destination).lower()
        exempt = any(k in dest for k in ("pokemon center", "poke center", "pokecenter", "mart"))
        needs = self._readiness()
        if (not force and not exempt and self.reader.detect_context() == GameContext.OVERWORLD
                and blocking(needs)):
            return ("Not travelling yet — sort this out first:\n" + "\n".join("⛔ " + n.text for n in blocking(needs))
                    + "\nThen go_to again (or pass force=true to go anyway).")
        out = self._go_to(destination)
        notes = [n.text for n in self._readiness() if n.level == "should"][:3]
        if notes:
            out += "\n(Before the next leg: " + "; ".join(notes) + ")"
        return out

    @staticmethod
    def _gym_city(gym_map):
        """(bank, id) of the outdoor city a gym interior belongs to, or None."""
        from knowledge.leafgreen_data import GYMS, GYM_MAP_LEADER
        leader = GYM_MAP_LEADER.get(tuple(gym_map[:2]))
        if not leader:
            return None
        city_name = next((g["city"] for g in GYMS if g["leader"] == leader), None)
        return next((k for k, v in MAP_NAMES.items() if v == city_name and k[0] == 3), None)

    def _go_to(self, destination: str) -> str:
        """Travel to a named map ("Pewter City", "Route 1") or waypoint ("Pokemon
        Center", "Mart", "Gym"), auto-routing across map connections AND building/
        cave warps. Re-routes from the current map after each hop.

        Wild battles en route are auto-fled so travelling through a route/forest/
        cave is one call, not dozens of round-trips (this is what makes Viridian
        Forest fast). It stops — resumably — on a TRAINER battle (can't flee), when
        the lead's HP drops low (so you can heal), if it can't escape a wild battle,
        or if a hop is blocked (e.g. a cave splits the map so the far edge isn't
        walkable)."""
        from game.state import GameContext
        from knowledge.map_graph import route_to, node_for
        target_map, target_name = self._resolve_destination(destination)
        if target_map is None:
            return target_name   # error message
        self._travel_fights = 0

        # Cerulean → the west (Pewter / Viridian / Pallet / Routes 1-3 / Mt. Moon) has NO walking route:
        # Route 4's east end is a pocket of one-way ledges, so you can come OUT of Mt. Moon into it but
        # never climb back (live-verified: no walkable path from Route 4's Cerulean side to Mt. Moon). The
        # planner's region-blind fallback used to invent a "South edge" link here and loop on
        # "Reached the South edge but could not cross".
        if self.reader.read_current_map() in ((3, 3), (3, 22)) and tuple(target_map[:2]) in self._WEST_OF_ROUTE4:
            return (f"There is no walking route from Cerulean back to {target_name}: Route 4's ledges only "
                    "go one way (out of Mt. Moon). Fly there (needs HM Fly) or load an earlier save — and "
                    "plan trips so you don't need to go back west on foot.")

        # A gym interior is often sealed from the planner's static view (Cut-tree doors: Vermilion,
        # Celadon, ...), which made it fall back to a region-blind route that marched into walls. Get to
        # the gym's CITY first (plain routing), then take the last hop from inside the city, where a
        # blocking tree is handled by the auto-Cut in the stall branch below.
        gym_city = self._gym_city(target_map)
        here = self.reader.read_current_map()
        if gym_city and here not in (gym_city, target_map):
            out = self._go_to(MAP_NAMES[gym_city])
            if not out.startswith("Arrived"):
                return out

        for _hop in range(40):   # higher budget: auto-fled battles each cost a hop
            # A trainer spotting us, post-battle text, or a stray menu leaves the
            # game non-walkable (often misreads as IN_MENU). Advance it to overworld
            # or a battle before trying to route — otherwise we're pinned in a maze.
            ctx = self.reader.detect_context()
            if ctx not in (GameContext.OVERWORLD, GameContext.IN_BATTLE):
                ctx = self._advance_to_control()
            if ctx == GameContext.IN_BATTLE:
                stop = self._handle_travel_battle(target_name)
                if stop:
                    return stop
                continue   # fled; resume travelling
            self._travel_catch_offered = False   # overworld — next battle is a fresh offer

            cur = self.reader.read_current_map()
            if cur == target_map:
                self._go_to_stalls = 0          # reached it — clear any stall streak
                self._go_to_last_end = None
                return f"Arrived at {target_name}."
            # Region-qualify the current node (Route 2's north/south halves route
            # differently) so a split map is crossed via its gate, not a sealed edge.
            px, py = self.reader.read_player_pos()
            cur_node = node_for(*cur, px, py)
            fails = self.__dict__.setdefault("_edge_fail", {})
            avoid = {k for k, n in fails.items() if n >= 2}
            route = route_to(cur_node, target_map, avoid_edges=avoid)
            if not route and avoid:
                fails.clear()          # every known path is blocked — forget and retry fresh
                route = route_to(cur_node, target_map)
            if not route:
                return (f"No route to {target_name} from {MAP_NAMES.get(cur, cur)} "
                        f"(it may be behind a locked/blocked area).")
            route, why = self._respect_gates(cur_node, target_map, route, avoid)
            if why:
                return f"Can't get to {target_name} yet: {why}"
            kind_step, arg, next_map = route[0]
            before = cur
            before_pos = (px, py)
            if kind_step == "connection":
                res = self._go_to_map(arg, dest=next_map[:2])
            else:   # warp: walk onto the door/stairs tile (walk_to steps through)
                res = self._walk_to(*self._warp_exit_tile(arg))

            # Handle a battle that interrupted this hop.
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                stop = self._handle_travel_battle(target_name)
                if stop:
                    return stop
                continue   # escaped; resume travelling

            after = self.reader.read_current_map()
            if after != before:
                fails.pop((cur_node, kind_step, arg), None)   # this edge works (again)
                self._maybe_visit_new_town(after, destination)
            if after == before:
                # Map didn't change — but in a big maze/dungeon one walk_to hop only
                # gets PART of the way to the exit warp. If the player still moved,
                # that's progress: re-route and keep going. Only give up when we're
                # truly pinned (same map AND didn't move at all this hop).
                if self.reader.read_player_pos() != before_pos:
                    continue
                # A Cut tree in the way (Vermilion Gym's door): if we can Cut, do it and carry on.
                if self._can_use_cut() and self._use_hm("cut").startswith("Used Cut"):
                    continue
                # A warp tile we're standing next to but that didn't fire: staircases can be DIRECTIONAL
                # (the Underground Path entrance only takes you when you step onto it from one side).
                # Try each approach direction once before declaring the edge dead.
                if kind_step == "warp" and self._probe_warp(self._warp_exit_tile(arg)):
                    continue
                # Learn the dead edge: after two failures of the SAME hop (a puzzle door, an
                # HM obstacle, a switch we haven't hit) route_to avoids it and picks another
                # ladder/exit — so one new puzzle doesn't need a hand-made routing fix.
                edge = (cur_node, kind_step, arg)
                fails[edge] = fails.get(edge, 0) + 1
                guidance = self._register_go_to_stall(target_name, before)
                if guidance:
                    return guidance
                here = MAP_NAMES.get(before, before)
                return (f"Heading to {target_name}: stuck at {here} ({res}). "
                        f"It may need something first (a cave/HM), or try again.")
        end_map = self.reader.read_current_map()
        guidance = self._register_go_to_stall(target_name, end_map)
        if guidance:
            return guidance
        here = MAP_NAMES.get(end_map, "?")
        return f"Stopped at {here} en route to {target_name} (still travelling — call go_to again)."

    def _can_use_cut(self) -> bool:
        try:
            return self._knows_cut() and bool(self.reader.read_badges()[1] >> 1 & 1)
        except Exception:
            return False

    def _probe_warp(self, warp: tuple[int, int]) -> bool:
        """Step onto `warp` from each side (Up/Left/Right/Down into it) until the map changes. True if
        it did. Verified live: the Underground Path (Route 5) stairs at (7,4) only fire from one side."""
        before = self.reader.read_current_map()
        wx, wy = warp
        # Already standing ON an exit mat (arrive-on-the-mat, e.g. after a gym fight): arrow warps fire
        # when you press the arrow's direction while standing on them, so try that first.
        if self.reader.read_player_pos() == (wx, wy):
            for btn in ("Down", "Left", "Right", "Up"):
                self.mgba.hold(btn, 20)
                self.mgba.tick(72)
                if self.reader.read_current_map() != before:
                    return True
                if self.reader.read_player_pos() != (wx, wy):
                    break                               # walked off the mat; fall through to approaches
        for dx, dy, btn in ((0, 1, "Up"), (1, 0, "Left"), (-1, 0, "Right"), (0, -1, "Down")):
            stand = (wx + dx, wy + dy)
            self._walk_to(*stand)
            if self.reader.read_player_pos() != stand:
                continue
            self.mgba.hold(btn, 20)
            self.mgba.tick(72)                       # let the warp fade finish
            if self.reader.read_current_map() != before:
                return True
        return False

    def _warp_exit_tile(self, warp: tuple[int, int]) -> tuple[int, int]:
        """Snap a routed warp tile to the DOOR CENTER of its doormat. A door spans
        several adjacent warp tiles but usually only the middle one actually warps —
        the map graph may list a side tile (the Poké Center exit lists (6,8) but only
        (7,8) warps), which walk_to can reach but never triggers, stalling forever.
        Returns the nearest door-center in the same cluster, or the tile unchanged."""
        from game.pathfinding import door_centers
        try:
            self.tilemap.refresh()
            centers = door_centers(self.tilemap.read_warps())
        except Exception:
            return warp
        if not centers:
            return warp
        wx, wy = warp
        cx, cy = min(centers, key=lambda c: max(abs(c[0] - wx), abs(c[1] - wy)))
        # Only snap within the same doormat cluster (Chebyshev ≤ 1); otherwise the
        # graph tile is a standalone warp we should target directly.
        return (cx, cy) if max(abs(cx - wx), abs(cy - wy)) <= 1 else warp

    def _challenge_leader(self) -> str:
        """Start the fight with the current gym's Leader. Walks to the tile below
        the Leader (GYM_LEADER_APPROACH) and TALKS to them (face up + A) — the model
        kept facing the Leader without pressing A, so this does the interaction
        deterministically. Once the battle starts, attack with use_move."""
        from game.state import GameContext
        from knowledge.map_graph import MAP_KIND
        from knowledge.leafgreen_data import GYM_LEADER_APPROACH
        cur = self.reader.read_current_map()
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "Already in a battle — attack with use_move."
        if MAP_KIND.get(cur) != "gym":
            return "You're not in a gym. go_to the gym first."
        approach = GYM_LEADER_APPROACH.get(cur)
        if not approach:
            return ("I don't have this gym's Leader position — walk_to the Leader at "
                    "the top of the gym and press A to challenge them.")
        # Under-levelled guard: a gym loss costs half your money and a long walk back.
        # Warn once per gym (a second consecutive call proceeds — the agent may judge
        # that it can win with type advantage).
        from knowledge.leafgreen_data import GYM_MAP_LEADER, GYM_ACE_LEVEL
        leader = GYM_MAP_LEADER.get(cur, "the Gym Leader")
        ace = GYM_ACE_LEVEL.get(leader)
        party = self.reader.read_party()
        top = max((p.level for p in party), default=0)
        if ace and top < ace - 2 and getattr(self, "_gym_warned", None) != cur:
            self._gym_warned = cur
            return (f"Your highest-level Pokémon is L{top} but {leader}'s ace is L{ace} — "
                    f"you will likely lose. grind({ace - 1}) first (and heal()), or call "
                    f"challenge_leader() again to fight anyway.")
        lag = self._lagging_mons(party)
        if lag and getattr(self, "_balance_warned", None) != cur:
            self._balance_warned = cur
            names = ", ".join(f"{p.species_name} L{p.level}" for _, p in lag)
            return (f"Your team is lopsided (top L{top}; lagging: {names}). Call grind() (no level) first so "
                    f"every Pokémon is within ~25% of L{top} — you'll need backups if the lead faints "
                    f"or a move gets Disabled. Or call challenge_leader() again to fight anyway.")
        if cur == (9, 6):       # Vermilion: open the electric locks first (switches read from memory)
            res = self._solve_vermilion_switches()
            if not res.startswith(("Both", "The electric")):
                return res
        self._walk_to(*approach)
        # Face the Leader (they stand just NORTH of the approach tile) and talk.
        for _ in range(5):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return f"A gym battle started (a gym trainer on the way, or {leader} himself) — attack with use_move, preferring a super-effective move. After winning, call challenge_leader() again until you hold the badge."
            self.mgba.tap("Up")     # face the Leader
            self.mgba.tap("A")      # talk → challenge
            self.mgba.tick(15)
            self._advance_to_control()   # advance the pre-battle dialogue
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "The Gym Leader battle started — attack with use_move."
        return ("Approached the Leader but the battle didn't start — make sure you're "
                f"at {approach} facing them, then press A.")

    def _go_to_map(self, direction: str, dest: tuple | None = None) -> str:
        """Cross the map connection on the given edge (walk to the edge gap, then
        step off). direction is a compass word/letter (N/S/E/W)."""
        direction = self._DIR_ALIAS.get(str(direction).strip().lower(), str(direction).title())
        if direction not in self._EDGE:
            return f"'{direction}' is not a valid edge (use North/South/East/West)."
        self.tilemap.refresh()
        conns = {c["direction"] for c in self.tilemap.read_connections()}
        if direction not in conns:
            return f"This map has no connection to the {direction} (edges: {', '.join(conns) or 'none'})."
        grid, w, h = self.tilemap.passable_grid(surf=self._surfing())
        if grid is None:
            return "Cannot read the map right now."
        side, step = self._EDGE[direction]
        if side == "top":      edge = [(x, 0) for x in range(w) if grid[0][x]]
        elif side == "bottom": edge = [(x, h - 1) for x in range(w) if grid[h - 1][x]]
        elif side == "left":   edge = [(0, y) for y in range(h) if grid[y][0]]
        else:                  edge = [(w - 1, y) for y in range(h) if grid[y][w - 1]]
        if not edge and not self._surfing() and self._party_knows(57):
            # The edge is open water: start Surf, then recompute the (now water-walkable) edge.
            self._use_hm("surf")
            if self._surfing():
                return self._go_to_map(direction)
        if not edge:
            return f"No walkable opening on the {direction} edge."
        # Only edge tiles whose neighbour exists in the destination map can cross (generated spans).
        from knowledge.map_regions import CONN_RANGES
        here = self.reader.read_current_map()
        spans = [rg for (m, d, dd), rg in CONN_RANGES.items()
                 if m == here and d == direction and (dest is None or dd == tuple(dest))]
        if spans:
            along = (lambda c: c[0]) if direction in ("North", "South") else (lambda c: c[1])
            narrowed = [c for c in edge if any(lo <= along(c) <= hi for lo, hi in spans)]
            edge = narrowed or edge
        px, py = self.reader.read_player_pos()
        # On a SPLIT map (Cerulean, Route 2/4, …) only edge tiles in the player's own region can be walked
        # to. The nearest-by-distance tile used to be in another region (Cerulean's north edge at (28,0) is a
        # separate pocket from the real road at x=22..24), so the walk failed and the "step off the edge" taps
        # below walked the player straight back through the door they had just left — the Pokémart loop.
        from knowledge.map_graph import region_at
        mine = region_at(tuple(here[:2]), px, py)
        if mine is not None:
            same = [c for c in edge if region_at(tuple(here[:2]), c[0], c[1]) == mine]
            edge = same or edge
        edge.sort(key=lambda c: abs(c[0] - px) + abs(c[1] - py))
        from game.state import GameContext
        start_map = self.reader.read_current_map()
        # Try tiles spread along the edge (the arrival tile in the next map may be blocked —
        # e.g. Cinnabar's north coast — so neighbouring tiles all fail together).
        tried: list = []
        for ex, ey in edge:
            if any(abs(ex - tx) + abs(ey - ty) <= 2 for tx, ty in tried):
                continue
            if len(tried) >= 8:
                break
            tried.append((ex, ey))
            self._walk_to(ex, ey)
            if self.reader.read_current_map() != start_map:
                nb, ni = self.reader.read_current_map()
                return f"Crossed {direction} to map {nb}/{ni} at {self.reader.read_player_pos()}."
            # A wild battle/dialog interrupted the walk to the edge — bail so we
            # don't mash the step direction into a battle/dialog menu.
            if self.reader.detect_context() != GameContext.OVERWORLD:
                return f"Interrupted while walking to the {direction} edge (context {self.reader.detect_context().name})."
            if self.reader.read_player_pos() != (ex, ey):
                continue         # never reached this edge tile: don't mash the step key from wherever we are
            for _ in range(5):   # step off the edge into the connected map
                self.mgba.tap(step)
                if self.reader.read_current_map() != start_map:
                    nb, ni = self.reader.read_current_map()
                    return f"Crossed {direction} to map {nb}/{ni} at {self.reader.read_player_pos()}."
        if (not self._surfing() and self._party_knows(57)
                and not getattr(self, "_surf_retry", False)):
            # The land edge tiles lead into open water (a shore, not a crossing): Surf, retry.
            self._surf_retry = True
            try:
                self._use_hm("surf")
                if self._surfing():
                    return self._go_to_map(direction, dest)
            finally:
                self._surf_retry = False
        return f"Reached the {direction} edge but could not cross."
