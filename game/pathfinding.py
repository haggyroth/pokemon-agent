"""A* grid pathfinding for overworld navigation.

Pure and dependency-light so it unit-tests without an emulator: it takes a
`passable(x, y) -> bool` callable and grid bounds, and returns the list of
button directions ("Up"/"Down"/"Left"/"Right") to walk from start to goal, or
None if unreachable. The caller (walk_to) snapshots passability from the live
tilemap and executes the moves.
"""
import heapq

# GBA screen convention: Up decreases Y (north), Down increases Y (south).
_MOVES = (("Up", 0, -1), ("Down", 0, 1), ("Left", -1, 0), ("Right", 1, 0))


def find_path(start, goal, passable, width, height, max_nodes=8000):
    """Shortest 4-connected path from start to goal over passable tiles.

    Returns a list of direction strings, [] if already at goal, or None if no
    path exists (or the search exceeds max_nodes). The goal tile must itself be
    passable. start is assumed reachable/standable (the player is on it).
    """
    if start == goal:
        return []
    gx, gy = goal
    if not (0 <= gx < width and 0 <= gy < height) or not passable(gx, gy):
        return None

    sx, sy = start
    open_heap = [(abs(sx - gx) + abs(sy - gy), 0, start)]
    came = {start: None}       # node -> (prev, move) ; start maps to None
    best = {start: 0}
    expanded = 0

    while open_heap and expanded < max_nodes:
        _, g, cur = heapq.heappop(open_heap)
        if cur == goal:
            moves = []
            node = cur
            while came[node] is not None:
                prev, mv = came[node]
                moves.append(mv)
                node = prev
            moves.reverse()
            return moves
        if g > best.get(cur, g):
            continue
        expanded += 1
        cx, cy = cur
        for name, dx, dy in _MOVES:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if not passable(nx, ny):
                continue
            ng = g + 1
            if ng < best.get((nx, ny), 1 << 30):
                best[(nx, ny)] = ng
                came[(nx, ny)] = (cur, name)
                heapq.heappush(open_heap, (ng + abs(nx - gx) + abs(ny - gy), ng, (nx, ny)))
    return None


def door_centers(warps):
    """Collapse contiguous warp tiles (a multi-tile doormat) to the middle tile of
    each cluster — usually the only one that actually warps (side tiles just
    "arrive" without exiting). Single warps pass through unchanged. Pure/testable."""
    clusters = []
    for w in warps:
        for cl in clusters:
            if any(abs(w[0] - x) <= 1 and abs(w[1] - y) <= 1 for x, y in cl):
                cl.append(w)
                break
        else:
            clusters.append([w])
    centers = []
    for cl in clusters:
        mx = sorted(x for x, _ in cl)[len(cl) // 2]
        my = sorted(y for _, y in cl)[len(cl) // 2]
        centers.append(min(cl, key=lambda t: abs(t[0] - mx) + abs(t[1] - my)))
    return centers
