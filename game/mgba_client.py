import requests
import time
from config import MGBA_HTTP_BASE, BUTTON_TAP_DELAY


class MGBAClient:
    def __init__(self, base_url: str = MGBA_HTTP_BASE):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()

    # ── Response parsing ─────────────────────────────────────────────────────

    def _hex_csv_to_bytes(self, text: str) -> bytes:
        """Parse 'aa,bb,cc' response from /core/readrange into bytes.
        The API returns lowercase hex bytes separated by commas, no 0x prefix."""
        text = text.strip()
        if not text:
            return b""
        return bytes(int(h, 16) for h in text.split(","))

    # ── Buttons ──────────────────────────────────────────────────────────────
    # Valid button values: A B Select Start Right Left Up Down R L

    def tap(self, button: str) -> None:
        """Press and release a single button."""
        self.session.post(f"{self.base}/mgba-http/button/tap",
                          params={"button": button})
        time.sleep(BUTTON_TAP_DELAY)

    def tap_many(self, buttons: list[str]) -> None:
        """Press and release multiple buttons simultaneously."""
        self.session.post(f"{self.base}/mgba-http/button/tapmany",
                          params=[("buttons", b) for b in buttons])
        time.sleep(BUTTON_TAP_DELAY)

    def hold(self, button: str, duration_frames: int) -> None:
        """Hold a button for exactly N frames then release."""
        self.session.post(f"{self.base}/mgba-http/button/hold",
                          params={"button": button, "duration": duration_frames})

    def tick(self, frames: int = 9) -> None:
        """Let game time pass. The mGBA-http emulator runs in real time on its
        own, so this just sleeps ~frames/60s; the native backend steps frames.
        Kept for a backend-agnostic main loop."""
        time.sleep(frames / 60.0)

    # ── Memory reads (full absolute GBA bus addresses) ────────────────────────
    # Use these. They take 0x02024284-style addresses directly.
    # No domain name, no offset calculation needed.

    def read8(self, address: int) -> int:
        """Read unsigned 8-bit integer. Returns decimal value as int."""
        r = self.session.get(f"{self.base}/core/read8",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read16(self, address: int) -> int:
        """Read unsigned 16-bit integer. Returns decimal value as int."""
        r = self.session.get(f"{self.base}/core/read16",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read32(self, address: int) -> int:
        """Read unsigned 32-bit integer. Returns decimal value as int."""
        r = self.session.get(f"{self.base}/core/read32",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read_range(self, address: int, length: int) -> bytes:
        """Read `length` bytes starting at `address`.
        API returns 'aa,bb,cc,...' — parsed to bytes here.
        Example: read_range(0x02024288, 100) reads first party slot."""
        r = self.session.get(f"{self.base}/core/readrange",
                             params={"address": hex(address), "length": length})
        r.raise_for_status()
        return self._hex_csv_to_bytes(r.text)

    # ── Memory writes (domain-relative addresses) ────────────────────────────
    # The write API uses /memorydomain/write8 with a domain name and a
    # domain-relative address.  For WRAM (0x02000000–0x02FFFFFF) subtract
    # 0x02000000.  For IWRAM (0x03000000–0x03FFFFFF) subtract 0x03000000.

    def write8(self, address: int, value: int) -> None:
        """Write an unsigned 8-bit value at an absolute GBA bus address.
        Only WRAM (0x02xxxxxx) addresses are supported."""
        wram_addr = address - 0x02000000
        self.session.post(f"{self.base}/memorydomain/write8",
                          params={"memoryDomain": "wram",
                                  "address": hex(wram_addr),
                                  "value": str(value & 0xFF)})

    # ── State management ──────────────────────────────────────────────────────
    # slot param MUST be a string per swagger schema

    def save_state(self, slot: int = 0) -> bool:
        """Save to a numbered slot (mGBA manages file location). Returns True if
        the request succeeded (HTTP 2xx); the slot endpoint returns no body, so
        this reflects transport success, not a core-level bool. Interface parity
        with the native backend so callers can branch on failure."""
        try:
            r = self.session.post(f"{self.base}/core/savestateslot",
                                  params={"slot": str(slot)})
            return r.ok
        except Exception:
            return False

    def load_state(self, slot: int = 0) -> bool:
        """Load from a numbered slot. Returns True on a successful request. Note
        the REST slot endpoint can't distinguish "no such slot" from success at
        the body level, so a missing slot may still report True on the http
        backend; the native backend reports it accurately."""
        try:
            r = self.session.post(f"{self.base}/core/loadstateslot",
                                  params={"slot": str(slot)})
            return r.ok
        except Exception:
            return False

    def save_state_file(self, path: str) -> bool:
        """Save state to a specific file. Use for named pre-gym saves."""
        r = self.session.post(f"{self.base}/core/savestatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    def load_state_file(self, path: str) -> bool:
        """Load state from a specific file."""
        r = self.session.post(f"{self.base}/core/loadstatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    # ── Verification and utilities ────────────────────────────────────────────

    def get_game_title(self) -> str:
        """Returns 'POKEMON LEAF' for LeafGreen US."""
        return self.session.get(f"{self.base}/core/getgametitle").text.strip()

    def get_game_code(self) -> str:
        """Returns 'AGB-BPGE' for Pokemon LeafGreen English."""
        return self.session.get(f"{self.base}/core/getgamecode").text.strip()

    def screenshot(self, path: str) -> None:
        """Save PNG screenshot to path. Useful for debugging."""
        self.session.post(f"{self.base}/core/screenshot", params={"path": path})

    def log(self, message: str) -> None:
        """Print to mGBA-http console window."""
        self.session.post(f"{self.base}/console/log", params={"message": message})

    def verify_connection(self) -> bool:
        """Returns True if mGBA-http is running and LeafGreen is loaded.
        Note: get_game_code() returns 'AGB-BPGE', not just 'BPGE' — use 'in'."""
        try:
            return "BPGE" in self.get_game_code()
        except Exception:
            return False
