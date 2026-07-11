"""Level-up move-learn policy: which of the current 4 moves (if any) to forget when
the game offers a new one. Pure/testable. Two hard rules from real runs:

  1. NEVER cripple the moveset — always keep at least one damaging move (the agent
     let Sleep Powder overwrite Tackle, leaving Bulbasaur with only weak Grass moves).
  2. Don't stack status — a Pokémon rarely wants two "inflict a status" moves, so a
     new status move is declined when the lead already has a non-damaging move.

`choose_move_to_forget` returns the slot index (0-3) to forget, or None to DECLINE
(keep the current moveset). The battle handler executes the decision.
"""
from knowledge.leafgreen_data import (
    MOVE_POWER, MOVE_POWER_DEFAULT, STATUS_MOVES,
)


def _power(name: str) -> int:
    """Damage-ranking power of a move: 0 for status/utility (non-damaging) moves,
    else its base power. Moves in STATUS_MOVES (incl. Leech Seed) count as 0."""
    if not name or name in STATUS_MOVES:
        return 0
    return MOVE_POWER.get(name, MOVE_POWER_DEFAULT)


def choose_move_to_forget(current_names: list[str], new_name: str) -> int | None:
    """Given the lead's 4 current move names and the offered new move name, return the
    slot (0-3) to forget, or None to decline. Never returns a slot that would drop the
    last damaging move."""
    if len(current_names) != 4:
        return None
    powers = [_power(n) for n in current_names]
    dmg_slots = [i for i, p in enumerate(powers) if p > 0]
    status_slots = [i for i, p in enumerate(powers) if p == 0]
    new_pow = _power(new_name)
    new_is_status = new_pow == 0

    if new_is_status:
        # Don't stack status: if we already carry a non-damaging move, decline.
        if status_slots:
            return None
        # All four are damaging — a status move is only worth a slot if we still keep
        # at least TWO damaging moves afterward. Forget the weakest.
        if len(dmg_slots) >= 3:
            return min(dmg_slots, key=lambda i: powers[i])
        return None

    # New move IS damaging. Prefer forgetting a non-damaging move (keep all damage and
    # gain the new attack).
    if status_slots:
        # Forget the weakest non-damaging move (they're all 0-power; pick the first
        # for determinism — typically a stat move like Growl over Leech Seed).
        return status_slots[0]
    # All four are damaging: forget the weakest, but only if the new move is an
    # upgrade over it (and we always keep the other three damaging moves).
    weakest = min(range(4), key=lambda i: powers[i])
    if new_pow > powers[weakest]:
        return weakest
    return None
