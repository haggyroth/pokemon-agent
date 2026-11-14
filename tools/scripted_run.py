#!/usr/bin/env python3
"""Run the real decision loop with a rule-based policy instead of the LLM (zero token cost).

    python tools/scripted_run.py --goal badges:2 --max-steps 300 [--state saves/live/pregym.ss1]

Finds where the skill chain (go_to / grind / heal / challenge_leader / battles) stalls end to end.
Writes a normal run log under logs/runs/ (its tool results are the timeline); prints the scorecard.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default="badges:2", help="badges:N | map:BANK,ID")
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--max-wall", type=float, default=1800, help="wall-clock cap, seconds")
    ap.add_argument("--state", default="", help="start from this emulator state instead of the save")
    ap.add_argument("--save", default=os.path.expanduser("~/mgba-http/Pokemon_LeafGreen.sav"))
    a = ap.parse_args()
    os.environ.update(USE_VISION="false", SHOW_WINDOW="false", MGBA_BACKEND="native",
                      MAX_LLM_CALLS="0", TOKEN_BUDGET="0", START_FROM_SAVE=a.save)
    if a.state:
        os.environ["START_FROM_STATE"] = a.state
    import game.mgba_core as mc
    mc.SHOW_WINDOW = False
    import main
    from evals import goals
    from agent.scripted_policy import FakeLLM, ScriptedPolicy
    from memory.run_log import RunLog

    kind, _, val = a.goal.partition(":")
    goal = (goals.badges_at_least(int(val)) if kind == "badges"
            else goals.reached_map(*[int(x) for x in val.split(",")]))
    import tempfile
    tmp = tempfile.mkdtemp()
    rt = main.build_runtime(ltm_path=f"{tmp}/ltm.json", journal_path=f"{tmp}/j.jsonl", verbose=False,
                            **({"start_state": a.state} if a.state else {}))
    if rt is None:
        sys.exit("could not build the runtime (ROM / binding?)")
    policy = ScriptedPolicy(rt)
    rt.client.llm = FakeLLM(policy)
    rlog = RunLog(os.path.join(os.path.dirname(main.__file__), "logs", "scripted"))
    rlog.write_meta(kind="scripted", goal=a.goal, max_steps=a.max_steps, state=a.state)
    t0 = time.time()
    try:
        res = main.run_episode(rt, goal=goal, goal_desc=a.goal, max_steps=a.max_steps,
                               max_wall_s=a.max_wall, verbose=False, run_log=rlog)
    finally:
        rlog.close()
    print(f"\nlog: {rlog.dir}\n{res}\nwall {time.time() - t0:.0f}s")
    print("last decisions:", policy.history[-12:])


if __name__ == "__main__":
    main()
