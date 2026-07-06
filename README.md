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
- **Battle reasoning** — type chart lookups, Gen III physical/special split awareness, PP tracking
- **Navigation hints** — tilemap passability from ROM data, overhead area maps, revisit detection
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
| `MODEL_NAME` | — | Must match the LM Studio model name exactly |
| `ENABLE_THINKING` | `false` | Set `true` for reasoning models that expose thinking tokens |
| `TEMPERATURE` | `0.6` | LLM sampling temperature |
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

## Project structure

```
├── main.py                   Main agent loop
├── config.py                 Settings loaded from .env
├── agent/
│   ├── lm_studio_client.py   LLM client, tool execution, screenshot handling
│   ├── tools.py              Tool schemas (press_button, read_game_state, etc.)
│   └── reward.py             Shaped → sparse reward tracker
├── game/
│   ├── _mgba_build.py        cffi builder for the in-process libmgba binding
│   ├── mgba_core.py          NativeMGBAClient — drives libmgba in-process (default)
│   ├── mgba_client.py        MGBAClient — legacy mGBA-http REST wrapper
│   ├── viewer.py             Optional pygame window (SHOW_WINDOW)
│   ├── memory_reader.py      Gen III XOR decryption + state machine
│   ├── state.py              GameState, PokemonStatus, StateDiff dataclasses
│   ├── constants.py          Memory addresses, charset, lookup tables
│   └── tilemap_reader.py     ROM passability data for navigation hints
├── memory/                   Short-term, long-term, and battle-journal memory
├── knowledge/                Type chart, gym data, navigation, prompts
└── tests/                    Hardware-free unit tests
```

## Memory layout notes

All memory reads use full GBA bus addresses, identical between the native binding and the HTTP API, so the decoder is backend-agnostic. Party data at `0x02024288` uses Gen III XOR encryption (PID ^ OT_ID key); HP, level, and status are unencrypted and always reliable.

See [CLAUDE.md](CLAUDE.md) for the full memory map, backend details, and Gen III data structure documentation.

## Model recommendations

The agent requires a model with **function/tool calling** support — pure chat models won't work. Playing Pokémon well over long horizons is hard for smaller local models; larger tool-capable models reason and navigate more reliably.

## Logs

- `logs/progress.json` — session count, badges, battles won/lost, towns visited
- `logs/battles.jsonl` — per-battle records used for loss-lesson retrieval

Both are gitignored. The `logs/` directory is preserved by `.gitkeep`.
