"""Helpers for staging live scenarios (party patching, forcing a wild battle, ...)."""
import pytest

from game.constants import Addr
from game.memory_reader import SUBSTRUCT_ORDER
from game.state import GameContext

B1 = Addr.BATTLE_MON0_SPECIES + 0x58          # gBattleMons[1]: the live foe


class Live:
    def __init__(self, rt, live_dir):
        self.rt, self.dir = rt, live_dir
        self.c, self.r, self.m = rt.client, rt.reader, rt.mgba

    def load(self, name: str) -> None:
        path = self.dir / f"{name}.ss1"
        if not path.exists():
            pytest.skip(f"fixture {path} missing — see tests/live/README.md")
        assert self.m.load_state_file(str(path)), f"could not load {path}"
        self.m.tick(30)
        self.heal_hp()

    def heal_hp(self) -> None:
        for i in range(len(self.r.read_party())):
            b = Addr.PARTY_DATA + 100 * i
            self.m.write16(b + 0x56, self.m.read16(b + 0x58))

    def patch_mon(self, slot, moves=None, pps=None, level=None, exp=None) -> None:
        """Rewrite a party member's moves / PP / level / exp in the encrypted struct (and its checksum).
        Keep exp consistent with level, or the game hangs on the 'gained EXP' text."""
        m = self.m
        b = Addr.PARTY_DATA + 100 * slot
        raw = bytearray(m.read8(b + i) for i in range(100))
        pid = int.from_bytes(raw[0:4], "little")
        key = pid ^ int.from_bytes(raw[4:8], "little")
        enc = bytearray(raw[32:80])
        for i in range(0, 48, 4):
            enc[i:i + 4] = (int.from_bytes(enc[i:i + 4], "little") ^ key).to_bytes(4, "little")
        order = SUBSTRUCT_ORDER[pid % 24]
        ai, gi = order.index("A") * 12, order.index("G") * 12
        if exp is not None:
            enc[gi + 4:gi + 8] = exp.to_bytes(4, "little")
        for i, mv in enumerate(moves or []):
            enc[ai + i * 2:ai + i * 2 + 2] = mv.to_bytes(2, "little")
        for i, pp in enumerate(pps or []):
            enc[ai + 8 + i] = pp
        chk = sum(int.from_bytes(enc[i:i + 2], "little") for i in range(0, 48, 2)) & 0xFFFF
        out = bytearray(enc)
        for i in range(0, 48, 4):
            out[i:i + 4] = (int.from_bytes(out[i:i + 4], "little") ^ key).to_bytes(4, "little")
        for i in range(48):
            m.write8(b + 32 + i, out[i])
        m.write8(b + 28, chk & 0xFF)
        m.write8(b + 29, chk >> 8)
        if level:
            m.write8(b + 0x54, level)

    def wild_battle(self, tries: int = 600) -> bool:
        """Stand on grass and wander until a wild battle starts."""
        if not self.c._relocate_to_grass():
            return False
        st = {"stuck": 0, "reloc": 0}
        for _ in range(tries):
            if self.r.detect_context() == GameContext.IN_BATTLE:
                return True
            self.c._grass_step(st, "x")
        return False

    def set_foe_hp(self, hp: int) -> None:
        self.m.write16(B1 + 0x28, hp)
