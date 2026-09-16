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
        for _attempt in range(16):
            self.tilemap.refresh()
            grid, w, h = self.tilemap.passable_grid()
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
            def _passable(x, y):
                if (x, y) == (tx, ty):
                    return True
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
        garbage read, #58), and it's a species not already on the team. Ball-count and
        the once-per-battle flag are checked by the caller."""
        if enemy is None or not getattr(enemy, "species_id", 0):
            return False
        name = getattr(enemy, "species_name", "") or ""
        if not name or name.startswith("#"):
            return False
        if len(party) >= 4:
            return False
        return enemy.species_id not in {p.species_id for p in party}

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
            self.mgba.tap("A")
            self.mgba.tick(10)
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
            route = route_to(cur_node, target_map)
            if not route:
                return (f"No route to {target_name} from {MAP_NAMES.get(cur, cur)} "
                        f"(it may be behind a locked/blocked area).")
            kind_step, arg, next_map = route[0]
            before = cur
            before_pos = (px, py)
            if kind_step == "connection":
                res = self._go_to_map(arg)
            else:   # warp: walk onto the door/stairs tile (walk_to steps through)
                res = self._walk_to(*self._warp_exit_tile(arg))

            # Handle a battle that interrupted this hop.
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                stop = self._handle_travel_battle(target_name)
                if stop:
                    return stop
                continue   # escaped; resume travelling

            after = self.reader.read_current_map()
            if after == before:
                # Map didn't change — but in a big maze/dungeon one walk_to hop only
                # gets PART of the way to the exit warp. If the player still moved,
                # that's progress: re-route and keep going. Only give up when we're
                # truly pinned (same map AND didn't move at all this hop).
                if self.reader.read_player_pos() != before_pos:
                    continue
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
        self._walk_to(*approach)
        # Face the Leader (they stand just NORTH of the approach tile) and talk.
        for _ in range(5):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return "The Gym Leader battle started — attack with use_move (Vine Whip vs Brock)."
            self.mgba.tap("Up")     # face the Leader
            self.mgba.tap("A")      # talk → challenge
            self.mgba.tick(15)
            self._advance_to_control()   # advance the pre-battle dialogue
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "The Gym Leader battle started — attack with use_move."
        return ("Approached the Leader but the battle didn't start — make sure you're "
                f"at {approach} facing them, then press A.")

    def _go_to_map(self, direction: str) -> str:
        """Cross the map connection on the given edge (walk to the edge gap, then
        step off). direction is a compass word/letter (N/S/E/W)."""
        direction = self._DIR_ALIAS.get(str(direction).strip().lower(), str(direction).title())
        if direction not in self._EDGE:
            return f"'{direction}' is not a valid edge (use North/South/East/West)."
        self.tilemap.refresh()
        conns = {c["direction"] for c in self.tilemap.read_connections()}
        if direction not in conns:
            return f"This map has no connection to the {direction} (edges: {', '.join(conns) or 'none'})."
        grid, w, h = self.tilemap.passable_grid()
        if grid is None:
            return "Cannot read the map right now."
        side, step = self._EDGE[direction]
        if side == "top":      edge = [(x, 0) for x in range(w) if grid[0][x]]
        elif side == "bottom": edge = [(x, h - 1) for x in range(w) if grid[h - 1][x]]
        elif side == "left":   edge = [(0, y) for y in range(h) if grid[y][0]]
        else:                  edge = [(w - 1, y) for y in range(h) if grid[y][w - 1]]
        if not edge:
            return f"No walkable opening on the {direction} edge."
        px, py = self.reader.read_player_pos()
        edge.sort(key=lambda c: abs(c[0] - px) + abs(c[1] - py))
        from game.state import GameContext
        start_map = self.reader.read_current_map()
        for ex, ey in edge[:4]:
            self._walk_to(ex, ey)
            if self.reader.read_current_map() != start_map:
                nb, ni = self.reader.read_current_map()
                return f"Crossed {direction} to map {nb}/{ni} at {self.reader.read_player_pos()}."
            # A wild battle/dialog interrupted the walk to the edge — bail so we
            # don't mash the step direction into a battle/dialog menu.
            if self.reader.detect_context() != GameContext.OVERWORLD:
                return f"Interrupted while walking to the {direction} edge (context {self.reader.detect_context().name})."
            for _ in range(5):   # step off the edge into the connected map
                self.mgba.tap(step)
                if self.reader.read_current_map() != start_map:
                    nb, ni = self.reader.read_current_map()
                    return f"Crossed {direction} to map {nb}/{ni} at {self.reader.read_player_pos()}."
        return f"Reached the {direction} edge but could not cross."
