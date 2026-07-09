"""Goal predicates for eval scenarios.

A Goal wraps a `(GameState, LongTermMemory) -> bool` check plus a human
description. It's callable, so it drops straight into `run_episode(goal=...)`.
Pure and light-importing (no openai/cffi) so it unit-tests in CI.
"""
from dataclasses import dataclass
from typing import Callable
from game.state import GameState
from memory.long_term import LongTermMemory
from knowledge.navigation import MAP_NAMES

Predicate = Callable[[GameState, LongTermMemory], bool]


@dataclass
class Goal:
    fn:   Predicate
    desc: str

    def __call__(self, state: GameState, ltm: LongTermMemory) -> bool:
        return self.fn(state, ltm)


def reached_map(bank: int, id: int, name: str | None = None) -> Goal:
    """Player is standing on map (bank, id) — the interior-aware current map."""
    label = name or MAP_NAMES.get((bank, id), f"{bank}/{id}")
    return Goal(lambda s, _l: (s.map_bank, s.map_id) == (bank, id),
                f"reach {label}")


def badges_at_least(n: int) -> Goal:
    return Goal(lambda _s, l: l.data["badges_earned"] >= n,
                f"earn ≥{n} badge(s)")


def has_milestone(name: str) -> Goal:
    return Goal(lambda _s, l: name in l.data.get("milestones", []),
                f"milestone '{name}'")


def party_size_at_least(n: int) -> Goal:
    return Goal(lambda s, _l: s.party_count >= n,
                f"party size ≥{n}")


def all_of(*goals: Goal) -> Goal:
    return Goal(lambda s, l: all(g(s, l) for g in goals),
                " AND ".join(g.desc for g in goals))


def any_of(*goals: Goal) -> Goal:
    return Goal(lambda s, l: any(g(s, l) for g in goals),
                " OR ".join(g.desc for g in goals))
