"""Routing fixes found getting the scripted bot to Celadon (#185 item 5, Erika)."""
import pytest

from knowledge import map_graph as mg


def test_route_to_can_ban_whole_maps():
    n = mg.node_for(3, 3, 24, 0)
    banned = mg.route_to(n, (3, 6), avoid_maps={(3, 10)})
    assert banned and all(tuple(s[2][:2]) != (3, 10) for s in banned)
    assert any(tuple(s[2][:2]) == (3, 10) for s in mg.route_to(n, (3, 6)))      # Saffron is the short way


def test_respect_gates_routes_around_a_gated_city_through_the_underground_path():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    # Tea (Saffron gate) and the Poké Flute (Route 12/16 Snorlaxes) are missing; everything else is fine.
    c._gate_ok = lambda req: not (req.kind == "key_item" and req.value in (369, 350))
    start = mg.node_for(3, 5, 24, 0)                       # Vermilion
    route = mg.route_to(start, (3, 6))
    fixed, why = c._respect_gates(start, (3, 6), route, set())
    assert why is None, why
    maps = [tuple(s[2][:2]) for s in fixed]
    assert (3, 10) not in maps and (3, 30) not in maps and (3, 34) not in maps
    assert (1, 34) in maps or (1, 33) in maps or (1, 35) in maps     # Underground Path Route 8 → Route 7


def test_gym_interiors_resolve_to_their_city():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    assert AgentClient._gym_city((10, 16)) == (3, 6)        # Celadon
    assert AgentClient._gym_city((9, 6)) == (3, 5)          # Vermilion
    assert AgentClient._gym_city((3, 3)) is None            # not a gym


def test_no_walking_route_from_cerulean_back_west():
    pytest.importorskip("openai")
    from types import SimpleNamespace
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_current_map=lambda: (3, 3), read_player_pos=lambda: (24, 0))
    out = c._go_to("Pewter City")
    assert "no walking route" in out.lower() and "Fly" in out


def test_cerulean_north_edge_tiles_split_into_separate_regions():
    # (28,0) is a different pocket from the road at x=22..24: picking the nearest edge tile by distance
    # (the old behaviour) sent the walk to an unreachable tile — see the Pokémart enter/exit loop.
    assert mg.region_at((3, 3), 24, 0) == "0" and mg.region_at((3, 3), 28, 0) == "1"
    assert mg.region_at((3, 3), 29, 29) == "0"
