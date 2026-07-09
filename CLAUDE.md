# CLAUDE.md — Pokemon LeafGreen LLM Agent
**Project root:** `/Users/kylec/Projects/pokemon-agent`
**Platform:** macOS (Apple Silicon, arm64)
**Python:** 3.14 (project `.venv`) — all required packages compatible

> The code is cross-platform (paths use `pathlib`/`tempfile`); only the environment
> locations and shell commands below are host-specific. This file documents the macOS host.

> **For AI coding assistants:** This is the authoritative project reference. Read fully before writing any code. All API endpoints are verified against the actual swagger.json from mGBA-http 0.8.2.

---

## Emulator Backend

Two backends, selected by `MGBA_BACKEND` in `.env`:

- **`native` (default)** — drives libmgba **in-process** via a cffi binding. No mGBA
  GUI, no Lua, no mGBA-http, no HTTP. The agent owns the emulator and steps frames
  directly (~50× real-time, deterministic). This is the recommended path.
- **`http` (legacy)** — the old mGBA GUI + Lua socket + mGBA-http .NET transport.
  Kept as a fallback; see the legacy notes at the bottom of this section.

### Native backend

| Component | Location | Notes |
|-----------|----------|-------|
| libmgba | Homebrew (`brew install mgba`) — `/opt/homebrew/lib/libmgba.dylib` | Provides the core + headers the binding builds against |
| Binding source | `game/_mgba_build.py` | cffi builder → `game/_mgba_native*.so` (gitignored) |
| Native client | `game/mgba_core.py` (`NativeMGBAClient`) | Drop-in for `MGBAClient` |
| LeafGreen ROM | `~/mgba-http/Pokemon_LeafGreen.gba` (override with `ROM_PATH`) | US v1.0, 16 MB |
| LLM (local or cloud) | `MODEL_NAME` + `LLM_BASE_URL`/`LLM_API_KEY` in `.env` — a tool-capable model | Local: LM Studio on port 1234. Cloud: point `LLM_BASE_URL` at any OpenAI-compatible endpoint (OpenAI, OpenRouter, …). Text-only models: `USE_VISION=false`; ensure `MAX_TOKENS` fits the loaded context |
| Project root | `/Users/kylec/Projects/pokemon-agent` | |

Build the binding once (or after upgrading libmgba):
```fish
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish        # bash/zsh: source .venv/bin/activate
python -m game._mgba_build            # compiles game/_mgba_native*.so
```
The binding reads/writes memory with the **same absolute GBA bus addresses** as the
HTTP API, so `game/constants.py` and `memory_reader.py` are backend-agnostic.

**Booting from a save.** `NativeMGBAClient.load_save(path)` loads a battery `.sav`
into cartridge memory; call it before `reset()` so the title screen offers
"Continue":  `m.load_save("game.sav"); m.reset()`. (This is the cartridge save, not
an mGBA save state — the binding does not read mGBA's compressed `.ss*`/`.svs`
state files.)

**Watching it play (live window).** The native backend is headless by default. Set
`SHOW_WINDOW=true` (needs `pip install pygame`) to open a window that renders
libmgba's framebuffer each frame (`game/viewer.py`). It's smooth during actions and
holds the last frame still while the LLM thinks (the game only advances when the
agent runs frames). Tunables: `VIEWER_SCALE` (window size), `VIEWER_FPS` (playback
cap; 0 = full emulator speed). Close the window or press Esc to stop cleanly.
The framebuffer is 32-bit color, laid out `[R,G,B,pad]` (RGBX) per pixel.

### Legacy `http` backend (fallback, `MGBA_BACKEND=http`)

| Component | Location |
|-----------|----------|
| mGBA emulator | `/Applications/mGBA.app` |
| mGBA-http binary | `~/mgba-http/mGBA-http-0.8.2-osx-arm64-self-contained` (self-contained Mach-O) |
| Lua socket script | `~/mgba-http/mGBASocketServer.lua` (load in mGBA scripting console) |

First-run note for that binary: it's a downloaded, unsigned Mach-O — if Gatekeeper
blocks it, run `chmod +x` and `xattr -d com.apple.quarantine <binary>` once.

---

## Architecture

