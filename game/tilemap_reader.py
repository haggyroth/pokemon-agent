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
