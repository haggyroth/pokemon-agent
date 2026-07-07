from dataclasses import dataclass, field
from collections import defaultdict
from game.state import GameState, StateDiff

@dataclass
class ShortTermMemory:
    current_state:           GameState | None = None
    last_state:              GameState | None = None
    last_diff:               StateDiff | None = None
    last_action:             str = ""
    action_history:          list[str] = field(default_factory=list)
    battle_turn:             int = 0
    consecutive_same_action: int = 0
    steps_without_movement:  int = 0
    last_x:                  int | None = None
    last_y:                  int | None = None
    # Tracks how many times the agent has been at each (x, y) on the current map.
    # Reset when map changes. Used to detect looping/revisiting.
    _pos_visits:             dict = field(default_factory=lambda: defaultdict(int))

    def record_action(self, action: str, x: int | None = None, y: int | None = None):
        # None means "position unknown"; (0, 0) is a valid map coordinate and
        # must be tracked like any other (it isn't a sentinel).
        has_pos = x is not None and y is not None
        pos_changed = has_pos and (x, y) != (self.last_x, self.last_y)
        if action == self.last_action and not pos_changed:
            self.consecutive_same_action += 1
        else:
            self.consecutive_same_action = 1
        if has_pos and not pos_changed:
            self.steps_without_movement += 1
        elif has_pos:
            self.steps_without_movement = 0
        self.last_action = action
        if has_pos:
            self.last_x, self.last_y = x, y
            self._pos_visits[(x, y)] += 1
        self.action_history.append(action)
        if len(self.action_history) > 30:
            self.action_history.pop(0)

    @property
    def stuck(self) -> bool:
        """True if position hasn't changed for 4+ steps, regardless of which buttons were pressed."""
        return self.steps_without_movement >= 4

    def visit_count(self, x: int, y: int) -> int:
        """How many times this (x, y) has been visited on the current map."""
        return self._pos_visits.get((x, y), 0)

    def reset_for_new_map(self):
        """Call when map changes — resets position visit counts for the new area."""
        self._pos_visits = defaultdict(int)
        self.steps_without_movement = 0

    def reset_for_new_battle(self):
        self.battle_turn = 0
        self.consecutive_same_action = 0
        self.steps_without_movement = 0
