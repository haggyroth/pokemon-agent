"""
tools/diagnostic_tilemap.py — Tilemap / Collision Address Discovery

WHAT THIS DOES
  1. Scans EWRAM for gMapHeader (fingerprint: 3 consecutive ROM pointers
     where the first resolves to a valid MapLayout struct).
  2. Reads the tile grid around the player using the metatile attribute
     pointer chain → behavior byte (lower 8 bits = passability code).
  3. Auto-moves the player one tile right, rescans EWRAM for any u16 pair
     that shifted by (+1, 0) → those are the live player coordinates.

HOW TO USE — three comparison runs to decode passability:

  Position A  stand on open walkable floor
              python tools/diagnostic_tilemap.py
              Note Behavior values for N/S/E/W tiles.

  Position B  stand directly adjacent to a wall, facing it
              Run again. The tile in that direction will show a different
              Behavior byte — that is the wall / impassable code.

  Position C  face water, ledge, or tall grass and run again.

POINTER CHAIN (pokefirered decomp):
  gMapHeader (EWRAM, linker-determined):
    +0x00  MapLayout *mapLayout   → ROM pointer
    +0x04  MapEvents *events      → ROM pointer
    +0x08  u8 *mapScripts         → ROM pointer
    +0x0C  MapConnections *conn   → ROM or NULL
    +0x10  u16 music              (small integer)
    +0x12  u16 mapLayoutId        (small integer)
    +0x14  u8 regionMapSectionId  (< 0x80)
  MapLayout (ROM):
    +0x00  s32 width
    +0x04  s32 height
    +0x08  u16 *border            → ROM
    +0x0C  u16 *map               → ROM  (u16 per tile: bits[0:9] = metatileID)
    +0x10  Tileset *primaryTileset → ROM
    +0x14  Tileset *secondaryTileset → ROM
  Tileset (ROM):
    +0x14  u32 *metatileAttributes → ROM  (4 bytes each)
  metatileAttributes[id]:
    bits[0:7] = behavior byte (0x00 = MB_NORMAL / passable)
"""
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.table import Table
from rich import box

from game.mgba_client import MGBAClient
from game.constants import Addr

console = Console()

ROM_LO = 0x08000000
ROM_HI = 0x0A000000


def is_rom(v: int) -> bool:
    return ROM_LO <= v < ROM_HI


def u32le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "little")


def u16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 2], "little")


# ── Pointer-chain helpers ────────────────────────────────────────────────────

def read_map_layout(mgba: MGBAClient, layout_ptr: int) -> dict | None:
    """Read MapLayout from ROM. All 4 internal pointers must be ROM addresses."""
    try:
        raw = mgba.read_range(layout_ptr, 0x1A)
        if len(raw) < 0x18:
            return None
        d = {
            "width":            u32le(raw, 0x00),
            "height":           u32le(raw, 0x04),
            "border_ptr":       u32le(raw, 0x08),
            "map_ptr":          u32le(raw, 0x0C),
            "primary_ts_ptr":   u32le(raw, 0x10),
            "secondary_ts_ptr": u32le(raw, 0x14),
        }
        for key in ("border_ptr", "map_ptr", "primary_ts_ptr", "secondary_ts_ptr"):
            if not is_rom(d[key]):
                return None
        if not (5 <= d["width"] <= 200 and 5 <= d["height"] <= 200):
            return None
        return d
    except Exception:
        return None


def read_tile(mgba: MGBAClient, map_ptr: int, width: int, tx: int, ty: int) -> int | None:
    try:
        raw = mgba.read_range(map_ptr + (ty * width + tx) * 2, 2)
        return u16le(raw, 0) if len(raw) >= 2 else None
    except Exception:
        return None


def read_metatile_attr(mgba: MGBAClient, layout: dict, metatile_id: int) -> int | None:
    """Follow primaryTileset or secondaryTileset → metatileAttributes[id]."""
    try:
        ts_ptr = layout["primary_ts_ptr"] if metatile_id < 512 else layout["secondary_ts_ptr"]
        idx    = metatile_id if metatile_id < 512 else metatile_id - 512
        ts_raw = mgba.read_range(ts_ptr, 0x18)
        attr_array_ptr = u32le(ts_raw, 0x14)
        if not is_rom(attr_array_ptr):
            return None
        attr_raw = mgba.read_range(attr_array_ptr + idx * 4, 4)
        return u32le(attr_raw, 0) if len(attr_raw) >= 4 else None
    except Exception:
        return None


# ── EWRAM scan ───────────────────────────────────────────────────────────────

