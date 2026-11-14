"""A rule-based stand-in for the LLM: drives the real skills end to end with NO model calls.

`FakeLLM` is a drop-in for the OpenAI client the AgentClient talks to. Each time the agent asks for a
decision it asks `ScriptedPolicy.decide()` for one tool call (from live emulator state); on the follow-up
round (after the tool result) it replies with plain text so control returns to the main loop, exactly
like a real model that has nothing more to call. Everything else — observations, rewards, ltm
bookkeeping, run logging, checkpoints, the watchdog — is the real run_episode.

Use it to find where the skill chain stalls (item 5 of #185) without spending a token:
    python tools/scripted_run.py --goal badges:2 --max-steps 300
"""
from __future__ import annotations

import json
from types import SimpleNamespace

# Lead level wanted before each gym, and the town to head for once that badge is in hand.
GYM_PLAN = [
    {"leader": "Brock", "city": "Pewter City", "lead_level": 14},
    {"leader": "Misty", "city": "Cerulean City", "lead_level": 21},
    {"leader": "Lt. Surge", "city": "Vermilion City", "lead_level": 26},
]


class ScriptedPolicy:
    def __init__(self, rt):
        self.rt = rt
        self.c, self.r, self.m, self.ltm = rt.client, rt.reader, rt.mgba, rt.ltm
        self.history: list[str] = []

    # ── helpers ─────────────────────────────────────────────────────────────
    def _next_gym(self):
        beaten = set(self.ltm.data.get("gyms_beaten", []))
        return next((g for g in GYM_PLAN if g["leader"] not in beaten), None)

    def _battle(self):
        from game.constants import Addr
        from game.menu import forced_party_screen
        from knowledge.party import can_attack
        if forced_party_screen(self.m, self.r):
            party = self.r.read_party()
            ok = [i for i, p in enumerate(party) if p.current_hp > 0]
            return "switch_pokemon", {"target": str((ok or [0])[0] + 1)}
        trainer = bool(self.m.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER)
        _ids, names, pp, _d, _t = self.c._active_moves_view()
        atk, dfn = self.c._battle_types()
        mv = self.c._best_damaging_move(names, pp, atk, dfn)
        if mv:
            return "use_move", {"move": mv}
        if not any(n and q > 0 for n, q in zip(names, pp)):
            return "use_move", {"move": "Struggle"}
        party = self.r.read_party()
        active = self.r.read_active_battle_species()
        backups = [i for i, p in enumerate(party) if p.species_id != active and p.current_hp > 0 and can_attack(p)]
        if backups:
            return "switch_pokemon", {"target": str(backups[0] + 1)}
        if not trainer:
            return "flee_battle", {}
        return "use_move", {"move": next(n for n, q in zip(names, pp) if n and q > 0)}

    # ── the decision ────────────────────────────────────────────────────────
    def decide(self):
        from game.state import GameContext
        ctx = self.r.detect_context()
        if ctx == GameContext.IN_BATTLE:
            return self._battle()
        if ctx == GameContext.IN_MENU:
            return "close_menus", {}
        if ctx == GameContext.DIALOG_OPEN:
            return "advance_dialog", {}
        if ctx != GameContext.OVERWORLD:
            return "wait_frames", {"frames": 30}
        party = self.r.read_party()
        if not party:
            return "wait_frames", {"frames": 30}
        # Recover first: hurt, or attacks out of PP.
        if self.c._party_needs_heal() and any(p.current_hp < 0.6 * p.max_hp or not _has_pp(p) for p in party):
            return "heal", {}
        gym = self._next_gym()
        if gym is None:
            return "wait_frames", {"frames": 30}
        lead = party[0]
        if lead.level < gym["lead_level"]:
            return "grind", {"level": gym["lead_level"]}
        # Past Misty the story needs Bill's SS Anne ticket before Cerulean's exits open. Walking out of
        # Cerulean's north side triggers the mandatory rival fight, so go in healthy.
        if gym["leader"] == "Lt. Surge" and not self.c._has_ss_ticket():
            if any(p.current_hp < 0.9 * p.max_hp for p in party):
                return "heal", {}
            return "get_ss_ticket", {}
        cur = self.r.read_current_map()
        from knowledge.leafgreen_data import GYM_MAP_LEADER
        if GYM_MAP_LEADER.get(cur) == gym["leader"]:
            return "challenge_leader", {}
        return "go_to", {"destination": "Gym"}

    # ── fake OpenAI surface ─────────────────────────────────────────────────
    def respond(self, messages):
        """One chat.completions response for the agent's current message list."""
        last = messages[-1]["role"] if messages else "user"
        if last == "tool":
            return _response("")
        name, args = self.decide()
        self.history.append(f"{name}({json.dumps(args)})")
        return _response("", name, args)


def _has_pp(mon) -> bool:
    from knowledge.party import can_attack
    return can_attack(mon)


_ids = iter(range(10**9))


def _response(content: str, tool: str | None = None, args: dict | None = None):
    calls = None
    if tool:
        fn = SimpleNamespace(name=tool, arguments=json.dumps(args or {}))
        cid = f"scripted_{next(_ids)}"
        tc = SimpleNamespace(id=cid, function=fn, type="function")
        tc.model_dump = lambda: {"id": cid, "type": "function",
                                 "function": {"name": tool, "arguments": json.dumps(args or {})}}
        calls = [tc]
    msg = SimpleNamespace(content=content, tool_calls=calls, model_extra={}, role="assistant")
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0))


class FakeLLM:
    """Quacks like the `openai.OpenAI` client for chat.completions.create only."""

    def __init__(self, policy: ScriptedPolicy):
        self.policy = policy
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        return self.policy.respond(kw["messages"])
