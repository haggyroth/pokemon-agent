# CLAUDE.md — Pokemon LeafGreen LLM Agent
**Project root:** `/Users/kylec/Projects/pokemon-agent`
**Platform:** macOS (Apple Silicon, arm64)
**Python:** 3.14 (project `.venv`) — all required packages compatible

> The code is cross-platform (paths use `pathlib`/`tempfile`); only the environment
> locations and shell commands below are host-specific. This file documents the macOS host.

> **For AI coding assistants:** This is the *operational* reference — what you need to
> build, run, and not break. Deep reference material (mGBA-http API, Gen III data
> structures/decryption, the type chart, game strategy) moved to
> [HISTORY.md](HISTORY.md); version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Emulator Backend

Two backends, selected by `MGBA_BACKEND` in `.env`:

- **`native` (default)** — drives libmgba **in-process** via a cffi binding. No mGBA
  GUI, no Lua, no mGBA-http, no HTTP. The agent owns the emulator and steps frames
  directly (~50× real-time, deterministic). This is the recommended path.
- **`http` (legacy)** — the old mGBA GUI + Lua socket + mGBA-http .NET transport.
  Kept as a fallback; full endpoint reference + canonical `MGBAClient` in [HISTORY.md](HISTORY.md).

### Native backend

| Component | Location | Notes |
|-----------|----------|-------|
| libmgba | Homebrew (`brew install mgba`) — `/opt/homebrew/lib/libmgba.dylib` | Provides the core + headers the binding builds against |
| Binding source | `game/_mgba_build.py` | cffi builder → `game/_mgba_native*.so` (gitignored) |
| Native client | `game/mgba_core.py` (`NativeMGBAClient`) | Drop-in for `MGBAClient` |
| LeafGreen ROM | `~/mgba-http/Pokemon_LeafGreen.gba` (override with `ROM_PATH`) | US v1.0, 16 MB |
| LLM (local or cloud) | `MODEL_NAME` + `LLM_BASE_URL`/`LLM_API_KEY` in `.env` — a tool-capable model | Local: LM Studio on port 1234. Cloud: point `LLM_BASE_URL` at any OpenAI-compatible endpoint (OpenAI, OpenRouter, …). Text-only models: `USE_VISION=false`; ensure `MAX_TOKENS` fits the loaded context |

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

## Memory Addresses & Context Detection

**`game/constants.py` (the `Addr` class) and `game/memory_reader.py` are the
authoritative source.** All are full GBA bus addresses (usable directly with the
native binding's reads, or `/core/read8|16|32|readrange`). Do not hand-copy the
full map here — several addresses were re-derived empirically during development
(diffing live save states) and a duplicate list drifts. The notable, hard-won
ones:

| What | Address | Notes |
|------|---------|-------|
| Party count / data | `0x02024284` / `0x02024288` | 6 × 100-byte structs (Gen III XOR, see HISTORY.md) |
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

Party-data XOR decryption, the 100-byte struct layout, and the Gen III charset are
documented in [HISTORY.md](HISTORY.md) (implemented in `memory_reader.py` /
`constants.py`). Dialog/event detection via state-diffing is also in HISTORY.md.

---

## Agent Behavior

### Tool List

```python
# Defined in agent/tools.py. Navigation, battle, and menu actions are all HIGH-LEVEL
# SKILLS — deterministic code drives the emulator; the LLM only picks the intent
# (destination / move / item / target). Each skill self-verifies via memory and is
# resumable/clean-failing rather than mashing buttons.

# ── Navigation ────────────────────────────────────────────────────────────────
go_to(destination: str)      # travel to a named map ("Pewter City") OR waypoint
                             #   ("Pokemon Center"/"Mart"/"Gym"). BFS over map_graph +
                             #   warps; auto-flees wild battles; stops resumably on a
                             #   trainer/low-HP/block; gives guidance on a stalled route;
                             #   stops on a NEW wild species (team-building). Primary tool.
walk_to(x: int, y: int)      # A* to a tile on the CURRENT map (walls/ledges/NPCs).
go_to_map(direction: str)    # cross the seamless connection on one edge (N/S/E/W).
# ── Battle ────────────────────────────────────────────────────────────────────
use_move(move: str)          # drive the FIGHT menu by name; confirms via PP drop; also
                             #   resolves a level-up move-learn per knowledge/movelearn.py.
switch_pokemon(target: str)  # swap the active mon (species name or 1-based slot);
                             #   verifies via gBattleMons[0].species. (Known limit: a
                             #   2nd switch back to the just-active slot can fail cleanly.)
use_item(item: str)          # Potion / status cure on the active lead, from the Items pocket.
catch()                      # throw a Poké Ball (verdict from gBattleOutcome).
flee_battle()                # run from a WILD battle (writes action cursor = RUN).
# ── Progression / field ───────────────────────────────────────────────────────
heal()                       # restore the party at the nearest Pokémon Center.
shop()                       # buy a badge-gated, par-level restock at a Mart.
grind(level: int)            # auto-fight wild Pokémon until the lead hits `level`.
pick_up_items()              # collect item balls (gObjectEvents gfx 92) on this map.
challenge_leader()           # walk up to the Gym Leader and start the battle.
# ── Meta ──────────────────────────────────────────────────────────────────────
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
3. `switch_pokemon(...)` if the opponent has a 2× type advantage and you have a better counter.
4. Heal a low mon mid-battle with `use_item("Potion")`; out of battle `heal()` if HP/PP low.
5. `catch()` a weakened wild Pokémon to build a team (a lone mon can't sustain a dungeon/E4).
6. Save state before every gym leader and every E4 trainer; after a loss, load and retry.

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
