"""Tier-2 eval runner: drive the real agent loop through scenarios and score them.

Each scenario builds an isolated AgentRuntime (its own scratch progress.json /
battles.jsonl so the real logs are never touched), runs `main.run_episode` with
the scenario's goal + step budget, and collects the EpisodeResult. Results print
as a table and write to logs/eval/<timestamp>.json.

This imports the heavy agent stack (via `main`), so it only runs where the LLM
endpoint + native binding + ROM are available — not in the dependency-light CI.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config import PROGRESS_PATH
from evals.scenarios import Scenario, SCENARIOS

console = Console()
EVAL_DIR = Path(PROGRESS_PATH).parent / "eval"
DEFAULT_EVAL_WALL_S = 7200.0   # 2h hard ceiling for any scenario without its own cap


def run_scenario(sc: Scenario, *, verbose: bool = False) -> dict | None:
    """Run one scenario end-to-end. Returns a result dict (EpisodeResult + meta),
    or None if the emulator couldn't be brought up."""
    import main as agent  # heavy import kept local so `evals` stays importable

    scratch = EVAL_DIR / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    ltm_path     = scratch / f"{sc.name}_progress.json"
    journal_path = scratch / f"{sc.name}_battles.jsonl"
    for p in (ltm_path, journal_path):     # start clean every run
        p.unlink(missing_ok=True)

    console.print(f"[bold]▶ {sc.name}[/] — goal: {sc.goal.desc} (≤{sc.max_steps} steps)")
    rt = agent.build_runtime(
        start_save=sc.start_save or "", start_state=sc.start_state or "",
        ltm_path=str(ltm_path), journal_path=str(journal_path), verbose=verbose,
    )
    if rt is None:
        console.print(f"[red]  could not start emulator for {sc.name} — skipping[/]")
        return None

    # Always bound the wall-clock so an unattended eval can't run away (an 11-hour
    # run happened when a local model degraded). Scenarios may set a tighter cap.
    wall = sc.max_wall_s or DEFAULT_EVAL_WALL_S
    t0 = time.time()
    result = agent.run_episode(rt, goal=sc.goal, goal_desc=sc.goal.desc,
                               max_steps=sc.max_steps, max_wall_s=wall, verbose=verbose)
    elapsed = round(time.time() - t0, 1)

    out = result.to_dict()
    out.update(scenario=sc.name, elapsed_s=elapsed, xfail=sc.xfail)
    # An xfail scenario that fails is "expected"; if it unexpectedly passes, flag it.
    out["status"] = _status(result.passed, sc.xfail)
    console.print(f"  {result.summary()}  [{out['status']}]  ({elapsed}s)")
    return out


def _status(passed: bool, xfail: str) -> str:
    if xfail:
        return "XPASS" if passed else "xfail"   # XPASS = bug may be fixed!
    return "PASS" if passed else "FAIL"


def run_all(scenarios: list[Scenario] | None = None, *, verbose: bool = False) -> list[dict]:
    scenarios = scenarios if scenarios is not None else SCENARIOS
    results = [r for sc in scenarios if (r := run_scenario(sc, verbose=verbose)) is not None]
    _report(results)
    return results


def _report(results: list[dict]) -> None:
    if not results:
        console.print("[yellow]No scenarios ran.[/]")
        return
    table = Table(title="Eval results", show_lines=False)
    for col in ("scenario", "status", "reason", "steps", "reward",
                "final_map", "stuck", "llm_calls", "tokens", "time"):
        table.add_column(col)
    for r in results:
        style = {"PASS": "green", "XPASS": "yellow bold",
                 "FAIL": "red", "xfail": "dim"}.get(r["status"], "")
        table.add_row(
            r["scenario"], f"[{style}]{r['status']}[/]" if style else r["status"],
            r["reason"], str(r["steps"]), f"{r['reward']:.1f}",
            str(tuple(r["final_map"])), f"{r['stuck_ratio']:.0%}",
            str(r["llm_calls"]), str(r["total_tokens"]), f"{r['elapsed_s']}s",
        )
    console.print(table)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = EVAL_DIR / f"{stamp}.json"
    path.write_text(json.dumps({"timestamp": stamp, "results": results}, indent=2))
    console.print(f"[dim]Wrote {path}[/]")

    passed = sum(r["status"] in ("PASS", "XPASS") for r in results)
    console.print(f"\n[bold]{passed}/{len(results)} scenarios met their goal.[/]")