def scan_ewram_for_header(mgba: MGBAClient) -> tuple[int, dict] | None:
    """
    Find gMapHeader without needing player position.

    Fingerprint: 3 consecutive ROM pointers at 4-byte alignment
    (mapLayout, events, mapScripts = offsets 0, 4, 8 of MapHeader).
    Validated by: all 4 MapLayout pointer fields are ROM, sane dimensions,
    plausible MapHeader music/region fields.
    """
    CHUNK  = 4096
    OVERLAP = 12  # avoid misses at chunk boundaries

    scan_ranges = [
        (0x02028000, 0x02040000),   # targeted — map data tends to live here
        (0x02000000, 0x02028000),   # full EWRAM fallback
    ]

    for range_start, range_end in scan_ranges:
        console.print(f"  [dim]Scanning 0x{range_start:08X}–0x{range_end:08X}...[/]")
        addr = range_start
        while addr < range_end:
            length = min(CHUNK + OVERLAP, range_end - addr)
            try:
                chunk = mgba.read_range(addr, length)
            except Exception as e:
                console.print(f"  [red]Read error at 0x{addr:08X}: {e}[/]")
                addr += CHUNK
                continue

            for i in range(0, len(chunk) - 11, 4):
                w0 = u32le(chunk, i)
                w1 = u32le(chunk, i + 4)
                w2 = u32le(chunk, i + 8)
                if not (is_rom(w0) and is_rom(w1) and is_rom(w2)):
                    continue

                candidate = addr + i
                layout = read_map_layout(mgba, w0)
                if layout is None:
                    continue

                # Extra MapHeader sanity: music ID and region section at known offsets
                try:
                    hdr = mgba.read_range(candidate + 0x10, 6)
                    if len(hdr) < 6:
                        continue
                    music_id      = u16le(hdr, 0)   # offset 0x10 in MapHeader
                    region_section = hdr[4]           # offset 0x14 in MapHeader
                    if music_id >= 0x300 or region_section >= 0x80:
                        continue
                except Exception:
                    continue

                return candidate, layout

            addr += CHUNK

    return None


