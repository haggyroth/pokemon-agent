# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions use [SemVer](https://semver.org/).

## [Unreleased]

### Added — PC boxes (drive the storage system)
- feat: `pc_boxes()` lists every stored Pokémon (read from `gPokemonStoragePtr` — 14 boxes × 30 × 80-byte BoxPokemon at
  +4; levels derived from experience via the new `knowledge/growth.py` + generated growth rates); `pc_deposit`,
  `pc_withdraw` (by species/nickname or `box:slot`, switching boxes) and `pc_swap` drive the real Pokémon Center PC menus:
  PC tile found by metatile behavior 0x83 → "Which PC?" → the storage-system menu (WITHDRAW/DEPOSIT) → the storage screen
  (cursor area 0x02039820 / position 0x02039821, found by RAM diff) → STORE/WITHDRAW → "which box?". Every change is verified
  against memory; it can't deposit the last battle-ready Pokémon; `pc_swap` validates the boxed mon first. Live: deposit,
  list, withdraw, and a withdraw from box 2 slot 14 each take ~1-4 s.

### Changed — training, level-up moves, trapped awareness, Pokédex (watched-run observations)
- feat(training): balance-mode `grind()` puts the TRAINEE in slot 1 (via `reorder_party`) so it fights alone and keeps
  all the XP — swapping a trainee in after a strong lead was sent out gave the lead half of every fight, which is why
  hours of grinding never caught the rest of the party up. The ace is put back in front afterwards, even after a
  time-limit abort (retried). Live: Bulbasaur L19 stayed L19 while Pikachu/Caterpie levelled.
- tune: the "lagging" threshold is looser — within ~25% of the top level (ratio 0.75, was 0.85): top L40 → nobody under L30.
- fix(moves): the level-up driver could only forget move SLOT 0 and declined everything else — the reason Venusaur kept
  refusing SolarBeam / Razor Leaf. It now steers the KNOWN MOVES summary to any slot (cursor read from 0x0203B16D, verified live
  for all four slots) and `knowledge/movelearn.py` scores moves by VALUE (power ×1.5 same-type, two-turn discount; sleep/
  paralysis/recovery/set-up ≫ Growl) — a clearly better move replaces the cheapest forgettable one, HM moves are never
  forgotten, at least two attacks are always kept.
- feat(battle): trapped awareness — `reader.read_battle_volatiles` decodes gBattleMons.status2 (Wrap/Bind/Fire Spin/Clamp/
  Whirlpool, Mean Look/Spider Web/Block, Torment, Confusion, Attract, Recharge). The observation shows `⛓ TRAPPED` etc.,
  and `flee_battle` / voluntary `switch_pokemon` refuse early with an explanation. Prompt gains a "special moves" note.
- feat(dex): Pokédex counts read from SaveBlock2 (`read_pokedex`, `read_dex_owned`); a SECONDARY objective in the
  readiness block and system prompt; the catch policy accepts a brand-new species even with a full party (it goes to the PC box).

### Fixed — viewer stutter between 1× and ~50× on macOS
- fix(viewer): emulation pacing and presentation are decoupled. The window used to be presented after EVERY
  emulated frame; on macOS `display.flip()` blocks on the display refresh while the window is visible (→ ~1×) but
  returns instantly when it is occluded or in Mission Control (→ ~50×) — hence the stutter and the speed-up in
  Mission Control. Now `VIEWER_FPS` paces frames against a running deadline (0 = uncapped, 60 = real time, 120 =
  2×), and the window is presented at most 60×/s, stamped after `flip()`. `flush_viewer()` shows the newest frame
  before each LLM wait so the window never freezes on a stale frame. Measured on this Mac with the window open:
  uncapped ≈ 41×.

