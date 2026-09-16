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
from config import (LLM_BASE_URL, LLM_API_KEY, MODEL_NAME, TEMPERATURE, MAX_TOKENS,
                    ENABLE_THINKING, SCREENSHOT_PATH, LLM_TIMEOUT)
from rich.console import Console
from agent.skills.nav import NavMixin
from agent.skills.overworld import OverworldMixin
from agent.skills.battle import BattleMixin
from agent.skills.movelearn import MoveLearnMixin
from agent.skills.evolution import EvolutionMixin

console = Console()


class AgentClient(NavMixin, OverworldMixin, BattleMixin, MoveLearnMixin, EvolutionMixin):

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

        checkpoint = len(self.messages)     # roll back to here if this step fails (#69)
        self.messages.append({"role": "user", "content": user_content})
        self._trim_image_history()
        actions: list[str] = []
        last_reasoning = ""

        # Bounded tool-call loop: a model can otherwise keep calling tools forever
        # within a single decision (making MAX_STEPS meaningless and acting on a
        # stale screenshot). After MAX_TOOL_ROUNDS we return control so the main
        # loop re-observes (fresh screenshot + observation).
        for _round in range(self.MAX_TOOL_ROUNDS):
            try:
                resp = self.llm.chat.completions.create(
                    model=MODEL_NAME, messages=self.messages,
                    tools=TOOLS, tool_choice="auto",
                    temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                    timeout=LLM_TIMEOUT or None,   # bound a single call (see config)
                )
            except Exception:
                # A failed LLM call (e.g. an LLM_TIMEOUT) must not leave a dangling user
                # turn — or a half-finished tool_calls group — in history: the API would
                # reject the next request, and each retried step would pile on another,
                # inflating token cost. Roll back everything this step appended (#69).
                del self.messages[checkpoint:]
                raise
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
            case "pick_up_items":
                return self._pick_up_items()
            case "use_item":
                return self._use_item(args["item"])
            case "switch_pokemon":
                return self._switch_pokemon(str(args["target"]))
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
                # Clamp defensively — a model can ignore the schema's maximum and
                # a huge/negative frame count would freeze the run (HTTP) or fast-
                # forward the game thousands of steps (native).
                frames = max(0, min(int(args.get("frames", 30)), 120))
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
