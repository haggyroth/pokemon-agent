# Pokemon LeafGreen LLM Agent

An autonomous AI agent that plays **Pokemon LeafGreen** on a GBA emulator using a locally-running large language model. The agent reads live game state directly from emulator memory, reasons about what to do next, and sends button inputs — no ROM hacks, no scripted walkthroughs.

## How it works

```
mGBA emulator
    │  Lua TCP socket → port 5000
mGBA-http REST API
    │  HTTP
Python agent
    ├── Reads GBA WRAM/IRAM (party data, badges, map, position)
    ├── Decrypts Gen III XOR-encrypted Pokémon substructures
    ├── Builds observation string + live screenshot
    └── Calls local LLM (LM Studio) with tool use → presses buttons
```

The LLM uses tool calling to press buttons, read game state, and save/load emulator states. A shaped reward system tracks progress and transitions to sparse rewards after badge 4.

## Features

- **Direct memory reading** — parses the 100-byte Gen III party struct, XOR-decrypts species ID and moves, reads HP/level/status unencrypted
- **Context detection** — distinguishes OVERWORLD / IN_BATTLE / TRANSITIONING via memory flags
- **Battle reasoning** — type chart lookups, Gen III physical/special split awareness, PP tracking
- **Navigation hints** — tilemap passability from ROM data, overhead area maps, revisit detection
- **Persistent memory** — battle journal (JSONL), long-term progress (JSON), session tracking
- **Stuck detection** — auto-advances dialog when the same action repeats with no state change
- **State save/load** — saves before gym leaders, loads on blackout

## Requirements

- Windows (paths use Windows conventions; easily adapted)
- [mGBA](https://mgba.io/) emulator
- [mGBA-http 0.8.2](https://github.com/nikouu/mGBA-http) — REST API for mGBA
- [LM Studio](https://lmstudio.ai/) with a tool-capable model (Qwen2.5-14B-Instruct recommended)
- Pokemon LeafGreen ROM (`.gba`, US version, game code `AGB-BPGE`)
- Python 3.12+

## Setup

### 1. Install dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```powershell
copy .env.example .env
```

Edit `.env` and set `MODEL_NAME` to match the model loaded in LM Studio. Everything else works with defaults if you use the standard ports.

### 3. Start the stack (in order)

1. **mGBA** → File → Load ROM → `Pokemon_LeafGreen.gba`
2. **mGBA**: Tools → Scripting → Load Script → `mGBASocketServer.lua` (from mGBA-http)
3. **mGBA-http** binary — run it, leave the window open (listens on port 5000)
4. **LM Studio** — load your model, enable the local server on port 1234, enable tool use
5. **Agent**:
   ```powershell
   .venv\Scripts\activate
   python main.py
   ```

### 4. Verify the connection

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/core/getgamecode"
# Expected: AGB-BPGE
```

## Configuration

All settings live in `.env` (copy from `.env.example`). Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `qwen/qwen2.5-14b-instruct` | Must match LM Studio model name exactly |
| `ENABLE_THINKING` | `false` | Set `true` for Qwen3 thinking models |
| `TEMPERATURE` | `0.6` | LLM sampling temperature |
| `SCREENSHOT_PATH` | `C:\mgba\agent_frame.png` | Where mGBA saves the agent's screenshot |
| `BUTTON_TAP_DELAY` | `0.10` | Seconds to pause after each button press |

## Project structure

```
├── main.py                   Main agent loop
├── config.py                 Settings loaded from .env
├── agent/
│   ├── lm_studio_client.py   LLM client, tool execution, screenshot handling
│   ├── tools.py              Tool schemas (press_button, read_game_state, etc.)
│   └── reward.py             Shaped → sparse reward tracker
├── game/
│   ├── mgba_client.py        Verified REST wrapper for mGBA-http 0.8.2
│   ├── memory_reader.py      Gen III XOR decryption + state machine
│   ├── state.py              GameState, PokemonStatus, StateDiff dataclasses
│   ├── constants.py          Memory addresses, charset, lookup tables
│   └── tilemap_reader.py     ROM passability data for navigation hints
├── memory/
│   ├── short_term.py         Per-session context (in-process)
│   ├── long_term.py          Persistent progress → logs/progress.json
│   └── battle_journal.py     JSONL battle log + loss-lesson retrieval
└── knowledge/
    ├── type_chart.py         Gen III type effectiveness
    ├── leafgreen_data.py     Gym data, badge bits, milestone names
    ├── navigation.py         Map names, travel direction hints
    ├── battle.py             Battle summary builder
    └── system_prompt.py      Dynamic system prompt builder
```

## Memory layout notes

All memory reads use full GBA bus addresses with mGBA-http's `/core/read8|16|32|readrange` endpoints. Party data at `0x02024288` uses Gen III XOR encryption (PID ^ OT_ID key); HP, level, and status are unencrypted and always reliable.

See [CLAUDE.md](CLAUDE.md) for the full memory map, API reference, and Gen III data structure documentation.

## Model recommendations

| Model | Notes |
|-------|-------|
| Qwen2.5-14B-Instruct | Solid default. Reliable tool use, good spatial reasoning. |
| Qwen3-14B (thinking on) | Better reasoning; set `ENABLE_THINKING=true`, `TEMPERATURE=0.6` |
| Llama 3.1 8B | Faster, weaker tool use — increase `MAX_TOKENS` |

The agent requires a model with **function/tool calling** support. Pure chat models won't work.

## Logs

- `logs/progress.json` — session count, badges, battles won/lost, towns visited
- `logs/battles.jsonl` — per-battle records used for loss-lesson retrieval

Both are gitignored. The `logs/` directory is preserved by `.gitkeep`.
