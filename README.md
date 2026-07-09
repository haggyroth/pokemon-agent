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

The LLM uses tool calling to press buttons, read game state, and save/load emulator states. A shaped reward system tracks progress and transitions to sparse rewards after badge 4.

## Features

- **In-process emulation** — libmgba driven directly in Python; deterministic frame stepping, no network round-trips
- **Direct memory reading** — parses the 100-byte Gen III party struct, XOR-decrypts species ID and moves, reads HP/level/status unencrypted
- **Context detection** — distinguishes OVERWORLD / IN_BATTLE / DIALOG / TRANSITIONING via memory flags
- **High-level navigation skills** — `go_to("<place>")` auto-routes across map connections and building/cave doors (BFS over a graph generated from the pokefirered decomp), incl. waypoints like "Pokemon Center"; `walk_to(x,y)` A*-paths around walls and NPCs. The LLM picks destinations; code drives movement
- **Battle skills** — opponent read from memory, type-chart / physical-special-split analysis, and `use_move("<name>")` that drives the FIGHT menu deterministically
- **Navigation hints** — tilemap passability, warps, and connections from ROM data; overhead area maps
- **Persistent memory** — battle journal (JSONL), long-term progress (JSON), session tracking
- **Live viewer** — optional pygame window to watch the agent play (`SHOW_WINDOW=true`)
- **State save/load** — saves before gym leaders, loads on blackout

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
| `VIEWER_FPS` | `60` | Playback cap; `0` = full emulator speed |

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

All memory reads use full GBA bus addresses, identical between the native binding and the HTTP API, so the decoder is backend-agnostic. Party data at `0x02024288` uses Gen III XOR encryption (PID ^ OT_ID key); HP, level, and status are unencrypted and always reliable.

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
