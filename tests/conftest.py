"""Shared test fixtures.

These tests are hardware-free: no libmgba, no ROM, no network. The emulator is
replaced by `FakeClient`, a sparse byte-addressable memory that implements the
same read/write surface `LeafGreenReader` depends on. This lets the full Gen III
decoder and state machine be tested deterministically on any CI runner.
"""
from game.constants import Addr
from game.memory_reader import SUBSTRUCT_ORDER


class FakeClient:
    """Sparse GBA memory keyed by absolute address (defaults to 0)."""

    def __init__(self):
        self.mem: dict[int, int] = {}

    # writes used by tests to stage memory
    def set_bytes(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.mem[address + i] = b

    def set8(self, address: int, value: int) -> None:
        self.mem[address] = value & 0xFF

    def set16(self, address: int, value: int) -> None:
        self.set_bytes(address, (value & 0xFFFF).to_bytes(2, "little"))

    def set32(self, address: int, value: int) -> None:
        self.set_bytes(address, (value & 0xFFFFFFFF).to_bytes(4, "little"))

    # read/write surface consumed by LeafGreenReader
    def read8(self, address: int) -> int:
        return self.mem.get(address, 0) & 0xFF

    def read16(self, address: int) -> int:
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read32(self, address: int) -> int:
        return self.read16(address) | (self.read16(address + 2) << 16)

    def read_range(self, address: int, length: int) -> bytes:
        return bytes(self.mem.get(address + i, 0) for i in range(length))

    def write8(self, address: int, value: int) -> None:
        self.set8(address, value)


def build_party_mon(pid: int, ot_id: int, *, level: int, cur_hp: int, max_hp: int,
                    status_word: int = 0, species: int = 1,
                    moves=(1, 2, 3, 4), pp=(35, 30, 25, 20)) -> bytes:
    """Construct a valid 100-byte Gen III party slot with encrypted substructures.

    Inverse of memory_reader.decrypt_substructs: place Growth/Attacks data in the
    order dictated by pid, then XOR-encrypt with key = pid ^ ot_id.
    """
    raw = bytearray(100)
    raw[0:4] = pid.to_bytes(4, "little")
    raw[4:8] = ot_id.to_bytes(4, "little")

    # Build the four decrypted 12-byte substructures.
    growth = bytearray(12)
    growth[0:2] = species.to_bytes(2, "little")
    attacks = bytearray(12)
    for i, m in enumerate(moves):
        attacks[i * 2:i * 2 + 2] = int(m).to_bytes(2, "little")
    for i, p in enumerate(pp):
        attacks[8 + i] = p & 0xFF
    subs = {"G": bytes(growth), "A": bytes(attacks), "E": bytes(12), "M": bytes(12)}

    order = SUBSTRUCT_ORDER[pid % 24]
    plain = bytearray()
    for letter in order:
        plain += subs[letter]

    key = pid ^ ot_id
    enc = bytearray(48)
    for i in range(0, 48, 4):
        word = int.from_bytes(plain[i:i + 4], "little") ^ key
        enc[i:i + 4] = word.to_bytes(4, "little")
    raw[32:80] = enc

    # Unencrypted Tier-1 fields.
    raw[0x50:0x54] = status_word.to_bytes(4, "little")
    raw[0x54] = level & 0xFF
    raw[0x56:0x58] = cur_hp.to_bytes(2, "little")
    raw[0x58:0x5A] = max_hp.to_bytes(2, "little")
    return bytes(raw)


def stage_overworld(fc: FakeClient, *, x: int = 5, y: int = 7,
                    map_bank: int = 3, map_id: int = 0) -> None:
    """Put the FakeClient into a plausible OVERWORLD state."""
    fc.set32(Addr.GMAIN_CALLBACK2, Addr.CB2_OVERWORLD)  # field system active
    fc.set8(Addr.SCREEN_FADE, 0)
    fc.set8(Addr.SCRIPT_RAM, 0)
    fc.set32(Addr.START_MENU_CB, 0)   # no Start menu open
    fc.set8(Addr.MAP_BANK, map_bank)
    fc.set8(Addr.MAP_ID, map_id)
    ptr = 0x03005100
    fc.set32(Addr.PLAYER_PTR, ptr)
    fc.set16(ptr, x)
    fc.set16(ptr + 2, y)
