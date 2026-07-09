"""Overworld map connection graph — which map edge leads to which map.

GENERATED from the pret/pokefirered decomp map data (data/maps/*/map.json +
map_groups.json). Keys/values are (map_bank, map_id) matching game/constants and
knowledge.navigation.MAP_NAMES. Direction = the edge you cross to reach the
neighbour. Regenerate with tools/gen_map_graph.py if maps change.

These are seamless edge CONNECTIONS only (not building/cave warps), so a route
here is map-adjacency; a hop can still be unwalkable if a dungeon blocks the map
(e.g. Mt. Moon splits Route 4) — go_to executes hop-by-hop and stops if blocked."""
from collections import deque

MAP_CONNECTIONS: dict[tuple[int, int], dict[str, tuple[int, int]]] = {
    (3, 0): {"North": (3, 19), "South": (3, 39)},
    (3, 1): {"North": (3, 20), "South": (3, 19), "West": (3, 41)},
    (3, 2): {"East": (3, 21), "South": (3, 20)},
    (3, 3): {"East": (3, 27), "North": (3, 43), "South": (3, 23), "West": (3, 22)},
    (3, 4): {"North": (3, 28), "South": (3, 30), "West": (3, 26)},
    (3, 5): {"East": (3, 29), "North": (3, 24)},
    (3, 6): {"East": (3, 25), "West": (3, 34)},
    (3, 7): {"East": (3, 33), "South": (3, 37), "West": (3, 36)},
    (3, 8): {"East": (3, 38), "North": (3, 40)},
    (3, 9): {"South": (3, 42)},
    (3, 10): {"East": (3, 26), "North": (3, 23), "South": (3, 24), "West": (3, 25)},
    (3, 11): {"East": (3, 26), "North": (3, 23), "South": (3, 24), "West": (3, 25)},
    (3, 12): {"East": (3, 45), "South": (3, 46)},
    (3, 13): {"North": (3, 47)},
    (3, 14): {"South": (3, 49), "West": (3, 48)},
    (3, 16): {"East": (3, 56), "North": (3, 55)},
    (3, 17): {"North": (3, 62), "South": (3, 63)},
    (3, 18): {"East": (3, 60)},
    (3, 19): {"North": (3, 1), "South": (3, 0)},
    (3, 20): {"North": (3, 2), "South": (3, 1)},
    (3, 21): {"North": (3, 22), "West": (3, 2)},
    (3, 22): {"East": (3, 3), "South": (3, 21)},
    (3, 23): {"North": (3, 3), "South": (3, 11)},
    (3, 24): {"North": (3, 11), "South": (3, 5)},
    (3, 25): {"East": (3, 11), "West": (3, 6)},
    (3, 26): {"East": (3, 4), "West": (3, 11)},
    (3, 27): {"East": (3, 28), "West": (3, 3)},
    (3, 28): {"South": (3, 4), "West": (3, 27)},
    (3, 29): {"East": (3, 30), "West": (3, 5)},
    (3, 30): {"North": (3, 4), "South": (3, 31), "West": (3, 29)},
    (3, 31): {"North": (3, 30), "West": (3, 32)},
    (3, 32): {"East": (3, 31), "West": (3, 33)},
    (3, 33): {"East": (3, 32), "West": (3, 7)},
    (3, 34): {"East": (3, 6), "South": (3, 35)},
    (3, 35): {"North": (3, 34), "South": (3, 36)},
    (3, 36): {"East": (3, 7), "North": (3, 35)},
    (3, 37): {"North": (3, 7), "West": (3, 38)},
    (3, 38): {"East": (3, 37), "West": (3, 8)},
    (3, 39): {"North": (3, 0), "South": (3, 40)},
    (3, 40): {"North": (3, 39), "South": (3, 8)},
    (3, 41): {"East": (3, 1), "North": (3, 42)},
    (3, 42): {"North": (3, 9), "South": (3, 41)},
    (3, 43): {"East": (3, 44), "South": (3, 3)},
    (3, 44): {"West": (3, 43)},
    (3, 45): {"West": (3, 12)},
    (3, 46): {"North": (3, 12)},
    (3, 47): {"South": (3, 13)},
    (3, 48): {"East": (3, 14)},
    (3, 49): {"North": (3, 14)},
    (3, 50): {"North": (3, 14)},
    (3, 51): {"North": (3, 14)},
    (3, 54): {"South": (3, 55)},
    (3, 55): {"North": (3, 54), "South": (3, 16)},
    (3, 56): {"East": (3, 57), "West": (3, 16)},
    (3, 57): {"West": (3, 56)},
    (3, 58): {"South": (3, 59)},
    (3, 59): {"East": (3, 60), "North": (3, 58)},
    (3, 60): {"West": (3, 61)},
    (3, 61): {"East": (3, 60)},
    (3, 62): {"South": (3, 17)},
    (3, 63): {"East": (3, 64), "North": (3, 17)},
    (3, 64): {"South": (3, 65), "West": (3, 63)},
    (3, 65): {"North": (3, 64)},
}


def bfs_route(start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[str, tuple[int, int]]] | None:
    """Shortest connection route from start to goal as [(direction, next_map), ...],
    [] if already there, or None if unreachable via connections."""
    if start == goal:
        return []
    q = deque([(start, [])])
    seen = {start}
    while q:
        cur, path = q.popleft()
        for direction, nb in sorted(MAP_CONNECTIONS.get(cur, {}).items()):
            if nb == goal:
                return path + [(direction, nb)]
            if nb not in seen:
                seen.add(nb)
                q.append((nb, path + [(direction, nb)]))
    return None