def scan_coord_candidates(mgba: MGBAClient, width: int, height: int) -> dict[int, tuple[int, int]]:
    """
    Scan EWRAM for u16 pairs (x, y) where x ∈ [0, width) and y ∈ [0, height).
    Returns {wram_addr: (x, y)} for all candidates.
    """
    CHUNK = 4096
    candidates: dict[int, tuple[int, int]] = {}
    addr = 0x02000000
    while addr < 0x02040000:
        length = min(CHUNK + 4, 0x02040000 - addr)
        try:
            chunk = mgba.read_range(addr, length)
        except Exception:
            addr += CHUNK
            continue
        for i in range(0, len(chunk) - 3, 4):
            x = u16le(chunk, i)
            y = u16le(chunk, i + 2)
            if 0 <= x < width and 0 <= y < height:
                candidates[addr + i] = (x, y)
        addr += CHUNK
    return candidates


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    console.rule("[bold green]Tilemap / Collision Diagnostic")

    mgba = MGBAClient()
    try:
        code = mgba.get_game_code()
        if "BPGE" not in code:
            console.print(f"[red]Wrong ROM: {code!r}. Expected AGB-BPGE (LeafGreen).[/]")
            return
        console.print(f"[green]Connected: {mgba.get_game_title()} ({code})[/]")
    except Exception as e:
        console.print(f"[red]Cannot reach mGBA-http: {e}[/]")
        return

    bank = mgba.read8(Addr.MAP_BANK)
    mid  = mgba.read8(Addr.MAP_ID)
    try:
        # Always indirect — DMA block address changes on map transitions
        player_ptr = mgba.read32(Addr.PLAYER_PTR)
        raw_px     = mgba.read16(player_ptr)       # Camera X = player tile X
        raw_py     = mgba.read16(player_ptr + 2)   # Camera Y = player tile Y
        console.print(f"Map: bank={bank} id={mid}   "
                      f"Player (live via [0x03005008]): ({raw_px}, {raw_py})   "
                      f"DMA block=0x{player_ptr:08X}")
    except Exception as e:
        raw_px, raw_py = 0, 0
        console.print(f"Map: bank={bank} id={mid}   Player read failed: {e}")

    # ── 1. Locate gMapHeader ──────────────────────────────────────────────
    console.print("\n[bold cyan]── 1. Locating gMapHeader ──[/]")

    # Fast path: DataCrystal-confirmed address 0x02036DFC
    KNOWN_HEADER = Addr.MAP_HEADER
    fast_layout  = read_map_layout(mgba, mgba.read32(KNOWN_HEADER))
    if fast_layout is not None:
        header_addr = KNOWN_HEADER
        layout      = fast_layout
        console.print(f"  [green]VERIFIED[/]  gMapHeader = [bold]0x{header_addr:08X}[/]  (DataCrystal fast path)")
    else:
        console.print(f"  0x{KNOWN_HEADER:08X} didn't validate — falling back to EWRAM scan...")
        result = scan_ewram_for_header(mgba)
        if result is None:
            console.print("[red]  gMapHeader not found. Load a save, walk around, then retry.[/]")
            return
        header_addr, layout = result
        console.print(f"  [green]FOUND[/]  gMapHeader = [bold]0x{header_addr:08X}[/]  (scan)")
    w, h = layout["width"], layout["height"]

    console.print(f"  [green]FOUND[/]  gMapHeader     = [bold]0x{header_addr:08X}[/]")
    console.print(f"           map_ptr       = 0x{layout['map_ptr']:08X}  (u16[] in ROM)")
    console.print(f"           dimensions    = {w} × {h} tiles")
    console.print(f"           primaryTS     = 0x{layout['primary_ts_ptr']:08X}")
    console.print(f"           secondaryTS   = 0x{layout['secondary_ts_ptr']:08X}")

    # ── 2. Find live player coordinates via auto-move ─────────────────────
    console.print("\n[bold cyan]── 2. Live Player Coordinate Search ──[/]")
    console.print(f"  Map is {w}×{h}. Scanning EWRAM for u16 pairs in [0,{w}) × [0,{h})...")

    before = scan_coord_candidates(mgba, w, h)
    console.print(f"  Found {len(before)} candidate address(es) before move.")

    console.print("  Pressing Right (1 tile) and waiting...")
    mgba.tap("Right")
    time.sleep(0.35)   # ~21 frames — enough for one tile step

    after = scan_coord_candidates(mgba, w, h)

    # Find addresses where value changed by exactly (+1, 0)
    moved_right: list[tuple[int, int, int]] = []   # (addr, x_before, y_before)
    moved_any:   list[tuple[int, int, int, int]] = []

    for addr, (bx, by) in before.items():
        if addr not in after:
            continue
        ax, ay = after[addr]
        if ax == bx + 1 and ay == by:
            moved_right.append((addr, bx, by))
        elif (ax, ay) != (bx, by):
            moved_any.append((addr, bx, by, ax * 65536 + ay))

    # OW sprite slots contain per-NPC tile coordinates — exclude them so a
    # walking NPC can't be mistaken for the player during the auto-move scan.
    # RAM map: OW 00 (player) at 0x02036E38, 16 slots × 36 bytes = 0x02037078.
    OW_START, OW_END = 0x02036E38, 0x02037078
    moved_right = [(a, bx, by) for a, bx, by in moved_right
                   if not (OW_START <= a < OW_END)]

    if moved_right:
        console.print(f"\n  [bold green]Live player coords found — shifted (+1,0) as expected:[/]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        t.add_column("WRAM addr",    width=14)
        t.add_column("Before (x,y)", width=14)
        t.add_column("After (x,y)",  width=14)
        t.add_column("Verdict")

        # Prefer the candidate whose "before" value matches the initial player read
        best = next(
            (addr for addr, bx, by in moved_right if (bx, by) == (raw_px, raw_py)),
            moved_right[0][0],
        )

        for addr, bx, by in moved_right:
            ax, ay = after[addr]
            verdict = "[bold green]← BEST MATCH[/]" if addr == best else "[dim]also shifted[/]"
            t.add_row(f"0x{addr:08X}", f"({bx},{by})", f"({ax},{ay})", verdict)
        console.print(t)
        console.print(f"\n  [bold]Add to game/constants.py:[/]")
        console.print(f"    PLAYER_X = 0x{best:08X}   # live tile X (confirmed)")
        console.print(f"    PLAYER_Y = 0x{best + 2:08X}   # live tile Y (+2 bytes)")
    else:
        console.print("  [yellow]No address shifted by exactly (+1,0).[/]")
        console.print("  Possible reasons: player was blocked by a wall to the right,")
        console.print("  or the step animation hasn't finished. Try moving to open ground")
        console.print("  and re-running, OR check these addresses that changed at all:")
        for addr, bx, by, _ in moved_any[:12]:
            ax, ay = after.get(addr, (0,0))
            console.print(f"    0x{addr:08X}  ({bx},{by}) → ({ax},{ay})")

    # Re-read live coords if we found them
    live_px, live_py = None, None
    if moved_right:
        best_addr = moved_right[0][0]
        live_px, live_py = after[best_addr]

    # ── 3. Tile Grid ──────────────────────────────────────────────────────
    console.print("\n[bold cyan]── 3. Tile Grid (player + cardinal directions) ──[/]")

    if live_px is None:
        console.print("  [yellow]No confirmed live coordinates — using raw PLAYER_X/Y from constants.[/]")
        console.print("  Fix Addr.PLAYER_X/Y and re-run for accurate tile reads.\n")
        px, py = raw_px, raw_py
    else:
        px, py = live_px, live_py
        console.print(f"  Using confirmed live position: ({px}, {py})\n")

    if not (0 <= px < w and 0 <= py < h):
        console.print(f"  [red]Position ({px},{py}) is outside map bounds {w}×{h} — skipping tile grid.[/]")
    else:
        DIRS = [("HERE", 0, 0), ("N", 0, -1), ("S", 0, 1), ("W", -1, 0), ("E", 1, 0)]

        t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        t.add_column("Dir",        width=5)
        t.add_column("(x,y)",      width=10)
        t.add_column("u16",        width=8)
        t.add_column("MetatileID", width=13)
        t.add_column("Attr u32",   width=12)
        t.add_column("Behavior",   width=10)
        t.add_column("Note")

        for label, dx, dy in DIRS:
            tx, ty = px + dx, py + dy
            if not (0 <= tx < w and 0 <= ty < h):
                t.add_row(label, f"({tx},{ty})", "—", "—", "—", "—", "[dim]out of bounds[/]")
                continue

            tile = read_tile(mgba, layout["map_ptr"], w, tx, ty)
            if tile is None:
                t.add_row(label, f"({tx},{ty})", "ERR", "—", "—", "—", "read failed")
                continue

            metatile_id = tile & 0x3FF
            attr = read_metatile_attr(mgba, layout, metatile_id)
            attr_str = f"0x{attr:08X}" if attr is not None else "[dim]—[/]"
            beh_str  = f"0x{attr & 0xFF:02X}" if attr is not None else "[dim]—[/]"
            note     = "[bold yellow]← you are here[/]" if label == "HERE" else ""

            t.add_row(
                label, f"({tx},{ty})", f"0x{tile:04X}",
                f"0x{metatile_id:03X} ({metatile_id})",
                attr_str, beh_str, note,
            )

        console.print(t)

        # Full tile breakdown — elevation bits are the passability signal
        console.print("  [bold]Full tile breakdown (untruncated):[/]")
        console.print("  [dim]elevation = tile[15:12]  collision = tile[11:10]  metatile = tile[9:0][/]")
        console.print("  [dim]elevation 3 = walkable floor  |  elevation 0 = impassable (wall/tree)[/]")
        for label, dx, dy in DIRS:
            tx, ty = px + dx, py + dy
            if not (0 <= tx < w and 0 <= ty < h):
                continue
            tile = read_tile(mgba, layout["map_ptr"], w, tx, ty)
            if tile is None:
                continue
            metatile_id = tile & 0x3FF
            collision   = (tile >> 10) & 0x3
            elevation   = (tile >> 12) & 0xF
            passable    = elevation != 0
            flag = "[green]PASS[/]" if passable else "[red]WALL[/]"
            console.print(
                f"    {flag} {label:5s} ({tx:3d},{ty:3d})  "
                f"tile=0x{tile:04X}  elev={elevation}  coll={collision}  meta={metatile_id:4d}"
            )

    # ── 4. Summary ────────────────────────────────────────────────────────
    console.print("\n[bold cyan]── 4. Summary ──[/]")
    console.print(f"  gMapHeader  = 0x{header_addr:08X}")
    console.print(f"  map[]       = 0x{layout['map_ptr']:08X}")
    console.print(f"  map size    = {w} × {h} tiles")
    if live_px is not None:
        best_addr = moved_right[0][0]
        console.print(f"  PLAYER_X    = 0x{best_addr:08X}  (confirmed live)")
        console.print(f"  PLAYER_Y    = 0x{best_addr + 2:08X}  (confirmed live)")
    else:
        console.print(f"  PLAYER_X/Y  = not yet confirmed (re-run on open ground)")

    console.print("""
Behavior byte key (compare Position A vs B vs C runs):
  0x00  MB_NORMAL        — open passable floor
  other  wall / water / ledge / grass — note the exact value from your B/C runs

Once you have all values, add to game/constants.py:
  MAP_HEADER = 0x{header:08X}
  PLAYER_X   = 0x????????  (from section 2 above)
  PLAYER_Y   = PLAYER_X + 2
  MB_PASSABLE = {mb}  # behavior byte for open floor
  MB_WALL     = ???   # fill in from Position B run
""".format(
        header=header_addr,
        mb="0x00 (typical)" if live_px is None else "0x00 (typical)",
    ))


if __name__ == "__main__":
    run()
