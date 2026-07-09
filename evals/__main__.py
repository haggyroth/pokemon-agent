"""CLI for the eval harness:  python -m evals [--scenario NAME] [--verbose] [--list]

Runs Tier-2 scenarios (real agent loop toward a goal) and prints a scorecard.
Needs the LLM endpoint + native binding + ROM up, same as `python main.py`.
"""
import argparse
import sys

from evals.scenarios import SCENARIOS, by_name


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m evals",
                                 description="Run agent eval scenarios.")
    ap.add_argument("--scenario", "-s", help="run only this scenario by name")
    ap.add_argument("--list", "-l", action="store_true", help="list scenarios and exit")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="stream the per-tick agent output (default: quiet)")
    args = ap.parse_args()

    if args.list:
        for sc in SCENARIOS:
            tag = f" [xfail {sc.xfail}]" if sc.xfail else ""
            print(f"{sc.name:16} ≤{sc.max_steps:<4} {sc.goal.desc}{tag}")
            if sc.notes:
                print(f"{'':16} {sc.notes}")
        return

    from evals.runner import run_all, run_scenario, _report

    if args.scenario:
        sc = by_name(args.scenario)
        if sc is None:
            print(f"Unknown scenario '{args.scenario}'. "
                  f"Known: {', '.join(s.name for s in SCENARIOS)}", file=sys.stderr)
            sys.exit(2)
        r = run_scenario(sc, verbose=args.verbose)
        _report([r] if r else [])
    else:
        run_all(verbose=args.verbose)


if __name__ == "__main__":
    main()