```
Pokemon_LeafGreen.gba
        │
   ┌────────────────── native (default) ──────────────────┐
   │  libmgba (Homebrew)  ──cffi──►  game/_mgba_native.so  │   in-process,
   │                                 game/mgba_core.py     │   ~50× realtime
   └───────────────────────────────────────────────────────┘
        │                     (or, legacy http backend:)
        │            mGBA GUI → Lua socket → mGBA-http → REST :5000 → game/mgba_client.py
        │
   main.py                      build_runtime() + run_episode() decision loop; thin main()
                                (run controls: START_FROM_SAVE, MAX_STEPS, MAX_LLM_CALLS,
                                 TOKEN_BUDGET). run_episode(goal=…) returns an EpisodeResult;
                                the eval harness reuses it so eval and real runs never diverge.
   Python Agent
   ├── game/mgba_core.py        NativeMGBAClient — in-process libmgba (default)
   ├── game/mgba_client.py      MGBAClient — legacy REST wrapper (http backend)
   ├── game/memory_reader.py    WRAM decoder — XOR decryption + detect_context
   ├── game/state.py            GameState, PokemonStatus, StateDiff, helpers
   ├── game/constants.py        Memory addresses (authoritative), lookup tables, charset
   ├── game/tilemap_reader.py   ROM tile passability, warps, connections (navigation)
   ├── game/pathfinding.py      A* grid pathfinding + door_centers (pure, testable)
   ├── game/viewer.py           Optional pygame window (SHOW_WINDOW)
   ├── agent/lm_studio_client.py OpenAI-compat client (local OR cloud), tool calling +
   │                            the nav/battle skills (walk_to/go_to/go_to_map/use_move)
   ├── agent/tools.py           Tool schemas + button-name normalization
   ├── agent/history.py         Message trimming + control-token stripping (dependency-light)
   ├── agent/reward.py          Shaped/sparse reward tracker
   ├── memory/short_term.py     Current context (in-process)
   ├── memory/long_term.py      Persistent progress → logs/progress.json
   ├── memory/battle_journal.py JSONL log + retrieval
   └── knowledge/
       ├── type_chart.py        Gen III type effectiveness
       ├── leafgreen_data.py    Gyms, moves (type/power), Pokémon types, milestones
       ├── navigation.py        Map names, route/building guidance, area maps
       ├── map_graph.py         GENERATED map connection+warp graph + BFS routing
       │                        (tools/gen_map_graph.py, from the pokefirered decomp)
       ├── battle.py            Battle observation builder (best-move ranking)
       └── system_prompt.py     Dynamic system prompt builder
   └── evals/                   Eval harness (python -m evals)
       ├── goals.py             Goal predicates (reach_map/badges_at_least/…) — pure
       ├── scenarios.py         Scenario registry (start state + goal + step budget)
       └── runner.py            Runs scenarios via main.run_episode → scorecard JSON/table
```

**Module boundaries — never cross these:**
- `game/` drives the emulator (native binding or legacy mGBA-http) and does memory decoding. No LLM, no reward logic.
- `agent/` talks only to LM Studio. Interacts with the game only through tool execution.
- `memory/` reads/writes memory structures only. No network I/O.
- `knowledge/` is pure data and string construction. Zero I/O.
- `evals/` — `goals.py`/`scenarios.py` are pure/light (CI-testable); only `runner.py` imports the heavy agent stack (`main`).

---

## mGBA-http 0.8.2 — Verified API Reference

**Base URL:** `http://localhost:5000`
**All endpoints verified against swagger.json from the running server.**

### Button Endpoints

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Tap (press + release) | POST | `/mgba-http/button/tap` | `button=A` |
| Tap multiple simultaneously | POST | `/mgba-http/button/tapmany` | `buttons=A&buttons=B` |
| Hold for N frames | POST | `/mgba-http/button/hold` | `button=A&duration=30` |
| Hold multiple for N frames | POST | `/mgba-http/button/holdmany` | `buttons=A&buttons=B&duration=30` |
| Add (hold down indefinitely) | POST | `/mgba-http/button/add` | `button=A` |
| Clear (release) | POST | `/mgba-http/button/clear` | `button=A` |
| Get button state | GET | `/mgba-http/button/get` | `button=A` → `"0"` or `"1"` |
| Get all active buttons | GET | `/mgba-http/button/getall` | → `"A,B,Start"` |

**Valid button values:** `A` `B` `Select` `Start` `Right` `Left` `Up` `Down` `R` `L`

### Core Memory Endpoints

**Key insight: these use full GBA bus addresses (e.g. `0x02024284`), no domain name needed.**
**All return plain-text strings, not JSON.**

| Action | Method | Endpoint | Params | Returns |
|--------|--------|----------|--------|---------|
| Read 8-bit | GET | `/core/read8` | `address=0x02024284` | `"255"` (decimal string) |
| Read 16-bit | GET | `/core/read16` | `address=0x02024284` | `"65535"` (decimal string) |
| Read 32-bit | GET | `/core/read32` | `address=0x02024284` | `"4294967295"` (decimal string) |
| Read byte range | GET | `/core/readrange` | `address=0x02024284&length=100` | `"d3,00,ea,66,..."` (comma-sep hex, no 0x) |

### Domain-Based Memory Endpoints (Alternative)

Use these if you need domain-relative addressing. Domain names for GBA: `wram`, `cart0`, `bios`, `iwram`.

| Action | Method | Endpoint | Params | Returns |
|--------|--------|----------|--------|---------|
| Read 8-bit | GET | `/memorydomain/read8` | `memoryDomain=wram&address=0x24284` | `"255"` (decimal) |
| Read byte range | GET | `/memorydomain/readrange` | `memoryDomain=wram&address=0x24284&length=100` | `"d3,00,ea,..."` |
| Get domain size | GET | `/memorydomain/size` | `memoryDomain=wram` | `"262144"` |
| Write 8-bit | POST | `/memorydomain/write8` | `memoryDomain=wram&address=0x24284&value=255` | `""` |
| Write 16-bit | POST | `/memorydomain/write16` | `memoryDomain=wram&address=0x24284&value=65535` | `""` |
| Write 32-bit | POST | `/memorydomain/write32` | `memoryDomain=wram&address=0x24284&value=4294967295` | `""` |

**Prefer `/core/read8|16|32|readrange`** — they take full absolute addresses, directly matching all memory map documentation.