### Changed — play like a trainer, not a travel agent
- feat: `knowledge/readiness.py` assesses the party's actual state — MUST heal (lead < 60% HP, anyone < 50%, a
  faint, attack PP nearly/completely gone) and SHOULD restock / catch (team < 4) / train (lagging members) /
  level (best below the next gym's ace − 1). The observation shows it as a "READINESS" block each overworld tick,
  replacing the separate team-size / imbalance / Brock nudges.
- feat: the model-facing `go_to` is travel only: it refuses to start a trip while a must-heal need exists (heal(),
  or `force=true`), still goes to Centers/Marts when hurt, and appends the overdue should-do items to its result.
  Internal callers (grind relocation, quests) are unaffected.
- feat: while travelling, `go_to` fights up to 4 ordinary wild battles per call for XP (training the lowest lagging
  member) when levelling is due, the lead is ≥ 60% and nothing must-heal — instead of fleeing every encounter.
- feat: system prompt gains "Play like a Pokémon trainer, not a travel agent" (heal → restock → catch → level →
  then travel; watch PP, rotate moves) and softens the flee-everything advice; `heal()` now also fires when attack
  PP is nearly gone. The zero-token bot follows the same pre-flight.

### Fixed — Pokémart enter/exit loop in Cerulean (run 20261114-101556)
- fix(nav): `_go_to_map` picked the nearest edge tile by distance even when it sat in another REGION of a split
  map (Cerulean's north edge at (28,0) is a pocket apart from the road at x=22..24), so the walk failed — and the
  "step off the edge" taps then walked the player straight back through the Mart door they had just left. Edge
  candidates are now limited to the player's own region, and the step taps only happen once the edge tile was
  actually reached.

### Added — party control, town healing, auto-catch, rival-loop guard
- feat: `reorder_party(first, second)` and `set_lead(pokemon)` drive Start → POKéMON → SWITCH out of battle
  (verified live; the cursor address doesn't track in "Move to where?", so it counts presses and verifies the
  resulting order, retrying). In battle, `switch_pokemon` already does the same.
- feat: the first arrival in any town with a Pokémon Center heals there (nurse conversation, which also sets the
  blackout respawn) — `ltm.pc_visited`, once per town. `_heal(force=True)` talks to Nurse Joy even at full HP.
- feat: `grind()`/balance mode auto-catch worthwhile wild Pokémon (catch policy), weakening gently (never the
  killing blow) and naming them from `knowledge.nicknames.auto_name` (species puns + a varied pool). Opt out with
  `grind(catch=false)`; the result lists what was caught.
- fix: no more rival retry loops — a trainer loss is remembered per map; the second loss on the same way in
  returns "Do NOT retry — grind elsewhere", and grass relocation heals once and picks a different route instead of
  walking back into the rival.
- fix(nav): Cerulean → the west has NO walking route (Route 4's east end is a pocket of one-way ledges; live-checked
  there's no walkable path from it to Mt. Moon). `go_to` now says so (Fly / long way) instead of looping on a phantom
  "South edge could not cross".

### Fixed — the road to Celadon (#185 item 5, Erika)
- fix(nav): when a route enters a gated map (Saffron's Tea guards, the Route 12/16 Snorlaxes) the re-plan now
  bans the WHOLE gated map (`route_to(avoid_maps=...)`) and gets 6 tries instead of blocking one edge at a time
  — Saffron alone has eight mat tiles, so Vermilion→Celadon ran out of retries and reported "needs Tea"
  instead of taking Cerulean → Route 9 → Rock Tunnel → Lavender → Route 8 → Underground Path → Route 7.
- fix(nav): `go_to('Gym')` first travels to the gym's CITY and takes the last hop from inside it. A gym door
  behind a Cut tree (Vermilion, Celadon) made the planner fall back to a region-blind route that marched into
  walls; from inside the city the stall branch auto-Cuts the tree.
- Zero-token bot: from the post-Surge state it now reaches **4 badges (Erika)** in 42 steps / ~215 s — Route 9's
  Cut tree, the dark Rock Tunnel, the Underground Path and Celadon's gym tree all handled by existing skills.
  The bot now advances (A) through blackout/transition screens instead of waiting, and levels the lone
  Venusaur to L40 for Erika (Grass vs Grass: only Normal Cut hits for neutral).

### Added — S.S. Anne → Cut → Vermilion Gym / Lt. Surge (#185 item 5c)
- feat: `get_cut()`: with the SS Ticket, boards the S.S. Anne (trainers auto-fought, resumable), cures the seasick
  Captain for HM01 (flag 0x237) and teaches Cut. Verified live (~67 s). go_to now uses Cut itself when a tree
  pins it (the Vermilion Gym door).
- feat: Vermilion Gym's two trash-can switches are READ from memory (VAR_TEMP_0/1 = can ids; script vars live
  at SaveBlock1+0x1000, new `reader.read_var`) and pressed directly — no searching, so a wrong second can can't
  reset the locks. `challenge_leader()` does this first in Vermilion.
- Zero-token bot (`tools/scripted_run.py --goal badges:3`) now beats Brock, Misty AND Lt. Surge: 57 steps,
  ~4 min wall, no model calls. Names added for the S.S. Anne maps.

### Added — Bill's SS-ticket quest + routing fixes (#185 item 5b)
- feat: `get_ss_ticket()` (agent/skills/quests.py): travels to Bill's Sea Cottage (Route 25, past Nugget
  Bridge — trainers auto-fought, resumable), talks to Bill-as-Clefairy (YES), runs his teleporter computer, and
  takes the SS Ticket from human Bill. Idempotent; verified live (~35 s). Cerulean's south/east exits are now a
  gated map (`knowledge/gates.py`) with a hint pointing at it; the Vermilion Gym is gated on Cut.
- fix(data): four map names were off by one (FRLG splits Route 21): `(3,43)` is Route 24 and `(3,44)` Route 25
  (not 25 / unnamed), and the Route 23 badge gate sat on Route 22. Added "Bill's Sea Cottage" (30,0).
- fix(nav): routing no longer goes through `SaffronCity_Connection` (3,11), a walled-off shell map — it sent
  Cerulean→Vermilion into Saffron's wall instead of the Underground Path.
- fix(nav): directional / arrow warps. When a warp tile doesn't fire, go_to now steps onto it from each side (and
  presses each direction while standing on an exit mat) before declaring the edge dead — the Underground Path
  stairs and a gym door mat after a fight both needed this.
- fix(budget): `get_ss_ticket` gets a larger frame budget (Nugget Bridge + the cutscene).

### Added — zero-token end-to-end runs (#185 item 5)
- feat: `tools/scripted_run.py` + `agent/scripted_policy.py`: a rule-based stand-in for the LLM (a fake
  OpenAI client) drives the REAL run loop — observations, rewards, ltm, logging, checkpoints, watchdog —
  with no model calls. From the real save it beats Brock AND Misty (Viridian → Pewter → Route 3 →
  Mt. Moon → Cerulean) in ~3 min of wall time. It found the next gap: **after Misty the way on is blocked
  until the SS Anne ticket from Bill** (Slowbro/Lass block Cerulean's south exit, a policeman the east).
- fix: `challenge_leader` had a Leader position only for Brock; it returned "I don't have this gym's Leader
  position" in Cerulean. All 8 gyms now have approach tiles from the decomp (Pewter + Cerulean verified;
  the puzzle gyms — Vermilion, Fuchsia, Saffron, Cinnabar, Viridian — unverified).

### Added — catch policy (#185 item 4)
- feat: `knowledge/catch_policy.py` weighs a catch's grinding debt (levels under the ~15% balance floor)
  against what it adds (strong evolution line, a new type). go_to only stops for worthwhile species, and
  the battle observation says "worth catching: <why>" or "NOT worth a ball: <why>" (e.g. the L5 Kakuna /
  L9 Zubat / L10 Geodude behind an L19 lead from run #2). The model can still catch anything.
- data: `knowledge/species_data.py` (base stat totals, types, best evolution BST for every species) is
  generated from the decomp by `tools/gen_species_data.py`.
- fix: catching with a full party reports that it went to the PC box (it said "on your team").

### Added — live regression tests + eval scenarios (#185 item 3)
- test: `tests/live/` replays watched-run bugs on the real ROM (zero-PP grind, watchdog vs the old status
  spam, catch nickname vetting/naming, broke-free ball, Disabled move). Skipped automatically without the
  binding/ROM/fixtures (CI). Fixtures live in gitignored `saves/live/`; `tests/live/README.md` documents
  them and the staging tricks (`harness.py`: `patch_mon`, `wild_battle`, ...).
- eval: `party_balanced` goal; scenarios `catch_a_pokemon` and `balance_party`.
- fix: when a tool hits its hard time limit while still making progress (long `grind`), the message now
  says so and to call it again, instead of claiming it "isn't working".

### Added — checkpoints + resume (#185 item 2)
- feat: the run saves an emulator state every `CHECKPOINT_EVERY` decision ticks (default 20, ~19 KB each, newest
  5 kept) and a permanent one per new badge, under `logs/runs/<ts>/checkpoints/` with a `latest.json`.
  `RESUME=latest` (or `RESUME=<path.ss1>`) continues a cancelled/stuck run from its last checkpoint.

### Added — skill watchdog (#185 item 1)
- feat: every tool call runs under a frame budget (`agent/budgets.py`, `game/watchdog.py`): a hard cap
  (default ≈25 game-minutes) and a no-progress detector (map/position/party growth/money/foe HP unchanged
  for ≈4 game-minutes). A tripped skill returns an explanation to the model instead of spinning with no
  LLM in the loop (run #2: one `train_party()` call ran 26 minutes). Frames, not wall time, so it behaves
  the same under the paced viewer. `SkillBudgetExceeded` is a BaseException so skills' broad
  `except Exception` fallbacks can't swallow it; trips are logged as `watchdog` events in run.jsonl.

### Fixed — catch() after a ball breaks free
- fix(catch): the post-catch Yes/No probe (nudges Down/Up) no longer runs while the battle action menu is up —
  it flicked the cursor Bag↔Run on screen — and a broke-free ball now returns after ~20 idle iterations at the
  menu instead of pressing B through all 60/120 (over a minute when watched). A successful catch only
  flickers through the menu value (≤6 iterations, live-traced), so naming is unaffected.

### Changed — zero-PP loop + grind/train_party merge (second watched run)
- fix(battle): `_best_damaging_move` no longer falls back to a status move. With attacks out of PP the
  grind/train loop picked Growl/Harden forever (run 20261113-222109: one `train_party()` call spun for
  26 minutes). New `_no_attack_turn`: all PP gone → Struggle; a teammate that can still attack →
  switch to it; wild → flee; trainer with nobody left → best move with PP.
- fix(data): the move tables missed ~100 real moves (Thunder Shock was spelled "Thundershock", plus
  Horn Attack, Take Down, Facade, …), which read as "no power". `knowledge/move_data.py` is generated
  from the decomp (`tools/gen_move_data.py`) and merged under the curated tables.
- feat: ONE grinding tool. `grind(level)` raises the lead; `grind()` with no level balances the team
  (the old `train_party`, kept as an alias). Both heal themselves at a Pokémon Center (HP or attack PP
  low, resuming after wild/trainer interruptions) and walk back to grass — up to 8 round-trips per call.
- fix(heal): `heal()` no longer refuses "full HP" when attacks are at 0 PP (a Center restores PP).
- fix(grind): an open field menu/party screen is closed with B instead of pressing A inside it.
- feat(nicknames): the model invents names with personality — tool/system prompt/new-species obs push for
  puns, pop-culture, dramatic titles (never the species name or a number, none alike). `catch()` vets the
  name BEFORE throwing a ball (`knowledge/nicknames.py`): untypeable chars are sanitized, a bland /
  too-long / duplicate name is refused once with the reason, then accepted. Party nicknames are now read
  from the struct so the obs lists names already taken. Verified live (typed `Mr. Zap!`).
- feat(obs): status moves read `Status — deals NO damage` (Leech Seed used to show ×4 SUPER); a
  `⚠ NO ATTACKING MOVE WITH PP` line names teammates that can attack; low attack PP warns to heal;
  repeating a no-damage move twice in `use_move` adds a warning.

### Added — run logging + fixes from the first watched 500-call run (gemma4:31b-cloud)
- feat(logging): every `python main.py` run writes `logs/runs/<timestamp>/run.jsonl` (+ `meta.json`):
  one line per decision tick (observation, state, reasoning, actions), per LLM call (tokens,
  reasoning, requested tools) and per tool call (args, result, seconds, map/pos/HP afterwards).
- feat: `train_party()` keeps the whole team within ~15% of the top level — works the grass like
  `grind`, sends the lowest lagging mon in first, lets a strong teammate finish tough fights (XP is
  shared with every participant), pauses when the trainee is hurt. Observation gets a
  "Team imbalance" warning; `challenge_leader()` warns once about a lopsided team.
- feat: Disable handling — `gDisableStructs` (0x02023E0C, found live) is read, the move shows as
  `DISABLED (n turns)` and is never suggested/used; the move-menu refusal fallback backs out after two
  refused commits instead of looping forever.
- feat: `use_move('Struggle')` / automatic Struggle when every move is out of PP or Disabled.

### Fixed
- fix(switch): the party-screen row for a switch target is now taken from the party as read AFTER
  the screen settles (the game physically reorders gPlayerParty to battle order) instead of applying
  gBattlePartyCurrentOrder on top — forced switches to the 2nd-slot mon failed every time. Cursor
  movement is lag-tolerant (waits for two identical reads).
- fix(battle): `advance_dialog` in a battle drives the text to the next decision (it used to answer
  "a battle started" and press nothing: 191 wasted calls through a gym trainer's send-outs); after a
  KO `use_move` settles the win/send-out text itself.
- fix(battle): the opponent is read from the live battler (gBattleMons[1]), not gEnemyParty[0] — the
  second mon of a trainer showed as the fainted first one.
- fix(move-learn): level-ups are tracked per species, so a party reorder (Pikachu L5 -> Ivysaur L18 in
  slot 0) no longer arms the driver on a stale offer ('declined Sleep Powder' x8). The state diff pairs
  mons by identity, so reordering no longer reports phantom level-ups.

### Added (work in progress — see the WIP PR; partly unverified)
- feat: `fly_to(town)` (party sub-menu -> region map; live-verified to all 11 towns) and Flash via
  `use_hm('Flash')` (verified in the real Rock Tunnel: lights the cave, flag set, control returns).
- feat: story/capability gates in `go_to` (`knowledge/gates.py`): Silph Scope, Poké Flute, Tea, Surf,
  Strength, 8 badges — explains what to get instead of walking into a locked road.
- feat: Silph card-key door / Pokémon Mansion switch tiles from the decomp (`tools/gen_puzzle_tiles.py`)
  and a `walk_to` solver; live map buffer (gBackupMapLayout) + collision-aware passability.

### Verified live in this batch
- Pokémon Mansion: one `walk_to` onto a barrier tile presses the statue (A -> YES), the barrier opens, and it
  arrives. Silph Co. 2F: `walk_to` opened card-key door 1 and door 2 and arrived behind each (note: the
  game checks FLAG_HIDE_SILPH_CO_5F_CARD_KEY 0x192, not the bag item). `go_to` explains story gates.
- passability: script-opened barriers (elevation 0 / collision 0 that differ from the ROM) are walkable;
  a wall goal on a puzzle map now yields 'no path' so the solvers run instead of bumping forever.

### Fixed
- fix: in-battle party switching used an unreliable cursor variable (0x020207FE read 0/1/0 while the
  real cursor went 0/1/2 with 3 mons): forced switches stalled in a slow loop. Now uses gPartyMenu.slotId
  (0x0203B0A9). Live-verified: forced + 5 voluntary switches across 3 Pokémon.
- fix: **regression from #176** — the battle action menu remembers its cursor, so after a mid-fight Potion
  (Bag) the next A reopened the Bag and every following fight stalled ("tough trainer battle isn't
  resolving"). `_battle_advance` now points the cursor at FIGHT first and backs out of full-screen
  menus with B. Also: the mid-fight Potion is cross-checked against party HP, `_exit_battle_menus` /
  `_advance_to_control` never press A inside a full-screen menu, and a forced replacement screen is
  resolved inside `_advance_to_control`. Bisected: #175 fine, #176 broke the Pewter->Cerulean trip.

### Added
- feat: `teach_move(tm, pokemon?, forget?)` — teaches a TM/HM via the TM Case (`agent/skills/tmhm.py`).
  Start -> Bag -> Key Items -> TM CASE -> OPEN -> TM/HM -> USE -> party target -> (full moveset: YES ->
  summary screen -> pick the move to forget). Reads the live state at every stage (callback, list
  scroll+row, party slot, summary cursor) and confirms the outcome (move learned, forgotten move gone,
  TM consumed / HM kept). Compatibility comes from the decomp (`tools/gen_tmhm_learnsets.py` ->
  `knowledge/tmhm_learnsets.py`) so it never mashes A into the wrong Pokémon; the default forget policy
  never drops an HM move or the last attack. Without `pokemon` it tries each party member in order.

### Added
- feat: field (overworld) `use_item` — Potions, Revive, status cures and Repel via Start -> Bag -> Items
  -> USE -> party target, confirmed by item count / HP / status (`agent/skills/items.py`). `use_item`
  gains an optional `target` and picks whoever needs it when omitted.
- feat: `use_hm` — Surf (starts at the nearest shore), Cut, Rock Smash, Strength (`agent/skills/hm.py`).
  Surf is path-aware: `walk_to`/`go_to_map` treat water as walkable while surfing (`gPlayerAvatar.flags`
  bit 3), start Surf by themselves when only water blocks the way, and `go_to` surfed Pallet -> Cinnabar.
- feat: generated `CONN_RANGES` (which edge tiles of a seamless connection actually cross) and a
  spread-out edge-tile search in `_go_to_map`.

### Fixed
- fix: the Bag list index is `scroll + cursor` (0x0203AD0A + 0x0203AD04). The cursor alone is the row
  within the visible window, so pockets with more than ~6 entries selected the WRONG item (battle
  `use_item` included).

### Fixed
- fix: forced replacement screen after your lead faints. The party screen can't be cancelled, so
  `close_menus` pressed B 14× and failed and `use_move` said "menu did not respond". Now detected
  (`game.menu.forced_party_screen`): `close_menus`/`use_move`/the `MENU:` hint say to
  `switch_pokemon` (with the healthy roster), `switch_pokemon` works from that screen, and
  `_auto_fight` auto-sends the healthiest mon.
- fix: `grind`/`_auto_fight` drink a Potion (Potion→Super→Hyper, max 3/battle) when the active mon
  drops below 35% instead of fighting it to ~3% HP.
- fix: idle-in-battle stall. `use_move` now ends with both HPs and "Still in battle — call
  use_move again (do NOT press A or wait)", and the observation adds an `IDLE IN BATTLE` warning with
  the best move after 3 non-battle actions in a row (the overnight run burned ~20 calls on
  press A / wait_frames mid gym-trainer fight).

### Added
- feat: naming-screen driver (`game/naming.py`) + `catch(nickname=…)` and `enter_name(name)` tools.
  Types key by key across the UPPER/lower/symbol pages (cursor read from RAM, START jumps to OK)
  and confirms every letter against the Gen III text buffer, self-correcting dropped presses.
  The post-catch Yes/No is detected with a settle+bidirectional probe on the battle cursor
  (it clamps and initialises lazily); without a nickname the prompt is still declined.

### Changed
- feat: generic region-aware routing for EVERY map (`tools/gen_regions.py` ->
  `knowledge/map_regions.py`, replaces the hand-built Mt. Moon data). Regions are derived
  from the decomp (walkable-tile flood fill, ledge hops, Cut/Rock Smash/boulder/Snorlax
  objects as blockers, warp pairing, connection offsets), so Rock Tunnel, Silph Co., Pokémon
  Tower/Mansion, Seafoam, etc. route like Mt. Moon with no per-cave fixes. `route_to` tries the
  strict region graph first and falls back to the optimistic coarse graph for HM/puzzle
  obstacles the tiles can't express; `go_to` learns hops that keep failing and re-plans around
  them. `DUNGEON_MAPS` is now derived (map bank 1). Re-run the generator after bumping the decomp.

### Fixed
- fix: Mt. Moon routing. Each cave floor is several disconnected regions joined by ladders
  (B1F has four); the router treated floors as one node, so `go_to('Cerulean City')` looped on
  "No walkable path to (45,4)" from B1F for ~100 calls in an overnight run. Region labels +
  per-warp arrival regions (`knowledge/cave_regions.py`, from live flood fills + the decomp
  warp pairing) now route 1F -> B1F -> B2F -> B1F -> Route 4 east. Also: the Route 4 Pokémon
  Center exit lands on the west half (it had no route out at all).
- fix: `walk_to` engages an NPC that is the sole chokepoint (trainers in B2F's 2-wide corridor)
  instead of reporting the target unreachable.

### Added
- feat: menu / prompt / dialogue driver (`game/menu.py`, `agent/skills/menu.py`) with new
  tools `open_menu`, `answer_prompt`, `advance_dialog`, `close_menus`. Start-menu rows are
  read from `sStartMenuCursorPos`/`sStartMenuOrder` (0x020370F4..), small menus (Yes/No,
  Save prompt) from `sMenu.cursorPos` (0x0203ADE6, probed for liveness since it goes stale).
  The observation carries a `MENU:` hint. Bag/Party list cursors live in heap memory, so
  those screens are opened/closed deterministically but navigated with the D-pad.
- docs: Ollama endpoint example (`gemma4:31b-cloud`) in `.env.example`.

## [0.31.2]

### Fixed
- fix: `use_move` advances the post-battle state to overworld control (battle). A battle
  end often lingers in a menu/fade (a blackout warp, a trainer's post-battle line, a
  gym's badge script) that reads as IN_MENU/TRANSITIONING; use_move used to return
  "Battle is over" immediately and no-op every subsequent call while walk_to couldn't
  move, parking the agent in a post-battle menu (the "stuck in the Pewter Gym" stall).
  It now presses A to real OVERWORLD before returning. Reproduced: a loss to Brock left
  the agent stuck IN_MENU 25+ steps; now recovers in 1–2 calls.

## [0.31.1]

### Fixed
- fix: `use_move` targets the ACTIVE battler's moves, not the lead's (battle). Once a
  non-lead mon is out (a switch, or a forced send-out after the lead faints), the FIGHT
  menu shows the active mon's moves — but the code indexed `gPlayerParty[0]` (the lead),
  so it could land on an empty slot (a caught Pidgey with two moves "trying to use a slot
  with no move learned"). Now reads the active mon from `gBattleMons[0]`
  (moves/PP/HP/species) for validation, slot, PP-drop, and the faint check; `_auto_fight`
  picks from it too; empty move names are rejected. Verified live: a switched-in Weedle
  attacks with its own moves and the lead's are rejected.

## [0.31.0]

### Added
- feat: `go_to` now auto-fights trainer battles it hits while travelling (it already
  auto-flees wilds), so a trainer-dense dungeon like Mt. Moon is one call instead of
  dozens of LLM round-trips. It hands back to the model only when judgement is needed —
  a loss/blackout, a fight that didn't finish on autopilot (tough trainer or a forced
  switch after a faint), or a win that left the lead below the travel HP floor. Move-learn
  and evolution mid-fight are handled inside the auto-fight; wild-battle handling (catch
  offer + auto-flee) is unchanged. Live: one `go_to` cleared Viridian Forest's Bug
  Catchers to Pewter in a single call.

## [0.30.11]

### Fixed
- fix: Mt. Moon traversal no longer stalls (nav). (1) `walk_to` regains real overworld
  control before pathing — in a lingering post-battle/dialog/fade state the D-pad is
  absorbed, so it used to sit pinned in place reporting "Stopped at (x,y)" (the same root
  as the Poké Center stall, hit here after the cave's trainer battles). (2) A go_to stall
  inside a cave (new `DUNGEON_MAPS`: Mt. Moon 1F/B1F/B2F) now returns maze guidance
  ("keep pushing to the far-side exit, don't backtrack") instead of the wrong "gated —
  you need an HM" message that made the agent turn back. Surfaced by the `second_badge`
  eval (agent reached Mt. Moon 1F but stalled at 44%).

## [0.30.10]

### Fixed
- fix: `heal()` now returns in real overworld control, fixing the Poké Center exit stall
  (nav). After healing, the game lingers IN_MENU for ~80 frames (nurse's closing dialogue
  + heal fade); the old fixed 4 A-taps handed control back while the player was still on
  the counter tile flagged IN_MENU, where `walk_to` can't move — the agent sat re-issuing
  `walk_to(exit)` for ~50s until the fade cleared on its own. `heal()` now advances to
  OVERWORLD before returning. Surfaced by the `second_badge` eval.

## [0.30.9]

### Fixed
- fix: `use_move` no longer loops on a lingering move-learn offer (battle). After a mon
  declines a level-up move (e.g. Bulbasaur's Poison/Sleep Powder at L15), `gMoveToLearn`
  and `learnMoveState` both linger, so the driver re-declined the same move every turn
  instead of attacking — the `second_badge` eval stalled ~83 min on Route 3 and capped
  out at badge 1. The driver now refuses to re-drive an offer id it already resolved.
  Also closes an evolution timing gap in the model-driven path: `use_move`/`_auto_fight`
  now wait for the post-battle evolution scene to launch and complete it (verified live:
  a levelled-up Bulbasaur evolves to Ivysaur through `use_move`, not just grind).

## [0.30.8]

### Fixed
- fix: Pokémon now evolve instead of having the evolution cancelled (battle). A level-up
  triggers a post-battle evolution scene (its own callback `CB2_EVOLUTION`) whose context
  flickers into IN_MENU — so the model dismissed it with B, which *cancels* the evolution.
  The agent now detects the scene and advances it with A only (never B), in the main loop
  and after each auto-fought battle. Verified live: a levelled-up Bulbasaur evolves to
  Ivysaur instead of staying Bulbasaur.

## [0.30.7]

### Fixed
- fix: routing to Cerulean now goes through Mt. Moon instead of into the mountain wall
  (nav). Route 4 is one map split by Mt. Moon — the agent arrives from Route 3 on the
  west half, but Cerulean's seam is on the east half, reachable only by traversing the
  cave. BFS took the 1-hop east seam and `walk_to` kept hitting the wall, stalling the
  agent at badge 1. Route 4 is now a split map (west/east regions) so routing enters the
  Mt. Moon warp and emerges on the far side.

## [0.30.6]

### Fixed
- fix: `switch_pokemon` is now reliable on every turn, not just the first switch of a
  battle (#120). The in-battle party menu lists mons in battle order
  (`gBattlePartyCurrentOrder`), which is permuted after each switch; the tool navigated
  to the target's field slot, valid only pre-switch — afterward it landed on the active
  mon and the game rejected the SHIFT as "already in battle" (the "keeps selecting the
  active Pokémon" symptom). Now translates field slot → battle-order display slot
  (`Addr.BATTLE_PARTY_ORDER`). Also removes the mis-diagnosed once-per-battle fast-fail
  (the "stuck" callback `0x0811eb79` is just the normal `CB2_UpdatePartyMenu`). Verified
  live: three consecutive switches in one battle all land.

## [0.30.5]

### Fixed
- fix: `use_move` no longer flails when the lead faints mid-turn (#68). If a faster foe
  KOs our lead the same turn we pick a move, our PP never drops — the resolution loop
  used to hold `A` through the forced send-out prompt (blindly confirming a switch) and
  return a misleading "Could not use…". It now breaks when `party[0]` faints
  (`current_hp==0`) or changes identity (`species_id`) and returns a truthful
  observation directing the model to send out its next Pokémon with `switch_pokemon`.

## [0.30.4]

### Fixed
- fix: history hygiene (#69). A failed LLM call (likelier now with `LLM_TIMEOUT`) no
  longer leaves a dangling user turn — `step()` rolls back everything it appended if
  the call raises, so retries don't pile up unanswered turns and inflate token cost.
  `trim_messages` now hard-resets to the system prompt + last user group when no
  boundary is in the trim window, instead of returning oversized history.

### Changed
- chore(ci): SHA-pin `actions/checkout` (v4.3.1) and `actions/setup-python` (v5.6.0)
  to commit SHAs, and add `.github/dependabot.yml` (github-actions + pip) so the pins
  and requirements still auto-update (#72).

## [0.30.3]

### Fixed
- fix: reject garbage party reads on the battle-load frame. The encrypted party
  substructs momentarily decrypt to nonsense there (out-of-range species/move ids),
  which made `use_move` fail with "not a known move"; `read_party` now plausibility-
  checks each mon and reuses the last-known-good party until the data settles (#58).
- fix(perf): `BattleJournal` caches parsed records (keyed on file mtime/size) so
  `get_loss_lessons` no longer re-parses the whole journal every in-battle step (#70).
- fix(security): the screenshot frame defaults to a per-process temp dir instead of a
  fixed shared-/tmp name — avoids a symlink-follow truncate (CWE-379) and concurrent-run
  clobber (#67).

## [0.30.2]

### Fixed
- fix: bound the transition auto-advance so a stuck game state can't bypass the run
  guardrails. A `TRANSITIONING`-stuck main loop tapped A and `continue`d forever, before
  the step/wall-clock budget checks — an eval hung ~3h there. Now the wall-clock cap is
  enforced inline and the auto-A is capped so a genuinely stuck state falls through to a
  normal step (LLM re-engages, budgets run). Complements the 0.28.0 guardrails. (#122)

## [0.30.1]

### Fixed
- fix: `switch_pokemon` fails fast on the corrupted second-open. Deep dive found the
  real cause of "switching keeps selecting the active mon": the first switch of a battle
  works, but after ANY switch the party-menu subsystem is corrupted for the rest of that
  battle (every subsequent open is non-interactive to A — `callback2` stuck at
  `0x811eb79`). It now bails quickly with a clear "reliable only once per battle" message
  instead of mashing a dead menu, and the tool description warns upfront. Proper fix
  needs disassembly-level RE (#120). (#121)

## [0.30.0]

### Added
- feat: `switch_pokemon(target)` — swap the active Pokémon mid-battle (by species name
  or 1-based slot), so a built team can actually be used to bring in a type-favorable
  or healthier mon. Drives the action-menu POKEMON option + party menu + SHIFT, and
  verifies the swap via the active battler's species (`gBattleMons[0].species`); fails
  cleanly (never a wrong-switch) otherwise. Known limitation: switching a second time
  back to the just-active/slot-0 mon can fail cleanly (party menu reopens into a
  non-interactive state) — the common case (bring in a different mon) works, 3/3. (#118)

## [0.29.0]

### Added
- feat: team-building. `go_to` now stops once on a wild NEW species (not already on the
  team) while the team is small (<4) with Poké Balls, so the model can `catch()` a roster
  instead of auto-fleeing every wild battle; re-issuing `go_to` skips it (flees) and
  offers the next new species (no loop; fast travel resumes once the team is built). The
  enemy read is settled + validated to dodge the battle-load garbage read (#58). Plus an
  overworld obs nudge when the party is <3. Groundwork for using a team: in-battle
  switching. (#117)

## [0.28.0]

### Added
- feat: run guardrails + overworld PP awareness (from an 11-hour runaway eval). New
  `LLM_TIMEOUT` (per-request, default 180s) bounds a single chat completion; new
  `MAX_WALL_SECONDS` / `run_episode(max_wall_s=…)` is a hard wall-clock cap (result
  reason `max_wall`); the eval runner always bounds wall-clock (2h ceiling) and gains
  a `second_badge` scenario. Plus `knowledge.battle.overworld_pp_summary()` adds a
  `Lead moves: … PP:n` obs line and a LOW-PP warning (≤5 attacking PP) so the agent
  heals to restore PP instead of grinding its moves to Struggle. (#116)

## [0.27.0]

### Added
- feat: `use_item(item)` skill + tool uses a Bag item on the active lead in battle — a
  Potion (Super/Hyper/Max) to restore HP, or a status cure (Antidote, Paralyze Heal,
  Awakening, Burn/Ice/Full Heal). Reuses the battle-bag nav, walks the live list cursor
  (`Addr.BAG_LIST_CURSOR`) to the item, and uses it on the lead, self-verifying by the
  item being consumed / HP rising / status clearing. Prevents blackouts by healing
  mid-fight. Verified live (Potion heal + Antidote cure). (#115)

## [0.26.0]

### Added
- feat: `pick_up_items()` skill + tool collects ground item balls (free Potions,
  Antidotes, Poké Balls, TMs). Item balls are object events with gfx id
  `OBJ_EVENT_GFX_ITEM_BALL` (92); scanning loaded `gObjectEvents` for that id lists
  the uncollected balls on screen. Walks to each, faces it, picks it up, and confirms
  via the bag total; the observation surfaces visible balls so the model calls it.
  Verified live (Viridian Forest Potion). (#114)

## [0.25.0]

### Added
- feat: `go_to` stall detection breaks the travel retry loop. Its resumable "call
  go_to again" message looped the agent forever when the path was story-gated (e.g.
  leaving Pewter east at 0 badges, the guard NPC shuffles the player back to the gym,
  which reads as "progress"). Now tracks consecutive calls that end at the same map
  without arriving, and after 3 returns actionable guidance — redirect to the local
  unbeaten Gym (`go_to('Gym')` → `challenge_leader()`) when that's the gate, else
  explain the way is gated (story event / missing HM). Resets on arrival, real
  progress, and after advising, so long journeys are unaffected (#113)

## [0.24.1]

### Fixed
- fix: the move-learn driver no longer forfeits trainer battles. gMoveToLearn LINGERS
  after a declined level-up move, so the driver kept re-engaging every turn of Brock's
  Onix, starved `use_move` of a move menu, and the agent left the gym at 0 badges (then
  looped at the Pewter guard). Now armed on a lead level-up edge (disarmed after
  driving) with a live-delete-box safety net, and it terminates on the overworld /
  an idle-timeout instead of the STALE `gBattlerControllerFuncs` value that read
  CHOOSE_ACTION mid-victory-sequence. Verified: `first_badge` eval now beats Brock and
  earns the Boulder Badge (#112)

## [0.24.0]

### Added
- feat: deterministic in-battle move-learn driver — when a Pokémon at 4 moves levels
  into a new move, the agent now resolves the "Delete a move?" prompt by the shipped
  forget policy instead of mashing A/B and forgetting a move at random (which was
  overwriting damaging moves with status moves, e.g. Sleep Powder over Tackle).
  `_maybe_drive_learn` (gated on `gMoveToLearn`, set ~16 frames before the box) takes
  over in `use_move` + `_auto_fight` and frame-steps the flow with anti-bleed so an A
  never slips through the ~2-frame interactive window. Decline = mash B to
  `learnMoveState == 4` then A gated on the offered move changing (handles back-to-back
  same-level prompts); accept supported for slot 0, non-0 slots stay decline-safe.
  Adds `Addr.LEARN_MOVE_STATE` (`0x02023FE3`). Verified live: Bulbasaur's L15 double
  (Poison + Sleep Powder) declines both and keeps Tackle, 3/3 (#111)

## [0.23.1]

### Fixed
- fix: `use_move` no longer declares "Battle is over" on a transient state (a Gym
  Leader's fainted Pokémon being replaced by its next one) — it gates on
  `gBattleOutcome`. This caused the agent to leave a gym after beating only the
  first Pokémon, land at 0 badges, and get stuck at the Pewter guard (#110)

## [0.23.0]

### Added
- feat: move-forget decision policy (`knowledge/movelearn.py`) — decides which move
  to forget on a level-up, never dropping the last damaging move and never stacking a
  second status move (correctly declines Poison/Sleep Powder for Bulbasaur, keeping
  Tackle). Plus `Addr.MOVE_TO_LEARN` (`0x02024022`, derived+verified). The
  foundation for the deterministic in-battle move-learn handler (follow-up: the
  decline press is timing-sensitive on back-to-back same-level prompts) (#109)

## [0.22.2]

### Fixed
- fix: startup badge reconciliation is now authoritative to the cartridge — it drops
  badges the journal claims but the save doesn't have (with a warning), not just adds.
  A journal left ahead of the save deadlocked the agent (it thought a gym was beaten,
  headed on, and the Pewter guard NPC marched it back) — this was the real cause of the
  "city-edge loop". Mid-session stays monotonic so a load_state retry can't un-earn.
  Pewter guidance notes the east exit is guarded until Brock is beaten (#108)

## [0.22.1]

### Fixed
- fix: Poké Center / building exit stall — `go_to` out of a Center looped forever
  ("stuck at (5,4)"). The exit doormat spans 3 warp tiles but only the center warps;
  routing picked a side tile. Now warp hops snap to the door-center, and `walk_to`'s
  warp-nudge waits for the fade to complete (it was abandoning the in-progress warp).
  Verified: heal → route → Center → route all complete in one call each (#107)

## [0.22.0]

### Added
- feat: status-aware battle observation — shows the opponent's status
  ("Opponent: CATERPIE [Bug] — ASLEEP"), flags status-inflicting moves as
  "WON'T STICK (already statused)", and steers to a damaging move when the foe
  already has a major status (fixes the Sleep Powder spam loop). New
  `STATUS_INFLICTING_MOVES`; prompt says use one status move at most.
- feat: `tools/reset_journal.py` — resets `progress.json` to the battery save's
  pre-game state (keeping starter/parcel) and clears `battles.jsonl`, so the
  journal can't drift ahead of the cartridge save (startup reconcile only adds badges).

### Fixed
- fix: Leech Seed (and other over-time moves) are no longer ranked as the "Best
  move" — they deal no direct damage (added to `STATUS_MOVES`) (#106)

## [0.21.0]

### Added
- feat: `catch()` skill — throws a Poké Ball at a wild Pokémon deterministically
  (opens the battle Bag, switches to the Balls pocket, throws, reports the outcome).
  Reliability came from driving the bag across the turn-varying action-menu handler,
  a self-verifying throw (press A until a ball is consumed), and resolving via
  `gBattleOutcome` (`0x02023E8A`, =7 CAUGHT) rather than the laggy party count.
  Stress-verified live (3 caught / 2 broke free / 0 stranded). The obs flags a NEW
  SPECIES worth catching; weaken first for a better rate; buy balls with `shop()`.
  Completes the Shopping→Catching workstream (#105)

## [0.20.1]

### Added
- feat: deterministic `shop()` skill — travels to a Poké Mart, talks to the clerk,
  and buys the badge-gated par-level restock automatically (no model menu-driving).
  Driven through `sShopData` (`0x02039934`): navigates the item list via
  `itemList[scrollOffset+selectedRow]`, dials quantity by watching `itemPrice`, and
  confirms each purchase by the bag count rising, retrying through fade/text drops.
  Verified live at Viridian Mart (5 Balls + 6 Potions + 2 Antidotes, ¥3000) (#104)

## [0.20.0]

### Added
- feat: shopping foundation — the agent reads its money and consumable inventory
  (`read_money`/`read_bag`, decrypting FRLG's XOR-obfuscated money + item quantities
  via `gSaveBlock2->encryptionKey`) and a badge-gated purchase policy
  (`knowledge/shopping.py`) with par levels: Poké→Great(≥3)→Ultra(≥5) balls,
  Potion→Super(≥3)→Hyper(≥5), status cures→Full Heal(≥4), Revive(≥4). The obs now
  shows money/balls/potions and, at a Mart, an affordable restock recommendation.
  Deterministic `buy` skill + wild-catching land next (#103)

## [0.19.9]

### Fixed
- fix: `go_to("Gym")` now routes to the next gym you still owe (first Leader not in
  `gyms_beaten`), not the nearest one. After Brock it sent the agent back into the
  beaten Pewter Gym or to Viridian's gym (the final gym, locked until 7 badges);
  now it heads to Cerulean/Misty. Viridian/Giovanni is only chosen once it's next (#92)

## [0.19.8]

### Fixed
- fix: **badges now register** — `read_badges()` read `SaveBlock1 + 0x41C` (the bag-items
  region), so a Gym win never counted and `badges_earned` was 0 across every run ever.
  Corrected to the decomp-derived badge-flag byte `SaveBlock1 + 0xFE4`
  (`flags[]@0xEE0` + `FLAG_BADGE01_GET(0x820)>>3`), bit0=Boulder..bit7=Earth. Verified
  on hardware; cross-checked against the known-good key-items offset. This is why the
  agent looped at Pewter after beating Brock — the badge never registered (#101)

## [0.19.7]

### Fixed
- fix: the agent no longer loops re-challenging a Gym Leader it already beat. A new
  `GYM_MAP_LEADER` map lets the obs tell a beaten gym from an unbeaten one — beaten
  gyms now say "ALREADY BEATEN, leave and head to your next objective" instead of
  nudging `challenge_leader()`. Building-interior guidance also names the badge-gated
  next objective (so it has a destination on exit), and the system prompt gained an
  "Advancing objectives" rule against re-doing finished goals (#100)

## [0.19.6]

### Fixed
- fix: the live viewer now paces playback to `VIEWER_FPS` (default 60→120, ≈2× GBA
  speed) by sleeping in `render()` instead of frame-skipping the draw while the
  emulator ran full-speed — motion no longer flashes by incomprehensibly. Pacing is
  scoped to windowed mode only, so headless runs stay full speed (#99)

## [0.19.5]

### Fixed
- fix: ledge-aware pathfinding + deterministic grind grass-relocation — closes the
  Route 1 self-trap from the badge run. `walk_to`/`find_path` now hop one-way ledges
  (`MB_JUMP_*` 0x38–0x3B) in their facing direction (a single D-pad press lands 2
  tiles across) instead of treating them as walls, and `grind()` travels to the
  nearest grass route itself (`map_graph.nearest_grass`) when no grass is reachable
  rather than bouncing a "go find grass" message the model ignored (#98)

## [0.19.4]

### Added
- feat: real tall-grass detection — `TilemapReader.metatile_behavior()` reads
  `MapLayout → Tileset → metatileAttributes` (`MB_TALL_GRASS=0x02`), verified on
  hardware (grass=0x2, path=0x0). `grind()` now routes the player onto the nearest
  real grass tile and only paces while actually standing on grass, instead of
  guessing the patch from the last encounter tile and drifting off it (#97)

## [0.19.3]

### Added
- feat: `challenge_leader()` skill — starts the gym-leader battle deterministically
  (walk to the tile below the Leader, face them, press A to talk → battle). The model
  reached Brock's tile but kept pressing Up without ever pressing A; this closes that
  gap. Obs + prompt now say to call `challenge_leader()` inside a gym (#96)

## [0.19.2]

### Fixed
- fix: the live viewer (`SHOW_WINDOW=true`) no longer throttles the run — `VIEWER_FPS`
  now caps the display refresh by frame-skipping instead of pacing the emulator, so
  the emulator runs full speed (grind/battles are thousands of frames) while the
  window redraws at ~VIEWER_FPS. Watching a run is now roughly as fast as headless (#95)

## [0.19.1]

### Fixed
- fix: `go_to` traverses trainer-filled dungeons (#81) — a trainer spotting the
  player leaves the game in an engagement state that reads as IN_MENU, where
  walk_to/go_to can't move, so the agent was pinned inside Viridian Forest despite a
  clear path to the exit. `go_to` now advances a dialog/menu/engagement into
  overworld-or-battle before routing (trainer → the model fights it, wild → auto-flee),
  and treats a hop that moved the player as progress rather than "stuck". Verified:
  Pallet → Pewter now crosses the forest deterministically. Generalizes to Mt. Moon,
  Rock Tunnel, and the game's other trainer-heavy mazes

## [0.19.0]

### Added
- feat: gym-leader approach navigation — inside a gym `go_to` is a no-op, so the
  observation and prompt now point the agent at the tile just below the Leader
  (`GYM_LEADER_APPROACH`, e.g. Pewter (6,2)→(6,6) below Brock) and say to `walk_to`
  up to them, not `go_to` (#91)

### Fixed
- fix: the live viewer window no longer kills the run — a backgrounded pygame window
  on macOS emits spurious QUIT events that (as a KeyboardInterrupt subclass) stopped
  long runs minutes in. Closing the window now tears it down but the run continues
  headless; Ctrl-C the terminal to stop (#91)

## [0.18.1]

### Added
- feat: `grind(target_level)` skill — while standing in tall grass, wanders to trigger
  wild battles and auto-fights each one (best damaging move) until the lead reaches the
  target level, orbiting the last encounter tile to stay in the patch and pausing at
  <35% HP. Turns the LLM's ~1 level / 15 min manual grind into ~1 level / ~10 s. Use
  `grind(13)` to get Vine Whip before Brock (#90)

## [0.18.0]

### Added
- feat: `first_badge` (Brock) eval scenario + gym-prep/grinding guidance — the save's
  Bulbasaur is L8 with no Vine Whip, so the system prompt now tells the model to grind
  wild Pokémon to ~L13 before Brock (fight in tall grass with use_move, don't flee),
  and the observation nudges when the lead is under-levelled for the first gym (#89)

## [0.17.0]

### Added
- feat: `go_to` auto-flees wild battles while travelling (#81) — it flees wild
  encounters itself and keeps going, so one `go_to` walks through a whole
  route/forest/cave instead of handing every battle back to the model (the ~27-min
  Viridian Forest crossing collapses). It stops only on a TRAINER battle (win first),
  when the lead's HP drops below 30% after a fight (heal() first), on a failed
  escape, or if blocked. Verified Pallet → Viridian in one call, zero wild battles
  punted. Deliberate catching will come via a dedicated `catch()` skill (#88)

## [0.16.1]

### Changed
- chore: the `reach_pewter` eval reached Pewter City end-to-end with the real LLM
  (XPASS: goal, steps=27, stuck_ratio=6%, ~27 min) — the Route 2 / Viridian Forest
  gauntlet is solved by #59 region routing plus `heal()`/`flee_battle()` to survive
  and skip wild encounters. Dropped the scenario's `xfail=#59` (closes #59)

## [0.16.0]

### Added
- feat: `flee_battle()` skill — runs from a WILD battle by driving the action menu
  to RUN (detect `gBattlerControllerFuncs[0]==0x08030611`; write action cursor
  `0x02023FF8=3`, hold A; confirm the battle ends). Guards trainer battles, retries
  across turns if the escape roll fails. The battle observation now says whether you
  can flee (wild) or must fight (trainer), and a system-prompt rule steers the model
  to flee encounters when just travelling (the fast way through Viridian Forest, #81)
  or when HP is low. Hardware-verified 4/4 wild flees (#85)

## [0.15.0]

### Added
- feat: `heal()` skill — travels to the nearest Pokémon Center (resumable), walks
  to Nurse Joy, and advances the heal dialogue until the party is at full HP (talk
  tile (7,4) across the counter; YES/NO defaults to YES). A `⚠ Lead HP low` obs
  nudge below 40% outside battle and a system-prompt rule tell the model when to
  call it. Blackout/Nurse-Joy recovery now advances the whiteout dialogue several
  A-presses per pass (was one) and stops as soon as the party revives (#84)

## [0.14.4]

### Fixed
- fix: validate the SaveBlock1/map pointer before dereferencing in
  `read_badges`/`read_player_pos`/`read_current_map` (#66) — on a title/reset/
  transition frame the pointer is stale, so the reads returned garbage positions
  and a badge flicker the reward logic could misread as newly-earned; they now
  return the last good value. Also: honest comment on reward persistence (#71),
  log NPC-read failures instead of silently pathing through NPCs (#73), and
  document the read-only-RAM-plus-move-cursor write policy (#74)

## [0.14.3]

### Fixed
- fix: `walk_to` no longer bails with a bogus "No walkable path" right after a warp
  (#81). It was reading the previous map's grid before the new map finished loading
  (the player's real position is out of bounds of the stale grid). Now it detects the
  out-of-bounds/stale case and settles until the map loads, and retries a `None` path
  within its attempt budget instead of giving up on the first try. The agent now walks
  from the Viridian Forest entrance deep into the maze (the deeper forest traversal is
  still tracked in #81)

## [0.14.2]

### Fixed
- fix: confirm real player control on boot (#79) — `drive_into_gameplay` declared
  success at the first full-color frame, but the FRLG recap has bright frames and a
  fade before control, so ~half of boots handed back a frozen player on a garbage
  tilemap. It now verifies the player responds to input (`_has_control`) and retries
  the boot up to 4× (5/5 fresh boots now reach movable control)
- fix: turn-vs-step in `walk_to` — Gen III's first D-pad press only turns the
  character; the blocked-tile logic from 0.14.1 mistook every corner for an obstacle
  and stalled (e.g. inside the Viridian Forest gate). Each move now presses up to
  twice (turn, then step) before flagging a tile blocked. The agent now traverses
  Pallet → Route 1 → Route 2 → the forest gate → into Viridian Forest

## [0.14.1]

### Fixed
- fix: region-aware routing through gated maps (#59) — Route 2 is one map id split
  by Viridian Forest's gate buildings, so `go_to("Pewter City")` thrashed forever on
  the sealed north edge. A curated split-map overlay expands such maps into
  per-region nodes (`(3,20,"N")`/`(3,20,"S")`) so `route_to` routes THROUGH the
  forest gates; `node_for()` maps a live position to its region. Also: `walk_to`
  now marks a tile blocked and replans around it when a step fails (obstacles the
  ROM passability grid can't see — object events, ledges, cut trees — which was the
  Viridian Forest traversal stall and the general "ledges/trees" navigation issue)

## [0.14.0]

### Added
- feat: eval harness (`python -m evals`) — scores a run against a goal + step
  budget with an `EpisodeResult` scorecard (pass/fail, steps, reward, stuck-ratio,
  LLM calls, tokens), writing `logs/eval/<ts>.json`. Scenarios + goals live in
  `evals/` (pure, CI-tested); `reach_pewter` is an `xfail` documenting #59. A
  Tier-1 no-LLM nav-skill check (`RUN_NAV_EVALS=1 pytest tests/test_nav_scenarios.py`)
  isolates routing bugs from reasoning bugs (#77)

### Changed
- refactor: extracted `build_runtime()` + `run_episode(goal, max_steps)` from
  `main()`'s decision loop (the eval harness reuses the exact same loop, so eval
  and real runs never diverge); `LongTermMemory`/`BattleJournal` accept a path
  override so a scenario runs against isolated scratch files (#77)

## [0.13.0]

### Added
- feat: spend controls for cloud LLM endpoints — `MAX_LLM_CALLS` and `TOKEN_BUDGET`
  env caps stop the run cleanly (like `MAX_STEPS`); the agent tracks cumulative
  LLM calls + prompt/completion tokens and prints a run summary (steps, reward,
  calls, tokens) on every exit; a startup warning fires when `LLM_BASE_URL` is
  non-local and no run cap is set (#64)

### Fixed
- fix: run safety — `save_state`/`load_state` return a real success bool on both
  backends and the tool executor reports the true outcome instead of always
  claiming success; the blackout handler fires the loss penalty once per blackout
  (was every tick) and advances the game's own respawn when no save state exists
  instead of looping on a no-op reload (#63)

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
