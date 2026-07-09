"""Eval scenario registry.

A Scenario is a start point (battery save or mGBA save state) + a goal + a step
budget. The runner loads each in isolation and scores the episode. Add scenarios
here; keep them light (no heavy imports) so this stays CI-testable.

Start points default to the project's standard post-parcel save. Override per
scenario, or via env for local curated states (e.g. a Route-2 save that isolates
the #59 crossing without the whole Pallet→Route 2 journey).
"""
import os
from dataclasses import dataclass
from typing import Optional
from evals import goals

# The standard save the project boots from (post-parcel, Pokédex obtained).
DEFAULT_SAVE = os.path.expanduser(
    os.getenv("EVAL_START_SAVE", "~/mgba-http/Pokemon_LeafGreen.sav"))


@dataclass
class Scenario:
    name:        str
    goal:        goals.Goal
    max_steps:   int
    start_save:  Optional[str] = None
    start_state: Optional[str] = None
    notes:       str = ""
    # Known-failing today (documents an open bug); the run still executes and is
    # scored, but the runner reports it as an expected failure rather than a
    # regression. Set to an issue reference.
    xfail:       str = ""


SCENARIOS: list[Scenario] = [
    Scenario(
        name="reach_viridian",
        goal=goals.reached_map(3, 1, "Viridian City"),
        max_steps=30,
        start_save=DEFAULT_SAVE,
        notes="From the post-parcel Pallet save, head north through Route 1 into "
              "Viridian City. Baseline overworld traversal + wild-battle handling.",
    ),
    Scenario(
        name="reach_pewter",
        goal=goals.reached_map(3, 2, "Pewter City"),
        max_steps=150,
        start_save=DEFAULT_SAVE,
        notes="The gauntlet: Route 2 is split by Viridian Forest's gate buildings, "
              "so go_to must WARP through the forest rather than walk to the sealed "
              "north edge. #59 fixed this with region-aware routing (verified: the "
              "agent now enters the forest); a full Pallet→Pewter traversal wasn't "
              "hardware-confirmed end-to-end, so this stays xfail until a run turns "
              "it into an XPASS.",
        xfail="#59",
    ),
]


def by_name(name: str) -> Optional[Scenario]:
    return next((s for s in SCENARIOS if s.name == name), None)
