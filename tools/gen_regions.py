#!/usr/bin/env python3
"""Generate knowledge/map_regions.py — walkable-region data for EVERY map — from the decomp.

Usage:
    python tools/gen_regions.py [path-to-pokefirered] > knowledge/map_regions.py

Why: many maps are ONE map id but several DISCONNECTED walkable regions (Mt. Moon's
floors, Route 2/4, Rock Tunnel, Seafoam, Silph Co., Pokémon Tower/Mansion, …). Routing
treated every map as a single node, so each new cave needed a hand-made fix. This derives
the regions mechanically, so any map is handled by the same router:

  * passability  = exactly what game/tilemap_reader.passable_grid() uses: a block is
                   walkable iff its elevation nibble == 3 (map.bin u16: id | collision<<10 | elev<<12)
  * regions      = 4-connected components of the walkable tiles
  * "interesting"= a region that touches a warp or a seamless-connection edge. A map with
                   >= 2 interesting regions is "split"; its routing nodes are (bank, id, tag).
  * arrival tags = which region you land in via each warp / seamless connection, from the
                   decomp's dest_warp_id pairing and the connection offsets.

Dynamic blockers the tilemap can't show (HM obstacles, card-key doors, switch doors, boulders)
are NOT modelled here; the runtime handles those (see nav._go_to blocked-edge learning).
"""
import json
import os
import re
import sys

ELEV_FLOOR = 3
DIRW = {"up": "North", "down": "South", "left": "West", "right": "East"}
ALPHA = "0123456789abcdefghijklmnopqrstuvwxyz"


def load(pf):
    groups = json.load(open(f"{pf}/data/maps/map_groups.json"))
    layouts = {l["id"]: l for l in json.load(open(f"{pf}/data/layouts/layouts.json"))["layouts"] if "id" in l}
    maps, const_to_gn = {}, {}
    for gi, gname in enumerate(groups["group_order"]):
        if not gname.startswith("gMapGroup_"):
            continue
        for ni, dname in enumerate(groups[gname]):
            mj = f"{pf}/data/maps/{dname}/map.json"
            if os.path.exists(mj):
                d = json.load(open(mj))
                const_to_gn[d["id"]] = (gi, ni)
                maps[(gi, ni)] = d
    return maps, const_to_gn, layouts


def tileset_attrs(pf):
    """gTileset_X -> list of u32 metatile attributes (behavior = attr & 0x1FF)."""
    hdr = open(f"{pf}/src/data/tilesets/headers.h").read()
    inc = open(f"{pf}/src/data/tilesets/metatiles.h").read()
    path = dict(re.findall(r'const u32 (gMetatileAttributes_\w+)\[\] = INCBIN_U32\("([^"]+)"\)', inc))
    out = {}
    for name, body in re.findall(r"const struct Tileset (gTileset_\w+)\s*=\s*\{(.*?)\};", hdr, re.S):
        m = re.search(r"\.metatileAttributes\s*=\s*(\w+)", body)
        if m and m.group(1) in path:
            raw = open(f"{pf}/{path[m.group(1)]}", "rb").read()
            out[name] = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw) - 3, 4)]
    return out


LEDGE = {0x38: (1, 0), 0x39: (-1, 0), 0x3A: (0, -1), 0x3B: (0, 1)}   # MB_JUMP_E/W/N/S
NUM_PRIMARY = 640
# Objects that physically block a tile until the right HM/event (Cut tree, Rock Smash rock,
# Strength boulder, sleeping Snorlax). The tilemap shows them as plain floor, so without this
# a Cut-tree-sealed gate looked reachable (Route 2's east building). Treated as walls here;
# route_to falls back to the optimistic graph when this strict view finds no route.
BLOCKER_GFX = ("CUT_TREE", "ROCK_SMASH_ROCK", "PUSHABLE_BOULDER", "SNORLAX")


def ledge_tiles(pf, layout, attrs):
    """[(x, y, dx, dy)] of one-way ledge tiles on the layout."""
    prim, sec = attrs.get(layout["primary_tileset"]), attrs.get(layout["secondary_tileset"])
    w, h = layout["width"], layout["height"]
    raw = open(f"{pf}/{layout['blockdata_filepath']}", "rb").read()
    out = []
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 2
            if i + 1 >= len(raw):
                continue
            mid = (raw[i] | (raw[i + 1] << 8)) & 0x3FF
            arr, idx = (prim, mid) if mid < NUM_PRIMARY else (sec, mid - NUM_PRIMARY)
            if arr is None or idx >= len(arr):
                continue
            beh = arr[idx] & 0x1FF
            if beh in LEDGE:
                out.append((x, y) + LEDGE[beh])
    return out


