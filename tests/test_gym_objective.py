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
