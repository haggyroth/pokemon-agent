import base64
import json
import re
import time
from pathlib import Path
from openai import OpenAI
from agent.tools import TOOLS, normalize_button
from agent.history import trim_messages, strip_control_tokens
from game.memory_reader import LeafGreenReader
from game.mgba_client import MGBAClient
from memory.long_term import LongTermMemory
from knowledge.leafgreen_data import MILESTONES
from knowledge.navigation import get_map_image_path, MAP_NAMES
from config import LLM_BASE_URL, LLM_API_KEY, MODEL_NAME, TEMPERATURE, MAX_TOKENS, ENABLE_THINKING, SCREENSHOT_PATH
from rich.console import Console

console = Console()


class AgentClient:
    def __init__(self, mgba: MGBAClient, reader: LeafGreenReader, ltm: LongTermMemory):
        self.llm    = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self.mgba   = mgba
        self.reader = reader
        self.ltm    = ltm
        from game.tilemap_reader import TilemapReader
        self.tilemap = TilemapReader(mgba)   # for walk_to pathfinding
        self.messages: list[dict] = []
        self._current_opponent: str = ""  # set by set_opponent tool call
        # Cumulative LLM usage for spend tracking (#64). resp.usage may be absent
        # on some endpoints, so token totals are best-effort; call count is exact.
        self.llm_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    MAX_HISTORY = 20  # keep last ~10 user/assistant turns (text only for old turns)
    MAX_TOOL_ROUNDS = 6  # cap model tool-call rounds per decision step, then re-observe

    def set_system(self, prompt: str):
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0] = {"role": "system", "content": prompt}
        else:
            self.messages = [{"role": "system", "content": prompt}]
        # Trim only at user-turn boundaries so a tool_calls/tool-response group
        # is never split (which the API rejects with a 400).
        self.messages = trim_messages(self.messages, self.MAX_HISTORY)

    @staticmethod
    def _strip_images(content) -> str:
        """Extract only text from a (possibly multipart) message content.
        Images in older history turns are removed to keep the context window lean —
        the model only needs the current screenshot, not a history of game frames."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [part["text"] for part in content
                     if isinstance(part, dict) and part.get("type") == "text"]
            return " ".join(texts)
        return str(content)

    def _trim_image_history(self):
        """Strip image_url parts from all user messages except the most recent one.
        Called just before sending to the API. Each screenshot is ~8K tokens;
        keeping only the latest one makes the context ~10x smaller."""
        latest_user_idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i]["role"] == "user":
                latest_user_idx = i
                break
        for i, msg in enumerate(self.messages):
            if msg["role"] != "user":
                continue
            if i == latest_user_idx:
                continue  # keep images in the most recent user turn
            if isinstance(msg.get("content"), list):
                # Replace multipart content with text-only string
                self.messages[i] = {**msg,
                                     "content": self._strip_images(msg["content"])}

    def capture_screenshot(self) -> str | None:
        """Take a screenshot via mGBA and return base64-encoded PNG, or None on error."""
        try:
            self.mgba.screenshot(SCREENSHOT_PATH)
            time.sleep(0.05)
            with open(SCREENSHOT_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception:
            return None

    _map_b64_cache: dict[Path, str] = {}

    @classmethod
    def load_area_map(cls, bank: int, id: int) -> tuple[str | None, str]:
        """Return (base64 PNG | None, human map name). Caches per file path."""
        path = get_map_image_path(bank, id)
        name = MAP_NAMES.get((bank, id), f"bank={bank},id={id}")
        if path is None:
            return None, name
        cached = cls._map_b64_cache.get(path)
        if cached is None:
            with open(path, "rb") as f:
                cached = base64.b64encode(f.read()).decode()
            cls._map_b64_cache[path] = cached
        return cached, name

    # Matches a Qwen3-style <think>...</think> block (possibly multi-line)
    _THINK_RE = re.compile(r"<think>(.*?)</think>\s*", re.DOTALL)

    def _extract_response(self, msg) -> tuple[str, str]:
        """Parse a model reply into (reasoning_for_display, content_for_history).

        Qwen3 thinking models embed reasoning inside <think>...</think> tags
        in msg.content.  Storing those tags in history and replaying them to
        the API on the next turn causes a parse error (the garbage characters
        seen in the 400 error).  This method always strips the think block from
        the stored content.

        Returns
        -------
        reasoning : str
            The thinking text (for console display).  Empty string for
            non-thinking models or when no think block is present.
        clean_content : str
            msg.content with all <think>…</think> blocks removed — safe to
            store in message history and replay to the API.
        """
        raw = strip_control_tokens(msg.content or "")

        if ENABLE_THINKING:
            m = self._THINK_RE.search(raw)
            if m:
                thinking    = m.group(1).strip()
                clean       = self._THINK_RE.sub("", raw).strip()
                return thinking, clean
            # No inline tags — some LM Studio builds surface reasoning_content
            # as a separate field instead.
            extra = getattr(msg, "model_extra", {}) or {}
            reasoning = (extra.get("reasoning_content") or "").strip()
            if reasoning:
                return reasoning, raw   # raw has no tags to strip here

        return "", raw

    def step(self, observation: str, screenshot_b64: str | None = None,
             area_map_b64: str | None = None, area_map_name: str = "") -> tuple[str, list[str]]:
        """Run one decision step. Returns (reasoning_text, actions).

        If `area_map_b64` is provided, attaches it as an additional reference image
        (overhead map of the current area). Use only on area entry — re-injecting
        every tick wastes context."""
        if screenshot_b64 or area_map_b64:
            user_content: list[dict] = []
            if area_map_b64:
                label = (f"Overhead reference map of {area_map_name} (you just entered this area). "
                         f"Use it to plan your route — exits, paths, key buildings. "
                         f"Your current position is shown in the live screenshot below.")
                user_content.append({"type": "text", "text": label})
                user_content.append({"type": "image_url",
                                     "image_url": {"url": f"data:image/png;base64,{area_map_b64}"}})
            user_content.append({"type": "text", "text": observation})
            if screenshot_b64:
                user_content.append({"type": "image_url",
                                     "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})
        else:
            user_content = observation

        self.messages.append({"role": "user", "content": user_content})
        self._trim_image_history()
        actions: list[str] = []
        last_reasoning = ""

        # Bounded tool-call loop: a model can otherwise keep calling tools forever
        # within a single decision (making MAX_STEPS meaningless and acting on a
        # stale screenshot). After MAX_TOOL_ROUNDS we return control so the main
        # loop re-observes (fresh screenshot + observation).
        for _round in range(self.MAX_TOOL_ROUNDS):
            resp = self.llm.chat.completions.create(
                model=MODEL_NAME, messages=self.messages,
                tools=TOOLS, tool_choice="auto",
                temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
            )
            self.llm_calls += 1
            usage = getattr(resp, "usage", None)
            if usage:
                self.total_prompt_tokens     += getattr(usage, "prompt_tokens", 0) or 0
                self.total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            msg = resp.choices[0].message

            # Split thinking from the actual response BEFORE storing in history.
            # <think>...</think> blocks must never be replayed to the API —
            # LM Studio rejects them with a 400 parse error on subsequent turns.
            reasoning, clean_content = self._extract_response(msg)
            last_reasoning = reasoning or clean_content

            history_entry: dict = {"role": "assistant", "content": clean_content}
            if msg.tool_calls:
                history_entry["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            self.messages.append(history_entry)

            if not msg.tool_calls:
                return last_reasoning, actions

            for tc in msg.tool_calls:
                # A malformed/truncated tool call (bad JSON args, missing keys)
                # must NOT raise out of this loop: the assistant message carrying
                # tool_calls is already in history, so bailing here would orphan it
                # and every subsequent API request would 400 (tool_calls without
                # matching tool responses). Instead, turn any failure into a tool
                # response the model can see and recover from.
                try:
                    result = self._execute(tc.function.name, tc.function.arguments)
                except Exception as e:
                    result = f"Tool {tc.function.name} failed: {e}"
                console.log(f"[cyan]{tc.function.name}[/] → {str(result)[:80]}")
                self.messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": str(result)
                })
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (json.JSONDecodeError, ValueError):
                    args = {}
                if tc.function.name == "press_button":
                    actions.append(f"press:{args.get('button', '?')}")
                else:
                    actions.append(tc.function.name)

        return last_reasoning, actions

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
                # On a door/stairs tile, stepping onto it isn't enough — you have
                # to step through. Nudge each direction until the map changes.
                if (tx, ty) in warps:
                    for mv in ("Down", "Left", "Right", "Up"):
                        self.mgba.tap(mv)
                        if self.reader.read_current_map() != start_map:
                            nb, ni = self.reader.read_current_map()
                            return f"Exited through ({tx},{ty}) to map {nb}/{ni} at {self.reader.read_player_pos()}."
                        # if the nudge moved us off the warp, walk back and retry
                        if self.reader.read_player_pos() != (tx, ty):
                            break
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

    def _handle_travel_battle(self, target_name: str):
        """A battle interrupted travel. Trainer → return so the model fights it;
        wild → auto-flee and keep going (return None), unless the escape fails or HP
        is low. Returns a message to stop go_to, or None to continue travelling."""
        from game.constants import Addr
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            return (f"A trainer battle started en route to {target_name}. You can't "
                    f"flee it — win with use_move (or switch), then "
                    f"go_to({target_name!r}) again.")
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

            cur = self.reader.read_current_map()
            if cur == target_map:
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
                res = self._walk_to(arg[0], arg[1])

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
                here = MAP_NAMES.get(before, before)
                return (f"Heading to {target_name}: stuck at {here} ({res}). "
                        f"It may need something first (a cave/HM), or try again.")
        here = MAP_NAMES.get(self.reader.read_current_map(), "?")
        return f"Stopped at {here} en route to {target_name} (still travelling — call go_to again)."

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

    # Nurse Joy stands at (7,2) in the shared Pokémon Center interior, behind the
    # counter at (7,3). The player stands one tile below the counter, at (7,4), and
    # presses A facing up — the counter metatile forwards the interaction to the
    # nurse behind it. The heal is a pure dialogue: greeting → YES/NO (defaults to
    # YES) → heal → "restored". So we advance with A and confirm success by the
    # party returning to full HP.
    _NURSE_TILE = (7, 4)

    def _party_full_hp(self) -> bool:
        party = self.reader.read_party()
        return bool(party) and all(m.current_hp == m.max_hp for m in party)

    def _heal(self) -> str:
        """Heal the whole party at a Pokémon Center. Travels to the nearest one if
        not already inside, walks to Nurse Joy, and advances the heal dialogue
        until the party is at full HP. Resumable: if a wild battle/dialog interrupts
        the trip, it stops and reports so the caller can resume."""
        from game.state import GameContext
        from knowledge.map_graph import MAP_KIND
        if self._party_full_hp():
            return "Party is already at full HP — no need to heal."
        # Get inside a Pokémon Center first (resumable travel).
        if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
            res = self._go_to("Pokemon Center")
            if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
                return f"On the way to a Pokémon Center to heal: {res}"
        # Walk to the nurse's counter and face her.
        nx, ny = self._NURSE_TILE
        self._walk_to(nx, ny)
        if self.reader.read_player_pos() != (nx, ny):
            return (f"Couldn't reach Nurse Joy's counter at {self._NURSE_TILE} "
                    f"(at {self.reader.read_player_pos()}). Try walk_to it, then talk.")
        self.mgba.tap("Up")            # face the nurse across the counter
        # Advance greeting → YES/NO (YES is default) → heal → closing. A-mash and
        # watch for full HP; nudge Up before confirming so the cursor sits on YES.
        for _ in range(40):
            if self._party_full_hp():
                for _ in range(4):     # clear the "restored to full health" line
                    self.mgba.tap("A")
                    self.mgba.tick(6)
                return "Healed the party to full HP at the Pokémon Center."
            self.mgba.tap("Up")        # keep the YES/NO cursor on YES if it's up
            self.mgba.tap("A")
            self.mgba.tick(12)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return "A battle started while healing — handle it, then heal again."
        return ("Talked to Nurse Joy but couldn't confirm a full heal — "
                "try heal again, or check you're facing her at the counter.")

    # ── Poké Mart shopping ────────────────────────────────────────────────────
    # Standard marts share LAYOUT_MART: the clerk is behind a counter at (2,3); the
    # player stands in front at (2,5) (walk_to (2,4) stops there — the counter is
    # impassable) and presses A facing up to talk across it. The buy menu is driven
    # through sShopData (Addr.SHOP_DATA): the highlighted item is
    # itemList[scrollOffset + selectedRow], so we navigate the list by reading those
    # and pressing Down/Up, set quantity by watching itemPrice, and confirm each
    # purchase by the bag count rising. Menu inputs get dropped during animations, so
    # every step re-reads state and retries rather than pressing blindly.
    _MART_CLERK_APPROACH = (2, 4)

    def _buy_list_open(self) -> bool:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        return (0x08000000 <= lp < 0x0A000000
                and 0 < self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT) <= 30)

    def _buy_list_interactive(self) -> bool:
        """Probe whether the buy ITEM LIST is live and taking D-pad input: on the list
        a Down nudges selectedRow (we immediately undo it); on a text box / mid-fade /
        transition it's inert. ONLY safe when we're not on the Buy/Sell choice menu
        (i.e. after Buy is selected / after a purchase), where Down would move a
        different cursor. Used to wait out the post-purchase 'Here you go!' text."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        r0 = self.mgba.read16(SD + Addr.SHOP_SELROW)
        self.mgba.tap("Down")
        self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.SHOP_SELROW) != r0:
            self.mgba.tap("Up")            # undo the probe, back to where we were
            self.mgba.tick(8)
            return True
        return False

    def _shop_item_list(self) -> list[int]:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        n = self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT)
        if not (0x08000000 <= lp < 0x0A000000):
            return []
        return [self.mgba.read16(lp + 2 * i) for i in range(min(n, 30))]

    def _open_buy_menu(self) -> bool:
        """Talk to the clerk, then select Buy so the interactive item list is open.
        sShopData.itemList is set as soon as the Buy/Sell menu appears (before Buy is
        chosen), so 'itemList valid' only means the shop menu is up — we then select
        Buy (top option, default cursor) and let the item list fade in before the
        caller navigates (Task_BuyMenu ignores D-pad while gPaletteFade is active)."""
        self._walk_to(*self._MART_CLERK_APPROACH)   # lands at the counter-front tile
        # 1. Talk to the clerk and advance the greeting until the shop menu appears.
        shop_up = False
        for _ in range(3):
            self.mgba.tap("Up")                       # face the clerk
            for _ in range(8):
                if self._buy_list_open():
                    shop_up = True
                    break
                self.mgba.tap("A")                    # advance greeting
                self.mgba.tick(20)
            if shop_up:
                break
        if not shop_up:
            return False
        # 2. Select Buy (default top option) → enter the item list, then settle so the
        #    fade finishes and the list starts taking D-pad input.
        self.mgba.tap("A")
        if hasattr(self.mgba, "wait_until_idle"):
            self.mgba.wait_until_idle()
        self.mgba.tick(40)
        return self._buy_list_open()

    def _buy_one_item(self, item_id: int, qty: int, unit_price: int) -> int:
        """Navigate to item_id in the open list, buy `qty`, return how many were
        actually added to the bag (0 if not sold here / couldn't afford any)."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        items = self._shop_item_list()
        if item_id not in items:
            return 0
        target = items.index(item_id)
        # Move the highlight to the target row (verify each press; retry drops).
        for _ in range(40):
            cur = self.mgba.read16(SD + Addr.SHOP_SCROLL) + self.mgba.read16(SD + Addr.SHOP_SELROW)
            if cur == target:
                break
            self.mgba.tap("Down" if cur < target else "Up")
            self.mgba.tick(8)
        else:
            return 0
        before = self.reader.read_bag().get(item_id, 0)
        idle = getattr(self.mgba, "wait_until_idle", None)
        # Select the item → the "How many?" quantity box. Wait for its init to run
        # (it computes maxQuantity = money/price; 0 means it hasn't run yet).
        if idle:
            idle()
        self.mgba.tap("A")
        maxq = 0
        for _ in range(10):
            if idle:
                idle()
            self.mgba.tick(6)
            maxq = self.mgba.read16(SD + Addr.SHOP_MAXQTY)
            if maxq > 0:
                break
        if maxq <= 0:
            return 0                     # quantity box never opened
        want = max(1, min(qty, maxq))
        # Dial the quantity up from 1 to `want` (Up = +1), confirming via
        # itemPrice = unit×count. Re-read after each press; retry drops.
        for _ in range(want + 15):
            cur_n = self.mgba.read32(SD + Addr.SHOP_ITEMPRICE) // unit_price if unit_price else 1
            if cur_n >= want:
                break
            self.mgba.tap("Up")
            self.mgba.tick(6)
        # Confirm + purchase. A opens the "…you wanted N?" YES/NO box (YES default),
        # another A selects YES → the purchase runs and the bag grows. Press A until
        # the bag actually increases — self-verifying, so a dropped input just means
        # another press rather than a mis-aligned sequence. Then a SINGLE A dismisses
        # the "Here you go!" line back to the list (never press A on the list itself —
        # there it re-selects the highlighted item).
        got = 0
        for _ in range(10):
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(10)
            got = self.reader.read_bag().get(item_id, 0) - before
            if got > 0:
                break
        if got > 0:
            # Advance the "Here you go! Thank you!" text (which may still be printing)
            # until the item list is interactive again — probe first so we never press
            # A while ON the list (that would re-select the item).
            for _ in range(12):
                if self._buy_list_interactive():
                    break
                self.mgba.tap("A")
                if idle:
                    idle()
                self.mgba.tick(10)
        return max(0, got)

    def _close_buy_menu(self) -> None:
        from game.state import GameContext
        for _ in range(12):
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self.mgba.tap("B")
            self.mgba.tick(12)

    def _shop(self) -> str:
        """Restock at the Poké Mart per the badge-gated purchase policy: travel to a
        Mart if needed, open the buy menu, buy the affordable par-level list of items
        this mart sells, and leave. The model just calls shop()."""
        from knowledge.map_graph import MAP_KIND
        from knowledge.shopping import compute_shopping_list, ITEM_NAMES, ITEM_PRICES
        if MAP_KIND.get(self.reader.read_current_map()) != "mart":
            res = self._go_to("Mart")
            if MAP_KIND.get(self.reader.read_current_map()) != "mart":
                return f"On the way to a Mart to restock: {res}"
        money = self.reader.read_money()
        plan = compute_shopping_list(self.reader.read_bag(),
                                     self.ltm.data["badges_earned"], money)
        if not plan["lines"]:
            return f"Bag is already stocked (¥{money}) — nothing to buy."
        if not self._open_buy_menu():
            return ("Couldn't open the Mart buy menu — walk up to the clerk at the "
                    "counter and call shop() again.")
        sold = set(self._shop_item_list())
        bought, spent, skipped = [], 0, []
        for line in plan["lines"]:
            iid, qty = line["item_id"], line["qty"]
            if iid not in sold:
                skipped.append(ITEM_NAMES.get(iid, str(iid)))
                continue
            got = self._buy_one_item(iid, qty, ITEM_PRICES.get(iid, line["unit_price"]))
            if got > 0:
                bought.append(f"{got}× {ITEM_NAMES.get(iid, iid)}")
                spent += got * line["unit_price"]
        self._close_buy_menu()
        if not bought:
            return ("At the Mart but bought nothing (this mart doesn't sell the "
                    "recommended items, or you couldn't afford them).")
        msg = f"Bought {', '.join(bought)} (¥{spent}). Money left: ¥{self.reader.read_money()}."
        if skipped:
            msg += f" (Not sold here: {', '.join(dict.fromkeys(skipped))}.)"
        return msg

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

    def _battle_press(self, button: str) -> None:
        """A battle-reliable press: wait until the game is idle (text finished /
        menu up), then hold long enough to register. Short taps are silently
        dropped during battle animations/printing."""
        waiter = getattr(self.mgba, "wait_until_idle", None)
        if waiter:
            waiter()
        self.mgba.hold(button, 20)

    def _use_move(self, name: str) -> str:
        """Use a move by name in battle, deterministically.

        Per pokefirered HandleInputChooseMove, pressing A commits
        gMoveSelectionCursor[gActiveBattler] as the chosen move. So we: advance to
        the FIGHT move menu (detected by gBattlerControllerFuncs[0] ==
        CTRL_CHOOSE_MOVE), WRITE the target slot into the cursor, press A to
        commit, then let the turn RESOLVE (the move executes and PP decrements only
        after both sides have chosen and the turn plays out — checking sooner is
        why this looked broken before). Success = that move's PP dropped (or the
        battle ended). Single-battle scope (player = battler 0)."""
        from game.constants import Addr
        from game.state import GameContext
        party = self.reader.read_party()
        if not party:
            return "No active Pokémon."
        names = [n.lower() for n in party[0].move_names]
        if name.lower().strip() not in names:
            known = ", ".join(m for m in party[0].move_names if m)
            return f"'{name}' is not a known move. Known moves: {known}."
        slot = names.index(name.lower().strip())
        move_label = party[0].move_names[slot]
        if party[0].pp[slot] == 0:
            return f"{move_label} has no PP left — choose another move."

        for _ in range(20):
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                return "Battle is over."
            if hasattr(self.mgba, "wait_until_idle"):
                self.mgba.wait_until_idle()
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) != Addr.CTRL_CHOOSE_MOVE:
                self._battle_press("A")   # advance intro/result text, or open FIGHT
                continue
            # Move menu is up: pick the slot and commit.
            pp_before = self.reader.read_party()[0].pp[slot]
            self.mgba.write8(Addr.MOVE_CURSOR, slot)
            self.mgba.hold("A", 20)       # A edge → commits gMoveSelectionCursor
            # Let the turn resolve — advance result text until OUR move's PP drops,
            # the battle ends, or the next action menu appears.
            for _ in range(24):
                after = self.reader.read_party()
                if not after or self.reader.detect_context() != GameContext.IN_BATTLE:
                    return f"Used {move_label} (battle ended)."
                if after[0].pp[slot] < pp_before:
                    return f"Used {move_label}."
                if hasattr(self.mgba, "wait_until_idle"):
                    self.mgba.wait_until_idle()
                self.mgba.hold("A", 18)
        return f"Could not use {name} — the battle menu did not respond as expected."

    def _flee_battle(self) -> str:
        """Run from a WILD battle. Drives the action menu to RUN (writes the action
        cursor, like use_move does for the move cursor) and confirms escape by the
        battle ending. Trainer battles can't be fled. The escape roll can fail (the
        foe is faster) — this retries across turns, and reports if it can't get
        away so the caller can fight instead."""
        from game.state import GameContext
        from game.constants import Addr
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Not in a battle — nothing to flee."
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            return "Can't run from a trainer battle — win it or switch Pokémon."
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(20):
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                return "Got away safely — fled the wild battle."
            if idle:
                idle()
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) == Addr.CTRL_CHOOSE_ACTION:
                self.mgba.write8(Addr.ACTION_CURSOR, Addr.ACTION_RUN)   # select RUN
                self.mgba.hold("A", 20)                                 # commit
            else:
                self._battle_press("A")   # advance intro / result / escape text
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Got away safely — fled the wild battle."
        return ("Couldn't get away (the escape failed or the foe is faster) — "
                "try flee_battle again, or use_move to fight.")

    # ── Catching ──────────────────────────────────────────────────────────────
    def _ball_count(self) -> int:
        bag = self.reader.read_bag()
        return sum(bag.get(b, 0) for b in (1, 2, 3, 4))   # Master/Ultra/Great/Poké

    def _battle_bag_open(self) -> bool:
        """True only when the in-battle Bag is actually up: the main callback has left
        CB2_BATTLE (so it's not mid-turn) AND gBagMenuState.location ==
        ITEMMENULOCATION_BATTLE(5). (bagOpen reads 0 while open, so it's unusable.)"""
        from game.constants import Addr
        return (self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_BATTLE
                and self.mgba.read8(Addr.BAG_MENU_STATE + Addr.BAG_LOCATION_OFF) == 5)

    def _open_battle_bag(self) -> bool:
        """Open the Bag from a battle by selecting BAG (action cursor = 1), the same
        write-cursor+A method flee_battle uses for RUN. The bag hands off across a
        controller handshake; confirm it's really up via gBagMenuState, not just a
        callback change."""
        from game.constants import Addr
        from game.state import GameContext
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(30):
            if self._battle_bag_open():
                return True
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return False                 # battle ended out from under us
            if idle:
                idle()
            # The action-menu controller value VARIES by turn (0x08030611 on turn 1,
            # 0x0802e439 later), so don't gate on it. Instead: if the MOVE menu is up,
            # back out with B (never attack); otherwise write the BAG cursor and press
            # A — at the action menu that opens the bag, and on intro/result text it
            # just advances (the cursor write is ignored there).
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) == Addr.CTRL_CHOOSE_MOVE:
                self._battle_press("B")
            else:
                self.mgba.write8(Addr.ACTION_CURSOR, Addr.ACTION_BAG)
                self.mgba.hold("A", 20)
            self.mgba.tick(6)
        return self._battle_bag_open()

    def _catch(self) -> str:
        """Throw a Poké Ball at the wild Pokémon. Opens the Bag, switches to the Poké
        Balls pocket (via gBagMenuState.pocket), throws the top ball, and reports the
        outcome (caught / broke free). Weaken the foe with use_move first for a better
        rate. Can't catch trainer battles."""
        from game.constants import Addr
        from game.state import GameContext
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Not in a battle — you can only catch a wild Pokémon during its battle."
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            return "You can't catch a trainer's Pokémon — only wild ones. Win with use_move."
        balls0 = self._ball_count()
        if balls0 <= 0:
            return "No Poké Balls — buy some at a Mart with shop(), then catch."
        idle = getattr(self.mgba, "wait_until_idle", None)
        if not self._open_battle_bag():
            return "Couldn't open the Bag in battle — try catch again."
        if idle:
            idle()
        self.mgba.tick(12)
        # Switch to the Poké Balls pocket (Right cycles Items→Key Items→Balls).
        SD = Addr.BAG_MENU_STATE
        for _ in range(8):
            if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) == Addr.BAG_POCKET_BALLS:
                break
            self.mgba.tap("Right")
            if idle:
                idle()
            self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) != Addr.BAG_POCKET_BALLS:
            self._exit_battle_menus()
            return "Couldn't reach the Poké Balls pocket — try catch again."
        # Throw the ball. Selecting the ball opens a USE/CANCEL context menu (USE is
        # the default); A there throws it. Press A until a ball is actually consumed —
        # self-verifying, so a dropped input in the list→context→USE chain just means
        # another press instead of stranding us mid-menu (the old flaky spot).
        if idle:
            idle()
        for _ in range(10):
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(10)
            if self._ball_count() < balls0:
                break
        if self._ball_count() >= balls0:
            self._exit_battle_menus()
            return ("Couldn't throw the ball this time — you're back in the battle; "
                    "try catch() again.")
        # A ball was thrown. Resolve using gBattleOutcome — the ONLY reliable verdict:
        # a transient action-menu handler flickers through even a successful catch, and
        # the party count lags. == B_OUTCOME_CAUGHT the instant the catch succeeds.
        # Advance with B only — it advances capture/broke-free/Pokédex text, declines
        # the "give a nickname?" prompt, and is a harmless no-op at the action menu
        # (unlike A, which would attack). If the outcome stays 0 through the loop, the
        # mon broke free (still battling).
        OUTCOME = Addr.BATTLE_OUTCOME
        caught = False
        for _ in range(60):
            if idle:
                idle()
            self.mgba.tick(10)
            if self.mgba.read8(OUTCOME) == Addr.B_OUTCOME_CAUGHT:
                caught = True
                break
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tap("B")
        self._exit_battle_menus()            # clear any prompt; never strand in a menu
        if caught or self.mgba.read8(OUTCOME) == Addr.B_OUTCOME_CAUGHT:
            return "Gotcha! Caught the wild Pokémon — it's on your team now."
        return ("It broke free! Weaken it more with use_move (bring its HP low, or "
                "inflict a status like sleep), then catch() again.")

    def _exit_battle_menus(self) -> None:
        """Back out of any Bag / context / prompt menu until we're on solid ground
        (IN_BATTLE or OVERWORLD), so a catch attempt never strands the agent. Settles
        before each press (menu inputs drop mid-animation) and tries B then A."""
        from game.state import GameContext
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(14):
            if self.reader.detect_context() in (GameContext.IN_BATTLE, GameContext.OVERWORLD):
                return
            if idle:
                idle()
            self.mgba.tap("B")
            self.mgba.tick(8)
            if self.reader.detect_context() in (GameContext.IN_BATTLE, GameContext.OVERWORLD):
                return
            self.mgba.tap("A")
            self.mgba.tick(8)

    @staticmethod
    def _best_damaging_move(mon) -> str | None:
        """The mon's highest-power move that still has PP, or (if none has listed
        power) the first move with PP. None only if every move is out of PP."""
        from knowledge.leafgreen_data import MOVE_POWER
        best, best_pow = None, 0
        for name, pp in zip(mon.move_names, mon.pp):
            if not name or pp <= 0:
                continue
            pw = MOVE_POWER.get(name, 0)
            if pw > best_pow:
                best, best_pow = name, pw
        if best is not None:
            return best
        for name, pp in zip(mon.move_names, mon.pp):   # fallback: any move with PP
            if name and pp > 0:
                return name
        return None

    def _auto_fight(self) -> None:
        """Fight the current battle to the end with the best damaging move each turn."""
        from game.state import GameContext
        for _ in range(24):
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                return
            party = self.reader.read_party()
            if not party:
                return
            mv = self._best_damaging_move(party[0])
            if mv:
                self._use_move(mv)
            else:
                self._battle_press("A")   # no PP → Struggle / advance

    _OPPOSITE = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}

    def _wander_step(self) -> bool:
        """Take one overworld step to seek a wild encounter, PACING back and forth so
        we stay in the local (grassy) patch instead of drifting out of it. Keeps a
        heading, reverses when blocked, and rotates axis if fully boxed in. Returns
        True if a battle started."""
        from game.state import GameContext
        heading = getattr(self, "_wander_dir", "Up")
        # Try the current heading, then its reverse, then the other axis.
        order = [heading, self._OPPOSITE[heading]]
        for d in ("Up", "Down", "Left", "Right"):
            if d not in order:
                order.append(d)
        for mv in order:
            before = self.reader.read_player_pos()
            self.mgba.tap(mv)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                self._wander_dir = mv
                return True
            if self.reader.read_player_pos() != before:
                self._wander_dir = mv   # keep pacing this way until blocked
                return False
        return False

    def _nearest_grass(self) -> tuple[int, int] | None:
        """Closest tall-grass tile to the player on the current map (Manhattan), or
        None if the map has no grass. Uses the metatile-behavior reader so grind can
        route the player onto a real patch instead of guessing from encounters."""
        self.tilemap.refresh()
        tiles = self.tilemap.grass_tiles()
        if not tiles:
            return None
        px, py = self.reader.read_player_pos()
        return min(tiles, key=lambda t: abs(t[0] - px) + abs(t[1] - py))

    def _relocate_to_grass(self, exclude_current: bool = False) -> bool:
        """Deterministically travel to the nearest grass route so grind has grass to
        work with, instead of handing a 'go find grass' message back to the model
        (which it tends to ignore). Returns True if we end up somewhere with grass."""
        from knowledge.map_graph import nearest_grass
        bank, mid = self.reader.read_current_map()
        found = nearest_grass((bank, mid), exclude_current=exclude_current)
        if found is None:
            return False
        goal_map = found[0]
        if goal_map == (bank, mid):
            return self._nearest_grass() is not None
        name = MAP_NAMES.get(goal_map)
        if not name:
            return False
        self._go_to(name)                       # resumable; may stop on battle/dialog
        return self._nearest_grass() is not None

    _GRIND_HP_FLOOR = 0.35

    def _grind(self, target_level: int) -> str:
        """Grind wild battles until the lead reaches target_level. Wanders the
        current area to trigger encounters and auto-fights each with the best
        damaging move — the LLM doesn't drive each battle. Routes the player onto
        tall grass first (real metatile detection), so it works even if called from
        a path tile. Stops at the target level, when the lead's HP gets low (heal,
        then grind again), or if the current map has no grass at all."""
        from game.state import GameContext
        party = self.reader.read_party()
        if not party:
            return "No Pokémon to grind with."
        target_level = max(1, min(int(target_level), 100))
        start = party[0].level
        if start >= target_level:
            return f"Lead is already L{start} (target L{target_level}) — no need to grind."

        # No grass on this map ⇒ travel to the nearest grass route ourselves rather
        # than bouncing a "go find grass" message off the model (it ignores it).
        if self._nearest_grass() is None and not self._relocate_to_grass():
            return ("No tall grass reachable from here — go_to a route with grass "
                    "(e.g. 'Route 1'/'Route 2' or Viridian Forest), then call "
                    f"grind({target_level}) again.")

        battles = 0
        stuck_steps = 0      # overworld steps that couldn't reach grass
        relocations = 0      # deterministic grass-route relocations spent
        for _ in range(400):
            party = self.reader.read_party()
            if not party:
                break
            lvl = party[0].level
            if lvl >= target_level:
                return (f"Grinded L{start}→L{lvl} in {battles} battles. "
                        f"heal(), then head to the gym.")
            if party[0].max_hp and party[0].hp_percent < self._GRIND_HP_FLOOR:
                return (f"Grinding paused at L{lvl} — lead HP low "
                        f"({party[0].hp_percent:.0%}). Call heal(), then grind({target_level}) again.")
            ctx = self.reader.detect_context()
            if ctx == GameContext.IN_BATTLE:
                self._auto_fight()
                battles += 1
                stuck_steps = 0
            elif ctx == GameContext.OVERWORLD:
                px, py = self.reader.read_player_pos()
                if self.tilemap.is_tall_grass(px, py):
                    # On grass — pace back and forth to trigger encounters.
                    self._wander_step()
                    stuck_steps = 0
                else:
                    # Off grass — route back onto the patch (walk_to is ledge-aware,
                    # so downhill-ledge patches like Route 1's are reachable now).
                    target = self._nearest_grass()
                    if target is not None:
                        self._walk_to(*target)
                    stuck_steps += 1
                    # Can't reach any grass on this map (walled off / none) — try a
                    # deterministic relocation to another grass route before giving up.
                    if stuck_steps >= 25:
                        if relocations < 2 and self._relocate_to_grass(exclude_current=True):
                            relocations += 1
                            stuck_steps = 0
                        else:
                            return ("Couldn't reach tall grass to grind. go_to a grassy "
                                    f"route yourself, then call grind({target_level}) again.")
            else:
                self.mgba.tap("A")        # advance a dialog/transition
                self.mgba.tick()
        party = self.reader.read_party()
        lvl = party[0].level if party else start
        return f"Grinded L{start}→L{lvl} in {battles} battles. Call grind({target_level}) again to continue."

    def _execute(self, name: str, args_json: str) -> str:
        args = json.loads(args_json) if args_json else {}
        match name:
            case "press_button":
                # Clamp defensively — a model can ignore the schema's maximum.
                times = max(1, min(int(args.get("times", 1)), 10))
                # Accept compass synonyms (West→Left, N→Up, …) the model emits.
                button = normalize_button(args["button"])
                # In battle, short taps are dropped during text printing/animations —
                # the game only accepts input once idle. Use the reliable path so
                # the model's FIGHT/move/A presses actually register.
                from game.state import GameContext
                in_battle = self.reader.detect_context() == GameContext.IN_BATTLE
                for _ in range(times):
                    if in_battle:
                        self._battle_press(button)
                    else:
                        self.mgba.tap(button)
                return f"Pressed {button} × {times}"
            case "walk_to":
                return self._walk_to(int(args["x"]), int(args["y"]))
            case "go_to_map":
                return self._go_to_map(args["direction"])
            case "go_to":
                return self._go_to(args["destination"])
            case "heal":
                return self._heal()
            case "shop":
                return self._shop()
            case "challenge_leader":
                return self._challenge_leader()
            case "use_move":
                return self._use_move(args["move"])
            case "flee_battle":
                return self._flee_battle()
            case "catch":
                return self._catch()
            case "grind":
                return self._grind(int(args.get("level", 0)))
            case "read_game_state":
                s = self.reader.read_state()
                party_summary = [
                    {"slot": p.slot, "species": p.species_name or f"#{p.species_id}",
                     "level": p.level, "hp": f"{p.current_hp}/{p.max_hp}",
                     "status": p.status, "moves": [m for m in p.move_names if m]}
                    for p in s.party
                ]
                return json.dumps({
                    "context": s.context.name, "badges": s.badges,
                    "party": party_summary, "map": [s.map_bank, s.map_id],
                    "pos": [s.player_x, s.player_y],
                })
            case "save_state":
                slot = args.get("slot", 0)
                ok = self.mgba.save_state(slot)
                return f"State saved to slot {slot}." if ok else \
                       f"Save to slot {slot} FAILED (state not written)."
            case "load_state":
                slot = args.get("slot", 0)
                ok = self.mgba.load_state(slot)
                return f"State loaded from slot {slot}." if ok else \
                       f"Load from slot {slot} FAILED — no saved state in that slot yet."
            case "wait_frames":
                # Advance the emulator. The native backend only progresses when
                # frames are stepped, so a real-time sleep would leave the game
                # frozen; tick() advances both backends (native steps frames, the
                # HTTP backend sleeps while its emulator runs on its own).
                frames = int(args.get("frames", 30))
                self.mgba.tick(frames)
                return f"Waited {frames} frames."
            case "record_milestone":
                ms_name = args.get("name", "")
                if ms_name not in MILESTONES:
                    return f"Invalid milestone '{ms_name}'. Valid: {', '.join(MILESTONES)}"
                added = self.ltm.add_milestone(ms_name, args.get("note", ""))
                return f"Milestone '{ms_name}' {'recorded' if added else 'already recorded'}."
            case _:
                return f"Unknown tool: {name}"
