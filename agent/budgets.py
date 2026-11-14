"""Frame budgets for tool calls (see game/watchdog.py). Frames are GBA frames: 60 = one game second."""

DEFAULT = (90_000, 15_000)          # (hard cap ≈ 25 min of game time, no-progress limit ≈ 4 min)
BUDGETS = {
    "grind": (360_000, 15_000),     # built to run long (hundreds of battles), but still bounded
    "go_to": (240_000, 15_000),     # cross-map trips with fights en route
    "heal": (60_000, 12_000),
    "shop": (60_000, 12_000),
    "use_move": (30_000, 9_000),
    "catch": (30_000, 9_000),
    "flee_battle": (30_000, 9_000),
    "switch_pokemon": (30_000, 9_000),
}
# Trivial or deliberately-long-by-request tools: never watched.
EXEMPT = frozenset({"press_button", "wait_frames", "read_game_state", "save_state", "load_state",
                    "record_milestone"})


def budget_for(tool: str):
    """(max_frames, stall_frames) for a tool, or None when it is exempt."""
    if tool in EXEMPT:
        return None
    return BUDGETS.get(tool, DEFAULT)
