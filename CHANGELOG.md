# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions use [SemVer](https://semver.org/).

## [0.12.1]

### Fixed
- fix: harden reliability blockers found in code review — startup badge
  reconciliation now reads the relocation-safe `reader.read_badges()` instead of
  the fixed `Addr.BADGES` (a DMA-relocated read fabricated phantom badges into
  LTM); the tool-execution loop wraps `_execute` so a malformed model tool call
  can no longer orphan `tool_calls` in history and cascade API 400s;
  `progress.json` is written atomically (temp + fsync + `os.replace`) and a
  corrupt file is renamed aside instead of crashing startup; the main-loop
  catch-all logs full tracebacks to `logs/errors.log` and exits cleanly after 30
  consecutive failing ticks instead of spinning forever (#60, #61, #62, #65)

## [0.12.0]

### Added
- feat: configurable LLM endpoint + API key (`LLM_BASE_URL`, `LLM_API_KEY`) so the
  agent can use any OpenAI-compatible cloud model (OpenAI, OpenRouter proxying
  Claude/Gemini, etc.), not just local LM Studio. Local defaults unchanged (#56)

## [0.11.1]

### Fixed
- fix: run-feedback nav fixes — `go_to` waypoints match fuzzily ("Viridian
  Pokemart", "Poké Mart", "Pewter City Gym" now resolve); the building-exit hint
  points at the functional center door tile (multi-tile doormats where only the
  middle warps); removed the redundant `set_opponent` tool (opponent is read from
  memory); system prompt refreshed to the current tools (#55)

## [0.11.0]

### Added
- feat: warp-aware routing + waypoints — `go_to(destination)` now routes across
  building/cave warps as well as connections, and accepts waypoints ("Pokemon
  Center", "Mart", "Gym") routed to the nearest one (`MAP_WARPS`/`MAP_KIND` +
  `route_to`/`nearest_of_kind` in map_graph.py). `walk_to` routes around on-screen
  NPCs (gObjectEvents) and can target door tiles on walls. Completes the nav
  system (#54, closes #51)

### Fixed
- fix: removed an incorrect constants note claiming 0x0202402C is gFrameCount —
  verified live it is gEnemyParty (opponent ID was correct)

## [0.10.0]

### Added
- feat: working `use_move(name)` — deterministic battle move selection. Detects
  the FIGHT menu (`gBattlerControllerFuncs[0]`), writes the target slot to
  `gMoveSelectionCursor` (0x02023FFC), commits with A, and waits for the turn to
  RESOLVE before confirming via that move's PP dropping (the missing piece — moves
  execute after the turn resolves, not on confirm). Verified: correct-slot
  selection + 3/3 wild battles won. Closes #48

## [0.9.0]

### Added
- feat: multi-hop `go_to(destination)` — auto-routes across multiple connected
  maps via a BFS over `knowledge/map_graph.py` (generated from the pokefirered
  decomp; 63 overworld maps). Crosses each edge, and stops resumably on a wild
  battle/dialog or a blocked hop. `go_to` is now the main overworld travel tool
  (#52, part of #51)

## [0.8.0]

### Added
- feat: `go_to(destination)` — travel toward a named map (resolves the name and
  crosses if it's a live connection, else reports adjacent maps). Observation now
  includes map size so the model stops picking off-map `walk_to` targets. Nav
  Track B (#50)

## [0.7.4]

### Fixed
- fix: `walk_to` stops on a wild battle or dialog that interrupts a walk (it only
  stopped on a map change before, so it mashed through grass into an encounter).
  Now returns on IN_BATTLE/DIALOG_OPEN. First piece of nav Track B (#49)

## [0.7.3]

### Fixed
- fix: battle button presses now register — short taps are dropped during battle
  text/animations, so `press_button` uses wait-until-idle + hold when in battle
  (`NativeMGBAClient.wait_until_idle`). This was the root cause of the in-battle
  flailing; driving a fight now reliably progresses and wins. Also found the
  move-selection cursor (`MOVE_CURSOR`) for a future `use_move` (#47)

## [0.7.2]

### Fixed
- fix: the battle opponent is identified from memory (`gEnemyParty[0]` at
  `0x0202402C`) instead of the model reading the species off-screen (which was
  wrong). `read_enemy_lead()` decodes it with the existing XOR logic; the loop
  refreshes it each battle tick and shows real opponent HP/level. `set_opponent`
  is now only a fallback (#46)

## [0.7.1]

### Added
- feat: `go_to_map(direction)` tool — cross the seamless map connection on an edge
  (walk to the opening, step across) to travel between towns/routes. Completes the
  navigation skill layer: verified end-to-end bedroom → Pallet Town → Route 1 in
  two deterministic tool calls (#45)

## [0.7.0]

### Added
- feat: `walk_to(x, y)` navigation tool — A* pathfinding over the tilemap
  (`game/pathfinding.py` + `TilemapReader.passable_grid()`) drives the player to a
  destination instead of the model pressing directions tile-by-tile. Replans
  around NPCs, stops on map change, and is warp-aware (one `walk_to(door)` leaves
  a building). System prompt now prefers it for travel; `press_button` is for
  menus/battle/dialog. First half of the LLM-as-strategist pivot (#44)

## [0.6.3]

### Added
- feat: `TilemapReader.read_connections()` reads gMapHeader map connections;
  outdoors the observation lists which edge leads where ("Map edges: North→Route
  1, South→Route 21"). Town/route exits are seamless connections (not warps), so
  the agent previously had no way to find them. First piece of the nav skill
  layer (#43)

## [0.6.2]

### Fixed
- fix: badges are read via the live SaveBlock1 pointer (`deref+0x41C`) instead of
  the fixed `0x02025968`. gSaveBlock1 is DMA-relocated on map transitions, so the
  fixed address drifted off the badge byte after a warp and returned garbage —
  producing phantom badges and false gym/milestone rewards (e.g. a bogus
  beat_surge). Completes the SaveBlock1-relocation audit (#42)

## [0.6.1]

### Added
- feat: `START_FROM_STATE` run control — load an mGBA save state (`.ss*`) directly
  at startup (native), landing instantly in that scene with no title/Continue/
  recap. Takes precedence over `START_FROM_SAVE`. Useful for testing from a fixed
  spot (a Pallet Town exterior state ships in `saves/`, gitignored) (#41)

## [0.6.0]

### Added
- feat: interior exit guidance. `TilemapReader.read_warps()` reads the current
  map's door/stairs tiles; when the agent is indoors the route guidance says
  "leave the building first" and the observation lists the exit tiles with the
  nearest one and step-by-step direction to it (#40)

## [0.5.5]

### Fixed
- fix: the current map is now read from the live DMA block (`[PLAYER_PTR]+0x04/05`)
  instead of the absolute `0x02031DBC/DBD`, which is the *parent outdoor* map and
  stays on the town while indoors. The agent was misreading every interior as the
  town (e.g. the player's bedroom read as "Pallet Town"), getting outdoor route
  guidance it couldn't act on (#39)

## [0.5.4]

### Fixed
- fix: a stale `MENU_OPEN` flag no longer traps the agent in a phantom `IN_MENU`.
  The flag over-stays after a full-screen menu (Pokédex/Bag/…) closes; the
  `IN_MENU` gate now also requires `SCREEN_FADE` (which clears on close), rebuilt
  around `gMain.callback2` (#38)

## [0.5.3]

### Fixed
- fix: `press_button` accepts compass synonyms (North/South/East/West, N/S/E/W)
  and maps them to Up/Down/Left/Right — the observation labels tiles N/S/E/W, so
  the model kept calling invalid button names and wasting steps (#37)
- fix: frame each turn as a directive — a "How this works" loop-contract section
  in the system prompt plus an explicit call-to-action on every observation, so
  the model acts (calls a tool) instead of replying "there's no task" (#37)

## [0.5.2]

### Fixed
- fix: `START_FROM_SAVE` now skips the FRLG "Previously on your quest…" quest-log
  recap. The recap masquerades as the overworld (and auto-animates the player),
  so the old A-mash-until-OVERWORLD drive got stuck in it; the continue drive now
  presses B until the desaturated recap palette clears to full color (#36)

## [0.5.1]

### Fixed
- fix: viewer colors were wrong — convert the framebuffer surface to the display
  format before scaling (the raw RGBX was fine; the direct display-surface scale
  reinterpreted channels) (#35)

## [0.5.0] — 2026-07-07

### Added
- feat: `USE_VISION` toggle for text-only runs — skip the screenshot / area-map
  images (for text-only models, or models whose vision is unstable) (#32)

### Fixed
- fix: `AgentClient.step()` caps tool-call rounds per decision (`MAX_TOOL_ROUNDS`)
  so one step can't run unbounded generations; and strips leaked control tokens
  (`<|channel|>`, …) from model output (#31)

## [0.4.0] — 2026-07-07

### Added
- feat: `START_FROM_SAVE` (boot from a battery `.sav` and Continue into gameplay)
  and `MAX_STEPS` (bounded runs) run controls, for smoke/eval runs

## [0.3.10] — 2026-07-07

### Fixed
- fix: align agent guidance with the `IN_MENU` / `DIALOG_OPEN` contexts introduced
  by the detect_context rebuild — new "Game Contexts" prompt section, corrected
  decision priorities, and the loop's auto-advance-A now fires on `DIALOG_OPEN`
  (not in `IN_MENU`)

## [0.3.9] — 2026-07-07

### Fixed
- fix: the `key_item` reward now fires when a bag key item is obtained (bag
  key-items pocket at `gSaveBlock1 + 0x3B8`; generic, covers all key items)
  (partial #22; elite_four_win/champion_win still pending)

## [0.3.8] — 2026-07-07

### Fixed
- fix: the `trainer_win` reward now fires, via the real `gBattleTypeFlags`
  (`0x02022B4C`, TRAINER bit `0x08`) captured at battle start (partial #22;
  elite_four_win/champion_win/key_item still pending)

## [0.3.7] — 2026-07-06

### Fixed
- fix: the battle "Best move" hint now ranks by power × STAB × effectiveness (new
  `MOVE_POWER` table), so a strong neutral move can outrank a weak super-effective
  one — completing the best-move improvements (#19)

## [0.3.6] — 2026-07-06

### Fixed
- fix: all field menus (Start, Bag, Party, Trainer Card, Option, …) now read as
  `IN_MENU` via a general menu-open flag (`0x03002415`), completing the menu
  detection started in 0.3.5 and preventing spurious auto-A in any menu (#18)

## [0.3.5] — 2026-07-06

### Fixed
- fix: the overworld Start menu now reads as `IN_MENU` instead of `TRANSITIONING`
  (via the overlay callback at `0x0300512C`), suppressing navigation hints and a
  spurious auto-A tap there. `SCREEN_FADE` was found to stay 1 while the menu is
  open. Full-screen submenus still pending (partial #18)

## [0.3.4] — 2026-07-06

### Fixed
- fix: removed unreachable Center/Mart/Gym building-guide dead code (#17)
- fix: capped `press_button` repeats and stopped treating map position (0,0) as
  "unknown" in stuck detection (#20)
- fix: battle "Best move" now excludes non-damaging status moves and applies STAB
  (partial #19; base-power ranking still pending)

## [0.3.3] — 2026-07-06

### Fixed
- fix: `wait_frames` tool now advances the emulator instead of a real-time sleep,
  which was a no-op on the native backend (#13)
- fix: conversation-history trimming no longer orphans tool messages (which could
  crash a run with an API 400); it cuts only at user-turn boundaries (#16)
- fix: the current opponent is passed into the system prompt, so battle-journal
  loss lessons actually reach the model (#15)
- fix: fire `gym_leader_win` and `party_faint` rewards, which were never awarded
  (partial #14; remaining reward types tracked in #22)

## [0.3.2] — 2026-07-06

### Fixed
- fix: the battle journal records the Pokémon that was actually fighting (tracked
  as the last party slot to take damage), not always the lead (#2)

## [0.3.1] — 2026-07-06

### Fixed
- fix: `detect_context` now uses `gMain.callback2` instead of the bogus
  `OVERWORLD_FLAG` (which read 0 during free-roam, misdetecting the overworld as
  TRANSITIONING). Resolves the context gate and the SCRIPT_RAM dialog-byte
  question (#10, #1, #5)

## [0.3.0] — 2026-07-06

### Added
- feat: `NativeMGBAClient.load_save(path)` and `reset()` — boot the native backend
  from an existing cartridge `.sav` via the load-then-reset "Continue" pattern

## [0.2.2] — 2026-07-06

### Fixed
- fix: startup no longer overwrites game RAM with LTM's badge belief; RAM is the
  source of truth and LTM reconciles from it monotonically (#3)
- fix: `LongTermMemory._load` deep-copies defaults, fixing a latent aliasing bug
  where instances shared the same `gyms_beaten`/`milestones` lists

## [0.2.1] — 2026-07-06

### Fixed
- fix: `detect_context` no longer swallows read errors in broad `except` blocks,
  so a backend failure surfaces instead of being mislabeled as OVERWORLD/TRANSITIONING (#4)

## [0.2.0] — 2026-07-06

### Added
- feat: native in-process libmgba backend (`MGBA_BACKEND=native`, default) — drives
  the emulator directly via a cffi binding; no mGBA GUI, Lua, or mGBA-http required
- feat: optional live pygame viewer (`SHOW_WINDOW=true`) to watch the agent play
- test: hardware-free unit suite (Gen III decryption, state machine, type chart,
  reward, charset) plus pytest/ruff config
- ci: GitHub Actions — lint + tests on Python 3.11–3.13 and a macOS native-binding build

### Changed
- docs: README, CLAUDE.md, and `.env.example` rewritten around the native-first
  architecture; legacy mGBA-http retained as the `http` backend

### Fixed
- fix: removed unused imports and a duplicate move-type key that silently dropped an entry
- fix(build): disabled setuptools auto-discovery so the cffi extension builds in CI

[0.12.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.12.0
[0.11.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.11.1
[0.11.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.11.0
[0.10.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.10.0
[0.9.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.9.0
[0.8.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.8.0
[0.7.4]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.7.4
[0.7.3]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.7.3
[0.7.2]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.7.2
[0.7.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.7.1
[0.7.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.7.0
[0.6.3]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.6.3
[0.6.2]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.6.2
[0.6.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.6.1
[0.6.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.6.0
[0.5.5]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.5
[0.5.4]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.4
[0.5.3]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.3
[0.5.2]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.2
[0.5.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.1
[0.5.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.5.0
[0.4.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.4.0
[0.3.10]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.10
[0.3.9]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.9
[0.3.8]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.8
[0.3.7]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.7
[0.3.6]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.6
[0.3.5]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.5
[0.3.4]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.4
[0.3.3]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.3
[0.3.2]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.2
[0.3.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.1
[0.3.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.3.0
[0.2.2]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.2.2
[0.2.1]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.2.1
[0.2.0]: https://github.com/haggyroth/pokemon-agent/releases/tag/v0.2.0
