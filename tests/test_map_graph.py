from knowledge.map_graph import (
    MAP_CONNECTIONS, MAP_WARPS, MAP_KIND, bfs_route, route_to, nearest_of_kind,
    node_for,
)


def test_graph_has_early_overworld():
    # Pallet Town connects north to Route 1, south to Route 21.
    assert MAP_CONNECTIONS[(3, 0)]["North"] == (3, 19)
    assert MAP_CONNECTIONS[(3, 0)]["South"] == (3, 39)
    # Route 1 north to Viridian City.
    assert MAP_CONNECTIONS[(3, 19)]["North"] == (3, 1)


def test_already_there_is_empty():
    assert bfs_route((3, 0), (3, 0)) == []


def test_multi_hop_pallet_to_viridian_is_clean_norths():
    # The un-gated early stretch is still a simple connection walk.
    route = route_to((3, 0), (3, 1))         # Pallet → Viridian City
    assert [d for _, d, _m in route] == ["North", "North"]   # Route 1 → Viridian
    assert route[-1][2] == (3, 1)


def test_pallet_to_pewter_uses_a_warp_across_the_split_route2():
    # Route 2 is split into disconnected regions (#59); the walk must WARP across (a gate
    # building or Viridian Forest), never "cross the North edge" from the sealed south half.
    route = route_to((3, 0), (3, 2))
    assert route is not None
    assert route[-1][:2] == ("connection", "North")      # ends entering Pewter
    assert route[-1][2][:2] == (3, 2)
    assert any(step[0] == "warp" for step in route), "must cross Route 2 via a warp"


def test_route2_south_needs_a_warp_but_north_is_direct():
    south = route_to(node_for(3, 20, 5, 60), (3, 2))
    assert south[0][0] == "warp"                         # not the sealed north edge
    assert south[-1][:2] == ("connection", "North")
    north = route_to(node_for(3, 20, 5, 14), (3, 2))
    assert [s[:2] for s in north] == [("connection", "North")]


def test_node_for_regionizes_split_map():
    south, north = node_for(3, 20, 5, 60), node_for(3, 20, 5, 14)
    assert south[:2] == north[:2] == (3, 20) and south != north and len(south) == 3
    assert node_for(3, 1) == (3, 1)                    # non-split map unchanged
    assert node_for(3, 1, 10, 10) == (3, 1)


def test_route4_west_to_cerulean_routes_through_mt_moon():
    # Route 4 is one map split by Mt. Moon: you arrive from Route 3 on the WEST side and
    # Cerulean's seam is on the EAST side — reachable only THROUGH the cave.
    route = route_to(node_for(3, 22, 19, 6), (3, 3))   # west side of Route 4
    assert route is not None
    assert route[-1][:2] == ("connection", "East") and route[-1][2][:2] == (3, 3)
    maps = [step[2][:2] for step in route]
    assert (1, 1) in maps, "route must pass through Mt. Moon 1F"
    assert route[0][:2] == ("warp", (19, 5))           # first hop = the cave entrance warp


def test_route4_east_to_cerulean_is_direct_seam():
    east = node_for(3, 22, 32, 5)                      # B1F exit / Cerulean side
    route = route_to(east, (3, 3))
    assert [s[:2] for s in route] == [("connection", "East")]


def test_node_for_regionizes_route4_by_position():
    assert node_for(3, 22, 19, 6) != node_for(3, 22, 32, 5)


def test_connection_only_route_to_pewter_is_not_the_naive_four_norths():
    # Regression for #59: the direct (3,20)->North->Pewter walk is a lie from the
    # south region. bfs_route (connection-only) must NOT offer it as a 4-step walk.
    route = bfs_route((3, 0), (3, 2))
    naive = route is not None and [d for d, _ in route] == ["North"] * 4
    assert not naive, "connection-only routing must not claim a straight walk to Pewter"


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
    from game.pathfinding import door_centers
    # 3-tile doormat -> the middle (functional) tile
    assert door_centers([(4, 8), (5, 8), (3, 8)]) == [(4, 8)]
    # single door unchanged; separate doors kept
    assert door_centers([(4, 8)]) == [(4, 8)]
    assert sorted(door_centers([(3, 8), (4, 8), (5, 8), (10, 2)])) == [(4, 8), (10, 2)]
