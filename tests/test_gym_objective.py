"""The agent must not get stuck re-challenging a Gym Leader it already beat, and
must know its next objective the moment it leaves a building. Pure (no ROM/LLM)."""
from game.state import GameState, GameContext
from knowledge.leafgreen_data import GYM_MAP_LEADER, GYMS
from knowledge.map_graph import MAP_KIND
from knowledge.navigation import get_route_guidance


def _state(bank, mid, badges=0):
    return GameState(
        context=GameContext.OVERWORLD, badges=badges, badge_bits=0,
        party=[], party_count=0, map_bank=bank, map_id=mid,
        player_x=5, player_y=6, screen_fading=False,
    )


def test_gym_map_leader_matches_map_kind_gyms():
    # Every gym map is mapped to a leader and vice-versa — so the "already beaten"
    # gate in the obs can never silently miss a gym after a MAP_KIND/data edit.
    gym_maps = {k for k, v in MAP_KIND.items() if v == "gym"}
    assert set(GYM_MAP_LEADER) == gym_maps


def test_gym_map_leader_names_are_real_leaders():
    valid = {g["leader"] for g in GYMS}
    assert set(GYM_MAP_LEADER.values()) == valid


def test_pewter_gym_maps_to_brock():
    assert GYM_MAP_LEADER[(6, 2)] == "Brock"


def test_interior_guidance_names_next_objective_after_a_badge():
    # Inside the Pewter Gym with 1 badge (Brock beaten): guidance must point at the
    # NEXT objective (Cerulean/Misty), not leave the agent with only "exit".
    guidance = get_route_guidance(_state(6, 2, badges=1), milestones=["brock"])
    assert "objective" in guidance.lower()
    assert "Cerulean" in guidance or "Misty" in guidance


def test_interior_guidance_still_says_to_leave():
    guidance = get_route_guidance(_state(6, 2, badges=1), milestones=[])
    assert "INSIDE" in guidance or "Leave" in guidance


# ── story-aware "gym" waypoint (#92: don't route to nearest/beaten/locked gym) ──

def _client_with_beaten(beaten):
    from unittest.mock import MagicMock
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.ltm = MagicMock()
    c.ltm.data = {"gyms_beaten": list(beaten)}
    return c


def test_gym_waypoint_after_brock_goes_to_cerulean_not_viridian():
    # The bug: nearest-gym routing sent the agent back to Pewter (beaten) or to
    # Viridian's gym (locked until 7 badges). It must go to Misty next.
    target_map, name = _client_with_beaten(["Brock"])._resolve_next_gym()
    assert target_map == (7, 5) and "Misty" in name        # Cerulean City Gym


def test_gym_waypoint_no_badges_is_pewter():
    target_map, name = _client_with_beaten([])._resolve_next_gym()
    assert target_map == (6, 2) and "Brock" in name


def test_gym_waypoint_viridian_only_when_it_is_next():
    seven = ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine"]
    target_map, name = _client_with_beaten(seven)._resolve_next_gym()
    assert target_map == (5, 1) and "Giovanni" in name     # Viridian, finally


def test_gym_waypoint_all_beaten_points_to_league():
    target_map, msg = _client_with_beaten(
        ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"]
    )._resolve_next_gym()
    assert target_map is None and "League" in msg
