from game.pathfinding import find_path


def _grid_passable(rows):
    # rows: list of strings, '.'=floor '#'=wall
    def passable(x, y):
        return rows[y][x] == "."
    return passable, len(rows[0]), len(rows)


def test_straight_line():
    rows = ["....", "....", "...."]
    p, w, h = _grid_passable(rows)
    assert find_path((0, 0), (3, 0), p, w, h) == ["Right", "Right", "Right"]


def test_already_at_goal():
    rows = ["..", ".."]
    p, w, h = _grid_passable(rows)
    assert find_path((1, 1), (1, 1), p, w, h) == []


def test_routes_around_wall():
    rows = [
        ".....",
        ".###.",
        ".#...",
        ".....",
    ]
    p, w, h = _grid_passable(rows)
    path = find_path((1, 0), (3, 2), p, w, h)
    assert path is not None
    # walk it and confirm it lands on the goal without crossing a wall
    x, y = 1, 0
    d = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}
    for mv in path:
        dx, dy = d[mv]
        x, y = x + dx, y + dy
        assert rows[y][x] == ".", f"stepped into wall at {(x, y)}"
    assert (x, y) == (3, 2)


def test_unreachable_returns_none():
    rows = [
        "..#..",
        "..#..",
        "..#..",
    ]
    p, w, h = _grid_passable(rows)
    assert find_path((0, 0), (4, 0), p, w, h) is None


def test_goal_wall_is_none():
    rows = ["...", ".#.", "..."]
    p, w, h = _grid_passable(rows)
    assert find_path((0, 0), (1, 1), p, w, h) is None


def test_shortest_length():
    rows = ["....", "....", "....", "...."]
    p, w, h = _grid_passable(rows)
    assert len(find_path((0, 0), (3, 3), p, w, h)) == 6  # Manhattan distance


# ── one-way ledges ────────────────────────────────────────────────────────────

def _ledge_grid(rows):
    def passable(x, y):
        return rows[y][x] == "."
    def ledge(x, y):
        return "Down" if rows[y][x] == "v" else None
    return passable, ledge, len(rows[0]), len(rows)


def test_ledge_lets_you_cross_a_wall():
    # A south-facing ledge ('v') at (1,1), walled either side, is the ONLY crossing
    # between start (1,0) and grass (1,2). Plain passability treats it as a wall;
    # with the ledge callable, A* hops it in one Down press.
    rows = ["...", "#v#", "..."]
    p, lg, w, h = _ledge_grid(rows)
    assert find_path((1, 0), (1, 2), p, w, h) is None                 # walled off
    assert find_path((1, 0), (1, 2), p, w, h, ledge=lg) == ["Down"]


def test_ledge_only_crosses_in_its_facing_direction():
    # A single down-ledge at (2,2). Travelling UPHILL must detour around it, never
    # hop it backwards.
    rows = [".....", ".....", "..v..", ".....", "....."]
    p, lg, w, h = _ledge_grid(rows)
    path = find_path((2, 4), (2, 0), p, w, h, ledge=lg)
    assert path is not None
    x, y = 2, 4
    d = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}
    for mv in path:
        dx, dy = d[mv]
        x, y = x + dx, y + dy
        assert rows[y][x] != "v", "walked onto a ledge going uphill"
    assert (x, y) == (2, 0)


def test_ledge_needs_passable_landing():
    # Ledge at (1,1) with a wall row directly beyond it: nothing to land on, and
    # the sides are walled, so the goal below stays unreachable.
    rows = ["...", "#v#", "###", "..."]
    p, lg, w, h = _ledge_grid(rows)
    assert find_path((1, 0), (1, 3), p, w, h, ledge=lg) is None
