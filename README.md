# Pokemon LeafGreen LLM Agent

[![CI](https://github.com/haggyroth/pokemon-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/haggyroth/pokemon-agent/actions/workflows/ci.yml)

An autonomous AI agent that plays **Pokemon LeafGreen** using a locally-running large language model. The agent reads live game state directly from emulator memory, reasons about what to do next, and sends button inputs — no ROM hacks, no scripted walkthroughs.

By default it drives **libmgba in-process** (via a small cffi binding): no emulator GUI, no Lua, no HTTP — just Python controlling the core directly at many times real-time. A legacy HTTP backend (mGBA + mGBA-http) is still supported for spectating in the real mGBA window.

## How it works

```
Pokemon_LeafGreen.gba
        │
   libmgba  ──cffi──►  game/_mgba_native  (in-process, headless, ~50× realtime)
        │
   Python agent
     ├── Reads GBA WRAM/IRAM (party data, badges, map, position)
     ├── Decrypts Gen III XOR-encrypted Pokémon substructures
     ├── Builds an observation string + live screenshot
     └── Calls a local LLM (LM Studio) with tool use → presses buttons
```

The agent works through **deterministic high-level skills**, not raw button-mashing: the LLM picks *what* to do (a destination, a move, a Pokémon to switch to) and tested Python code drives the emulator to do it reliably. This is the core design — the model reasons about strategy while the skills handle the finicky menu/frame timing. A shaped reward system tracks progress and transitions to sparse rewards after badge 4.

## What it can do

The agent has a full gameplay skill set. The LLM calls these as tools:

**Navigation**
- `go_to("<place>")` — travel to a named map or waypoint ("Pewter City", "Pokémon Center", "Mart", "Gym"), auto-routing across map connections and building/cave warps (BFS over a graph generated from the pokefirered decomp). Auto-flees wild battles so a whole route/forest is one call; stops resumably on a trainer, low HP, or a block. Detects a stalled route and gives actionable guidance instead of looping. Stops on a *new* wild species so the agent can build a team.
- `walk_to(x, y)` — A* to a tile on the current map, routing around walls, ledges, and loaded NPCs.
- `go_to_map(direction)` — cross a seamless map-edge connection.

**Battle**
- `use_move("<name>")` — drive the FIGHT menu by memory (opponent identified from RAM, type-chart + Gen III physical/special-split analysis in the observation). Resolves a level-up **move-learn** prompt per a policy that never cripples the moveset.
- `switch_pokemon(target)` — swap in another party member (type advantage / save a low mon).
- `use_item(name)` — Potions and status cures from the bag, on the active Pokémon.
- `catch()` — throw a Poké Ball (verdict read from `gBattleOutcome`); `flee_battle()` — run from a wild battle.

**Progression & survival**
- `heal()` — restore the party at the nearest Pokémon Center; `shop()` — buy a badge-gated, par-level restock at a Mart; `grind(level)` — auto-fight wild Pokémon to a target level.
- `pick_up_items()` — collect item balls on the ground; `challenge_leader()` — walk up to a Gym Leader and start the fight.
- `record_milestone`, `save_state` / `load_state`, `read_game_state`, `press_button`, `wait_frames`.

## Features

- **In-process emulation** — libmgba driven directly in Python; deterministic frame stepping, no network round-trips, ~50× real-time
- **Direct memory reading** — parses the 100-byte Gen III party struct, XOR-decrypts species ID and moves, reads HP/level/status/PP unencrypted
- **Context detection** — distinguishes OVERWORLD / IN_BATTLE / DIALOG / IN_MENU / TRANSITIONING via the live `gMain.callback2` dispatcher
- **Team-building & resource awareness** — nudges the agent to catch a team, surfaces move PP (so it heals before running its moves dry), recommends restocks
- **Navigation hints** — tilemap passability, warps, and connections from ROM data; overhead area maps
- **Persistent memory** — battle journal (JSONL), long-term progress (JSON), session tracking, loss-lesson retrieval
- **Live viewer** — optional pygame window to watch the agent play (`SHOW_WINDOW=true`)
- **Run guardrails** — per-call `LLM_TIMEOUT` and a wall-clock cap so an unattended run can't hang; state save/load before gyms and on blackout
- **Eval harness** — score real agent runs against goals (see below)

## Requirements

- **Python 3.11+**
- **libmgba** — `brew install mgba` (macOS) or your distro's `libmgba` package (Linux). Provides the core the binding compiles against.
- A C compiler (Xcode Command Line Tools on macOS; `build-essential` on Linux) — cffi builds a small extension.
- [LM Studio](https://lmstudio.ai/) with a **tool-capable** model, local server on port 1234
- Pokemon LeafGreen ROM (`.gba`, US version, game code `AGB-BPGE`) — supply your own
- *(legacy `http` backend only)* [mGBA](https://mgba.io/) + [mGBA-http 0.8.2](https://github.com/nikouu/mGBA-http)

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

brew install mgba                 # or your Linux libmgba package
python -m game._mgba_build        # compiles game/_mgba_native (the cffi binding)

cp .env.example .env              # then edit: set MODEL_NAME and ROM_PATH
```

Point `ROM_PATH` in `.env` at your LeafGreen `.gba`, and set `MODEL_NAME` to match the model loaded in LM Studio.

### Run

1. **LM Studio** — load your model, start the local server on port 1234, enable tool use.
2. **Agent**:
   ```sh
   source .venv/bin/activate
   python main.py
   ```

That's it — `main.py` loads the ROM in-process. Set `SHOW_WINDOW=true` in `.env` to watch it play in a window.

### Spectating via the legacy backend

Set `MGBA_BACKEND=http` in `.env` to use the original transport instead: start mGBA, load `mGBASocketServer.lua` (Tools → Scripting), run the mGBA-http binary (port 5000), then `python main.py`. You get the real mGBA window at the cost of real-time speed and extra processes.

## Configuration

All settings live in `.env` (copy from `.env.example`). Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `MGBA_BACKEND` | `native` | `native` (in-process libmgba) or `http` (legacy mGBA-http) |
| `ROM_PATH` | `~/mgba-http/Pokemon_LeafGreen.gba` | Path to the LeafGreen `.gba` (native backend) |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint. Point at a cloud provider (OpenAI, OpenRouter, …) to use cloud models |
| `LLM_API_KEY` | `lm-studio` | API key for the endpoint (placeholder for local; your provider key for cloud) |
| `MODEL_NAME` | — | Model id: the LM Studio name locally, or the provider's id (e.g. `gpt-4o`) for cloud |
| `START_FROM_STATE` | — | Path to an mGBA save state (`.ss*`) to boot into directly (no title/Continue/recap) |
| `ENABLE_THINKING` | `false` | Set `true` for reasoning models that expose thinking tokens |
| `TEMPERATURE` | `0.6` | LLM sampling temperature |
| `MAX_TOKENS` | `4096` | Response cap. `prompt + MAX_TOKENS` must fit the model's **loaded** context, or calls fail with "Context size exceeded" |
| `USE_VISION` | `true` | Attach the screenshot to the model. Set `false` for text-only models or unstable vision |
| `START_FROM_SAVE` | — | Path to a battery `.sav` to load and "Continue" into at startup (native) |
| `MAX_STEPS` | `0` | Stop after N decision steps (`0` = run until interrupted) |
| `MAX_LLM_CALLS` | `0` | Stop after N LLM API calls (`0` = unlimited). Spend guard for cloud endpoints |
| `TOKEN_BUDGET` | `0` | Stop once cumulative prompt+completion tokens reach this (`0` = unlimited) |
| `SHOW_WINDOW` | `false` | Live pygame window (native backend; requires `pygame`) |
| `VIEWER_SCALE` | `3` | Window scale — 240×160 × scale |
| `VIEWER_FPS` | `120` | Viewer playback pace cap (≈2× GBA speed); `0` = full emulator speed |
| `LLM_TIMEOUT` | `180` | Per chat-completion timeout (s); bounds a single call so a slow/hung endpoint can't stall a run. `0` = none |
| `MAX_WALL_SECONDS` | `0` | Hard wall-clock cap on a whole run (`0` = unlimited) |

## Testing

Hardware-free unit tests cover the Gen III decoder, state machine, type chart, reward logic, and charset — no ROM, libmgba, or network required.

```sh
pip install -r requirements-test.txt
python -m pytest          # unit tests
ruff check .              # lint (real-error rules)
```

Tests that need the compiled binding or a ROM skip automatically when those aren't present. [CI](.github/workflows/ci.yml) runs the suite on Python 3.11–3.13 and separately builds the native binding against libmgba on macOS.

## Eval harness

Measuring whether a run actually made progress — instead of reading hundreds of
log lines — is what `evals/` is for. It runs the **real agent loop**
(`main.run_episode`) from a start state toward a goal with a step budget, and
scores the episode: pass/fail, steps, reward, **stuck-ratio** (overworld ticks
with no movement — the signature of a nav skill that can't cross), LLM calls, and
tokens. Each scenario runs in isolation (its own scratch `progress.json`), so the
real save is never touched.

```sh
python -m evals --list            # show scenarios
python -m evals                   # run all (needs LM Studio/cloud + ROM up, like main.py)
python -m evals -s reach_pewter -v  # one scenario, streaming output
```

Results print as a table and are written to `logs/eval/<timestamp>.json`.
Scenarios live in [`evals/scenarios.py`](evals/scenarios.py); goals (reach a map,
earn N badges, hit a milestone, …) in [`evals/goals.py`](evals/goals.py). Goals
and scenarios are pure/light-importing so they unit-test in CI.

A scenario can be marked `xfail=<issue>` to document a known failure — e.g.
`reach_pewter` (#59: Route 2 is gated by Viridian Forest, and `go_to` walks to the
sealed north edge instead of warping through). The harness reports it as an
expected failure, flipping to a loud **XPASS** the day the bug is fixed.

There's also a **Tier-1** deterministic skill check
([`tests/test_nav_scenarios.py`](tests/test_nav_scenarios.py)) that drives the nav
skills directly with **no LLM** — a failure there is unambiguously a
pathfinding/routing bug. It boots a real emulator, so it's opt-in:
`RUN_NAV_EVALS=1 python -m pytest tests/test_nav_scenarios.py`.

## Project structure

```
├── main.py                   Main agent loop
├── config.py                 Settings loaded from .env
├── agent/
│   ├── lm_studio_client.py   LLM client (local/cloud) + nav/battle skills, tool loop
│   ├── tools.py              Tool schemas (go_to, walk_to, use_move, press_button, …)
│   ├── history.py            Message trimming + control-token stripping
│   └── reward.py             Shaped → sparse reward tracker
├── game/
│   ├── _mgba_build.py        cffi builder for the in-process libmgba binding
│   ├── mgba_core.py          NativeMGBAClient — drives libmgba in-process (default)
│   ├── mgba_client.py        MGBAClient — legacy mGBA-http REST wrapper
│   ├── viewer.py             Optional pygame window (SHOW_WINDOW)
│   ├── memory_reader.py      Gen III XOR decryption + state machine
│   ├── state.py              GameState, PokemonStatus, StateDiff dataclasses
│   ├── constants.py          Memory addresses, charset, lookup tables
│   ├── pathfinding.py        A* grid pathfinding (pure/testable)
│   └── tilemap_reader.py     ROM passability, warps, and connections
├── memory/                   Short-term, long-term, and battle-journal memory
├── knowledge/                Type chart, gym data, navigation, map_graph, prompts
├── evals/                    Eval harness — goals, scenarios, runner (python -m evals)
├── tools/gen_map_graph.py    Regenerate knowledge/map_graph.py from a pokefirered checkout
└── tests/                    Hardware-free unit tests
```

## Memory layout notes

All memory reads use full GBA bus addresses, identical between the native binding and the HTTP API, so the decoder is backend-agnostic. Party data at `0x02024284` uses Gen III XOR encryption (PID ^ OT_ID key); HP, level, status, and PP are unencrypted and always reliable.

**On writes:** the agent treats game RAM as read-only for observation — it does not touch save data, badges, stats, experience, RNG, or battle outcomes. The only sanctioned writes are **menu cursor positions** — the FIGHT move cursor, the battle action cursor (FIGHT/BAG/POKÉMON/RUN), and the bag/party list cursors — which the skills set to a target before pressing A. That's exactly equivalent to navigating a menu with the D-pad (it only chooses *which* legal option to select, deterministically, avoiding dropped-input flakiness); it never alters game logic or outcomes. This is why "no ROM hacks" above refers to the ROM and game rules, not a claim that no RAM byte is ever written.

The authoritative memory map is [`game/constants.py`](game/constants.py); see [CLAUDE.md](CLAUDE.md) for context-detection details, backend notes, and Gen III data structure documentation.

## Model recommendations

The agent requires a model with **function/tool calling** support — pure chat models won't work. Practical notes from running it:

- **Reasoning models work well** and don't need vision — the observation string carries the key state. A ~9B reasoning model with tool calling reasons and navigates coherently.
- **Vision is optional and can be flaky.** Some quantized multimodal builds crash or blow their context on the screenshot; set `USE_VISION=false` to run text-only.
- **Mind the context window.** `prompt + MAX_TOKENS` must fit the model's *loaded* context in LM Studio (not its max) — an oversized `MAX_TOKENS` makes every call fail with "Context size exceeded."
- On consumer hardware, keep LM Studio to **one concurrent generation**.

## Logs

- `logs/progress.json` — session count, badges, battles won/lost, towns visited
- `logs/battles.jsonl` — per-battle records used for loss-lesson retrieval

Both are gitignored. The `logs/` directory is preserved by `.gitkeep`.
