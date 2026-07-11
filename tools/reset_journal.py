"""Reset the agent's long-term journal so a run starts fresh from the battery save.

Backs up logs/progress.json + logs/battles.jsonl, then rewrites progress.json to a
clean PRE-game state (0 badges, no gyms) while KEEPING the milestones/starter that
are baked into the battery save (starter_chosen, delivered_oaks_parcel) — otherwise
the phase logic would think you still need to pick a starter.

Why this is needed: startup badge reconciliation only ADDS badges (never un-earns),
so an in-memory gym win from a prior run sticks in progress.json even though the
cartridge save never advanced. Run this whenever progress.json has drifted ahead of
the save you're testing with.

Usage:
    python -m tools.reset_journal            # keep starter/parcel (default)
    python -m tools.reset_journal --bare     # wipe everything (as if brand new)
"""
import argparse
import copy
import json
from datetime import datetime

from config import JOURNAL_PATH, PROGRESS_PATH
from memory.long_term import DEFAULTS

KEEP_MILESTONES = ("starter_chosen", "delivered_oaks_parcel")
KEEP_TOWNS = ("Pallet Town", "Viridian City")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset the agent journal to the battery save's state.")
    ap.add_argument("--bare", action="store_true",
                    help="wipe everything (don't preserve starter/parcel milestones)")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in (PROGRESS_PATH, JOURNAL_PATH):
        if p.exists():
            bak = p.with_name(f"{p.name}.bak-{stamp}")
            bak.write_bytes(p.read_bytes())
            print(f"backed up {p.name} → {bak.name}")

    data = copy.deepcopy(DEFAULTS)
    if not args.bare and PROGRESS_PATH.exists():
        try:
            old = json.loads(PROGRESS_PATH.read_text())
            data["milestones"] = [m for m in old.get("milestones", []) if m in KEEP_MILESTONES]
            data["towns_visited"] = [t for t in old.get("towns_visited", []) if t in KEEP_TOWNS]
            data["starter"] = old.get("starter")
            data["notes"] = [n for n in old.get("notes", [])
                             if any(n.startswith(m) for m in KEEP_MILESTONES)]
            data["session_count"] = old.get("session_count", 0)
        except (json.JSONDecodeError, OSError):
            pass

    PROGRESS_PATH.write_text(json.dumps(data, indent=2))
    JOURNAL_PATH.write_text("")
    print(f"reset progress.json: badges=0, gyms=[], milestones={data['milestones']}")
    print("cleared battles.jsonl")


if __name__ == "__main__":
    main()
