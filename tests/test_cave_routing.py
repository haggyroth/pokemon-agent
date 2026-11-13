"""Mt. Moon is several disconnected regions per floor joined by ladders; routing must
hop them in the right order (the overnight run looped ~100 calls in B1F)."""
from knowledge.cave_regions import CAVE_GRIDS, CAVE_WARP_ARRIVAL, region_at
from knowledge.map_graph import MAP_WARPS, node_for, route_to

CERULEAN = (3, 3)


def _warps(route):
    return [s[1] for s in route if s[0] == "warp"]


def test_route4_west_to_cerulean_goes_down_and_back_up():
    r = route_to(node_for(3, 22, 19, 5), CERULEAN)
    # 1F -> B1F (west region) -> B2F -> B1F (exit region) -> Route 4 east -> Cerulean
    assert _warps(r) == [(19, 5), (5, 6), (22, 18), (5, 10), (45, 4)]
    assert r[-1] == ("connection", "East", CERULEAN)


def test_from_the_b1f_ladder_region():
    """The exact spot the run got stuck: B1F (3,3). Must go DOWN to B2F, not hunt (45,4)."""
    r = route_to(node_for(1, 2, 3, 3), CERULEAN)
    assert _warps(r) == [(22, 18), (5, 10), (45, 4)]


def test_route4_pokemon_center_exits_to_the_west_half():
    r = route_to((16, 0), CERULEAN)
    assert r is not None and _warps(r)[0] == (6, 8)


def test_every_cave_warp_has_a_known_arrival_region():
    for mp in CAVE_GRIDS:
        for (x, y, dest) in MAP_WARPS[mp]:
            if dest[:2] not in CAVE_GRIDS:
                continue          # exits to Route 4 are handled by the Route 4 split tables
            assert (mp, (x, y)) in CAVE_WARP_ARRIVAL, (mp, (x, y))


def test_b1f_has_four_regions_and_exit_is_isolated_from_the_entrance():
    assert region_at((1, 2), 3, 3) != region_at((1, 2), 45, 4)
    assert len({ch for row in CAVE_GRIDS[(1, 2)] for ch in row if ch != "#"}) == 4
