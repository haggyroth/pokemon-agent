"""
game/tilemap_reader.py — ROM map tile passability reader.

Reads the u16 map[] array from gMapHeader.mapLayout (ROM).
Passability is encoded in bits 12-15 (elevation field) of each tile entry:

  elevation 3 (0x3xxx) — normal walkable floor
  elevation 1 (0x1xxx) — water (needs Surf; behavior byte typically 0x13–0x16)
  elevation 0 (0x0xxx) — impassable: trees, building walls, fences
  elevation 2 (0x2xxx) — not observed yet; treated as impassable by default

Empirically verified via diagnostic_tilemap.py on FRLG US (AGB-BPGE):
  - Viridian City floor tiles:    0x316F, 0x316E → elev=3 ✓ passable
  - Viridian City tree:           0x0016        → elev=0 ✗ wall
  - Pokemon Center building wall: 0x04BA        → elev=0 ✗ wall
  - Pallet Town floor:            0x3009        → elev=3 ✓ passable
  - Pallet Town water:            0x112A        → elev=1 ✗ water (no Surf)
"""
from dataclasses import dataclass
from game.mgba_client import MGBAClient
from game.constants import Addr

ELEV_WALL  = 0
ELEV_WATER = 1
ELEV_FLOOR = 3


@dataclass
class TileInfo:
    tile_u16:    int
    metatile_id: int
    elevation:   int
    collision:   int   # bits 10-11, supplementary hint
    passable:    bool  # True = agent can walk here freely
    is_water:    bool  # True = water tile (needs Surf)


class TilemapReader:
    def __init__(self, client: MGBAClient):
        self.client = client
        self._map_ptr:  int | None = None
        self._width:    int | None = None
        self._height:   int | None = None

    def refresh(self) -> bool:
        """
        Re-read MapLayout from gMapHeader. Call after every map transition
        (i.e. whenever map_bank or map_id changes between state reads).
        """
        try:
            layout_ptr = self.client.read32(Addr.MAP_HEADER)
            if not (0x08000000 <= layout_ptr < 0x0A000000):
                return False
            self._width   = self.client.read32(layout_ptr)
            self._height  = self.client.read32(layout_ptr + 4)
            self._map_ptr = self.client.read32(layout_ptr + 0x0C)
            return True
        except Exception:
            return False

    @property
    def ready(self) -> bool:
        return self._map_ptr is not None

    def read_tile(self, x: int, y: int) -> TileInfo | None:
        """Return TileInfo for map tile (x, y), or None on error / out-of-bounds."""
        if not self.ready:
            self.refresh()
        if self._map_ptr is None:
            return None
        if not (0 <= x < self._width and 0 <= y < self._height):
            return None
        try:
            raw  = self.client.read_range(self._map_ptr + (y * self._width + x) * 2, 2)
            tile = int.from_bytes(raw, "little")
            elev = (tile >> 12) & 0xF
            return TileInfo(
                tile_u16    = tile,
                metatile_id = tile & 0x3FF,
                elevation   = elev,
                collision   = (tile >> 10) & 0x3,
                passable    = elev == ELEV_FLOOR,
                is_water    = elev == ELEV_WATER,
            )
        except Exception:
            return None

    def read_warps(self) -> list[tuple[int, int]]:
        """Warp (door/stairs/exit) tile coordinates on the current map.

        These are in the same coordinate space as the player position, so the
        agent can walk onto one to change maps. Read from gMapHeader.events:
          gMapHeader (Addr.MAP_HEADER): +0x00 mapLayout, +0x04 mapEvents.
          MapEvents: +0x01 warpCount(u8), +0x08 warps ptr.
          WarpEvent (8 bytes): x(s16 @0), y(s16 @2), elevation, warpId, mapNum, mapGroup.
        Indoor maps have 1-3 warps (the exit); returns [] on any read error.
        """
        try:
            events = self.client.read32(Addr.MAP_HEADER + 0x04)
            if not (0x02000000 <= events < 0x03100000 or 0x08000000 <= events < 0x0A000000):
                return []
            count     = self.client.read8(events + 0x01)
            warps_ptr = self.client.read32(events + 0x08)
            out = []
            for i in range(min(count, 16)):
                base = warps_ptr + i * 8
                out.append((self.client.read16(base), self.client.read16(base + 2)))
            return out
        except Exception:
            return []

    # Gen III connection direction codes (gMapHeader.connections).
    _CONN_DIR = {1: "South", 2: "North", 3: "West", 4: "East", 5: "Dive", 6: "Emerge"}

    def read_connections(self) -> list[dict]:
        """Adjacent-map connections for the current map: which edge leads where.

        Town/route exits are seamless map connections (walking off the edge loads
        the neighbour), NOT warp tiles — the tilemap just shows the border, so the
        agent can't see them without this. Read from gMapHeader.connections:
          gMapHeader +0x0C -> MapConnections{ s32 count; MapConnection* }.
          MapConnection (12 bytes): direction(u8 @0), offset(s32 @4),
                                    mapGroup(u8 @8), mapNum(u8 @9).
        Returns [{direction, offset, map_bank, map_id}], [] on error / none.
        """
        try:
            conns = self.client.read32(Addr.MAP_HEADER + 0x0C)
            if not (0x08000000 <= conns < 0x0A000000 or 0x02000000 <= conns < 0x03100000):
                return []
            count = self.client.read32(conns + 0)
            arr   = self.client.read32(conns + 4)
            out = []
            for i in range(min(count, 8)):
                b = arr + i * 12
                offset = self.client.read32(b + 4)
                if offset >= 2 ** 31:
                    offset -= 2 ** 32
                out.append({
                    "direction": self._CONN_DIR.get(self.client.read8(b), "?"),
                    "offset": offset,
                    "map_bank": self.client.read8(b + 8),
                    "map_id": self.client.read8(b + 9),
                })
            return out
        except Exception:
            return []

    def passable_directions(self, x: int, y: int) -> dict[str, bool]:
        """Return {N/S/E/W: can_walk} for each cardinal direction from (x, y)."""
        result = {}
        for label, dx, dy in (("N", 0, -1), ("S", 0, 1), ("W", -1, 0), ("E", 1, 0)):
            info = self.read_tile(x + dx, y + dy)
            result[label] = info.passable if info is not None else False
        return result

    def surroundings_str(self, x: int, y: int) -> str:
        """
        Compact one-line summary for the agent observation.
        Example: "N:floor S:wall E:floor W:water"
        """
        labels = []
        for label, dx, dy in (("N", 0, -1), ("S", 0, 1), ("W", -1, 0), ("E", 1, 0)):
            info = self.read_tile(x + dx, y + dy)
            if info is None:
                kind = "oob"
            elif info.passable:
                kind = "floor"
            elif info.is_water:
                kind = "water"
            else:
                kind = "wall"
            labels.append(f"{label}:{kind}")
        return " ".join(labels)
