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
    # Wall-clock safety cap (seconds) so an unattended eval can't run away — a local
    # model degraded to 3+ hour steps and burned 11 hours before. 0 = use the runner's
    # default ceiling. Set explicitly for legitimately long scenarios.
    max_wall_s:  float = 0.0
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
        name="first_badge",
        goal=goals.badges_at_least(1),
        max_steps=400,
        start_save=DEFAULT_SAVE,
        notes="Earn the Boulder Badge from Brock. The save's lead is Bulbasaur L8 "
              "(Tackle/Growl/Leech Seed, no Vine Whip yet), so the agent must GRIND "
              "to ~L13 for Vine Whip before it can reliably beat Geodude L12 / Onix "
              "L14, then navigate the Pewter Gym and win. Long, exploratory run.",
    ),
    Scenario(
        name="second_badge",
        goal=goals.badges_at_least(2),
        max_steps=800,
        max_wall_s=5400,     # ~90 min ceiling; should finish well under this
        start_save=DEFAULT_SAVE,
        notes="Full mid-game pipeline: beat Brock, then cross Route 3 + Mt. Moon (a "
              "trainer-dense multi-floor maze) to Cerulean and beat Misty (Starmie L21, "
              "has Recover). Exercises everything post-first-badge — dungeon nav, trainer "
              "battles, healing/items — to surface the next capability gate.",
    ),
    Scenario(
        name="reach_pewter",
        goal=goals.reached_map(3, 2, "Pewter City"),
        max_steps=150,
        start_save=DEFAULT_SAVE,
        notes="The gauntlet: Route 2 is split by Viridian Forest's gate buildings, "
              "so go_to must WARP through the forest rather than walk to the sealed "
              "north edge. Solved end-to-end (#59 region routing + heal()/flee_battle "
              "to survive and skip wild encounters): a full LLM run reached Pewter "
              "(XPASS, steps=27, stuck=6%). Forest traversal is stochastic, so this "
              "is a probabilistic pass — go_to-through-forest autonomy (#81) would "
              "make it faster/more reliable.",
    ),
]


def by_name(name: str) -> Optional[Scenario]:
    return next((s for s in SCENARIOS if s.name == name), None)
