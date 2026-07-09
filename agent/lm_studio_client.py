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
                result = self._execute(tc.function.name, tc.function.arguments)
                console.log(f"[cyan]{tc.function.name}[/] → {str(result)[:80]}")
                self.messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": str(result)
                })
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
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
        except Exception:
            pass
        return tiles

    def _walk_to(self, tx: int, ty: int) -> str:
        """Deterministically walk the player to tile (tx, ty) on the current map
        via A* over the tilemap. Replans if a step is unexpectedly blocked (an
        NPC moved) and stops if the map changes (walked onto a warp/edge)."""
        from game.pathfinding import find_path
        from game.state import GameContext
        start_map = self.reader.read_current_map()
        warps = set(self.tilemap.read_warps())
        for _attempt in range(8):
            self.tilemap.refresh()
            grid, w, h = self.tilemap.passable_grid()
            if grid is None:
                return "Cannot read the map to path-find right now."
            px, py = self.reader.read_player_pos()
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
                return grid[y][x] and (x, y) not in npcs
            path = find_path((px, py), (tx, ty), _passable, w, h)
            if path is None:
                return (f"No walkable path from ({px},{py}) to ({tx},{ty}) — "
                        f"the target may be blocked or off this map.")
            for mv in path:
                before = self.reader.read_player_pos()
                self.mgba.tap(mv)
                if self.reader.read_current_map() != start_map:
                    nb, ni = self.reader.read_current_map()
                    return f"Entered a new map ({nb}/{ni}) at ({self.reader.read_player_pos()})."
                # A wild encounter or NPC/script can interrupt mid-walk — stop and
                # hand control back so the agent deals with it, rather than mashing
                # movement into a battle/dialog.
                ctx = self.reader.detect_context()
                if ctx == GameContext.IN_BATTLE:
                    return f"A wild battle started while walking (at {self.reader.read_player_pos()})."
                if ctx == GameContext.DIALOG_OPEN:
                    return f"A dialog opened while walking (at {self.reader.read_player_pos()})."
                if self.reader.read_player_pos() == before:
                    break   # unexpectedly blocked → replan
            else:
                continue    # full path walked without a block; loop re-checks arrival
        px, py = self.reader.read_player_pos()
        if (px, py) == (tx, ty):
            return f"Arrived at ({tx},{ty})."   # e.g. a warp target we couldn't step through
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
        from knowledge.map_graph import nearest_of_kind
        # normalise: lowercase, strip, drop accents (é→e) so "Poké Mart" matches.
        dest = str(destination).strip().lower().replace("é", "e").replace("è", "e")
        cur = self.reader.read_current_map()
        kind = self._waypoint_kind(dest)
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

    def _go_to(self, destination: str) -> str:
        """Travel to a named map ("Pewter City", "Route 1") or waypoint ("Pokemon
        Center", "Mart", "Gym"), auto-routing across map connections AND building/
        cave warps. Re-routes from the current map after each hop (robust to
        interrupts). Stops — resumably — on a wild battle/dialog, or if a hop is
        blocked (e.g. a cave splits the map so the far edge isn't walkable)."""
        from game.state import GameContext
        from knowledge.map_graph import route_to
        target_map, target_name = self._resolve_destination(destination)
        if target_map is None:
            return target_name   # error message

        for _hop in range(16):
            cur = self.reader.read_current_map()
            if cur == target_map:
                return f"Arrived at {target_name}."
            route = route_to(cur, target_map)
            if not route:
                return (f"No route to {target_name} from {MAP_NAMES.get(cur, cur)} "
                        f"(it may be behind a locked/blocked area).")
            kind_step, arg, next_map = route[0]
            before = cur
            if kind_step == "connection":
                res = self._go_to_map(arg)
            else:   # warp: walk onto the door/stairs tile (walk_to steps through)
                res = self._walk_to(arg[0], arg[1])
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return f"A wild battle started en route to {target_name}. Handle it, then go_to({target_name!r}) again."
            after = self.reader.read_current_map()
            if after == before:
                here = MAP_NAMES.get(before, before)
                return (f"Heading to {target_name}: stuck at {here} ({res}). "
                        f"It may need something first (a cave/HM), or try again.")
        here = MAP_NAMES.get(self.reader.read_current_map(), "?")
        return f"Stopped at {here} en route to {target_name}."

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
            case "use_move":
                return self._use_move(args["move"])
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
                self.mgba.save_state(args.get("slot", 0))
                return "State saved."
            case "load_state":
                self.mgba.load_state(args.get("slot", 0))
                return "State loaded."
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