### State Management Endpoints

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Save to slot | POST | `/core/savestateslot` | `slot=0` |
| Load from slot | POST | `/core/loadstateslot` | `slot=0` |
| Save to file | POST | `/core/savestatefile` | `path=/Users/kylec/Projects/pokemon-agent/saves/pre_gym.ss1` |
| Load from file | POST | `/core/loadstatefile` | `path=/Users/kylec/Projects/pokemon-agent/saves/pre_gym.ss1` |
| Save to buffer | POST | `/core/savestatebuffer` | → hex csv string |
| Load from buffer | POST | `/core/loadstatebuffer` | body: `[d3,00,ea,...]` |

**State flags bitmask:** SCREENSHOT=1, SAVEDATA=2, CHEATS=4, RTC=8, METADATA=16. Default save=31 (all), load=29 (excludes screenshot).

### Other Useful Endpoints

| Action | Method | Endpoint | Returns |
|--------|--------|----------|---------|
| Get game title | GET | `/core/getgametitle` | `"POKEMON LEAF"` |
| Get game code | GET | `/core/getgamecode` | `"AGB-BPGE"` (LeafGreen US) |
| Get platform | GET | `/core/platform` | `"0"` (GBA=0, GB=1) |
| Save screenshot | POST | `/core/screenshot` | `path=/tmp/screenshot.png` |
| Read CPU register | GET | `/core/readregister` | `regName=pc` → decimal |
| Load ROM | POST | `/core/loadfile` | `path=...` |

### Console Logging (writes to mGBA-http terminal)

| Action | Method | Endpoint | Params |
|--------|--------|----------|--------|
| Log | POST | `/console/log` | `message=hello` |
| Warn | POST | `/console/warn` | `message=...` |
| Error | POST | `/console/error` | `message=...` |

---

## Python Client — Canonical Implementation

This is the single source of truth for `game/mgba_client.py`. All method signatures here are derived from the swagger and must match it exactly.

```python
# game/mgba_client.py
import requests
import time
from config import MGBA_HTTP_BASE, BUTTON_TAP_DELAY

class MGBAClient:
    def __init__(self, base_url: str = MGBA_HTTP_BASE):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()

    # ── Response parsing ────────────────────────────────────────────────────

    def _hex_csv_to_bytes(self, text: str) -> bytes:
        """Parse 'aa,bb,cc,dd' response from readrange into bytes."""
        text = text.strip()
        if not text:
            return b""
        return bytes(int(h, 16) for h in text.split(","))

    # ── Buttons ─────────────────────────────────────────────────────────────

    def tap(self, button: str) -> None:
        """Press and release. button must be: A B Select Start Right Left Up Down R L"""
        self.session.post(f"{self.base}/mgba-http/button/tap", params={"button": button})
        time.sleep(BUTTON_TAP_DELAY)

    def tap_many(self, buttons: list[str]) -> None:
        self.session.post(f"{self.base}/mgba-http/button/tapmany",
                          params=[("buttons", b) for b in buttons])
        time.sleep(BUTTON_TAP_DELAY)

    def hold(self, button: str, duration_frames: int) -> None:
        """Hold a button for exactly N frames."""
        self.session.post(f"{self.base}/mgba-http/button/hold",
                          params={"button": button, "duration": duration_frames})

    # ── Memory reads (full absolute GBA bus addresses) ──────────────────────

    def read8(self, address: int) -> int:
        """Read unsigned 8-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read8",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read16(self, address: int) -> int:
        """Read unsigned 16-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read16",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read32(self, address: int) -> int:
        """Read unsigned 32-bit value at absolute GBA bus address."""
        r = self.session.get(f"{self.base}/core/read32",
                             params={"address": hex(address)})
        r.raise_for_status()
        return int(r.text.strip())

    def read_range(self, address: int, length: int) -> bytes:
        """Read `length` bytes starting at absolute GBA bus address.
        Response is comma-separated hex: 'd3,00,ea,66,...' — parsed to bytes."""
        r = self.session.get(f"{self.base}/core/readrange",
                             params={"address": hex(address), "length": length})
        r.raise_for_status()
        return self._hex_csv_to_bytes(r.text)

    # ── State management ────────────────────────────────────────────────────

    def save_state(self, slot: int = 0) -> None:
        """Save to a numbered slot (mGBA manages the file location)."""
        self.session.post(f"{self.base}/core/savestateslot",
                          params={"slot": str(slot)})

    def load_state(self, slot: int = 0) -> None:
        """Load from a numbered slot."""
        self.session.post(f"{self.base}/core/loadstateslot",
                          params={"slot": str(slot)})

    def save_state_file(self, path: str) -> bool:
        """Save state to a specific file path. Returns True on success."""
        r = self.session.post(f"{self.base}/core/savestatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    def load_state_file(self, path: str) -> bool:
        """Load state from a specific file path. Returns True on success."""
        r = self.session.post(f"{self.base}/core/loadstatefile",
                              params={"path": path})
        return r.text.strip().lower() == "true"

    # ── Info / verification ─────────────────────────────────────────────────

    def get_game_title(self) -> str:
        """Returns e.g. 'POKEMON LEAF' for LeafGreen."""
        return self.session.get(f"{self.base}/core/getgametitle").text.strip()

    def get_game_code(self) -> str:
        """Returns 'AGB-BPGE' for Pokemon LeafGreen English."""
        return self.session.get(f"{self.base}/core/getgamecode").text.strip()

    def screenshot(self, path: str) -> None:
        """Save a PNG screenshot to the given filesystem path."""
        self.session.post(f"{self.base}/core/screenshot", params={"path": path})

    def log(self, message: str) -> None:
        """Print a message to the mGBA-http console (useful for debugging)."""
        self.session.post(f"{self.base}/console/log", params={"message": message})

    def verify_connection(self) -> bool:
        """Returns True if mGBA-http is running and serving LeafGreen.
        Note: get_game_code() returns 'AGB-BPGE', not just 'BPGE' — use 'in'."""
        try:
            return "BPGE" in self.get_game_code()
        except Exception:
            return False
```

