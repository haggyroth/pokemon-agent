#!/usr/bin/env python3
"""Regenerate knowledge/map_graph.py from a local pret/pokefirered checkout.

Usage:
    python tools/gen_map_graph.py [path-to-pokefirered] > knowledge/map_graph.py

Emits, keyed by (map_bank, map_id) matching game/constants + MAP_NAMES:
  MAP_CONNECTIONS — seamless edge crossings: {(g,n): {direction: (g,n)}}
  MAP_WARPS       — door/stairs warps:       {(g,n): [(x, y, (g,n)), ...]}
  MAP_KIND        — special maps for waypoints: {(g,n): "pokecenter"|"mart"|"gym"}
plus routing helpers (bfs_route, route_to, nearest_of_kind). Warp x/y are in the
same coordinate space as live read_warps()/player position (verified).
"""
import json
import os
import sys

DIRW = {"up": "North", "down": "South", "left": "West", "right": "East"}


def _kind(map_const: str) -> str | None:
    if "POKEMON_CENTER_1F" in map_const:
        return "pokecenter"
    if map_const.endswith("_MART"):
        return "mart"
    if map_const.endswith("_GYM"):
        return "gym"
    return None


def build(pf: str):
    groups = json.load(open(f"{pf}/data/maps/map_groups.json"))
    order = groups["group_order"]
    const_to_gn, gn_to_const = {}, {}
    for gi, gname in enumerate(order):
        if not gname.startswith("gMapGroup_"):
            continue
        for ni, dname in enumerate(groups[gname]):
            mj = f"{pf}/data/maps/{dname}/map.json"
            if os.path.exists(mj):
                c = json.load(open(mj))["id"]
                const_to_gn[c] = (gi, ni)
                gn_to_const[(gi, ni)] = c
    conns, warps, kinds = {}, {}, {}
    for gname in order:
        if not gname.startswith("gMapGroup_"):
            continue
        for dname in groups[gname]:
            mj = f"{pf}/data/maps/{dname}/map.json"
            if not os.path.exists(mj):
                continue
            d = json.load(open(mj))
            src = const_to_gn.get(d["id"])
            if src is None:
                continue
            for c in (d.get("connections") or []):
                dst = const_to_gn.get(c["map"])
                dr = DIRW.get(c["direction"])
                if dst and dr:
                    conns.setdefault(src, {})[dr] = dst
            for w in (d.get("warp_events") or []):
                dst = const_to_gn.get(w["dest_map"])
                if dst is not None:
                    warps.setdefault(src, []).append((int(w["x"]), int(w["y"]), dst))
            k = _kind(d["id"])
            if k:
                kinds[src] = k
    return conns, warps, kinds


_HELPERS = '''

def bfs_route(start, goal):
    """Connection-only route [(direction, next_map), ...] — kept for callers that
    only want seamless edges. [] if already there, None if no connection route."""
    steps = route_to(start, goal, warps=False)
    if steps is None:
        return None
    return [(d, m) for kind, d, m in steps]


def route_to(start, goal, warps=True):
    """Shortest route from start to goal over connections (and warps if warps=True).
    Returns a list of steps, [] if already there, or None if unreachable:
      ("connection", direction, next_map)  — cross a seamless edge
      ("warp", (x, y), next_map)           — walk onto a door/stairs tile
    """
    from collections import deque
    if start == goal:
        return []
    q = deque([(start, [])])
    seen = {start}
    while q:
        cur, path = q.popleft()
        for direction, nb in sorted(MAP_CONNECTIONS.get(cur, {}).items()):
            step = ("connection", direction, nb)
            if nb == goal:
                return path + [step]
            if nb not in seen:
                seen.add(nb)
                q.append((nb, path + [step]))
        if warps:
            for (x, y, nb) in MAP_WARPS.get(cur, []):
                step = ("warp", (x, y), nb)
                if nb == goal:
                    return path + [step]
                if nb not in seen:
                    seen.add(nb)
                    q.append((nb, path + [step]))
    return None


def nearest_of_kind(start, kind):
    """Route to the nearest map of a kind ("pokecenter"/"mart"/"gym").
    Returns (goal_map, steps) or None."""
    from collections import deque
    if MAP_KIND.get(start) == kind:
        return (start, [])
    q = deque([(start, [])])
    seen = {start}
    while q:
        cur, path = q.popleft()
        neighbours = [("connection", d, m) for d, m in sorted(MAP_CONNECTIONS.get(cur, {}).items())]
        neighbours += [("warp", (x, y), m) for (x, y, m) in MAP_WARPS.get(cur, [])]
        for step in neighbours:
            nb = step[2]
            if nb in seen:
                continue
            seen.add(nb)
            if MAP_KIND.get(nb) == kind:
                return (nb, path + [step])
            q.append((nb, path + [step]))
    return None
'''


def main():
    pf = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Projects/pokefirered")
    conns, warps, kinds = build(pf)
    out = sys.stdout
    out.write('"""Overworld map graph — connections, warps, and special-map kinds.\n\n')
    out.write("GENERATED by tools/gen_map_graph.py from the pret/pokefirered decomp map data.\n")
    out.write("Keys are (map_bank, map_id) matching game/constants and MAP_NAMES. Directions\n")
    out.write("are the edge you cross; warp (x, y) are the tile to walk onto (same coordinate\n")
    out.write('space as live read_warps()/player pos)."""\n\n')
    out.write("MAP_CONNECTIONS: dict[tuple[int, int], dict[str, tuple[int, int]]] = {\n")
    for src in sorted(conns):
        edges = ", ".join(f'"{d}": {conns[src][d]}' for d in sorted(conns[src]))
        out.write(f"    {src}: {{{edges}}},\n")
    out.write("}\n\n")
    out.write("MAP_WARPS: dict[tuple[int, int], list[tuple[int, int, tuple[int, int]]]] = {\n")
    for src in sorted(warps):
        ws = ", ".join(f"({x}, {y}, {dst})" for x, y, dst in warps[src])
        out.write(f"    {src}: [{ws}],\n")
    out.write("}\n\n")
    out.write("MAP_KIND: dict[tuple[int, int], str] = {\n")
    for src in sorted(kinds):
        out.write(f'    {src}: "{kinds[src]}",\n')
    out.write("}\n")
    out.write(_HELPERS)


if __name__ == "__main__":
    main()
