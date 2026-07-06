"""In-process mGBA backend — drop-in replacement for MGBAClient.

Drives libmgba directly via the compiled `game._mgba_native` binding: no mGBA
GUI, no Lua socket, no mGBA-http, no HTTP round-trips. The emulator only
advances when we run frames, so button presses and `tick()` explicitly step it.

Exposes the same method surface as `game.mgba_client.MGBAClient`, so the rest of
the codebase (memory_reader, agent, tools, main) is unchanged apart from which
client it constructs.

Build the binding first if needed:  python -m game._mgba_build
"""
from pathlib import Path
from config import ROM_PATH, SAVE_DIR, SHOW_WINDOW

try:
    from game._mgba_native import ffi, lib
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "game._mgba_native is not built. Run:  python -m game._mgba_build\n"
        "(requires Homebrew libmgba:  brew install mgba)"
    ) from e

# GBA key bit positions (from libmgba's enum GBAKey).
_KEY_BIT = {
    "A": 0, "B": 1, "Select": 2, "Start": 3, "Right": 4,
    "Left": 5, "Up": 6, "Down": 7, "R": 8, "L": 9,
}

# Frame timing. A tap holds then releases; movement needs the button held long
# enough for the walk animation to commit a tile.
TAP_HOLD_FRAMES = 8
TAP_RELEASE_FRAMES = 8
IDLE_TICK_FRAMES = 6  # advanced by main loop each iteration (animations/fades)


def _mask(buttons) -> int:
    m = 0
    for b in buttons:
        if b not in _KEY_BIT:
            raise ValueError(f"invalid button {b!r}; valid: {list(_KEY_BIT)}")
        m |= 1 << _KEY_BIT[b]
    return m


class NativeMGBAClient:
    def __init__(self, rom_path: str | None = None, show_window: bool | None = None):
        rom = str(rom_path or ROM_PATH)
        if not Path(rom).is_file():
            raise FileNotFoundError(f"ROM not found: {rom}")
        self._h = lib.pycore_load(rom.encode())
        if self._h == ffi.NULL:
            raise RuntimeError(f"libmgba failed to load ROM: {rom}")
        SAVE_DIR.mkdir(parents=True, exist_ok=True)

        # Live framebuffer view + optional window.
        w = ffi.new("uint32_t*"); h = ffi.new("uint32_t*")
        lib.pycore_video_dims(self._h, w, h)
        self._vw, self._vh = int(w[0]), int(h[0])
        self._video = ffi.cast("uint8_t*", lib.pycore_video_ptr(self._h))
        self._video_bytes = self._vw * self._vh * 4  # RGBX
        self._viewer = None
        if SHOW_WINDOW if show_window is None else show_window:
            from game.viewer import PygameViewer
            self._viewer = PygameViewer(self._vw, self._vh)

    def framebuffer(self) -> bytes:
        """Latest frame as RGBX bytes (width*height*4)."""
        return bytes(ffi.buffer(self._video, self._video_bytes))

    # ── Frame stepping ───────────────────────────────────────────────────────

    def run_frames(self, n: int) -> None:
        v = self._viewer
        if v is None:
            for _ in range(n):
                lib.pycore_run_frame(self._h)
        else:
            for _ in range(n):
                lib.pycore_run_frame(self._h)
                v.render(ffi.buffer(self._video, self._video_bytes))

    def tick(self, frames: int = IDLE_TICK_FRAMES) -> None:
        """Advance the emulator with no input (animations, fades, NPC motion)."""
        lib.pycore_set_keys(self._h, 0)
        self.run_frames(frames)

    # ── Buttons ──────────────────────────────────────────────────────────────

    def _press(self, mask: int) -> None:
        lib.pycore_set_keys(self._h, mask)
        self.run_frames(TAP_HOLD_FRAMES)
        lib.pycore_set_keys(self._h, 0)
        self.run_frames(TAP_RELEASE_FRAMES)

    def tap(self, button: str) -> None:
        self._press(_mask([button]))

    def tap_many(self, buttons: list[str]) -> None:
        self._press(_mask(buttons))

    def hold(self, button: str, duration_frames: int) -> None:
        lib.pycore_set_keys(self._h, _mask([button]))
        self.run_frames(max(1, duration_frames))
        lib.pycore_set_keys(self._h, 0)
        self.run_frames(2)

    # ── Memory reads ─────────────────────────────────────────────────────────

    def read8(self, address: int) -> int:
        return int(lib.pycore_read8(self._h, address)) & 0xFF

    def read16(self, address: int) -> int:
        return int(lib.pycore_read16(self._h, address)) & 0xFFFF

    def read32(self, address: int) -> int:
        return int(lib.pycore_read32(self._h, address)) & 0xFFFFFFFF

    def read_range(self, address: int, length: int) -> bytes:
        buf = ffi.new("uint8_t[]", length)
        lib.pycore_read_range(self._h, address, length, buf)
        return bytes(buf)

    # ── Memory writes ────────────────────────────────────────────────────────

    def write8(self, address: int, value: int) -> None:
        lib.pycore_write8(self._h, address, value & 0xFF)

    def write16(self, address: int, value: int) -> None:
        lib.pycore_write16(self._h, address, value & 0xFFFF)

    def write32(self, address: int, value: int) -> None:
        lib.pycore_write32(self._h, address, value & 0xFFFFFFFF)

    # ── State management ─────────────────────────────────────────────────────

    def _slot_path(self, slot: int) -> str:
        return str(SAVE_DIR / f"slot_{slot}.ss1")

    def save_state(self, slot: int = 0) -> None:
        lib.pycore_save_state(self._h, self._slot_path(slot).encode())

    def load_state(self, slot: int = 0) -> None:
        lib.pycore_load_state(self._h, self._slot_path(slot).encode())

    def save_state_file(self, path: str) -> bool:
        return bool(lib.pycore_save_state(self._h, str(path).encode()))

    def load_state_file(self, path: str) -> bool:
        return bool(lib.pycore_load_state(self._h, str(path).encode()))

    # ── Info / verification ──────────────────────────────────────────────────

    def get_game_title(self) -> str:
        # ROM header title: 12 bytes at bus 0x080000A0.
        raw = self.read_range(0x080000A0, 12)
        return raw.split(b"\x00")[0].decode("ascii", "replace").strip()

    def get_game_code(self) -> str:
        # ROM header game code: 4 bytes at bus 0x080000AC (e.g. "BPGE").
        code = self.read_range(0x080000AC, 4).decode("ascii", "replace")
        return f"AGB-{code}"

    def screenshot(self, path: str) -> None:
        lib.pycore_screenshot(self._h, str(path).encode())

    def log(self, message: str) -> None:
        print(f"[mgba] {message}")

    def verify_connection(self) -> bool:
        try:
            return "BPGE" in self.get_game_code()
        except Exception:
            return False

    def __del__(self):
        try:
            if getattr(self, "_viewer", None) is not None:
                self._viewer.close()
                self._viewer = None
        except Exception:
            pass
        try:
            if getattr(self, "_h", None) not in (None, ffi.NULL):
                lib.pycore_destroy(self._h)
                self._h = None
        except Exception:
            pass