---

## Gen III Pokémon Data Structures and Decryption

### Why This Matters

Party Pokémon data is partially XOR-encrypted. **Species ID and moves require decryption.** HP, level, and status are stored unencrypted and always readable. Getting this wrong means silently reading garbage for species and moves.

### 100-Byte Party Structure Layout

Each of the 6 party slots is 100 bytes at `PARTY_DATA + (slot * 100)`.

| Offset | Size | Field | Encrypted? |
|--------|------|-------|-----------|
| `0x00` | 4 | Personality value (PID) | No |
| `0x04` | 4 | OT ID (public + secret) | No |
| `0x08` | 10 | Nickname (Gen III charset) | No |
| `0x12` | 1 | Language | No |
| `0x13` | 1 | Misc flags | No |
| `0x14` | 7 | OT name | No |
| `0x1B` | 1 | Markings | No |
| `0x1C` | 2 | Checksum | No |
| `0x1E` | 2 | Padding | No |
| **`0x20`** | **48** | **Substructures (G/A/E/M) — XOR encrypted** | **Yes** |
| `0x50` | 4 | Status condition bitmask | **No** |
| `0x54` | 1 | Level | **No** |
| `0x55` | 1 | Mail ID | No |
| `0x56` | 2 | Current HP | **No** |
| `0x58` | 2 | Max HP | **No** |
| `0x5A`–`0x62` | 14 | Battle stats (Atk/Def/Spd/SpA/SpD) | No |

**Tier 1 (no decryption needed):** Level, HP, Max HP, Status — get the agent running with just these.
**Tier 2 (decryption):** Species ID and moves — add after Tier 1 is working.

### XOR Decryption

```python
SUBSTRUCT_ORDER = [
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
]

def decrypt_substructs(raw_100: bytes) -> dict[str, bytes]:
    pid   = int.from_bytes(raw_100[0:4], "little")
    ot_id = int.from_bytes(raw_100[4:8], "little")
    key   = pid ^ ot_id
    enc   = bytearray(raw_100[32:80])
    for i in range(0, 48, 4):
        word = int.from_bytes(enc[i:i+4], "little") ^ key
        enc[i:i+4] = word.to_bytes(4, "little")
    order = SUBSTRUCT_ORDER[pid % 24]
    return {letter: bytes(enc[i * 12:(i + 1) * 12]) for i, letter in enumerate(order)}

def parse_species(sub: dict[str, bytes]) -> int:
    return int.from_bytes(sub["G"][0:2], "little")

def parse_moves(sub: dict[str, bytes]) -> tuple[list[int], list[int]]:
    a = sub["A"]
    return [int.from_bytes(a[i*2:(i+1)*2], "little") for i in range(4)], [a[8+i] for i in range(4)]

def decode_status(word: int) -> str:
    if word == 0: return "healthy"
    sleep = word & 0b111
    if sleep: return f"asleep ({sleep} turns)"
    if word & (1 << 3): return "poisoned"
    if word & (1 << 4): return "burned"
    if word & (1 << 5): return "frozen"
    if word & (1 << 6): return "paralyzed"
    if word & (1 << 7): return "badly_poisoned"
    return "unknown"
```

### Attacks Substructure (A, 12 bytes post-decrypt)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | Move 1 ID |
| 0x02 | 2 | Move 2 ID |
| 0x04 | 2 | Move 3 ID |
| 0x06 | 2 | Move 4 ID |
| 0x08 | 1 | PP move 1 |
| 0x09 | 1 | PP move 2 |
| 0x0A | 1 | PP move 3 |
| 0x0B | 1 | PP move 4 |

### Growth Substructure (G, 12 bytes post-decrypt)

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2 | Species ID (National Dex) |
| 0x02 | 2 | Held item ID |
| 0x04 | 4 | Experience |
| 0x08 | 1 | PP bonuses |
| 0x09 | 1 | Friendship |

---

## Memory Addresses & Context Detection

