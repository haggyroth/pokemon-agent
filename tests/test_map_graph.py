from knowledge.map_graph import MAP_CONNECTIONS, bfs_route


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
