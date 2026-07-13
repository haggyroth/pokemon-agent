"""go_to stall detection: repeated travel calls that end at the same map without
arriving must, after a few, return actionable guidance instead of the resumable
"call go_to again" message — otherwise a story-gated path (e.g. the Pewter guard
shuffling the player back to the gym, which reads as movement) loops the agent
forever. Pure logic (no ROM/LLM), just the counter + guidance text."""
import importlib.util

import pytest

# AgentClient imports openai, which CI's dependency-light env may lack — skip cleanly.
requires_openai = pytest.mark.skipif(
    importlib.util.find_spec("openai") is None, reason="openai not installed")

PEWTER = (3, 2)      # MAP_NAMES[(3,2)] == "Pewter City"; Brock's city
MT_MOON_1F = (1, 1)  # a cave-maze map (DUNGEON_MAPS)


def _client(beaten):
    from unittest.mock import MagicMock
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.ltm = MagicMock()
    c.ltm.data = {"gyms_beaten": list(beaten)}
    c._go_to_last_end = None
    c._go_to_stalls = 0
    return c


@requires_openai
def test_first_two_stalls_do_not_trip():
    # The resume message must still work for genuinely-long journeys: the first two
    # same-map stalls return None (caller sends its normal "call go_to again").
    c = _client([])
    assert c._register_go_to_stall("Cerulean City", PEWTER) is None
    assert c._register_go_to_stall("Cerulean City", PEWTER) is None


@requires_openai
def test_third_stall_redirects_to_local_unbeaten_gym():
    # Blocked leaving Pewter with Brock unbeaten → guidance names the gym redirect.
    c = _client([])
    for _ in range(2):
        c._register_go_to_stall("Cerulean City", PEWTER)
    msg = c._register_go_to_stall("Cerulean City", PEWTER)
    assert msg is not None
    assert "go_to('Gym')" in msg and "Brock" in msg
    assert "challenge_leader" in msg


@requires_openai
def test_progress_resets_the_streak():
    # Ending somewhere NEW each call (real progress) never trips the detector.
    c = _client([])
    assert c._register_go_to_stall("Cerulean City", PEWTER) is None
    assert c._register_go_to_stall("Cerulean City", (3, 3)) is None   # moved on
    assert c._register_go_to_stall("Cerulean City", (3, 4)) is None
    assert c._go_to_stalls == 1


@requires_openai
def test_generic_gate_when_no_local_gym_owed():
    # Stalling in a city whose gym is already beaten → generic "gated/HM" guidance,
    # not a wrong gym redirect.
    c = _client(["Brock"])   # Brock done; Pewter no longer owes a gym
    for _ in range(2):
        c._register_go_to_stall("Cerulean City", PEWTER)
    msg = c._register_go_to_stall("Cerulean City", PEWTER)
    assert msg is not None
    assert "Brock" not in msg
    assert "gated" in msg or "HM" in msg


@requires_openai
def test_dungeon_stall_gives_maze_guidance_not_gated():
    # Stalling inside Mt. Moon is a cave maze, not a gated road — the guidance must tell
    # the agent to keep pushing through, NOT that it needs an HM (which made it backtrack).
    c = _client([])   # Brock unbeaten, but a cave isn't a city gym gate
    for _ in range(2):
        c._register_go_to_stall("Cerulean City", MT_MOON_1F)
    msg = c._register_go_to_stall("Cerulean City", MT_MOON_1F)
    assert msg is not None
    assert "maze" in msg.lower()
    assert "HM" not in msg or "no HM" in msg   # must not claim an HM is required
    assert "backtrack" in msg.lower()
    assert "go_to('Gym')" not in msg           # not the city-gym redirect


@requires_openai
def test_streak_resets_after_advising():
    # After firing guidance, the counter resets so a later genuine retry gets a fresh
    # window (doesn't instantly re-fire on the very next call).
    c = _client([])
    for _ in range(3):
        last = c._register_go_to_stall("Cerulean City", PEWTER)
    assert last is not None
    assert c._go_to_stalls == 0
    assert c._register_go_to_stall("Cerulean City", PEWTER) is None