**`game/constants.py` (the `Addr` class) and `game/memory_reader.py` are the
authoritative source.** All are full GBA bus addresses (usable directly with the
native binding's reads, or `/core/read8|16|32|readrange`). Do not hand-copy the
full map here — several addresses were re-derived empirically during development
(diffing live save states) and a duplicate list drifts. The notable, hard-won
ones:

| What | Address | Notes |
|------|---------|-------|
| Party count / data | `0x02024284` / `0x02024288` | 6 × 100-byte structs (Gen III XOR, below) |
| Badges | `0x02025968` | u8 bitmask; popcount = badge count |
| Map bank / id | `0x02031DBC` / `0x02031DBD` | |
| Player X/Y | deref `PLAYER_PTR` `0x03005008` +0/+2 | DMA-protected block; camera = player tile |
| `gMain.callback2` | `0x030030F4` | live "current screen" dispatcher — the context gate |
| Menu flag | `0x03002415` | set while a field menu is open, but **over-stays** after a full-screen menu closes — pair with screen-fade, never use alone |
| Script engine | `0x03000EB0` | byte[0] ≠ 0 while a map script/dialog runs |
| Screen fade | `0x03000F9C` | 1 while a menu is on screen **or** mid-fade; clears the instant a menu closes |
| `gBattleTypeFlags` | `0x02022B4C` | TRAINER bit `0x08`; set at battle init, read at battle start |
| Bag key-items pocket | `gSaveBlock1(0x03005008) + 0x3B8` | 30 slots; count non-empty for the `key_item` reward |
| Current map (bank/id) | deref `PLAYER_PTR` `+0x04`/`+0x05` | the TRUE current map (interior-aware); the absolute `0x02031DBC/DBD` is the stale *parent outdoor* map |
| `gEnemyParty[0]` | `0x0202402C` | opponent's active Pokémon — same 100-byte Gen III struct as gPlayerParty; fixed global. `read_enemy_lead()` |
| `gObjectEvents` | `0x02036E38` (= OW slot 0) | NPCs on screen; 36-byte stride, `currentCoords` at +0x10/+0x12 = grid coord **+7**. walk_to routes around them |
| `gBattlerControllerFuncs[0]` | `0x03004FE0` | `== 0x0802EA11` (HandleInputChooseMove) ⇒ FIGHT move menu is open (use_move gate) |
| `gMoveSelectionCursor` | `0x02023FFC` | move slot A commits (2×2 grid); use_move writes the target slot here, then presses A |

### Context Detection (verified live — implemented in `memory_reader.detect_context`)

⚠ The old `OVERWORLD_FLAG` / `BATTLE_FLAGS` approach was **wrong** and is
deprecated: `OVERWORLD_FLAG` (`0x0202287C`) reads 0 during free-roam, and
`BATTLE_FLAGS` (`0x02022880`) is transient during battle and stale afterward. The
correct gate is `gMain.callback2`:

`MENU_OPEN` alone is **not** a safe gate: after a full-screen menu (Pokédex/Bag/…)
closes it stays `1` back on the field, which trapped the agent in a phantom
`IN_MENU` forever. The fix pairs it with `SCREEN_FADE`, which *does* clear when a
menu closes (an open menu is `MENU_OPEN && SCREEN_FADE`; a stale flag has
`SCREEN_FADE == 0` and reads OVERWORLD):

```python
cb2  = read32(GMAIN_CALLBACK2)            # 0x030030F4
menu = read8(MENU_OPEN) != 0             # 0x03002415  (over-stays; never under-reports)
fade = read8(SCREEN_FADE) == 1          # 0x03000F9C  (on-screen menu OR fade; clears on close)
if cb2 == CB2_BATTLE:                     # 0x08011101   -> IN_BATTLE
elif cb2 == CB2_OVERWORLD:                # 0x080565B5   (field callback)
    if menu and fade:                     #              -> IN_MENU  (Start/Save overlay)
    elif fade:                            #              -> TRANSITIONING  (warp/map fade)
    elif read8(SCRIPT_RAM) != 0:          # byte[0]      -> DIALOG_OPEN  (NPC/sign/script)
    else:                                 #              -> OVERWORLD  (stale MENU_OPEN lands here)
else:                                     # full-screen menu has its own callback
    if menu:                              #              -> IN_MENU  (Pokédex/Party/Bag/Option/…)
    else:                                 #              -> TRANSITIONING  (warps, load screens)
```

`GameContext` values: `OVERWORLD`, `IN_BATTLE`, `DIALOG_OPEN`, `IN_MENU`,
`TRANSITIONING`, `UNKNOWN`. The `CB2_*` and menu addresses are specific to this
LeafGreen build; re-derive by diffing live states if OVERWORLD is misdetected.

### Dialog Observation — State Diffing Strategy

The agent doesn't read dialog text character-by-character. It detects **what changed** between two state polls. Every meaningful game event leaves a detectable footprint:

| Game Event | How Detected |
|-----------|-------------|
| Took damage | Party HP decreased |
| Leveled up | Party level increased |
| Learned move | Party moves changed (Tier 2) |
| Caught Pokémon | Party count increased |
| Earned badge | Badge bitmask changed |
| Battle ended | context left `IN_BATTLE` (`gMain.callback2` no longer the battle callback) |
| Healed | All HP values restored to max |

For dialog that just needs advancing (NPC text, item fanfares): press A until context changes. The **stuck detector** in `ShortTermMemory` fires when the same action repeats 5+ times with no state change, switching the agent to dialog-advance mode automatically.

### Gen III Character Table (for Nickname/Name decoding)

```python
GEN3_CHARSET: dict[int, str | None] = {
    0x00: " ",
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xAF: "…",
    0xBB: "A", 0xBC: "B", 0xBD: "C", 0xBE: "D", 0xBF: "E",
    0xC0: "F", 0xC1: "G", 0xC2: "H", 0xC3: "I", 0xC4: "J",
    0xC5: "K", 0xC6: "L", 0xC7: "M", 0xC8: "N", 0xC9: "O",
    0xCA: "P", 0xCB: "Q", 0xCC: "R", 0xCD: "S", 0xCE: "T",
    0xCF: "U", 0xD0: "V", 0xD1: "W", 0xD2: "X", 0xD3: "Y",
    0xD4: "Z",
    0xD5: "a", 0xD6: "b", 0xD7: "c", 0xD8: "d", 0xD9: "e",
    0xDA: "f", 0xDB: "g", 0xDC: "h", 0xDD: "i", 0xDE: "j",
    0xDF: "k", 0xE0: "l", 0xE1: "m", 0xE2: "n", 0xE3: "o",
    0xE4: "p", 0xE5: "q", 0xE6: "r", 0xE7: "s", 0xE8: "t",
    0xE9: "u", 0xEA: "v", 0xEB: "w", 0xEC: "x", 0xED: "y",
    0xEE: "z",
    0xFC: "\n", 0xFD: "[NAME]", 0xFE: "\n\n", 0xFF: None,
}

def decode_gen3_string(raw: bytes) -> str:
    chars = []
    for byte in raw:
        ch = GEN3_CHARSET.get(byte)
        if ch is None:
            break
        chars.append(ch)
    return "".join(chars)
```

---

## Pokemon LeafGreen — Game Knowledge

### Type Chart (Gen III — no Fairy)

Row = attacking type. `2`=super effective, `½`=not very, `0`=immune.

|   | NOR | FIR | WAT | ELE | GRS | ICE | FIG | POI | GRD | FLY | PSY | BUG | ROC | GHO | DRG | DRK | STL |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|NOR| 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |½| **0** | 1 | 1 |½|
|FIR| 1 |½|½| 1 | **2** | **2** | 1 | 1 | 1 | 1 | 1 | **2** |½| 1 |½| 1 | **2** |
|WAT| 1 | **2** |½| 1 |½| 1 | 1 | 1 | **2** | 1 | 1 | 1 | **2** | 1 |½| 1 | 1 |
|ELE| 1 | 1 | **2** |½|½| 1 | 1 | 1 | **0** | **2** | 1 | 1 | 1 | 1 |½| 1 | 1 |
|GRS| 1 |½| **2** | 1 |½| 1 | 1 |½| **2** |½| 1 |½| **2** | 1 |½| 1 | 1 |
|ICE| 1 |½|½| 1 | **2** |½| 1 | 1 | **2** | **2** | 1 | 1 | 1 | 1 | **2** | 1 |½|
|FIG| **2** | 1 | 1 | 1 | 1 | **2** | 1 |½| 1 |½|½|½| **2** | **0** | 1 | **2** | **2** |
|POI| 1 | 1 | 1 | 1 | **2** | 1 | 1 |½|½| 1 | 1 |½|½|½| 1 | 1 | **0** |
|GRD| 1 | **2** | 1 | **2** |½| 1 | 1 | **2** | 1 | **0** | 1 |½| **2** | 1 | 1 | 1 | **2** |
|FLY| 1 | 1 | 1 |½| **2** | 1 | **2** | 1 | 1 | 1 | 1 | **2** |½| 1 | 1 | 1 |½|
|PSY| 1 | 1 | 1 | 1 | 1 | 1 | **2** | **2** | 1 | 1 |½| 1 | 1 | 1 | 1 | **0** |½|
|BUG| 1 |½| 1 | 1 | **2** | 1 |½|½| 1 |½| **2** | 1 | 1 |½| 1 | **2** |½|
|ROC| 1 | **2** | 1 | 1 | 1 | **2** |½| 1 |½| **2** | 1 | **2** | 1 | 1 | 1 | 1 |½|
|GHO| **0** | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 | 1 | **2** | 1 |½|½|
|DRG| 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 |½|
|DRK| 1 | 1 | 1 | 1 | 1 | 1 |½| 1 | 1 | 1 | **2** | 1 | 1 | **2** | 1 |½|½|
|STL| 1 |½|½|½| 1 | **2** | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 | 1 | 1 |½|

**Key immunities:** Ground→Electric (Flying/Levitate immune), Ghost→Normal+Fighting, Dark→Psychic, Steel→Poison.

### Gen III Physical/Special Split — Critical Rule

Damage category is determined by **move type**, not per-move. This is the biggest mechanical difference from Gen IV+.

| Physical (uses Atk vs Def) | Special (uses SpAtk vs SpDef) |
|---------------------------|-------------------------------|
| Normal, Fighting, Flying, Poison, Ground, Rock, Bug, **Ghost**, **Steel** | Fire, Water, Grass, Electric, Ice, Psychic, **Dragon**, **Dark** |

**Critical consequences:**
- **Shadow Ball** (Ghost) → Special. Useless on Machamp (high Atk, low SpAtk).
- **Crunch/Bite** (Dark) → Special. Does NOT benefit from high Attack.
- **Aerial Ace** (Flying) → Physical. Strong on high-Attack flyers.
- **Sabrina's Alakazam** uses SpAtk — bring high-SpDef counter or Bug moves (2× vs Psychic).
- **Ghost is NOT 2× vs Psychic in Gen III** (this was a Gen I bug). Ghost is immune to Psychic only if the Ghost move is used as the attacking move. Dark is 2× vs Psychic, but Dark is Special — only effective on high-SpAtk attackers.

### Starter Recommendation

**Choose Bulbasaur.** It trivializes the first two gyms (Vine Whip is Grass/Physical 2× vs Brock's Rock and Misty's Water), learns Sleep Powder for catching, and gives the agent more time to learn navigation before difficulty increases. Charmander is the hardest early game.

### Gym Order and Strategy

| # | Leader | City | Type | Key Threats | Counter |
|---|--------|------|------|-------------|---------|
| 1 | **Brock** | Pewter | Rock | Geodude L12, Onix L14 | Grass/Water. Vine Whip wins. |
| 2 | **Misty** | Cerulean | Water | Starmie L21 (has Recover) | Grass/Electric. Hit fast — Recover stalls. |
| 3 | **Lt. Surge** | Vermilion | Electric | Raichu L24 | Ground. Diglett from Diglett's Cave trivializes. |
| 4 | **Erika** | Celadon | Grass | Vileplume L29 (Sleep Powder) | Fire/Ice/Flying/Poison. Lum Berry blocks sleep. |
| 5 | **Koga** | Fuchsia | Poison | Weezing L43 (Self-Destruct) | Ground/Psychic. Bring Antidotes + Full Heals. |
| 6 | **Sabrina** | Saffron | Psychic | Alakazam L43 | Bug (2×). Dark moves only if high SpAtk. Ghost → immune (not 2×). |
| 7 | **Blaine** | Cinnabar | Fire | Arcanine L47 | Water. Any Surf user. Requires Surf to reach. |
| 8 | **Giovanni** | Viridian | Ground | Rhydon L50 | Water/Grass/Ice. Ice Beam for Rhydon. |

### HM Requirements

| HM | Required For | Where |
|----|-------------|-------|
| **Surf (HM03)** | All water routes — required for Gym 7 | Safari Zone warden quest (Gold Teeth) |
| **Strength (HM04)** | Boulders in caves — required for Victory Road | Same warden quest |
| Cut (HM01) | Optional tree shortcuts | S.S. Anne, Vermilion |
| Fly (HM02) | Fast travel | Route 16 house (need Cut) |
| Flash (HM05) | Rock Tunnel navigation | Route 2 Oak's aide |

### Story Path

```
Pallet → Viridian → Pewter [GYM1] → Cerulean [GYM2]
  → Vermilion [GYM3] + S.S. Anne (Cut HM)
  → Lavender (via Rock Tunnel) → Celadon [GYM4] + Rocket Hideout
  → Saffron (Silph Co. rescue) [GYM6]
  → Fuchsia [GYM5] + Safari Zone warden (Surf + Strength)
  → Cinnabar Island [GYM7] (requires Surf)
  → Viridian [GYM8] → Victory Road → Indigo Plateau [Elite Four + Champion Gary]
```

**Critical blockers:** Rock Tunnel is dark without Flash. Pokémon Tower needs Silph Scope (Celadon Rocket Hideout). Snorlax blocks Routes 12/16 — need Poke Flute from Mr. Fuji (Lavender). Silph Co. must be cleared to unlock Sabrina.

### Key Items and TMs

| Item | Location | Priority |
|------|----------|----------|
| TM26 Earthquake | Silph Co. | Critical — Ground/Physical 100 power |
| TM13 Ice Beam | Celadon Game Corner (4000 coins) | Critical — covers Dragon/Ground/Flying |
| TM24 Thunderbolt | Celadon Game Corner (4000 coins) | High |
| TM35 Flamethrower | Celadon Game Corner (4000 coins) | High |
| TM29 Psychic | Saffron man in house | High |
| Lapras | Silph Co. (free, L25) | Very High — only one available |
| Silph Scope | Celadon Rocket Hideout B4F | Critical — required for Pokémon Tower |
| Poke Flute | Mr. Fuji, Lavender | Critical — wakes Snorlax |

### Elite Four

| Trainer | Biggest Threat | Counter |
|---------|---------------|---------|
| Lorelei | Lapras L60 | Electric, Rock, Fighting |
| Bruno | Machamp L58 | Psychic, Flying |
| Agatha | Gengar L58 | Ground, Psychic |
| Lance | Dragonite L62 | **Ice Beam is critical.** Dragonite survives most else. |
| Gary | Alakazam + Rhydon + starter counter | Ice Beam for Rhydon; Psychic for Fighting |

---

## Agent Behavior

### Tool List

```python
# Defined in agent/tools.py. Navigation and battle are HIGH-LEVEL SKILLS —
# deterministic code drives the emulator; the LLM only picks destinations/moves.
go_to(destination: str)      # travel to a named map ("Pewter City") OR waypoint
                             #   ("Pokemon Center"/"Mart"/"Gym"). Auto-routes across
                             #   map connections + building/cave warps (BFS over
                             #   knowledge/map_graph.py); resumable on battle/dialog.
                             #   THE primary overworld tool.
walk_to(x: int, y: int)      # A* to a tile on the CURRENT map (routes around walls +
                             #   loaded NPCs; warp-aware; stops on battle/dialog).
go_to_map(direction: str)    # cross the seamless connection on one edge (N/S/E/W).
use_move(move: str)          # battle: drive the FIGHT menu and use a move by name,
                             #   confirming via that move's PP dropping.
press_button(button: str, times: int = 1)   # menus/dialog/nudges (times clamped 1–10)
read_game_state() -> GameState
save_state(slot: int = 0) / load_state(slot: int = 0)
wait_frames(frames: int)                     # advances the emulator (native) / waits (http)
record_milestone(name: str, note: str = "")  # persist a story milestone to long-term memory
```
The opponent is identified from memory (`gEnemyParty`), so there is no
`set_opponent` tool — it's shown in the observation automatically.

### Battle Decision Priority

1. Opponent + types are auto-detected (shown in the obs) — no need to set them.
2. `use_move("<name>")` to attack — prefer the super-effective / highest-power move with PP.
3. Switch if the opponent has a 2× type advantage and you have a better counter.
4. Heal if HP < 30% (`go_to("Pokemon Center")`, or Bag → Medicine).
5. Save state before every gym leader and every E4 trainer; after a loss, load and retry.

### Reward Schedule

| Event | Shaped (≤4 badges) | Sparse (>4 badges) |
|-------|-------------------|-------------------|
| Beat random trainer | +1.0 | +0.0 |
| Beat gym leader | +10.0 | +10.0 |
| Beat Elite Four member | +15.0 | +15.0 |
| Beat Champion | +50.0 | +100.0 |
| New badge | +5.0 | +10.0 |
| New town | +2.0 | +0.0 |
| Catch new species | +1.0 | +0.0 |
| Level up | +0.5 | +0.0 |
| Key item | +2.0 | +0.0 |
| Party faint | −1.0 | −0.5 |
| Blackout/loss | −2.0 | −1.0 |

Call `reward.anneal_to_sparse()` after the 4th badge.

All events above are wired in `main.py` **except** `elite_four_win` / `champion_win`
(the E4/Champion are trainer battles, so they currently fire `trainer_win`;
distinguishing them needs their trainer IDs — tracked in issue #22). Battle type
is read from `gBattleTypeFlags` (`0x02022B4C`), key items from the bag key-items
pocket.

---

## Development Reference

### Errors to Never Repeat

- mGBA is a **GBA** emulator. ROM must be `.gba`. Never `.nds`.
- mGBA-http is a **self-contained binary** (bundles its own .NET runtime). Never run with Python. Run it directly.
- Correct repo: `nikouu/mGBA-http`. Not `mgba-emu/mgbahttp`.
- Memory reads: `/core/read8|16|32|readrange` with **full absolute GBA addresses**.
- **No** `/core/memory/domain` endpoint — it doesn't exist.
- **No** `/core/state/save` — correct is `/core/savestateslot`.
- **No** `/core/frame/forward` — doesn't exist.
- Response from `/core/read8`: `"255"` (plain text decimal). Parse with `int(r.text.strip())`.
- Response from `/core/readrange`: `"d3,00,ea,66"` (comma-sep hex). Parse: `bytes(int(h,16) for h in r.text.strip().split(","))`.
- `slot` param for savestateslot/loadstateslot is a **string**, not integer: `params={"slot": "0"}`

### Startup Order (Every Session)

**Native backend (default) — two steps:**
```
1. LM Studio: load the model named in .env (MODEL_NAME), server port 1234, tools enabled
2. Terminal (fish): cd /Users/kylec/Projects/pokemon-agent → source .venv/bin/activate.fish → python main.py
```
main.py loads the ROM (`ROM_PATH`) in-process. No GUI, no Lua, no mGBA-http.
First time only: `python -m game._mgba_build` to compile the binding.

Run controls (env vars, native backend): `START_FROM_SAVE=<path.sav>` boots from a
battery save and drives to "Continue" (real gameplay instead of the new-game
intro); `MAX_STEPS=<n>` bounds a run for smoke/eval; `USE_VISION=false` runs
text-only (for text models or unstable vision). Example bounded text-only run:
`USE_VISION=false MAX_STEPS=20 START_FROM_SAVE=~/mgba-http/Pokemon_LeafGreen.sav python main.py`

**Legacy http backend (`MGBA_BACKEND=http`):**
```
1. Open /Applications/mGBA.app → File → Load ROM → ~/mgba-http/Pokemon_LeafGreen.gba
2. mGBA: Tools → Scripting → File → Load Script → ~/mgba-http/mGBASocketServer.lua
3. Terminal: ~/mgba-http/mGBA-http-0.8.2-osx-arm64-self-contained  (leave running)
4. LM Studio: load the model, server port 1234, tools enabled
5. Terminal (fish): cd .../pokemon-agent → source .venv/bin/activate.fish → python main.py
```

### Verification Commands

```fish
# Native backend: verify the binding loads the ROM in-process
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish
python -c "from game.mgba_core import NativeMGBAClient as C; m=C(); print(m.get_game_title(), m.get_game_code(), m.verify_connection())"
# Expected: POKEMON LEAF AGB-BPGE True

# Legacy http backend (only if MGBA_BACKEND=http and the server is running):
#   curl http://localhost:5000/core/getgametitle      -> "POKEMON LEAF"
#   curl http://localhost:5000/core/getgamecode        -> "AGB-BPGE"
#   curl "http://localhost:5000/core/read32?address=0x02024284"  -> 0-6
#   curl -X POST "http://localhost:5000/mgba-http/button/tap?button=A"

# Test Python imports  (fish shell)
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish
python -c "import requests, openai, rich; print('OK')"
```
