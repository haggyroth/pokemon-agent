from knowledge.map_graph import (
    MAP_CONNECTIONS, MAP_WARPS, MAP_KIND, bfs_route, route_to, nearest_of_kind,
)


def test_graph_has_early_overworld():
    # Pallet Town connects north to Route 1, south to Route 21.
    assert MAP_CONNECTIONS[(3, 0)]["North"] == (3, 19)
    assert MAP_CONNECTIONS[(3, 0)]["South"] == (3, 39)
    # Route 1 north to Viridian City.
    assert MAP_CONNECTIONS[(3, 19)]["North"] == (3, 1)


def test_already_there_is_empty():
    assert bfs_route((3, 0), (3, 0)) == []


def test_multi_hop_pallet_to_pewter():
    route = bfs_route((3, 0), (3, 2))
    assert route is not None
    dirs = [d for d, _ in route]
    dests = [m for _, m in route]
    assert dests[-1] == (3, 2)               # ends at Pewter
    assert dirs == ["North", "North", "North", "North"]  # Route1→Viridian→Route2→Pewter
    # every hop is a real edge in the graph
    cur = (3, 0)
    for d, nb in route:
        assert MAP_CONNECTIONS[cur][d] == nb
        cur = nb


def test_unreachable_returns_none():
    # A map id with no connection route from Pallet (isolated / indoor-only).
    assert bfs_route((3, 0), (99, 99)) is None


def test_warps_and_kinds_present():
    # Rival's house (4,2) has three door warps back to Pallet Town (3,0).
    assert (4, 2) in MAP_WARPS
    assert all(dest == (3, 0) for _, _, dest in MAP_WARPS[(4, 2)])
    # There are Pokémon Centers / gyms / marts classified for waypoints.
    kinds = set(MAP_KIND.values())
    assert {"pokecenter", "mart", "gym"} <= kinds


def test_route_to_uses_warp_into_building():
    # Viridian City → its gym is a single warp step.
    route = route_to((3, 1), (5, 1))  # (5,1) = Viridian Gym
    assert route is not None
    assert route[-1][2] == (5, 1)
    assert any(step[0] == "warp" for step in route)


def test_nearest_of_kind_finds_pokecenter():
    got = nearest_of_kind((3, 1), "pokecenter")  # from Viridian City
    assert got is not None
    target, steps = got
    assert MAP_KIND.get(target) == "pokecenter"
    assert steps and steps[-1][2] == target


def test_door_centers_collapses_doormat():
    from main import door_centers
    # 3-tile doormat -> the middle (functional) tile
    assert door_centers([(4, 8), (5, 8), (3, 8)]) == [(4, 8)]
    # single door unchanged; separate doors kept
    assert door_centers([(4, 8)]) == [(4, 8)]
    assert sorted(door_centers([(3, 8), (4, 8), (5, 8), (10, 2)])) == [(4, 8), (10, 2)]