def grid_for(pf, layout):
    w, h = layout["width"], layout["height"]
    raw = open(f"{pf}/{layout['blockdata_filepath']}", "rb").read()
    g = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 2
            if i + 1 < len(raw):
                v = raw[i] | (raw[i + 1] << 8)
                g[y][x] = ((v >> 12) & 0xF) == ELEV_FLOOR
    return g, w, h


def components(g, w, h):
    lab = [[-1] * w for _ in range(h)]
    n = 0
    for y in range(h):
        for x in range(w):
            if g[y][x] and lab[y][x] < 0:
                stack = [(x, y)]
                lab[y][x] = n
                while stack:
                    cx, cy = stack.pop()
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and g[ny][nx] and lab[ny][nx] < 0:
                            lab[ny][nx] = n
                            stack.append((nx, ny))
                n += 1
    return lab, n


def arrival_label(lab, w, h, x, y):
    """Region you stand in after a warp lands on (x, y): the tile itself if walkable, else
    the tile the game walks you out onto (prefer south/the doormat exit)."""
    for nx, ny in ((x, y), (x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y)):
        if 0 <= nx < w and 0 <= ny < h and lab[ny][nx] >= 0:
            return lab[ny][nx]
    return None


def departure_labels(lab, w, h, x, y):
    """Regions from which you can step onto warp tile (x, y)."""
    out = set()
    for nx, ny in ((x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < w and 0 <= ny < h and lab[ny][nx] >= 0:
            out.add(lab[ny][nx])
    return out


def main():
    pf = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Projects/pokefirered")
    maps, c2g, layouts = load(pf)
    attrs = tileset_attrs(pf)
    info = {}   # gn -> dict(lab, w, h, interesting set, remap)
    for gn, d in maps.items():
        lay = layouts.get(d.get("layout"))
        if not lay:
            continue
        g, w, h = grid_for(pf, lay)
        for o in d.get("object_events") or []:
            if any(k in o.get("graphics_id", "") for k in BLOCKER_GFX):
                ox, oy = int(o["x"]), int(o["y"])
                if 0 <= ox < w and 0 <= oy < h:
                    g[oy][ox] = False
        lab, n = components(g, w, h)
        touch = set()
        for wv in d.get("warp_events") or []:
            touch |= departure_labels(lab, w, h, int(wv["x"]), int(wv["y"]))
            a = arrival_label(lab, w, h, int(wv["x"]), int(wv["y"]))
            if a is not None:
                touch.add(a)
        for c in d.get("connections") or []:
            if c["direction"] not in DIRW:
                continue
            edge = {"up": [(x, 0) for x in range(w)], "down": [(x, h - 1) for x in range(w)],
                    "left": [(0, y) for y in range(h)], "right": [(w - 1, y) for y in range(h)]}[c["direction"]]
            for (x, y) in edge:
                if lab[y][x] >= 0:
                    touch.add(lab[y][x])
        ledges = set()
        for (lx, ly, dx, dy) in ledge_tiles(pf, lay, attrs):
            ax, ay, bx, by = lx - dx, ly - dy, lx + dx, ly + dy
            if 0 <= ax < w and 0 <= ay < h and 0 <= bx < w and 0 <= by < h:
                la, lb = lab[ay][ax], lab[by][bx]
                if la >= 0 and lb >= 0 and la != lb:
                    ledges.add((la, lb))          # one-way: hop from region la down to lb
        info[gn] = dict(lab=lab, w=w, h=h, touch=touch, ledges=ledges)
    # Incoming connections also make a region interesting on the DESTINATION side.
    for gn, d in maps.items():
        for c in d.get("connections") or []:
            dst = c2g.get(c["map"])
            if dst in info and c["direction"] in DIRW:
                _mark_incoming(info, gn, d, c, dst)
    split = {gn: sorted(v["touch"]) for gn, v in info.items() if len(v["touch"]) >= 2}
    tag = {gn: {lbl: ALPHA[i] for i, lbl in enumerate(lbls)} for gn, lbls in split.items()}

    def node_tag(gn, lbl):
        return tag[gn].get(lbl) if gn in split else None

    out = sys.stdout
    out.write('"""Walkable-region data for every split map. GENERATED by tools/gen_regions.py —\n')
    out.write('do not edit. See that file for the model. Keys are (map_bank, map_id)."""\n\n')
    out.write("# Maps with >= 2 disconnected walkable regions that touch a warp/connection.\n")
    out.write("# Rows: '#' = not walkable (or an unreachable pocket), else the region tag char.\n")
    out.write("REGION_GRIDS: dict[tuple[int, int], list[str]] = {\n")
    for gn in sorted(split):
        v = info[gn]
        out.write(f"    {gn}: [\n")
        for y in range(v["h"]):
            row = "".join(tag[gn].get(v["lab"][y][x], "#") if v["lab"][y][x] >= 0 else "#" for x in range(v["w"]))
            out.write(f'        "{row}",\n')
        out.write("    ],\n")
    out.write("}\n\n")

    # warp arrival tags (only needed when the DEST map is split)
    out.write("# (src map, (warp x, y)) -> (dest map, region tag you land in)  [dest maps that are split]\n")
    out.write("WARP_ARRIVAL: dict[tuple, tuple[tuple[int, int], str]] = {\n")
    for gn in sorted(maps):
        d = maps[gn]
        for wv in d.get("warp_events") or []:
            dst = c2g.get(wv["dest_map"])
            if dst not in split:
                continue
            did = int(wv["dest_warp_id"])
            dwarps = maps[dst].get("warp_events") or []
            if did >= len(dwarps):
                continue
            dx, dy = int(dwarps[did]["x"]), int(dwarps[did]["y"])
            v = info[dst]
            a = arrival_label(v["lab"], v["w"], v["h"], dx, dy)
            t = node_tag(dst, a)
            if t:
                out.write(f"    ({gn}, ({int(wv['x'])}, {int(wv['y'])})): ({dst}, \"{t}\"),\n")
    out.write("}\n\n")

    # seamless connections: (src map, direction) -> [(src tag|None, dest map, dest tag|None)]
    out.write("# (src map, direction, dest map) -> [(src region tag or None, dest region tag or None)]\n")
    out.write("CONN_LINKS: dict[tuple, list[tuple]] = {\n")
    for gn in sorted(maps):
        d = maps[gn]
        if gn not in info:
            continue
        for c in d.get("connections") or []:
            dst = c2g.get(c["map"])
            dr = DIRW.get(c["direction"])
            if dst not in info or not dr:
                continue
            links = set()
            vs, vd = info[gn], info[dst]
            for (x, y, tx, ty) in _edge_pairs(c["direction"], int(c["offset"]), vs["w"], vs["h"], vd["w"], vd["h"]):
                ls, ld = vs["lab"][y][x], vd["lab"][ty][tx]
                if ls < 0 or ld < 0:
                    continue
                links.add((node_tag(gn, ls), node_tag(dst, ld)))
            if links and (gn in split or dst in split):
                out.write(f"    ({gn}, \"{dr}\", {dst}): [{', '.join(f'({a!r}, {b!r})' for a, b in sorted(links, key=str))}],\n")
    out.write("}\n\n")
    out.write("# One-way ledge hops between regions of the same map: (from tag, to tag). A region can\n")
    out.write("# use any warp/edge reachable from a region it can ledge-hop into.\n")
    out.write("LEDGE_LINKS: dict[tuple[int, int], list[tuple[str, str]]] = {\n")
    for gn in sorted(split):
        links = sorted({(tag[gn][a], tag[gn][b]) for (a, b) in info[gn]["ledges"]
                        if a in tag[gn] and b in tag[gn]})
        if links:
            out.write(f"    {gn}: {links!r},\n")
    out.write("}\n")


def _edge_pairs(direction, off, ws, hs, wd, hd):
    """Yield (src_x, src_y, dest_x, dest_y) for every src edge tile that has a dest tile."""
    if direction == "right":
        for y in range(hs):
            ty = y - off
            if 0 <= ty < hd:
                yield (ws - 1, y, 0, ty)
    elif direction == "left":
        for y in range(hs):
            ty = y - off
            if 0 <= ty < hd:
                yield (0, y, wd - 1, ty)
    elif direction == "down":
        for x in range(ws):
            tx = x - off
            if 0 <= tx < wd:
                yield (x, hs - 1, tx, 0)
    elif direction == "up":
        for x in range(ws):
            tx = x - off
            if 0 <= tx < wd:
                yield (x, 0, tx, hd - 1)


def _mark_incoming(info, gn, d, c, dst):
    vs, vd = info[gn], info[dst]
    for (x, y, tx, ty) in _edge_pairs(c["direction"], int(c["offset"]), vs["w"], vs["h"], vd["w"], vd["h"]):
        if vd["lab"][ty][tx] >= 0:
            vd["touch"].add(vd["lab"][ty][tx])


if __name__ == "__main__":
    main()
